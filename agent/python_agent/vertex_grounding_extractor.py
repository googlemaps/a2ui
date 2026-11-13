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

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=pydantic.BaseModel)

_DATA_BLOCK_RE = re.compile(r"<data>(.*?)</data>", re.DOTALL | re.IGNORECASE)


class VertexGroundingExtractor:
  """Extractor using Vertex AI Grounding with Google Maps (GwGM)."""

  def __init__(
      self,
      client: genai.Client,
      model_id: str = "gemini-3.7-flash",
      shared_guidelines: str = "",
      thinking_budget: int = 0,
  ):
    self.client = client
    self.model_id = model_id.removeprefix("gemini/").removeprefix("models/")
    self.shared_guidelines = shared_guidelines
    self.thinking_budget = thinking_budget

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

    return f"""You are an expert location specialist.
You MUST call the Google Maps tool to answer the user's location request and follow the Grounding & Tool-Calling Policy.

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
        "tools": [types.Tool(google_maps=types.GoogleMaps())],
    }
    if self.thinking_budget > 0:
      config_kwargs["thinking_config"] = types.ThinkingConfig(
          thinking_budget=self.thinking_budget
      )

    response = await self.client.aio.models.generate_content(
        model=self.model_id,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )

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
      if self.shared_guidelines:
        system_instruction = (
            f"{GROUNDED_TEXT_BASE_INSTRUCTION}\n\n"
            f"## Style Guidelines\n{self.shared_guidelines}"
        )
      else:
        system_instruction = GROUNDED_TEXT_BASE_INSTRUCTION
    config_kwargs: dict[str, Any] = {
        "system_instruction": system_instruction,
        "tools": [types.Tool(google_maps=types.GoogleMaps())],
    }
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
      return response.text or ""
    except Exception as e:
      logger.exception("Error generating grounded text with Vertex AI: %s", e)
      return ""
