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

import json
import unittest
from unittest import mock

from after_tools_callback import _add_maps_tools_tokens_to_part
from after_tools_callback import _extract_place_label
from after_tools_callback import _state_invocation_ids
from after_tools_callback import after_maps_tools_callback
from after_tools_callback import after_tools_callback
from after_tools_callback import enrich_search_places_with_routing
from after_tools_callback import extract_user_query
from templates.common import haversine_distance
from templates.common import is_superlative_proximity_query
from templates.common import sort_extracted_places_by_proximity
from templates.local_search.schema import LocalSearchExtractorSchema
from templates.nearby_places_depth.schema import NearbyPlacesDepthExtractorSchema


class TestAfterToolsCallback(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(_state_invocation_ids.clear)

  def test_after_tool_callback_aggregates_maps_tools_content_tokens(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    tool_response_1 = {
        "structuredContent": {"contentToken": "token_abc_123"},
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
        "structuredContent": {"contentToken": "token_def_456"},
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
        tool_response={"structuredContent": {"contentToken": "token_abc_123"}},
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_abc_123", "token_def_456"],
    )

  def test_after_tool_callback_keeps_tokens_only_for_one_prompt(self):
    """Verifies that content tokens are reset when invocation_id changes."""
    shared_state = {}
    prompt_1_context = mock.MagicMock()
    prompt_1_context.state = shared_state
    prompt_1_context.invocation_id = "prompt_1"

    after_tools_callback(
        tool=None,
        args={},
        tool_context=prompt_1_context,
        tool_response={"structuredContent": {"contentToken": "token_prompt_1"}},
    )
    self.assertEqual(
        shared_state.get("maps_tools_content_tokens"),
        ["token_prompt_1"],
    )

    # Second prompt with a new invocation_id resets tokens from the first prompt
    prompt_2_context = mock.MagicMock()
    prompt_2_context.state = shared_state
    prompt_2_context.invocation_id = "prompt_2"

    after_tools_callback(
        tool=None,
        args={},
        tool_context=prompt_2_context,
        tool_response={"structuredContent": {"contentToken": "token_prompt_2"}},
    )
    self.assertEqual(
        shared_state.get("maps_tools_content_tokens"),
        ["token_prompt_2"],
    )

    # Third prompt with no contentToken clears previous prompt's tokens
    prompt_3_context = mock.MagicMock()
    prompt_3_context.state = shared_state
    prompt_3_context.invocation_id = "prompt_3"

    after_tools_callback(
        tool=None,
        args={},
        tool_context=prompt_3_context,
        tool_response={"structuredContent": {}},
    )
    self.assertEqual(
        shared_state.get("maps_tools_content_tokens"),
        [],
    )

  def test_after_tool_callback_with_kwargs(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    after_tools_callback(
        tool="mock_tool",
        args={"query": "test"},
        tool_context=mock_tool_context,
        tool_response={"structuredContent": {"contentToken": "token_xyz"}},
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
        tool_response={"structuredContent": {"contentToken": "token_1"}},
    )
    self.assertIsNone(result)

    # tool_context with state=None
    mock_context_no_state = mock.MagicMock()
    mock_context_no_state.state = None
    result = after_maps_tools_callback(
        tool_context=mock_context_no_state,
        tool_response={"structuredContent": {"contentToken": "token_1"}},
    )
    self.assertIsNone(result)

    # tool_context without state attribute
    class DummyContext:
      pass

    result = after_maps_tools_callback(
        tool_context=DummyContext(),
        tool_response={"structuredContent": {"contentToken": "token_1"}},
    )
    self.assertIsNone(result)

  def test_after_maps_tools_callback_invalid_token_values(self):
    mock_tool_context = mock.MagicMock()
    mock_tool_context.state = {}

    # None token
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"structuredContent": {"contentToken": None}},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Empty string token
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"structuredContent": {"contentToken": ""}},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Non-string token (int)
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"structuredContent": {"contentToken": 12345}},
    )
    self.assertEqual(mock_tool_context.state, {})

    # Missing contentToken key
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
        tool_response={"structuredContent": {"contentToken": "token_1"}},
    )
    self.assertEqual(
        mock_tool_context.state.get("maps_tools_content_tokens"),
        ["token_1"],
    )

    # If state['maps_tools_content_tokens'] is None
    mock_tool_context.state = {"maps_tools_content_tokens": None}
    after_maps_tools_callback(
        tool_context=mock_tool_context,
        tool_response={"structuredContent": {"contentToken": "token_2"}},
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


class TestExtractPlaceLabel(unittest.TestCase):
  """Unit tests for _extract_place_label following real PlaceView schema."""

  def test_extract_place_label_from_attribution_title_with_suffix(self):
    place = {"attribution": {"title": "Pike Place Chowder - Google Maps"}}
    self.assertEqual(_extract_place_label(place), "Pike Place Chowder")

  def test_extract_place_label_from_attribution_title_without_suffix(self):
    place = {"attribution": {"title": "Space Needle"}}
    self.assertEqual(_extract_place_label(place), "Space Needle")

  def test_extract_place_label_from_display_name_text(self):
    place = {"displayName": {"text": "Local Cafe"}}
    self.assertEqual(_extract_place_label(place), "Local Cafe")

  def test_extract_place_label_from_name(self):
    place = {"name": "Gas Works Park"}
    self.assertEqual(_extract_place_label(place), "Gas Works Park")

  def test_extract_place_label_from_id_or_place(self):
    place1 = {"id": "ChIJ_12345"}
    self.assertEqual(_extract_place_label(place1), "ChIJ_12345")
    place2 = {"place": "ChIJ_67890"}
    self.assertEqual(_extract_place_label(place2), "ChIJ_67890")

  def test_extract_place_label_fallback_to_default(self):
    self.assertEqual(_extract_place_label({}), "Place")


class TestProximityEnrichmentAndRouting(unittest.TestCase):
  """Unit tests for proximity calculation, query classification, and routing."""

  def setUp(self):
    super().setUp()
    self.addCleanup(_state_invocation_ids.clear)

  def test_haversine_distance_accuracy(self):
    """Verifies Haversine distance accuracy between known coordinates."""
    # Space Needle (47.6205, -122.3493) to Pike Place (47.6085, -122.3400)
    # is approximately 1500m.
    p1 = (47.6205, -122.3493)
    p2 = (47.6085, -122.3400)
    dist = haversine_distance(p1, p2)
    self.assertAlmostEqual(dist, 1500, delta=200)
    # Zero distance to self
    self.assertEqual(haversine_distance(p1, p1), 0.0)

  def test_is_superlative_proximity_query_positive_matches(self):
    """Verifies superlative proximity query keyword matching for nearest/closest."""
    self.assertTrue(is_superlative_proximity_query("nearest coffee shop"))
    self.assertTrue(
        is_superlative_proximity_query("Find the closest gas station")
    )
    self.assertTrue(
        is_superlative_proximity_query("Which pharmacy is nearest?")
    )
    self.assertTrue(is_superlative_proximity_query("CLOSEST park near me"))

  def test_is_superlative_proximity_query_negative_matches(self):
    """Verifies non-superlative queries never trigger superlative sorting."""
    self.assertFalse(is_superlative_proximity_query("best coffee shop nearby"))
    self.assertFalse(is_superlative_proximity_query("top rated restaurants"))
    self.assertFalse(is_superlative_proximity_query("highest rated hotels"))
    self.assertFalse(is_superlative_proximity_query("nearby attractions"))
    self.assertFalse(is_superlative_proximity_query(""))
    self.assertFalse(is_superlative_proximity_query(None))

  def test_extract_user_query_from_state_dict(self):
    ctx = mock.MagicMock()
    ctx.state = {"user_query": "find nearest coffee"}
    self.assertEqual(extract_user_query(ctx), "find nearest coffee")

  def test_extract_user_query_from_target_intent_user_content(self):
    ctx = mock.MagicMock()
    ctx.state = {}
    part = mock.MagicMock()
    part.text = (
        "[TARGET_INTENT: NEARBY_PLACES_DEPTH]\nFind closest pharmacy near"
        " 47.6205, -122.3493"
    )
    ctx.user_content.parts = [part]
    self.assertEqual(
        extract_user_query(ctx),
        "Find closest pharmacy near 47.6205, -122.3493",
    )

  def test_extract_user_query_none_or_empty_context(self):
    self.assertEqual(extract_user_query(None), "")
    ctx = mock.MagicMock()
    ctx.state = {}
    ctx.user_content = None
    self.assertEqual(extract_user_query(ctx), "")

  def test_enrich_search_places_with_routing_deterministic_fallback(self):
    """Verifies deterministic road-adjusted Haversine routing fallback."""
    origin = (47.6205, -122.3493)  # Space Needle
    tool_response = {
        "structuredContent": {
            "places": [
                {
                    "name": "Far Place",
                    "location": {"latitude": 47.7000, "longitude": -122.3493},
                },
                {
                    "name": "Near Place",
                    "location": {"latitude": 47.6220, "longitude": -122.3493},
                },
            ]
        }
    }
    changed = enrich_search_places_with_routing(
        tool_response,
        origin,
        sort_closest_first=True,
    )
    self.assertTrue(changed)
    places = tool_response["structuredContent"]["places"]
    self.assertEqual(places[0]["name"], "Near Place")
    self.assertEqual(places[1]["name"], "Far Place")
    self.assertIn("distanceFromQueryLocation", places[0])
    self.assertIn("travelTimeFromQueryLocation", places[0])
    self.assertIn("mi", places[0]["distanceFromQueryLocation"])
    self.assertIn("mins walk", places[0]["travelTimeFromQueryLocation"])

  def test_enrich_search_places_preserves_summary_and_remaps_citations(self):
    """Verifies structuredContent.summary preserves existing text and appends block."""
    origin = (47.6205, -122.3493)
    tool_response = {
        "content": [{"text": "original text"}],
        "structuredContent": {
            "summary": "Check out [0] and [1] in downtown.",
            "places": [
                {
                    "attribution": {"title": "Far Place - Google Maps"},
                    "location": {"latitude": 47.7000, "longitude": -122.3493},
                },
                {
                    "attribution": {"title": "Near Place - Google Maps"},
                    "location": {"latitude": 47.6220, "longitude": -122.3493},
                },
            ],
        },
    }
    enrich_search_places_with_routing(
        tool_response,
        origin,
        sort_closest_first=True,
    )
    structured_content = tool_response["structuredContent"]
    summary = structured_content["summary"]
    # [0] (Far Place) was swapped to index [1]; [1] (Near Place) moved to [0]
    self.assertTrue(summary.startswith("Check out [1] and [0] in downtown."))
    self.assertIn("\n\nProximity from origin:\n", summary)
    self.assertIn("- **Near Place**:", summary)
    self.assertIn("- **Far Place**:", summary)
    # content[0].text is also updated
    self.assertEqual(tool_response["content"][0]["text"], summary)

  def test_enrich_search_places_updates_content_text_when_not_sorted(self):
    """Verifies proximity block and content text are updated when sort_closest_first is False."""
    origin = (47.6205, -122.3493)
    tool_response = {
        "content": [{"text": "original text"}],
        "structuredContent": {
            "summary": "Places found near you.",
            "places": [
                {
                    "attribution": {"title": "Place A - Google Maps"},
                    "location": {"latitude": 47.6210, "longitude": -122.3493},
                },
            ],
        },
    }
    enrich_search_places_with_routing(
        tool_response,
        origin,
        sort_closest_first=False,
    )
    summary = tool_response["structuredContent"]["summary"]
    self.assertTrue(summary.startswith("Places found near you."))
    self.assertIn("Proximity from origin:\n- **Place A**:", summary)
    self.assertEqual(tool_response["content"][0]["text"], summary)

  def test_enrich_search_places_preserves_json_serialized_content_text(self):
    """Verifies content text containing serialized JSON places is preserved with enriched metrics."""
    origin = (47.6205, -122.3493)
    initial_structured = {
        "summary": "Two places nearby.",
        "places": [{
            "id": "ChIJ_place1",
            "attribution": {"title": "Place One"},
            "location": {"latitude": 47.6210, "longitude": -122.3493},
        }],
    }
    tool_response = {
        "content": [{"text": json.dumps(initial_structured)}],
        "structuredContent": initial_structured,
    }
    enrich_search_places_with_routing(
        tool_response,
        origin,
        sort_closest_first=False,
    )
    # content[0].text remains valid JSON containing places and enriched fields
    parsed_json = json.loads(tool_response["content"][0]["text"])
    self.assertIn("places", parsed_json)
    self.assertEqual(parsed_json["places"][0]["id"], "ChIJ_place1")
    self.assertIn("distanceFromQueryLocation", parsed_json["places"][0])

  def test_enrich_search_places_with_custom_route_matrix_fn(self):
    """Verifies custom route_matrix_fn provides travel metrics and handles failures."""
    origin = (47.6205, -122.3493)
    tool_response = {
        "structuredContent": {
            "places": [{
                "name": "Custom Place",
                "location": {"latitude": 47.6210, "longitude": -122.3493},
            }]
        }
    }

    def mock_route_matrix(orig, dests):
      del orig, dests
      return [{
          "distanceMeters": 800.0,
          "walkMinutes": 10,
          "driveMinutes": 2,
      }]

    enrich_search_places_with_routing(
        tool_response,
        origin,
        route_matrix_fn=mock_route_matrix,
    )
    p0 = tool_response["structuredContent"]["places"][0]
    self.assertEqual(
        p0["travelTimeFromQueryLocation"], "10 mins walk, 2 mins drive"
    )

    # Failing route_matrix_fn falls back to deterministic road-adjusted
    # Haversine distance estimation.
    def failing_route_matrix(orig, dests):
      del orig, dests
      raise RuntimeError("Network error")

    enrich_search_places_with_routing(
        tool_response,
        origin,
        route_matrix_fn=failing_route_matrix,
    )
    self.assertIn("distanceFromQueryLocation", p0)

  def test_after_maps_tools_callback_ignores_non_search_places_tool(self):
    """Verifies tools other than search_places (e.g.

    search_along_route) are skipped.
    """
    ctx = mock.MagicMock()
    ctx.state = {}
    mock_tool = mock.MagicMock()
    mock_tool.name = "search_along_route"
    resp = {
        "structuredContent": {
            "places": [{
                "name": "Ignored Place",
                "location": {"latitude": 47.6210, "longitude": -122.3493},
            }]
        }
    }
    after_maps_tools_callback(ctx, resp, tool=mock_tool, args={})
    # Proximity enrichment is not executed for search_along_route
    self.assertNotIn(
        "distanceFromQueryLocation", resp["structuredContent"]["places"][0]
    )

  def test_after_maps_tools_callback_pending_place_responses_retroactive_flush(
      self,
  ):
    """Verifies multi-place search without anchor is flushed once anchor arrives."""
    ctx = mock.MagicMock()
    ctx.state = {}
    ctx.invocation_id = "inv_pending"

    multi_resp = {
        "structuredContent": {
            "places": [
                {
                    "name": "P1",
                    "location": {"latitude": 47.6210, "longitude": -122.3493},
                },
                {
                    "name": "P2",
                    "location": {"latitude": 47.6220, "longitude": -122.3493},
                },
            ]
        }
    }
    # Turn 1: multi-place query without origin -> saved to
    # _pending_place_responses
    after_maps_tools_callback(ctx, multi_resp, tool=None, args={})
    self.assertEqual(len(ctx.state["_pending_place_responses"]), 1)
    self.assertNotIn(
        "distanceFromQueryLocation",
        multi_resp["structuredContent"]["places"][0],
    )

    # Turn 2: 1-place anchor arrives in same turn -> flushes pending and
    # sets anchor
    anchor_resp = {
        "structuredContent": {
            "places": [{
                "name": "Space Needle Anchor",
                "location": {"latitude": 47.6205, "longitude": -122.3493},
            }]
        }
    }
    after_maps_tools_callback(ctx, anchor_resp, tool=None, args={})
    self.assertEqual(ctx.state["last_anchor_location"], (47.6205, -122.3493))
    # Pending responses flushed and enriched with anchor coordinates
    self.assertEqual(len(ctx.state["_pending_place_responses"]), 0)
    self.assertIn(
        "distanceFromQueryLocation",
        multi_resp["structuredContent"]["places"][0],
    )

  def test_bound_state_invocation_ids_and_rollover(self):
    """Verifies FIFO bounding at 1024 entries and state rollover clearing."""
    _state_invocation_ids.clear()
    for i in range(1025):
      _state_invocation_ids[i] = f"inv_{i}"
    self.assertGreater(len(_state_invocation_ids), 1024)

    state_dict = {"last_anchor_location": (47.6205, -122.3493)}
    ctx = mock.MagicMock()
    ctx.state = state_dict
    ctx.invocation_id = "new_inv"

    after_maps_tools_callback(ctx, {})
    self.assertLessEqual(len(_state_invocation_ids), 1024)

    # Rollover clears last_anchor_location
    ctx.invocation_id = "another_inv"
    after_maps_tools_callback(ctx, {})
    self.assertNotIn("last_anchor_location", state_dict)

  def test_concurrent_sessions_state_isolation(self):
    """Verifies two concurrent sessions store pending place responses independently."""
    ctx1 = mock.MagicMock()
    ctx1.state = {}
    ctx1.invocation_id = "session_1_inv"

    ctx2 = mock.MagicMock()
    ctx2.state = {}
    ctx2.invocation_id = "session_2_inv"

    resp1 = {
        "structuredContent": {
            "places": [
                {
                    "name": "P1",
                    "location": {"latitude": 47.6205, "longitude": -122.3493},
                },
                {
                    "name": "P2",
                    "location": {"latitude": 47.6210, "longitude": -122.3493},
                },
            ]
        }
    }
    resp2 = {
        "structuredContent": {
            "places": [
                {
                    "name": "P3",
                    "location": {"latitude": 40.7128, "longitude": -74.0060},
                },
                {
                    "name": "P4",
                    "location": {"latitude": 40.7130, "longitude": -74.0060},
                },
            ]
        }
    }

    # Session 1 receives multi-place search without anchor
    after_maps_tools_callback(ctx1, resp1, tool=None, args={})
    # Session 2 receives multi-place search without anchor
    after_maps_tools_callback(ctx2, resp2, tool=None, args={})

    self.assertIn(resp1, ctx1.state.get("_pending_place_responses", []))
    self.assertNotIn(resp2, ctx1.state.get("_pending_place_responses", []))
    self.assertIn(resp2, ctx2.state.get("_pending_place_responses", []))
    self.assertNotIn(resp1, ctx2.state.get("_pending_place_responses", []))

  def test_anchor_location_bias_camel_and_snake_case(self):
    """Verifies locationBias and location_bias circle center coordinates are parsed."""
    ctx = mock.MagicMock()
    ctx.state = {}
    ctx.invocation_id = "inv_bias"

    resp = {
        "structuredContent": {
            "places": [
                {
                    "name": "P1",
                    "location": {"latitude": 47.6220, "longitude": -122.3493},
                },
                {
                    "name": "P2",
                    "location": {"latitude": 47.6240, "longitude": -122.3493},
                },
            ]
        }
    }

    # camelCase locationBias
    args_camel = {
        "locationBias": {
            "circle": {"center": {"latitude": 47.6205, "longitude": -122.3493}}
        }
    }
    after_maps_tools_callback(ctx, resp, tool=None, args=args_camel)
    self.assertIn(
        "distanceFromQueryLocation", resp["structuredContent"]["places"][0]
    )

    # snake_case location_bias
    resp_snake = {
        "structuredContent": {
            "places": [
                {
                    "name": "P3",
                    "location": {"latitude": 47.6220, "longitude": -122.3493},
                },
                {
                    "name": "P4",
                    "location": {"latitude": 47.6240, "longitude": -122.3493},
                },
            ]
        }
    }
    args_snake = {
        "location_bias": {
            "circle": {"center": {"latitude": 47.6205, "longitude": -122.3493}}
        }
    }
    after_maps_tools_callback(ctx, resp_snake, tool=None, args=args_snake)
    self.assertIn(
        "distanceFromQueryLocation",
        resp_snake["structuredContent"]["places"][0],
    )

  def test_single_place_anchor_non_overwrite(self):
    """Verifies existing last_anchor_location is not overwritten by subsequent 1-place search."""
    ctx = mock.MagicMock()
    ctx.state = {"last_anchor_location": (47.6205, -122.3493)}
    ctx.invocation_id = "inv_anchor"

    single_place_resp = {
        "structuredContent": {
            "places": [{
                "name": "Subsequent Place",
                "location": {"latitude": 47.7000, "longitude": -122.3493},
            }]
        }
    }
    after_maps_tools_callback(ctx, single_place_resp, tool=None, args={})
    # last_anchor_location remains the original (47.6205, -122.3493)
    self.assertEqual(ctx.state["last_anchor_location"], (47.6205, -122.3493))

  def test_single_place_within_15m_self_anchor_not_enriched(self):
    """Verifies 1-place response within 15m of explicit origin is treated as anchor and not enriched."""
    origin = (47.6205, -122.3493)
    ctx = mock.MagicMock()
    ctx.state = {}
    ctx.invocation_id = "inv_self"

    single_place_resp = {
        "structuredContent": {
            "places": [{
                "name": "Space Needle Anchor",
                "location": {"latitude": 47.6205, "longitude": -122.3493},
            }]
        }
    }
    args = {
        "locationBias": {
            "circle": {
                "center": {"latitude": origin[0], "longitude": origin[1]}
            }
        }
    }
    after_maps_tools_callback(ctx, single_place_resp, tool=None, args=args)
    # Since distance is 0.0m (< 15.0m), it should not be enriched as destination
    p0 = single_place_resp["structuredContent"]["places"][0]
    self.assertNotIn("distanceFromQueryLocation", p0)


class TestSortExtractedPlacesByProximity(unittest.TestCase):
  """Unit tests for sort_extracted_places_by_proximity and schema integration."""

  def test_sort_extracted_places_by_proximity_superlative(self):
    """Verifies sorting places closest first and reordering summary bullets."""

    class MockPlace:

      def __init__(self, name, lat, lng):
        self.name = name
        self.lat = lat
        self.lng = lng

    class MockModel:

      def __init__(self, places, summary=None, anchor_marker=None):
        self.places = places
        self.summary = summary
        self.anchor_marker = anchor_marker

    origin = (47.6205, -122.3493)  # Space Needle
    p_far = MockPlace("Joe's (24/7) [Cafe+]", 47.7000, -122.3493)
    p_near = MockPlace("Near Coffee", 47.6220, -122.3493)
    summary = (
        "- Joe's (24/7) [Cafe+]: A great cafe\n- Near Coffee: Quick espresso"
    )

    model = MockModel([p_far, p_near], summary=summary)
    query = f"Find the nearest cafe to {origin[0]}, {origin[1]}"

    res = sort_extracted_places_by_proximity(model, query)
    self.assertEqual(res.places[0].name, "Near Coffee")
    self.assertEqual(res.places[1].name, "Joe's (24/7) [Cafe+]")
    self.assertTrue(res.summary.startswith("- Near Coffee:"))

  def test_sort_extracted_places_fail_open_on_mismatch_or_non_superlative(self):
    """Verifies fail-open behavior when summary bullets do not match places."""

    class MockPlace:

      def __init__(self, name, lat, lng):
        self.name = name
        self.lat = lat
        self.lng = lng

    class MockModel:

      def __init__(self, places, summary=None):
        self.places = places
        self.summary = summary

    p1 = MockPlace("Cafe 1", 47.7000, -122.3493)
    p2 = MockPlace("Cafe 2", 47.6220, -122.3493)
    summary = "- Cafe 1: info"

    model = MockModel([p1, p2], summary=summary)
    res = sort_extracted_places_by_proximity(model, "best cafes")
    self.assertEqual(res.places[0].name, "Cafe 1")
    self.assertEqual(res.summary, summary)

    res2 = sort_extracted_places_by_proximity(
        model, "nearest cafes near 47.6205, -122.3493"
    )
    self.assertEqual(res2.places[0].name, "Cafe 2")
    self.assertEqual(res2.summary, summary)

  def test_sort_extracted_places_with_local_search_extractor_schema(self):
    """Verifies sort_extracted_places_by_proximity with real LocalSearchExtractorSchema."""
    schema = LocalSearchExtractorSchema(
        heading="Burger places near you",
        places=[
            {
                "placeId": "place_far",
                "name": "Far Burger",
                "lat": 47.7000,
                "lng": -122.3493,
            },
            {
                "placeId": "place_near",
                "name": "Near Burger",
                "lat": 47.6220,
                "lng": -122.3493,
            },
        ],
        summary=(
            "- **Far Burger**: Gourmet burgers [cite:1]\n"
            "- **Near Burger**: Fast smashburgers [cite:2]"
        ),
    )
    query = "closest burgers near 47.6205, -122.3493"
    res = sort_extracted_places_by_proximity(schema, query)
    self.assertEqual(res.places[0].name, "Near Burger")
    self.assertEqual(res.places[1].name, "Far Burger")
    self.assertIn("[cite:1]", res.summary.splitlines()[0])
    self.assertIn("[cite:2]", res.summary.splitlines()[1])

  def test_sort_extracted_places_with_nearby_places_depth_extractor_schema(
      self,
  ):
    """Verifies sort_extracted_places_by_proximity with NearbyPlacesDepthExtractorSchema."""
    schema = NearbyPlacesDepthExtractorSchema(
        heading="Bistros near you",
        places=[
            {
                "placeId": "p_far",
                "name": "Far Bistro",
                "lat": 47.7000,
                "lng": -122.3493,
                "description": (
                    "**Far Bistro** (4.5★) fine dining [cite:1]\n\n* **Standout"
                    " feature**: Ambiance\n* **Logistics**: 4 miles"
                ),
            },
            {
                "placeId": "p_near",
                "name": "Near Bistro",
                "lat": 47.6220,
                "lng": -122.3493,
                "description": (
                    "**Near Bistro** (4.8★) cozy dining [cite:2]\n\n*"
                    " **Standout feature**: Quick seating\n* **Logistics**: 0.2"
                    " miles"
                ),
            },
        ],
        summary="Top dining options in the area.",
    )
    query = "nearest bistro near 47.6205, -122.3493"
    res = sort_extracted_places_by_proximity(schema, query)
    self.assertEqual(res.places[0].name, "Near Bistro")
    self.assertEqual(res.places[1].name, "Far Bistro")
    # Verify [cite:N] remapping inside place.description
    self.assertIn("[cite:1]", res.places[0].description)
    self.assertIn("[cite:2]", res.places[1].description)


if __name__ == "__main__":
  unittest.main()
