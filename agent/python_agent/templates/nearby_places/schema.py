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

"""Pydantic extraction schema for nearby_places (depth 3-4) template bundle."""

import re
from typing import Any, ClassVar

import pydantic

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
          "Individualized markdown description starting with one vivid opening"
          " hook sentence followed by 2 concise markdown bullet points with"
          " bold labels (e.g., '* **The Vibe**: ...', '* **Logistics**: ...')."
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
      if "name" not in data and "label" in data:
        data["name"] = data["label"]
      if "label" not in data and "name" in data:
        data["label"] = data["name"]
    return data


class NearbyPlacesExtractorSchema(BaseModel):
  """Structured parameters to render a nearby places depth (3-4) UI update."""

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
  center_lat: float = Field(description="Latitude of the center of results")
  center_lng: float = Field(description="Longitude of the center of results")
  zoom: int = Field(
      default=14, description="Recommended map zoom level (typically 14)"
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


ExtractorSchema = NearbyPlacesExtractorSchema

__all__ = [
    "ExtractorSchema",
    "NearbyPlaceItem",
    "NearbyPlacesExtractorSchema",
    "Pin",
    "PlacePrimaryType",
]
