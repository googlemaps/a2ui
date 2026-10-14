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


if __name__ == "__main__":
  unittest.main()
