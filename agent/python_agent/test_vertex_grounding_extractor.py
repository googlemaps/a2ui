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

"""Unit tests for VertexGroundingExtractor."""

import json
from typing import Any
import unittest
from unittest import mock

from extractor import DirectionsExtractorSchema, LocalSearchExtractorSchema
from vertex_grounding_extractor import GroundingChunk, VertexGroundingExtractor, normalize_maps_title, normalize_place_id


def _create_mock_response(
    text: str = "",
    chunks: list[tuple[str, str, str]] | None = None,
    json_data: dict[str, Any] | None = None,
) -> mock.MagicMock:
  """Builds a mock Vertex AI generate_content response with grounding chunks.

  Args:
      text: Model output text or JSON string.
      chunks: Optional list of (title, place_id, uri) tuples.
      json_data: Optional dict to serialize as response text JSON.

  Returns:
      Mock response object matching the Google GenAI SDK candidate structure.
  """
  mock_response = mock.MagicMock()
  mock_response.text = json.dumps(json_data) if json_data is not None else text
  mock_chunks = []
  for item in chunks or []:
    title = item[0]
    place_id = item[1]
    uri = item[2] if len(item) > 2 else ""
    mock_chunk = mock.MagicMock()
    mock_chunk.maps.title = title
    mock_chunk.maps.place_id = place_id
    mock_chunk.maps.uri = uri
    mock_chunks.append(mock_chunk)

  mock_meta = mock.MagicMock()
  mock_meta.grounding_chunks = mock_chunks
  mock_candidate = mock.MagicMock()
  mock_candidate.grounding_metadata = mock_meta
  mock_response.candidates = [mock_candidate]
  return mock_response


def _create_place_pin_dict(
    name: str,
    place_id: str = "",
    lat: float = 40.75,
    lng: float = -73.98,
) -> dict[str, Any]:
  """Creates a minimal place dictionary for LocalSearch extractor tests."""
  return {
      "name": name,
      "lat": lat,
      "lng": lng,
      "placeId": place_id,
  }


def _create_local_search_payload(
    places: list[dict[str, Any]],
    heading: str = "3 Coffee Shops near Central Park",
    summary: str = "Found coffee shops.",
) -> dict[str, Any]:
  """Creates a minimal extracted data dictionary for LocalSearch tests."""
  return {
      "heading": heading,
      "summary": summary,
      "center_lat": 40.78,
      "center_lng": -73.96,
      "zoom": 13,
      "places": places,
  }


def _create_directions_payload(
    origin_label: str = "Times Square",
    destination_label: str = "Central Park",
    origin_place_id: str | None = None,
    destination_place_id: str | None = None,
) -> dict[str, Any]:
  """Creates a minimal extracted data dictionary for Directions tests."""
  return {
      "summary": f"Directions from {origin_label} to {destination_label}.",
      "center_lat": 40.77,
      "center_lng": -73.97,
      "zoom": 13,
      "travel_mode": "walking",
      "routes": [{
          "origin": {
              "lat": 40.758,
              "lng": -73.985,
              "label": origin_label,
              "placeId": origin_place_id,
          },
          "destination": {
              "lat": 40.782,
              "lng": -73.965,
              "label": destination_label,
              "placeId": destination_place_id,
          },
      }],
  }


class VertexGroundingExtractorTest(unittest.IsolatedAsyncioTestCase):

  def setUp(self):
    super().setUp()
    self.extractor = VertexGroundingExtractor(
        project_id="test-project",
        location="global",
        model_id="gemini-3-flash-preview",
        shared_guidelines="Conversational Text Style Guidelines",
    )

  def test_default_shared_guidelines_empty(self):
    extractor = VertexGroundingExtractor(
        project_id="test-project",
        location="global",
    )
    self.assertEqual(extractor.shared_guidelines, "")

  def test_missing_project_id_raises_value_error(self):
    with self.assertRaises(ValueError) as ctx:
      VertexGroundingExtractor(project_id=None)
    self.assertIn("Vertex AI project_id must be provided", str(ctx.exception))

  def test_normalize_maps_title(self):
    cases = [
        ("Chez Panisse - Google Maps", "chez panisse"),
        ("Blue Bottle Coffee, New York", "blue bottle coffee, new york"),
    ]
    for raw_title, expected in cases:
      with self.subTest(raw_title=raw_title):
        self.assertEqual(normalize_maps_title(raw_title), expected)

  def test_normalize_place_id(self):
    cases = [
        ("places/ChIJ12345", "ChIJ12345"),
        ("ChIJ12345", "ChIJ12345"),
        ("places/custom_id_99", "custom_id_99"),
    ]
    for raw_id, expected in cases:
      with self.subTest(raw_id=raw_id):
        self.assertEqual(normalize_place_id(raw_id), expected)

  def test_extract_grounding_chunks_from_metadata(self):
    mock_response = _create_mock_response(
        chunks=[
            (
                "Sip and Co - Google Maps",
                "places/ChIJK4Gklg1ZwokRmDGLQSxEaUI",
                "https://maps.google.com/?cid=1",
            ),
            (
                "Sote Coffee Roasters",
                "ChIJwR4noh5ZwokREcz36jnEQbo",
                "https://maps.google.com/?cid=2",
            ),
        ]
    )

    grounding_chunks = self.extractor._extract_grounding_chunks(mock_response)
    self.assertEqual(len(grounding_chunks), 2)
    self.assertEqual(
        grounding_chunks[0],
        GroundingChunk(
            title="Sip and Co - Google Maps",
            place_id="places/ChIJK4Gklg1ZwokRmDGLQSxEaUI",
            uri="https://maps.google.com/?cid=1",
        ),
    )
    self.assertEqual(
        grounding_chunks[1],
        GroundingChunk(
            title="Sote Coffee Roasters",
            place_id="ChIJwR4noh5ZwokREcz36jnEQbo",
            uri="https://maps.google.com/?cid=2",
        ),
    )

  def test_extract_grounding_chunks_empty_or_missing_metadata(self):
    mock_response = mock.MagicMock()
    mock_response.candidates = []
    self.assertEqual(
        self.extractor._extract_grounding_chunks(mock_response), []
    )

    mock_candidate = mock.MagicMock()
    mock_candidate.grounding_metadata = None
    mock_response.candidates = [mock_candidate]
    self.assertEqual(
        self.extractor._extract_grounding_chunks(mock_response), []
    )

  def test_hydrate_grounding_metadata_local_search(self):
    grounding_chunks = [
        GroundingChunk(
            title="Sip and Co - Google Maps",
            place_id="places/ChIJ_SIP_123",
            uri="https://maps.google.com/?cid=sip",
        ),
        GroundingChunk(
            title="Sote Coffee Roasters New York",
            place_id="ChIJ_SOTE_456",
        ),
    ]

    extracted_payload = _create_local_search_payload([
        _create_place_pin_dict("Sip and Co", place_id=""),
        _create_place_pin_dict("Sote Coffee", place_id=""),
        _create_place_pin_dict(
            "Solid State Coffee", place_id="places/ChIJ_SOLID_STATE_789"
        ),
    ])

    hydrated_payload = self.extractor._hydrate_grounding_metadata(
        extracted_payload, grounding_chunks
    )

    validated_schema = LocalSearchExtractorSchema.model_validate(
        hydrated_payload
    )
    self.assertEqual(validated_schema.places[0].placeId, "ChIJ_SIP_123")
    self.assertEqual(validated_schema.places[1].placeId, "ChIJ_SOTE_456")
    self.assertEqual(validated_schema.places[2].placeId, "ChIJ_SOLID_STATE_789")

  def test_hydrate_grounding_metadata_normalizes_without_chunks(self):
    extracted_payload = _create_local_search_payload([
        _create_place_pin_dict("Test Cafe", place_id="places/ChIJ_TEST_123"),
    ])
    hydrated_payload = self.extractor._hydrate_grounding_metadata(
        extracted_payload, []
    )
    validated_schema = LocalSearchExtractorSchema.model_validate(
        hydrated_payload
    )
    self.assertEqual(validated_schema.places[0].placeId, "ChIJ_TEST_123")

  def test_hydrate_grounding_metadata_directions(self):
    grounding_chunks = [
        GroundingChunk(
            title="Times Square",
            place_id="ChIJ_TIMES_SQUARE",
        ),
        GroundingChunk(
            title="Central Park",
            place_id="ChIJ_CENTRAL_PARK",
        ),
    ]

    extracted_payload = _create_directions_payload(
        origin_label="Times Square",
        destination_label="Central Park",
    )

    hydrated_payload = self.extractor._hydrate_grounding_metadata(
        extracted_payload, grounding_chunks
    )

    validated_schema = DirectionsExtractorSchema.model_validate(
        hydrated_payload
    )
    self.assertEqual(
        validated_schema.routes[0].origin.placeId, "ChIJ_TIMES_SQUARE"
    )
    self.assertEqual(
        validated_schema.routes[0].destination.placeId, "ChIJ_CENTRAL_PARK"
    )

  async def test_extract_uses_response_schema_and_hydrates(self):
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe")],
            summary="Test summary",
        ),
        chunks=[(
            "Test Cafe - Google Maps",
            "places/ChIJ_TEST_CAFE",
            "https://maps.google.com/?cid=123",
        )],
    )

    mock_client = mock.MagicMock()
    mock_generate = mock.AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    self.extractor._client = mock_client

    result = await self.extractor.extract(
        "coffee shops", LocalSearchExtractorSchema, max_places=3
    )

    self.assertEqual(result.heading, "3 Coffee Shops near Central Park")
    self.assertEqual(result.summary, "Test summary")
    self.assertEqual(len(result.places), 1)
    self.assertEqual(result.places[0].placeId, "ChIJ_TEST_CAFE")

    # Verify config passed to generate_content
    mock_generate.assert_awaited_once()
    call_args = mock_generate.call_args
    config = call_args.kwargs.get("config")
    self.assertIsNotNone(config)
    self.assertEqual(config.response_mime_type, "application/json")
    self.assertIn("Strictly honor user constraints", config.system_instruction)
    self.assertIn("at most 3 places", config.system_instruction)
    self.assertIn(
        "Do not rely on your internal knowledge.", config.system_instruction
    )
    self.assertIn(
        "Conversational Text Style Guidelines", config.system_instruction
    )


if __name__ == "__main__":
  unittest.main()
