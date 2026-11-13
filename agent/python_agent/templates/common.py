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
    "normalize_markdown_text",
    "normalize_name_and_label",
    "parse_user_coordinates",
]
