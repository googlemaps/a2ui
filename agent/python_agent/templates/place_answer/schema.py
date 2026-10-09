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

"""Pydantic extraction schema for place_answer template bundle."""

import re
from typing import Any

import pydantic

from templates.common import Pin

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class PlaceAnswerExtractorSchema(BaseModel):
  """Structured parameters to render a single-place answer UI update."""

  heading: str = Field(
      description=(
          "A concise sentence-case heading naming the place or confirming the"
          " inquiry (e.g., 'Space Needle', 'Parking at Space Needle'). Plain"
          " text only; do NOT include markdown hashtags or conversational"
          " filler."
      ),
  )
  summary: str = Field(
      description=(
          "A concise paragraph directly answering the user's question about"
          " this specific place with grounded facts and context. Do NOT include"
          " conversational greetings ('Sure!', 'Here is...')."
      ),
  )
  place_id: str = Field(
      description="The unique Google Maps Place ID for the place."
  )
  name: str = Field(description="The official name of the place.")
  lat: float = Field(description="Latitude coordinate of the place.")
  lng: float = Field(description="Longitude coordinate of the place.")
  zoom: int = Field(
      default=16,
      description="Recommended map zoom level (default 16 for single place).",
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def resolve_heading(cls, data: Any) -> Any:
    """Strips markdown from heading or synthesizes one from entity name."""
    if not isinstance(data, dict):
      return data
    heading = data.get("heading")
    if isinstance(heading, str) and heading.strip():
      data["heading"] = re.sub(r"^#+\s*", "", heading).strip()
      return data
    name = data.get("name")
    if isinstance(name, str) and name.strip():
      data["heading"] = name.strip()
    else:
      data["heading"] = "Place Answer"
    return data

  @pydantic.computed_field
  @property
  def markers(self) -> list[Pin]:
    """Synthesizes a 1:1 map marker for the single place entity."""
    return [
        Pin(
            lat=self.lat,
            lng=self.lng,
            label=self.name or self.heading,
            placeId=self.place_id,
        )
    ]


ExtractorSchema = PlaceAnswerExtractorSchema

__all__ = [
    "ExtractorSchema",
    "Pin",
    "PlaceAnswerExtractorSchema",
]
