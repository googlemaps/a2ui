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

"""Pydantic extraction schema for nearby_places_depth (2 to 4 places, default 3) template bundle."""

import re
from typing import Any, ClassVar

import pydantic

from templates.common import normalize_markdown_text
from templates.common import normalize_name_and_label
from templates.common import Pin
from templates.common import PlacePrimaryType

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class NearbyPlaceItem(BaseModel):
  """Place representation with individualized reasoning for depth rendering."""

  # Note: Using camelCase field name to match frontend A2UI requirements.
  # ADK's SetModelResponseTool serialization dumps using field names
  # without aliases.
  placeId: str = Field(  # pylint: disable=invalid-name
      description="The unique Google Maps Place ID"
  )
  name: str = Field(description="Name of the place")
  lat: float = Field(description="Latitude coordinates")
  lng: float = Field(description="Longitude coordinates")
  intro: str = Field(
      description=(
          "ONE vivid, sensory opening hook sentence rendered directly beneath"
          " the place heading and above the place card, highlighting the"
          " place's defining character, unique identity, and why it"
          " specifically answers the user's constraints. Do NOT repeat the"
          " numeric star rating (e.g., '4.8★') in the text."
      ),
  )
  description: str = Field(
      description=(
          "2 to 3 concise markdown bullet points rendered below the place"
          " card:\n"
          "1. **Contextual Bullet Points**: 1 to 2 concise markdown bullet"
          " points (`* **Label**: ...`) using bold, domain-appropriate labels"
          " (e.g., **The Vibe**, **Standout Feature**, **Pet Suitability**,"
          " **Timing & Crowds**) that capture what makes the place special and"
          " how it fits the user's specific request—avoiding generic labels"
          " like 'Highlights' or 'Details'.\n"
          "2. **Proactive Logistics**: ALWAYS include at least 1 concise"
          " markdown bullet covering actionable logistical needs: ticketing or"
          " fees, operating hours, parking, peak vs. quiet times, leash rules,"
          " or dress codes."
      ),
  )
  placePrimaryType: PlacePrimaryType = Field(  # pylint: disable=invalid-name
      description=(
          "Primary POI category type string so the map pin displays its"
          " category icon and color. Use 'generic' only when no specific"
          " category applies."
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_place_item(cls, data: Any) -> Any:
    if isinstance(data, dict):
      normalize_name_and_label(data)
      if not data.get("placePrimaryType"):
        data["placePrimaryType"] = "generic"
      intro = data.get("intro")
      desc = data.get("description")
      if not intro and isinstance(desc, str):
        parts = re.split(r"\n+(?=[*-]\s+)", desc.strip(), maxsplit=1)
        if len(parts) == 2:
          data["intro"] = parts[0].strip()
          data["description"] = parts[1].strip()
        else:
          data["intro"] = desc.strip()
      elif isinstance(intro, str) and isinstance(desc, str):
        parts = re.split(r"\n+(?=[*-]\s+)", desc.strip(), maxsplit=1)
        if len(parts) == 2 and parts[0].strip() == intro.strip():
          data["description"] = parts[1].strip()
      if isinstance(data.get("intro"), str):
        data["intro"] = re.sub(r"^#+\s*", "", data["intro"]).strip()
      if isinstance(data.get("description"), str):
        data["description"] = normalize_markdown_text(data["description"])
    return data


class NearbyPlacesDepthExtractorSchema(BaseModel):
  """Structured parameters to render a nearby places depth (2 to 4 places, default 3) UI update."""

  clamped_collections: ClassVar[tuple[str, ...]] = ("places",)

  preamble: str = Field(
      description=(
          "ONE brief, plain sentence that directly answers the prompt and"
          " clarifies the context of the response: what kind of places these"
          " are, the primary reference location, and the range or variety"
          " covered (e.g., 'Try one of these highly-rated spots near the"
          " Lotte, ranging from casual comfort food to upscale French fare',"
          " 'Here are family-friendly parks within a short walk of The Little"
          " Nell, from quiet gardens to a riverside playground'). Only state a"
          " count or constraint the user asked for. Use only the primary"
          " reference location without redundant city/state nesting. No"
          " title-case headline, no markdown, no second sentence."
      ),
  )
  places: list[NearbyPlaceItem] = Field(
      min_length=1,
      max_length=4,
      description=(
          "Curated list of grounded places (typically 3 places, or 2 to 4 if"
          " explicitly requested by the user) with individualized descriptions."
      ),
  )
  anchor_marker: Pin | None = Field(
      default=None,
      description=(
          "Optional starting or focus point marker (e.g. hotel location)"
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_fields(cls, data: Any) -> Any:
    """Normalizes legacy heading alias and strips markdown hashtags from preamble."""
    if isinstance(data, dict):
      if "heading" in data:
        data["preamble"] = data.pop("heading")
      preamble = data.get("preamble")
      if preamble and isinstance(preamble, str):
        data["preamble"] = re.sub(r"^#+\s*", "", preamble).strip()
    return data

  @property
  def heading(self) -> str:
    """Backwards-compatible read alias for preamble."""
    return self.preamble

  @pydantic.computed_field
  @property
  def markers(self) -> list[Pin]:
    """Projects map pins from the places list."""
    return [
        Pin(
            lat=p.lat,
            lng=p.lng,
            label=p.name,
            placeId=p.placeId,
            placePrimaryType=p.placePrimaryType,
        )
        for p in self.places
    ]


ExtractorSchema = NearbyPlacesDepthExtractorSchema

__all__ = [
    "ExtractorSchema",
    "NearbyPlaceItem",
    "NearbyPlacesDepthExtractorSchema",
    "Pin",
    "PlacePrimaryType",
]
