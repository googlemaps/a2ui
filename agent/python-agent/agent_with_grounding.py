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

import os
import pathlib
import logging
from typing import Optional
from google import genai
from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import skill_toolset
from google.adk.tools import FunctionTool
from google.adk.skills import load_skill_from_dir
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.schema.catalog import CatalogConfig
from a2ui.schema.common_modifiers import remove_strict_validation
from a2ui.schema.constants import VERSION_0_9

# Import MAUIAgent to inherit from it
from agent import MAUIAgent, AGENT_INSTRUCTION, MergedCatalogProvider

logger = logging.getLogger(__name__)

CLEANUP_INSTRUCTION_TEMPLATE = """
Please update the A2UI json response by replacing any incorrect 
Place IDs with the correct ones using the following grounding map of name to place ID:
```
{grounding_map}
```
Return only the cleaned JSON array. Here is the A2UI JSON response to clean up: 
```json
{final_response_content}
```
"""

# Load skill content at module level
skill_content = ""
skill_path = pathlib.Path(__file__).parent / "skills" / "google-maps-enriched-local-query-response" / "SKILL.md"
if skill_path.exists():
    with open(skill_path, "r") as f:
        skill_content = f.read()
else:
    logger.warning(f"Skill file not found at {skill_path}")

async def query_vertex_map(query: str) -> str:
    """Query Google Maps via Vertex Grounding and return cleaned response.
    
    Args:
        query: The location query or question.
    """
    
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
      raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set. You must set a valid Google Cloud project ID to use the Agent with Grounding.")

    location = os.environ.get("GOOGLE_CLOUD_LOCATION")
    if not location:
        location = "global"
        logger.warning("GOOGLE_CLOUD_LOCATION is not set, defaulting to 'global'.")

    model_id = "gemini-3-flash-preview"
    cleanup_model_id = "gemini-3-flash-preview"
    
    client = genai.Client(vertexai=True, project=project_id, location=location)
    
    # Force use of skill for specialized maps tool
    use_skill = True
        
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
                provider=MergedCatalogProvider(VERSION_0_9, str(extension_path))
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
    
    final_instruction = """Use the Google Maps tool to answer queries about places.
    
    IMPORTANT: When generating the A2UI JSON response, you MUST include the "<a2ui-json> ...content... </a2ui-json>" tags immediately around the JSON content.
    Failure to do so will prevent the UI from rendering the map."""
    
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
    
    # Cleanup logic (second pass)
    try:
        grounding_map = {}
        if hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'grounding_metadata'):
            meta = response.candidates[0].grounding_metadata
            if hasattr(meta, 'grounding_chunks'):
                for chunk in meta.grounding_chunks:
                    if hasattr(chunk, 'maps') and chunk.maps:
                        title = getattr(chunk.maps, 'title', None)
                        place_id = getattr(chunk.maps, 'place_id', None)
                        if title and place_id:
                            grounding_map[title.lower().strip()] = place_id

        if grounding_map and "<a2ui-json>" in final_response_content:
            cleanup_response = client.models.generate_content(
                model=cleanup_model_id,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=CLEANUP_INSTRUCTION_TEMPLATE.format(
                        grounding_map=grounding_map,
                        final_response_content=final_response_content
                    ),
                ),
            )
            text = cleanup_response.text
            start_idx = text.find("<a2ui-json>")
            end_idx = text.rfind("</a2ui-json>")
            if start_idx == -1 and end_idx == -1:
                final_response_content = "<a2ui-json>" + text + "</a2ui-json>"
            else:
                final_response_content = text

    except Exception as e:
        logger.error(f"Error during Place ID cleanup: {e}")
        
    # Final safety check: Extract JSON array if marker is present
    if "<a2ui-json>" in final_response_content:
        marker_idx = final_response_content.find("<a2ui-json>")
        before_marker = final_response_content[:marker_idx]
        after_marker = final_response_content[marker_idx + len("<a2ui-json>"):]
        
        start_idx = after_marker.find("[")
        end_idx = after_marker.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_only = after_marker[start_idx:end_idx+1]
            final_response_content = before_marker + "<a2ui-json>" + json_only + "</a2ui-json>"
            
    return final_response_content


class MAUIAgentWithGrounding(MAUIAgent):
    """An agent that finds restaurants based on user criteria, using Vertex Grounding."""

    def __init__(self, base_url: str):
        super().__init__(base_url, agent_name="MAUI Agent with Grounding")

    def _build_llm_agent(
        self, schema_manager: Optional[A2uiSchemaManager] = None
    ) -> LlmAgent:
        """Builds the LLM agent for the MAUI agent with grounding."""
        
        _SKILL_BASE_PATH = pathlib.Path(__file__).parent / "skills"

        skill_names = [
            "google-maps-enriched-local-query-response",
        ]
        skills = []
        for name in skill_names:
            skills.append(load_skill_from_dir(_SKILL_BASE_PATH / name))

        skill_manager_tool = skill_toolset.SkillToolset(skills=skills)
        
        # Use FunctionTool for Vertex grounding
        grounding_tool = FunctionTool(func=query_vertex_map)

        AGENT_INSTRUCTION = """You are a location routing agent.
        Whenever the user asks a question about a location, directions, places, or maps,
        you MUST call the query_vertex_map tool.
        Do NOT attempt to answer location questions yourself.
        
        When calling the query_vertex_map tool, ensure you provide a fully self-contained query. If the user refers to places, routes, or context mentioned in previous turns (e.g., 'there', 'that hotel', 'a different route', 'reverse it'), you MUST resolve those references to include specific names, origins, and destinations from the conversation history so the tool has full context. For example, if the user asks "Can I take a different route?", you should call the tool with a query like "Show me a different route from [Origin] to [Destination]" using the origin and destination from the previous turn.
        
        CRITICAL: Return the output of the query_vertex_map tool EXACTLY as it is received, without any summarization, explanation, or modification. Your final response should be just the output of the tool."""

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
            name="maui_agent_grounding",
            description="An agent that can provide Google Maps UI-enriched responses using Vertex Grounding",
            instruction=instruction,
            tools=[grounding_tool, skill_manager_tool],
        )
