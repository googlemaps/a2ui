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

"""After-tool callback for grounding tools in MAUI Agent."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tracks the current prompt invocation_id per underlying state dictionary so
# maps_tools_content_tokens is only kept in tool_context for a single prompt.
_state_invocation_ids: dict[int, Any] = {}


def after_tools_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
    **kwargs: Any,
) -> Any:
  """Callback to aggregate grounding_content_token into session state."""
  # pylint: disable=unused-argument
  after_maps_tools_callback(tool_context, tool_response)

  return None


def after_maps_tools_callback(
    tool_context: Any,
    tool_response: Any,
) -> Any:
  """Callback to aggregate content tokens from Maps Tools for one prompt."""
  # pylint: disable=unused-argument
  if tool_context is None or getattr(tool_context, "state", None) is None:
    return None

  # 1. Reset collected tokens when a new prompt turn (invocation_id) starts.
  state_obj = getattr(tool_context.state, "_value", tool_context.state)
  state_id = id(state_obj)
  invocation_id = getattr(tool_context, "invocation_id", None)
  if invocation_id is not None:
    if (
        state_id in _state_invocation_ids
        and _state_invocation_ids[state_id] != invocation_id
    ):
      if "maps_tools_content_tokens" in tool_context.state:
        tool_context.state["maps_tools_content_tokens"] = {}
    _state_invocation_ids[state_id] = invocation_id

  if not tool_response or not isinstance(tool_response, dict):
    return None

  # 2. Extract contentToken from the Maps Grounding Lite MCP tool response.
  structured_content = tool_response.get("structuredContent")
  if not isinstance(structured_content, dict):
    return None
  token = structured_content.get("contentToken")
  places = structured_content.get("places")
  results = structured_content.get("results")
  if isinstance(places, list):
    # SearchTextResponse
    entities = places
  elif isinstance(results, list):
    # SearchAlongRouteResponse
    entities = [r.get("place") or r for r in results if isinstance(r, dict)]
  else:
    entities = []

  if isinstance(token, str) and token:
    content_tokens = tool_context.state.get("maps_tools_content_tokens", {})
    # If content_tokens is not a dict, initialize it to an empty dict.
    if not isinstance(content_tokens, dict):
      content_tokens = {}
    if not entities:
      # Add token to the empty string key if there are no entities to support
      # other types of responses.
      fallback_tokens = content_tokens.setdefault("", [])
      if token not in fallback_tokens:
        fallback_tokens.append(token)
    else:
      for entity in entities:
        if isinstance(entity, dict):
          place_id = entity.get("id")
          if isinstance(place_id, str) and place_id:
            content_tokens[place_id] = token
    if content_tokens:
      tool_context.state["maps_tools_content_tokens"] = content_tokens
      logger.info(
          "--- after_maps_tools_callback: Aggregated content token into"
          " content_tokens. ---"
      )

  return None


def add_maps_tools_tokens_to_part(part: Any, session: Any) -> None:
  """Adds maps_tools_content_tokens from session state to part metadata."""
  if session is None or getattr(session, "state", None) is None:
    return
  maps_tools_content_tokens = session.state.get("maps_tools_content_tokens")
  if maps_tools_content_tokens:
    if getattr(part, "root", None) is not None:
      if getattr(part.root, "metadata", None) is None:
        part.root.metadata = {}
      part.root.metadata["maps_tools_content_tokens"] = (
          maps_tools_content_tokens
      )
