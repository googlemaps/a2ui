# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MAUI Agent with template-based latency optimization."""

import asyncio
import inspect
import json
import logging
import pathlib
from types import SimpleNamespace
from typing import Any, AsyncIterable
import uuid

from a2a.types import DataPart
from a2a.types import Part
from google.adk import skills as adk_skills
from google.adk.agents import run_config
from google.adk.agents.llm_agent import LlmAgent
from google.adk.events.event import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.runners import Runner
from google.genai import types
import pydantic

from a2ui.a2a.parts import create_a2ui_part
from a2ui.schema.manager import (
    A2uiSchemaManager,
)
from agent import MAUIAgent
from agent_config import AgentConfig
from agent_config import FallbackMode, GroundingMode
from extractor import DirectionsExtractorSchema
from extractor import LocalSearchExtractorSchema
from merger import merge_template
from router_config import IntentClass
from router_config import ROUTER_SYSTEM_INSTRUCTION
from router_config import RouterClassification
from template_tool import (
    BaseTemplateTool,
    RenderDirectionsTemplateTool,
    RenderLocalSearchTemplateTool,
    RenderTextOnlyTemplateTool,
    STATE_RENDERED_A2UI_DATA,
    STATE_RENDERED_A2UI_PARTS,
)
from vertex_grounding_extractor import VertexGroundingExtractor

logger = logging.getLogger(__name__)
_SKILL_BASE_PATH = pathlib.Path(__file__).parent / "skills"
_SHARED_INSTRUCTIONS_PATH = (
    pathlib.Path(__file__).parent / "shared" / "instructions"
)


_LOCAL_SEARCH_SKILL_NAME = "local-search-template-response"
_LOCAL_SEARCH_TEMPLATE_NAME = "local_search"
_LOCAL_SEARCH_SURFACE_PREFIX = "local-search-surface"

_DIRECTIONS_SKILL_NAME = "directions-template-response"
_DIRECTIONS_TEMPLATE_NAME = "directions"
_DIRECTIONS_SURFACE_PREFIX = "directions-surface"

_SUPPORTED_INTENTS = {IntentClass.LOCAL_SEARCH, IntentClass.DIRECTIONS}

_GROUNDED_TEXT_BASE_INSTRUCTION = """\
You are an expert location and navigation assistant with access to Google Maps tools.

## Core Rules
1. **Accuracy & Grounding**: Use Google Maps tools to look up real-time places, business hours, amenities, contact details, routes, and weather. NEVER hallucinate place facts, locations, or operational details.
2. **Parallel Tool Execution**: When researching multiple entities, neighborhoods, routes, or options, emit ALL independent tool calls in parallel within your initial response turn. Only serialize calls when Step 2 strictly depends on data returned by Step 1.
3. **Minimize Round-Trips**: Gather necessary place facts efficiently and emit independent queries in parallel. Only perform follow-up tool turns when subsequent calls strictly depend on data returned from earlier steps (e.g., retrieving details for specific place IDs or searching along a computed route polyline). Avoid redundant follow-up queries for details already retrieved.
4. **Helpful & Actionable Answers**: Fully address all constraints in the user's prompt (e.g., parking, pricing, specific dietary options, bag policies). If tools return generic listings that lack specific policy details, supplement with known facts while noting any uncertainty.
5. **No A2UI Tags**: Return standard plain text/markdown only. Do NOT output A2UI tags or JSON surfaces.
"""


class MAUIAgentWithTemplates(MAUIAgent):
  """MAUI Agent extending base with server-side layout templates and query intent routing."""

  def __init__(self, base_url: str, config: AgentConfig | None = None) -> None:
    self.config = config or AgentConfig()
    super().__init__(base_url=base_url, model_name=self.config.generic_model)
    self.router_client = LiteLlm(model=self.config.router_model)
    self.extractor_client = LiteLlm(model=self.config.template_model)
    self.fallback_client = LiteLlm(model=self.config.generic_model)
    self._vertex_extractor: VertexGroundingExtractor | None = None

  def _get_vertex_extractor(self) -> VertexGroundingExtractor:
    """Lazily initializes and caches the VertexGroundingExtractor."""
    if self._vertex_extractor is None:
      self._vertex_extractor = VertexGroundingExtractor(
          project_id=self.config.gwgm.project_id,
          location=self.config.gwgm.location,
          model_id=self.config.gwgm.model_id,
          shared_guidelines=self._load_shared_guidelines(),
      )
    return self._vertex_extractor

  def _build_runner(self, agent: LlmAgent) -> Runner:
    runner = super()._build_runner(agent)
    # The extractor agent runs inside a dynamically created runner.
    # We must enable auto_create_session to prevent SessionNotFoundError
    # since we don't pre-create the session for this runner.
    runner.auto_create_session = True
    return runner

  def _on_tool_error(
      self,
      tool: Any,
      args: dict[str, Any],
      tool_context: Any,
      error: Exception,
  ) -> dict[str, Any] | None:
    """Callback for tool errors during extraction."""
    # pylint: disable=unused-argument
    if tool.name in (
        "render_local_search_template",
        "render_directions_template",
        "render_text_only_template",
        "set_model_response",
    ) and isinstance(error, pydantic.ValidationError):
      logger.warning(
          "Extractor tool '%s' failed validation: %s. "
          "Returning error to model for self-correction.",
          tool.name,
          error,
      )
      return {
          "error": (
              f"Validation failed: {error}. Please correct the arguments"
              " and try again."
          )
      }
    return None

  def _load_shared_guidelines(self) -> str:
    """Loads shared conversational text style guidelines if available."""
    shared_guidelines_path = (
        _SHARED_INSTRUCTIONS_PATH / "shared_style_guidelines.md"
    )
    if shared_guidelines_path.exists():
      try:
        with open(shared_guidelines_path, "r", encoding="utf-8") as f:
          return f.read()
      except (OSError, ValueError) as e:
        logger.warning("Failed to load shared style guidelines: %s", e)
    return ""

  def _build_dynamic_extractor_agent(
      self,
      skill_name: str,
      schema_manager: A2uiSchemaManager | None = None,
  ) -> LlmAgent:
    """Builds an extractor agent loaded directly with the target skill's prompt."""
    skill_dir = _SKILL_BASE_PATH / skill_name
    skill = adk_skills.load_skill_from_dir(skill_dir)
    skill_instructions = skill.instructions
    shared_guidelines = self._load_shared_guidelines()
    if shared_guidelines:
      skill_instructions = f"{skill_instructions}\n\n{shared_guidelines}"

    # Extractors use template_model, generic UI uses generic_model
    if skill_name.endswith("-template-response"):
      model_name = self.config.template_model
    else:
      model_name = self.config.generic_model

    logger.info(
        f"Building extractor agent for '{skill_name}' using model: {model_name}"
    )

    tools = [self.make_grounding_lite_mcp()]
    target_tool = None
    if skill_name == _LOCAL_SEARCH_SKILL_NAME:
      target_tool = RenderLocalSearchTemplateTool(
          schema_manager=schema_manager,
          max_list_size=self.config.max_list_size,
          surface_id_prefix=_LOCAL_SEARCH_SURFACE_PREFIX,
      )
    elif skill_name == _DIRECTIONS_SKILL_NAME:
      target_tool = RenderDirectionsTemplateTool(
          schema_manager=schema_manager,
          max_list_size=self.config.max_list_size,
          surface_id_prefix=_DIRECTIONS_SURFACE_PREFIX,
      )

    generate_content_config = None
    if target_tool:
      tools.append(target_tool)

      workaround_instruction = (
          "IMPORTANT: After using any other tools needed to complete the task,"
          f" you MUST call {target_tool.name} to render the final response"
          " interface."
      )
      if skill_name == _LOCAL_SEARCH_SKILL_NAME:
        workaround_instruction += (
            "\nCRITICAL CONSTRAINT: You MUST extract and display at most"
            f" {self.config.max_list_size} of the most relevant places. Do not"
            " mention, recommend, or extract more than"
            f" {self.config.max_list_size} places in your text response or your"
            f" {target_tool.name} tool call."
        )
      skill_instructions = f"{skill_instructions}\n\n{workaround_instruction}"

      if self.config.extractor_thinking_budget > 0:
        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=self.config.extractor_thinking_budget
            )
        )
        logger.info(
            "Applying template extractor thinking budget limit:"
            f" {self.config.extractor_thinking_budget} tokens"
        )

    if schema_manager:
      instruction = schema_manager.generate_system_prompt(
          role_description=skill_instructions,
          include_schema=True,
          include_examples=False,
          validate_examples=False,
      )
    else:
      instruction = skill_instructions

    return LlmAgent(
        model=LiteLlm(model=model_name),
        name="maui_agent",
        description="An extractor agent executing specific Maps tool tasks",
        instruction=instruction,
        tools=tools,
        output_schema=None,  # Keep output_schema as None in LlmAgent
        generate_content_config=generate_content_config,
        on_tool_error_callback=self._on_tool_error,
        after_tool_callback=self._after_tool_callback,
    )

  async def _run_extractor(
      self,
      runner: Any,
      agent: LlmAgent,
      current_message: types.Content,
      session_id: str,
  ) -> tuple[list[Part] | None, list[str], dict[str, Any] | None]:
    """Runs the extractor agent and collects its output (rendered parts or text)."""
    rendered_parts: list[Part] | None = None
    rendered_data: dict[str, Any] | None = None
    full_content_list = []

    async for event in runner.run_async(
        user_id=self._user_id,
        session_id=session_id,
        run_config=run_config.RunConfig(
            streaming_mode=run_config.StreamingMode.SSE
        ),
        new_message=current_message,
        # Initialize session state.
        state_delta={
            "expression": "{expression}",
            "base_url": self.base_url,
        },
    ):
      if hasattr(event, "get_function_calls"):
        for fc in event.get_function_calls():
          if fc.name in (
              "render_local_search_template",
              "render_directions_template",
              "render_text_only_template",
              "set_model_response",
          ):
            logger.info(
                "--- AGENT_WITH_TEMPLATES: Observed %s tool call with args:"
                " %s ---",
                fc.name,
                fc.args,
            )

            target_tool = None
            for t in agent.tools:
              if getattr(t, "name", None) == fc.name:
                target_tool = t
                break

            if target_tool and hasattr(target_tool, "run_async"):
              tool_ctx = SimpleNamespace(state={})
              try:
                tool_result = await target_tool.run_async(
                    args=fc.args, tool_context=tool_ctx
                )
                if (
                    isinstance(tool_result, dict)
                    and "error" not in tool_result
                    and STATE_RENDERED_A2UI_PARTS in tool_ctx.state
                ):
                  rendered_parts = tool_ctx.state[STATE_RENDERED_A2UI_PARTS]
                  rendered_data = tool_ctx.state.get(STATE_RENDERED_A2UI_DATA)
                  logger.info(
                      "--- AGENT_WITH_TEMPLATES: Template tool %s succeeded!"
                      " Captured %d rendered parts. ---",
                      fc.name,
                      len(rendered_parts),
                  )
                  break
              except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "--- AGENT_WITH_TEMPLATES: Tool execution error: %s ---", e
                )

      if event.content and event.content.parts:
        if event.partial:
          for p in event.content.parts:
            if p.text:
              full_content_list.append(p.text)
        else:
          full_content_list.clear()
          for p in event.content.parts:
            if p.text:
              full_content_list.append(p.text)

    if rendered_parts is None and getattr(runner, "session_service", None):
      get_session_fn = getattr(runner.session_service, "get_session", None)
      if callable(get_session_fn):
        try:
          res = get_session_fn(
              app_name=getattr(runner, "app_name", ""),
              user_id=self._user_id,
              session_id=session_id,
          )
          if inspect.isawaitable(res):
            session = await res
            if session and getattr(session, "state", None):
              rendered_parts = session.state.get(STATE_RENDERED_A2UI_PARTS)
              rendered_data = session.state.get(STATE_RENDERED_A2UI_DATA)
        except Exception as e:  # pylint: disable=broad-exception-caught
          logger.debug("Could not retrieve session from session_service: %s", e)

    return rendered_parts, full_content_list, rendered_data

  async def _run_extractor_and_merge(
      self,
      skill_name: str,
      template_name: str,
      surface_id_prefix: str,
      cleaned_query: str,
      session_id: str,
      ui_version: str | None = None,
  ) -> tuple[list[Part] | None, str | None, dict[str, Any] | None]:
    """Runs the dynamic extractor agent and returns rendered template parts."""
    del template_name, surface_id_prefix
    # 1. Resolve catalog schema manager
    schema_manager = self._schema_managers.get(ui_version)

    # 2. Build the extractor agent and runner
    agent = self._build_dynamic_extractor_agent(
        skill_name,
        schema_manager=schema_manager,
    )
    runner = self._build_runner(agent)

    # 3. Setup user query message
    current_message = types.Content(
        role="user", parts=[types.Part.from_text(text=cleaned_query)]
    )

    # 4. Run extractor runner, collecting output
    rendered_parts, full_content_list, rendered_data = (
        await self._run_extractor(runner, agent, current_message, session_id)
    )

    if rendered_parts is not None:
      return rendered_parts, None, rendered_data
    else:
      raw_text = "".join(full_content_list)
      return None, raw_text, None

  async def stream(
      self, query: str, session_id: str, ui_version: str | None = None
  ) -> AsyncIterable[dict[str, Any]]:
    """Streams responses, routing via intent classifier to template extractors.

    Args:
        query: User input query string.
        session_id: Context session ID.
        ui_version: A2UI protocol version if requested.

    Yields:
        Update dictionaries compatible with A2A TaskExecutor.
    """
    if not ui_version:
      logger.info("No ui_version provided. Routing to base text streaming.")
      async for part in super().stream(query, session_id, ui_version):
        yield part
      return

    intent, cleaned_query = await self._classify_intent(query)

    if intent == IntentClass.OTHER_SPATIAL:
      if self.config.fallback_mode == FallbackMode.DYNAMIC:
        logger.warning(
            "Router matched OTHER_SPATIAL and fallback_mode is DYNAMIC. "
            "Falling back to Dynamic UI flow."
        )
        async for part in super().stream(query, session_id, ui_version):
          yield part
        return
      else:
        logger.info(
            "Router matched OTHER_SPATIAL and fallback_mode is TEXT. "
            "Executing grounded text fallback flow."
        )
        final_parts = await self._handle_grounded_text_fallback(
            cleaned_query, session_id
        )
        yield {
            "is_task_complete": True,
            "parts": final_parts,
        }
        return

    elif intent == IntentClass.TEXT_ONLY:
      logger.info("Executing fast text response flow for TEXT_ONLY intent.")
      final_parts = await self._handle_text_only(cleaned_query, session_id)
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
      return

    elif intent in _SUPPORTED_INTENTS:
      async for part in self._handle_extracted_intent(
          intent, cleaned_query, session_id, ui_version
      ):
        yield part
      return

    # Fallback for un-implemented spatial intents or validation failures
    if self.config.fallback_mode == FallbackMode.TEXT:
      logger.info(
          "FallbackMode.TEXT enabled: routing intent %s to grounded text"
          " handler.",
          intent,
      )
      final_parts = await self._handle_grounded_text_fallback(
          cleaned_query, session_id
      )
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
      return

    logger.warning(
        "Intent %s not supported by template extractors. Falling back to base"
        " UI stream.",
        intent,
    )
    async for part in super().stream(query, session_id, ui_version):
      yield part

  async def _classify_intent(self, query: str) -> tuple[IntentClass, str]:
    """Classifies the query intent and returns the intent and cleaned query."""
    logger.info(
        "Routing query: '%s' using model %s",
        query,
        self.config.router_model,
    )
    try:
      router_config = {
          "system_instruction": ROUTER_SYSTEM_INSTRUCTION,
          "response_mime_type": "application/json",
          "response_schema": RouterClassification,
      }
      if self.config.router_thinking_budget > 0:
        router_config["thinking_config"] = types.ThinkingConfig(
            thinking_budget=self.config.router_thinking_budget
        )

      req = LlmRequest(
          contents=[
              types.Content(
                  role="user", parts=[types.Part.from_text(text=query)]
              )
          ],
          config=types.GenerateContentConfig(**router_config),
      )

      router_response_text = ""
      async for res in self.router_client.generate_content_async(req):
        if res.content and res.content.parts:
          for p in res.content.parts:
            if p.text:
              router_response_text += p.text

      logger.info("Router response content: %s", router_response_text)
      classification = RouterClassification.model_validate_json(
          router_response_text
      )
      intent = classification.intent
      cleaned_query = classification.query
      logger.info(
          "Intent classified: %s (Cleaned Query: '%s')", intent, cleaned_query
      )
      return intent, cleaned_query
    except Exception as e:  # pylint: disable=broad-exception-caught
      logger.warning(
          "Intent routing failed: %s. Defaulting to TEXT_ONLY.",
          e,
          exc_info=True,
      )
      return IntentClass.TEXT_ONLY, query

  def _wrap_in_text_only(self, text: str, session_id: str) -> list[Part]:
    """Wraps plain text in a text_only template Part list."""
    short_id = uuid.uuid4().hex[:8]
    merged_actions = merge_template(
        "text_only",
        {
            "text": text,
            "surface_id": f"text-only_{session_id}-{short_id}",
        },
    )
    return [create_a2ui_part(action) for action in merged_actions]

  def _get_grounded_text_instruction(self) -> str:
    """Builds system instruction for grounded text responses."""
    return _GROUNDED_TEXT_BASE_INSTRUCTION

  async def _handle_grounded_text(
      self, cleaned_query: str, session_id: str, client: LiteLlm
  ) -> list[Part]:
    """Generates a grounded plain text response using the provided model client with GroundingLite tools."""
    system_instruction = self._get_grounded_text_instruction()
    if self.config.grounding_mode == GroundingMode.GWGM:
      vertex_extractor = self._get_vertex_extractor()
      response = await vertex_extractor.client.aio.models.generate_content(
          model=self.config.gwgm.model_id,
          contents=cleaned_query,
          config=types.GenerateContentConfig(
              system_instruction=system_instruction,
              tools=[types.Tool(google_maps=types.GoogleMaps())],
          ),
      )
      answer_text = response.text or ""
      if not answer_text:
        answer_text = (
            "I'm sorry, I encountered an issue retrieving location details"
            " right now."
        )
      return self._wrap_in_text_only(answer_text, session_id)

    generate_content_config = None
    if (
        client == self.extractor_client
        and self.config.extractor_thinking_budget > 0
    ):
      generate_content_config = types.GenerateContentConfig(
          thinking_config=types.ThinkingConfig(
              thinking_budget=self.config.extractor_thinking_budget
          )
      )

    tools = [self.make_grounding_lite_mcp()]
    agent = LlmAgent(
        model=client,
        name="maui_grounded_text_agent",
        description="Agent for text responses with Maps grounding",
        instruction=system_instruction,
        tools=tools,
        generate_content_config=generate_content_config,
    )
    runner = self._build_runner(agent)
    current_message = types.Content(
        role="user", parts=[types.Part.from_text(text=cleaned_query)]
    )
    answer_text = ""
    try:
      async for event in runner.run_async(
          user_id=self._user_id,
          session_id=session_id,
          run_config=run_config.RunConfig(
              streaming_mode=run_config.StreamingMode.SSE,
          ),
          new_message=current_message,
          state_delta={
              "expression": "{expression}",
              "base_url": self.base_url,
          },
      ):
        if event.content and event.content.parts:
          if event.partial:
            for p in event.content.parts:
              if p.text:
                answer_text += p.text
          else:
            answer_text = ""
            for p in event.content.parts:
              if p.text:
                answer_text += p.text
    except Exception as e:
      logger.warning("Grounded text generation failed: %s", e)

    if not answer_text:
      answer_text = (
          "I'm sorry, I encountered an issue retrieving location details"
          " right now."
      )

    return self._wrap_in_text_only(answer_text, session_id)

  async def _handle_text_only(
      self, cleaned_query: str, session_id: str
  ) -> list[Part]:
    """Generates a plain text response for TEXT_ONLY intent using template_model with grounding."""
    return await self._handle_grounded_text(
        cleaned_query, session_id, client=self.extractor_client
    )

  async def _handle_grounded_text_fallback(
      self, cleaned_query: str, session_id: str
  ) -> list[Part]:
    """Generates a grounded plain text response for fallback/complex spatial queries using generic_model."""
    return await self._handle_grounded_text(
        cleaned_query, session_id, client=self.fallback_client
    )

  async def _handle_gwgm_template(
      self,
      intent: IntentClass,
      query: str,
  ) -> AsyncIterable[dict[str, Any]]:
    """Handles supported template intents using Vertex Grounding with Google Maps."""
    if intent == IntentClass.LOCAL_SEARCH:
      schema_cls = LocalSearchExtractorSchema
      template_name = _LOCAL_SEARCH_TEMPLATE_NAME
      surface_prefix = _LOCAL_SEARCH_SURFACE_PREFIX
    elif intent == IntentClass.DIRECTIONS:
      schema_cls = DirectionsExtractorSchema
      template_name = _DIRECTIONS_TEMPLATE_NAME
      surface_prefix = _DIRECTIONS_SURFACE_PREFIX
    else:
      raise ValueError(f"Unsupported intent for GwGM extractor: {intent}")

    logger.info(
        "Using VertexGroundingExtractor for intent %s with schema %s",
        intent,
        schema_cls.__name__,
    )
    vertex_extractor = self._get_vertex_extractor()
    extracted_template_params = await vertex_extractor.extract(
        query, schema_cls, max_places=self.config.max_list_size
    )

    template_payload = extracted_template_params.model_dump(exclude_none=True)
    if not template_payload.get("surface_id"):
      surface_suffix = uuid.uuid4().hex[:8]
      template_payload["surface_id"] = f"{surface_prefix}-{surface_suffix}"

    merge_options: dict[str, Any] = {}
    if template_name == _LOCAL_SEARCH_TEMPLATE_NAME:
      merge_options["max_list_size"] = self.config.max_list_size

    merged_actions = merge_template(
        template_name, template_payload, **merge_options
    )
    a2ui_parts = [create_a2ui_part(action) for action in merged_actions]
    yield {
        "is_task_complete": True,
        "parts": a2ui_parts,
    }

  async def _handle_mcp_template(
      self,
      intent: IntentClass,
      query: str,
      session_id: str,
      ui_version: str | None = None,
  ) -> AsyncIterable[dict[str, Any]]:
    """Handles template intents using the MCP extractor agent."""
    if intent == IntentClass.LOCAL_SEARCH:
      skill_name = _LOCAL_SEARCH_SKILL_NAME
      template_name = _LOCAL_SEARCH_TEMPLATE_NAME
      surface_prefix = _LOCAL_SEARCH_SURFACE_PREFIX
    elif intent == IntentClass.DIRECTIONS:
      skill_name = _DIRECTIONS_SKILL_NAME
      template_name = _DIRECTIONS_TEMPLATE_NAME
      surface_prefix = _DIRECTIONS_SURFACE_PREFIX
    else:
      raise ValueError(f"Unsupported intent for MCP extractor: {intent}")

    merged_parts, fallback_text, _ = await self._run_extractor_and_merge(
        skill_name=skill_name,
        template_name=template_name,
        surface_id_prefix=surface_prefix,
        cleaned_query=query,
        session_id=session_id,
        ui_version=ui_version,
    )

    if merged_parts is not None:
      yield {
          "is_task_complete": True,
          "parts": merged_parts,
      }
      return
    else:
      logger.warning(
          "Template extraction failed for intent %s. "
          "Always falling back to plain text response.",
          intent,
      )
      if not fallback_text:
        final_parts = await self._handle_grounded_text_fallback(
            query, session_id
        )
      else:
        final_parts = self._wrap_in_text_only(fallback_text, session_id)
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
      return

  async def _handle_extracted_intent(
      self,
      intent: IntentClass,
      query: str,
      session_id: str,
      ui_version: str | None = None,
  ) -> AsyncIterable[dict[str, Any]]:
    """Handles intents that use template extractors."""
    if intent not in _SUPPORTED_INTENTS:
      raise ValueError(f"Unsupported intent for extractor: {intent}")

    logger.info("Router matched %s. Dispatching template extractor.", intent)

    if self.config.grounding_mode == GroundingMode.GWGM:
      async for response_chunk in self._handle_gwgm_template(intent, query):
        yield response_chunk
      return

    async for response_chunk in self._handle_mcp_template(
        intent, query, session_id, ui_version
    ):
      yield response_chunk
