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

"""Tests for Router Configuration."""

import unittest
from unittest import mock
from google import genai
from router_config import IntentClass
from router_config import ROUTER_SYSTEM_INSTRUCTION
from router_config import RouterClassification
from router_config import VertexIntentClassifier


class TestRouterConfig(unittest.TestCase):
  """Unit tests for Intent Router configuration schema and prompt."""

  def test_schema_instantiation(self):
    data = {"intent": "LOCAL_SEARCH", "query": "coffee near me"}
    classification = RouterClassification(**data)
    self.assertEqual(classification.intent, IntentClass.LOCAL_SEARCH)
    self.assertEqual(classification.query, "coffee near me")

  def test_schema_validation_error(self):
    data = {"intent": "INVALID_INTENT", "query": "coffee near me"}
    with self.assertRaises(ValueError):
      RouterClassification(**data)

  def test_instruction_not_empty(self):
    self.assertGreater(len(ROUTER_SYSTEM_INSTRUCTION), 0)


class TestVertexIntentClassifier(unittest.IsolatedAsyncioTestCase):
  """Unit tests for VertexIntentClassifier."""

  def test_constructor_validation_missing_project_and_client_raises(self):
    """Verifies that constructor raises ValueError when project_id and client are missing."""
    with self.assertRaises(ValueError) as ctx:
      VertexIntentClassifier()
    self.assertIn("project_id", str(ctx.exception))

    with self.assertRaises(ValueError) as ctx:
      VertexIntentClassifier(project_id=None, client=None)
    self.assertIn("project_id", str(ctx.exception))

  def test_constructor_with_project_id_succeeds(self):
    """Verifies that constructor succeeds with a valid project_id."""
    classifier = VertexIntentClassifier(project_id="test-proj")
    self.assertEqual(classifier.project_id, "test-proj")
    self.assertEqual(classifier.location, "global")
    self.assertEqual(classifier.model_id, "gemini-3.5-flash-lite")

  def test_constructor_with_shared_client_succeeds_without_project_id(self):
    """Verifies that constructor succeeds when client is provided without project_id."""
    mock_client = mock.MagicMock(spec=genai.Client)
    classifier = VertexIntentClassifier(client=mock_client)
    self.assertIs(classifier.client, mock_client)

  def test_shared_client_injection_avoids_new_client(self):
    """Verifies that injecting a client avoids instantiating a new genai.Client."""
    mock_client = mock.MagicMock(spec=genai.Client)
    with mock.patch("google.genai.Client") as mock_genai_cls:
      classifier = VertexIntentClassifier(project_id="p1", client=mock_client)
      self.assertIs(classifier.client, mock_client)
      mock_genai_cls.assert_not_called()

  def test_lazy_client_initialization_when_not_injected(self):
    """Verifies that client is lazily initialized when not injected."""
    mock_instance = mock.MagicMock()
    with mock.patch(
        "google.genai.Client", return_value=mock_instance
    ) as mock_genai_cls:
      classifier = VertexIntentClassifier(project_id="p1", location="us-west1")
      self.assertIsNone(classifier._client)
      client = classifier.client
      self.assertIs(client, mock_instance)
      mock_genai_cls.assert_called_once_with(
          vertexai=True, project="p1", location="us-west1"
      )

  def test_model_id_normalization(self):
    """Verifies model ID prefix stripping for various formats."""
    test_cases = [
        ("gemini/gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
        ("models/gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini/gemini-3-flash-preview", "gemini-3-flash-preview"),
    ]
    mock_client = mock.MagicMock(spec=genai.Client)
    for raw_model, expected_model in test_cases:
      with self.subTest(raw_model=raw_model):
        classifier = VertexIntentClassifier(
            client=mock_client, model_id=raw_model
        )
        self.assertEqual(classifier.model_id, expected_model)

  async def test_classify_with_parsed_response(self):
    """Verifies classification when structured response is in response.parsed."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = RouterClassification(
        intent=IntentClass.LOCAL_SEARCH, query="coffee near me"
    )
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(client=mock_client)

    intent, query = await classifier.classify("find coffee near me")
    self.assertEqual(intent, IntentClass.LOCAL_SEARCH)
    self.assertEqual(query, "coffee near me")

  async def test_classify_with_text_json_fallback(self):
    """Verifies classification fallback to response.text JSON parsing."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = None
    mock_response.text = '{"intent": "DIRECTIONS", "query": "route to park"}'
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(client=mock_client)

    intent, query = await classifier.classify("directions to park")
    self.assertEqual(intent, IntentClass.DIRECTIONS)
    self.assertEqual(query, "route to park")

  async def test_classify_with_markdown_fenced_json(self):
    """Verifies classification handles response.text wrapped in markdown code fences."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = None
    mock_response.text = (
        '```json\n{"intent": "DIRECTIONS", "query": "route to park"}\n```'
    )
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(client=mock_client)

    intent, query = await classifier.classify("directions to park")
    self.assertEqual(intent, IntentClass.DIRECTIONS)
    self.assertEqual(query, "route to park")

  async def test_classify_thinking_budget_passed_in_config(self):
    """Verifies thinking_config is included when thinking_budget is positive."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = RouterClassification(
        intent=IntentClass.OTHER_SPATIAL, query="map"
    )
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(
        client=mock_client, thinking_budget=1024
    )

    await classifier.classify("show map")
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    self.assertIsNotNone(call_kwargs["config"].thinking_config)
    self.assertEqual(
        call_kwargs["config"].thinking_config.thinking_budget, 1024
    )

  async def test_classify_zero_thinking_budget_omits_thinking_config(self):
    """Verifies thinking_config is omitted when thinking_budget is zero."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = RouterClassification(
        intent=IntentClass.TEXT_ONLY, query="hello"
    )
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(client=mock_client, thinking_budget=0)

    await classifier.classify("hello")
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    self.assertIsNone(call_kwargs["config"].thinking_config)

  async def test_classify_error_handling_invalid_json_raises(self):
    """Verifies that invalid JSON output raises an Exception."""
    mock_client = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.parsed = None
    mock_response.text = "NOT_VALID_JSON"
    mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )
    classifier = VertexIntentClassifier(client=mock_client)

    with self.assertRaises(Exception):
      await classifier.classify("invalid")

  async def test_classify_error_handling_api_error_raises(self):
    """Verifies that API errors are propagated to the caller."""
    mock_client = mock.MagicMock()
    mock_client.aio.models.generate_content = mock.AsyncMock(
        side_effect=RuntimeError("API Error")
    )
    classifier = VertexIntentClassifier(client=mock_client)

    with self.assertRaises(RuntimeError):
      await classifier.classify("query")


if __name__ == "__main__":
  unittest.main()
