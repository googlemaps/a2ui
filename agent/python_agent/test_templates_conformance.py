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

"""Build-time conformance test suite for A2UI template directory bundles."""

import json
import pathlib
import re
from typing import Any
import unittest

from google.adk import features as adk_features
from google.adk import skills as adk_skills
import pydantic

import a2ui
import agent
import (
    template_registry,
)
from merger import (
    merge_template,
)


def _extract_placeholders(obj: Any) -> set[str]:
  """Recursively extracts all {{placeholder}} tokens from a JSON structure."""
  placeholders = set()
  if isinstance(obj, str):
    matches = re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", obj)
    placeholders.update(matches)
  elif isinstance(obj, list):
    for item in obj:
      placeholders.update(_extract_placeholders(item))
  elif isinstance(obj, dict):
    for value in obj.values():
      placeholders.update(_extract_placeholders(value))
  return placeholders


class ConformanceFewShotExample(pydantic.BaseModel):
  """Strongly typed few-shot example for bundle router prompt injection."""

  model_config = pydantic.ConfigDict(extra="forbid")

  user_query: str = pydantic.Field(min_length=1)
  intent: str = pydantic.Field(min_length=1)
  query: str = pydantic.Field(min_length=1)


class BundleManifestModel(pydantic.BaseModel):
  """Strongly typed manifest model for bundle conformance validation."""

  model_config = pydantic.ConfigDict(extra="forbid")

  intent: str = pydantic.Field(min_length=1)
  surface_prefix: str = pydantic.Field(min_length=1)
  archetype: str = pydantic.Field(min_length=1)
  empty_fallback_text: str = pydantic.Field(min_length=1)
  conformance_example: dict[str, Any]
  few_shot_examples: list[ConformanceFewShotExample] = pydantic.Field(
      min_length=1
  )
  tool_description: str | None = None

  @pydantic.model_validator(mode="after")
  def validate_few_shot_intents(self) -> "BundleManifestModel":
    for example in self.few_shot_examples:
      if example.intent != self.intent:
        raise ValueError(
            f"Few-shot example intent '{example.intent}' does not match"
            f" manifest intent '{self.intent}'."
        )
    return self


class TestTemplatesConformance(unittest.TestCase):
  """Validates template bundle structure, schemas, and layouts."""

  maxDiff = None

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    adk_features.override_feature_enabled(
        adk_features.FeatureName.SNAKE_CASE_SKILL_NAME, True
    )
    cls.package_dir = pathlib.Path(__file__).parent
    extension_path = (
        cls.package_dir / "shared" / "schema" / "maps_catalog_extension.json"
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
    cls.validator = schema_manager.get_selected_catalog().validator

    # Discover through the production registry so this suite validates the
    # bundles the agent will actually serve, not a parallel reimplementation.
    cls.bundles = template_registry.TemplateRegistry().list_bundles()

  def _load_bundle_manifest(
      self, bundle: template_registry.TemplateBundle
  ) -> BundleManifestModel:
    """Loads and validates manifest.json against BundleManifestModel."""
    manifest_path = bundle.bundle_dir / "manifest.json"
    self.assertTrue(
        manifest_path.exists(),
        f"Manifest file {manifest_path} does not exist for bundle"
        f" {bundle.name}",
    )
    return BundleManifestModel.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

  def test_discovered_at_least_one_bundle(self):
    """Ensures at least local_search and directions bundles are discovered."""
    bundle_names = {bundle.name for bundle in self.bundles}
    self.assertIn("local_search", bundle_names)
    self.assertIn("directions", bundle_names)

  def test_bundle_manifest_conformance(self):
    """Verifies manifest.json contains required metadata and examples."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        self._load_bundle_manifest(bundle)

        # `clamped_collections` is optional, but when a bundle declares it
        # every name must be a real field, or the extractor prompt would tell
        # the model to limit something that does not exist.
        for collection in getattr(bundle.schema_cls, "clamped_collections", ()):
          self.assertIn(collection, bundle.schema_cls.model_fields)

  def test_bundle_schema_exports_extractor_schema(self):
    """Verifies that schema.py exports an ExtractorSchema BaseModel."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        self.assertTrue((bundle.bundle_dir / "schema.py").exists())
        self.assertTrue(issubclass(bundle.schema_cls, pydantic.BaseModel))

  def test_bundle_schema_validates_conformance_example(self):
    """Verifies each bundle's conformance_example passes schema validation."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        manifest = self._load_bundle_manifest(bundle)

        # Directly validate against the Pydantic schema class to ensure
        # invalid data fails loudly at build time rather than falling back.
        validated_model = bundle.schema_cls.model_validate(
            manifest.conformance_example
        )
        self.assertIsNotNone(validated_model)

  def test_bundle_layout_placeholder_alignment(self):
    """Verifies every {{placeholder}} in layout.json exists in schema fields."""
    framework_placeholders = {"surface_id", "catalog_id"}

    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        self.assertTrue(bundle.layout_path.exists())
        with open(bundle.layout_path, "r", encoding="utf-8") as layout_file:
          layout_data = json.load(layout_file)

        model_fields = set(bundle.schema_cls.model_fields.keys())
        computed_fields = set(
            getattr(
                bundle.schema_cls, "__pydantic_computed_fields__", {}
            ).keys()
        )
        available_fields = (
            model_fields | computed_fields | framework_placeholders
        )

        placeholders = _extract_placeholders(layout_data)
        missing_fields = placeholders - available_fields
        self.assertFalse(
            missing_fields,
            f"Bundle '{bundle.name}' layout.json contains placeholders with no"
            " matching field or computed_field in ExtractorSchema:"
            f" {missing_fields}",
        )

  def test_bundle_skill_conformance(self):
    """Verifies that SKILL.md conforms to the ADK skill specification."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        skill = adk_skills.load_skill_from_dir(bundle.skill_dir)
        self.assertEqual(skill.frontmatter.name, bundle.name)
        self.assertTrue(skill.frontmatter.description)
        self.assertGreater(len(skill.instructions), 0)
        self.assertEqual(bundle.skill_instructions, skill.instructions)

  def test_bundle_catalog_schema_compliance(self):
    """Verifies that rendered layouts pass A2UI catalog schema validation."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        manifest = self._load_bundle_manifest(bundle)
        merged_messages = merge_template(
            bundle.name, manifest.conformance_example
        )
        self.validator.validate(merged_messages)

  def test_merged_output_matches_golden(self):
    """Verifies rendered layouts match checked-in golden A2UI wire messages."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        golden_file = bundle.bundle_dir / "testdata" / "merged.golden.json"
        self.assertTrue(
            golden_file.exists(),
            f"Golden file {golden_file} does not exist for bundle"
            f" {bundle.name}",
        )
        expected_messages = json.loads(golden_file.read_text(encoding="utf-8"))

        manifest = self._load_bundle_manifest(bundle)
        actual_messages = merge_template(
            bundle.name, manifest.conformance_example
        )
        self.assertEqual(actual_messages, expected_messages)


if __name__ == "__main__":
  unittest.main()
