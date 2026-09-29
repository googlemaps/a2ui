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

"""Pydantic extraction schema for local_search template bundle."""

import re
from typing import Any, ClassVar

import pydantic

from templates.common import Pin
from templates.common import PlacePrimaryType

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class PlacePin(BaseModel):
  """Simplified Map Pin representation for search results."""

  # Note: Using camelCase field name to match frontend A2UI requirements.
  # ADK's SetModelResponseTool serialization dumps using field names
  # without aliases.
  placeId: str = Field(  # pylint: disable=invalid-name
      description="The unique Google Maps Place ID"
  )
  name: str = Field(description="Name of the place")
  lat: float = Field(description="Latitude coordinates")
  lng: float = Field(description="Longitude coordinates")
  placePrimaryType: PlacePrimaryType | None = Field(  # pylint: disable=invalid-name
      default=None,
      description="Optional primary POI category type string",
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_place_pin(cls, data: Any) -> Any:
    if isinstance(data, dict):
      if "name" not in data and "label" in data:
        data["name"] = data["label"]
      if "label" not in data and "name" in data:
        data["label"] = data["name"]
    return data


class LocalSearchExtractorSchema(BaseModel):
  """Structured parameters to render a local search UI update."""

  # Collections the extractor prompt explicitly tells the model to limit. A
  # place search can return dozens of candidates, and the model will happily
  # narrate all of them even though the layout renders only `max_list_size`.
  # Bundles whose collections are naturally small omit this and get no
  # constraint paragraph.
  clamped_collections: ClassVar[tuple[str, ...]] = ("places",)

  heading: str = Field(
      description=(
          "A concise, constraint-confirming primary heading in sentence case"
          " that starts with or includes the exact number of places provided"
          " in the UI response, reflecting the prompt and primary reference"
          " location (e.g. '5 vegetarian restaurants near The Plaza Hotel',"
          " '5 transit stops near Seattle Center'). Plain text only; do"
          " NOT include markdown hashtags or conversational filler."
      ),
  )
  summary: str = Field(
      description=(
          "A concise 1-paragraph overview that covers all returned places by"
          " weaving them into natural, contrasting groups (e.g., pairing"
          " lively group-friendly spots vs. intimate neighborhood bistros)"
          " rather than listing them one by one. Broadly characterize the"
          " dining or activity landscape near the reference location using"
          " concrete, sensory details, bolding every place name (e.g.,"
          " **Carmine's** and **Tony's Di Napoli**), and directly addressing"
          " any prompt constraints. For nearby places, never describe"
          " distances as numbers (e.g., do not say '0.3 miles' or '500"
          " meters'); instead generalize (e.g., 'a short walk', 'just steps"
          " away', 'a quick stroll'). Plain text with markdown bolding only;"
          " do NOT include conversational greetings ('Sure!', 'Here are...')"
          " and do NOT list place names in bullet points."
      ),
  )
  center_lat: float = Field(description="Latitude of the center of results")
  center_lng: float = Field(description="Longitude of the center of results")
  zoom: int = Field(
      default=13, description="Recommended map zoom level (typically 13)"
  )
  places: list[PlacePin] = Field(
      min_length=1,
      description="A list of places found (limit to max list size, e.g. 5)",
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


ExtractorSchema = LocalSearchExtractorSchema

__all__ = [
    "ExtractorSchema",
    "LocalSearchExtractorSchema",
    "Pin",
    "PlacePin",
    "PlacePrimaryType",
]
