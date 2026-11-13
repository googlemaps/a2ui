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

"""Vertex Grounding with Google Maps (GwGM) template parameter extractor."""

import json
import logging
import re
from typing import Any, TypeVar

from google import genai
from google.genai import types
import pydantic

from agent import GROUNDED_TEXT_BASE_INSTRUCTION
from templates.common import parse_user_coordinates

logger = logging.getLogger(__name__)


def build_retrieval_tool_config(query: str) -> types.ToolConfig | None:
  """Builds a ToolConfig with user coordinate biasing if parsed from query.

  Args:
      query: User query string.

  Returns:
      ToolConfig with RetrievalConfig lat_lng populated, or None if coordinates
      are not present.
  """
  coords = parse_user_coordinates(query)
  if coords is None:
    return None
  lat, lng = coords
  return types.ToolConfig(
      retrieval_config=types.RetrievalConfig(
          lat_lng=types.LatLng(latitude=lat, longitude=lng)
      )
  )


T = TypeVar("T", bound=pydantic.BaseModel)

_DATA_BLOCK_RE = re.compile(r"<data>(.*?)</data>", re.DOTALL | re.IGNORECASE)

DUAL_GROUNDING_INSTRUCTIONS = """\
## Dual-Tool Grounding Rules (Google Maps + Google Search)
1. **Parallel Dual-Tool Co-Invocation**: Call Google Maps in parallel for every named venue, route endpoint, corridor stop, or search area; in parallel, call Google Search whenever the query needs live web details, schedules or transit options, policies, pricing, payment methods, or specific services and amenities not guaranteed in static Maps records.
2. **Maps-Backed Entity Resolution**: Google Maps is the exclusive authority for place existence, verbatim Place IDs, coordinates, addresses, ratings, and travel metrics. If Search surfaces a venue not yet retrieved from Maps, call Google Maps to verify its verbatim Place ID and metrics—or emit only Maps-verified venues.
3. **Evidence Hierarchy & Web Enrichment**: Always preserve Google Maps numeric distances (miles/km/ft) and estimated travel or detour times alongside live web specifics from Search; fall back to general norms only when a requested detail is absent from both tools.
"""


def log_grounding_metadata(
    response: Any,
    enable_search_grounding: bool,
) -> None:
  """Logs grounding metadata and chunk counts for Search observability.

  Args:
      response: Response object from generate_content.
      enable_search_grounding: Whether Search grounding was requested.
  """
  try:
    web_search_queries: list[str] = []
    maps_chunks = 0
    web_chunks = 0

    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, (list, tuple)) and candidates:
      candidate = candidates[0]
      meta = getattr(candidate, "grounding_metadata", None)
      if meta is not None:
        raw_queries = getattr(meta, "web_search_queries", None)
        if isinstance(raw_queries, (list, tuple)):
          web_search_queries = [q for q in raw_queries if isinstance(q, str)]
        raw_chunks = getattr(meta, "grounding_chunks", None)
        if isinstance(raw_chunks, (list, tuple)):
          for chunk in raw_chunks:
            if getattr(chunk, "maps", None) is not None:
              maps_chunks += 1
            if getattr(chunk, "web", None) is not None:
              web_chunks += 1

    logger.info(
        "Vertex Grounding: enable_search_grounding=%s,"
        " web_search_queries=%s, maps_chunks=%d, web_chunks=%d",
        enable_search_grounding,
        web_search_queries,
        maps_chunks,
        web_chunks,
    )
  except Exception as e:  # pylint: disable=broad-except
    logger.debug("Failed to log grounding metadata: %s", e)


class VertexGroundingExtractor:
  """Extractor using Vertex AI Grounding with Google Maps (GwGM)."""

  def __init__(
      self,
      client: genai.Client,
      model_id: str = "gemini-3.7-flash",
      shared_guidelines: str = "",
      thinking_budget: int = 0,
      enable_search_grounding: bool = True,
  ):
    """Initializes VertexGroundingExtractor.

    Args:
        client: GenAI client instance.
        model_id: Model ID for grounded extraction.
        shared_guidelines: Style and formatting guidelines string.
        thinking_budget: Thinking budget for reasoning models.
        enable_search_grounding: Whether to enable Google Search grounding
          alongside Google Maps. Defaults to True.
    """
    self.client = client
    self.model_id = model_id.removeprefix("gemini/").removeprefix("models/")
    self.shared_guidelines = shared_guidelines
    self.thinking_budget = thinking_budget
    self.enable_search_grounding = enable_search_grounding

  def _log_grounding_metadata(self, response: Any) -> None:
    """Logs grounding metadata and chunk counts for Search observability."""
    log_grounding_metadata(
        response=response,
        enable_search_grounding=self.enable_search_grounding,
    )

  def _build_tools(self) -> list[types.Tool]:
    """Builds the list of tools for grounded extraction."""
    tools = [types.Tool(google_maps=types.GoogleMaps())]
    if self.enable_search_grounding:
      tools.append(types.Tool(google_search=types.GoogleSearch()))
    return tools

  def _build_instruction(
      self,
      schema_cls: type[T],
      max_places: int,
      skill_instructions: str = "",
  ) -> str:
    """Builds the system instruction for a free-text grounded extraction.

    The request deliberately does not set `response_schema`, which suppresses
    Google Maps grounding tool execution in Vertex AI. Asking for a delimited
    `<data>...</data>` JSON block keeps the response free-text so the grounding
    tool executes and returns verified place IDs and facts, while still yielding
    a machine-readable payload.

    Args:
        schema_cls: Pydantic model the data block must satisfy.
        max_places: Upper bound on places in a list result.
        skill_instructions: Optional template-specific domain skill guidelines.

    Returns:
        The system instruction string.
    """
    skill_block = f"\n\n{skill_instructions}" if skill_instructions else ""
    guidelines_block = (
        f"\n\n{self.shared_guidelines}" if self.shared_guidelines else ""
    )
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)

    dual_grounding_block = (
        f"\n\n{DUAL_GROUNDING_INSTRUCTIONS}"
        if self.enable_search_grounding
        else ""
    )

    return f"""You are an expert location specialist.
You MUST call the Google Maps tool to answer the user's location request and follow the Grounding & Tool-Calling Policy.{dual_grounding_block}

Respond with a machine-readable block wrapped in <data> and </data> tags, containing
a single JSON object conforming to this JSON Schema:

{schema_json}

CRITICAL RULES:
1. For geographic coordinates (latitude and longitude), provide accurate coordinates based on the tool findings.
2. Strictly honor user constraints (e.g., outdoor vs indoor, ratings, price, dietary restrictions, and travel modes).
3. If extracting a list of places, limit the results to at most {max_places} places.
4. If extracting directions or routes, you MUST populate 'routes' with RouteSegment items connecting the origin, any waypoints, and the destination with accurate latitude and longitude coordinates.
5. Emit nothing outside the <data> and </data> tags.{guidelines_block}{skill_block}
"""

  def _parse_data_block(self, response_text: str) -> str:
    """Slices the <data> block out of a free-text response.

    Args:
        response_text: Raw model response.

    Returns:
        The JSON string between the data tags.

    Raises:
        ValueError: If no data block is present.
    """
    match = _DATA_BLOCK_RE.search(response_text or "")
    if not match:
      raise ValueError(
          "Model response contained no <data> block. Received"
          f" {len(response_text or '')} characters."
      )
    return match.group(1).strip()

  async def extract(
      self,
      query: str,
      schema_cls: type[T],
      max_places: int = 5,
      skill_instructions: str = "",
  ) -> T:
    """Runs one grounded turn and returns validated template parameters.

    Args:
        query: End-user location request.
        schema_cls: Pydantic model describing the template parameters.
        max_places: Upper bound on places in a list result.
        skill_instructions: Optional template-specific domain skill guidelines.

    Returns:
        A validated instance of `schema_cls`.

    Raises:
        ValueError: If the response carries no data block, or the block is not
          valid JSON.
    """
    config_kwargs: dict[str, Any] = {
        "system_instruction": self._build_instruction(
            schema_cls, max_places, skill_instructions=skill_instructions
        ),
        "tools": self._build_tools(),
    }
    tool_config = build_retrieval_tool_config(query)
    if tool_config is not None:
      config_kwargs["tool_config"] = tool_config
    if self.thinking_budget > 0:
      config_kwargs["thinking_config"] = types.ThinkingConfig(
          thinking_budget=self.thinking_budget
      )

    response = await self.client.aio.models.generate_content(
        model=self.model_id,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    self._log_grounding_metadata(response)

    data_block = self._parse_data_block(response.text)
    try:
      data = json.loads(data_block)
    except (json.JSONDecodeError, TypeError) as e:
      raise ValueError(f"<data> block was not valid JSON: {e}") from e

    return schema_cls.model_validate(data)

  async def generate_grounded_text(
      self,
      query: str,
      system_instruction: str | None = None,
  ) -> str:
    """Generates a plain-text grounded response using Vertex AI GwGM.

    Args:
        query: User query string.
        system_instruction: Optional instruction override. Defaults to
          `GROUNDED_TEXT_BASE_INSTRUCTION` with `shared_guidelines` appended.

    Returns:
        The generated text, or an empty string on error or safety block.
    """
    if system_instruction is None:
      base_inst = GROUNDED_TEXT_BASE_INSTRUCTION
      if self.enable_search_grounding:
        base_inst = f"{base_inst}\n\n{DUAL_GROUNDING_INSTRUCTIONS}"
      if self.shared_guidelines:
        system_instruction = (
            f"{base_inst}\n\n## Style Guidelines\n{self.shared_guidelines}"
        )
      else:
        system_instruction = base_inst
    config_kwargs: dict[str, Any] = {
        "system_instruction": system_instruction,
        "tools": self._build_tools(),
    }
    tool_config = build_retrieval_tool_config(query)
    if tool_config is not None:
      config_kwargs["tool_config"] = tool_config
    if self.thinking_budget > 0:
      config_kwargs["thinking_config"] = types.ThinkingConfig(
          thinking_budget=self.thinking_budget
      )

    try:
      response = await self.client.aio.models.generate_content(
          model=self.model_id,
          contents=query,
          config=types.GenerateContentConfig(**config_kwargs),
      )
      self._log_grounding_metadata(response)
      return response.text or ""
    except Exception as e:
      logger.exception("Error generating grounded text with Vertex AI: %s", e)
      return ""
