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

"""Intent Router using Native Vertex AI Structured Outputs."""

import enum
import logging
from typing import Any, Protocol, runtime_checkable

from google import genai
from google.genai import types

from template_registry import TemplateRegistry

logger = logging.getLogger(__name__)


@runtime_checkable
class IntentClassifier(Protocol):
  """Protocol defining the query intent classifier contract."""

  async def classify(self, query: str) -> tuple[str, str]:
    """Classifies user query intent.

    Args:
        query: User input query string.

    Returns:
        A tuple of (intent_str, cleaned_query).
    """
    raise NotImplementedError


class VertexIntentClassifier(IntentClassifier):
  """Native Vertex AI Intent Classifier using structured output."""

  def __init__(
      self,
      client: genai.Client,
      model_id: str = "gemini-3.5-flash-lite",
      thinking_budget: int = 0,
      registry: TemplateRegistry | None = None,
  ):
    self.client = client
    self.model_id = model_id.removeprefix("gemini/").removeprefix("models/")
    self.thinking_budget = thinking_budget
    self.registry = registry or TemplateRegistry()

  async def classify(self, query: str) -> tuple[str, str]:
    """Classifies user query intent using Vertex AI structured output.

    Args:
        query: User input query string.

    Returns:
        A tuple of (intent_str, cleaned_query).

    Raises:
        ValueError: If the model response is empty or cannot be parsed.
    """
    classification_schema = self.registry.router_classification
    config_kwargs: dict[str, Any] = {
        "system_instruction": self.registry.compile_router_instruction(),
        "response_mime_type": "application/json",
        "response_schema": classification_schema,
    }
    if self.thinking_budget > 0:
      config_kwargs["thinking_config"] = types.ThinkingConfig(
          thinking_budget=self.thinking_budget
      )

    response = await self.client.aio.models.generate_content(
        model=self.model_id,
        contents=query,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    if response.parsed is not None:
      classification = response.parsed
    elif response.text:
      classification = classification_schema.model_validate_json(response.text)
    else:
      raise ValueError("Empty or unparseable response from intent classifier.")

    intent_val = (
        classification.intent.value
        if isinstance(classification.intent, enum.Enum)
        else str(classification.intent)
    )
    return intent_val, classification.query


__all__ = [
    "IntentClassifier",
    "VertexIntentClassifier",
]
