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

"""Unit tests for shared template models and primitives."""

import typing
import unittest

import pydantic

from templates import common


class PinTest(unittest.TestCase):
  """Tests for the Pin model and its validators."""

  def test_pin_valid_construction(self):
    pin = common.Pin(
        lat=37.7749,
        lng=-122.4194,
        label="San Francisco",
        placeId="ChIJIQBpAG2ahYAR_6128GcTUEo",
        placePrimaryType="retail",
    )
    self.assertEqual(pin.lat, 37.7749)
    self.assertEqual(pin.lng, -122.4194)
    self.assertEqual(pin.label, "San Francisco")
    self.assertEqual(pin.placeId, "ChIJIQBpAG2ahYAR_6128GcTUEo")
    self.assertEqual(pin.placePrimaryType, "retail")

  def test_pin_normalizes_name_to_label_when_label_is_missing(self):
    data = {
        "lat": 47.6062,
        "lng": -122.3321,
        "name": "Pike Place Market",
    }
    pin = common.Pin.model_validate(data)
    self.assertEqual(pin.label, "Pike Place Market")

  def test_pin_defaults_to_location_when_label_and_name_are_empty(self):
    data = {
        "lat": 47.6062,
        "lng": -122.3321,
    }
    pin = common.Pin.model_validate(data)
    self.assertEqual(pin.label, "Location")

  def test_pin_preserves_explicit_label_even_if_name_is_present(self):
    data = {
        "lat": 47.6062,
        "lng": -122.3321,
        "label": "Custom Label",
        "name": "Ignored Name",
    }
    pin = common.Pin.model_validate(data)
    self.assertEqual(pin.label, "Custom Label")

  def test_pin_requires_coordinates(self):
    with self.assertRaises(pydantic.ValidationError):
      common.Pin.model_validate({"label": "Missing Coords"})


class PlacePrimaryTypeTest(unittest.TestCase):
  """Tests for the supported POI taxonomy."""

  def test_matches_supported_taxonomy(self):
    # Pinned so that adding or removing a category is a deliberate edit that
    # also has to be mirrored in the client lookups and the agent skills.
    self.assertEqual(
        typing.get_args(common.PlacePrimaryType),
        (
            "food_and_drink",
            "outdoor",
            "retail",
            "gas_station",
            "ev",
            "bank",
            "lodging",
            "emergency",
            "entertainment",
            "airport",
            "parking",
            "generic",
        ),
    )

  def test_pin_accepts_every_supported_type(self):
    for place_primary_type in typing.get_args(common.PlacePrimaryType):
      with self.subTest(placePrimaryType=place_primary_type):
        pin = common.Pin(
            lat=1.0,
            lng=2.0,
            label="Place",
            placePrimaryType=place_primary_type,
        )
        self.assertEqual(pin.placePrimaryType, place_primary_type)

  def test_pin_rejects_retired_types(self):
    # `service` was split into `gas_station`/`bank`, and `closed` was dropped.
    for place_primary_type in ("service", "closed"):
      with self.subTest(placePrimaryType=place_primary_type):
        with self.assertRaises(pydantic.ValidationError):
          common.Pin(
              lat=1.0,
              lng=2.0,
              label="Place",
              placePrimaryType=place_primary_type,
          )


class NormalizationHelpersTest(unittest.TestCase):
  """Tests for shared normalization helpers in common.py."""

  def test_normalize_name_and_label_copies_label_to_name(self):
    data = {"label": "Pike Place Market"}
    common.normalize_name_and_label(data)
    self.assertEqual(data["name"], "Pike Place Market")
    self.assertEqual(data["label"], "Pike Place Market")

  def test_normalize_name_and_label_copies_name_to_label(self):
    data = {"name": "Space Needle"}
    common.normalize_name_and_label(data)
    self.assertEqual(data["name"], "Space Needle")
    self.assertEqual(data["label"], "Space Needle")

  def test_normalize_markdown_text_unescapes_newlines_and_formats_bullets(self):
    raw = (
        "**Bistro One** is cozy.\\n* **The vibe**: Cozy. * **Logistics**: Easy."
    )
    normalized = common.normalize_markdown_text(raw)
    self.assertEqual(
        normalized,
        "**Bistro One** is cozy.\n\n* **The vibe**: Cozy.\n* **Logistics**:"
        " Easy.",
    )

  def test_normalize_markdown_text_preserves_indented_sub_bullets(self):
    raw = (
        "Intro overview.\\n* **Venue** (4.8★)\\n  * **Logistics**: 123 Main St,"
        " **0.4 miles** (**8 min walk**)"
    )
    normalized = common.normalize_markdown_text(raw)
    self.assertEqual(
        normalized,
        "Intro overview.\n\n* **Venue** (4.8★)\n  * **Logistics**: 123 Main St,"
        " **0.4 miles** (**8 min walk**)",
    )


class ParseUserCoordinatesTest(unittest.TestCase):
  """Unit tests for parse_user_coordinates."""

  def test_priority1_explicit_tags_valid(self):
    """Verifies explicit location tags parse valid decimal coordinate pairs."""
    test_cases = [
        (
            "Coffee shops near me (my location: 37.7749, -122.4194)",
            (37.7749, -122.4194),
        ),
        ("my location is 37.7749, -122.4194", (37.7749, -122.4194)),
        ("current location: 40.7128, -74.0060", (40.7128, -74.0060)),
        ("user location = 51.5074, -0.1278", (51.5074, -0.1278)),
        ("user's location: -33.8688, 151.2093", (-33.8688, 151.2093)),
        ("my coordinates: 35.6762, 139.6503", (35.6762, 139.6503)),
        ("my coordinates are: 37.7749, -122.4194", (37.7749, -122.4194)),
        ("i am at 37.7749, -122.4194", (37.7749, -122.4194)),
        ("i am at: (37.7749, -122.4194)", (37.7749, -122.4194)),
        ("MY LOCATION: 37.7749, -122.4194", (37.7749, -122.4194)),
    ]
    for query, expected in test_cases:
      with self.subTest(query=query):
        coords = common.parse_user_coordinates(query)
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], expected[0], places=4)
        self.assertAlmostEqual(coords[1], expected[1], places=4)

  def test_priority1_rejects_integer_street_numbers(self):
    """Verifies street numbers like 'I am at 35, 37 West 44th St' return None."""
    query = "I am at 35, 37 West 44th St"
    self.assertIsNone(common.parse_user_coordinates(query))

  def test_priority1_continues_past_non_numeric_tag_to_valid_tag(self):
    """Verifies continues checking finditer matches when first tag is non-numeric."""
    query = (
        "I am at O'Hare, find deep dish (my location is: 41.9867507,"
        " -87.8721602)"
    )
    coords = common.parse_user_coordinates(query)
    self.assertIsNotNone(coords)
    self.assertAlmostEqual(coords[0], 41.9867507, places=4)
    self.assertAlmostEqual(coords[1], -87.8721602, places=4)

  def test_priority1_short_circuits_when_explicit_tag_has_no_coords(self):
    """Verifies that if explicit metadata tags are present without coords, returns None."""
    query = "Coffee near me (my location is: Ha-Dekel St 2, Jerusalem)"
    self.assertIsNone(common.parse_user_coordinates(query))

    query2 = "Find parks near current location: Main Street 123, New York"
    self.assertIsNone(common.parse_user_coordinates(query2))

  def test_priority2_unlabeled_single_coordinate_pair(self):
    self.assertEqual(
        common.parse_user_coordinates("Find coffee near 37.7749, -122.4194"),
        (37.7749, -122.4194),
    )

  def test_priority1_conversational_prefix_falls_through_to_priority2(self):
    """Verifies 'I am at Landmark' falls through to Priority 2 coordinates."""
    query = "I am at Pike Place Market, find coffee near 47.6085, -122.3400"
    coords = common.parse_user_coordinates(query)
    self.assertIsNotNone(coords)
    self.assertAlmostEqual(coords[0], 47.6085, places=4)
    self.assertAlmostEqual(coords[1], -122.3400, places=4)

  def test_priority2_rejects_multiple_coordinate_pairs(self):
    query = "Directions from 37.7749, -122.4194 to 37.8044, -122.2712"
    self.assertIsNone(common.parse_user_coordinates(query))

  def test_priority2_rejects_insufficient_fractional_digits(self):
    self.assertIsNone(common.parse_user_coordinates("near 37.77, -122.41"))
    self.assertIsNone(common.parse_user_coordinates("near 37.7, -122.4"))

  def test_validation_bounds_and_null_island(self):
    self.assertIsNone(
        common.parse_user_coordinates("my location: 95.0000, 10.0000")
    )
    self.assertIsNone(
        common.parse_user_coordinates("my location: 0.0000, 0.0000")
    )


class SortExtractedPlacesByProximityTest(unittest.TestCase):
  """Unit tests for sort_extracted_places_by_proximity and citation remapping."""

  def test_sort_extracted_places_by_proximity_superlative(self):
    """Verifies sorting places closest first and reordering summary bullets."""

    class MockPlace:

      def __init__(self, name, lat, lng, description=""):
        self.name = name
        self.lat = lat
        self.lng = lng
        self.description = description

    class MockModel:

      def __init__(self, places, summary=None, anchor_marker=None):
        self.places = places
        self.summary = summary
        self.anchor_marker = anchor_marker

    origin = (47.6205, -122.3493)  # Space Needle
    p_far = MockPlace("Joe's Cafe", 47.7000, -122.3493, "Great coffee [cite:1]")
    p_near = MockPlace(
        "Near Coffee", 47.6220, -122.3493, "Fast espresso [cite:2]"
    )
    summary = (
        "- Joe's Cafe: A great cafe [cite:1]\n- Near Coffee: Quick espresso"
        " [cite:2]"
    )

    model = MockModel([p_far, p_near], summary=summary)
    query = f"Find the nearest cafe to {origin[0]}, {origin[1]}"

    res = common.sort_extracted_places_by_proximity(model, query)
    self.assertEqual(res.places[0].name, "Near Coffee")
    self.assertEqual(res.places[1].name, "Joe's Cafe")
    # Verify [cite:N] remapping in summary and description:
    # Near Coffee is now place 1 -> cites [cite:1]
    # Joe's Cafe is now place 2 -> cites [cite:2]
    self.assertIn("[cite:1]", res.summary.splitlines()[0])
    self.assertIn("[cite:2]", res.summary.splitlines()[1])
    self.assertEqual(res.places[0].description, "Fast espresso [cite:1]")
    self.assertEqual(res.places[1].description, "Great coffee [cite:2]")

  def test_sort_extracted_places_null_island_anchor_falls_back_to_query(self):
    """Verifies Null Island anchor coordinates fall back to query coordinates."""

    class MockAnchor:

      def __init__(self, lat, lng, place_id):
        self.lat = lat
        self.lng = lng
        self.place_id = place_id

      @property
      def placeId(self):  # pylint: disable=invalid-name
        return self.place_id

    class MockPlace:

      def __init__(self, name, lat, lng):
        self.name = name
        self.lat = lat
        self.lng = lng

    class MockModel:

      def __init__(self, places, summary=None, anchor_marker=None):
        self.places = places
        self.summary = summary
        self.anchor_marker = anchor_marker

    # Anchor has Null Island coordinates (0.0, 0.0) -> should fall back to
    # query coordinates.
    anchor = MockAnchor(0.0, 0.0, "ChIJ_NULL_ISLAND")
    p_far = MockPlace("Far Cafe", 47.7000, -122.3493)
    p_near = MockPlace("Near Cafe", 47.6220, -122.3493)
    model = MockModel([p_far, p_near], summary="Summary", anchor_marker=anchor)
    query = "Find closest cafe (my location: 47.6205, -122.3493)"

    res = common.sort_extracted_places_by_proximity(model, query)
    self.assertEqual(res.places[0].name, "Near Cafe")
    self.assertEqual(res.places[1].name, "Far Cafe")


if __name__ == "__main__":
  unittest.main()
