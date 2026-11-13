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

"""Shared schema models and primitive types for MAUI template bundles."""

import math
import re
from typing import Any, Literal

import pydantic

_USER_LOCATION_PREFIX_RE = re.compile(
    r"(?i)\b(?:my\s+location\s+is|my\s+location|current\s+location|"
    r"user(?:'s)?\s+location|my\s+coordinates\s+are|my\s+coordinates|"
    r"i\s+am\s+at)\b"
)

# Numeric coordinate pair that requires at least one decimal point so that
# street numbers like "35, 37 West 44th St" are never parsed as coordinates.
_NUMERIC_COORD_RE = re.compile(
    r"^[-+]?\d{1,2}\.\d+\s*,\s*[-+]?\d{1,3}\.\d+(?![\d.])"
)

_DECIMAL_PAIR_RE = re.compile(
    r"(?<![\d.])(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})(?![\d.])"
)

_EXPLICIT_METADATA_TAGS_RE = re.compile(
    r"(?i)\b(?:my\s+location|current\s+location|user(?:'s)?\s+location|"
    r"my\s+coordinates)\b"
)


def _validate_coordinates(lat: float, lng: float) -> tuple[float, float] | None:
  """Validates that lat/lng are finite, within bounds, and not Null Island."""
  if not math.isfinite(lat) or not math.isfinite(lng):
    return None
  if lat < -90.0 or lat > 90.0 or lng < -180.0 or lng > 180.0:
    return None
  if lat == 0.0 and lng == 0.0:
    return None
  return (lat, lng)


def parse_user_coordinates(query: str) -> tuple[float, float] | None:
  """Parses user coordinates (lat, lng) from query.

  Follows a 2-priority parsing strategy:
  1. Explicit user-location tags (e.g. 'my location: lat, lng', 'i am at ...').
     Coordinates must have decimal points. If a tag (e.g. 'i am at Landmark')
     is non-numeric, subsequent explicit matches are checked. If explicit
     metadata tags ('my location', 'current location', 'user location',
     'my coordinates') were present and none yielded valid decimal coordinates,
     returns None without falling through to Priority 2.
  2. Unlabeled single coordinate pair with >= 3 fractional digits. If multiple
     coordinate pairs exist, returns None.

  Args:
    query: User query string.

  Returns:
    (latitude, longitude) tuple or None if not found or invalid.
  """
  if not query or not isinstance(query, str):
    return None

  # Priority 1: Check for explicit user-location tags using finditer
  for match in _USER_LOCATION_PREFIX_RE.finditer(query):
    tail = query[match.end() :].lstrip(" :=(")
    coord_match = _NUMERIC_COORD_RE.match(tail)
    if coord_match:
      try:
        lat_str, lng_str = coord_match.group(0).split(",")
        lat = float(lat_str.strip())
        lng = float(lng_str.strip())
        valid = _validate_coordinates(lat, lng)
        if valid is not None:
          return valid
      except (ValueError, TypeError):
        pass

  # If explicit metadata tags were present but none contained valid coords
  # (e.g. '(my location is: Ha-Dekel St 2, Jerusalem)'), short-circuit to None.
  if _EXPLICIT_METADATA_TAGS_RE.search(query):
    return None

  # Priority 2: Unlabeled single decimal coordinate pair with >= 3 fractional
  # digits
  matches = _DECIMAL_PAIR_RE.findall(query)
  if len(matches) == 1:
    try:
      lat = float(matches[0][0])
      lng = float(matches[0][1])
      return _validate_coordinates(lat, lng)
    except (ValueError, TypeError):
      return None

  return None


_EARTH_RADIUS_METERS = 6371000.0
_SUPERLATIVE_PROXIMITY_RE = re.compile(
    r"\b(?:nearest|closest)\b", re.IGNORECASE
)
_CITE_MARKER_RE = re.compile(r"\[cite:([0-9,\s]+)\]")


def haversine_distance(
    coord1: tuple[float, float], coord2: tuple[float, float]
) -> float:
  """Calculates great-circle distance in meters between two (lat, lng) points."""
  lat1, lng1 = coord1
  lat2, lng2 = coord2
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  delta_phi = math.radians(lat2 - lat1)
  delta_lambda = math.radians(lng2 - lng1)

  a = (
      math.sin(delta_phi / 2.0) ** 2
      + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
  )
  c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
  return _EARTH_RADIUS_METERS * c


def is_superlative_proximity_query(query: str | None) -> bool:
  """Returns True strictly if query contains superlative proximity keywords.

  Never matches 'best', 'top', 'highest rated', or 'nearby'.

  Args:
    query: Raw query string or None.
  """
  if not query or not isinstance(query, str):
    return False
  return bool(_SUPERLATIVE_PROXIMITY_RE.search(query))


def _remap_citation_markers(
    text: str | None, old_to_new: dict[int, int]
) -> str | None:
  """Remaps 1-based [cite:N] citation markers in text based on old_to_new index mapping."""
  if not text or not isinstance(text, str):
    return text

  def _replace_match(match: re.Match[str]) -> str:
    raw_nums = match.group(1)
    tokens = [t.strip() for t in raw_nums.split(",") if t.strip()]
    remapped = []
    for t in tokens:
      try:
        old_idx = int(t)
        new_idx = old_to_new.get(old_idx, old_idx)
        remapped.append(str(new_idx))
      except ValueError:
        remapped.append(t)
    return f"[cite:{', '.join(remapped)}]"

  return _CITE_MARKER_RE.sub(_replace_match, text)


def sort_extracted_places_by_proximity(model_instance: Any, query: str) -> Any:
  """Sorts model_instance.places ascending by proximity for superlative queries.

  Args:
      model_instance: The Pydantic model instance (e.g.
        LocalSearchExtractorSchema).
      query: User input query string.

  Returns:
      The model_instance (reordered in-place if applicable).
  """
  if not is_superlative_proximity_query(query):
    return model_instance

  places = getattr(model_instance, "places", None)
  if not isinstance(places, list) or len(places) < 2:
    return model_instance

  # Origin selection:
  # Use (anchor.lat, anchor.lng) ONLY when anchor has a non-empty placeId and
  # valid finite non-(0,0) coordinates; otherwise fall back to
  # parse_user_coordinates(query).
  origin = None
  anchor = getattr(model_instance, "anchor_marker", None)
  if anchor is not None and bool(getattr(anchor, "placeId", None)):
    anchor_lat = getattr(anchor, "lat", None)
    anchor_lng = getattr(anchor, "lng", None)
    if anchor_lat is not None and anchor_lng is not None:
      try:
        origin = _validate_coordinates(float(anchor_lat), float(anchor_lng))
      except (ValueError, TypeError):
        origin = None

  if origin is None:
    origin = parse_user_coordinates(query)

  if origin is None:
    return model_instance

  # Calculate distance for each place with valid lat/lng
  def _get_dist(p: Any) -> float:
    lat = getattr(p, "lat", None)
    lng = getattr(p, "lng", None)
    if lat is not None and lng is not None:
      try:
        valid = _validate_coordinates(float(lat), float(lng))
        if valid is not None:
          return haversine_distance(origin, valid)
      except (ValueError, TypeError):
        pass
    return float("inf")

  original_order = list(places)
  places.sort(key=_get_dist)

  if places != original_order:
    # 1. Markdown bullet block reordering
    summary = getattr(model_instance, "summary", None)
    if isinstance(summary, str):
      bullet_blocks = re.findall(r"(?m)^[*-]\s+.*(?:\n[ \t]+.*)*", summary)
      if len(bullet_blocks) == len(places):
        matched_blocks = []
        all_matched = True
        for p in places:
          p_name = getattr(p, "name", "")
          escaped_name = re.escape(p_name)
          pattern_first_line = re.compile(
              rf"(?i)(?:\*\*|\b){escaped_name}(?:\*\*|\b)"
          )
          pattern_fallback = re.compile(rf"(?i){escaped_name}")

          matching = []
          for b in bullet_blocks:
            first_line = b.splitlines()[0]
            if pattern_first_line.search(first_line):
              matching.append(b)

          if len(matching) != 1:
            matching = [b for b in bullet_blocks if pattern_fallback.search(b)]

          if len(matching) == 1:
            matched_blocks.append(matching[0])
          else:
            all_matched = False
            break

        # Ensure exact 1-to-1 bijection
        if all_matched and len(set(matched_blocks)) == len(bullet_blocks):
          new_bullets_str = "\n".join(matched_blocks)
          first_bullet = bullet_blocks[0]
          last_bullet = bullet_blocks[-1]
          start_idx = summary.find(first_bullet)
          end_idx = summary.rfind(last_bullet) + len(last_bullet)
          if start_idx != -1 and end_idx != -1:
            model_instance.summary = (
                summary[:start_idx] + new_bullets_str + summary[end_idx:]
            )

    # 2. 1P Dolphin Citation Remapping ([cite:N])
    old_to_new = {
        (orig_idx + 1): places.index(item) + 1
        for orig_idx, item in enumerate(original_order)
    }

    current_summary = getattr(model_instance, "summary", None)
    if isinstance(current_summary, str):
      model_instance.summary = _remap_citation_markers(
          current_summary, old_to_new
      )

    for p in places:
      p_desc = getattr(p, "description", None)
      if isinstance(p_desc, str):
        p.description = _remap_citation_markers(p_desc, old_to_new)

  return model_instance


PlacePrimaryType = Literal[
    "food_and_drink",
    "outdoor",
    "retail",
    "gas_station",
    "ev",
    "bank",
    "lodging",
    "emergency",
    "entertainment",
    "airport",
    "parking",
    "generic",
]


def normalize_name_and_label(data: dict[str, Any]) -> dict[str, Any]:
  """Synchronizes 'name' and 'label' fields when one is omitted."""
  if "name" not in data and "label" in data:
    data["name"] = data["label"]
  if "label" not in data and "name" in data:
    data["label"] = data["name"]
  return data


def normalize_markdown_text(text: str) -> str:
  """Normalizes escaped newlines and markdown bullet list boundaries."""
  text = text.replace("\\n", "\n")
  text = re.sub(r"([^\s*])[ \t]+(\*\s+)", r"\1\n\2", text)
  text = re.sub(r"(?m)^((?!\s*[*-]\s+)[^\n]+)\n([*-]\s+)", r"\1\n\n\2", text)
  return text


class Pin(pydantic.BaseModel):
  """Representation of a Map Pin."""

  lat: float = pydantic.Field(description="Latitude coordinate")
  lng: float = pydantic.Field(description="Longitude coordinate")
  label: str = pydantic.Field(
      description=(
          "Descriptive display label string (e.g. name of address, business, or"
          " landmark)"
      )
  )
  # Note: Using camelCase field name to match frontend A2UI requirements.
  placeId: str | None = pydantic.Field(  # pylint: disable=invalid-name
      default=None, description="Optional Google Maps Place ID"
  )
  placePrimaryType: PlacePrimaryType | None = pydantic.Field(  # pylint: disable=invalid-name
      default=None,
      description=(
          "Optional primary POI category type string. Use 'generic' for"
          " geopolitical or non-POI places (cities, towns, neighborhoods,"
          " regions, countries, addresses)."
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_label(cls, data: Any) -> Any:
    """Normalizes the pin label.

    If 'label' is missing but 'name' is present, copies 'name' to 'label'.
    If 'label' is still empty, defaults to 'Location' to ensure
    the UI always has a valid string to render for the marker (avoiding raw
    Place IDs).

    Args:
      data: The input dictionary before validation.

    Returns:
      The normalized dictionary.
    """
    if isinstance(data, dict):
      normalize_name_and_label(data)
      if not data.get("label"):
        data["label"] = "Location"
    return data


__all__ = [
    "Pin",
    "PlacePrimaryType",
    "haversine_distance",
    "is_superlative_proximity_query",
    "normalize_markdown_text",
    "normalize_name_and_label",
    "parse_user_coordinates",
    "sort_extracted_places_by_proximity",
]
