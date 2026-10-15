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

import json
import types
import unittest
from unittest import mock

from a2a.types import DataPart, TextPart

from a2ui.schema.constants import VERSION_0_9
from agent import MAUIAgent, extract_surface_id


def _make_event(text: str):
  """Creates a lightweight mock ADK runner event carrying a text chunk."""
  part = types.SimpleNamespace(text=text)
  content = types.SimpleNamespace(parts=[part])
  return types.SimpleNamespace(content=content)


def _valid_a2ui_payload(surface_id: str) -> str:
  """Returns a valid v0.9 <a2ui-json> string for testing."""
  messages = [
      {
          "version": "v0.9",
          "createSurface": {
              "surfaceId": surface_id,
              "catalogId": "a2ui://maps-agentic-ui-catalog.json",
          },
      },
      {
          "version": "v0.9",
          "updateComponents": {
              "surfaceId": surface_id,
              "components": [
                  {
                      "id": "root",
                      "component": "Column",
                      "children": ["msg_text"],
                  },
                  {
                      "id": "msg_text",
                      "component": "Text",
                      "text": "Found great coffee nearby.",
                  },
              ],
          },
      },
  ]
  return f"<a2ui-json>{json.dumps(messages)}</a2ui-json>"


def _invalid_a2ui_payload(surface_id: str) -> str:
  """Returns an invalid v0.9 <a2ui-json> string missing required fields."""
  messages = [
      {
          "version": "v0.9",
          "createSurface": {
              "surfaceId": surface_id,
              "catalogId": "a2ui://maps-agentic-ui-catalog.json",
          },
      },
      {
          "version": "v0.9",
          "updateComponents": {
              "surfaceId": surface_id,
          },
      },
  ]
  return f"<a2ui-json>{json.dumps(messages)}</a2ui-json>"


class SurfaceIdExtractionTest(unittest.TestCase):

  def test_extract_from_create_surface(self):
    data = {
        "createSurface": {"surfaceId": "map_surface_1", "catalogId": "maps"}
    }
    self.assertEqual(extract_surface_id(data), "map_surface_1")

  def test_extract_from_update_components(self):
    data = {
        "updateComponents": {"surfaceId": "details_card_2", "components": []}
    }
    self.assertEqual(extract_surface_id(data), "details_card_2")

  def test_extract_from_update_data_model(self):
    data = {"updateDataModel": {"surfaceId": "weather_card_3", "dataModel": {}}}
    self.assertEqual(extract_surface_id(data), "weather_card_3")

  def test_extract_from_delete_surface(self):
    data = {"deleteSurface": {"surfaceId": "old_surface_4"}}
    self.assertEqual(extract_surface_id(data), "old_surface_4")

  def test_extract_non_matching_or_malformed_data(self):
    self.assertIsNone(extract_surface_id({"text": "hello"}))
    self.assertIsNone(extract_surface_id(None))
    self.assertIsNone(extract_surface_id("not_a_dict"))
    self.assertIsNone(extract_surface_id({"createSurface": "malformed_shape"}))
    self.assertIsNone(extract_surface_id({"createSurface": {}}))


class MAUIAgentStreamTest(unittest.IsolatedAsyncioTestCase):
  """Unit tests for MAUIAgent.stream streaming, validation, and retry logic."""

  def setUp(self):
    super().setUp()
    self.agent = MAUIAgent(base_url="http://localhost:10002")

  async def test_stream_valid_first_attempt(self):
    valid_text = _valid_a2ui_payload("surface_ok")

    async def fake_run_async(**kwargs):  # pylint: disable=unused-argument
      yield _make_event(valid_text)

    runner = self.agent._ui_runners[VERSION_0_9]
    with mock.patch.object(runner, "run_async", side_effect=fake_run_async):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Coffee nearby",
              session_id="sess_valid",
              ui_version=VERSION_0_9,
          )
      ]

    self.assertTrue(chunks[-1]["is_task_complete"])
    delete_ids = [
        p.root.data["deleteSurface"]["surfaceId"]
        for c in chunks
        for p in c.get("parts", [])
        if isinstance(p.root, DataPart) and "deleteSurface" in p.root.data
    ]
    self.assertEqual(delete_ids, [])

  async def test_stream_deduplicates_identical_final_parts(self):
    valid_block = _valid_a2ui_payload("surface_dedup")
    duplicated_text = valid_block + valid_block

    async def fake_run_async(**kwargs):  # pylint: disable=unused-argument
      yield _make_event(duplicated_text)

    runner = self.agent._ui_runners[VERSION_0_9]
    with mock.patch.object(runner, "run_async", side_effect=fake_run_async):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Coffee nearby",
              session_id="sess_dedup",
              ui_version=VERSION_0_9,
          )
      ]

    final_parts = chunks[-1]["parts"]
    # 2 unique DataParts (createSurface + updateComponents), deduplicated from 4
    self.assertEqual(len(final_parts), 2)

  async def test_stream_retry_succeeds_after_first_attempt_failure(self):
    call_count = 0
    captured_prompts = []

    async def fake_run_async(**kwargs):
      nonlocal call_count
      call_count += 1
      new_msg = kwargs["new_message"]
      captured_prompts.append(new_msg.parts[0].text)
      if call_count == 1:
        yield _make_event(_invalid_a2ui_payload("broken_surface_1"))
      else:
        yield _make_event(_valid_a2ui_payload("recovered_surface_2"))

    runner = self.agent._ui_runners[VERSION_0_9]
    with mock.patch.object(runner, "run_async", side_effect=fake_run_async):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Coffee nearby",
              session_id="sess_retry_ok",
              ui_version=VERSION_0_9,
          )
      ]

    self.assertEqual(call_count, 2)
    self.assertIn("Your previous response was invalid.", captured_prompts[1])

    delete_ids = [
        p.root.data["deleteSurface"]["surfaceId"]
        for c in chunks
        for p in c.get("parts", [])
        if isinstance(p.root, DataPart) and "deleteSurface" in p.root.data
    ]
    self.assertEqual(delete_ids, ["broken_surface_1"])
    self.assertTrue(chunks[-1]["is_task_complete"])

  async def test_stream_exhausts_max_retries_returns_fallback_error(self):
    call_count = 0

    async def fake_run_async(**kwargs):  # pylint: disable=unused-argument
      nonlocal call_count
      call_count += 1
      yield _make_event(_invalid_a2ui_payload(f"broken_surface_{call_count}"))

    runner = self.agent._ui_runners[VERSION_0_9]
    with mock.patch.object(runner, "run_async", side_effect=fake_run_async):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Coffee nearby",
              session_id="sess_exhausted",
              ui_version=VERSION_0_9,
          )
      ]

    self.assertEqual(call_count, 2)
    final_chunk = chunks[-1]
    self.assertTrue(final_chunk["is_task_complete"])
    self.assertIsInstance(final_chunk["parts"][0].root, TextPart)
    self.assertIn(
        "trouble generating the interface",
        final_chunk["parts"][0].root.text,
    )

  async def test_stream_missing_schema_returns_configuration_error(self):
    schema_mgr = self.agent._schema_managers[VERSION_0_9]
    with mock.patch.object(
        schema_mgr, "get_selected_catalog", return_value=None
    ):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Coffee nearby",
              session_id="sess_no_schema",
              ui_version=VERSION_0_9,
          )
      ]

    self.assertEqual(len(chunks), 1)
    self.assertTrue(chunks[0]["is_task_complete"])
    self.assertIsInstance(chunks[0]["parts"][0].root, TextPart)
    self.assertIn(
        "internal configuration error", chunks[0]["parts"][0].root.text
    )

  async def test_stream_text_only_when_ui_version_is_none(self):
    async def fake_run_async(**kwargs):  # pylint: disable=unused-argument
      yield _make_event("Hello ")
      yield _make_event("world!")

    runner = self.agent._text_runner
    with mock.patch.object(runner, "run_async", side_effect=fake_run_async):
      chunks = [
          chunk
          async for chunk in self.agent.stream(
              query="Hi",
              session_id="sess_text",
              ui_version=None,
          )
      ]

    updates = [c["updates"] for c in chunks if "updates" in c]
    self.assertEqual(updates, ["Hello ", "world!"])


if __name__ == "__main__":
  unittest.main()
