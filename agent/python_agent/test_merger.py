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

import pathlib
import re
import unittest

import a2ui
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
    schema_manager = a2ui.schema.manager.A2uiSchemaManager(
        version=a2ui.schema.constants.VERSION_0_9,
        catalogs=[
            a2ui.schema.catalog.CatalogConfig(
                name="maps-agentic-ui-catalog",
                provider=agent.MergedCatalogProvider(
                    a2ui.schema.constants.VERSION_0_9, str(extension_path)
                ),
            )
        ],
        schema_modifiers=[
            a2ui.schema.common_modifiers.remove_strict_validation
        ],
    )
    selected_catalog = schema_manager.get_selected_catalog()
    selected_catalog.validator.validate(result)

  def test_merge_unknown_template_raises_error(self):
    """Verifies that an unknown template raises FileNotFoundError."""
    with self.assertRaises(FileNotFoundError):
      merge_template("non_existent_template", {"text": "hello"})

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
                        "children": ["summary-text", "map", "list"],
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
    map_comp = next(c for c in components if c["id"] == "map")
    self.assertEqual(len(map_comp["markers"]), 2)

    # Check that updateDataModel has only 2 places
    places = result[2]["updateDataModel"]["value"]["places"]
    self.assertEqual(len(places), 2)
    self.assertEqual(places[0]["placeId"], "1")
    self.assertEqual(places[1]["placeId"], "2")

  def test_merge_directions_full_json(self):
    """Verifies complete end-to-end directions template merging, placeholder replacement, and travel mode normalization."""
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
                        "children": ["summary-text", "map"],
                    },
                    {
                        "id": "summary-text",
                        "component": "Text",
                        "variant": "body",
                        "text": "Typical commute is 1h 15m.",
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
        c for c in update_components["components"] if c["id"] == "map"
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
        c for c in update_components["components"] if c["id"] == "map"
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


if __name__ == "__main__":
  unittest.main()
