# Copyright 2025 Google LLC
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

import json
import logging
import pathlib
import os
from collections import OrderedDict
from collections.abc import AsyncIterable
from typing import Any, Optional, Dict

import jsonschema
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Part,
    TextPart,
)
from google.adk.agents import run_config
from google.adk.agents.llm_agent import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from a2ui.schema.constants import VERSION_0_8, VERSION_0_9, A2UI_OPEN_TAG, A2UI_CLOSE_TAG
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.parser.parser import parse_response, ResponsePart
from a2ui.schema.common_modifiers import remove_strict_validation
from a2ui.a2a.extension import get_a2ui_agent_extension
from a2ui.a2a.parts import parse_response_to_parts, stream_response_to_parts
from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.catalog_provider import A2uiCatalogProvider
from a2ui.basic_catalog.provider import BundledCatalogProvider

logger = logging.getLogger(__name__)


_SKILL_BASE_PATH = pathlib.Path(__file__).parent / "skills"

google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY")

if not google_maps_api_key:
    # Fallback or direct assignment for testing - NOT RECOMMENDED FOR PRODUCTION
    google_maps_api_key = "YOUR_GOOGLE_MAPS_API_KEY_HERE" # Replace if not using env var
    if google_maps_api_key == "YOUR_GOOGLE_MAPS_API_KEY_HERE":
        print("WARNING: GOOGLE_MAPS_API_KEY is not set. Please set it as an environment variable or in the script.")

AGENT_INSTRUCTION = f"""
    You are a helpful location expert and assistant. Your goal is to help provide effective answers to a user's location based questions.

    To achieve this, you MUST follow this logic:

    If the user asks a location-based question, use your skills or tools to answer the user. Location based questions
      may include the following:

      * Show me sushi in Seattle
      * Where can I get a beer in Ballard?
      * Navigate to the space needle

    **Important**: Do NOT include conversational text outside of the A2UI structure.
    ALL TEXT RESPONSES MUST BE CONTAINED WITHIN A TEXT COMPONENT IN THE A2UI OUTPUT.

    **Important**: When answering a location-based question, you may need to find up-to-date information
    about places or routes. Use your skills or tools to answer the user. When returning information for places, always
    fetch the place's name, address, lat, lng, and place id.

    **Important**: Consider that subsequent requests are likely to be part of the same "user journey", and keep track of
    any context that you may need to provide to the user. Examples:

    * if the user asks for "sushi restaurants in seattle", and then asks for "directions to the first restaurant", you should use the first restaurant's address as the destination address for the directions.
    * if the user asks for "sushi restaurants in seattle", and then asks for "how about in Redmond?", you should assume that they are asking for a new set of _sushi_ restaurants based on their previous query.

    **Important**: When using the `google-maps-enriched-local-query-response` skill, you MUST respond with EXACTLY ONE <a2ui-json> ... </a2ui-json> block.
    If you have more than one of these blocks, the UI will not render correctly.

"""

class MergedCatalogProvider(A2uiCatalogProvider):
  """Dynamically loads the bundled basic catalog and extends it with local definitions."""
  def __init__(self, version: str, extension_catalog_path: str):
    self.version = version
    self.extension_catalog_path = extension_catalog_path

  def load(self) -> Dict[str, Any]:
    # 1. Load the bundled base catalog from the package
    base_provider = BundledCatalogProvider(self.version)
    catalog = base_provider.load()

    # 2. Load extension definitions from local JSON
    with open(self.extension_catalog_path, 'r') as f:
      overrides = json.load(f)

    # 3. Merge custom extensions into the schema
    if "components" in overrides:
      catalog.setdefault("components", {}).update(overrides["components"])
    if "$defs" in overrides:
      catalog.setdefault("$defs", {}).update(overrides["$defs"])
    if "catalogId" in overrides:
      catalog["catalogId"] = overrides["catalogId"]

    return catalog


class MAUIAgent:
  """An agent that finds restaurants based on user criteria."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self, base_url: str, agent_name: str = "MAUI Agent"):
    self.base_url = base_url
    self._agent_name = agent_name
    self._user_id = "remote_agent"
    self._text_runner: Optional[Runner] = self._build_runner(self._build_llm_agent())

    self._schema_managers: Dict[str, A2uiSchemaManager] = {}
    self._ui_runners: Dict[str, Runner] = {}
    self._parsers = OrderedDict()
    self._max_parsers = 1000  # Max active sessions to keep in memory

    for version in [VERSION_0_9]:
      schema_manager = self._build_schema_manager(version)
      self._schema_managers[version] = schema_manager
      agent = self._build_llm_agent(schema_manager)
      self._ui_runners[version] = self._build_runner(agent)

    self._agent_card = self._build_agent_card()

  @property
  def agent_card(self) -> AgentCard:
    return self._agent_card

  def _build_schema_manager(self, version: str) -> A2uiSchemaManager:
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

    return A2uiSchemaManager(
        version=version,
        catalogs=[
            CatalogConfig(
                name="maps-agentic-ui-catalog",
                provider=MergedCatalogProvider(version, str(extension_path))
            )
        ],
        schema_modifiers=[remove_strict_validation],
    )

  def make_grounding_lite_mcp(self):
    return McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url="https://mapstools.googleapis.com/mcp",
                    headers={"X-Goog-Api-Key": google_maps_api_key} if google_maps_api_key and google_maps_api_key != "YOUR_GOOGLE_MAPS_API_KEY_HERE" else {},
                    timeout=30.0,
                ),
                # You can filter for specific Maps tools if needed:
                # tool_filter=['get_directions', 'find_place_by_id']
            )

  def _build_agent_card(self) -> AgentCard:
    extensions = []
    if self._schema_managers:
      for version, sm in self._schema_managers.items():
        ext = get_a2ui_agent_extension(
            version,
            sm.accepts_inline_catalogs,
            sm.supported_catalog_ids,
        )
        extensions.append(ext)

    capabilities = AgentCapabilities(
        streaming=True,
        extensions=extensions,
    )

    return AgentCard(
        name="AI Kit Agent",
        description="This agent can provide Google Maps UI-enriched responses to relevant prompts",
        url=self.base_url,
        version="1.0.0",
        default_input_modes=MAUIAgent.SUPPORTED_CONTENT_TYPES,
        default_output_modes=MAUIAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=capabilities,
        skills=[],
    )

  def _build_runner(self, agent: LlmAgent) -> Runner:
    return Runner(
        app_name=self._agent_name,
        agent=agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
    return "Working on it..."

  def _build_llm_agent(
      self, schema_manager: Optional[A2uiSchemaManager] = None
  ) -> LlmAgent:
    """Builds the LLM agent for the AI Kit agent."""
    LITELLM_MODEL = os.getenv("LITELLM_MODEL", "gemini/gemini-2.5-flash")


    skill_names = [
        "google-maps-enriched-local-query-response",
    ]
    skills = []
    for name in skill_names:
        skills.append(load_skill_from_dir(_SKILL_BASE_PATH / name))

    skill_manager_tool = skill_toolset.SkillToolset(skills=skills)
    grounding_lite_mcp = self.make_grounding_lite_mcp()

    instruction = (
        schema_manager.generate_system_prompt(
            role_description=AGENT_INSTRUCTION,
            include_schema=True,
            include_examples=False,
            validate_examples=False,
        )
        if schema_manager
        else AGENT_INSTRUCTION
    )

    return LlmAgent(
        model=LiteLlm(model="gemini/gemini-3-flash-preview"),
        name="maui_agent",
        description="An agent that can provide Google Maps UI-enriched responses to relevant prompts",
        instruction=instruction,
        tools=[grounding_lite_mcp, skill_manager_tool],
    )

  async def stream(
      self, query, session_id, ui_version: Optional[str] = None
  ) -> AsyncIterable[dict[str, Any]]:
    session_state = {"base_url": self.base_url, "expression": "{expression}"}

    # Determine which runner to use based on whether the a2ui extension is active.
    if ui_version:
      runner = self._ui_runners[ui_version]
      schema_manager = self._schema_managers[ui_version]
      selected_catalog = (
          schema_manager.get_selected_catalog() if schema_manager else None
      )
    else:
      runner = self._text_runner
      schema_manager = None
      selected_catalog = None

    session = await runner.session_service.get_session(
        app_name=self._agent_name,
        user_id=self._user_id,
        session_id=session_id,
    )
    if session is None:
      session = await runner.session_service.create_session(
          app_name=self._agent_name,
          user_id=self._user_id,
          state=session_state,
          session_id=session_id,
      )
    elif "base_url" not in session.state:
      session.state["base_url"] = self.base_url

    # --- Begin: UI Validation and Retry Logic ---
    max_retries = 1  # Total 2 attempts
    attempt = 0
    current_query_text = query

    # Ensure schema was loaded
    if ui_version and (not selected_catalog or not selected_catalog.catalog_schema):
      logger.error(
          "--- MAUIAgent.stream: A2UI_SCHEMA is not loaded. "
          "Cannot perform UI validation. ---"
      )
      yield {
          "is_task_complete": True,
          "parts": [
              Part(
                  root=TextPart(
                      text=(
                          "I'm sorry, I'm facing an internal configuration error with"
                          " my UI components. Please contact support."
                      )
                  )
              )
          ],
      }
      return

    while attempt <= max_retries:
      attempt += 1
      logger.info(
          f"--- MAUIAgent.stream: Attempt {attempt}/{max_retries + 1} "
          f"for session {session_id} ---"
      )

      current_message = types.Content(
          role="user", parts=[types.Part.from_text(text=current_query_text)]
      )

      full_content_list = []

      async def token_stream():
        async for event in runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            run_config=run_config.RunConfig(
                streaming_mode=run_config.StreamingMode.SSE
            ),
            new_message=current_message,
        ):
          if event.content and event.content.parts:
            for p in event.content.parts:
              if p.text:
                full_content_list.append(p.text)
                yield p.text

      if selected_catalog:
        logger.info(
            f"--- MAUIAgent.stream: Using A2UI stream parser for catalog {selected_catalog.catalog_id} ---"
        )
        from a2ui.parser.streaming import A2uiStreamParser

        if session_id in self._parsers:
          self._parsers.move_to_end(session_id)
        else:
          self._parsers[session_id] = A2uiStreamParser()
          if len(self._parsers) > self._max_parsers:
            self._parsers.popitem(last=False)


        logger.info(
            f"--- MAUIAgent.stream: Streamed part: {token_stream()} ---"
        )

        async for part in stream_response_to_parts(
            self._parsers[session_id],
            token_stream(),
        ):
          logger.info(
            f"-- MAUIAgent.stream: Streamed part: {part} ---"
          )
          yield {
              "is_task_complete": False,
              "parts": [part],
          }
      else:
        async for token in token_stream():
          yield {
              "is_task_complete": False,
              "updates": token,
          }

      final_response_content = "".join(full_content_list)

      logger.info(
        f"-- MAUIAgent.stream: Final response content: {final_response_content} ---"
      )

      is_valid = False
      error_message = ""

      if ui_version:
        logger.info(
            "--- MAUIAgent.stream: Validating UI response (Attempt"
            f" {attempt})... ---"
        )
        try:
          logger.info(f"--- MAUIAgent.stream: Final response content: {final_response_content} ---")
          response_parts = parse_response(final_response_content)


          for part in response_parts:
            if not part.a2ui_json:
              continue

            parsed_json_data = part.a2ui_json

            # --- Validation Steps ---
            # Check if it validates against the A2UI_SCHEMA
            # This will raise jsonschema.exceptions.ValidationError if it fails
            logger.info(
                "--- MAUIAgent.stream: Validating against A2UI_SCHEMA... ---"
            )
            selected_catalog.validator.validate(parsed_json_data)
            # --- End Validation Steps ---

            logger.info(
                "--- MAUIAgent.stream: UI JSON successfully parsed AND validated"
                f" against schema. Validation OK (Attempt {attempt}). ---"
            )
            is_valid = True

        except (
            ValueError,
            json.JSONDecodeError,
            jsonschema.exceptions.ValidationError,
        ) as e:
          logger.warning(
            f"--- final content full_content_list {full_content_list}  ---")

          logger.warning(
              f"--- MAUIAgent.stream: A2UI validation failed: {e} (Attempt"
              f" {attempt}) ---"
          )
          logger.warning(
              f"--- Failed response content: {final_response_content[:500]}... ---"
          )
          error_message = f"Validation failed: {e}."

      else:  # Not using UI, so text is always "valid"
        is_valid = True

      if is_valid:
        logger.info(
            "--- MAUIAgent.stream: Response is valid. Sending final response"
            f" (Attempt {attempt}). ---"
        )
        final_parts = parse_response_to_parts(
            final_response_content, fallback_text="OK."
        )

        logger.info(f"--- MAUIAgent.stream: Final response parts: {final_parts} ---")

        seen_fingerprints = set()
        filtered_parts = []
        for p in final_parts:
            if isinstance(p.root, DataPart):
                fingerprint = ("data", json.dumps(p.root.data, sort_keys=True))
            elif isinstance(p.root, TextPart):
                fingerprint = ("text", p.root.text)
            else:
                fingerprint = ("other", str(p.root))

            if fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                filtered_parts.append(p)
        final_parts = filtered_parts


        yield {
            "is_task_complete": True,
            "parts": final_parts,
        }
        return  # We're done, exit the generator

      # --- If we're here, it means validation failed ---

      if attempt <= max_retries:
        logger.warning(
            f"--- MAUIAgent.stream: Retrying... ({attempt}/{max_retries + 1}) ---"
        )
        # Prepare the query for the retry
        current_query_text = (
            f"Your previous response was invalid. {error_message} You MUST generate a"
            " valid response that strictly follows the A2UI JSON SCHEMA. The response"
            " MUST be a JSON list of A2UI messages. Ensure each JSON part is wrapped in"
            f" '{A2UI_OPEN_TAG}' and '{A2UI_CLOSE_TAG}' tags. Please retry the"
            f" original request: '{query}'"
        )
        # Loop continues...

    # --- If we're here, it means we've exhausted retries ---
    logger.error(
        "--- MAUIAgent.stream: Max retries exhausted. Sending text-only"
        " error. ---"
    )
    yield {
        "is_task_complete": True,
        "parts": [
            Part(
                root=TextPart(
                    text=(
                        "I'm sorry, I'm having trouble generating the interface for"
                        " that request right now. Please try again in a moment."
                    )
                )
            )
        ],
    }
    # --- End: UI Validation and Retry Logic ---
