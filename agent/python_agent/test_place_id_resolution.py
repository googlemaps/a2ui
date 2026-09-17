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

"""Unit tests for Place ID placeholder substitution."""

import unittest
from unittest import mock

import place_id_resolution


def _create_mock_response(
    chunks: list[tuple[str, str, str]] | None = None,
) -> mock.MagicMock:
  """Builds a mock genai response carrying Maps attribution sources.

  The shape mirrors production: every Maps source arrives with a non-empty
  `place_id`, which is what makes placeholder substitution viable at all.

  Args:
      chunks: List of (title, place_id) tuples.

  Returns:
      Mock response matching the Google GenAI SDK candidate structure.
  """
  mock_chunks = []
  for title, place_id in chunks or []:
    mock_chunk = mock.MagicMock()
    mock_chunk.maps.title = title
    mock_chunk.maps.place_id = place_id
    mock_chunks.append(mock_chunk)

  mock_meta = mock.MagicMock()
  mock_meta.grounding_chunks = mock_chunks
  mock_candidate = mock.MagicMock()
  mock_candidate.grounding_metadata = mock_meta
  mock_response = mock.MagicMock()
  mock_response.candidates = [mock_candidate]
  return mock_response


def _chunk(title: str, place_id: str) -> place_id_resolution.AttributionSource:
  """Shorthand for constructing an attribution source."""
  return place_id_resolution.AttributionSource(title=title, place_id=place_id)


class NormalizePlaceIdTest(unittest.TestCase):

  def test_strips_places_resource_prefix(self):
    self.assertEqual(
        place_id_resolution.normalize_place_id(
            "places/ChIJN1t_tDeuEmsRUsoyG83frY4"
        ),
        "ChIJN1t_tDeuEmsRUsoyG83frY4",
    )

  def test_leaves_bare_id_untouched(self):
    self.assertEqual(
        place_id_resolution.normalize_place_id("ChIJN1t_tDeuEmsRUsoyG83frY4"),
        "ChIJN1t_tDeuEmsRUsoyG83frY4",
    )

  def test_leaves_prefixed_id_untouched_when_it_is_not_a_chi_id(self):
    # Pins shipped behavior. The prefix check demands "places/ChI", so an ID
    # from any other family keeps its resource prefix.
    self.assertEqual(
        place_id_resolution.normalize_place_id("places/GhIJabc"),
        "places/GhIJabc",
    )


class CanonicalPlaceTitleTest(unittest.TestCase):

  def test_strips_google_maps_branding_suffix(self):
    self.assertEqual(
        place_id_resolution.canonical_place_title("Chez Panisse - Google Maps"),
        "Chez Panisse",
    )

  def test_leaves_branding_suffix_written_with_an_en_dash(self):
    # Pins shipped behavior. Only the hyphen form is recognized.
    self.assertEqual(
        place_id_resolution.canonical_place_title(
            "Chez Panisse \u2013 Google Maps"
        ),
        "Chez Panisse \u2013 Google Maps",
    )

  def test_preserves_original_casing(self):
    # The prompt tells the model to copy the title character for character, so
    # lowercasing here would make every substitution key miss.
    self.assertEqual(
        place_id_resolution.canonical_place_title("Starbucks Coffee Company"),
        "Starbucks Coffee Company",
    )

  def test_leaves_review_prefix_in_place(self):
    # Pins shipped behavior. Grounding emits user reviews as their own sources,
    # and they canonicalize to a title distinct from the venue's.
    self.assertEqual(
        place_id_resolution.canonical_place_title(
            "Review of Joe's Pizza - Google Maps"
        ),
        "Review of Joe's Pizza",
    )

  def test_leaves_unbranded_title_untouched(self):
    self.assertEqual(
        place_id_resolution.canonical_place_title("Joe's Pizza"), "Joe's Pizza"
    )


class ExtractAttributionSourcesTest(unittest.TestCase):

  def test_extracts_title_and_place_id_in_arrival_order(self):
    response = _create_mock_response([
        ("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
        ("Prince St. Pizza - Google Maps", "places/ChIJ_prince"),
    ])

    chunks = place_id_resolution.extract_attribution_sources(response)

    self.assertEqual(
        chunks,
        [
            _chunk("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
            _chunk("Prince St. Pizza - Google Maps", "places/ChIJ_prince"),
        ],
    )

  def test_returns_empty_when_response_has_no_candidates(self):
    response = mock.MagicMock()
    response.candidates = []
    self.assertEqual(
        place_id_resolution.extract_attribution_sources(response), []
    )

  def test_returns_empty_when_grounding_metadata_absent(self):
    response = mock.MagicMock()
    candidate = mock.MagicMock()
    candidate.grounding_metadata = None
    response.candidates = [candidate]
    self.assertEqual(
        place_id_resolution.extract_attribution_sources(response), []
    )

  def test_skips_sources_missing_a_place_id(self):
    response = _create_mock_response([
        ("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
        ("A Web Result", ""),
    ])

    chunks = place_id_resolution.extract_attribution_sources(response)

    self.assertEqual(len(chunks), 1)
    self.assertEqual(chunks[0].title, "Joe's Pizza - Google Maps")


class BuildPlaceholderIndexTest(unittest.TestCase):

  def test_five_same_titled_venues_get_five_distinct_ids(self):
    chunks = [
        _chunk("Starbucks - Google Maps", f"places/ChIJ_sbux_{i}")
        for i in range(1, 6)
    ]

    placeholder_index = place_id_resolution._build_placeholder_index(chunks)

    self.assertEqual(
        placeholder_index,
        {
            "PLACE_ID_FOR_1_Starbucks": "ChIJ_sbux_1",
            "PLACE_ID_FOR_2_Starbucks": "ChIJ_sbux_2",
            "PLACE_ID_FOR_3_Starbucks": "ChIJ_sbux_3",
            "PLACE_ID_FOR_4_Starbucks": "ChIJ_sbux_4",
            "PLACE_ID_FOR_5_Starbucks": "ChIJ_sbux_5",
        },
    )

  def test_review_source_lands_in_its_own_title_bucket(self):
    # Pins shipped behavior. "Review of X" canonicalizes to a title distinct
    # from "X", so it gets its own counter and produces a key the model never
    # emits. Venue ordinals are only disturbed when a venue surfaces
    # exclusively as a review source.
    chunks = [
        _chunk("Starbucks - Google Maps", "places/ChIJ_sbux_1"),
        _chunk("Review of Starbucks - Google Maps", "places/ChIJ_sbux_1"),
        _chunk("Starbucks - Google Maps", "places/ChIJ_sbux_2"),
    ]

    placeholder_index = place_id_resolution._build_placeholder_index(chunks)

    self.assertEqual(
        placeholder_index,
        {
            "PLACE_ID_FOR_1_Starbucks": "ChIJ_sbux_1",
            "PLACE_ID_FOR_1_Review of Starbucks": "ChIJ_sbux_1",
            "PLACE_ID_FOR_2_Starbucks": "ChIJ_sbux_2",
        },
    )

  def test_distinct_titles_each_start_at_ordinal_one(self):
    chunks = [
        _chunk("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
        _chunk("Prince St. Pizza - Google Maps", "places/ChIJ_prince"),
    ]

    placeholder_index = place_id_resolution._build_placeholder_index(chunks)

    self.assertEqual(
        placeholder_index,
        {
            "PLACE_ID_FOR_1_Joe's Pizza": "ChIJ_joe",
            "PLACE_ID_FOR_1_Prince St. Pizza": "ChIJ_prince",
        },
    )

  def test_returns_empty_map_for_no_sources(self):
    self.assertEqual(place_id_resolution._build_placeholder_index([]), {})


class ResolvePlaceIdsTest(unittest.TestCase):

  def test_rewrites_placeholders_with_grounded_place_ids(self):
    text = (
        '{"places": [{"placeId": "PLACE_ID_FOR_1_Joe\'s Pizza"},'
        ' {"placeId": "PLACE_ID_FOR_1_Prince St. Pizza"}]}'
    )
    chunks = [
        _chunk("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
        _chunk("Prince St. Pizza - Google Maps", "places/ChIJ_prince"),
    ]

    result, unresolved = place_id_resolution.resolve_place_ids(text, chunks)

    self.assertEqual(
        result,
        '{"places": [{"placeId": "ChIJ_joe"}, {"placeId": "ChIJ_prince"}]}',
    )
    self.assertEqual(unresolved, 0)

  def test_shorter_key_shadows_the_longer_one_sharing_its_prefix(self):
    # Pins shipped behavior. Substitution walks the index in arrival order, so
    # PLACE_ID_FOR_1_Joe's Pizza fires first and strands " Express" on a
    # now-real Place ID. Observed live on "Grand Central" versus "Grand Central
    # Terminal".
    text = "PLACE_ID_FOR_1_Joe's Pizza Express"
    chunks = [
        _chunk("Joe's Pizza - Google Maps", "places/ChIJ_joe"),
        _chunk("Joe's Pizza Express - Google Maps", "places/ChIJ_express"),
    ]

    result, unresolved = place_id_resolution.resolve_place_ids(text, chunks)

    self.assertEqual(result, "ChIJ_joe Express")
    self.assertEqual(unresolved, 0)

  def test_leaves_placeholder_in_place_when_sources_run_short(self):
    # Grounding cited fewer venues than the model named. A visible placeholder
    # breaks the card loudly; a nearby Place ID would render a wrong venue with
    # full confidence.
    text = "PLACE_ID_FOR_1_Starbucks and PLACE_ID_FOR_2_Starbucks"
    chunks = [_chunk("Starbucks - Google Maps", "places/ChIJ_sbux_1")]

    with self.assertLogs(place_id_resolution.__name__, level="WARNING") as logs:
      result, unresolved = place_id_resolution.resolve_place_ids(text, chunks)

    self.assertEqual(result, "ChIJ_sbux_1 and PLACE_ID_FOR_2_Starbucks")
    self.assertEqual(unresolved, 1)
    self.assertIn("unresolved", logs.output[0])

  def test_warns_and_passes_text_through_when_no_sources_returned(self):
    text = "PLACE_ID_FOR_1_Starbucks"

    with self.assertLogs(place_id_resolution.__name__, level="WARNING") as logs:
      result, unresolved = place_id_resolution.resolve_place_ids(text, [])

    self.assertEqual(result, text)
    self.assertEqual(unresolved, 1)
    self.assertIn("unresolved against 0 source(s)", logs.output[0])

  def test_empty_text_is_a_no_op(self):
    chunks = [_chunk("Starbucks - Google Maps", "places/ChIJ_sbux_1")]
    self.assertEqual(place_id_resolution.resolve_place_ids("", chunks), ("", 0))

  def test_text_without_placeholders_is_unchanged(self):
    text = '{"places": [{"placeId": "ChIJ_already_real"}]}'
    chunks = [_chunk("Starbucks - Google Maps", "places/ChIJ_sbux_1")]

    result, unresolved = place_id_resolution.resolve_place_ids(text, chunks)

    self.assertEqual(result, text)
    self.assertEqual(unresolved, 0)


class PromptContractTest(unittest.TestCase):

  def test_prompt_rules_describe_the_format_the_parser_builds(self):
    # The prompt and build_placeholder_index must agree on the placeholder
    # format. If they drift, every key misses and raw placeholders ship to
    # the client, so pin the shared prefix and the ordinal example here.
    self.assertIn(
        f"{place_id_resolution.PLACEHOLDER_PREFIX}{{Count}}_{{Exact Title}}",
        place_id_resolution.PROMPT_RULES,
    )

    built = place_id_resolution._build_placeholder_index([
        _chunk("Chez Panisse - Google Maps", "places/ChIJ_cp_1"),
        _chunk("Chez Panisse - Google Maps", "places/ChIJ_cp_2"),
    ])

    for example in (
        f"{place_id_resolution.PLACEHOLDER_PREFIX}1_Chez Panisse",
        f"{place_id_resolution.PLACEHOLDER_PREFIX}2_Chez Panisse",
    ):
      with self.subTest(placeholder=example):
        self.assertIn(example, place_id_resolution.PROMPT_RULES)
        self.assertIn(example, built)


if __name__ == "__main__":
  unittest.main()
