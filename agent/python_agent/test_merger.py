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

"""Tests for A2UI Layout Template Merger (`merger.py`)."""

import enum
import importlib
import importlib.resources
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

from a2a.types import DataPart, Part

from google3.third_party.a2ui.agent_sdks.python.a2ui_agent.src.a2ui import schema
import agent
import merger

merge_template = merger.merge_template


class TestMerger(unittest.TestCase):
  """Tests for A2UI Layout Template Merger."""

  def _validate_schema(self, result):
    """Validates the merged result against the Maps Catalog Extension schema."""
    extension_path = (
        pathlib.Path(__file__).parent
        / "shared"
        / "schema"
        / "maps_catalog_extension.json"
    )
    schema_manager = schema.manager.A2uiSchemaManager(
        version=schema.constants.VERSION_0_9,
        catalogs=[
            schema.catalog.CatalogConfig(
                name="maps-agentic-ui-catalog",
                provider=agent.MergedCatalogProvider(
                    schema.constants.VERSION_0_9, str(extension_path)
                ),
            )
        ],
        schema_modifiers=[schema.common_modifiers.remove_strict_validation],
    )
    selected_catalog = schema_manager.get_selected_catalog()
    selected_catalog.validator.validate(result)

  def test_merge_unknown_template_raises_error(self):
    """Verifies that an unknown template raises FileNotFoundError."""
    with self.assertRaises(FileNotFoundError):
      merge_template("non_existent_template", {"text": "hello"})

  def test_merge_defaults_to_maps_catalog_id(self):
    """Verifies the surface binds to the Maps catalog when none is named."""
    result = merge_template("text_only", {"text": "hello"})
    self.assertEqual(
        result[0]["createSurface"]["catalogId"],
        "a2ui://maps-agentic-ui-catalog.json",
    )
    self.assertEqual(
        result[0]["createSurface"]["catalogId"], merger.DEFAULT_CATALOG_ID
    )

  def test_merge_honors_custom_catalog_id(self):
    """Verifies a host-supplied catalog id reaches every template's surface."""
    host_catalog = "https://example.test/host_catalog.json"
    local_search_data = {
        "surface_id": "test-surface",
        "summary": "Two places.",
        "center_lat": 37.0,
        "center_lng": -122.0,
        "zoom": 12,
        "places": [{"name": "A", "lat": 37.0, "lng": -122.0}],
    }
    directions_data = {
        "surface_id": "test-surface",
        "summary": "A route.",
        "center_lat": 37.0,
        "center_lng": -122.0,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": 37.0, "lng": -122.0, "label": "A"},
            "destination": {"lat": 37.1, "lng": -122.1, "label": "B"},
        }],
    }
    for template_name, data in (
        ("text_only", {"text": "hello"}),
        ("local_search", local_search_data),
        ("directions", directions_data),
    ):
      with self.subTest(template=template_name):
        result = merge_template(template_name, data, catalog_id=host_catalog)
        self.assertEqual(result[0]["createSurface"]["catalogId"], host_catalog)

  def test_text_only_fallback_keeps_custom_catalog_id(self):
    """Verifies the catalog id survives the bail-out to `text_only`.

    The prepare helpers discard the caller's dict and build a fresh one when
    they fall back, so a catalog id applied before that point would be lost.
    Losing it is silent: the placeholder resolves to None and the key is
    stripped, leaving a surface bound to no catalog at all.
    """
    host_catalog = "https://example.test/host_catalog.json"
    invalid_local_search = {
        "surface_id": "test-surface",
        "summary": "Short response.",
        "center_lat": 37.0,
        "center_lng": 127.0,
        "zoom": 10,
        "places": "NOT_A_LIST",
    }
    invalid_directions = {
        "surface_id": "test-surface",
        "summary": "Cannot compute directions.",
    }
    for template_name, data in (
        ("local_search", invalid_local_search),
        ("directions", invalid_directions),
    ):
      with self.subTest(template=template_name):
        result = merge_template(template_name, data, catalog_id=host_catalog)
        create_surface = result[0]["createSurface"]
        self.assertIn("catalogId", create_surface)
        self.assertEqual(create_surface["catalogId"], host_catalog)

  def test_merge_text_only_full_json(self):
    """Verifies that text-only response is merged correctly."""
    data = {
        "surface_id": "text-only-surface-efg",
        "text": "Google Maps directions are not supported in South Korea.",
    }

    expected = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "text-only-surface-efg",
                "catalogId": "a2ui://maps-agentic-ui-catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "text-only-surface-efg",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["text-content"],
                    },
                    {
                        "id": "text-content",
                        "component": "Text",
                        "variant": "body",
                        "text": (
                            "Google Maps directions are not supported in South"
                            " Korea."
                        ),
                    },
                ],
            },
        },
    ]
    result = merge_template("text_only", data)
    self.assertEqual(result, expected)

  def test_validate_merged_output_with_schema(self):
    """Validates the merged output against maps catalog extension schema."""
    data = {
        "surface_id": "text-only-surface-efg",
        "text": "Google Maps directions are not supported in South Korea.",
    }
    result = merge_template("text_only", data)

    self._validate_schema(result)

  def test_merge_omitted_surface_id_generates_random_suffix(self):
    """Verifies that omitting surface_id generates a random dynamic ID."""
    data = {
        "text": "Hello world",
    }
    result = merge_template("text_only", data)
    # createSurface is the first event in the list
    surface_id = result[0]["createSurface"]["surfaceId"]
    self.assertTrue(re.fullmatch(r"text_only_surface_[a-f0-9]{6}", surface_id))

  def test_merge_generic_surface_id_generates_random_suffix(self):
    """Verifies that a generic default surface_id gets a random suffix."""
    data = {
        "surface_id": "text-only-surface",
        "text": "Hello world",
    }
    result = merge_template("text_only", data)
    surface_id = result[0]["createSurface"]["surfaceId"]
    self.assertTrue(re.fullmatch(r"text-only-surface_[a-f0-9]{6}", surface_id))

  def test_merge_custom_surface_id_remains_intact(self):
    """Verifies that a custom unique surface_id is preserved exactly."""
    data = {
        "surface_id": "my-special-surface-123",
        "text": "Hello world",
    }
    result = merge_template("text_only", data)
    surface_id = result[0]["createSurface"]["surfaceId"]
    self.assertEqual(surface_id, "my-special-surface-123")

  def test_merge_local_search_full_json(self):
    """Verifies merging a complete local search payload."""
    data = {
        "surface_id": "local-search-surface-abc",
        "heading": "Top Coffee Shops in Seattle",
        "summary": "Here are 3 highly-rated coffee shops in Seattle.",
        "center_lat": "47.6062",
        "center_lng": -122.3321,
        "zoom": "14",
        "places": [
            {
                "placeId": "ChIJ111",
                "name": "Espresso Vivace",
                "lat": "47.6200",
                "lng": "-122.3200",
            },
            {
                "placeId": "ChIJ222",
                "name": "Milstead & Co.",
                "lat": 47.6400,
                "lng": -122.3500,
            },
            {
                "placeId": "ChIJ333",
                "name": "Victrola Coffee",
                "lat": 47.6100,
                "lng": -122.3200,
            },
        ],
    }

    expected = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "local-search-surface-abc",
                "catalogId": "a2ui://maps-agentic-ui-catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "local-search-surface-abc",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": [
                            "heading-text",
                            "summary-text",
                            "map",
                            "list",
                        ],
                    },
                    {
                        "id": "heading-text",
                        "component": "Text",
                        "variant": "body",
                        "text": "### Top Coffee Shops in Seattle",
                    },
                    {
                        "id": "summary-text",
                        "component": "Text",
                        "variant": "body",
                        "text": (
                            "Here are 3 highly-rated coffee shops in Seattle."
                        ),
                    },
                    {
                        "id": "map",
                        "component": "GoogleMap",
                        "center": {"lat": 47.6062, "lng": -122.3321},
                        "zoom": 14,
                        "tilt": 0,
                        "mode": "roadmap",
                        "markers": [
                            {
                                "lat": 47.62,
                                "lng": -122.32,
                                "label": "Espresso Vivace",
                                "placeId": "ChIJ111",
                            },
                            {
                                "lat": 47.64,
                                "lng": -122.35,
                                "label": "Milstead & Co.",
                                "placeId": "ChIJ222",
                            },
                            {
                                "lat": 47.61,
                                "lng": -122.32,
                                "label": "Victrola Coffee",
                                "placeId": "ChIJ333",
                            },
                        ],
                    },
                    {
                        "id": "list",
                        "component": "List",
                        "direction": "vertical",
                        "children": {
                            "componentId": "place-card",
                            "path": "/places",
                        },
                    },
                    {
                        "id": "place-card",
                        "component": "PlaceDetailsCompact",
                        "placeId": {"path": "placeId"},
                    },
                ],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "local-search-surface-abc",
                "path": "/",
                "value": {
                    "places": [
                        {
                            "placeId": "ChIJ111",
                            "name": "Espresso Vivace",
                            "lat": 47.62,
                            "lng": -122.32,
                        },
                        {
                            "placeId": "ChIJ222",
                            "name": "Milstead & Co.",
                            "lat": 47.64,
                            "lng": -122.35,
                        },
                        {
                            "placeId": "ChIJ333",
                            "name": "Victrola Coffee",
                            "lat": 47.61,
                            "lng": -122.32,
                        },
                    ]
                },
            },
        },
    ]

    result = merge_template("local_search", data, max_list_size=3)
    self.assertEqual(result, expected)

  def test_validate_local_search_output_with_schema(self):
    """Validates the merged local search output against maps catalog extension schema."""
    data = {
        "surface_id": "local-search-surface-abc",
        "summary": "Here are coffee shops.",
        "center_lat": 47.6062,
        "center_lng": -122.3321,
        "zoom": 14,
        "places": [{
            "placeId": "ChIJ111",
            "name": "Espresso Vivace",
            "lat": 47.62,
            "lng": -122.32,
        }],
    }
    result = merge_template("local_search", data)

    self._validate_schema(result)

  def test_merge_max_list_size_slicing(self):
    """Verifies that max_list_size parameter slices the places and markers list."""
    data = {
        "surface_id": "test-surface",
        "summary": "Here are some places.",
        "center_lat": 47.6062,
        "center_lng": -122.3321,
        "zoom": 14,
        "places": [
            {"placeId": "1", "name": "P1", "lat": 47.61, "lng": -122.31},
            {"placeId": "2", "name": "P2", "lat": 47.62, "lng": -122.32},
            {"placeId": "3", "name": "P3", "lat": 47.63, "lng": -122.33},
        ],
    }
    result = merge_template("local_search", data, max_list_size=2)
    # Check that updateComponents has only 2 markers
    components = result[1]["updateComponents"]["components"]
    map_comp = next(comp for comp in components if comp["id"] == "map")
    self.assertEqual(len(map_comp["markers"]), 2)

    # Check that updateDataModel has only 2 places
    places = result[2]["updateDataModel"]["value"]["places"]
    self.assertEqual(len(places), 2)
    self.assertEqual(places[0]["placeId"], "1")
    self.assertEqual(places[1]["placeId"], "2")

  def test_merge_local_search_heading_normalization(self):
    """Verifies that heading is cleaned of markdown headers or synthesized from anchor."""
    # Case 1: Heading with leading markdown hashtags
    data_with_hash = {
        "surface_id": "test-surface",
        "heading": "### Best Bakeries",
        "summary": "Here are bakeries.",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 13,
        "places": [{"placeId": "p1", "name": "B1", "lat": 47.6, "lng": -122.3}],
    }
    result = merge_template("local_search", data_with_hash)
    comps = result[1]["updateComponents"]["components"]
    heading_comp = next(comp for comp in comps if comp["id"] == "heading-text")
    self.assertEqual(heading_comp["text"], "### Best Bakeries")

    # Case 2: Missing heading with anchor marker
    data_with_anchor = {
        "surface_id": "test-surface",
        "summary": "Here are bakeries.",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 13,
        "anchor_marker": {"lat": 47.6, "lng": -122.3, "label": "Space Needle"},
        "places": [{"placeId": "p1", "name": "B1", "lat": 47.6, "lng": -122.3}],
    }
    result = merge_template("local_search", data_with_anchor)
    comps = result[1]["updateComponents"]["components"]
    heading_comp = next(comp for comp in comps if comp["id"] == "heading-text")
    self.assertEqual(heading_comp["text"], "### Places near Space Needle")

    # Case 3: Missing heading and no anchor
    data_no_heading = {
        "surface_id": "test-surface",
        "summary": "Here are bakeries.",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 13,
        "places": [{"placeId": "p1", "name": "B1", "lat": 47.6, "lng": -122.3}],
    }
    result = merge_template("local_search", data_no_heading)
    comps = result[1]["updateComponents"]["components"]
    heading_comp = next(comp for comp in comps if comp["id"] == "heading-text")
    self.assertEqual(heading_comp["text"], "### Nearby Places")

  def test_merge_directions_full_json(self):
    """Verifies complete end-to-end directions template merging, placeholder replacement, and travel mode normalization."""
    data = {
        "surface_id": "directions-surface-xyz",
        "heading": "Walking Route from Dobong to Gangnam",
        "summary": "Typical commute is 1h 15m.",
        "center_lat": "37.5665",
        "center_lng": 126.9780,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": "37.6700", "lng": "127.0400", "label": "Dobong"},
            "destination": {
                "lat": 37.4900,
                "lng": 127.0200,
                "label": "Gangnam",
            },
        }],
        "travel_mode": "WALK",
    }

    expected = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "directions-surface-xyz",
                "catalogId": "a2ui://maps-agentic-ui-catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "directions-surface-xyz",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["heading-text", "map", "summary-text"],
                    },
                    {
                        "id": "heading-text",
                        "component": "Text",
                        "variant": "body",
                        "text": "### Walking Route from Dobong to Gangnam",
                    },
                    {
                        "id": "map",
                        "component": "GoogleMap",
                        "center": {"lat": 37.5665, "lng": 126.978},
                        "zoom": 12,
                        "routes": [{
                            "origin": {
                                "lat": 37.67,
                                "lng": 127.04,
                                "label": "Dobong",
                            },
                            "destination": {
                                "lat": 37.49,
                                "lng": 127.02,
                                "label": "Gangnam",
                            },
                        }],
                        "travelMode": "walking",
                    },
                    {
                        "id": "summary-text",
                        "component": "Text",
                        "variant": "body",
                        "text": "Typical commute is 1h 15m.",
                    },
                ],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "directions-surface-xyz",
                "path": "/",
                "value": {},
            },
        },
    ]

    result = merge_template("directions", data, max_list_size=3)
    self.assertEqual(result, expected)

  def test_merge_directions_heading_fallback(self):
    """Verifies that missing heading is synthesized from route endpoints."""
    # Case 1: Heading with leading markdown hashtags
    data_with_hash = {
        "surface_id": "test-surface",
        "heading": "### Driving Route",
        "summary": "About 15 minutes.",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": 37.5, "lng": 127.0, "label": "Origin"},
            "destination": {"lat": 37.6, "lng": 127.1, "label": "Dest"},
        }],
    }
    result = merge_template("directions", data_with_hash)
    comps = result[1]["updateComponents"]["components"]
    heading_comp = next(c for c in comps if c["id"] == "heading-text")
    self.assertEqual(heading_comp["text"], "### Driving Route")

    # Case 2: Missing heading with origin and destination labels
    data_missing = {
        "surface_id": "test-surface",
        "summary": "About 15 minutes.",
        "center_lat": 37.5,
        "center_lng": 127.0,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": 37.5, "lng": 127.0, "label": "Seattle Center"},
            "destination": {
                "lat": 37.6,
                "lng": 127.1,
                "label": "Pike Place Market",
            },
        }],
    }
    result = merge_template("directions", data_missing)
    comps = result[1]["updateComponents"]["components"]
    heading_comp = next(c for c in comps if c["id"] == "heading-text")
    self.assertEqual(
        heading_comp["text"],
        "### Route from Seattle Center to Pike Place Market",
    )

  def test_validate_directions_output_with_schema(self):
    """Verifies merged directions output passes schema validation."""
    data = {
        "surface_id": "directions-surface-xyz",
        "summary": "Typical commute is 1h 15m.",
        "center_lat": "37.5665",
        "center_lng": 126.9780,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": "37.6700", "lng": "127.0400", "label": "Dobong"},
            "destination": {
                "lat": 37.4900,
                "lng": 127.0200,
                "label": "Gangnam",
            },
        }],
        "travel_mode": "WALK",
    }
    result = merge_template("directions", data)

    self._validate_schema(result)


class TestMergerEdgeCases(unittest.TestCase):
  """Edge case tests for A2UI Layout Template Merger."""

  def test_missing_keys_no_crash_local_search(self):
    """Verifies that merging local_search template with empty/missing places falls back to text_only."""
    data = {
        "surface_id": "test-surface",
        "summary": "Short response without places.",
    }
    result = merge_template("local_search", data, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Short response without places.",
    )

  def test_invalid_places_with_valid_center_fallback(self):
    """Verifies that local_search fallback to text_only if places is invalid but center is valid."""
    data = {
        "surface_id": "test-surface",
        "summary": "Short response.",
        "center_lat": 37.0,
        "center_lng": 127.0,
        "zoom": 10,
        "places": "NOT_A_LIST",  # Invalid places
    }
    result = merge_template("local_search", data, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Short response.",
    )

  def test_missing_keys_no_crash_directions(self):
    """Verifies that merging directions template with missing or empty routes gracefully falls back to a text-only representation."""
    # Test missing routes
    data_no_routes = {
        "surface_id": "test-surface",
        "summary": "Cannot compute directions.",
    }
    result = merge_template("directions", data_no_routes, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Cannot compute directions.",
    )

    # Test empty routes
    data_empty_routes = {
        "surface_id": "test-surface",
        "summary": "Cannot compute directions.",
        "routes": [],
    }
    result = merge_template("directions", data_empty_routes, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Cannot compute directions.",
    )

  def test_unrecognized_travel_mode(self):
    """Verifies that unrecognized travel modes are ignored and not passed to output."""
    data = {
        "surface_id": "test-surface",
        "summary": "Short response.",
        "center_lat": 37.0,
        "center_lng": 127.0,
        "zoom": 10,
        "routes": [{
            "origin": {"lat": 37.0, "lng": 127.0, "label": "Start"},
            "destination": {"lat": 37.1, "lng": 127.1, "label": "End"},
        }],
        "travel_mode": "TELEPORT",
    }
    result = merge_template("directions", data, max_list_size=3)
    map_comp = next(
        c
        for c in result[1]["updateComponents"]["components"]
        if c["component"] == "GoogleMap"
    )
    self.assertNotIn("travelMode", map_comp)

  def test_travel_mode_synonyms_normalization(self):
    """Verifies that various travel mode synonyms normalize properly in merger."""
    test_cases = [
        ("public transit", "transit"),
        ("on foot", "walking"),
        ("auto", "driving"),
        ("cycling", "bicycling"),
        ("subway", "transit"),
        ("pedestrian", "walking"),
    ]
    for raw_mode, expected_mode in test_cases:
      with self.subTest(raw_mode=raw_mode, expected_mode=expected_mode):
        data = {
            "surface_id": "test-surface",
            "summary": "Commute.",
            "center_lat": 37.0,
            "center_lng": 127.0,
            "zoom": 10,
            "routes": [{
                "origin": {"lat": 37.0, "lng": 127.0, "label": "Start"},
                "destination": {"lat": 37.1, "lng": 127.1, "label": "End"},
            }],
            "travel_mode": raw_mode,
        }
        result = merge_template("directions", data, max_list_size=3)
        map_comp = next(
            c
            for c in result[1]["updateComponents"]["components"]
            if c["component"] == "GoogleMap"
        )
        self.assertEqual(map_comp.get("travelMode"), expected_mode)

  def test_malformed_coordinate_types(self):
    """Verifies that coordinates parsing fallback triggers text_only fallback."""
    data = {
        "surface_id": "test-surface",
        "summary": "Short response.",
        "center_lat": "invalid-lat-string",  # Malformed float
        "center_lng": None,  # Malformed type
        "zoom": "invalid-zoom",  # Malformed int
        "places": [{"name": "Dummy Place", "lat": 47.6, "lng": -122.3}],
    }
    result = merge_template("local_search", data, max_list_size=3)
    # Validation failure in mandatory fields must trigger fallback to text_only
    # (2 parts)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Short response.",
    )

  def test_places_not_list(self):
    """Verifies type fallback when places is string."""
    data = {
        "surface_id": "test-surface",
        "summary": "Short response.",
        "places": "this is a string, not a list",  # Invalid type for places
    }
    result = merge_template("local_search", data, max_list_size=3)
    # Non-list places must trigger fallback to text_only (2 parts)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Short response.",
    )

  def test_missing_optional_placeholders_are_stripped(self):
    """Verifies that optional placeholders are omitted when missing from input data."""
    data = {
        "surface_id": "test-surface",
        "summary": "Results for sushi.",
        "center_lat": 47.6062,
        "center_lng": -122.3321,
        "zoom": 14,
        "places": [{
            "placeId": "ChIJ111",
            "name": "Espresso Vivace",
            "lat": 47.6200,
            "lng": -122.3200,
        }],
    }
    result = merge_template("local_search", data, max_list_size=3)
    update_components = result[1]["updateComponents"]
    map_comp = next(
        comp for comp in update_components["components"] if comp["id"] == "map"
    )
    # Verify anchorMarker key is NOT in map component (cleanly stripped)
    self.assertNotIn("anchorMarker", map_comp)

  def test_markers_explicitly_provided_and_sanitized(self):
    """Verifies that explicitly provided markers are used and sanitized."""
    data = {
        "surface_id": "test-surface",
        "summary": "Results with custom markers.",
        "center_lat": 47.6062,
        "center_lng": -122.3321,
        "zoom": 14,
        "places": [{
            "placeId": "ChIJ111",
            "name": "Espresso Vivace",
            "lat": 47.62,
            "lng": -122.32,
        }],
        "markers": [
            {"lat": "47.63", "lng": "-122.33", "label": "Custom 1"},
            {"lat": 47.64, "lng": -122.34, "label": None},
            {"invalid_marker": "yes"},
        ],
    }
    result = merge_template("local_search", data, max_list_size=3)
    update_components = result[1]["updateComponents"]
    map_comp = next(
        comp for comp in update_components["components"] if comp["id"] == "map"
    )
    expected_markers = [
        {"lat": 47.63, "lng": -122.33, "label": "Custom 1"},
        {"lat": 47.64, "lng": -122.34, "label": ""},
    ]
    self.assertEqual(map_comp["markers"], expected_markers)

  def test_fallback_preserves_surface_id(self):
    """Verifies that text_only fallback preserves the provided surface_id."""
    data = {
        "surface_id": "my-custom-fallback-surface",
        "summary": "Short response.",
        "places": "invalid",
    }
    result = merge_template("local_search", data, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["surfaceId"],
        "my-custom-fallback-surface",
    )

  def test_malformed_coordinate_types_directions(self):
    """Verifies that malformed coordinates in directions trigger text_only fallback."""
    data = {
        "surface_id": "test-surface",
        "summary": "Cannot compute directions.",
        "center_lat": "invalid-lat",
        "center_lng": 127.0,
        "zoom": 10,
        "routes": [{
            "origin": {"lat": 37.0, "lng": 127.0, "label": "Start"},
            "destination": {"lat": 37.1, "lng": 127.1, "label": "End"},
        }],
    }
    result = merge_template("directions", data, max_list_size=3)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Cannot compute directions.",
    )

  def test_merge_directions_with_direct_routes(self):
    """Verifies directions template merging when routes are directly passed."""
    data = {
        "surface_id": "directions-surface-xyz",
        "summary": "Commute is 1h.",
        "center_lat": 37.5665,
        "center_lng": 126.9780,
        "zoom": 12,
        "routes": [
            {
                "origin": {"lat": 37.6700, "lng": 127.0400, "label": "A"},
                "destination": {"lat": 37.5000, "lng": 127.0000, "label": "B"},
            },
            {
                "origin": {"lat": 37.5000, "lng": 127.0000, "label": "B"},
                "destination": {"lat": 37.4900, "lng": 127.0200, "label": "C"},
            },
        ],
    }
    result = merge_template("directions", data)
    # The merged updateComponents should contain routes in GoogleMap
    map_comp = next(
        c
        for c in result[1]["updateComponents"]["components"]
        if c["component"] == "GoogleMap"
    )
    self.assertEqual(len(map_comp["routes"]), 2)
    self.assertEqual(map_comp["routes"][0]["origin"]["label"], "A")
    self.assertEqual(map_comp["routes"][1]["destination"]["label"], "C")

  def test_merge_directions_malformed_routes_fallback(self):
    """Verifies that malformed routes trigger text_only fallback."""
    data = {
        "surface_id": "test-surface",
        "summary": "Fallback text.",
        "center_lat": 37.0,
        "center_lng": 127.0,
        "zoom": 10,
        "routes": [{
            "origin": "not-a-dict",
            "destination": {"lat": 37.1, "lng": 127.1, "label": "End"},
        }],
    }
    result = merge_template("directions", data)
    self.assertEqual(len(result), 2)
    self.assertEqual(
        result[1]["updateComponents"]["components"][1]["text"],
        "Fallback text.",
    )


class TestMergerZipImportedPackage(unittest.TestCase):
  """Covers template loading when the agent is served from a zip archive.

  The agent also ships as a zipped archive that Python imports without ever
  unpacking it to disk. In that mode `__file__` names an entry inside the
  archive, so resolving templates by filesystem path makes every merge fail at
  serving time while a suite run from an ordinary source tree keeps passing.
  These tests exercise the archive explicitly so that gap cannot reopen.
  """

  _PACKAGE = "a2ui_zipped_merger_probe"

  def _pack_merger_into_zip(self) -> str:
    """Copies `merger` and its templates into a zip and returns its path."""
    source = importlib.resources.files(merger.__package__)
    temp_dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
    archive_path = os.path.join(temp_dir, "merger_probe.zip")
    with zipfile.ZipFile(archive_path, "w") as archive:
      archive.writestr(f"{self._PACKAGE}/__init__.py", "")
      archive.writestr(
          f"{self._PACKAGE}/merger.py",
          source.joinpath("merger.py").read_text(encoding="utf-8"),
      )
      for entry in source.joinpath("templates").iterdir():
        layout = entry.joinpath("layout.json")
        if not layout.is_file():
          continue
        archive.writestr(
            f"{self._PACKAGE}/templates/{entry.name}/layout.json",
            layout.read_text(encoding="utf-8"),
        )
    return archive_path

  def _import_merger_from_zip(self):
    """Imports the packed `merger`, whose templates exist only in the zip."""
    archive_path = self._pack_merger_into_zip()
    sys.path.insert(0, archive_path)
    self.addCleanup(sys.path.remove, archive_path)
    for name in (f"{self._PACKAGE}.merger", self._PACKAGE):
      self.addCleanup(sys.modules.pop, name, None)
    importlib.invalidate_caches()
    return importlib.import_module(f"{self._PACKAGE}.merger")

  def test_probe_templates_are_reachable_only_inside_the_archive(self):
    """Asserts the probe exercises the archive rather than a copy on disk.

    Without this the remaining tests could pass against an unpacked directory
    and prove nothing, because that is the mode that never broke.
    """
    zipped_merger = self._import_merger_from_zip()

    on_disk_templates = os.path.join(
        os.path.dirname(os.path.abspath(zipped_merger.__file__)), "templates"
    )

    self.assertNotEqual(zipped_merger.__file__, merger.__file__)
    self.assertFalse(os.path.exists(on_disk_templates))

  def test_merges_every_shipped_template_from_the_archive(self):
    """Verifies each template resolves as package data inside the archive."""
    zipped_merger = self._import_merger_from_zip()
    cases = {
        "text_only": {"text": "hello"},
        "local_search": {
            "summary": "Coffee near the market.",
            "center_lat": 47.6097,
            "center_lng": -122.3422,
            "zoom": 14,
            "places": [
                {"name": "Storyville", "lat": 47.6092, "lng": -122.3418}
            ],
        },
        "directions": {
            "summary": "About 50 minutes via US-101 S.",
            "center_lat": 37.55,
            "zoom": 10,
            "travel_mode": "driving",
            "routes": [{
                "origin": {"lat": 37.7749, "lng": -122.4194, "label": "SF"},
                "destination": {
                    "lat": 37.3382,
                    "lng": -121.8863,
                    "label": "SJ",
                },
            }],
        },
    }

    for template_name, data in cases.items():
      with self.subTest(template=template_name):
        result = zipped_merger.merge_template(template_name, data)

        self.assertTrue(result)
        self.assertEqual(
            result[0]["createSurface"]["catalogId"], merger.DEFAULT_CATALOG_ID
        )

  def test_unknown_template_still_raises_from_the_archive(self):
    """A missing template must stay distinguishable from an unreadable one."""
    zipped_merger = self._import_merger_from_zip()

    with self.assertRaises(FileNotFoundError):
      zipped_merger.merge_template("non_existent_template", {"text": "hello"})

  def test_default_surface_id_is_uniquified_from_the_archive(self):
    """Covers the template scan that decides whether a surface ID is generic.

    The scan sat behind a filesystem probe that reported an empty directory
    inside an archive instead of failing, so default surface IDs quietly
    stopped being made unique per turn and no log line recorded it.
    """
    zipped_merger = self._import_merger_from_zip()

    result = zipped_merger.merge_template(
        "text_only", {"text": "hello", "surface_id": "text_only_surface"}
    )

    surface_id = result[0]["createSurface"]["surfaceId"]
    self.assertNotEqual(surface_id, "text_only_surface")
    self.assertTrue(surface_id.startswith("text_only_surface_"))


class _TestIntent(enum.Enum):
  LOCAL_SEARCH = "local_search"
  DIRECTIONS = "directions"


class TestSharedRenderingHelpers(unittest.TestCase):
  """Unit tests for shared rendering helpers (wrap_in_text_only and render_template_payload)."""

  def test_wrap_in_text_only_with_session_id(self):
    """Verifies wrap_in_text_only scopes surfaceId with session_id."""
    parts = merger.wrap_in_text_only("Hello world", session_id="sess-123")
    self.assertEqual(len(parts), 2)
    for p in parts:
      self.assertIsInstance(p, Part)
      self.assertIsInstance(p.root, DataPart)

    # Check surfaceId in createSurface
    create_surface = parts[0].root.data["createSurface"]
    self.assertTrue(
        create_surface["surfaceId"].startswith("text-only_sess-123-")
    )

    # Check text content in updateComponents
    update_comps = parts[1].root.data["updateComponents"]
    text_comp = update_comps["components"][1]
    self.assertEqual(text_comp["text"], "Hello world")

  def test_wrap_in_text_only_without_session_id(self):
    """Verifies wrap_in_text_only generates random surfaceId when session_id is empty."""
    parts = merger.wrap_in_text_only("Simple text")
    self.assertEqual(len(parts), 2)
    create_surface = parts[0].root.data["createSurface"]
    self.assertTrue(
        re.fullmatch(r"text-only_[a-f0-9]{8}", create_surface["surfaceId"])
    )

  def test_wrap_in_text_only_explicit_surface_id(self):
    """Verifies wrap_in_text_only respects explicit surface_id override."""
    parts = merger.wrap_in_text_only(
        "Custom ID text", surface_id="my-custom-text-id"
    )
    self.assertEqual(len(parts), 2)
    create_surface = parts[0].root.data["createSurface"]
    self.assertEqual(create_surface["surfaceId"], "my-custom-text-id")

  def test_render_template_payload_local_search_string_intent(self):
    """Verifies render_template_payload with local_search string template name."""
    payload = {
        "summary": "Coffee shops",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 14,
        "places": [
            {"placeId": "p1", "name": "Coffee 1", "lat": 47.61, "lng": -122.31}
        ],
    }
    parts = merger.render_template_payload("local_search", payload)
    self.assertEqual(len(parts), 3)
    for p in parts:
      self.assertIsInstance(p, Part)
      self.assertIsInstance(p.root, DataPart)
    self.assertIn("createSurface", parts[0].root.data)
    self.assertIn("updateComponents", parts[1].root.data)
    self.assertIn("updateDataModel", parts[2].root.data)

  def test_render_template_payload_local_search_enum_intent(self):
    """Verifies render_template_payload with IntentClass.LOCAL_SEARCH."""
    payload = {
        "summary": "Coffee shops",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 14,
        "places": [
            {"placeId": "p1", "name": "Coffee 1", "lat": 47.61, "lng": -122.31}
        ],
    }
    parts = merger.render_template_payload(_TestIntent.LOCAL_SEARCH, payload)
    self.assertEqual(len(parts), 3)

  def test_render_template_payload_directions_string_and_enum(self):
    """Verifies render_template_payload with directions string and enum."""
    payload = {
        "summary": "Route to park",
        "center_lat": 40.7,
        "center_lng": -73.9,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": 40.7, "lng": -73.9, "label": "Start"},
            "destination": {"lat": 40.8, "lng": -73.8, "label": "End"},
        }],
    }
    parts_str = merger.render_template_payload("directions", payload)
    self.assertEqual(len(parts_str), 3)

    parts_enum = merger.render_template_payload(_TestIntent.DIRECTIONS, payload)
    self.assertEqual(len(parts_enum), 3)

  def test_render_template_payload_surface_id_generation_and_override(self):
    """Verifies surface_id generation and explicit override in render_template_payload."""
    base_payload = {
        "summary": "Coffee shops",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 14,
        "places": [
            {"placeId": "p1", "name": "Coffee 1", "lat": 47.61, "lng": -122.31}
        ],
    }
    # Case 1: Omitted -> generated with prefix
    parts1 = merger.render_template_payload("local_search", base_payload)
    surface_id1 = parts1[0].root.data["createSurface"]["surfaceId"]
    self.assertTrue(
        re.fullmatch(r"local-search-surface-[a-f0-9]{8}", surface_id1)
    )

    # Case 2: In payload -> preserved
    payload_with_id = dict(base_payload, surface_id="payload-surface-id")
    parts2 = merger.render_template_payload("local_search", payload_with_id)
    surface_id2 = parts2[0].root.data["createSurface"]["surfaceId"]
    self.assertEqual(surface_id2, "payload-surface-id")

    # Case 3: Explicit argument -> overrides
    parts3 = merger.render_template_payload(
        "local_search", base_payload, surface_id="explicit-arg-id"
    )
    surface_id3 = parts3[0].root.data["createSurface"]["surfaceId"]
    self.assertEqual(surface_id3, "explicit-arg-id")

  def test_render_template_payload_max_list_size_clamping(self):
    """Verifies max_list_size clamps child elements in render_template_payload."""
    places = [
        {
            "placeId": f"p{i}",
            "name": f"P{i}",
            "lat": 47.6 + i * 0.01,
            "lng": -122.3,
        }
        for i in range(5)
    ]
    payload = {
        "summary": "Multiple places",
        "center_lat": 47.6,
        "center_lng": -122.3,
        "zoom": 14,
        "places": places,
    }
    parts = merger.render_template_payload(
        "local_search", payload, max_list_size=2
    )
    # Check updateComponents markers length
    update_comps = parts[1].root.data["updateComponents"]["components"]
    map_comp = next(c for c in update_comps if c.get("id") == "map")
    self.assertEqual(len(map_comp["markers"]), 2)

    # Check updateDataModel places length
    update_data = parts[2].root.data["updateDataModel"]["value"]["places"]
    self.assertEqual(len(update_data), 2)


if __name__ == "__main__":
  unittest.main()
