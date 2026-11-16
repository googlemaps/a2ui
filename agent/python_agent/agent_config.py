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

"""Configuration schemas for MAUI Agent with templates."""

import dataclasses
import enum
from typing import Optional


class FallbackMode(str, enum.Enum):
  """Fallback strategy when template validation fails."""

  TEXT = "TEXT"
  DYNAMIC = "DYNAMIC"


class McpTierMode(str, enum.Enum):
  """MCP tier selection strategy for search_places tool calls."""

  DYNAMIC = "DYNAMIC"
  LITE_ONLY = "LITE_ONLY"
  PRO_ONLY = "PRO_ONLY"


@dataclasses.dataclass(frozen=True)
class AgentConfig:
  """Configuration parameters for template-based MAUI Agent.

  Attributes:
      max_list_size: Max number of place elements returned in layout updates
        (defaults to 10).
      router_model: Model used for query intent routing.
      template_model: Model used for template parameter extraction.
      generic_model: Model used for unconstrained dynamic UI generation.
      router_thinking_budget: Thinking budget for routing model.
      extractor_thinking_budget: Thinking budget for extraction model.
      fallback_mode: Fallback strategy when specialized template extraction is
        not used or fails (e.g. for unsupported intents or validation failures).
      mcp_tier_mode: MCP tier selection policy (`DYNAMIC`, `LITE_ONLY`, or
        `PRO_ONLY`) controlling how `search_places` requests up to 10 places vs.
        parallel 5-place calls. Defaults to `DYNAMIC`.
      enable_search_grounding: Whether to enable Google Search grounding
        alongside Google Maps in Vertex AI. Defaults to True.
  """

  max_list_size: int = 10
  router_model: str = "gemini/gemini-3.5-flash-lite"
  template_model: str = "gemini/gemini-3.5-flash-lite"
  generic_model: str = "gemini/gemini-3.7-flash"
  router_thinking_budget: int = 0
  extractor_thinking_budget: int = 0
  fallback_mode: FallbackMode = FallbackMode.TEXT
  mcp_tier_mode: McpTierMode = McpTierMode.DYNAMIC
  enable_search_grounding: bool = True

  def __post_init__(self):
    if not isinstance(self.fallback_mode, FallbackMode):
      try:
        object.__setattr__(
            self, "fallback_mode", FallbackMode(self.fallback_mode)
        )
      except ValueError as exc:
        raise ValueError(
            f"Invalid fallback_mode: {self.fallback_mode}. Must be one of"
            " FallbackMode values."
        ) from exc
    if not isinstance(self.mcp_tier_mode, McpTierMode):
      try:
        object.__setattr__(
            self, "mcp_tier_mode", McpTierMode(self.mcp_tier_mode)
        )
      except ValueError as exc:
        raise ValueError(
            f"Invalid mcp_tier_mode: {self.mcp_tier_mode}. Must be one of"
            " McpTierMode values."
        ) from exc
