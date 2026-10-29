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

"""Pydantic extraction schema for place_answer_factual template bundle."""

import re
from typing import Any

import pydantic

from templates.common import normalize_markdown_text

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class PlaceAnswerFactualExtractorSchema(BaseModel):
  """Structured parameters to render a single-place factual answer UI update."""

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
          "A scannable factual answer for this place. Start with a concise"
          " direct answer bolding '**Place Name**' and key facts, followed by a"
          " blank line (\\n\\n) and 2 to 3 concise markdown bullet points ('*"
          " **Label**: Detail') covering street address (with **distance** and"
          " **travel time** if a reference point is given), operating hours,"
          " and practical visitor logistics (pricing, accessibility, or"
          " parking)."
      ),
  )
  placeId: str = Field(  # pylint: disable=invalid-name
      description="The unique Google Maps Place ID for the place."
  )
  name: str = Field(description="The official name of the place.")

  @pydantic.model_validator(mode="before")
  @classmethod
  def resolve_heading(cls, data: Any) -> Any:
    """Strips markdown from heading or synthesizes one from entity name."""
    if not isinstance(data, dict):
      return data
    summary = data.get("summary")
    if isinstance(summary, str):
      data["summary"] = normalize_markdown_text(summary)
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


ExtractorSchema = PlaceAnswerFactualExtractorSchema

__all__ = [
    "ExtractorSchema",
    "PlaceAnswerFactualExtractorSchema",
]
