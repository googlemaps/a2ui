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

"""Tests for the template bundle registry."""

import dataclasses
import enum
import pathlib
import tempfile
import unittest

import pydantic

import template_registry
from templates.directions import schema as directions_schema
from templates.local_search import schema as local_search_schema


class _StubSchema(pydantic.BaseModel):
  """Minimal schema for bundles constructed directly by a test."""

  title: str


def _make_bundle(
    name: str = "custom_poi",
    intent: str = "CUSTOM_POI",
    skill_instructions: str = "",
    tool_description: str = "",
    archetype: str = "",
) -> template_registry.TemplateBundle:
  """Builds a TemplateBundle without touching the filesystem."""
  bundle_dir = pathlib.Path("/nonexistent") / name
  return template_registry.TemplateBundle(
      name=name,
      intent=intent,
      surface_prefix=f"{name.replace('_', '-')}-surface",
      archetype=archetype or f"Archetype for {intent}.",
      few_shot_examples=[{
          "user_query": "Tell me about the Space Needle",
          "intent": intent,
          "query": "Space Needle Seattle",
      }],
      schema_cls=_StubSchema,
      layout_path=bundle_dir / "layout.json",
      skill_dir=bundle_dir,
      bundle_dir=bundle_dir,
      skill_instructions=skill_instructions,
      tool_description=tool_description,
  )


class SchemaResolutionTest(unittest.TestCase):
  """Schemas resolve by import, never by executing a file."""

  def test_builtin_bundles_resolve_schemas(self):
    for bundle_name in ("local_search", "directions"):
      with self.subTest(bundle=bundle_name):
        schema_cls = template_registry._resolve_schema(bundle_name)
        self.assertTrue(issubclass(schema_cls, pydantic.BaseModel))

  def test_unmapped_bundle_raises_key_error(self):
    with self.assertRaises(KeyError):
      template_registry._resolve_schema("no_such_bundle")

  def test_resolved_class_is_the_statically_imported_class(self):
    """Guards against a second copy of each schema class in the process.

    A registry that executes templates/<name>/schema.py directly defines a
    class distinct from the one the build system compiles into the library,
    so isinstance checks fail across the two copies.
    """
    registry = template_registry.TemplateRegistry()

    self.assertIs(
        registry.get_bundle("local_search").schema_cls,
        local_search_schema.ExtractorSchema,
    )
    self.assertIs(
        registry.get_bundle("directions").schema_cls,
        directions_schema.ExtractorSchema,
    )


class DiscoveryTest(unittest.TestCase):
  """Discovery of the bundles shipped in templates/."""

  def setUp(self):
    super().setUp()
    self.registry = template_registry.TemplateRegistry()

  def test_discovers_builtin_bundles(self):
    names = {bundle.name for bundle in self.registry.list_bundles()}
    self.assertIn("local_search", names)
    self.assertIn("directions", names)

  def test_populates_bundle_from_manifest(self):
    bundle = self.registry.get_bundle("local_search")

    self.assertEqual(bundle.intent, "LOCAL_SEARCH")
    self.assertEqual(bundle.surface_prefix, "local-search-surface")
    self.assertIn("points of interest", bundle.archetype)
    self.assertEqual(len(bundle.few_shot_examples), 1)
    self.assertEqual(
        bundle.few_shot_examples[0]["user_query"],
        "Find coffee shops near Central Park",
    )

  def test_bundle_assets_exist_on_disk(self):
    for bundle in self.registry.list_bundles():
      with self.subTest(bundle=bundle.name):
        self.assertTrue(bundle.layout_path.exists())
        self.assertTrue((bundle.skill_dir / "SKILL.md").exists())
        self.assertGreater(len(bundle.skill_instructions), 0)
        self.assertFalse(bundle.skill_instructions.startswith("---"))

  def test_supported_intents(self):
    self.assertEqual(
        self.registry.supported_intents, {"LOCAL_SEARCH", "DIRECTIONS"}
    )

  def test_discovery_order_is_deterministic(self):
    self.assertEqual(
        [bundle.name for bundle in self.registry.list_bundles()],
        ["directions", "local_search"],
    )


class GetBundleTest(unittest.TestCase):
  """Lookup by name, by intent, and by enum-like key."""

  def setUp(self):
    super().setUp()
    self.registry = template_registry.TemplateRegistry()

  def test_lookup_by_name(self):
    self.assertEqual(
        self.registry.get_bundle("local_search").name, "local_search"
    )

  def test_lookup_by_intent(self):
    self.assertEqual(
        self.registry.get_bundle_by_intent("LOCAL_SEARCH").name, "local_search"
    )

  def test_lookup_by_enum_like_object(self):
    class MockEnum:
      value = "DIRECTIONS"

    bundle = self.registry.get_bundle_by_intent(MockEnum())
    self.assertEqual(bundle.name, "directions")

  def test_unknown_key_returns_none(self):
    self.assertIsNone(self.registry.get_bundle("NOT_A_TEMPLATE"))
    self.assertIsNone(self.registry.get_bundle_by_intent("NOT_AN_INTENT"))

  def test_built_in_bundles_load_empty_fallback_text(self):
    local_search = self.registry.get_bundle("local_search")
    self.assertEqual(
        local_search.empty_fallback_text,
        "No places matching your query could be found.",
    )
    directions = self.registry.get_bundle("directions")
    self.assertEqual(
        directions.empty_fallback_text,
        "Could not calculate travel directions.",
    )


class RegisterBundleTest(unittest.TestCase):
  """register_bundle takes a constructed bundle and nothing else."""

  def setUp(self):
    super().setUp()
    self.registry = template_registry.TemplateRegistry()

  def test_registers_bundle_and_intent(self):
    bundle = _make_bundle()
    self.registry.register_bundle(bundle)

    self.assertIs(self.registry.get_bundle("custom_poi"), bundle)
    self.assertIs(self.registry.get_bundle_by_intent("CUSTOM_POI"), bundle)
    self.assertIn("CUSTOM_POI", self.registry.supported_intents)

  def test_registers_intent_with_the_router(self):
    self.registry.register_bundle(_make_bundle(intent="ROUTER_VISIBLE_INTENT"))

    classification = self.registry.router_classification(
        intent="ROUTER_VISIBLE_INTENT", query="anything"
    )
    self.assertEqual(classification.intent, "ROUTER_VISIBLE_INTENT")
    self.assertIn("ROUTER_VISIBLE_INTENT", self.registry.supported_intents)

  def test_router_classification_rejects_unregistered_intent(self):
    with self.assertRaises(pydantic.ValidationError):
      self.registry.router_classification(
          intent="UNREGISTERED_INTENT", query="anything"
      )

  def test_router_classification_generates_dynamic_enum_schema(self):
    schema = self.registry.router_classification
    self.assertTrue(issubclass(schema, template_registry.RouterClassification))
    intent_field = schema.model_fields["intent"]
    self.assertTrue(issubclass(intent_field.annotation, enum.Enum))
    self.assertTrue(issubclass(intent_field.annotation, str))

    classification = schema(intent="LOCAL_SEARCH", query="coffee near me")
    self.assertEqual(classification.intent, "LOCAL_SEARCH")

    with self.assertRaises(pydantic.ValidationError):
      schema(intent="INVALID_INTENT", query="coffee near me")

  def test_router_classification_is_cached(self):
    first = self.registry.router_classification
    second = self.registry.router_classification
    self.assertIs(first, second)

    self.registry.register_bundle(_make_bundle(intent="DYNAMIC_INTENT"))
    third = self.registry.router_classification
    self.assertIsNot(first, third)
    classification = third(intent="DYNAMIC_INTENT", query="test query")
    self.assertEqual(classification.intent, "DYNAMIC_INTENT")

  def test_registered_intent_stays_out_of_other_registries(self):
    self.registry.register_bundle(_make_bundle(intent="ROUTER_VISIBLE_INTENT"))
    other = template_registry.TemplateRegistry()

    self.assertNotIn("ROUTER_VISIBLE_INTENT", other.supported_intents)
    self.assertIsNone(other.get_bundle_by_intent("ROUTER_VISIBLE_INTENT"))

  def test_replacing_a_bundle_logs_a_warning(self):
    self.registry.register_bundle(_make_bundle())
    replacement = _make_bundle()

    with self.assertLogs(template_registry.__name__, level="WARNING") as logs:
      self.registry.register_bundle(replacement)

    self.assertIs(self.registry.get_bundle("custom_poi"), replacement)
    self.assertIn("already registered", "\n".join(logs.output))

  def test_stealing_an_intent_drops_the_displaced_bundle(self):
    self.registry.register_bundle(_make_bundle(name="first", intent="SHARED"))

    with self.assertLogs(template_registry.__name__, level="WARNING") as logs:
      self.registry.register_bundle(
          _make_bundle(name="second", intent="SHARED")
      )

    self.assertEqual(
        self.registry.get_bundle_by_intent("SHARED").name, "second"
    )
    self.assertIn("SHARED", "\n".join(logs.output))
    # The displaced bundle is unroutable, so it must not linger in either
    # index where it would still reach the router prompt.
    self.assertIsNone(self.registry.get_bundle("first"))
    self.assertNotIn(
        "first", [bundle.name for bundle in self.registry.list_bundles()]
    )

  def test_renaming_an_intent_drops_the_stale_intent_key(self):
    self.registry.register_bundle(_make_bundle(name="poi", intent="OLD"))

    with self.assertLogs(template_registry.__name__, level="WARNING"):
      self.registry.register_bundle(_make_bundle(name="poi", intent="NEW"))

    self.assertIsNone(self.registry.get_bundle_by_intent("OLD"))
    self.assertNotIn("OLD", self.registry.supported_intents)
    self.assertIn("NEW", self.registry.supported_intents)


class CompileRouterInstructionTest(unittest.TestCase):
  """The router prompt is assembled from whatever is registered."""

  def setUp(self):
    super().setUp()
    self.registry = template_registry.TemplateRegistry()
    self.instruction = self.registry.compile_router_instruction()

  def test_contains_registered_archetypes(self):
    self.assertIn("- **LOCAL_SEARCH**", self.instruction)
    self.assertIn("- **DIRECTIONS**", self.instruction)

  def test_contains_pinned_non_template_archetypes(self):
    self.assertIn("- **OTHER_SPATIAL**", self.instruction)
    self.assertIn("- **TEXT_ONLY**", self.instruction)
    self.assertIn("Conservative Routing", self.instruction)

  def test_contains_bundle_few_shot_examples(self):
    self.assertIn("Find coffee shops near Central Park", self.instruction)
    self.assertIn(
        "Directions from Sacramento to Mendocino via Clear Lake",
        self.instruction,
    )

  def test_registered_bundle_reaches_the_prompt(self):
    self.registry.register_bundle(_make_bundle())
    instruction = self.registry.compile_router_instruction()

    self.assertIn("- **CUSTOM_POI**", instruction)
    self.assertIn("Tell me about the Space Needle", instruction)

  def test_bundle_order_follows_intent_not_registration_order(self):
    """A late registration still lands in intent order, not at the end."""
    self.registry.register_bundle(
        _make_bundle(name="alpha_poi", intent="ALPHA_POI")
    )
    instruction = self.registry.compile_router_instruction()

    self.assertLess(
        instruction.index("- **ALPHA_POI**"),
        instruction.index("- **DIRECTIONS**"),
    )
    self.assertLess(
        instruction.index("Tell me about the Space Needle"),
        instruction.index("Directions from Sacramento to Mendocino"),
    )

  def test_matches_the_golden_prompt(self):
    """The compiled prompt matches a checked-in copy of its own output.

    The golden holds every archetype line and few-shot example that used to
    be hardcoded in `router_config.ROUTER_SYSTEM_INSTRUCTION`, with bundle
    entries reordered by intent. Pinning it here means a change to any
    manifest surfaces as a reviewable diff on the prompt itself rather than
    silently altering what the router sees.
    """
    golden_path = pathlib.Path(__file__).parent / "testdata"
    golden = (golden_path / "router_instruction.golden.txt").read_text()

    self.maxDiff = None
    self.assertEqual(self.instruction, golden)


class SkillInstructionsTest(unittest.TestCase):
  """Tests for _read_skill_instructions and TemplateBundle.skill_instructions."""

  def test_loads_and_strips_frontmatter(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      skill_dir = pathlib.Path(tmp_dir)
      skill_file = skill_dir / "SKILL.md"
      skill_file.write_text(
          "---\nname: test_bundle\ndescription: Test\n---\n\n# Header\nBody",
          encoding="utf-8",
      )
      self.assertEqual(
          template_registry._read_skill_instructions(skill_dir),
          "# Header\nBody",
      )

  def test_returns_content_without_frontmatter(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      skill_dir = pathlib.Path(tmp_dir)
      skill_file = skill_dir / "SKILL.md"
      skill_file.write_text(
          "# Header\nBody without frontmatter", encoding="utf-8"
      )
      self.assertEqual(
          template_registry._read_skill_instructions(skill_dir),
          "# Header\nBody without frontmatter",
      )

  def test_missing_skill_file_returns_empty_string(self):
    self.assertEqual(
        template_registry._read_skill_instructions(
            pathlib.Path("/nonexistent")
        ),
        "",
    )
    bundle = _make_bundle()
    self.assertEqual(bundle.skill_instructions, "")

  def test_built_in_bundles_have_non_empty_instructions(self):
    registry = template_registry.TemplateRegistry()
    local_search = registry.get_bundle("local_search")
    self.assertIsNotNone(local_search)
    self.assertIn("# Local Search Guidelines", local_search.skill_instructions)
    directions = registry.get_bundle("directions")
    self.assertIsNotNone(directions)
    self.assertIn("# Directions Guidelines", directions.skill_instructions)


class BundlePropertiesTest(unittest.TestCase):
  """Tests for derived bundle properties."""

  def test_render_tool_name(self):
    bundle = _make_bundle(name="custom_poi")
    self.assertEqual(bundle.render_tool_name, "render_custom_poi_template")

  def test_built_in_bundles_render_tool_names(self):
    registry = template_registry.TemplateRegistry()
    local_search = registry.get_bundle("local_search")
    self.assertEqual(
        local_search.render_tool_name, "render_local_search_template"
    )
    directions = registry.get_bundle("directions")
    self.assertEqual(directions.render_tool_name, "render_directions_template")


class EffectiveToolDescriptionTest(unittest.TestCase):
  """Tests for TemplateBundle.effective_tool_description."""

  def test_returns_tool_description_when_specified(self):
    bundle = _make_bundle(
        name="custom_poi",
        tool_description="Custom tool description for POI.",
        archetype="General POI queries.",
    )
    self.assertEqual(
        bundle.effective_tool_description, "Custom tool description for POI."
    )

  def test_falls_back_to_archetype_when_empty(self):
    bundle = _make_bundle(
        name="custom_poi",
        tool_description="",
        archetype="Finding specific tourist landmarks.",
    )
    self.assertEqual(
        bundle.effective_tool_description,
        "Renders the custom_poi UI component. Use it when the request matches:"
        " Finding specific tourist landmarks.",
    )

  def test_built_in_bundles_have_effective_tool_descriptions(self):
    registry = template_registry.TemplateRegistry()
    for bundle in registry.list_bundles():
      self.assertTrue(bundle.effective_tool_description)
      self.assertIn(
          bundle.effective_tool_description,
          [
              bundle.tool_description,
              (
                  f"Renders the {bundle.name} UI component. Use it when the"
                  f" request matches: {bundle.archetype}"
              ),
          ],
      )


if __name__ == "__main__":
  unittest.main()
