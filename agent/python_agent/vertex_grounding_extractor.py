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

import dataclasses
import json
import logging
import re
from typing import Any, TypeVar

from google import genai
from google.genai import types
import pydantic

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=pydantic.BaseModel)


@dataclasses.dataclass(frozen=True)
class GroundingChunk:
  """Represents a normalized grounding chunk extracted from Maps metadata."""

  title: str
  place_id: str
  uri: str = ""


def normalize_maps_title(raw_title: str) -> str:
  """Strips Google Maps branding suffixes and normalizes whitespace and casing.

  Grounding with Google Maps returns raw POI titles that frequently include
  branding suffixes (such as ' - Google Maps', ' – Google Maps', or
  ' — Google Maps'). Meanwhile, the LLM-extracted venue names generated in
  structured output do not include these suffixes. Normalizing both sides to
  lowercase and stripping the suffix enables deterministic title matching.

  Args:
      raw_title: Raw title string from grounding metadata or extracted schema.

  Returns:
      Normalized, lowercase title string with trailing Maps branding stripped.
  """
  cleaned_title = re.sub(
      r"\s*[-–—]\s*Google Maps$", "", raw_title, flags=re.IGNORECASE
  )
  return cleaned_title.strip().lower()


def normalize_place_id(raw_place_id: str) -> str:
  """Normalizes a Place ID by stripping API resource name prefixes.

  Vertex AI Grounding metadata and Google Maps APIs can return Place IDs
  prefixed with 'places/' (e.g., 'places/ChIJ...'). Downstream A2UI components
  and frontend client SDKs expect canonical ChI... identifiers without the
  resource prefix.

  Args:
      raw_place_id: Raw place ID string from grounding chunks or model output.

  Returns:
      Canonical Place ID string without the 'places/' prefix.
  """
  return raw_place_id.strip().removeprefix("places/")


def _build_title_to_place_info_map(
    grounding_chunks: list[GroundingChunk],
) -> dict[str, tuple[str, str]]:
  """Builds a lookup map from normalized venue title to (place_id, uri).

  Args:
      grounding_chunks: List of normalized GroundingChunk objects.

  Returns:
      Dictionary mapping normalized lowercase titles to (place_id, uri) tuples.
  """
  title_to_place_info: dict[str, tuple[str, str]] = {}
  for chunk in grounding_chunks:
    if chunk.title and chunk.place_id:
      normalized_title = normalize_maps_title(chunk.title)
      canonical_place_id = normalize_place_id(chunk.place_id)
      title_to_place_info[normalized_title] = (canonical_place_id, chunk.uri)
  return title_to_place_info


def _find_matching_place_info(
    venue_name: str, title_to_place_info: dict[str, tuple[str, str]]
) -> tuple[str, str] | None:
  """Finds the authoritative Place ID and URI for an extracted venue name.

  Performs a two-pass resolution:
  1. Exact match on normalized title.
  2. Substring containment match to handle minor title variations (e.g.
     model extracted 'Tartinery' vs chunk title 'Tartinery Café').

  Args:
      venue_name: Extracted venue name to match.
      title_to_place_info: Dictionary mapping normalized titles to (place_id,
        uri).

  Returns:
      (place_id, uri) tuple if matched, or None.
  """
  normalized_venue_name = normalize_maps_title(venue_name)
  if not normalized_venue_name:
    return None
  if normalized_venue_name in title_to_place_info:
    return title_to_place_info[normalized_venue_name]
  for candidate_title, place_info in title_to_place_info.items():
    if (
        normalized_venue_name in candidate_title
        or candidate_title in normalized_venue_name
    ):
      return place_info
  return None


def _hydrate_place_pins(
    place_pins: list[Any], title_to_place_info: dict[str, tuple[str, str]]
) -> None:
  """Hydrates placeId into a list of place dictionaries."""
  for place_pin in place_pins:
    if not isinstance(place_pin, dict):
      continue
    venue_name = place_pin.get("name") or place_pin.get("title") or ""
    matched_place_info = _find_matching_place_info(
        venue_name, title_to_place_info
    )
    if matched_place_info:
      canonical_place_id, maps_uri = matched_place_info
      place_pin["placeId"] = canonical_place_id
      if maps_uri and not place_pin.get("uri"):
        place_pin["uri"] = maps_uri
      logger.debug(
          "Hydrated place '%s' with Place ID '%s'",
          venue_name,
          canonical_place_id,
      )
    else:
      logger.warning(
          "Could not find authoritative Place ID for place '%s'", venue_name
      )
    raw_place_id = place_pin.get("placeId") or place_pin.get("place_id")
    if raw_place_id:
      place_pin["placeId"] = normalize_place_id(raw_place_id)


def _hydrate_route_pins(
    route_segments: list[Any], title_to_place_info: dict[str, tuple[str, str]]
) -> None:
  """Hydrates placeId into route origin and destination pins."""
  for segment in route_segments:
    if not isinstance(segment, dict):
      continue
    for pin_role in ("origin", "destination"):
      pin = segment.get(pin_role)
      if isinstance(pin, dict):
        waypoint_label = pin.get("label") or pin.get("name") or ""
        matched_place_info = _find_matching_place_info(
            waypoint_label, title_to_place_info
        )
        if matched_place_info:
          canonical_place_id, _ = matched_place_info
          pin["placeId"] = canonical_place_id
        raw_place_id = pin.get("placeId") or pin.get("place_id")
        if raw_place_id:
          pin["placeId"] = normalize_place_id(raw_place_id)


class VertexGroundingExtractor:
  """Extractor using Vertex AI Grounding with Google Maps (GwGM)."""

  def __init__(
      self,
      project_id: str | None = None,
      location: str = "global",
      model_id: str = "gemini-3.5-flash-lite",
      shared_guidelines: str = "",
  ):
    if not project_id:
      raise ValueError("Vertex AI project_id must be provided.")
    self.project_id = project_id
    self.location = location
    self.model_id = model_id
    self.shared_guidelines = shared_guidelines
    self._client: genai.Client | None = None

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

  def _extract_grounding_chunks(self, response: Any) -> list[GroundingChunk]:
    """Extracts normalized place IDs and titles from grounding metadata."""
    grounding_chunks: list[GroundingChunk] = []
    if not (
        hasattr(response, "candidates")
        and response.candidates
        and hasattr(response.candidates[0], "grounding_metadata")
    ):
      return grounding_chunks

    grounding_metadata = response.candidates[0].grounding_metadata
    if (
        hasattr(grounding_metadata, "grounding_chunks")
        and grounding_metadata.grounding_chunks
    ):
      for candidate_chunk in grounding_metadata.grounding_chunks:
        if hasattr(candidate_chunk, "maps") and candidate_chunk.maps:
          title = getattr(candidate_chunk.maps, "title", None)
          place_id = getattr(candidate_chunk.maps, "place_id", None)
          uri = getattr(candidate_chunk.maps, "uri", "")
          if title and place_id:
            grounding_chunks.append(
                GroundingChunk(
                    title=title,
                    place_id=place_id,
                    uri=uri,
                )
            )
    return grounding_chunks

  def _hydrate_grounding_metadata(
      self,
      extracted_payload: dict[str, Any],
      grounding_chunks: list[GroundingChunk],
  ) -> dict[str, Any]:
    """Hydrates grounding chunk metadata (Place IDs, URIs) into extracted dict data."""
    if not grounding_chunks:
      logger.warning("No grounding chunks available to hydrate place IDs.")
      title_to_place_info = {}
    else:
      title_to_place_info = _build_title_to_place_info_map(grounding_chunks)

    if "places" in extracted_payload and isinstance(
        extracted_payload["places"], list
    ):
      _hydrate_place_pins(extracted_payload["places"], title_to_place_info)
    if "routes" in extracted_payload and isinstance(
        extracted_payload["routes"], list
    ):
      _hydrate_route_pins(extracted_payload["routes"], title_to_place_info)

    return extracted_payload

  async def extract(
      self,
      query: str,
      schema_cls: type[T],
      max_places: int = 5,
  ) -> T:
    """Executes Vertex Maps grounding with native structured output."""
    guidelines_block = (
        f"\n\n{self.shared_guidelines}" if self.shared_guidelines else ""
    )
    instruction = f"""You are an expert location specialist.
You MUST call the Google Maps tool to answer the user's location request.
Do not rely on your internal knowledge.

CRITICAL RULES:
1. For geographic coordinates (latitude and longitude), provide accurate coordinates based on the tool findings.
2. Strictly honor user constraints (e.g., outdoor vs indoor, ratings, price, dietary restrictions, and travel modes).
3. If extracting a list of places, limit the results to at most {max_places} places.
4. For placeId or place_id, provide the Google Maps Place ID (e.g. 'ChI...') if found, or an empty string ("").
5. If extracting directions or routes, you MUST populate 'routes' with RouteSegment items connecting the origin, any waypoints, and the destination with accurate latitude and longitude coordinates.{guidelines_block}
"""

    response = await self.client.aio.models.generate_content(
        model=self.model_id,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=instruction,
            tools=[types.Tool(google_maps=types.GoogleMaps())],
            response_mime_type="application/json",
            response_schema=schema_cls,
        ),
    )

    try:
      extracted_payload = json.loads(response.text or "")
    except (json.JSONDecodeError, TypeError) as e:
      raise ValueError(f"Model output did not contain valid JSON: {e}") from e

    # Extract grounding chunks and hydrate real Place IDs
    grounding_chunks = self._extract_grounding_chunks(response)
    hydrated_payload = self._hydrate_grounding_metadata(
        extracted_payload, grounding_chunks
    )

    # Validate against target Pydantic schema
    return schema_cls.model_validate(hydrated_payload)
