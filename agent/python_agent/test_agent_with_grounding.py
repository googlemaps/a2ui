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
from a2ui.schema.constants import VERSION_0_9
import agent_config
import agent_with_grounding
from router import VertexIntentClassifier
from template_registry import INTENT_OTHER_SPATIAL, INTENT_TEXT_ONLY
from templates.common import Pin
from templates.directions.schema import DirectionsExtractorSchema, RouteSegment
from templates.local_search.schema import LocalSearchExtractorSchema, PlacePin

FallbackMode = agent_config.FallbackMode
GroundingTemplateConfig = agent_config.GroundingTemplateConfig
INTENT_LOCAL_SEARCH = "LOCAL_SEARCH"
INTENT_DIRECTIONS = "DIRECTIONS"
MAUIAgentWithGrounding = agent_with_grounding.MAUIAgentWithGrounding


class MAUIAgentWithGroundingTest(unittest.IsolatedAsyncioTestCase):
  """Unit tests for MAUIAgentWithGrounding."""

  def setUp(self):
    super().setUp()
    self.base_url = "http://localhost:10002"

  def test_init_without_template_config(self):
    agent = MAUIAgentWithGrounding(base_url=self.base_url)
    self.assertIsNone(agent.template_config)

  def test_init_with_template_config(self):
    cfg = GroundingTemplateConfig(
        enabled=True,
        router_model="gemini-3.1-flash-lite",
        extractor_model="gemini-3.5-flash-lite",
    )
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=cfg,
    )
    self.assertIsNotNone(agent.template_config)
    self.assertTrue(agent.template_config.enabled)
    self.assertEqual(
        agent.template_config.router_model, "gemini-3.1-flash-lite"
    )
    self.assertEqual(
        agent.template_config.extractor_model, "gemini-3.5-flash-lite"
    )

  def test_get_genai_client_missing_project_id_raises_value_error(self):
    """Verifies ValueError when project_id is missing and GOOGLE_CLOUD_PROJECT is unset."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=GroundingTemplateConfig(),
    )
    with mock.patch.dict(os.environ, {}, clear=True):
      with self.assertRaises(ValueError) as ctx:
        agent._get_genai_client()
      self.assertIn("GOOGLE_CLOUD_PROJECT", str(ctx.exception))

  def test_get_genai_client_cached_singleton(self):
    """Verifies that _get_genai_client caches and returns a singleton client instance."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=GroundingTemplateConfig(enabled=True),
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
    """Verifies that router classifier and vertex extractor share the single genai client."""
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=GroundingTemplateConfig(enabled=True),
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
        template_config=GroundingTemplateConfig(),
    )
    with mock.patch.dict(os.environ, {}, clear=True):
      with self.assertRaises(ValueError) as ctx:
        agent._get_vertex_extractor()
      self.assertIn("GOOGLE_CLOUD_PROJECT", str(ctx.exception))

  def test_get_vertex_extractor_with_project_id_succeeds(self):
    agent = MAUIAgentWithGrounding(
        base_url=self.base_url,
        template_config=GroundingTemplateConfig(
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

  async def test_stream_with_template_config_disabled_delegates_to_super(self):
    cfg = GroundingTemplateConfig(enabled=False)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
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
    cfg = GroundingTemplateConfig(enabled=True)
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

  async def test_classify_intent_successful(self):
    """Verifies that _classify_intent delegates to VertexIntentClassifier."""
    cfg = GroundingTemplateConfig(enabled=True)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    mock_classifier = mock.MagicMock(spec=VertexIntentClassifier)
    mock_classifier.classify = mock.AsyncMock(
        return_value=(INTENT_LOCAL_SEARCH, "coffee in seattle")
    )
    agent._router_classifier = mock_classifier

    intent, cleaned = await agent._classify_intent("find coffee in seattle")
    self.assertEqual(intent, INTENT_LOCAL_SEARCH)
    self.assertEqual(cleaned, "coffee in seattle")
    mock_classifier.classify.assert_called_once_with("find coffee in seattle")

  async def test_stream_local_search_intent_emits_template_parts(self):
    cfg = GroundingTemplateConfig(enabled=True, max_list_size=3)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_LOCAL_SEARCH, "coffee in seattle")
    )
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        return_value=LocalSearchExtractorSchema(
            heading="Coffee Shops in Seattle",
            summary="Found coffee shops.",
            center_lat=47.6,
            center_lng=-122.3,
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
    self.assertTrue(any(isinstance(p.root, DataPart) for p in parts))

  async def test_stream_directions_intent_emits_template_parts(self):
    cfg = GroundingTemplateConfig(enabled=True)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_DIRECTIONS, "from Times Sq to Central Park")
    )
    mock_extractor = mock.MagicMock()
    mock_extractor.extract = mock.AsyncMock(
        return_value=DirectionsExtractorSchema(
            summary="Directions from Times Sq to Central Park.",
            center_lat=40.77,
            center_lng=-73.97,
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
    self.assertTrue(any(isinstance(p.root, DataPart) for p in parts))

  async def test_stream_text_only_intent(self):
    cfg = GroundingTemplateConfig(enabled=True)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_TEXT_ONLY, "hello")
    )
    fake_part = create_a2ui_part({"text": "Hello there!"})
    agent._handle_grounded_text = mock.AsyncMock(return_value=[fake_part])

    chunks = []
    async for chunk in agent.stream("hello", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    agent._handle_grounded_text.assert_called_once_with("hello", "s1")

  async def test_stream_other_spatial_fallback_text(self):
    cfg = GroundingTemplateConfig(enabled=True, fallback_mode=FallbackMode.TEXT)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_OTHER_SPATIAL, "complex query")
    )
    fake_part = create_a2ui_part({"text": "Fallback text response"})
    agent._handle_grounded_text = mock.AsyncMock(return_value=[fake_part])

    chunks = []
    async for chunk in agent.stream("complex query", "s1", VERSION_0_9):
      chunks.append(chunk)

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    agent._handle_grounded_text.assert_called_once_with("complex query", "s1")

  async def test_stream_other_spatial_fallback_dynamic(self):
    cfg = GroundingTemplateConfig(
        enabled=True, fallback_mode=FallbackMode.DYNAMIC
    )
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_OTHER_SPATIAL, "complex query")
    )

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
    cfg = GroundingTemplateConfig(
        enabled=True, fallback_mode=FallbackMode.DYNAMIC
    )
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_LOCAL_SEARCH, "failing query")
    )
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
    cfg = GroundingTemplateConfig(enabled=True, fallback_mode=FallbackMode.TEXT)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)

    agent._classify_intent = mock.AsyncMock(
        return_value=(INTENT_LOCAL_SEARCH, "failing query")
    )
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
    """Verifies that _handle_grounded_text returns fallback text_only part when text generation is empty."""
    cfg = GroundingTemplateConfig(enabled=True)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
    mock_extractor = mock.MagicMock()
    mock_extractor.generate_grounded_text = mock.AsyncMock(return_value="")
    agent._vertex_extractor = mock_extractor

    parts = await agent._handle_grounded_text("test query", "s1")
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        any(
            "I'm sorry, I encountered an issue retrieving location details"
            in str(p.root.data)
            for p in parts
        )
    )

  async def test_handle_grounded_text_success(self):
    """Verifies that _handle_grounded_text formats generated text into text_only part."""
    cfg = GroundingTemplateConfig(enabled=True)
    agent = MAUIAgentWithGrounding(base_url=self.base_url, template_config=cfg)
    mock_extractor = mock.MagicMock()
    mock_extractor.generate_grounded_text = mock.AsyncMock(
        return_value="Grounded answer text"
    )
    agent._vertex_extractor = mock_extractor

    parts = await agent._handle_grounded_text("test query", "s1")
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        any("Grounded answer text" in str(p.root.data) for p in parts)
    )


if __name__ == "__main__":
  unittest.main()
