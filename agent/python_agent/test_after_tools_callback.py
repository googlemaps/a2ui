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

"""Tests for after_tools_callback."""

import unittest
from unittest import mock

from after_tools_callback import _add_maps_tools_tokens_to_part, after_maps_tools_callback, after_tools_callback


class TestAfterToolsCallback(unittest.TestCase):

  def test_after_tool_callback_aggregates_maps_tools_content_tokens(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    tool_response_1 = {
        "content_token": "token_abc_123",
    }
    after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response=tool_response_1,
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_abc_123"],
    )

    tool_response_2 = {
        "content_token": "token_def_456",
    }
    after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response=tool_response_2,
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_abc_123", "token_def_456"],
    )

    # Calling again with duplicate should not add duplicates
    after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response={"content_token": "token_abc_123"},
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_abc_123", "token_def_456"],
    )

  def test_after_tool_callback_limits_maps_tools_content_tokens(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    for i in range(15):
      after_tools_callback(
          tool=None,
          args={},
          tool_context=mock_tool_context,
          tool_response={"content_token": f"token_{i}"},
      )

    tokens = mock_tool_context.state.get("maps_tools_content_tokens")
    self.assertEqual(len(tokens), 10)
    self.assertEqual(tokens[0], "token_5")
    self.assertEqual(tokens[-1], "token_14")

  def test_after_tool_callback_with_kwargs(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    after_tools_callback(
        tool="mock_tool",
        args={"query": "test"},
        tool_context=mock_tool_context,
        tool_response={"content_token": "token_xyz"},
        extra_param="unused",
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_xyz"],
    )

  def test_after_tools_callback_none_or_empty_response(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    # None tool response
    result = after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response=None,
    )
    self.assertIsNone(result)
    self.assertEqual(mock_tool_context.state, {})

    # Empty dict tool response
    result = after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response={},
    )
    self.assertIsNone(result)
    self.assertEqual(mock_tool_context.state, {})

    # Non-dict tool response
    result = after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response="not a dict",
    )
    self.assertIsNone(result)
    self.assertEqual(mock_tool_context.state, {})

    result = after_tools_callback(
        tool=None,
        args={},
        tool_context=mock_tool_context,
        tool_response=["list_not_dict"],
    )
    self.assertIsNone(result)
    self.assertEqual(mock_tool_context.state, {})

  def test_after_maps_tools_callback_none_or_missing_context(self):
    # None tool_context
    result = after_maps_tools_callback(
        tool_context=None,
        tool_response={"content_token": "token_1"},
    )
    self.assertIsNone(result)

    # tool_context with state=None
    mock_context_no_state = mock.MagicMock()
    mock_context_no_state.state = None
    result = after_maps_tools_callback(
        tool_context=mock_context_no_state,
        tool_response={"content_token": "token_1"},
    )
    self.assertIsNone(result)

    # tool_context without state attribute
    class DummyContext:
      pass

    result = after_maps_tools_callback(
        tool_context=DummyContext(),
        tool_response={"content_token": "token_1"},
    )
    self.assertIsNone(result)

  def test_after_maps_tools_callback_invalid_token_values(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    # None token
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"content_token": None},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Empty string token
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"content_token": ""},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Non-string token (int)
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"content_token": 12345},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Missing content_token key
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"places": []},
    )
    self.assertEqual(mock_tool_context.state, {})

  def test_after_maps_tools_callback_non_list_state_content_tokens(self):
    mock_tool_context = mock.MagicMock()

    # If state['maps_tools_content_tokens'] is not a list (e.g. a string)
    mock_tool_context.state = {"maps_tools_content_tokens": "invalid_string"}
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"content_token": "token_1"},
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_1"],
    )

    # If state['maps_tools_content_tokens'] is None
    mock_tool_context.state = {"maps_tools_content_tokens": None}
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"content_token": "token_2"},
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_2"],
    )


class TestAddMapsToolsTokensToPart(unittest.TestCase):

  def test_add_tokens_session_none_or_missing_state(self):
    part = mock.MagicMock()
    part.root.metadata = None

    # session is None
    _add_maps_tools_tokens_to_part(part, None)
    self.assertIsNone(part.root.metadata)

    # session.state is None
    mock_session = mock.MagicMock()
    mock_session.state = None
    _add_maps_tools_tokens_to_part(part, mock_session)
    self.assertIsNone(part.root.metadata)

  def test_add_tokens_empty_tokens_in_session(self):
    part = mock.MagicMock()
    part.root.metadata = None

    # maps_tools_content_tokens is not in state
    session = mock.MagicMock()
    session.state = {}
    _add_maps_tools_tokens_to_part(part, session)
    self.assertIsNone(part.root.metadata)

    # maps_tools_content_tokens is empty list
    session.state = {"maps_tools_content_tokens": []}
    _add_maps_tools_tokens_to_part(part, session)
    self.assertIsNone(part.root.metadata)

    # maps_tools_content_tokens is None
    session.state = {"maps_tools_content_tokens": None}
    _add_maps_tools_tokens_to_part(part, session)
    self.assertIsNone(part.root.metadata)

  def test_add_tokens_with_metadata_none(self):
    part = mock.MagicMock()
    part.root.metadata = None

    session = mock.MagicMock()
    session.state = {"maps_tools_content_tokens": ["token_1", "token_2"]}

    _add_maps_tools_tokens_to_part(part, session)
    self.assertEqual(
        part.root.metadata,
        {"maps_tools_content_tokens": ["token_1", "token_2"]},
    )

  def test_add_tokens_with_existing_metadata(self):
    part = mock.MagicMock()
    part.root.metadata = {"existing_field": "existing_value"}

    session = mock.MagicMock()
    session.state = {"maps_tools_content_tokens": ["token_1"]}

    _add_maps_tools_tokens_to_part(part, session)
    self.assertEqual(
        part.root.metadata,
        {
            "existing_field": "existing_value",
            "maps_tools_content_tokens": ["token_1"],
        },
    )

  def test_add_tokens_with_none_root(self):
    part = mock.MagicMock()
    part.root = None

    session = mock.MagicMock()
    session.state = {"maps_tools_content_tokens": ["token_1"]}

    # Should not raise AttributeError
    _add_maps_tools_tokens_to_part(part, session)


if __name__ == "__main__":
  unittest.main()
