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

"""Unit tests for template_tool.py ADK tools."""

import pathlib
from types import SimpleNamespace
import unittest

from a2a.types import DataPart
from google.adk.tools.tool_context import ToolContext

import a2ui
import agent
import template_tool

BaseTemplateTool = template_tool.BaseTemplateTool
RenderLocalSearchTemplateTool = template_tool.RenderLocalSearchTemplateTool
RenderDirectionsTemplateTool = template_tool.RenderDirectionsTemplateTool
RenderTextOnlyTemplateTool = template_tool.RenderTextOnlyTemplateTool
TemplateToolset = template_tool.TemplateToolset
STATE_RENDERED_A2UI_PARTS = template_tool.STATE_RENDERED_A2UI_PARTS


def _create_schema_manager():
  extension_path = (
      pathlib.Path(__file__).parent
      / "shared"
      / "schema"
      / "maps_catalog_extension.json"
  )
  return a2ui.schema.manager.A2uiSchemaManager(
      version=a2ui.schema.constants.VERSION_0_9,
      catalogs=[
          a2ui.schema.catalog.CatalogConfig(
              name="maps-agentic-ui-catalog",
              provider=agent.MergedCatalogProvider(
                  a2ui.schema.constants.VERSION_0_9, str(extension_path)
              ),
          )
      ],
      schema_modifiers=[a2ui.schema.common_modifiers.remove_strict_validation],
  )


class MockToolContext:

  def __init__(self):
    self.state = {}
    self.actions = SimpleNamespace()


class TestTemplateTools(unittest.IsolatedAsyncioTestCase):
  """Unit tests for ADK template tools."""

  def setUp(self):
    super().setUp()
    self.schema_manager = _create_schema_manager()
    self.tool_context = MockToolContext()

  async def test_render_local_search_template_success(self):
    tool = RenderLocalSearchTemplateTool(
        schema_manager=self.schema_manager, max_list_size=3
    )

    args = {
        "summary": "Here are 2 coffee shops.",
        "center_lat": 47.6062,
        "center_lng": -122.3321,
        "zoom": 14,
        "places": [
            {
                "placeId": "ChIJ111",
                "name": "Espresso Vivace",
                "lat": 47.6200,
                "lng": -122.3200,
            },
            {
                "placeId": "ChIJ222",
                "name": "Milstead & Co.",
                "lat": 47.6400,
                "lng": -122.3500,
            },
        ],
    }

    result = await tool.run_async(args=args, tool_context=self.tool_context)

    self.assertEqual(result["status"], "success")
    self.assertEqual(result["template"], "local_search")
    self.assertIn("surface_id", result)

    # Verify session state was populated with A2A parts
    self.assertIn(STATE_RENDERED_A2UI_PARTS, self.tool_context.state)
    parts = self.tool_context.state[STATE_RENDERED_A2UI_PARTS]
    self.assertEqual(len(parts), 3)

    create_surface_data = parts[0].root.data["createSurface"]
    self.assertTrue(
        create_surface_data["surfaceId"].startswith("local-search-surface-")
    )

    update_components = parts[1].root.data["updateComponents"]["components"]
    map_comp = next(c for c in update_components if c["id"] == "map")
    self.assertEqual(len(map_comp["markers"]), 2)

    update_data_model = parts[2].root.data["updateDataModel"]["value"]
    self.assertEqual(len(update_data_model["places"]), 2)

  async def test_render_local_search_template_validation_failure(self):
    tool = RenderLocalSearchTemplateTool(schema_manager=self.schema_manager)

    # Missing mandatory center_lat and center_lng
    args = {
        "summary": "Places without center coordinates",
        "places": [{"placeId": "1", "name": "P1", "lat": 1.0, "lng": 2.0}],
    }

    result = await tool.run_async(args=args, tool_context=self.tool_context)
    self.assertIn("error", result)
    self.assertIn("Validation failed for tool", result["error"])

  async def test_render_directions_template_success(self):
    tool = RenderDirectionsTemplateTool(schema_manager=self.schema_manager)

    args = {
        "summary": "Commute is 30 minutes.",
        "center_lat": 37.7749,
        "center_lng": -122.4194,
        "zoom": 12,
        "routes": [{
            "origin": {
                "lat": 37.7749,
                "lng": -122.4194,
                "label": "San Francisco",
                "placeId": "ChIJ_SF",
            },
            "destination": {
                "lat": 37.8044,
                "lng": -122.2712,
                "label": "Oakland",
                "placeId": "ChIJ_OAK",
            },
        }],
        "travel_mode": "driving",
    }

    result = await tool.run_async(args=args, tool_context=self.tool_context)

    self.assertEqual(result["status"], "success")
    self.assertEqual(result["template"], "directions")

    self.assertIn(STATE_RENDERED_A2UI_PARTS, self.tool_context.state)
    parts = self.tool_context.state[STATE_RENDERED_A2UI_PARTS]
    self.assertEqual(len(parts), 3)

    update_components = parts[1].root.data["updateComponents"]["components"]
    map_comp = next(c for c in update_components if c["id"] == "map")
    self.assertEqual(map_comp["travelMode"], "driving")
    self.assertEqual(len(map_comp["routes"]), 1)

  async def test_render_directions_template_invalid_travel_mode_fails(self):
    tool = RenderDirectionsTemplateTool(schema_manager=self.schema_manager)

    args = {
        "summary": "Commute",
        "center_lat": 37.7,
        "center_lng": -122.4,
        "zoom": 12,
        "routes": [{
            "origin": {"lat": 37.7, "lng": -122.4, "label": "A"},
            "destination": {"lat": 37.8, "lng": -122.3, "label": "B"},
        }],
        "travel_mode": "ROCKET_SHIP",  # Invalid mode
    }

    result = await tool.run_async(args=args, tool_context=self.tool_context)
    self.assertIn("error", result)

  async def test_render_text_only_template_success(self):
    tool = RenderTextOnlyTemplateTool(schema_manager=self.schema_manager)

    args = {
        "text": "Hello world from text-only template.",
    }

    result = await tool.run_async(args=args, tool_context=self.tool_context)

    self.assertEqual(result["status"], "success")
    self.assertEqual(result["template"], "text_only")

    self.assertIn(STATE_RENDERED_A2UI_PARTS, self.tool_context.state)
    parts = self.tool_context.state[STATE_RENDERED_A2UI_PARTS]
    self.assertEqual(len(parts), 2)
    text_comp = parts[1].root.data["updateComponents"]["components"][1]
    self.assertEqual(text_comp["text"], "Hello world from text-only template.")

  async def test_template_toolset_returns_tools(self):
    toolset = TemplateToolset(
        schema_manager=self.schema_manager, max_list_size=3
    )
    tools = await toolset.get_tools()

    self.assertEqual(len(tools), 3)
    tool_names = [t.name for t in tools]
    self.assertIn("render_local_search_template", tool_names)
    self.assertIn("render_directions_template", tool_names)
    self.assertIn("render_text_only_template", tool_names)

  def test_tool_declarations_valid(self):
    tool_ls = RenderLocalSearchTemplateTool(schema_manager=self.schema_manager)
    decl_ls = tool_ls._get_declaration()
    self.assertIsNotNone(decl_ls)
    self.assertEqual(decl_ls.name, "render_local_search_template")

    tool_dir = RenderDirectionsTemplateTool(schema_manager=self.schema_manager)
    decl_dir = tool_dir._get_declaration()
    self.assertIsNotNone(decl_dir)
    self.assertEqual(decl_dir.name, "render_directions_template")

    tool_text = RenderTextOnlyTemplateTool(schema_manager=self.schema_manager)
    decl_text = tool_text._get_declaration()
    self.assertIsNotNone(decl_text)
    self.assertEqual(decl_text.name, "render_text_only_template")


if __name__ == "__main__":
  unittest.main()
