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

"""Place ID resolution shared by the grounded agents.

Grounding with Google Maps does not let the model see real Place IDs while it
is generating, and asking it to recall them from parametric memory produces
wrong IDs. Instead the system instruction tells the model to emit a
placeholder, and this module rewrites those placeholders using the Place
IDs that Grounding actually returned.

Both `agent_with_grounding` (free-form A2UI) and `vertex_grounding_extractor`
(template parameters) use this module so the two paths cannot drift apart.

Placeholder format, which the prompt and this module must agree on exactly:

    PLACE_ID_FOR_{count}_{title}

`title` is the Maps source title with the " - Google Maps" branding suffix
removed, in its original casing. `count` is the 1-based occurrence index of
the source within that title, so five sources sharing a title get placeholders
1 through 5.
"""

import collections
import dataclasses
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

PLACEHOLDER_PREFIX = "PLACE_ID_FOR_"

# Kept beside the parser on purpose. The placeholder format is a contract
# between this module and the model, and a prompt edit that drifts from
# build_placeholder_index fails silently: every key misses and raw
# placeholders ship to the client.
PROMPT_RULES = """PLACE ID GENERATION RULES:
You do not have access to real placeIds. Whenever a `placeId` is required, you MUST generate a synthetic placeholder using the following rules:
- Format: "PLACE_ID_FOR_{Count}_{Exact Title}"
- Example: If the tool returns a place named "Chez Panisse", use "PLACE_ID_FOR_1_Chez Panisse". If it returns a second "Chez Panisse", use "PLACE_ID_FOR_2_Chez Panisse".
- STRICT MATCHING: Do NOT change any characters, spaces, capitalization, or punctuation from the title returned by the tool.
- COUNTING: Always prepend the occurrence count (starting at 1) for each title based on the order they were returned by the tool, even if the title only occurs once."""

_BRANDED_TITLE_SUFFIX = " - Google Maps"

# Slicing at len(prefix) - 3 keeps the "ChI" that every Place ID starts with.
_PREFIXED_PLACE_ID = "places/ChI"


@dataclasses.dataclass(frozen=True)
class AttributionSource:
  """A Maps attribution source from grounding metadata."""

  title: str
  place_id: str


def normalize_place_id(raw_place_id: str) -> str:
  """Strips the 'places/' resource prefix, which A2UI components do not want."""
  if raw_place_id.startswith(_PREFIXED_PLACE_ID):
    return raw_place_id[len(_PREFIXED_PLACE_ID) - 3 :]
  return raw_place_id


def canonical_place_title(raw_title: str) -> str:
  """Drops the branding suffix the model never sees, keeping original casing."""
  if raw_title.endswith(_BRANDED_TITLE_SUFFIX):
    return raw_title[: -len(_BRANDED_TITLE_SUFFIX)]
  return raw_title


def extract_attribution_sources(response: Any) -> list[AttributionSource]:
  """Pulls the Maps attribution sources out of a genai response.

  Missing attributes are tolerated so callers do not have to guard every
  access. Arrival order is load-bearing: it is what the ordinals count over.

  Args:
      response: A `google.genai` GenerateContentResponse, or anything shaped
        like one.

  Returns:
      Sources that carry both a title and a Place ID, in arrival order.
  """
  candidates = getattr(response, "candidates", None)
  metadata = (
      getattr(candidates[0], "grounding_metadata", None) if candidates else None
  )
  raw_chunks = getattr(metadata, "grounding_chunks", None) if metadata else None

  sources = []
  for raw_chunk in raw_chunks or []:
    maps_source = getattr(raw_chunk, "maps", None)
    title = getattr(maps_source, "title", None)
    place_id = getattr(maps_source, "place_id", None)
    if title and place_id:
      sources.append(AttributionSource(title=title, place_id=place_id))
  return sources


def _build_placeholder_index(
    attribution_sources: list[AttributionSource],
) -> dict[str, str]:
  """Builds the placeholder-to-Place-ID substitution map.

  Ordinals count source occurrences within a canonical title, which is the
  COUNTING rule `PROMPT_RULES` gives the model. The model and this function
  derive their ordinals independently, so they can disagree. A disagreement
  usually leaves the placeholder unresolved, which is visible in the UI.

  Args:
      attribution_sources: Attribution sources in arrival order.

  Returns:
      Mapping from placeholder key to canonical Place ID.
  """
  placeholder_index = {}
  title_counts = {}
  for source in attribution_sources:
    title = canonical_place_title(source.title)
    place_id = normalize_place_id(source.place_id)
    if not title or not place_id:
      continue
    title_counts[title] = title_counts.get(title, 0) + 1
    placeholder_index[f"{PLACEHOLDER_PREFIX}{title_counts[title]}_{title}"] = (
        place_id
    )
  return placeholder_index


def resolve_place_ids(
    text: str,
    attribution_sources: list[AttributionSource],
) -> tuple[str, int]:
  """Replaces Place ID placeholders in a payload with grounded Place IDs.

  Placeholders with no matching source are deliberately left in place rather
  than substituted with a nearby ID. A visible placeholder fails loudly in the
  UI, whereas a plausible wrong Place ID renders a confidently wrong venue.

  Args:
      text: Serialized payload containing placeholders.
      attribution_sources: Attribution sources in arrival order.

  Returns:
      Tuple of the rewritten payload and the count left unresolved.
  """
  if not text:
    return text, 0

  # Matches `PLACE_ID_FOR_<index>_<canonical_title>` to extract `<canonical_title>`.
  placeholder_title_re = re.compile(
      rf"^{PLACEHOLDER_PREFIX}[0-9]+_(?P<title>.+)$"
  )
  placeholder_index = _build_placeholder_index(attribution_sources)
  matched_titles = set()
  for placeholder, place_id in placeholder_index.items():
    if placeholder in text:
      match = placeholder_title_re.match(placeholder)
      if match:
        matched_titles.add(match.group("title"))
    text = text.replace(placeholder, place_id)

  # Fallback pass for placeholders where the LLM used global list numbering
  # (e.g., `PLACE_ID_FOR_2_<title>` when `<title>` only appeared once as index 1).
  # Caveat: Titles already matched in pass 1 (`matched_titles`) are intentionally
  # skipped here so that if multiple distinct branches share the same title
  # (e.g., two "Starbucks" locations) and one placeholder was mis-indexed, we
  # leave the ambiguous placeholder unresolved rather than substituting the
  # wrong branch's Place ID.
  if PLACEHOLDER_PREFIX in text:
    title_counts = collections.Counter(
        canonical_place_title(s.title)
        for s in attribution_sources
        if canonical_place_title(s.title) and normalize_place_id(s.place_id)
    )
    for source in sorted(
        attribution_sources,
        key=lambda s: len(canonical_place_title(s.title)),
        reverse=True,
    ):
      title = canonical_place_title(source.title)
      place_id = normalize_place_id(source.place_id)
      if (
          title
          and place_id
          and title not in matched_titles
          and title_counts[title] == 1
      ):
        pattern = rf"{PLACEHOLDER_PREFIX}\d+_{re.escape(title)}"
        if len(re.findall(pattern, text, flags=re.IGNORECASE)) == 1:
          text = re.sub(pattern, place_id, text, count=1, flags=re.IGNORECASE)
          matched_titles.add(title)

  unresolved = text.count(PLACEHOLDER_PREFIX)
  if unresolved:
    logger.warning(
        "%d Place ID placeholder(s) unresolved against %d source(s).",
        unresolved,
        len(placeholder_index),
    )
  return text, unresolved
