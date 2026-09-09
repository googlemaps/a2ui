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

import logging
import re
from typing import Any, Protocol, runtime_checkable

from google import genai
from google.genai import types

from template_registry import INTENT_OTHER_SPATIAL, INTENT_TEXT_ONLY, TemplateRegistry

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
      project_id: str | None = None,
      location: str = "global",
      model_id: str = "gemini-3.5-flash-lite",
      client: genai.Client | None = None,
      thinking_budget: int = 0,
      registry: TemplateRegistry | None = None,
  ):
    if not project_id and client is None:
      raise ValueError(
          "Vertex AI project_id must be provided when client is not supplied."
      )
    self.project_id = project_id
    self.location = location
    self.model_id = model_id.removeprefix("gemini/").removeprefix("models/")
    self.thinking_budget = thinking_budget
    self._client = client
    self.registry = registry or TemplateRegistry()

  @property
  def client(self) -> genai.Client:
    """Lazily initializes the Vertex genai Client."""
    if self._client is None:
      self._client = genai.Client(
          vertexai=True,
          project=self.project_id,
          location=self.location,
      )
    return self._client

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
      text = response.text.strip()
      if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
      classification = classification_schema.model_validate_json(text)
    else:
      raise ValueError("Empty or unparseable response from intent classifier.")

    raw_intent = getattr(classification, "intent", "")
    intent_val = (
        raw_intent.value if hasattr(raw_intent, "value") else str(raw_intent)
    )
    cleaned_query = getattr(classification, "query", query)
    return intent_val, cleaned_query


__all__ = [
    "IntentClassifier",
    "VertexIntentClassifier",
]
