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

"""Tests for Native Vertex AI Intent Classifier."""

import unittest
from unittest import mock

import router
import template_registry


class VertexIntentClassifierTest(unittest.IsolatedAsyncioTestCase):

  def setUp(self):
    super().setUp()
    self.registry = template_registry.TemplateRegistry()
    self.mock_client = mock.MagicMock()
    self.classifier = router.VertexIntentClassifier(
        project_id="test-project",
        client=self.mock_client,
        registry=self.registry,
    )

  def test_constructor_validation(self):
    self.assertIsInstance(self.classifier, router.IntentClassifier)
    with self.assertRaises(ValueError):
      router.VertexIntentClassifier(project_id=None, client=None)

    c = router.VertexIntentClassifier(
        project_id="p1",
        model_id="gemini/gemini-3.1-flash-lite",
        client=self.mock_client,
    )
    self.assertEqual(c.model_id, "gemini-3.1-flash-lite")

  async def test_classify_with_parsed_response(self):
    mock_parsed = mock.MagicMock()
    mock_parsed.intent = "LOCAL_SEARCH"
    mock_parsed.query = "Coffee shops"

    mock_response = mock.MagicMock()
    mock_response.parsed = mock_parsed
    mock_response.text = None

    self.mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )

    intent, query = await self.classifier.classify("Coffee shops")
    self.assertEqual(intent, "LOCAL_SEARCH")
    self.assertEqual(query, "Coffee shops")

  async def test_classify_with_json_text_fallback(self):
    mock_response = mock.MagicMock()
    mock_response.parsed = None
    mock_response.text = (
        '```json\n{"intent": "DIRECTIONS", "query": "Directions to Central'
        ' Park"}\n```'
    )

    self.mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )

    intent, query = await self.classifier.classify("Directions to Central Park")
    self.assertEqual(intent, "DIRECTIONS")
    self.assertEqual(query, "Directions to Central Park")

  async def test_classify_thinking_budget_forwarding(self):
    classifier = router.VertexIntentClassifier(
        project_id="test-project",
        client=self.mock_client,
        thinking_budget=1024,
        registry=self.registry,
    )

    mock_parsed = mock.MagicMock()
    mock_parsed.intent = "TEXT_ONLY"
    mock_parsed.query = "Hello"

    mock_response = mock.MagicMock()
    mock_response.parsed = mock_parsed

    self.mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )

    await classifier.classify("Hello")

    call_kwargs = self.mock_client.aio.models.generate_content.call_args[1]
    config = call_kwargs["config"]
    self.assertIsNotNone(config.thinking_config)
    self.assertEqual(config.thinking_config.thinking_budget, 1024)

  async def test_classify_empty_response_raises(self):
    mock_response = mock.MagicMock()
    mock_response.parsed = None
    mock_response.text = ""

    self.mock_client.aio.models.generate_content = mock.AsyncMock(
        return_value=mock_response
    )

    with self.assertRaises(ValueError):
      await self.classifier.classify("Test query")


if __name__ == "__main__":
  unittest.main()
