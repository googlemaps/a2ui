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

"""Pydantic extraction schema for directions template bundle."""

import re
from typing import Any, Literal

import pydantic

from templates.common import normalize_markdown_text
from templates.common import Pin

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class RouteSegment(BaseModel):
  """A segment of a route, containing an origin and a destination pin."""

  origin: Pin = Field(description="The starting location pin of this segment")
  destination: Pin = Field(
      description="The ending location pin of this segment"
  )


TRAVEL_MODE_MAP: dict[str, str] = {
    "walk": "walking",
    "walking": "walking",
    "pedestrian": "walking",
    "foot": "walking",
    "on foot": "walking",
    "on_foot": "walking",
    "drive": "driving",
    "driving": "driving",
    "car": "driving",
    "auto": "driving",
    "automobile": "driving",
    "bike": "bicycling",
    "biking": "bicycling",
    "bicycling": "bicycling",
    "cycling": "bicycling",
    "bicycle": "bicycling",
    "transit": "transit",
    "bus": "transit",
    "train": "transit",
    "subway": "transit",
    "tube": "transit",
    "metro": "transit",
    "tram": "transit",
    "rail": "transit",
    "light rail": "transit",
    "ferry": "transit",
    "public transit": "transit",
    "public_transit": "transit",
    "public transport": "transit",
    "public_transport": "transit",
}


def normalize_travel_mode(mode: Any) -> str | None:
  """Normalizes a raw travel mode string to a canonical travel mode."""
  if not mode:
    return None
  return TRAVEL_MODE_MAP.get(str(mode).lower().strip())


class DirectionsExtractorSchema(BaseModel):
  """Structured parameters to render a directions UI update."""

  heading: str = Field(
      description=(
          "A concise, constraint-confirming primary heading for the response."
          " Plain text only (e.g., 'Walking route from Seattle Center to Pike"
          " Place Market', 'Driving directions to JFK Airport')."
      )
  )
  summary: str = Field(
      description=(
          "A scannable markdown resolution that directly answers the route"
          " prompt. Start with a concise introductory overview bolding the"
          " origin, destination, approximate travel duration (rounded to the"
          " nearest minute, or 'less than a minute' if under 30s; e.g.,"
          " '**about 20 minutes**'), and numerical distance in local units"
          " (miles vs. km, rounded to a whole number for driving/transit; e.g.,"
          " '**14 miles**'), followed by a blank line (\\n\\n) and 2 to 3"
          " concise markdown bullet points:\n"
          "- Standard routes: '* **Route details**: ...' (primary roads,"
          " specific transit lines and stations, intermediate stops) and"
          " '* **Arrival & logistics**: ...' (destination address, operating"
          " hours, parking or transfer tips).\n"
          "- Option comparisons (e.g., driving vs. transit, train vs. light"
          " rail, alternative corridors): summarize all options in the intro,"
          " provide a dedicated bullet for each option's duration, distance,"
          " and route details, and conclude with a"
          " '* **Recommendation**: ...' bullet.\n"
          "- Temporal/route constraints (departure time, rush hour, scenic"
          " preference, road/line avoidance): explicitly include the"
          " traffic-adjusted duration range or confirm how the route satisfies"
          " the constraint."
      ),
  )
  center_lat: float = Field(
      description="Latitude of the center of the route map"
  )
  center_lng: float = Field(
      description="Longitude of the center of the route map"
  )
  zoom: int = Field(
      default=12, description="Recommended map zoom level (typically 12)"
  )
  routes: list[RouteSegment] = Field(
      min_length=1,
      description=(
          "A list of route segments connecting the origin, intermediate"
          " waypoints, and the destination in order."
      ),
  )
  travel_mode: Literal["driving", "walking", "transit", "bicycling"] = Field(
      description=(
          "The transit travel mode, one of: driving, walking, transit,"
          " bicycling. Must match the user's requested travel mode (or the"
          " primary/recommended mode when comparing multiple travel modes)."
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_directions_data(cls, data: Any) -> Any:
    """Normalizes travel mode and markdown in heading in directions data."""
    if not isinstance(data, dict):
      return data

    heading = data.get("heading")
    if isinstance(heading, str):
      data["heading"] = re.sub(r"^#+\s*", "", heading).strip()

    summary = data.get("summary")
    if isinstance(summary, str):
      data["summary"] = normalize_markdown_text(summary)

    if "travel_mode" in data and data["travel_mode"]:
      normalized = normalize_travel_mode(data["travel_mode"])
      if normalized:
        data["travel_mode"] = normalized

    return data


ExtractorSchema = DirectionsExtractorSchema

__all__ = [
    "DirectionsExtractorSchema",
    "ExtractorSchema",
    "Pin",
    "RouteSegment",
    "TRAVEL_MODE_MAP",
    "normalize_travel_mode",
]
