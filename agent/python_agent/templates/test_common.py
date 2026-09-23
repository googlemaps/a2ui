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


if __name__ == "__main__":
  unittest.main()
