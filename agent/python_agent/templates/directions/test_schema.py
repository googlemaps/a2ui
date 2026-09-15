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

"""Unit tests for directions template bundle extraction schema."""

import unittest
import pydantic
from templates.directions.schema import (
    DirectionsExtractorSchema,
    ExtractorSchema,
    normalize_travel_mode,
)


class TestDirectionsSchema(unittest.TestCase):
  """Unit tests for directions schema and data normalization."""

  def test_directions_extractor_schema_normalize_travel_mode(self):
    """Verifies that travel mode is normalized to lowercase."""
    data = {
        "heading": "Commute Route",
        "summary": "Commute is 1h.",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "routes": [{
            "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
            "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
        }],
        "travel_mode": "WALK",
    }
    schema = DirectionsExtractorSchema(**data)
    self.assertEqual(schema.travel_mode, "walking")

  def test_directions_extractor_schema_with_routes(self):
    """Verifies that DirectionsExtractorSchema can be initialized with routes."""
    data = {
        "heading": "Scenic Route",
        "summary": "Scenic route.",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "travel_mode": "driving",
        "routes": [
            {
                "origin": {"lat": 37.4, "lng": 126.9, "label": "A"},
                "destination": {"lat": 37.5, "lng": 127.0, "label": "B"},
            },
            {
                "origin": {"lat": 37.5, "lng": 127.0, "label": "B"},
                "destination": {"lat": 37.6, "lng": 127.1, "label": "C"},
            },
        ],
    }
    schema = DirectionsExtractorSchema(**data)
    self.assertEqual(len(schema.routes), 2)
    self.assertEqual(schema.routes[0].origin.label, "A")
    self.assertEqual(schema.routes[1].destination.label, "C")
    self.assertEqual(schema.travel_mode, "driving")

  def test_directions_extractor_schema_missing_travel_mode_defaults(self):
    """Verifies that omitting travel_mode resolves to driving."""
    data = {
        "heading": "Directions Route",
        "summary": "Directions summary",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "routes": [{
            "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
            "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
        }],
    }
    schema = DirectionsExtractorSchema(**data)
    self.assertEqual(schema.travel_mode, "driving")

  def test_directions_extractor_schema_unroutable_travel_mode_defaults(self):
    """Verifies that a mode Maps cannot route resolves to driving."""
    for unroutable_mode in ["flying", "", None, "scooter", 123]:
      with self.subTest(unroutable_mode=unroutable_mode):
        data = {
            "heading": "Directions Route",
            "summary": "Directions summary",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "routes": [{
                "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
                "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
            }],
            "travel_mode": unroutable_mode,
        }
        schema = DirectionsExtractorSchema(**data)
        self.assertEqual(schema.travel_mode, "driving")

  def test_directions_extractor_schema_all_valid_modes(self):
    """Verifies all valid travel modes are accepted."""
    for mode in ["driving", "walking", "transit", "bicycling"]:
      with self.subTest(mode=mode):
        data = {
            "heading": f"Going via {mode}",
            "summary": f"Going via {mode}",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "routes": [{
                "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
                "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
            }],
            "travel_mode": mode,
        }
        schema = DirectionsExtractorSchema(**data)
        self.assertEqual(schema.travel_mode, mode)

  def test_directions_extractor_schema_normalize_all_synonyms(self):
    """Verifies all synonyms and case/whitespace variations normalize cleanly."""
    synonym_cases = {
        "transit": [
            "bus",
            "train",
            "subway",
            "tube",
            "metro",
            "tram",
            "rail",
            "light rail",
            "ferry",
            "public transit",
            "public_transit",
            "public transport",
            "public_transport",
            "transit",
            " BUS ",
            "Train",
            " Metro ",
            "SUBWAY",
            "Public Transit",
            " public_transport ",
            " Light Rail ",
        ],
        "walking": [
            "walk",
            "walking",
            "pedestrian",
            "foot",
            "on foot",
            "on_foot",
            " WALK ",
            "Foot",
            " pedestrian ",
            "On Foot",
            " on_foot ",
        ],
        "bicycling": [
            "bike",
            "biking",
            "bicycling",
            "cycling",
            "bicycle",
            " BIKE ",
            "Bicycle",
            " Cycling ",
        ],
        "driving": [
            "car",
            "drive",
            "driving",
            "auto",
            "automobile",
            " CAR ",
            "Drive",
            " Auto ",
            " Automobile ",
        ],
    }
    for expected_mode, synonyms in synonym_cases.items():
      for synonym in synonyms:
        with self.subTest(synonym=synonym, expected=expected_mode):
          data = {
              "heading": "Commute",
              "summary": "Commute",
              "center_lat": 37.5,
              "center_lng": 127.0,
              "routes": [{
                  "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
                  "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
              }],
              "travel_mode": synonym,
          }
          schema = DirectionsExtractorSchema(**data)
          self.assertEqual(schema.travel_mode, expected_mode)

  def test_directions_extractor_schema_with_heading(self):
    """Verifies that DirectionsExtractorSchema validates with heading."""
    data = {
        "heading": "Walking route from Seattle Center to Pike Place Market",
        "summary": "Walking takes about 25 minutes (1 mile).",
        "center_lat": 47.6205,
        "center_lng": -122.3493,
        "travel_mode": "walking",
        "routes": [{
            "origin": {
                "lat": 47.6205,
                "lng": -122.3493,
                "label": "Seattle Center",
            },
            "destination": {
                "lat": 47.6097,
                "lng": -122.3422,
                "label": "Pike Place Market",
            },
        }],
    }
    schema = DirectionsExtractorSchema(**data)
    self.assertEqual(
        schema.heading, "Walking route from Seattle Center to Pike Place Market"
    )

  def test_directions_extractor_schema_strips_markdown_heading(self):
    """Verifies that a markdown header prefix is stripped from the heading."""
    schema = DirectionsExtractorSchema(
        heading="### Driving Route",
        summary="About 15 minutes.",
        center_lat=37.5,
        center_lng=127.0,
        travel_mode="driving",
        routes=[{
            "origin": {"lat": 37.5, "lng": 127.0, "label": "Origin"},
            "destination": {"lat": 37.6, "lng": 127.1, "label": "Dest"},
        }],
    )
    self.assertEqual(schema.heading, "Driving Route")

  def test_directions_extractor_schema_synthesizes_missing_heading(self):
    """Verifies that an omitted heading is built from the route endpoints."""
    data = {
        "summary": "Walking takes about 25 minutes (1 mile).",
        "center_lat": 47.6205,
        "center_lng": -122.3493,
        "travel_mode": "walking",
        "routes": [{
            "origin": {
                "lat": 47.6205,
                "lng": -122.3493,
                "label": "Seattle Center",
            },
            "destination": {
                "lat": 47.6097,
                "lng": -122.3422,
                "label": "Pike Place Market",
            },
        }],
    }
    schema = DirectionsExtractorSchema(**data)
    self.assertEqual(
        schema.heading, "Route from Seattle Center to Pike Place Market"
    )

  def test_directions_extractor_schema_rejects_an_empty_route_list(self):
    """Verifies that a directions card with nothing to draw fails validation.

    The layout renders a route polyline, so an empty list produces a blank
    map. Rejecting it here is what degrades the response to plain text.
    """
    with self.assertRaises(pydantic.ValidationError):
      DirectionsExtractorSchema(
          heading="Directions",
          summary="No route available.",
          center_lat=47.6205,
          center_lng=-122.3493,
          travel_mode="walking",
          routes=[],
      )

  def test_directions_extractor_schema_still_requires_summary(self):
    """Verifies that the repairs did not relax the other required fields."""
    with self.assertRaises(pydantic.ValidationError):
      DirectionsExtractorSchema(
          heading="Directions",
          center_lng=-122.3493,
          travel_mode="walking",
          routes=[{
              "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
              "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
          }],
      )

  def test_extractor_schema_alias(self):
    """Verifies ExtractorSchema alias matches DirectionsExtractorSchema."""
    self.assertIs(ExtractorSchema, DirectionsExtractorSchema)


if __name__ == "__main__":
  unittest.main()
