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

import logging
import os
import pathlib
from typing import Optional

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
import place_id_resolution

# Import MAUIAgent to inherit from it
from agent import AGENT_INSTRUCTION, MAUIAgent, MergedCatalogProvider

logger = logging.getLogger(__name__)

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
  ):
    super().__init__(
        base_url,
        agent_name="MAUI Agent with Grounding",
        model_name=model_name,
    )

  async def query_vertex_map(self, query: str) -> str:
    """Query Google Maps via Vertex Grounding and return cleaned response.

    Args:
        query: The location query or question.

    Returns:
        The grounded and cleaned A2UI response string.
    """
    model_id = (
        self._model_name.removeprefix("gemini/").removeprefix("models/")
    )
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
