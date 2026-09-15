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

"""Pydantic schemas for structured data extraction from LLM responses (re-export shim)."""

from templates.directions.schema import (
    DirectionsExtractorSchema,
    Pin,
    RouteSegment,
    TRAVEL_MODE_MAP,
    normalize_travel_mode,
)
from templates.local_search.schema import (
    LocalSearchExtractorSchema,
    PlacePin,
    PlacePrimaryType,
)

__all__ = [
    "DirectionsExtractorSchema",
    "LocalSearchExtractorSchema",
    "Pin",
    "PlacePin",
    "PlacePrimaryType",
    "RouteSegment",
    "TRAVEL_MODE_MAP",
    "normalize_travel_mode",
]
