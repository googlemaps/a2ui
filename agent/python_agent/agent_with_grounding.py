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

"""MAUI Agent with Grounding implementation."""

from collections.abc import AsyncIterable
import logging
import os
import pathlib
from typing import Any, Optional
import uuid

from a2a.types import Part
from google import genai
from google.adk import skills as adk_skills
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import skill_toolset
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.common_modifiers import remove_strict_validation
from a2ui.schema.constants import VERSION_0_9
from a2ui.schema.manager import A2uiSchemaManager
import merger
import place_id_resolution
from agent import AGENT_INSTRUCTION, MAUIAgent, MergedCatalogProvider
from agent_config import FallbackMode, GroundingTemplateConfig
from extractor import DirectionsExtractorSchema, LocalSearchExtractorSchema
from router_config import IntentClass, VertexIntentClassifier
from vertex_grounding_extractor import VertexGroundingExtractor

logger = logging.getLogger(__name__)

_GROUNDED_TEXT_BASE_INSTRUCTION = """\
You are an expert location and navigation assistant with access to Google Maps tools.

## Core Rules
1. **Accuracy & Grounding**: Use Google Maps tools to look up real-time places, business hours, amenities, contact details, routes, and weather. NEVER hallucinate place facts, locations, or operational details.
2. **Parallel Tool Execution**: When researching multiple entities, neighborhoods, routes, or options, emit ALL independent tool calls in parallel within your initial response turn. Only serialize calls when Step 2 strictly depends on data returned by Step 1.
3. **Minimize Round-Trips**: Gather necessary place facts efficiently and emit independent queries in parallel. Only perform follow-up tool turns when subsequent calls strictly depend on data returned from earlier steps (e.g., retrieving details for specific place IDs or searching along a computed route polyline). Avoid redundant follow-up queries for details already retrieved.
4. **Helpful & Actionable Answers**: Fully address all constraints in the user's prompt (e.g., parking, pricing, specific dietary options, bag policies). If tools return generic listings that lack specific policy details, supplement with known facts while noting any uncertainty.
5. **No A2UI Tags**: Return standard plain text/markdown only. Do NOT output A2UI tags or JSON surfaces.
"""

# Load skill content at module level
skill_content = ""
skill_path = (
    pathlib.Path(__file__).parent
    / "skills"
    / "google-maps-enriched-local-query-response"
    / "SKILL.md"
)
if skill_path.exists():
  with open(skill_path, "r") as f:
    skill_content = f.read()
else:
  logger.warning("Skill file not found at %s", skill_path)


async def query_vertex_map(
    query: str,
    model_id: str = "gemini-3-flash-preview",
) -> str:
  """Query Google Maps via Vertex Grounding and return cleaned response.

  Args:
      query: The location query or question.
      model_id: The model ID to use for Vertex Grounding.

  Returns:
      The grounded and cleaned A2UI response string.
  """

  project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
  if not project_id:
    raise ValueError(
        "GOOGLE_CLOUD_PROJECT environment variable is not set. You must set a"
        " valid Google Cloud project ID to use the Agent with Grounding."
    )

  location = os.environ.get("GOOGLE_CLOUD_LOCATION")
  if not location:
    location = "global"
    logger.warning("GOOGLE_CLOUD_LOCATION is not set, defaulting to 'global'.")

  client = genai.Client(vertexai=True, project=project_id, location=location)

  # Construct instruction
  base_instruction = "You are a location specialist.\n\n" + AGENT_INSTRUCTION

  # Try sibling directory first (local dev)
  extension_path = (
      pathlib.Path(__file__).parent.parent
      / "shared"
      / "schema"
      / "maps_catalog_extension.json"
  )
  # Fallback to nested directory (deployed environment)
  if not extension_path.exists():
    extension_path = (
        pathlib.Path(__file__).parent
        / "shared"
        / "schema"
        / "maps_catalog_extension.json"
    )

  schema_manager = A2uiSchemaManager(
      version=VERSION_0_9,
      catalogs=[
          CatalogConfig(
              name="maps-agentic-ui-catalog",
              provider=MergedCatalogProvider(VERSION_0_9, str(extension_path)),
          )
      ],
      schema_modifiers=[remove_strict_validation],
  )

  generated_prompt = schema_manager.generate_system_prompt(
      role_description=base_instruction,
      include_schema=True,
      include_examples=False,
      validate_examples=False,
  )

  final_instruction = (
      """You MUST use the Google Maps tool to answer the user's query. Do not rely on your internal knowledge.
    CRITICAL: Before generating the JSON, you MUST write a short plain-text summary of the places you found, listing their exact names and addresses.
    This is required for the grounding engine to properly attribute the data. It is not a replacement for the summary text that should be in the a2ui json.
    IMPORTANT: When generating the A2UI JSON response, you MUST include the "<a2ui-json> ...content... </a2ui-json>" tags immediately around the JSON content.
    Failure to do so will prevent the UI from rendering the map.
    """
      + place_id_resolution.PROMPT_RULES
  )

  instruction = f"{generated_prompt}\n\n{skill_content}\n\n{final_instruction}"

  # Main generation call
  response = client.models.generate_content(
      model=model_id,
      contents=query,
      config=types.GenerateContentConfig(
          system_instruction=instruction,
          tools=[types.Tool(google_maps=types.GoogleMaps())],
      ),
  )

  final_response_content = response.text

  # Replace synthetic place ids with actual grounded place ids.
  try:
    attribution_sources = place_id_resolution.extract_attribution_sources(
        response
    )
    final_response_content, unresolved_placeholders = (
        place_id_resolution.resolve_place_ids(
            final_response_content, attribution_sources
        )
    )
    if unresolved_placeholders:
      logger.warning(
          "%d Place ID placeholder(s) remain in the response.",
          unresolved_placeholders,
      )
  except Exception as e:  # pylint: disable=broad-exception-caught
    logger.error("Error during Place ID cleanup: %s", e)

  # Final safety check: Extract JSON array if marker is present
  if "<a2ui-json>" in final_response_content:
    marker_idx = final_response_content.find("<a2ui-json>")
    after_marker = final_response_content[marker_idx + len("<a2ui-json>") :]

    start_idx = after_marker.find("[")
    end_idx = after_marker.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
      json_only = after_marker[start_idx : end_idx + 1]
      final_response_content = "<a2ui-json>" + json_only + "</a2ui-json>"

  return final_response_content


class MAUIAgentWithGrounding(MAUIAgent):
  """An agent that finds restaurants based on user criteria, using Vertex Grounding."""

  def __init__(
      self,
      base_url: str,
      model_name: str = "gemini/gemini-3-flash-preview",
      template_config: GroundingTemplateConfig | None = None,
  ):
    super().__init__(
        base_url,
        agent_name="MAUI Agent with Grounding",
        model_name=model_name,
    )
    self.template_config = template_config
    self._genai_client: genai.Client | None = None
    self._router_classifier: VertexIntentClassifier | None = None
    self._vertex_extractor: VertexGroundingExtractor | None = None

  def _get_genai_client(self) -> genai.Client:
    """Lazily initializes and caches a shared genai.Client."""
    if self._genai_client is None:
      cfg = self.template_config or GroundingTemplateConfig()
      project_id = (
          cfg.project_id
          or os.environ.get("GOOGLE_CLOUD_PROJECT")
          or os.environ.get("VERTEX_PROJECT_ID")
      )
      if not project_id:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT environment variable is not set. You must"
            " set a valid Google Cloud project ID to use the Agent with"
            " Grounding."
        )
      self._genai_client = genai.Client(
          vertexai=True,
          project=project_id,
          location=cfg.location,
      )
    return self._genai_client

  def _get_router_classifier(self) -> VertexIntentClassifier:
    """Lazily initializes and caches the VertexIntentClassifier."""
    if self._router_classifier is None:
      cfg = self.template_config or GroundingTemplateConfig()
      self._router_classifier = VertexIntentClassifier(
          project_id=cfg.project_id,
          location=cfg.location,
          model_id=cfg.router_model,
          client=self._get_genai_client(),
          thinking_budget=cfg.router_thinking_budget,
      )
    return self._router_classifier

  def _load_shared_guidelines(self) -> str:
    """Loads shared guidelines for vertex grounding extractor if present."""
    guidelines_path = (
        pathlib.Path(__file__).parent
        / "shared"
        / "instructions"
        / "voice_and_tone.md"
    )
    if guidelines_path.exists():
      with open(guidelines_path, "r") as f:
        return f.read()
    return ""

  def _get_vertex_extractor(self) -> VertexGroundingExtractor:
    """Lazily initializes and caches the VertexGroundingExtractor."""
    if self._vertex_extractor is None:
      cfg = self.template_config or GroundingTemplateConfig()
      self._vertex_extractor = VertexGroundingExtractor(
          project_id=cfg.project_id,
          location=cfg.location,
          model_id=cfg.extractor_model,
          shared_guidelines=self._load_shared_guidelines(),
          client=self._get_genai_client(),
          thinking_budget=cfg.extractor_thinking_budget,
      )
    return self._vertex_extractor

  def _wrap_in_text_only(self, text: str, session_id: str) -> list[Part]:
    """Wraps plain text in a text_only template Part list."""
    return merger.wrap_in_text_only(text, session_id=session_id)

  async def _handle_grounded_text(
      self, cleaned_query: str, session_id: str
  ) -> list[Part]:
    """Generates a grounded plain text response using Vertex AI GwGM."""
    vertex_extractor = self._get_vertex_extractor()
    try:
      response = await vertex_extractor.client.aio.models.generate_content(
          model=vertex_extractor.model_id,
          contents=cleaned_query,
          config=types.GenerateContentConfig(
              system_instruction=_GROUNDED_TEXT_BASE_INSTRUCTION,
              tools=[types.Tool(google_maps=types.GoogleMaps())],
          ),
      )
      answer_text = response.text or ""
    except Exception as e:
      logger.exception("Error generating grounded text with Vertex AI: %s", e)
      answer_text = ""

    if not answer_text:
      answer_text = (
          "I'm sorry, I encountered an issue retrieving location details"
          " right now."
      )
    return self._wrap_in_text_only(answer_text, session_id)

  async def _classify_intent(self, query: str) -> tuple[IntentClass, str]:
    """Classifies the query intent and returns the intent and cleaned query."""
    classifier = self._get_router_classifier()
    return await classifier.classify(query)

  async def _handle_template_intent(
      self,
      intent: IntentClass,
      query: str,
  ) -> AsyncIterable[dict[str, Any]]:
    """Handles supported template intents using Vertex Grounding with Google Maps."""
    if intent == IntentClass.LOCAL_SEARCH:
      schema_cls = LocalSearchExtractorSchema
      template_name = "local_search"
    elif intent == IntentClass.DIRECTIONS:
      schema_cls = DirectionsExtractorSchema
      template_name = "directions"
    else:
      raise ValueError(f"Unsupported intent for GwGM template: {intent}")

    logger.info(
        "Using VertexGroundingExtractor for intent %s with schema %s",
        intent,
        schema_cls.__name__,
    )
    cfg = self.template_config or GroundingTemplateConfig()
    vertex_extractor = self._get_vertex_extractor()
    extracted_template_params = await vertex_extractor.extract(
        query, schema_cls, max_places=cfg.max_list_size
    )

    a2ui_parts = merger.render_template_payload(
        template_name=template_name,
        payload=extracted_template_params,
        max_list_size=cfg.max_list_size,
    )
    yield {
        "is_task_complete": True,
        "parts": a2ui_parts,
    }

  async def stream(
      self, query: str, session_id: str, ui_version: str | None = None
  ) -> AsyncIterable[dict[str, Any]]:
    """Streams responses, routing via intent classifier to template extractors if enabled."""
    if not self.template_config or not self.template_config.enabled:
      async for part in super().stream(query, session_id, ui_version):
        yield part
      return

    if not ui_version:
      logger.info("No ui_version provided. Routing to base text streaming.")
      async for part in super().stream(query, session_id, ui_version):
        yield part
      return

    cfg = self.template_config
    try:
      intent, cleaned_query = await self._classify_intent(query)
    except Exception as e:  # pylint: disable=broad-exception-caught
      logger.warning("Intent routing failed: %s.", e, exc_info=True)
      if cfg.fallback_mode == FallbackMode.DYNAMIC:
        async for part in super().stream(query, session_id, ui_version):
          yield part
        return
      intent, cleaned_query = IntentClass.TEXT_ONLY, query

    if intent == IntentClass.OTHER_SPATIAL:
      if cfg.fallback_mode == FallbackMode.DYNAMIC:
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
        final_parts = await self._handle_grounded_text(
            cleaned_query, session_id
        )
        yield {
            "is_task_complete": True,
            "parts": final_parts,
        }
        return

    elif intent == IntentClass.TEXT_ONLY:
      logger.info("Executing fast text response flow for TEXT_ONLY intent.")
      final_parts = await self._handle_grounded_text(cleaned_query, session_id)
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
      return

    elif intent in {IntentClass.LOCAL_SEARCH, IntentClass.DIRECTIONS}:
      try:
        async for part in self._handle_template_intent(intent, cleaned_query):
          yield part
        return
      except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Template extraction failed for %s: %s", intent, e, exc_info=True
        )
        if cfg.fallback_mode == FallbackMode.DYNAMIC:
          logger.warning(
              "Falling back to dynamic generation due to template error."
          )
          async for part in super().stream(query, session_id, ui_version):
            yield part
          return
        else:
          logger.info("Falling back to grounded text due to template error.")
          final_parts = await self._handle_grounded_text(
              cleaned_query, session_id
          )
          yield {
              "is_task_complete": True,
              "parts": final_parts,
          }
          return

    # Fallback for un-implemented intents or validation failures
    if cfg.fallback_mode == FallbackMode.TEXT:
      final_parts = await self._handle_grounded_text(cleaned_query, session_id)
      yield {
          "is_task_complete": True,
          "parts": final_parts,
      }
    else:
      async for part in super().stream(query, session_id, ui_version):
        yield part

  async def query_vertex_map(self, query: str) -> str:
    """Query Google Maps via Vertex Grounding and return cleaned response.

    Args:
        query: The location query or question.

    Returns:
        The grounded and cleaned A2UI response string.
    """
    model_id = self._model_name.removeprefix("gemini/").removeprefix("models/")
    return await query_vertex_map(query, model_id=model_id)

  def _build_llm_agent(
      self, schema_manager: A2uiSchemaManager | None = None
  ) -> LlmAgent:
    """Builds the LLM agent for the MAUI agent with grounding."""

    skill_base_path = pathlib.Path(__file__).parent / "skills"

    skill_names = [
        "google-maps-enriched-local-query-response",
    ]
    skills = []
    for name in skill_names:
      skills.append(adk_skills.load_skill_from_dir(skill_base_path / name))

    skill_manager_tool = skill_toolset.SkillToolset(skills=skills)

    # Use FunctionTool for Vertex grounding
    grounding_tool = FunctionTool(func=self.query_vertex_map)

    agent_instruction = """You are a location routing agent.
        Whenever the user asks a question about a location, directions, places, or maps,
        you MUST call the query_vertex_map tool.
        Do NOT attempt to answer location questions yourself.

        When calling the query_vertex_map tool, ensure you provide a fully self-contained query. If the user refers to places, routes, or context mentioned in previous turns (e.g., 'there', 'that hotel', 'a different route', 'reverse it'), you MUST resolve those references to include specific names, origins, and destinations from the conversation history so the tool has full context. For example, if the user asks "Can I take a different route?", you should call the tool with a query like "Show me a different route from [Origin] to [Destination]" using the origin and destination from the previous turn.

        CRITICAL: Return the output of the query_vertex_map tool EXACTLY as it is received, without any summarization, explanation, or modification. Your final response should be just the output of the tool."""

    if schema_manager:
      instruction = schema_manager.generate_system_prompt(
          role_description=agent_instruction,
          include_schema=True,
          include_examples=False,
          validate_examples=False,
      )
    else:
      instruction = agent_instruction

    return LlmAgent(
        model=LiteLlm(model=self._model_name),
        name="maui_agent_grounding",
        description=(
            "An agent that can provide Google Maps UI-enriched responses using"
            " Vertex Grounding"
        ),
        instruction=instruction,
        tools=[grounding_tool, skill_manager_tool],
        after_tool_callback=self._after_tool_callback,
    )
