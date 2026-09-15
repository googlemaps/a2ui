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

from templates.local_search.schema import Pin

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


# Applied when the model omits a travel mode or names one Maps cannot route.
# Dropping the field instead would leave the map with no route rendering at
# all, which reads as a broken card.
_DEFAULT_TRAVEL_MODE = "driving"


def _synthesize_heading(routes: Any) -> str:
  """Builds a heading from route endpoints when the model omitted one.

  Args:
    routes: Raw `routes` value, before field validation, so its elements are
      normally plain dicts.

  Returns:
    A plain-text heading naming whichever endpoints are available.
  """
  if not (isinstance(routes, list) and routes):
    return "Directions"

  first, last = routes[0], routes[-1]
  origin = first.get("origin") if isinstance(first, dict) else None
  destination = last.get("destination") if isinstance(last, dict) else None
  origin_label = origin.get("label") if isinstance(origin, dict) else None
  destination_label = (
      destination.get("label") if isinstance(destination, dict) else None
  )

  if origin_label and destination_label:
    return f"Route from {origin_label} to {destination_label}"
  if destination_label:
    return f"Directions to {destination_label}"
  return "Directions"


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
          "A natural, direct resolution of the route prompt describing"
          " approximate travel duration and distance (e.g. 'Driving from"
          " [Origin] to [Destination] takes about 19 minutes (14 miles).')."
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
          " bicycling. Must match the user's requested travel mode."
      ),
  )

  @pydantic.model_validator(mode="before")
  @classmethod
  def normalize_directions_data(cls, data: Any) -> Any:
    """Repairs the heading and travel mode before field validation.

    The model is asked for both but does not reliably return either in a
    usable form. Repairing them here keeps the merger free of any knowledge
    of this bundle.

    Args:
      data: Raw input to the model, usually the extracted parameter dict.

    Returns:
      The input with a plain-text `heading` and a canonical `travel_mode`.
    """
    if not isinstance(data, dict):
      return data

    data["travel_mode"] = (
        normalize_travel_mode(data.get("travel_mode")) or _DEFAULT_TRAVEL_MODE
    )

    heading = data.get("heading")
    if isinstance(heading, str) and heading.strip():
      data["heading"] = re.sub(r"^#+\s*", "", heading).strip()
    else:
      data["heading"] = _synthesize_heading(data.get("routes"))

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
