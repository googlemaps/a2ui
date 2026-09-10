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
"""Configuration for the Intent Router, including prompts and schemas."""

import enum
import re
from typing import Any

from google import genai
from google.genai import types
import pydantic


class IntentClass(str, enum.Enum):
  """Supported intent categories for routing."""

  LOCAL_SEARCH = "LOCAL_SEARCH"
  DIRECTIONS = "DIRECTIONS"
  OTHER_SPATIAL = "OTHER_SPATIAL"
  TEXT_ONLY = "TEXT_ONLY"


class RouterClassification(pydantic.BaseModel):
  """Schema for the classification output of the intent router."""

  intent: IntentClass = pydantic.Field(
      description="The classified intent archetype name."
  )
  query: str = pydantic.Field(description="The cleaned user query")


ROUTER_SYSTEM_INSTRUCTION = """
## Role
You are an expert query intent router.

## Task Definition
Analyze a user's input and classify it into the most appropriate intent category based on the structural complexity and data requirements of the request.

## Intent Archetypes
- **LOCAL_SEARCH**: Search for categories of interest, places, businesses, or points of interest within a specific geographic proximity.
- **DIRECTIONS**: Standard navigation, route directions, walking/driving/transit times, or navigation instructions between an origin and destination. This includes multi-stop routes and routes with specified waypoints.
- **OTHER_SPATIAL**: Queries requiring rich map-based visualization, boundaries, coordinates, specific geographic displays, or complex navigation combining routes with secondary overlays (e.g., weather, air quality forecasts, displaying all available charging stations along a route).
- **TEXT_ONLY**: General information retrieval, questions, or requests for data associated with locations that can be answered fully with text without requiring a map interface.

## Classification Policy: Conservative Routing
If a query satisfies the structure of a base intent (such as DIRECTIONS or LOCAL_SEARCH) but also includes any Auxiliary Data (e.g., weather forecasts, environmental factors), you MUST promote the classification to OTHER_SPATIAL.
Note: Simple multi-stop routes or routes with specified waypoints (e.g., "A to B via C") should be classified as DIRECTIONS, unless they require searching for stops along the way (e.g., "find coffee shops along the route") which requires LOCAL_SEARCH overlays and should be promoted to OTHER_SPATIAL.

## Few-shot Examples

### Example 1
**User Query:** "Find coffee shops near Central Park"
**Output:**
{
  "intent": "LOCAL_SEARCH",
  "query": "coffee shops near Central Park"
}

### Example 2
**User Query:** "Walking route from Central Park to Times Square, but show coffee shops and rain forecasts along the way"
**Output:**
{
  "intent": "OTHER_SPATIAL",
  "query": "walking route from Central Park to Times Square with coffee shop stops and rain forecast"
}

### Example 3
**User Query:** "show the boundary of Yosemite National Park on the map"
**Output:**
{
  "intent": "OTHER_SPATIAL",
  "query": "boundary of Yosemite National Park"
}

### Example 4
**User Query:** "Directions from Sacramento to Mendocino via Clear Lake"
**Output:**
{
  "intent": "DIRECTIONS",
  "query": "Directions from Sacramento to Mendocino via Clear Lake"
}
"""


class VertexIntentClassifier:
  """Native Vertex AI Intent Classifier using structured output."""

  def __init__(
      self,
      project_id: str | None = None,
      location: str = "global",
      model_id: str = "gemini-3.5-flash-lite",
      client: genai.Client | None = None,
      thinking_budget: int = 0,
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

  async def classify(self, query: str) -> tuple[IntentClass, str]:
    """Classifies user query intent using Vertex AI structured output.

    Args:
        query: User input query string.

    Returns:
        A tuple of (IntentClass, cleaned_query).

    Raises:
        ValueError: If the model response is empty or cannot be parsed.
    """
    config_kwargs: dict[str, Any] = {
        "system_instruction": ROUTER_SYSTEM_INSTRUCTION,
        "response_mime_type": "application/json",
        "response_schema": RouterClassification,
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
      if isinstance(response.parsed, RouterClassification):
        classification = response.parsed
      elif isinstance(response.parsed, dict):
        classification = RouterClassification(**response.parsed)
      else:
        classification = RouterClassification.model_validate(response.parsed)
    elif response.text:
      text = response.text.strip()
      if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
      classification = RouterClassification.model_validate_json(text)
    else:
      raise ValueError("Empty or unparseable response from intent classifier.")

    return classification.intent, classification.query
