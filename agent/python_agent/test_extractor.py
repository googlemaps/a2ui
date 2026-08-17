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

"""Tests for extractor.py."""

import unittest
import pydantic
from python_agent.extractor import (
    DirectionsExtractorSchema,
    LocalSearchExtractorSchema,
    Pin,
    PlacePin,
)


class TestExtractor(unittest.TestCase):
  """Unit tests for extractor schemas and data normalization."""

  def test_pin_normalize_label_copies_name(self):
    data = {"lat": 1.0, "lng": 2.0, "name": "My Place"}
    pin = Pin(**data)
    self.assertEqual(pin.label, "My Place")

  def test_pin_normalize_label_defaults_to_location(self):
    data = {"lat": 1.0, "lng": 2.0}
    pin = Pin(**data)
    self.assertEqual(pin.label, "Location")

  def test_pin_normalize_label_preserves_existing(self):
    data = {
        "lat": 1.0,
        "lng": 2.0,
        "label": "Custom Label",
        "name": "Ignored Name",
    }
    pin = Pin(**data)
    self.assertEqual(pin.label, "Custom Label")

  def test_directions_extractor_schema_normalize_travel_mode(self):
    """Verifies that travel mode is normalized to lowercase."""
    data = {
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

  def test_directions_extractor_schema_missing_travel_mode_fails_validation(
      self,
  ):
    """Verifies that omitting travel_mode raises ValidationError."""
    data = {
        "summary": "Directions summary",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "routes": [{
            "origin": {"lat": 37.4, "lng": 126.9, "label": "Start"},
            "destination": {"lat": 37.6, "lng": 127.1, "label": "End"},
        }],
    }
    with self.assertRaises(pydantic.ValidationError):
      DirectionsExtractorSchema(**data)

  def test_directions_extractor_schema_invalid_travel_mode_fails_validation(
      self,
  ):
    """Verifies that invalid travel_mode values raise ValidationError."""
    for invalid_mode in ["flying", "", None, "scooter", 123]:
      with self.subTest(invalid_mode=invalid_mode):
        data = {
            "summary": "Directions summary",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "routes": [],
            "travel_mode": invalid_mode,
        }
        with self.assertRaises(pydantic.ValidationError):
          DirectionsExtractorSchema(**data)

  def test_directions_extractor_schema_all_valid_modes(self):
    """Verifies all valid travel modes are accepted."""
    for mode in ["driving", "walking", "transit", "bicycling"]:
      with self.subTest(mode=mode):
        data = {
            "summary": f"Going via {mode}",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "routes": [],
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
              "summary": "Commute",
              "center_lat": 37.5,
              "center_lng": 127.0,
              "routes": [],
              "travel_mode": synonym,
          }
          schema = DirectionsExtractorSchema(**data)
          self.assertEqual(schema.travel_mode, expected_mode)


if __name__ == "__main__":
  unittest.main()
