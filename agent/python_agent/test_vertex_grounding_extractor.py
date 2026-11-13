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

import vertex_grounding_extractor
from templates.directions.schema import DirectionsExtractorSchema
from templates.local_search.schema import LocalSearchExtractorSchema
from vertex_grounding_extractor import DUAL_GROUNDING_INSTRUCTIONS
from vertex_grounding_extractor import VertexGroundingExtractor


def _create_mock_response(
    text: str = "",
    chunks: list[tuple[str, str, str]] | None = None,
    web_chunks: list[str] | None = None,
    web_search_queries: list[str] | None = None,
    json_data: dict[str, Any] | None = None,
    prose: str = "Here is what I found nearby.",
) -> mock.MagicMock:
  """Builds a mock Vertex AI generate_content response with Maps and Search sources.

  When `json_data` is supplied the helper wraps it the way the model is now
  instructed to respond: a prose summary first, which is what the grounding
  engine attaches Maps citations to, then a delimited data block.

  Args:
      text: Raw model output, used verbatim when `json_data` is omitted.
      chunks: Optional list of (title, place_id, uri) tuples for Maps.
      web_chunks: Optional list of URI strings for Search.
      web_search_queries: Optional list of search query strings.
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
    mock_chunk.web = None
    mock_chunks.append(mock_chunk)
  for uri in web_chunks or []:
    mock_chunk = mock.MagicMock()
    mock_chunk.maps = None
    mock_chunk.web.uri = uri
    mock_chunks.append(mock_chunk)

  mock_meta = mock.MagicMock()
  mock_meta.grounding_chunks = mock_chunks
  mock_meta.web_search_queries = web_search_queries
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
    self.mock_client = mock.MagicMock()
    self.extractor = VertexGroundingExtractor(
        client=self.mock_client,
        model_id="gemini-3-flash-preview",
        shared_guidelines="Conversational Text Style Guidelines",
    )

  def test_default_shared_guidelines_empty(self):
    extractor = VertexGroundingExtractor(client=self.mock_client)
    self.assertEqual(extractor.shared_guidelines, "")

  def test_init_stores_client(self):
    mock_client = mock.MagicMock()
    extractor = VertexGroundingExtractor(client=mock_client)
    self.assertIs(extractor.client, mock_client)

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

  async def test_generate_grounded_text_success(self):
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "Here are the hours for Space Needle: 9am-10pm."
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    extractor = VertexGroundingExtractor(client=mock_client)
    result = await extractor.generate_grounded_text("Space needle hours")
    self.assertEqual(result, "Here are the hours for Space Needle: 9am-10pm.")

  async def test_generate_grounded_text_exception_returns_empty(self):
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        side_effect=RuntimeError("API failure")
    )
    extractor = VertexGroundingExtractor(client=mock_client)
    result = await extractor.generate_grounded_text("Failing query")
    self.assertEqual(result, "")

  async def test_generate_grounded_text_thinking_budget_forwarded(self):
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "Answer"
    mock_generate = mock.AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    extractor = VertexGroundingExtractor(
        client=mock_client, thinking_budget=1024
    )
    await extractor.generate_grounded_text("Query with budget")
    config = mock_generate.call_args.kwargs["config"]
    self.assertIsNotNone(config.thinking_config)
    self.assertEqual(config.thinking_config.thinking_budget, 1024)

  async def test_generate_grounded_text_appends_shared_guidelines(self):
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.text = "Answer"
    mock_generate = mock.AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    extractor = VertexGroundingExtractor(
        client=mock_client,
        shared_guidelines="Custom Shared Style Rule",
    )
    await extractor.generate_grounded_text("Query with shared guidelines")
    config = mock_generate.call_args.kwargs["config"]
    self.assertIn("Custom Shared Style Rule", config.system_instruction)

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
    """Wires a mock response into the extractor's client."""
    mock_client = mock.MagicMock()
    mock_generate = mock.AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    self.extractor.client = mock_client
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
    self.assertIn(
        "You MUST call the Google Maps tool to answer the user's location"
        " request and follow the Grounding & Tool-Calling Policy.",
        instruction,
    )
    self.assertIn('"heading"', instruction)
    self.assertNotIn("PLACE_ID_FOR_", instruction)
    self.assertIn("at most 3 places", instruction)
    self.assertIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)
    self.assertIn("Conversational Text Style Guidelines", instruction)

  async def test_extract_instruction_includes_skill_instructions(self):
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
            chunks=[("Test Cafe - Google Maps", "places/ChIJ_CAFE", "")],
        )
    )

    await self.extractor.extract(
        "coffee shops",
        LocalSearchExtractorSchema,
        max_places=3,
        skill_instructions="# Local Search Guidelines\nCustom domain rules.",
    )

    instruction = mock_generate.call_args.kwargs["config"].system_instruction
    self.assertIn(
        "# Local Search Guidelines\nCustom domain rules.", instruction
    )
    self.assertIn("Conversational Text Style Guidelines", instruction)
    self.assertLess(
        instruction.index("Conversational Text Style Guidelines"),
        instruction.index("# Local Search Guidelines"),
    )

  async def test_extract_direct_place_ids_local_search(self):
    """Verifies that direct Place IDs are parsed without placeholder replacement."""
    test_cases = [
        ("places/ChIJ_TEST_1", "ChIJ_TEST_2"),
        ("ChIJ_TEST_3", "places/ChIJ_TEST_4"),
    ]
    for pid1, pid2 in test_cases:
      with self.subTest(pid1=pid1, pid2=pid2):
        mock_response = _create_mock_response(
            json_data=_create_local_search_payload([
                _create_place_pin_dict("Cafe Alpha", place_id=pid1),
                _create_place_pin_dict("Cafe Beta", place_id=pid2),
            ]),
        )
        self._mock_out_generate_content(mock_response)

        result = await self.extractor.extract(
            "coffee shops", LocalSearchExtractorSchema, max_places=5
        )
        self.assertEqual(len(result.places), 2)
        self.assertEqual(result.places[0].placeId, pid1)
        self.assertEqual(result.places[1].placeId, pid2)

  async def test_extract_direct_place_ids_directions(self):
    """Verifies that route endpoint Place IDs are parsed directly from model output."""
    mock_response = _create_mock_response(
        json_data=_create_directions_payload(
            origin_place_id="places/ChIJ_ORIGIN",
            destination_place_id="ChIJ_DEST",
        )
    )
    self._mock_out_generate_content(mock_response)

    result = await self.extractor.extract(
        "directions to park", DirectionsExtractorSchema
    )
    self.assertEqual(len(result.routes), 1)
    self.assertEqual(result.routes[0].origin.placeId, "places/ChIJ_ORIGIN")
    self.assertEqual(result.routes[0].destination.placeId, "ChIJ_DEST")

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

  def test_enable_search_grounding_default_true(self):
    """Verifies enable_search_grounding defaults to True."""
    extractor = VertexGroundingExtractor(client=self.mock_client)
    self.assertTrue(extractor.enable_search_grounding)
    tools = extractor._build_tools()  # pylint: disable=protected-access
    self.assertEqual(len(tools), 2)
    has_maps = any(t.google_maps is not None for t in tools)
    has_search = any(t.google_search is not None for t in tools)
    self.assertTrue(has_maps)
    self.assertTrue(has_search)

  def test_enable_search_grounding_explicit_false(self):
    """Verifies enable_search_grounding can be explicitly disabled (opt-out)."""
    extractor = VertexGroundingExtractor(
        client=self.mock_client,
        enable_search_grounding=False,
    )
    self.assertFalse(extractor.enable_search_grounding)
    tools = extractor._build_tools()  # pylint: disable=protected-access
    self.assertEqual(len(tools), 1)
    self.assertIsNotNone(tools[0].google_maps)
    self.assertIsNone(tools[0].google_search)

  def test_enable_search_grounding_true_builds_dual_tools(self):
    """Verifies enable_search_grounding=True builds both GoogleMaps and GoogleSearch tools."""
    extractor = VertexGroundingExtractor(
        client=self.mock_client,
        enable_search_grounding=True,
    )
    self.assertTrue(extractor.enable_search_grounding)
    tools = extractor._build_tools()  # pylint: disable=protected-access
    self.assertEqual(len(tools), 2)
    has_maps = any(t.google_maps is not None for t in tools)
    has_search = any(t.google_search is not None for t in tools)
    self.assertTrue(has_maps)
    self.assertTrue(has_search)

  async def test_extract_forwards_dual_tools_when_search_grounding_enabled(
      self,
  ):
    """Verifies extract() attaches both tools when enable_search_grounding=True."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
        )
    )
    self.extractor.enable_search_grounding = True
    await self.extractor.extract("coffee shops", LocalSearchExtractorSchema)
    call_kwargs = mock_generate.call_args.kwargs
    tools = call_kwargs["config"].tools
    self.assertEqual(len(tools), 2)
    has_maps = any(t.google_maps is not None for t in tools)
    has_search = any(t.google_search is not None for t in tools)
    self.assertTrue(has_maps)
    self.assertTrue(has_search)

  async def test_extract_attaches_maps_only_when_search_grounding_disabled(
      self,
  ):
    """Verifies extract() attaches only Google Maps tool when search grounding is disabled."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(
            json_data=_create_local_search_payload(
                [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
            ),
        )
    )
    self.extractor.enable_search_grounding = False
    await self.extractor.extract("coffee shops", LocalSearchExtractorSchema)
    call_kwargs = mock_generate.call_args.kwargs
    tools = call_kwargs["config"].tools
    self.assertEqual(len(tools), 1)
    self.assertIsNotNone(tools[0].google_maps)
    self.assertIsNone(tools[0].google_search)

  async def test_generate_grounded_text_forwards_dual_tools_when_search_grounding_enabled(
      self,
  ):
    """Verifies generate_grounded_text() attaches both tools when enabled."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(text="Grounded text answer.")
    )
    self.extractor.enable_search_grounding = True
    await self.extractor.generate_grounded_text("Where is the nearest cafe?")
    call_kwargs = mock_generate.call_args.kwargs
    tools = call_kwargs["config"].tools
    self.assertEqual(len(tools), 2)
    has_maps = any(t.google_maps is not None for t in tools)
    has_search = any(t.google_search is not None for t in tools)
    self.assertTrue(has_maps)
    self.assertTrue(has_search)

  async def test_generate_grounded_text_updates_system_instruction_when_search_grounding_enabled(
      self,
  ):
    """Verifies generate_grounded_text updates system_instruction with dual-tool rules when enabled."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(text="Grounded text answer.")
    )
    self.extractor.enable_search_grounding = True
    await self.extractor.generate_grounded_text("Where is the nearest cafe?")
    call_kwargs = mock_generate.call_args.kwargs
    system_instruction = call_kwargs["config"].system_instruction
    self.assertIn(DUAL_GROUNDING_INSTRUCTIONS, system_instruction)

  async def test_generate_grounded_text_excludes_dual_tool_rules_when_search_disabled(
      self,
  ):
    """Verifies generate_grounded_text excludes dual-tool rules when search is disabled."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(text="Grounded text answer.")
    )
    self.extractor.enable_search_grounding = False
    await self.extractor.generate_grounded_text("Where is the nearest cafe?")
    call_kwargs = mock_generate.call_args.kwargs
    system_instruction = call_kwargs["config"].system_instruction
    self.assertNotIn(DUAL_GROUNDING_INSTRUCTIONS, system_instruction)
    self.assertNotIn("Google Search", system_instruction)

  async def test_generate_grounded_text_preserves_custom_instruction(
      self,
  ):
    """Verifies generate_grounded_text honors custom system_instruction override."""
    mock_generate = self._mock_out_generate_content(
        _create_mock_response(text="Custom answer.")
    )
    self.extractor.enable_search_grounding = True
    await self.extractor.generate_grounded_text(
        "Where is the nearest cafe?", system_instruction="Custom Instruction"
    )
    call_kwargs = mock_generate.call_args.kwargs
    self.assertEqual(
        call_kwargs["config"].system_instruction, "Custom Instruction"
    )

  def test_build_instruction_excludes_dual_tool_contract_when_search_disabled(
      self,
  ):
    """Verifies _build_instruction excludes dual-tool contract when search grounding is disabled."""
    extractor = VertexGroundingExtractor(
        client=self.mock_client,
        model_id="gemini-3-flash-preview",
        enable_search_grounding=False,
    )
    instruction = extractor._build_instruction(  # pylint: disable=protected-access
        LocalSearchExtractorSchema, max_places=5
    )
    self.assertNotIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)
    self.assertNotIn("Google Search", instruction)

  def test_build_instruction_includes_dual_tool_contract_by_default(
      self,
  ):
    """Verifies _build_instruction includes dual-tool contract by default."""
    extractor = VertexGroundingExtractor(
        client=self.mock_client,
        model_id="gemini-3-flash-preview",
    )
    instruction = extractor._build_instruction(  # pylint: disable=protected-access
        LocalSearchExtractorSchema, max_places=5
    )
    self.assertIn("Google Search", instruction)
    self.assertIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)

  def test_build_instruction_includes_dual_tool_contract_when_search_enabled(
      self,
  ):
    """Verifies _build_instruction includes dual-tool contract when search grounding is enabled."""
    extractor = VertexGroundingExtractor(
        client=self.mock_client,
        model_id="gemini-3-flash-preview",
        enable_search_grounding=True,
    )
    instruction = extractor._build_instruction(  # pylint: disable=protected-access
        LocalSearchExtractorSchema, max_places=5
    )
    self.assertIn("Google Search", instruction)
    self.assertIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)
    self.assertLess(
        instruction.index(DUAL_GROUNDING_INSTRUCTIONS),
        instruction.index("Respond with a machine-readable block"),
    )
    self.assertLess(
        instruction.index(DUAL_GROUNDING_INSTRUCTIONS),
        instruction.index("CRITICAL RULES:"),
    )

  async def test_extract_logs_grounding_metadata_with_search_and_chunks(self):
    """Verifies extract() logs Search queries and chunk counts at INFO level."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
        chunks=[("Test Cafe - Google Maps", "places/ChIJ_CAFE", "")],
        web_chunks=["https://example.com/cafe"],
        web_search_queries=["test cafe menu prices", "test cafe hours"],
    )
    self._mock_out_generate_content(mock_response)

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="INFO",
    ) as log_ctx:
      await self.extractor.extract("coffee shops", LocalSearchExtractorSchema)

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("enable_search_grounding=True", log_output)
    self.assertIn(
        "web_search_queries=['test cafe menu prices', 'test cafe hours']",
        log_output,
    )
    self.assertIn("maps_chunks=1", log_output)
    self.assertIn("web_chunks=1", log_output)

  async def test_extract_logs_grounding_metadata_with_empty_metadata(self):
    """Verifies extract() logs safely when grounding metadata is absent or empty."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
    )
    mock_response.candidates = []
    self._mock_out_generate_content(mock_response)

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="INFO",
    ) as log_ctx:
      await self.extractor.extract("coffee shops", LocalSearchExtractorSchema)

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("web_search_queries=[]", log_output)
    self.assertIn("maps_chunks=0", log_output)
    self.assertIn("web_chunks=0", log_output)

  async def test_generate_grounded_text_logs_grounding_metadata_with_search_and_chunks(
      self,
  ):
    """Verifies generate_grounded_text() logs Search queries and chunk counts."""
    mock_response = _create_mock_response(
        text="Cafe opens at 8am.",
        chunks=[("Test Cafe - Google Maps", "places/ChIJ_CAFE", "")],
        web_chunks=["https://example.com/cafe"],
        web_search_queries=["test cafe hours"],
    )
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    self.extractor.client = mock_client

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="INFO",
    ) as log_ctx:
      await self.extractor.generate_grounded_text("Cafe hours")

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("enable_search_grounding=True", log_output)
    self.assertIn("web_search_queries=['test cafe hours']", log_output)
    self.assertIn("maps_chunks=1", log_output)
    self.assertIn("web_chunks=1", log_output)

  async def test_generate_grounded_text_logs_grounding_metadata_with_empty_metadata(
      self,
  ):
    """Verifies generate_grounded_text() logs safely when candidate is None."""
    mock_response = mock.MagicMock()
    mock_response.text = "Answer without metadata."
    mock_response.candidates = None
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    self.extractor.client = mock_client

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="INFO",
    ) as log_ctx:
      await self.extractor.generate_grounded_text("General question")

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("web_search_queries=[]", log_output)
    self.assertIn("maps_chunks=0", log_output)
    self.assertIn("web_chunks=0", log_output)

  async def test_extract_logs_grounding_metadata_with_opt_out(self):
    """Verifies extract() logs enable_search_grounding=False when disabled."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
    )
    self._mock_out_generate_content(mock_response)
    self.extractor.enable_search_grounding = False

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="INFO",
    ) as log_ctx:
      await self.extractor.extract("coffee shops", LocalSearchExtractorSchema)

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("enable_search_grounding=False", log_output)

  async def test_extract_defensive_against_candidate_property_exception(self):
    """Verifies extract() succeeds even if candidate introspection raises an unexpected exception."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        ),
    )
    type(mock_response).candidates = mock.PropertyMock(
        side_effect=RuntimeError("Corrupt candidate property")
    )
    self._mock_out_generate_content(mock_response)

    with self.assertLogs(
        "vertex_grounding_extractor",
        level="DEBUG",
    ) as log_ctx:
      result = await self.extractor.extract(
          "coffee shops", LocalSearchExtractorSchema
      )

    self.assertIsNotNone(result)
    self.assertEqual(result.places[0].name, "Test Cafe")
    self.assertTrue(
        any(
            "Failed to log grounding metadata: Corrupt candidate property" in r
            for r in log_ctx.output
        )
    )

  def test_log_grounding_metadata_catches_and_debug_logs_exception(self):
    """Verifies module-level log_grounding_metadata catches unexpected errors and logs at DEBUG."""
    bad_response = mock.MagicMock()
    type(bad_response).candidates = mock.PropertyMock(
        side_effect=TypeError("Unexpected mock error")
    )
    with self.assertLogs(
        "vertex_grounding_extractor",
        level="DEBUG",
    ) as log_ctx:
      vertex_grounding_extractor.log_grounding_metadata(
          bad_response, enable_search_grounding=True
      )
    self.assertTrue(
        any(
            "Failed to log grounding metadata: Unexpected mock error" in r
            for r in log_ctx.output
        )
    )

  def test_build_retrieval_tool_config_with_valid_coordinates(self):
    tool_config = vertex_grounding_extractor.build_retrieval_tool_config(
        "coffee near me (my location: 37.7749, -122.4194)"
    )
    self.assertIsNotNone(tool_config)
    retrieval_config = getattr(tool_config, "retrieval_config", None)
    self.assertIsNotNone(retrieval_config)
    lat_lng = getattr(retrieval_config, "lat_lng", None)
    self.assertIsNotNone(lat_lng)
    self.assertAlmostEqual(lat_lng.latitude, 37.7749, places=4)
    self.assertAlmostEqual(lat_lng.longitude, -122.4194, places=4)

  def test_build_retrieval_tool_config_without_coordinates(self):
    self.assertIsNone(
        vertex_grounding_extractor.build_retrieval_tool_config(
            "coffee in Seattle"
        )
    )

  async def test_extract_passes_tool_config_when_coordinates_present(self):
    """Verifies extract attaches tool_config when coordinates are present."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        )
    )
    mock_generate = self._mock_out_generate_content(mock_response)

    query = "coffee near me (my location: 37.7749, -122.4194)"
    result = await self.extractor.extract(query, LocalSearchExtractorSchema)
    self.assertIsNotNone(result)

    call_kwargs = mock_generate.call_args.kwargs
    config = call_kwargs["config"]
    self.assertIsNotNone(config.tool_config)
    retrieval_config = config.tool_config.retrieval_config
    self.assertIsNotNone(retrieval_config)
    self.assertAlmostEqual(retrieval_config.lat_lng.latitude, 37.7749, places=4)
    self.assertAlmostEqual(
        retrieval_config.lat_lng.longitude, -122.4194, places=4
    )

  async def test_extract_omits_tool_config_when_coordinates_absent(self):
    """Verifies extract omits tool_config when coordinates are absent."""
    mock_response = _create_mock_response(
        json_data=_create_local_search_payload(
            [_create_place_pin_dict("Test Cafe", place_id="ChIJ_CAFE")]
        )
    )
    mock_generate = self._mock_out_generate_content(mock_response)

    result = await self.extractor.extract(
        "coffee in Seattle", LocalSearchExtractorSchema
    )
    self.assertIsNotNone(result)

    call_kwargs = mock_generate.call_args.kwargs
    config = call_kwargs["config"]
    self.assertIsNone(config.tool_config)

  async def test_generate_grounded_text_passes_tool_config_when_coordinates_present(
      self,
  ):
    """Verifies generate_grounded_text attaches tool_config when coordinates are present."""
    mock_response = mock.MagicMock()
    mock_response.text = "Here are coffee shops near your location."
    mock_candidate = mock.MagicMock()
    mock_candidate.grounding_metadata = None
    mock_response.candidates = [mock_candidate]
    mock_generate = self._mock_out_generate_content(mock_response)

    query = "coffee near me (my location: 37.7749, -122.4194)"
    text = await self.extractor.generate_grounded_text(query)
    self.assertIn("Here are coffee shops", text)

    call_kwargs = mock_generate.call_args.kwargs
    config = call_kwargs["config"]
    self.assertIsNotNone(config.tool_config)
    retrieval_config = config.tool_config.retrieval_config
    self.assertIsNotNone(retrieval_config)
    self.assertAlmostEqual(retrieval_config.lat_lng.latitude, 37.7749, places=4)
    self.assertAlmostEqual(
        retrieval_config.lat_lng.longitude, -122.4194, places=4
    )

  async def test_generate_grounded_text_omits_tool_config_when_coordinates_absent(
      self,
  ):
    """Verifies generate_grounded_text omits tool_config when coordinates are absent."""
    mock_response = mock.MagicMock()
    mock_response.text = "Here are coffee shops in Seattle."
    mock_candidate = mock.MagicMock()
    mock_candidate.grounding_metadata = None
    mock_response.candidates = [mock_candidate]
    mock_generate = self._mock_out_generate_content(mock_response)

    text = await self.extractor.generate_grounded_text("coffee in Seattle")
    self.assertIn("Here are coffee shops in Seattle.", text)

    call_kwargs = mock_generate.call_args.kwargs
    config = call_kwargs["config"]
    self.assertIsNone(config.tool_config)


if __name__ == "__main__":
  unittest.main()
