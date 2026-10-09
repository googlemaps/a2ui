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

"""Tests for nearby_places extraction schema and pin synthesis."""

import unittest

import pydantic

from templates.nearby_places.schema import ExtractorSchema
from templates.nearby_places.schema import NearbyPlaceItem
from templates.nearby_places.schema import NearbyPlacesExtractorSchema


class NearbyPlacesSchemaTest(unittest.TestCase):

  def test_nearby_places_extractor_schema_valid(self):
    schema = NearbyPlacesExtractorSchema(
        heading="3 hidden gem activities near Seattle Center",
        center_lat=47.6205,
        center_lng=-122.3493,
        zoom=14,
        places=[
            NearbyPlaceItem(
                placeId="ChIJ1",
                name="Chihuly Garden and Glass",
                lat=47.6206,
                lng=-122.3505,
                description=(
                    "Vibrant indoor and outdoor glass art exhibition.\n\n*"
                    " **The Vibe**: Immersive botanical glass installations."
                ),
            )
        ],
    )
    self.assertEqual(
        schema.heading, "3 hidden gem activities near Seattle Center"
    )
    self.assertEqual(schema.center_lat, 47.6205)
    self.assertEqual(schema.center_lng, -122.3493)
    self.assertEqual(schema.zoom, 14)
    self.assertEqual(len(schema.places), 1)
    self.assertEqual(schema.places[0].name, "Chihuly Garden and Glass")

  def test_nearby_places_extractor_schema_computed_markers(self):
    schema = NearbyPlacesExtractorSchema(
        heading="Quiet romantic dinner spots near The Plaza Hotel",
        center_lat=40.7644,
        center_lng=-73.9745,
        places=[
            NearbyPlaceItem(
                placeId="ChIJ1",
                name="Bistro One",
                lat=40.765,
                lng=-73.975,
                description="An intimate candlelit French bistro.",
            ),
            NearbyPlaceItem(
                placeId="ChIJ2",
                name="Trattoria Two",
                lat=40.763,
                lng=-73.974,
                description="A warm neighborhood trattoria.",
            ),
        ],
    )
    self.assertEqual(len(schema.markers), 2)
    self.assertEqual(schema.markers[0].lat, 40.765)
    self.assertEqual(schema.markers[0].lng, -73.975)
    self.assertEqual(schema.markers[0].label, "Bistro One")
    self.assertEqual(schema.markers[0].placeId, "ChIJ1")

    dumped = schema.model_dump(exclude_none=True)
    self.assertIn("markers", dumped)
    self.assertEqual(len(dumped["markers"]), 2)
    self.assertEqual(dumped["markers"][1]["placeId"], "ChIJ2")

  def test_nearby_places_extractor_schema_strips_markdown_heading(self):
    schema = NearbyPlacesExtractorSchema(
        heading="### 3 hidden gem activities near Seattle Center",
        center_lat=47.6205,
        center_lng=-122.3493,
        places=[
            NearbyPlaceItem(
                placeId="ChIJ1",
                name="Chihuly Garden and Glass",
                lat=47.6206,
                lng=-122.3505,
                description="Vibrant glass art exhibition.",
            )
        ],
    )
    self.assertEqual(
        schema.heading, "3 hidden gem activities near Seattle Center"
    )

  def test_nearby_place_item_normalizes_label_to_name(self):
    item = NearbyPlaceItem(
        placeId="ChIJ1",
        label="Pike Place Market",
        lat=47.6097,
        lng=-122.3422,
        description="Historic public market.",
    )
    self.assertEqual(item.name, "Pike Place Market")

  def test_nearby_places_extractor_schema_requires_at_least_one_place(self):
    with self.assertRaises(pydantic.ValidationError):
      NearbyPlacesExtractorSchema(
          heading="Empty",
          center_lat=47.6,
          center_lng=-122.3,
          places=[],
      )

  def test_nearby_places_extractor_schema_requires_mandatory_fields(self):
    with self.assertRaises(pydantic.ValidationError):
      NearbyPlacesExtractorSchema(
          heading="Missing coordinates",
          places=[
              NearbyPlaceItem(
                  placeId="ChIJ1",
                  name="Place 1",
                  lat=47.6,
                  lng=-122.3,
                  description="Desc",
              )
          ],
      )

  def test_extractor_schema_alias(self):
    self.assertIs(ExtractorSchema, NearbyPlacesExtractorSchema)


if __name__ == "__main__":
  unittest.main()
