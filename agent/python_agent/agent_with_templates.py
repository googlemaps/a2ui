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
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.runners import Runner
from google.adk.tools.set_model_response_tool import SetModelResponseTool
from google.genai import types
import pydantic

from a2ui.a2a.parts import create_a2ui_part
from a2ui.schema.manager import (
    A2uiSchemaManager,
)
from python_agent.agent import MAUIAgent
from python_agent.agent_config import AgentConfig
from python_agent.agent_config import FallbackMode
from python_agent.extractor import DirectionsExtractorSchema
from python_agent.extractor import LocalSearchExtractorSchema
from python_agent.merger import merge_template
from python_agent.router_config import IntentClass
from python_agent.router_config import ROUTER_SYSTEM_INSTRUCTION
from python_agent.router_config import RouterClassification

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

_EXTRACTOR_SCHEMAS = {
    _LOCAL_SEARCH_SKILL_NAME: LocalSearchExtractorSchema,
    _DIRECTIONS_SKILL_NAME: DirectionsExtractorSchema,
}
_SUPPORTED_INTENTS = {IntentClass.LOCAL_SEARCH, IntentClass.DIRECTIONS}


class MAUIAgentWithTemplates(MAUIAgent):
  """MAUI Agent extending base with server-side layout templates and query intent routing."""

  def __init__(self, base_url: str, config: AgentConfig | None = None) -> None:
    self.config = config or AgentConfig()
    super().__init__(base_url=base_url, model_name=self.config.generic_model)
    self.router_client = LiteLlm(model=self.config.router_model)
    self.extractor_client = LiteLlm(model=self.config.template_model)

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
    if tool.name == "set_model_response" and isinstance(
        error, pydantic.ValidationError
    ):
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

  def _build_dynamic_extractor_agent(
      self,
      skill_name: str,
      schema_manager: A2uiSchemaManager | None = None,
  ) -> LlmAgent:
    """Builds an extractor agent loaded directly with the target skill's prompt."""
    skill_dir = _SKILL_BASE_PATH / skill_name
    skill = adk_skills.load_skill_from_dir(skill_dir)
    skill_instructions = skill.instructions
    shared_guidelines_path = (
        _SHARED_INSTRUCTIONS_PATH / "shared_style_guidelines.md"
    )
    if shared_guidelines_path.exists():
      try:
        with open(shared_guidelines_path, "r", encoding="utf-8") as f:
          shared_guidelines = f.read()
        skill_instructions = f"{skill_instructions}\n\n{shared_guidelines}"
      except (OSError, ValueError) as e:
        logger.warning("Failed to load shared style guidelines: %s", e)

    # Extractors use template_model, generic UI uses generic_model
    if skill_name.endswith("-template-response"):
      model_name = self.config.template_model
    else:
      model_name = self.config.generic_model

    logger.info(
        f"Building extractor agent for '{skill_name}' using model: {model_name}"
    )

    tools = [self.make_grounding_lite_mcp()]
    output_schema = _EXTRACTOR_SCHEMAS.get(skill_name)

    generate_content_config = None
    if output_schema:
      # Manually inject SetModelResponseTool
      set_response_tool = SetModelResponseTool(output_schema)
      tools.append(set_response_tool)

      # Manually append instruction
      workaround_instruction = (
          "IMPORTANT: You have access to other tools, but you must provide"
          " your final response using the set_model_response tool with the"
          " required structured format. After using any other tools needed to"
          " complete the task, always call set_model_response with your final"
          " answer in the specified schema format."
      )
      if skill_name == _LOCAL_SEARCH_SKILL_NAME:
        workaround_instruction += (
            "\nCRITICAL CONSTRAINT: You MUST extract and display at most"
            f" {self.config.max_list_size} of the most relevant places. Do not"
            " mention, recommend, or extract more than"
            f" {self.config.max_list_size} places in your text response or your"
            " set_model_response tool call."
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
    )

  async def _run_extractor(
      self,
      runner: Any,
      agent: LlmAgent,
      current_message: types.Content,
      session_id: str,
  ) -> tuple[dict[str, Any] | None, list[str]]:
    """Runs the extractor agent and collects its output (structured or text)."""
    parsed_json_data = None
    full_content_list = []

    async for event in runner.run_async(
        user_id=self._user_id,
        session_id=session_id,
        run_config=run_config.RunConfig(
            streaming_mode=run_config.StreamingMode.SSE
        ),
        new_message=current_message,
        # Initialize session state.
        # "expression" is required to prevent KeyError during ADK's prompt
        # state injection, as the A2UI catalog schema contains "${expression}"
        # placeholders. "base_url" is passed for consistency with the main
        # agent session state.
        state_delta={
            "expression": "{expression}",
            "base_url": self.base_url,
        },
    ):
      if hasattr(event, "get_function_calls"):
        for fc in event.get_function_calls():
          if fc.name == "set_model_response":
            logger.info(
                "Intercepted set_model_response tool call with args: %s",
                fc.args,
            )

            # Find SetModelResponseTool in agent tools
            target_tool = None
            for t in agent.tools:
              if getattr(t, "name", None) == "set_model_response":
                target_tool = t
                break

            if target_tool and hasattr(target_tool, "run_async"):
              try:
                noop_tool_context = SimpleNamespace(
                    actions=SimpleNamespace(set_model_response=None)
                )
                validated_data = await target_tool.run_async(
                    args=fc.args, tool_context=noop_tool_context
                )
                # SetModelResponseTool.run_async catches ValidationError internally
                # and returns a dict with "error" key instead of raising the exception.
                if (
                    isinstance(validated_data, dict)
                    and "error" in validated_data
                ):
                  logger.warning(
                      "Local Pydantic validation failed: %s. Continuing.",
                      validated_data["error"],
                  )
                else:
                  parsed_json_data = validated_data
                  logger.info(
                      "Local Pydantic validation passed! Short-circuiting."
                  )
                  break
              except pydantic.ValidationError as e:
                logger.warning(
                    "Local Pydantic validation failed: %s. Continuing.",
                    e,
                )
            else:
              parsed_json_data = fc.args
              break

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

    return parsed_json_data, full_content_list

  async def _run_extractor_and_merge(
      self,
      skill_name: str,
      template_name: str,
      surface_id_prefix: str,
      cleaned_query: str,
      session_id: str,
      ui_version: str | None = None,
  ) -> tuple[list[Part] | None, str | None, dict[str, Any] | None]:
    """Runs the dynamic extractor agent and merges output into the template."""
    # 1. Resolve catalog schema manager and validator
    schema_manager = self._schema_managers.get(ui_version)
    selected_catalog = None
    if schema_manager:
      # Retrieve the resolved catalog config for validation.
      # Replacing the deprecated get_catalog("maps-agentic-ui-catalog")
      # API call.
      selected_catalog = schema_manager.get_selected_catalog()

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
    parsed_json_data, full_content_list = await self._run_extractor(
        runner, agent, current_message, session_id
    )

    # 5. Handle output layout merging
    if parsed_json_data is not None:
      logger.info(
          "Template parameters extracted successfully. Merging template."
      )
      if "surface_id" not in parsed_json_data:
        short_id = uuid.uuid4().hex[:8]
        parsed_json_data["surface_id"] = f"{surface_id_prefix}-{short_id}"

      merged_actions = merge_template(
          template_name,
          parsed_json_data,
          max_list_size=self.config.max_list_size,
      )

      if selected_catalog:
        logger.info("Validating merged template against A2UI catalog schema.")
        try:
          selected_catalog.validator.validate(merged_actions)
        except Exception as e:  # pylint: disable=broad-exception-caught
          logger.warning("Catalog validation failed: %s. Falling back.", e)
          return None, None, None

      final_parts = [create_a2ui_part(action) for action in merged_actions]
      return final_parts, None, parsed_json_data
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
            "Executing fast text response flow."
        )
        final_parts = await self._handle_text_only(cleaned_query, session_id)
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

    # Fallback for un-implemented spatial intents
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

  async def _handle_text_only(
      self, cleaned_query: str, session_id: str
  ) -> list[Part]:
    """Generates a plain text response and wraps it in the text_only template.

    Args:
      cleaned_query: The cleaned user query.
      session_id: Context session ID.

    Returns:
      List of A2A Parts.
    """
    extractor_config = {
        "system_instruction": (
            "You are a helpful location assistant. Answer the user's"
            " question directly. Keep it relatively concise. Do NOT"
            " output A2UI tags."
        ),
    }
    if self.config.extractor_thinking_budget > 0:
      extractor_config["thinking_config"] = types.ThinkingConfig(
          thinking_budget=self.config.extractor_thinking_budget
      )

    answer_req = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=cleaned_query)],
            )
        ],
        config=types.GenerateContentConfig(**extractor_config),
    )

    answer_text = ""
    async for res in self.extractor_client.generate_content_async(answer_req):
      if res.content and res.content.parts:
        for p in res.content.parts:
          if p.text:
            answer_text += p.text

    return self._wrap_in_text_only(answer_text, session_id)

  async def _handle_extracted_intent(
      self,
      intent: IntentClass,
      query: str,
      session_id: str,
      ui_version: str | None = None,
  ) -> AsyncIterable[dict[str, Any]]:
    """Handles intents that use dynamic extractor agents and templates."""
    if intent == IntentClass.LOCAL_SEARCH:
      skill_name = _LOCAL_SEARCH_SKILL_NAME
      template_name = _LOCAL_SEARCH_TEMPLATE_NAME
      surface_prefix = _LOCAL_SEARCH_SURFACE_PREFIX
    elif intent == IntentClass.DIRECTIONS:
      skill_name = _DIRECTIONS_SKILL_NAME
      template_name = _DIRECTIONS_TEMPLATE_NAME
      surface_prefix = _DIRECTIONS_SURFACE_PREFIX
    else:
      raise ValueError(f"Unsupported intent for extractor: {intent}")

    logger.info("Router matched %s. Dispatching template extractor.", intent)

    merged_parts, fallback_text, parsed_json_data = (
        await self._run_extractor_and_merge(
            skill_name=skill_name,
            template_name=template_name,
            surface_id_prefix=surface_prefix,
            cleaned_query=query,
            session_id=session_id,
            ui_version=ui_version,
        )
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
        final_parts = await self._handle_text_only(query, session_id)
      else:
        final_parts = self._wrap_in_text_only(fallback_text, session_id)
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
      return
