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
  description: str = Field(
      description=(
          "Individualized markdown description for this single place card."
          " Start with 1 vivid opening sentence bolding the place name and"
          " rating (e.g., '**Place Name** (4.8★) offers...'), followed by a"
          " blank line (\\n\\n) and 2 concise bullet points on separate lines:"
          " '* **Standout feature**: Specific vibe, specialty, or suitability"
          " for the prompt' and '* **Logistics**: Street address, **numerical"
          " distance** (**estimated travel time** from the reference location),"
          " and operating hours'."
      ),
  )
  placePrimaryType: PlacePrimaryType | None = Field(  # pylint: disable=invalid-name
      default=None,
      description=(
          "Optional primary POI category type string. Use 'generic' for"
          " geopolitical or non-POI places (cities, towns, neighborhoods,"
          " regions, countries, addresses)."
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_place_item(cls, data: Any) -> Any:
    if isinstance(data, dict):
      normalize_name_and_label(data)
      desc = data.get("description")
      if isinstance(desc, str):
        data["description"] = normalize_markdown_text(desc)
    return data


class NearbyPlacesDepthExtractorSchema(BaseModel):
  """Structured parameters to render a nearby places depth (2 to 4 places, default 3) UI update."""

  clamped_collections: ClassVar[tuple[str, ...]] = ("places",)

  heading: str = Field(
      description=(
          "A concise, constraint-confirming primary heading in sentence case"
          " reflecting the prompt and primary reference location (e.g.,"
          " 'Restaurants perfect for a romantic date night near The Plaza"
          " Hotel'). Plain text only; do NOT include markdown hashtags or"
          " conversational filler."
      ),
  )
  places: list[NearbyPlaceItem] = Field(
      min_length=1,
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
  def normalize_heading(cls, data: Any) -> Any:
    """Normalizes markdown headers in heading if present."""
    if isinstance(data, dict):
      heading = data.get("heading")
      if heading and isinstance(heading, str):
        data["heading"] = re.sub(r"^#+\s*", "", heading).strip()
    return data

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
