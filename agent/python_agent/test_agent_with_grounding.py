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

"""Unit tests for MAUIAgentWithGrounding template routing and execution."""

import os
import unittest
from unittest import mock

from a2a.types import DataPart
from google import genai

from a2ui.a2a.parts import create_a2ui_part
import agent_config
import agent_with_grounding
from agent import VERSION_0_9
from router import VertexIntentClassifier
from template_registry import INTENT_OTHER_SPATIAL, INTENT_TEXT_ONLY
from templates.common import Pin
from templates.directions.schema import DirectionsExtractorSchema, RouteSegment
from templates.local_search.schema import LocalSearchExtractorSchema, PlacePin
from vertex_grounding_extractor import DUAL_GROUNDING_INSTRUCTIONS

AgentConfig = agent_config.AgentConfig
FallbackMode = agent_config.FallbackMode
INTENT_LOCAL_SEARCH = "LOCAL_SEARCH"
INTENT_DIRECTIONS = "DIRECTIONS"
MAUIAgentWithGrounding = agent_with_grounding.MAUIAgentWithGrounding


def _mock_classifier(intent: str) -> mock.MagicMock:
  """Creates a mock VertexIntentClassifier returning intent."""
  classifier = mock.MagicMock(spec=VertexIntentClassifier)
  classifier.classify = mock.AsyncMock(return_value=intent)
  return classifier


class MAUIAgentWithGroundingTest(unittest.IsolatedAsyncioTestCase):
  """Unit tests for MAUIAgentWithGrounding."""

  def setUp(self):
    super().setUp()
    self.base_url = "http://localhost:10002"

  def test_init_without_template_config(self):
    agent = MAUIAgentWithGrounding(base_url=self.base_url)
    self.assertIsNone(agent.template_config)

  def test_init_with_template_config(self):
    cfg = AgentConfig(
        router_model="gemini/gemini-3.5-flash-lite",
        template_model="gemini/gemini-3.5-flash-lite",
    )
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=cfg,
    )
    self.assertIsNotNone(agent.template_config)
    self.assertEqual(
        agent.template_config.router_model, "gemini/gemini-3.5-flash-lite"
    )
    self.assertEqual(
        agent.template_config.template_model, "gemini/gemini-3.5-flash-lite"
    )

  def test_get_genai_client_missing_project_id_raises_value_error(self):
    """Verifies ValueError when GOOGLE_CLOUD_PROJECT is unset."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(),
    )
    with mock.patch.dict(os.environ, {}, clear=True):
      with self.assertRaises(ValueError) as ctx:
        agent._get_genai_client()
      self.assertIn("GOOGLE_CLOUD_PROJECT", str(ctx.exception))

  def test_get_genai_client_cached_singleton(self):
    """Verifies _get_genai_client caches and returns a singleton instance."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(),
    )
    with mock.patch.dict(
        os.environ,
        {
            "GOOGLE_CLOUD_PROJECT": "test-p1",
            "GOOGLE_CLOUD_LOCATION": "us-west1",
        },
        clear=True,
    ):
      with mock.patch("google.genai.Client") as mock_genai_cls:
        client1 = agent._get_genai_client()
        client2 = agent._get_genai_client()
        self.assertIs(client1, client2)
        mock_genai_cls.assert_called_once_with(
            vertexai=True, project="test-p1", location="us-west1"
        )

  def test_shared_client_injected_into_router_and_extractor(self):
    """Verifies router and extractor share the single genai client."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(),
    )
    mock_client = mock.MagicMock(spec=genai.Client)
    agent._genai_client = mock_client

    router = agent._get_router_classifier()
    extractor = agent._get_vertex_extractor()

    self.assertIs(router.client, mock_client)
    self.assertIs(extractor.client, mock_client)

  def test_get_vertex_extractor_missing_project_id_raises_value_error(self):
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(),
    )
    with mock.patch.dict(os.environ, {}, clear=True):
      with self.assertRaises(ValueError) as ctx:
        agent._get_vertex_extractor()
      self.assertIn("GOOGLE_CLOUD_PROJECT", str(ctx.exception))

  def test_get_vertex_extractor_with_project_id_succeeds(self):
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(
            extractor_thinking_budget=2048,
        ),
    )
    with mock.patch.dict(
        os.environ, {"GOOGLE_CLOUD_PROJECT": "explicit-project"}
    ):
      extractor_instance = agent._get_vertex_extractor()
      self.assertEqual(extractor_instance.thinking_budget, 2048)

  async def test_stream_without_template_config_delegates_to_super(self):
    agent = MAUIAgentWithGrounding(base_url=self.base_url)
    with mock.patch.object(
        agent_with_grounding.MAUIAgent,
        "stream",
    ) as mock_super_stream:

      async def fake_stream(*args, **kwargs):
        yield {"part": "legacy_stream"}

      mock_super_stream.side_effect = fake_stream
      parts = []
      async for chunk in agent.stream("coffee", "s1", VERSION_0_9):
        parts.append(chunk)

      mock_super_stream.assert_called_once_with("coffee", "s1", VERSION_0_9)
      self.assertEqual(parts, [{"part": "legacy_stream"}])

  async def test_stream_without_ui_version_delegates_to_super(self):
    cfg = AgentConfig()
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
    with mock.patch.object(
        agent_with_grounding.MAUIAgent,
        "stream",
    ) as mock_super_stream:

      async def fake_stream(*args, **kwargs):
        yield {"part": "text_stream"}

      mock_super_stream.side_effect = fake_stream
      parts = []
      async for chunk in agent.stream("coffee", "s1", ui_version=None):
        parts.append(chunk)

      mock_super_stream.assert_called_once_with("coffee", "s1", None)
      self.assertEqual(parts, [{"part": "text_stream"}])

  async def test_stream_local_search_intent_emits_template_parts(self):
    cfg = AgentConfig(max_list_size=3)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_LOCAL_SEARCH)
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        return_value=LocalSearchExtractorSchema(
            heading="Coffee Shops in Seattle",
            summary="Found coffee shops.",
            places=[
                PlacePin(
                    name="Coffee Shop A",
                    lat=47.6,
                    lng=-122.3,
                    placeId="places/ChIJ111111",
                )
            ],
        )
    )
    agent._vertex_extractor = mock_extractor

    chunks = []
    async for chunk in agent.stream("coffee in seattle", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    parts = chunks[0]["parts"]
    self.assertGreater(len(parts), 0)
    # Check that at least one part is an A2UI DataPart
    self.assertTrue(any(isinstance(part.root, DataPart) for part in parts))
    bundle = agent._get_template_registry().get_bundle_by_intent(
        INTENT_LOCAL_SEARCH
    )
    mock_extractor.extract.assert_called_once_with(
        "coffee in seattle",
        LocalSearchExtractorSchema,
        max_places=3,
        skill_instructions=bundle.skill_instructions,
    )
    self.assertIn("# Local Search Guidelines", bundle.skill_instructions)
    self.assertNotIn("search_places", bundle.skill_instructions)

  async def test_stream_directions_intent_emits_template_parts(self):
    cfg = AgentConfig()
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_DIRECTIONS)
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        return_value=DirectionsExtractorSchema(
            summary="Directions from Times Sq to Central Park.",
            travel_mode="walking",
            heading="Walking Directions",
            routes=[
                RouteSegment(
                    origin=Pin(
                        lat=40.758,
                        lng=-73.985,
                        label="Times Square",
                        placeId="places/ChIJTimesSq",
                    ),
                    destination=Pin(
                        lat=40.782,
                        lng=-73.965,
                        label="Central Park",
                        placeId="places/ChIJCentralPark",
                    ),
                )
            ],
        )
    )
    agent._vertex_extractor = mock_extractor

    chunks = []
    async for chunk in agent.stream(
        "directions from Times Sq to Central Park", "s1", VERSION_0_9
    ):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    parts = chunks[0]["parts"]
    self.assertGreater(len(parts), 0)
    self.assertTrue(any(isinstance(part.root, DataPart) for part in parts))

  async def test_stream_text_only_intent(self):
    cfg = AgentConfig()
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_TEXT_ONLY)
    fake_part = create_a2ui_part({"text": "Hello there!"})
    agent._handle_grounded_text = mock.AsyncMock(return_value=[fake_part])

    chunks = []
    async for chunk in agent.stream("hello", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    agent._handle_grounded_text.assert_called_once_with("hello", "s1")

  async def test_stream_other_spatial_fallback_text(self):
    cfg = AgentConfig(fallback_mode=FallbackMode.TEXT)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_OTHER_SPATIAL)
    fake_part = create_a2ui_part({"text": "Fallback text response"})
    agent._handle_grounded_text = mock.AsyncMock(return_value=[fake_part])

    chunks = []
    async for chunk in agent.stream("complex query", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    agent._handle_grounded_text.assert_called_once_with("complex query", "s1")

  async def test_stream_other_spatial_fallback_dynamic(self):
    cfg = AgentConfig(fallback_mode=FallbackMode.DYNAMIC)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_OTHER_SPATIAL)

    with mock.patch.object(
        agent_with_grounding.MAUIAgent,
        "stream",
    ) as mock_super_stream:

      async def fake_stream(*args, **kwargs):
        yield {"part": "dynamic_fallback"}

      mock_super_stream.side_effect = fake_stream
      chunks = []
      async for chunk in agent.stream("complex query", "s1", VERSION_0_9):
        chunks.append(chunk)

      mock_super_stream.assert_called_once_with(
          "complex query", "s1", VERSION_0_9
      )
      self.assertEqual(chunks, [{"part": "dynamic_fallback"}])

  async def test_stream_template_error_fallback_dynamic(self):
    cfg = AgentConfig(fallback_mode=FallbackMode.DYNAMIC)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_LOCAL_SEARCH)
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        side_effect=RuntimeError("Extraction failed")
    )
    agent._vertex_extractor = mock_extractor

    with mock.patch.object(
        agent_with_grounding.MAUIAgent,
        "stream",
    ) as mock_super_stream:

      async def fake_stream(*args, **kwargs):
        yield {"part": "dynamic_after_error"}

      mock_super_stream.side_effect = fake_stream
      chunks = []
      async for chunk in agent.stream("failing query", "s1", VERSION_0_9):
        chunks.append(chunk)

      mock_super_stream.assert_called_once_with(
          "failing query", "s1", VERSION_0_9
      )
      self.assertEqual(chunks, [{"part": "dynamic_after_error"}])

  async def test_stream_template_error_fallback_text(self):
    cfg = AgentConfig(fallback_mode=FallbackMode.TEXT)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._router_classifier = _mock_classifier(INTENT_LOCAL_SEARCH)
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        side_effect=RuntimeError("Extraction failed")
    )

    agent._vertex_extractor = mock_extractor

    fake_part = create_a2ui_part({"text": "Error fallback text"})
    agent._handle_grounded_text = mock.AsyncMock(return_value=[fake_part])

    chunks = []
    async for chunk in agent.stream("failing query", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    agent._handle_grounded_text.assert_called_once_with("failing query", "s1")

  async def test_handle_grounded_text_exception_fallback(self):
    """Verifies fallback text_only part when text generation is empty."""
    cfg = AgentConfig()
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
    mock_extractor = mock.MagicMock()
    mock_extractor.generate_grounded_text = mock.AsyncMock(return_value="")
    agent._vertex_extractor = mock_extractor

    parts = await agent._handle_grounded_text("test query", "s1")
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        any(
            "I'm sorry, I encountered an issue retrieving location details"
            in str(part.root.data)
            for part in parts
        )
    )

  async def test_handle_grounded_text_success(self):
    """Verifies _handle_grounded_text formats generated text into text_only."""
    cfg = AgentConfig()
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
    mock_extractor = mock.MagicMock()
    mock_extractor.generate_grounded_text = mock.AsyncMock(
        return_value="Grounded answer text"
    )
    agent._vertex_extractor = mock_extractor

    parts = await agent._handle_grounded_text("test query", "s1")
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        any("Grounded answer text" in str(part.root.data) for part in parts)
    )

  def test_agent_config_invalid_fallback_mode_raises(self):
    """Verifies AgentConfig raises ValueError on invalid mode."""
    with self.assertRaises(ValueError) as ctx:
      AgentConfig(fallback_mode="INVALID")
    self.assertIn("Invalid fallback_mode", str(ctx.exception))

  def test_load_shared_guidelines_returns_string(self):
    """Verifies _load_shared_guidelines loads package guideline text."""
    agent = MAUIAgentWithGrounding(base_url=self.base_url)
    guidelines = agent._load_shared_guidelines()
    self.assertIsInstance(guidelines, str)
    self.assertGreater(len(guidelines), 0)

  def test_agent_config_enable_search_grounding_default_true(self):
    """Verifies AgentConfig.enable_search_grounding defaults to True."""
    cfg = AgentConfig()
    self.assertTrue(cfg.enable_search_grounding)

  def test_agent_config_enable_search_grounding_opt_out(self):
    """Verifies AgentConfig.enable_search_grounding can be explicitly disabled."""
    cfg = AgentConfig(enable_search_grounding=False)
    self.assertFalse(cfg.enable_search_grounding)

  def test_maui_agent_with_grounding_enable_search_grounding_precedence(self):
    """Verifies constructor parameter and template_config precedence for enable_search_grounding."""
    # 1. Default without config -> True
    agent1 = MAUIAgentWithGrounding(base_url=self.base_url)
    self.assertTrue(agent1.enable_search_grounding)

    # 2. Config with False -> False (opt-out preserved)
    agent2 = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(enable_search_grounding=False),
    )
    self.assertFalse(agent2.enable_search_grounding)

    # 3. Config with True -> True
    agent3 = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(enable_search_grounding=True),
    )
    self.assertTrue(agent3.enable_search_grounding)

    # 4. Explicit constructor flag True overrides config False
    agent4 = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(enable_search_grounding=False),
        enable_search_grounding=True,
    )
    self.assertTrue(agent4.enable_search_grounding)

    # 5. Explicit constructor flag False overrides config True (kills
    # truthiness mutants and preserves opt-out).
    agent5 = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(enable_search_grounding=True),
        enable_search_grounding=False,
    )
    self.assertFalse(agent5.enable_search_grounding)

    # 6. Explicit constructor flag False without config -> False
    agent6 = MAUIAgentWithGrounding(
        base_url=self.base_url,
        enable_search_grounding=False,
    )
    self.assertFalse(agent6.enable_search_grounding)

  def test_vertex_extractor_lazily_created_with_search_grounding(self):
    """Verifies _get_vertex_extractor forwards enable_search_grounding to extractor."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=AgentConfig(enable_search_grounding=True),
    )
    with mock.patch.dict(
        os.environ,
        {"GOOGLE_CLOUD_PROJECT": "test-p1", "GOOGLE_CLOUD_LOCATION": "global"},
        clear=True,
    ):
      extractor = agent._get_vertex_extractor()  # pylint: disable=protected-access
      self.assertTrue(extractor.enable_search_grounding)

  @mock.patch("google.genai.Client")
  async def test_query_vertex_map_attaches_dual_tools_by_default(
      self, mock_client_cls
  ):
    """Verifies query_vertex_map defaults to dual tools (GoogleMaps + GoogleSearch)."""
    from agent_with_grounding import query_vertex_map  # pylint: disable=g-import-not-at-top

    mock_client = mock.MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = mock.MagicMock(
        text="<a2ui-json>{}</a2ui-json>"
    )

    with mock.patch.dict(
        os.environ,
        {"GOOGLE_CLOUD_PROJECT": "test-p1", "GOOGLE_CLOUD_LOCATION": "global"},
        clear=True,
    ):
      await query_vertex_map("coffee in Seattle")

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    tools = call_kwargs["config"].tools
    self.assertEqual(len(tools), 2)
    has_maps = any(t.google_maps is not None for t in tools)
    has_search = any(t.google_search is not None for t in tools)
    self.assertTrue(has_maps)
    self.assertTrue(has_search)
    instruction = call_kwargs["config"].system_instruction
    self.assertIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)

  @mock.patch("google.genai.Client")
  async def test_query_vertex_map_attaches_maps_only_when_search_disabled(
      self, mock_client_cls
  ):
    """Verifies query_vertex_map attaches only GoogleMaps tool when search is disabled."""
    from agent_with_grounding import query_vertex_map  # pylint: disable=g-import-not-at-top

    mock_client = mock.MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = mock.MagicMock(
        text="<a2ui-json>{}</a2ui-json>"
    )

    with mock.patch.dict(
        os.environ,
        {"GOOGLE_CLOUD_PROJECT": "test-p1", "GOOGLE_CLOUD_LOCATION": "global"},
        clear=True,
    ):
      await query_vertex_map("coffee in Seattle", enable_search_grounding=False)

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    tools = call_kwargs["config"].tools
    self.assertEqual(len(tools), 1)
    self.assertIsNotNone(tools[0].google_maps)
    self.assertIsNone(tools[0].google_search)
    instruction = call_kwargs["config"].system_instruction
    self.assertNotIn(DUAL_GROUNDING_INSTRUCTIONS, instruction)
    self.assertNotIn("Google Search", instruction)

  @mock.patch("google.genai.Client")
  async def test_query_vertex_map_logs_grounding_metadata(
      self, mock_client_cls
  ):
    """Verifies query_vertex_map logs grounding metadata at INFO level."""
    from agent_with_grounding import query_vertex_map  # pylint: disable=g-import-not-at-top

    mock_client = mock.MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = mock.MagicMock()
    mock_response.text = "<a2ui-json>{}</a2ui-json>"
    mock_meta = mock.MagicMock()
    mock_meta.web_search_queries = ["coffee near me"]
    mock_meta.grounding_chunks = []
    mock_candidate = mock.MagicMock()
    mock_candidate.grounding_metadata = mock_meta
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    with mock.patch.dict(
        os.environ,
        {"GOOGLE_CLOUD_PROJECT": "test-p1", "GOOGLE_CLOUD_LOCATION": "global"},
        clear=True,
    ):
      with self.assertLogs(
          "vertex_grounding_extractor",
          level="INFO",
      ) as log_ctx:
        await query_vertex_map(
            "coffee in Seattle", enable_search_grounding=True
        )

    log_output = "\n".join(log_ctx.output)
    self.assertIn("Vertex Grounding:", log_output)
    self.assertIn("enable_search_grounding=True", log_output)
    self.assertIn("web_search_queries=['coffee near me']", log_output)


if __name__ == "__main__":
  unittest.main()
