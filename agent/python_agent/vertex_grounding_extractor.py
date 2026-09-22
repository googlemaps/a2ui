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

import place_id_resolution
from place_id_resolution import AttributionSource
from place_id_resolution import normalize_place_id

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=pydantic.BaseModel)

_DATA_BLOCK_RE = re.compile(r"<data>(.*?)</data>", re.DOTALL | re.IGNORECASE)


class VertexGroundingExtractor:
  """Extractor using Vertex AI Grounding with Google Maps (GwGM)."""

  def __init__(
      self,
      project_id: str | None = None,
      location: str = "global",
      model_id: str = "gemini-3.5-flash-lite",
      shared_guidelines: str = "",
      client: genai.Client | None = None,
      thinking_budget: int = 0,
  ):
    if not project_id and client is None:
      raise ValueError("Vertex AI project_id must be provided.")
    self.project_id = project_id
    self.location = location
    self.model_id = model_id.removeprefix("gemini/").removeprefix("models/")
    self.shared_guidelines = shared_guidelines
    self._client: genai.Client | None = client
    self.thinking_budget = thinking_budget

  @property
  def client(self) -> genai.Client:
    """Lazily initializes the Vertex genai Client."""
    if self._client is None:
      self._client = genai.Client(
          vertexai=True,
          project=self.project_id,
          location=self.location,
      )
    return self._client

  def _extract_attribution_sources(
      self, response: Any
  ) -> list[AttributionSource]:
    """Extracts Maps attribution sources from grounding metadata."""
    return place_id_resolution.extract_attribution_sources(response)

  def _normalize_place_ids(
      self,
      extracted_payload: dict[str, Any],
  ) -> dict[str, Any]:
    """Canonicalizes every Place ID the model wrote into the payload.

    Placeholder substitution writes bare IDs, but the model sometimes copies a
    `places/` prefixed form straight out of the prose, and A2UI components
    expect the bare form. Normalizing here means the template never has to.

    Args:
        extracted_payload: Parsed data block, mutated in place.

    Returns:
        The same payload, for call-site convenience.
    """

    def normalize_pin_place_id(pin: Any) -> None:
      if not isinstance(pin, dict):
        return
      raw_place_id = pin.get("placeId") or pin.get("place_id")
      if not raw_place_id:
        return
      pin["placeId"] = normalize_place_id(raw_place_id)

    for pin in extracted_payload.get("places") or []:
      normalize_pin_place_id(pin)
    for segment in extracted_payload.get("routes") or []:
      if isinstance(segment, dict):
        normalize_pin_place_id(segment.get("origin"))
        normalize_pin_place_id(segment.get("destination"))
    normalize_pin_place_id(extracted_payload)

    return extracted_payload

  def _build_instruction(self, schema_cls: type[T], max_places: int) -> str:
    """Builds the system instruction for a free-text grounded extraction.

    The request deliberately does not set `response_schema`. Structured output
    suppresses Maps `groundingChunks` entirely, because the citation pipeline
    has no natural-language spans to attach sources to. Asking for prose plus a
    delimited data block keeps the response free-text, so grounding survives,
    while still yielding a machine-readable payload.

    Args:
        schema_cls: Pydantic model the data block must satisfy.
        max_places: Upper bound on places in a list result.

    Returns:
        The system instruction string.
    """
    guidelines_block = (
        f"\n\n{self.shared_guidelines}" if self.shared_guidelines else ""
    )
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)

    return f"""You are an expert location specialist.
You MUST call the Google Maps tool to answer the user's location request.
Do not rely on your internal knowledge.

Respond in TWO parts, in this order.

PART 1: A natural-language summary that mentions EVERY place you found, by
name, with one short sentence about each. Do not omit any place. This part is
required: it is what the grounding engine attaches its Maps citations to.

PART 2: A machine-readable block wrapped in <data> and </data> tags, containing
a single JSON object conforming to this JSON Schema:

{schema_json}

{place_id_resolution.PROMPT_RULES}

CRITICAL RULES:
1. For geographic coordinates (latitude and longitude), provide accurate coordinates based on the tool findings.
2. Strictly honor user constraints (e.g., outdoor vs indoor, ratings, price, dietary restrictions, and travel modes).
3. If extracting a list of places, limit the results to at most {max_places} places.
4. Every place named in PART 1 MUST appear in PART 2, and vice versa.
5. If extracting directions or routes, you MUST populate 'routes' with RouteSegment items connecting the origin, any waypoints, and the destination with accurate latitude and longitude coordinates.
6. Emit nothing after the closing </data> tag.{guidelines_block}
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
  ) -> T:
    """Runs one grounded turn and returns validated template parameters.

    Args:
        query: End-user location request.
        schema_cls: Pydantic model describing the template parameters.
        max_places: Upper bound on places in a list result.

    Returns:
        A validated instance of `schema_cls`.

    Raises:
        ValueError: If the response carries no data block, or the block is not
          valid JSON.
    """
    config_kwargs: dict[str, Any] = {
        "system_instruction": self._build_instruction(schema_cls, max_places),
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

    attribution_sources = self._extract_attribution_sources(response)
    if not attribution_sources:
      logger.warning(
          "Grounding returned no Maps attribution sources; Place ID"
          " placeholders cannot be resolved for query %r.",
          query,
      )

    data_block = self._parse_data_block(response.text)
    substituted_block, unresolved = place_id_resolution.resolve_place_ids(
        data_block, attribution_sources
    )

    try:
      extracted_payload = json.loads(substituted_block)
    except (json.JSONDecodeError, TypeError) as e:
      raise ValueError(f"<data> block was not valid JSON: {e}") from e

    logger.info(
        "GwGM extraction: %d attribution source(s), %d placeholder(s) left"
        " unresolved.",
        len(attribution_sources),
        unresolved,
    )

    return schema_cls.model_validate(
        self._normalize_place_ids(extracted_payload)
    )
