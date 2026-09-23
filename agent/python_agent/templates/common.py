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

from typing import Any, Literal

import pydantic

PlacePrimaryType = Literal[
    "food_and_drink",
    "retail",
    "outdoor",
    "service",
    "lodging",
    "emergency",
    "entertainment",
    "ev",
    "airport",
    "parking",
    "closed",
    "generic",
]


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
      description="Optional primary POI category type string",
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


__all__ = [
    "Pin",
    "PlacePrimaryType",
]
