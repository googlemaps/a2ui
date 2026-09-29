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

"""Unit tests for local_search template bundle extraction schema."""

import unittest
import pydantic
from templates.local_search.schema import (
    ExtractorSchema,
    LocalSearchExtractorSchema,
    Pin,
    PlacePin,
)


class TestLocalSearchSchema(unittest.TestCase):
  """Unit tests for local_search schema and data normalization."""

  def test_pin_normalize_label_copies_name(self):
    data = {"lat": 1.0, "lng": 2.0, "name": "My Place"}
    pin = Pin(**data)
    self.assertEqual(pin.label, "My Place")

  def test_pin_normalize_label_defaults_to_location(self):
    data = {"lat": 1.0, "lng": 2.0}
    pin = Pin(**data)
    self.assertEqual(pin.label, "Location")

  def test_pin_with_place_primary_type(self):
    data = {
        "lat": 1.0,
        "lng": 2.0,
        "label": "Coffee Shop",
        "placePrimaryType": "food_and_drink",
    }
    pin = Pin(**data)
    self.assertEqual(pin.placePrimaryType, "food_and_drink")

  def test_place_pin_with_place_primary_type(self):
    data = {
        "placeId": "ChIJ123",
        "name": "Coffee Shop",
        "lat": 1.0,
        "lng": 2.0,
        "placePrimaryType": "food_and_drink",
    }
    pin = PlacePin(**data)
    self.assertEqual(pin.placePrimaryType, "food_and_drink")

  def test_pin_normalize_label_preserves_existing(self):
    data = {
        "lat": 1.0,
        "lng": 2.0,
        "label": "Custom Label",
        "name": "Ignored Name",
    }
    pin = Pin(**data)
    self.assertEqual(pin.label, "Custom Label")

  def test_local_search_extractor_schema_with_heading(self):
    """Verifies that LocalSearchExtractorSchema validates with heading."""
    data = {
        "heading": "5 Transit Stops Near Seattle Center",
        "summary": "Here are 5 transit stops.",
        "center_lat": 47.6205,
        "center_lng": -122.3493,
        "places": [{
            "placeId": "ChIJ111",
            "name": "Stop 1",
            "lat": 47.62,
            "lng": -122.35,
        }],
    }
    schema = LocalSearchExtractorSchema(**data)
    self.assertEqual(schema.heading, "5 Transit Stops Near Seattle Center")

  def test_local_search_extractor_schema_heading_strips_markdown_hashtags(
      self,
  ):
    """Verifies that leading markdown hashtags in heading are stripped."""
    data = {
        "heading": "### Best Bakeries",
        "summary": "Here are bakeries.",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "places": [{"placeId": "p1", "name": "B1", "lat": 47.6, "lng": -122.3}],
    }
    schema = LocalSearchExtractorSchema(**data)
    self.assertEqual(schema.heading, "Best Bakeries")

  def test_local_search_extractor_schema_missing_heading_fails_validation(self):
    """Verifies that omitting heading raises ValidationError."""
    data = {
        "summary": "Here are 5 transit stops.",
        "center_lat": 47.6205,
        "center_lng": -122.3493,
        "places": [{
            "placeId": "ChIJ111",
            "name": "Stop 1",
            "lat": 47.62,
            "lng": -122.35,
        }],
    }
    with self.assertRaises(pydantic.ValidationError):
      LocalSearchExtractorSchema(**data)

  def test_local_search_extractor_schema_computed_markers(self):
    """Verifies that markers are computed from places automatically."""
    data = {
        "heading": "Coffee places",
        "summary": "Here are 2 coffee places.",
        "center_lat": 47.62,
        "center_lng": -122.35,
        "places": [
            {
                "placeId": "ChIJ111",
                "name": "Espresso Vivace",
                "lat": 47.62,
                "lng": -122.32,
                "placePrimaryType": "food_and_drink",
            },
            {
                "placeId": "ChIJ222",
                "name": "Milstead & Co.",
                "lat": 47.64,
                "lng": -122.35,
            },
        ],
    }
    schema = LocalSearchExtractorSchema(**data)
    self.assertEqual(len(schema.markers), 2)
    self.assertEqual(schema.markers[0].label, "Espresso Vivace")
    self.assertEqual(schema.markers[0].lat, 47.62)
    self.assertEqual(schema.markers[0].lng, -122.32)
    self.assertEqual(schema.markers[0].placeId, "ChIJ111")
    self.assertEqual(schema.markers[0].placePrimaryType, "food_and_drink")

    self.assertEqual(schema.markers[1].label, "Milstead & Co.")
    self.assertEqual(schema.markers[1].placeId, "ChIJ222")
    self.assertIsNone(schema.markers[1].placePrimaryType)

    # Verify model_dump includes markers
    dumped = schema.model_dump(exclude_none=True)
    self.assertIn("markers", dumped)
    self.assertEqual(len(dumped["markers"]), 2)
    self.assertEqual(dumped["markers"][0]["label"], "Espresso Vivace")
    self.assertEqual(dumped["markers"][0]["placeId"], "ChIJ111")
    self.assertEqual(dumped["markers"][0]["placePrimaryType"], "food_and_drink")
    self.assertNotIn("placePrimaryType", dumped["markers"][1])

  def test_local_search_extractor_schema_rejects_an_empty_places_list(self):
    """Verifies that a local search card with nothing to show fails validation.

    The layout renders a place list and its map markers, so zero places
    produces a blank map. Rejecting it here is what degrades the response to
    plain text.
    """
    data = {
        "heading": "No places",
        "summary": "No places found.",
        "center_lat": 47.62,
        "center_lng": -122.35,
        "places": [],
    }
    with self.assertRaises(pydantic.ValidationError):
      LocalSearchExtractorSchema(**data)

  def test_local_search_extractor_schema_rejects_place_without_place_id(self):
    """Verifies that a place missing placeId fails validation."""
    data = {
        "heading": "Coffee places",
        "summary": "Here are coffee places.",
        "center_lat": 47.62,
        "center_lng": -122.35,
        "places": [{
            "name": "Coffee Shop Without ID",
            "lat": 47.62,
            "lng": -122.35,
        }],
    }
    with self.assertRaises(pydantic.ValidationError):
      LocalSearchExtractorSchema(**data)

  def test_extractor_schema_alias(self):
    """Verifies ExtractorSchema alias matches LocalSearchExtractorSchema."""
    self.assertIs(ExtractorSchema, LocalSearchExtractorSchema)


if __name__ == "__main__":
  unittest.main()
