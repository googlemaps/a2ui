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


@dataclasses.dataclass(frozen=True)
class AgentConfig:
  """Configuration parameters for template-based MAUI Agent.

  Attributes:
      max_list_size: Max number of place elements returned in layout updates.
      router_model: Model used for query intent routing.
      template_model: Model used for template parameter extraction.
      generic_model: Model used for unconstrained dynamic UI generation.
      router_thinking_budget: Thinking budget for routing model.
      extractor_thinking_budget: Thinking budget for extraction model.
      fallback_mode: Fallback strategy when specialized template extraction is
        not used or fails (e.g. for unsupported intents or validation failures).
  """

  max_list_size: int = 5
  router_model: str = "gemini/gemini-3.1-flash-lite"
  template_model: str = "gemini/gemini-3.1-flash-lite"
  generic_model: str = "gemini/gemini-3-flash-preview"
  router_thinking_budget: int = 0
  extractor_thinking_budget: int = 0
  fallback_mode: FallbackMode = FallbackMode.TEXT

  def __post_init__(self):
    if not isinstance(self.fallback_mode, FallbackMode):
      try:
        object.__setattr__(
            self, "fallback_mode", FallbackMode(self.fallback_mode)
        )
      except ValueError:
        raise ValueError(
            f"Invalid fallback_mode: {self.fallback_mode}. Must be one of"
            " FallbackMode values."
        )
