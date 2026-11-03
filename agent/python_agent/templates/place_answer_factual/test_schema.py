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

"""Tests for Place Answer Factual extraction schema."""

import unittest

import pydantic

from templates.place_answer_factual.schema import ExtractorSchema
from templates.place_answer_factual.schema import PlaceAnswerFactualExtractorSchema


class PlaceAnswerFactualSchemaTest(unittest.TestCase):

  def test_place_answer_factual_extractor_schema_valid(self):
    data = {
        "heading": "Parking at Space Needle",
        "summary": "Yes, valet parking is available at the Space Needle.",
        "name": "Space Needle",
        "placeId": "ChIJ-bfVTh8VkFQR6yFmQ34e2mo",
    }
    schema = PlaceAnswerFactualExtractorSchema(**data)
    self.assertEqual(schema.heading, "Parking at Space Needle")
    self.assertEqual(
        schema.summary, "Yes, valet parking is available at the Space Needle."
    )
    self.assertEqual(schema.placeId, "ChIJ-bfVTh8VkFQR6yFmQ34e2mo")
    self.assertEqual(schema.name, "Space Needle")

  def test_place_answer_factual_extractor_schema_normalizes_inline_bullets(
      self,
  ):
    schema = PlaceAnswerFactualExtractorSchema(
        heading="Pike Place Market",
        summary=(
            "Service animals are welcome; pet dogs are permitted outdoors. *"
            " **Outdoor areas**: Leashed dogs allowed on sidewalks."
        ),
        name="Pike Place Market",
        placeId="ChIJp8JitVlqkFQRx6R94fO0n2Y",
    )
    self.assertIn("\n\n* **Outdoor areas**:", schema.summary)

  def test_place_answer_factual_extractor_schema_strips_markdown_heading(self):
    schema = PlaceAnswerFactualExtractorSchema(
        heading="### Space Needle",
        summary="Observation tower.",
        name="Space Needle",
        placeId="ChIJ123",
    )
    self.assertEqual(schema.heading, "Space Needle")

  def test_place_answer_factual_extractor_schema_synthesizes_heading_from_name(
      self,
  ):
    schema = PlaceAnswerFactualExtractorSchema(
        heading="",
        summary="Observation tower.",
        name="Space Needle",
        placeId="ChIJ123",
    )
    self.assertEqual(schema.heading, "Space Needle")

  def test_place_answer_factual_extractor_schema_synthesizes_heading_fallback(
      self,
  ):
    schema = PlaceAnswerFactualExtractorSchema(
        heading="",
        summary="Observation tower.",
        name="",
        placeId="ChIJ123",
    )
    self.assertEqual(schema.heading, "Place Answer")

  def test_place_answer_factual_extractor_schema_requires_mandatory_fields(
      self,
  ):
    with self.assertRaises(pydantic.ValidationError):
      PlaceAnswerFactualExtractorSchema(
          heading="Space Needle",
          summary="Observation tower.",
          name="Space Needle",
      )

  def test_extractor_schema_alias(self):
    self.assertIs(ExtractorSchema, PlaceAnswerFactualExtractorSchema)


if __name__ == "__main__":
  unittest.main()
