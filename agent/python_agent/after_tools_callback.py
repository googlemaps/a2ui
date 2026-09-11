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

# Maximum number of recent content tokens to retain in session state.
#
# Trade-offs / Considerations:
# - Pros of larger values:
#     - Retains grounding tokens across longer multi-turn conversations where
#       older tool calls returned entities that are still referenced or
#       rendered in UI widgets.
#     - Prevents premature eviction of valid tokens, ensuring Place Widget
#       requests can successfully waive billing even after multiple subsequent
#       tool turns.
# - Cons of larger values:
#     - Increases session state size and payload memory footprint across
#       requests.
#     - Increases serialized metadata size attached to message parts and RPCs.
#     - Adds backend processing overhead when downstream services must decrypt
#       and validate a larger list of candidate tokens.
#     - Since tokens have an expiration TTL (e.g. 30 minutes), retaining too
#       many historical tokens increases stale/expired tokens in the payload.
MAX_CONTENT_TOKENS: int = 10


def after_tools_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
    **kwargs: Any,
) -> Any:
  """Callback to aggregate grounding_content_token into session state."""
  # pylint: disable=unused-argument
  if not tool_response or not isinstance(tool_response, dict):
    return None

  after_maps_tools_callback(tool_context, tool_response)

  return None


def after_maps_tools_callback(
    tool_context: Any,
    tool_response: Any,
) -> Any:
  """Callback to aggregate content_token from Maps Tools into session state."""
  # pylint: disable=unused-argument
  if tool_context is None or getattr(tool_context, "state", None) is None:
    return None

  token = tool_response.get("content_token")
  if isinstance(token, str) and token:
    content_tokens = tool_context.state.get("maps_tools_content_tokens", [])
    # If content_tokens is not a list, initialize it to an empty list.
    if not isinstance(content_tokens, list):
      content_tokens = []
    if token not in content_tokens:
      content_tokens.append(token)
    # Keep only the last MAX_CONTENT_TOKENS tokens.
    if len(content_tokens) > MAX_CONTENT_TOKENS:
      content_tokens = content_tokens[-MAX_CONTENT_TOKENS:]
    tool_context.state["maps_tools_content_tokens"] = content_tokens
    logger.info(
        "--- after_maps_tools_callback: Aggregated content token into"
        " content_tokens. ---"
    )

  return None


def _add_maps_tools_tokens_to_part(part: Any, session: Any) -> None:
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
