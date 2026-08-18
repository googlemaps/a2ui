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

"""Pydantic schemas for structured data extraction from LLM responses."""

from typing import Any, Literal
import pydantic

BaseModel = pydantic.BaseModel
Field = pydantic.Field


class Pin(BaseModel):
  """Representation of a Map Pin."""

  lat: float = Field(description="Latitude coordinate")
  lng: float = Field(description="Longitude coordinate")
  label: str = Field(
      description=(
          "Descriptive display label string (e.g. name of address, business, or"
          " landmark)"
      )
  )
  # Note: Using camelCase field name to match frontend A2UI requirements.
  placeId: str | None = Field(  # pylint: disable=invalid-name
      default=None, description="Optional Google Maps Place ID"
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
      if "label" not in data and "name" in data:
        data["label"] = data["name"]
      if not data.get("label"):
        data["label"] = "Location"
    return data


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


class LocalSearchExtractorSchema(BaseModel):
  """Structured parameters to render a local search UI update."""

  summary: str = Field(
      description=(
          "A detailed response summarizing the search results, answering the"
          " user's query fully. Use markdown formatting (bullet points,"
          " bolding, tables) and break into paragraphs as needed. Bold place"
          " names."
      )
  )
  center_lat: float = Field(description="Latitude of the center of results")
  center_lng: float = Field(description="Longitude of the center of results")
  zoom: int = Field(
      default=13, description="Recommended map zoom level (typically 13)"
  )
  places: list[PlacePin] = Field(
      description="A list of places found (limit to max list size, e.g. 3)"
  )
  anchor_marker: Pin | None = Field(
      default=None,
      description=(
          "Optional starting or focus point marker (e.g. hotel location)"
      ),
  )


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

  summary: str = Field(
      description=(
          "A detailed response summarizing the travel directions, including"
          " key steps, estimated time, and travel mode. Use markdown"
          " formatting and break into paragraphs if helpful."
      )
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
      default_factory=list,
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
    """Normalizes travel mode in directions data."""
    if not isinstance(data, dict):
      return data

    if "travel_mode" in data and data["travel_mode"]:
      normalized = normalize_travel_mode(data["travel_mode"])
      if normalized:
        data["travel_mode"] = normalized

    return data
