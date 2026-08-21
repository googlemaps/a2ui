# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for MAUI Agent with templates orchestration."""

import unittest
from unittest import mock

from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from python_agent import agent_config
from python_agent import agent_with_templates

AgentConfig = agent_config.AgentConfig
FallbackMode = agent_config.FallbackMode
MAUIAgentWithTemplates = agent_with_templates.MAUIAgentWithTemplates

_LITELLM_PATH = (
    "python_agent"
    ".agent_with_templates.LiteLlm"
)


class MockPart:
  """Mock Part helper for test streaming."""

  def __init__(self, text=""):
    self.text = text


class MockContent:
  """Mock Content helper for test streaming."""

  def __init__(self, parts=None):
    self.parts = parts


class MockResponse:
  """Mock GenerateContentResponse helper for test streaming."""

  def __init__(self, content):
    self.content = content


class MockAsyncIterator:
  """Mock async iterator helper to simulate LLM stream."""

  def __init__(self, items):
    self.items = items

  def __aiter__(self):
    return self

  async def __anext__(self):
    if not self.items:
      raise StopAsyncIteration
    return self.items.pop(0)

  async def aclose(self):
    pass


class MockFunctionCall:
  """Mock FunctionCall helper for test streaming."""

  def __init__(self, name, args):
    self.name = name
    self.args = args


class MockEvent:
  """Mock Event helper for ADK runner streaming."""

  def __init__(self, function_calls=None, content=None, partial=False):
    self.function_calls = function_calls or []
    self.content = content
    self.partial = partial

  def get_function_calls(self):
    return self.function_calls


class TestAgentOrchestration(unittest.IsolatedAsyncioTestCase):
  """Unit tests for MAUIAgentWithTemplates orchestration."""

  def setUp(self):
    super().setUp()
    self.mock_router = mock.MagicMock(spec=LiteLlm)
    self.mock_router.model = "gemini/router-model"
    self.mock_extractor = mock.MagicMock(spec=LiteLlm)
    self.mock_extractor.model = "gemini/template-model"

  def _setup_mock_llm(self, mock_lite_llm_class):
    def lite_llm_side_effect(*args, **kwargs):
      model = kwargs.get("model") or (args[0] if args else None)
      if model == "gemini/router-model":
        return self.mock_router
      elif model in (
          "gemini/template-model",
          "gemini/gemini-3-flash-preview",
          "gemini/generic-model",
      ):
        return self.mock_extractor
      m = mock.MagicMock(spec=LiteLlm)
      m.model = model or "mock-model"
      return m

    mock_lite_llm_class.side_effect = lite_llm_side_effect

  def _mock_llm_stream(self, *contents: str) -> MockAsyncIterator:
    """Helper to mock LLM stream responses."""
    return MockAsyncIterator(
        [MockResponse(MockContent([MockPart(c)])) for c in contents]
    )

  def _get_component_by_id(self, parts, component_id: str) -> dict:
    """Helper to retrieve a component by ID from updateComponents parts."""
    for part in parts:
      if "updateComponents" in part.root.data:
        components = part.root.data["updateComponents"]["components"]
        for component in components:
          if component.get("id") == component_id:
            return component
    self.fail(f"Component with ID '{component_id}' not found in parts.")

  def _setup_agent(self, fallback_mode="TEXT"):
    """Helper to initialize MAUIAgentWithTemplates with standard config."""
    config = AgentConfig(
        fallback_mode=fallback_mode,
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    return MAUIAgentWithTemplates(base_url="http://test-url", config=config)

  def _mock_llm_responses(self, router_resp, extractor_resp=None):
    """Helper to set up default mock responses for router and extractor."""
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(router_resp)
    )
    if extractor_resp:
      self.mock_extractor.generate_content_async.return_value = (
          self._mock_llm_stream(extractor_resp)
      )

  async def _collect_stream(
      self, agent, query, session_id="session_123", ui_version="v0.9"
  ):
    """Helper to collect results from agent.stream."""
    results = []
    async for item in agent.stream(
        query=query, session_id=session_id, ui_version=ui_version
    ):
      results.append(item)
    return results

  @mock.patch(_LITELLM_PATH)
  async def test_agent_text_only_flow(self, mock_lite_llm_class):
    """Verifies fast text-only response flow when router yields TEXT_ONLY."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router response stream yielding classification JSON
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream('{"intent": "TEXT_ONLY", "query": "hello"}')
    )

    mock_runner = mock.MagicMock()
    mock_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent(
                [MockPart("This is a fast text-only response.")]
            )
        )
    ])

    config = AgentConfig(
        fallback_mode=FallbackMode.TEXT,
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, "hello")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    # createSurface and updateComponents
    self.assertTrue(
        parts[0]
        .root.data["createSurface"]["surfaceId"]
        .startswith("text-only_session_123-")
    )
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "This is a fast text-only response.",
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_router_failure_fallback(self, mock_lite_llm_class):
    """Verifies fallback to TEXT_ONLY when router fails."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.side_effect = Exception(
        "Router error"
    )
    mock_runner = mock.MagicMock()
    mock_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent([MockPart("Response after router failure.")])
        )
    ])

    config = AgentConfig(
        fallback_mode=FallbackMode.TEXT,
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, "hello")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "Response after router failure.",
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_extractor_empty_parts_handled_safely(
      self, mock_lite_llm_class
  ):
    """Verifies extractor response with empty/None parts is handled safely."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream('{"intent": "TEXT_ONLY", "query": "hello"}')
    )

    mock_runner = mock.MagicMock()
    mock_runner.run_async.return_value = MockAsyncIterator(
        [MockEvent(content=MockContent(None))]
    )

    config = AgentConfig(
        fallback_mode=FallbackMode.TEXT,
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, "hello")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "I'm sorry, I encountered an issue retrieving location details right"
        " now.",
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_unsupported_intent_fallback(self, mock_lite_llm_class):
    """Verifies fallback to base stream for unsupported intents (DYNAMIC)."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream('{"intent": "OTHER_SPATIAL", "query": "coffee"}')
    )

    config = AgentConfig(
        fallback_mode=FallbackMode.DYNAMIC,
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch(
        "python_agent.agent.MAUIAgent.stream",
    ) as mock_super_stream:
      mock_super_stream.return_value = MockAsyncIterator(
          [{"is_task_complete": False, "parts": ["dummy_base_part"]}]
      )

      results = []
      async for item in agent.stream(
          query="coffee", session_id="session_123", ui_version="v0.9"
      ):
        results.append(item)

      mock_super_stream.assert_called_once_with("coffee", "session_123", "v0.9")
      self.assertEqual(
          results, [{"is_task_complete": False, "parts": ["dummy_base_part"]}]
      )

  def test_init_without_config_uses_default(self):
    agent = MAUIAgentWithTemplates(base_url="http://test-url")
    self.assertIsNotNone(agent.config)
    self.assertEqual(agent.config.router_model, "gemini/gemini-3.1-flash-lite")
    self.assertEqual(
        agent.config.template_model, "gemini/gemini-3.1-flash-lite"
    )
    self.assertEqual(agent.config.fallback_mode, FallbackMode.TEXT)

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow(self, mock_lite_llm_class):
    """Verifies template extraction and merging for DIRECTIONS intent."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router yielding DIRECTIONS
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "directions from home to work"}'
        )
    )

    # Mock extractor runner:
    mock_runner = mock.MagicMock()

    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Typical commute is 45 mins.",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "zoom": 12,
            "routes": [{
                "origin": {
                    "lat": 37.4,
                    "lng": 126.9,
                    "label": "Home",
                    "placeId": "ChIJ_origin",
                },
                "destination": {
                    "lat": 37.6,
                    "lng": 127.1,
                    "label": "Work",
                    "placeId": "ChIJ_dest",
                },
            }],
            "travel_mode": "driving",
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    # Patch _build_runner
    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      # Run stream
      results = []
      async for item in agent.stream(
          query="directions from home to work",
          session_id="session_123",
          ui_version="v0.9",
      ):
        results.append(item)

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 3)

    create_surface = parts[0].root.data["createSurface"]
    self.assertTrue(
        create_surface["surfaceId"].startswith("directions-surface-")
    )

    map_comp = self._get_component_by_id(parts, "map")
    self.assertEqual(map_comp["center"], {"lat": 37.5, "lng": 127.0})
    self.assertEqual(map_comp["travelMode"], "driving")

    route = map_comp["routes"][0]
    self.assertEqual(route["origin"]["label"], "Home")
    self.assertEqual(route["destination"]["label"], "Work")

    update_data_model = parts[2].root.data["updateDataModel"]
    self.assertEqual(update_data_model["path"], "/")
    self.assertEqual(update_data_model["value"], {})

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow_fallback(self, mock_lite_llm_class):
    """Verifies DIRECTIONS flow falls back to text_only when extraction fails."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router yielding DIRECTIONS
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "directions to work"}'
        )
    )

    self.mock_extractor.generate_content_async.return_value = (
        self._mock_llm_stream("Cannot find route.")
    )

    mock_runner = mock.MagicMock()
    mock_event = MockEvent(
        content=MockContent([MockPart("Cannot find route.")])
    )
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        fallback_mode="TEXT",
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = []
      async for item in agent.stream(
          query="directions to work",
          session_id="session_123",
          ui_version="v0.9",
      ):
        results.append(item)

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        parts[0]
        .root.data["createSurface"]["surfaceId"]
        .startswith("text-only_session_123-")
    )
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "Cannot find route.",
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow_transit_mode(self, mock_lite_llm_class):
    """Verifies template extraction and merging with transit travel mode."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "bus to work"}'
        )
    )

    mock_runner = mock.MagicMock()
    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Take bus 10 to work.",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "zoom": 12,
            "routes": [{
                "origin": {
                    "lat": 37.4,
                    "lng": 126.9,
                    "label": "Home",
                    "placeId": "ChIJ_origin",
                },
                "destination": {
                    "lat": 37.6,
                    "lng": 127.1,
                    "label": "Work",
                    "placeId": "ChIJ_dest",
                },
            }],
            "travel_mode": "transit",
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, query="bus to work")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    map_comp = self._get_component_by_id(parts, "map")
    self.assertEqual(map_comp["travelMode"], "transit")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow_walking_mode(self, mock_lite_llm_class):
    """Verifies template extraction and merging with walking travel mode."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "walk to park"}'
        )
    )

    mock_runner = mock.MagicMock()
    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Walk for 15 minutes.",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "zoom": 12,
            "routes": [{
                "origin": {
                    "lat": 37.4,
                    "lng": 126.9,
                    "label": "Home",
                    "placeId": "ChIJ_origin",
                },
                "destination": {
                    "lat": 37.6,
                    "lng": 127.1,
                    "label": "Park",
                    "placeId": "ChIJ_dest",
                },
            }],
            "travel_mode": "walking",
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, query="walk to park")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    map_comp = self._get_component_by_id(parts, "map")
    self.assertEqual(map_comp["travelMode"], "walking")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow_bicycling_mode(
      self, mock_lite_llm_class
  ):
    """Verifies template extraction and merging with bicycling travel mode."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "bike to work"}'
        )
    )

    mock_runner = mock.MagicMock()
    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Bike for 25 minutes.",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "zoom": 12,
            "routes": [{
                "origin": {
                    "lat": 37.4,
                    "lng": 126.9,
                    "label": "Home",
                    "placeId": "ChIJ_origin",
                },
                "destination": {
                    "lat": 37.6,
                    "lng": 127.1,
                    "label": "Work",
                    "placeId": "ChIJ_dest",
                },
            }],
            "travel_mode": "bicycling",
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, query="bike to work")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    map_comp = self._get_component_by_id(parts, "map")
    self.assertEqual(map_comp["travelMode"], "bicycling")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_directions_flow_missing_travel_mode_fallback(
      self, mock_lite_llm_class
  ):
    """Verifies that omitting travel_mode causes schema validation failure and fallback to text-only."""
    self._setup_mock_llm(mock_lite_llm_class)

    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "DIRECTIONS", "query": "directions to work"}'
        )
    )

    self.mock_extractor.generate_content_async.return_value = (
        self._mock_llm_stream("Fallback plain text directions.")
    )

    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Typical commute is 45 mins.",
            "center_lat": 37.5,
            "center_lng": 127.0,
            "zoom": 12,
            "routes": [{
                "origin": {
                    "lat": 37.4,
                    "lng": 126.9,
                    "label": "Home",
                    "placeId": "ChIJ_origin",
                },
                "destination": {
                    "lat": 37.6,
                    "lng": 127.1,
                    "label": "Work",
                    "placeId": "ChIJ_dest",
                },
            }],
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_extractor_runner = mock.MagicMock()
    mock_extractor_runner.run_async.return_value = MockAsyncIterator(
        [mock_event]
    )

    mock_fallback_runner = mock.MagicMock()
    mock_fallback_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent([MockPart("Fallback plain text directions.")])
        )
    ])

    config = AgentConfig(
        fallback_mode="TEXT",
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(
        agent,
        "_build_runner",
        side_effect=[mock_extractor_runner, mock_fallback_runner],
    ):
      results = await self._collect_stream(agent, query="directions to work")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        parts[0]
        .root.data["createSurface"]["surfaceId"]
        .startswith("text-only_session_123-")
    )
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "Fallback plain text directions.",
    )

  @mock.patch(
      "python_agent.agent_with_templates.LiteLlm"
  )
  async def test_agent_local_search_flow(self, mock_lite_llm_class):
    """Verifies local search flow, structured extraction, and template merging."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router yielding LOCAL_SEARCH
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream(
            '{"intent": "LOCAL_SEARCH", "query": "sushi Seattle"}'
        )
    )

    # Mock extractor runner:
    mock_runner = mock.MagicMock()

    mock_fc = MockFunctionCall(
        name="set_model_response",
        args={
            "summary": "Here are some sushi places.",
            "center_lat": 47.6062,
            "center_lng": -122.3321,
            "zoom": 13,
            "places": [{
                "placeId": "ChIJ111",
                "name": "Shiki Sushi",
                "lat": 47.6200,
                "lng": -122.3200,
            }],
        },
    )
    mock_event = MockEvent(function_calls=[mock_fc])
    mock_runner.run_async.return_value = MockAsyncIterator([mock_event])

    config = AgentConfig(
        fallback_mode="DYNAMIC",
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    # Patch _build_runner
    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = []
      async for item in agent.stream(
          query="sushi Seattle", session_id="session_123", ui_version="v0.9"
      ):
        results.append(item)

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 3)

    create_surface = parts[0].root.data["createSurface"]
    self.assertTrue(
        create_surface["surfaceId"].startswith("local-search-surface-")
    )

    update_data_model = parts[2].root.data["updateDataModel"]
    # Verify places array was successfully populated in data model
    self.assertEqual(update_data_model["path"], "/")
    places = update_data_model["value"]["places"]
    self.assertEqual(len(places), 1)
    self.assertEqual(places[0]["name"], "Shiki Sushi")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_local_search_flow_validation_failure_fallback(
      self, mock_lite_llm_class
  ):
    """Verifies LOCAL_SEARCH fallback when extraction validation fails."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router yielding LOCAL_SEARCH
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream('{"intent": "LOCAL_SEARCH", "query": "coffee"}')
    )

    self.mock_extractor.generate_content_async.return_value = (
        self._mock_llm_stream("Fallback text here.")
    )

    mock_runner = mock.MagicMock()

    # Mock invalid set_model_response arguments (missing required center_lat)
    invalid_args = {"summary": "Invalid data", "places": []}
    mock_fc = MockFunctionCall("set_model_response", invalid_args)
    mock_event_fc = MockEvent(function_calls=[mock_fc])
    mock_event_text = MockEvent(
        content=MockContent([MockPart("Fallback text here.")])
    )

    mock_runner.run_async.return_value = MockAsyncIterator(
        [mock_event_fc, mock_event_text]
    )

    config = AgentConfig(
        fallback_mode="TEXT",
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    # Patch _build_runner
    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = []
      async for item in agent.stream(
          query="coffee", session_id="session_123", ui_version="v0.9"
      ):
        results.append(item)

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    self.assertTrue(
        parts[0]
        .root.data["createSurface"]["surfaceId"]
        .startswith("text-only_session_123-")
    )
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"],
        "Fallback text here.",
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_local_search_flow_catalog_validation_failure_fallback(
      self, mock_lite_llm_class
  ):
    """Verifies LOCAL_SEARCH flow falls back to text_only when catalog validation fails."""
    self._setup_mock_llm(mock_lite_llm_class)
    self._mock_llm_responses(
        router_resp='{"intent": "LOCAL_SEARCH", "query": "coffee"}',
        extractor_resp="Fallback text from LLM.",
    )

    mock_runner = mock.MagicMock()
    mock_fc = MockFunctionCall(
        "set_model_response",
        {"summary": "Coffee", "places": [{"name": "Starbucks"}]},
    )
    mock_runner.run_async.return_value = MockAsyncIterator(
        [MockEvent(function_calls=[mock_fc])]
    )

    agent = self._setup_agent(fallback_mode="TEXT")

    # Mock schema manager to return a catalog that fails validation (generic Exception)
    mock_catalog = mock.MagicMock()
    mock_catalog.validator.validate.side_effect = Exception(
        "Mock validation error"
    )
    mock_schema_manager = mock.MagicMock()
    mock_schema_manager.get_catalog.return_value = mock_catalog
    agent._schema_managers = {"v0.9": mock_schema_manager}

    mock_fallback_runner = mock.MagicMock()
    mock_fallback_runner.run_async.return_value = MockAsyncIterator(
        [MockEvent(content=MockContent([MockPart("Fallback text from LLM.")]))]
    )

    with mock.patch.object(
        agent, "_build_runner", side_effect=[mock_runner, mock_fallback_runner]
    ):
      results = await self._collect_stream(agent, "coffee")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    text_comp = self._get_component_by_id(results[0]["parts"], "text-content")
    self.assertEqual(text_comp["text"], "Fallback text from LLM.")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_fallback_mode_text_on_extractor_failure(
      self, mock_lite_llm_class
  ):
    """Verifies TEXT fallback mode when template extractor fails."""
    self._setup_mock_llm(mock_lite_llm_class)
    self._mock_llm_responses(
        router_resp='{"intent": "LOCAL_SEARCH", "query": "sushi Seattle"}',
    )
    mock_extractor_runner = mock.MagicMock()
    mock_extractor_runner.run_async.return_value = MockAsyncIterator(
        [MockEvent()]
    )
    mock_fallback_runner = mock.MagicMock()
    mock_fallback_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent(
                [MockPart("I could not search places right now.")]
            )
        )
    ])

    agent = self._setup_agent(fallback_mode="TEXT")
    with mock.patch.object(
        agent,
        "_build_runner",
        side_effect=[mock_extractor_runner, mock_fallback_runner],
    ):
      results = await self._collect_stream(agent, "sushi Seattle")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(text_comp["text"], "I could not search places right now.")

  @mock.patch(_LITELLM_PATH)
  async def test_agent_fallback_mode_dynamic_on_extractor_failure(
      self, mock_lite_llm_class
  ):
    """Verifies extractor failure always falls back to TEXT response, even in DYNAMIC mode."""
    self._setup_mock_llm(mock_lite_llm_class)
    self._mock_llm_responses(
        router_resp='{"intent": "LOCAL_SEARCH", "query": "sushi Seattle"}',
    )
    mock_extractor_runner = mock.MagicMock()
    mock_extractor_runner.run_async.return_value = MockAsyncIterator(
        [MockEvent()]
    )
    mock_fallback_runner = mock.MagicMock()
    mock_fallback_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent(
                [MockPart("Fast response after extraction failure.")]
            )
        )
    ])

    agent = self._setup_agent(fallback_mode="DYNAMIC")
    with mock.patch.object(
        agent,
        "_build_runner",
        side_effect=[mock_extractor_runner, mock_fallback_runner],
    ):
      with mock.patch(
          "python_agent.agent.MAUIAgent.stream",
      ) as mock_super_stream:
        results = await self._collect_stream(agent, "sushi Seattle")

    mock_super_stream.assert_not_called()
    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"], "Fast response after extraction failure."
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_other_spatial_fallback_mode_text(
      self, mock_lite_llm_class
  ):
    """Verifies OTHER_SPATIAL intent routes to TEXT fallback mode."""
    self._setup_mock_llm(mock_lite_llm_class)
    self._mock_llm_responses(
        router_resp='{"intent": "OTHER_SPATIAL", "query": "weather Yosemite"}',
    )
    mock_runner = mock.MagicMock()
    mock_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(
            content=MockContent(
                [MockPart("The weather in Yosemite is sunny, 75 degrees.")]
            )
        )
    ])
    agent = self._setup_agent(fallback_mode="TEXT")
    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, "weather Yosemite")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    self.assertEqual(len(parts), 2)
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(
        text_comp["text"], "The weather in Yosemite is sunny, 75 degrees."
    )

  @mock.patch(_LITELLM_PATH)
  async def test_agent_other_spatial_fallback_mode_dynamic(
      self, mock_lite_llm_class
  ):
    """Verifies OTHER_SPATIAL intent routes to DYNAMIC fallback mode."""
    self._setup_mock_llm(mock_lite_llm_class)
    self._mock_llm_responses(
        router_resp='{"intent": "OTHER_SPATIAL", "query": "weather Yosemite"}'
    )
    agent = self._setup_agent(fallback_mode="DYNAMIC")

    mock_part = mock.MagicMock()
    mock_part.root.text = "base_agent_dynamic_ui"

    async def mock_super_stream_gen(*_args, **_kwargs):
      yield {
          "is_task_complete": True,
          "parts": [mock_part],
      }

    # Patch MAUIAgent.stream
    with mock.patch(
        "python_agent.agent.MAUIAgent.stream",
        side_effect=mock_super_stream_gen,
    ) as mock_super_stream:
      results = await self._collect_stream(agent, "weather Yosemite")

    mock_super_stream.assert_called_once_with(
        "weather Yosemite", "session_123", "v0.9"
    )
    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    self.assertEqual(results[0]["parts"][0].root.text, "base_agent_dynamic_ui")

  @mock.patch(
      "python_agent.agent_with_templates.LiteLlm"
  )
  async def test_extractor_duplication_prevented(self, mock_lite_llm_class):
    """Verifies that text is not duplicated in fallback if extractor yields partial and final events."""
    self._setup_mock_llm(mock_lite_llm_class)

    # Mock router yielding LOCAL_SEARCH
    self.mock_router.generate_content_async.return_value = (
        self._mock_llm_stream('{"intent": "LOCAL_SEARCH", "query": "sushi"}')
    )

    # Mock extractor runner yielding partials and then final consolidated event
    mock_runner = mock.MagicMock()
    mock_runner.run_async.return_value = MockAsyncIterator([
        MockEvent(content=MockContent([MockPart("I'")]), partial=True),
        MockEvent(content=MockContent([MockPart("m sorry")]), partial=True),
        MockEvent(content=MockContent([MockPart("I'm sorry")]), partial=False),
    ])

    config = AgentConfig(
        fallback_mode="TEXT",
        router_model="gemini/router-model",
        template_model="gemini/template-model",
    )
    agent = MAUIAgentWithTemplates(base_url="http://test-url", config=config)

    with mock.patch.object(agent, "_build_runner", return_value=mock_runner):
      results = await self._collect_stream(agent, "sushi")

    self.assertEqual(len(results), 1)
    self.assertTrue(results[0]["is_task_complete"])
    parts = results[0]["parts"]
    text_comp = self._get_component_by_id(parts, "text-content")
    self.assertEqual(text_comp["text"], "I'm sorry")

  def test_build_runner_sets_auto_create_session(self):
    agent = MAUIAgentWithTemplates(base_url="http://test-url")
    mock_agent = mock.MagicMock(spec=LlmAgent)
    runner = agent._build_runner(mock_agent)  # pylint: disable=protected-access
    self.assertTrue(runner.auto_create_session)

  def test_build_dynamic_extractor_agent_appends_shared_guidelines(self):
    """Verifies that shared guidelines are appended to skill instructions."""
    agent = MAUIAgentWithTemplates(base_url="http://test-url")
    with mock.patch(
        "builtins.open", mock.mock_open(read_data="Shared guidelines content")
    ) as mock_file:
      with mock.patch(
          "google.adk.skills.load_skill_from_dir"
      ) as mock_load_skill:
        mock_skill = mock.MagicMock()
        mock_skill.instructions = "Base skill instructions"
        mock_load_skill.return_value = mock_skill

        extractor_agent = agent._build_dynamic_extractor_agent(  # pylint: disable=protected-access
            "local-search-template-response"
        )
        self.assertIn("Shared guidelines content", extractor_agent.instruction)
        self.assertIn("Base skill instructions", extractor_agent.instruction)
        mock_file.assert_called_once()

  def test_build_dynamic_extractor_agent_handles_file_read_error(self):
    """Verifies that file read errors are handled gracefully when loading guidelines."""
    agent = MAUIAgentWithTemplates(base_url="http://test-url")
    with mock.patch("builtins.open", side_effect=OSError("Read error")):
      with mock.patch(
          "google.adk.skills.load_skill_from_dir"
      ) as mock_load_skill:
        mock_skill = mock.MagicMock()
        mock_skill.instructions = "Base skill instructions"
        mock_load_skill.return_value = mock_skill

        # Check that it handles OSError gracefully and proceeds
        extractor_agent = agent._build_dynamic_extractor_agent(  # pylint: disable=protected-access
            "local-search-template-response"
        )
        self.assertNotIn(
            "Shared guidelines content", extractor_agent.instruction
        )
        self.assertIn("Base skill instructions", extractor_agent.instruction)

if __name__ == "__main__":
  unittest.main()
