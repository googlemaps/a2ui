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

"""Tests for Place Answer extraction schema and pin synthesis."""

import unittest

import pydantic

from templates.place_answer.schema import ExtractorSchema
from templates.place_answer.schema import PlaceAnswerExtractorSchema


class PlaceAnswerSchemaTest(unittest.TestCase):

  def test_place_answer_extractor_schema_valid(self):
    data = {
        "heading": "Parking at Space Needle",
        "summary": "Yes, valet parking is available at the Space Needle.",
        "name": "Space Needle",
        "place_id": "ChIJ-bfVTh8VkFQR6yFmQ34e2mo",
        "lat": 47.6205,
        "lng": -122.3493,
        "zoom": 16,
    }
    schema = PlaceAnswerExtractorSchema(**data)
    self.assertEqual(schema.heading, "Parking at Space Needle")
    self.assertEqual(
        schema.summary, "Yes, valet parking is available at the Space Needle."
    )
    self.assertEqual(schema.place_id, "ChIJ-bfVTh8VkFQR6yFmQ34e2mo")
    self.assertEqual(schema.name, "Space Needle")
    self.assertEqual(schema.lat, 47.6205)
    self.assertEqual(schema.lng, -122.3493)
    self.assertEqual(schema.zoom, 16)

  def test_place_answer_extractor_schema_computed_markers(self):
    schema = PlaceAnswerExtractorSchema(
        heading="Pike Place Market",
        summary="Service animals are welcome; pet dogs are permitted outdoors.",
        name="Pike Place Market",
        place_id="ChIJp8JitVlqkFQRx6R94fO0n2Y",
        lat=47.6097,
        lng=-122.3422,
    )
    self.assertEqual(len(schema.markers), 1)
    marker = schema.markers[0]
    self.assertEqual(marker.lat, 47.6097)
    self.assertEqual(marker.lng, -122.3422)
    self.assertEqual(marker.label, "Pike Place Market")
    self.assertEqual(marker.placeId, "ChIJp8JitVlqkFQRx6R94fO0n2Y")

    dumped = schema.model_dump(exclude_none=True)
    self.assertIn("markers", dumped)
    self.assertEqual(len(dumped["markers"]), 1)
    self.assertEqual(
        dumped["markers"][0]["placeId"], "ChIJp8JitVlqkFQRx6R94fO0n2Y"
    )

  def test_place_answer_extractor_schema_strips_markdown_heading(self):
    schema = PlaceAnswerExtractorSchema(
        heading="### Space Needle",
        summary="Observation tower.",
        name="Space Needle",
        place_id="ChIJ123",
        lat=47.62,
        lng=-122.35,
    )
    self.assertEqual(schema.heading, "Space Needle")

  def test_place_answer_extractor_schema_synthesizes_heading_from_name(self):
    schema = PlaceAnswerExtractorSchema(
        heading="",
        summary="Observation tower.",
        name="Space Needle",
        place_id="ChIJ123",
        lat=47.62,
        lng=-122.35,
    )
    self.assertEqual(schema.heading, "Space Needle")

  def test_place_answer_extractor_schema_synthesizes_heading_fallback(self):
    schema = PlaceAnswerExtractorSchema(
        heading="",
        summary="Observation tower.",
        name="",
        place_id="ChIJ123",
        lat=47.62,
        lng=-122.35,
    )
    self.assertEqual(schema.heading, "Place Answer")

  def test_place_answer_extractor_schema_requires_mandatory_fields(self):
    with self.assertRaises(pydantic.ValidationError):
      PlaceAnswerExtractorSchema(
          heading="Space Needle",
          summary="Observation tower.",
          name="Space Needle",
          lat=47.62,
          lng=-122.35,
      )

    with self.assertRaises(pydantic.ValidationError):
      PlaceAnswerExtractorSchema(
          heading="Space Needle",
          summary="Observation tower.",
          name="Space Needle",
          place_id="ChIJ123",
      )

  def test_extractor_schema_alias(self):
    self.assertIs(ExtractorSchema, PlaceAnswerExtractorSchema)


if __name__ == "__main__":
  unittest.main()
