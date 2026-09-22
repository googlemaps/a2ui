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

import place_id_resolution
from extractor import DirectionsExtractorSchema, LocalSearchExtractorSchema
from place_id_resolution import AttributionSource
from vertex_grounding_extractor import VertexGroundingExtractor


def _create_mock_response(
    text: str = "",
    chunks: list[tuple[str, str, str]] | None = None,
    json_data: dict[str, Any] | None = None,
    prose: str = "Here is what I found nearby.",
) -> mock.MagicMock:
  """Builds a mock Vertex AI generate_content response with Maps sources.

  When `json_data` is supplied the helper wraps it the way the model is now
  instructed to respond: a prose summary first, which is what the grounding
  engine attaches Maps citations to, then a delimited data block.

  Args:
      text: Raw model output, used verbatim when `json_data` is omitted.
      chunks: Optional list of (title, place_id, uri) tuples.
      json_data: Optional dict to serialize inside the data block.
      prose: Summary text preceding the data block.

  Returns:
      Mock response object matching the Google GenAI SDK candidate structure.
  """
  mock_response = mock.MagicMock()
  if json_data is not None:
    mock_response.text = f"{prose}\n\n<data>{json.dumps(json_data)}</data>"
  else:
    mock_response.text = text
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
    heading: str = "Walking Directions",
) -> dict[str, Any]:
  """Creates a minimal extracted data dictionary for Directions tests."""
  return {
      "heading": heading,
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

  def test_init_with_shared_client_succeeds_without_project_id(self):
    mock_client = mock.MagicMock()
    extractor = VertexGroundingExtractor(client=mock_client)
    self.assertIs(extractor.client, mock_client)

  def test_shared_client_injection_avoids_new_client(self):
    mock_client = mock.MagicMock()
    with mock.patch("google.genai.Client") as mock_genai_cls:
      extractor = VertexGroundingExtractor(
          project_id="test-proj", client=mock_client
      )
      self.assertIs(extractor.client, mock_client)
      mock_genai_cls.assert_not_called()

  def test_model_id_normalization(self):
    """Verifies model ID prefix stripping for various formats."""
    test_cases = [
        ("gemini/gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
        ("models/gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini/gemini-3-flash-preview", "gemini-3-flash-preview"),
    ]
    mock_client = mock.MagicMock()
    for raw_model, expected_model in test_cases:
      with self.subTest(raw_model=raw_model):
        extractor = VertexGroundingExtractor(
            client=mock_client, model_id=raw_model
        )
        self.assertEqual(extractor.model_id, expected_model)

  async def test_extract_thinking_budget_passed_in_config(self):
    """Verifies thinking_config is included when thinking_budget is positive."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
        chunks=[("Test Cafe", "places/ChIJ_CAFE", "")],
    )
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    extractor = VertexGroundingExtractor(
        client=mock_client, thinking_budget=1024
    )

    await extractor.extract("find cafe", LocalSearchExtractorSchema)
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    self.assertIsNotNone(call_kwargs["config"].thinking_config)
    self.assertEqual(
        call_kwargs["config"].thinking_config.thinking_budget, 1024
    )

  async def test_extract_zero_thinking_budget_omits_thinking_config(self):
    """Verifies thinking_config is omitted when thinking_budget is zero."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
        chunks=[("Test Cafe", "places/ChIJ_CAFE", "")],
    )
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    extractor = VertexGroundingExtractor(client=mock_client, thinking_budget=0)

    await extractor.extract("find cafe", LocalSearchExtractorSchema)
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    self.assertIsNone(call_kwargs["config"].thinking_config)

  def test_extract_attribution_sources_from_metadata(self):
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

    attribution_sources = self.extractor._extract_attribution_sources(
        mock_response
    )
    self.assertEqual(len(attribution_sources), 2)
    self.assertEqual(
        attribution_sources[0],
        AttributionSource(
            title="Sip and Co - Google Maps",
            place_id="places/ChIJK4Gklg1ZwokRmDGLQSxEaUI",
        ),
    )
    self.assertEqual(
        attribution_sources[1],
        AttributionSource(
            title="Sote Coffee Roasters",
            place_id="ChIJwR4noh5ZwokREcz36jnEQbo",
        ),
    )

  def test_extract_attribution_sources_empty_or_missing_metadata(self):
    mock_response = mock.MagicMock()
    mock_response.candidates = []
    self.assertEqual(
        self.extractor._extract_attribution_sources(mock_response), []
    )

    mock_candidate = mock.MagicMock()
    mock_candidate.grounding_metadata = None
    mock_response.candidates = [mock_candidate]
    self.assertEqual(
        self.extractor._extract_attribution_sources(mock_response), []
    )

  def test_normalize_place_ids_strips_resource_prefix_on_places(self):
    payload = _create_local_search_payload([
        _create_place_pin_dict("Sip and Co", place_id="places/ChIJ_SIP_123"),
        _create_place_pin_dict("Sote Coffee", place_id="ChIJ_SOTE_456"),
    ])

    normalized = self.extractor._normalize_place_ids(payload)
    validated = LocalSearchExtractorSchema.model_validate(normalized)

    self.assertEqual(validated.places[0].placeId, "ChIJ_SIP_123")
    self.assertEqual(validated.places[1].placeId, "ChIJ_SOTE_456")

  def test_normalize_place_ids_reaches_route_endpoints(self):
    payload = _create_directions_payload(
        origin_place_id="places/ChIJ_TIMES_SQUARE",
        destination_place_id="places/ChIJ_CENTRAL_PARK",
    )

    normalized = self.extractor._normalize_place_ids(payload)
    validated = DirectionsExtractorSchema.model_validate(normalized)

    self.assertEqual(validated.routes[0].origin.placeId, "ChIJ_TIMES_SQUARE")
    self.assertEqual(
        validated.routes[0].destination.placeId, "ChIJ_CENTRAL_PARK"
    )

  def test_normalize_place_ids_tolerates_absent_place_id(self):
    payload = _create_directions_payload()

    normalized = self.extractor._normalize_place_ids(payload)
    validated = DirectionsExtractorSchema.model_validate(normalized)

    self.assertIsNone(validated.routes[0].origin.placeId)

  def test_parse_data_block_extracts_json_between_tags(self):
    response_text = 'Some prose.\n\n<data>{"a": 1}</data>'
    self.assertEqual(
        self.extractor._parse_data_block(response_text), '{"a": 1}'
    )

  def test_parse_data_block_raises_when_block_absent(self):
    with self.assertRaises(ValueError) as ctx:
      self.extractor._parse_data_block("Prose only, no block.")
    self.assertIn("no <data> block", str(ctx.exception))

  def _mock_out_generate_content(
      self, mock_response: mock.MagicMock
  ) -> mock.AsyncMock:
    """Wires a mock response into the extractor's lazily built client."""
    mock_client = mock.MagicMock()
    mock_generate = mock.AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    self.extractor._client = mock_client
    return mock_generate

  async def test_extract_requests_free_text_not_structured_output(self):
    # Setting response_schema suppresses Maps attribution sources entirely,
    # which is the bug this design exists to work around. Guard the request
    # shape so a future refactor cannot quietly reintroduce it.
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
            chunks=[("Test Cafe - Google Maps", "places/ChIJ_CAFE", "")],
        )
    )

    await self.extractor.extract(
        "coffee shops", LocalSearchExtractorSchema, max_places=3
    )

    config = mock_generate.call_args.kwargs.get("config")
    self.assertIsNone(getattr(config, "response_schema", None))
    self.assertIsNone(getattr(config, "response_mime_type", None))

  async def test_extract_instruction_carries_schema_rules_and_guidelines(self):
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
            chunks=[("Test Cafe - Google Maps", "places/ChIJ_CAFE", "")],
        )
    )

    await self.extractor.extract(
        "coffee shops", LocalSearchExtractorSchema, max_places=3
    )

    instruction = mock_generate.call_args.kwargs["config"].system_instruction
    # The schema now travels in the prompt because the request no longer
    # carries one, so a required field name must appear verbatim.
    self.assertIn('"heading"', instruction)
    self.assertIn(place_id_resolution.PROMPT_RULES, instruction)
    self.assertIn("at most 3 places", instruction)
    self.assertIn("Do not rely on your internal knowledge.", instruction)
    self.assertIn("Conversational Text Style Guidelines", instruction)

  async def test_extract_substitutes_placeholders_with_grounded_place_ids(self):
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [
                _create_place_pin_dict(
                    "Starbucks", place_id="PLACE_ID_FOR_1_Starbucks"
                ),
                _create_place_pin_dict(
                    "Starbucks", place_id="PLACE_ID_FOR_2_Starbucks"
                ),
            ],
            summary="Two Starbucks locations.",
        ),
        chunks=[
            ("Starbucks - Google Maps", "places/ChIJ_SBUX_1", ""),
            ("Starbucks - Google Maps", "places/ChIJ_SBUX_2", ""),
        ],
    )
    self._mock_out_generate_content(mock_response)

    result = await self.extractor.extract(
        "starbucks near me", LocalSearchExtractorSchema, max_places=5
    )

    self.assertEqual(result.summary, "Two Starbucks locations.")
    self.assertEqual(
        [place.placeId for place in result.places],
        ["ChIJ_SBUX_1", "ChIJ_SBUX_2"],
    )

  async def test_extract_leaves_placeholder_when_sources_run_short(self):
    # Grounding cited one venue but the model named two. The unresolved
    # placeholder must survive to the client: it breaks the card loudly, whereas reusing a
    # nearby Place ID would render a confidently wrong store.
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload([
            _create_place_pin_dict(
                "Starbucks", place_id="PLACE_ID_FOR_1_Starbucks"
            ),
            _create_place_pin_dict(
                "Starbucks", place_id="PLACE_ID_FOR_2_Starbucks"
            ),
        ]),
        chunks=[("Starbucks - Google Maps", "places/ChIJ_SBUX_1", "")],
    )
    self._mock_out_generate_content(mock_response)

    result = await self.extractor.extract(
        "starbucks near me", LocalSearchExtractorSchema, max_places=5
    )

    self.assertEqual(result.places[0].placeId, "ChIJ_SBUX_1")
    self.assertEqual(result.places[1].placeId, "PLACE_ID_FOR_2_Starbucks")

  async def test_extract_substitutes_placeholders_on_route_endpoints(self):
    mock_response = _create_mock_response(
        json_data=_create_directions_payload(
            origin_place_id="PLACE_ID_FOR_1_Times Square",
            destination_place_id="PLACE_ID_FOR_1_Central Park",
        ),
        chunks=[
            ("Times Square - Google Maps", "places/ChIJ_TSQ", ""),
            ("Central Park - Google Maps", "places/ChIJ_CP", ""),
        ],
    )
    self._mock_out_generate_content(mock_response)

    result = await self.extractor.extract(
        "walk to central park", DirectionsExtractorSchema
    )

    self.assertEqual(result.routes[0].origin.placeId, "ChIJ_TSQ")
    self.assertEqual(result.routes[0].destination.placeId, "ChIJ_CP")

  async def test_extract_raises_when_response_has_no_data_block(self):
    self._mock_out_generate_content(
        _create_mock_response(text="I could not find anything.")
    )

    with self.assertRaises(ValueError) as ctx:
      await self.extractor.extract("coffee", LocalSearchExtractorSchema)
    self.assertIn("no <data> block", str(ctx.exception))

  async def test_extract_raises_when_data_block_is_not_json(self):
    self._mock_out_generate_content(
        _create_mock_response(text="Prose.\n\n<data>not json</data>")
    )

    with self.assertRaises(ValueError) as ctx:
      await self.extractor.extract("coffee", LocalSearchExtractorSchema)
    self.assertIn("not valid JSON", str(ctx.exception))

  async def test_extract_warns_when_grounding_returns_no_sources(self):
    self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
            chunks=[],
        )
    )

    with self.assertLogs(
        "google3.third_party.googlemaps.a2ui.agent.python_agent"
        ".vertex_grounding_extractor",
        level="WARNING",
    ) as logs:
      await self.extractor.extract("coffee", LocalSearchExtractorSchema)

    self.assertIn("no Maps attribution sources", logs.output[0])


if __name__ == "__main__":
  unittest.main()
