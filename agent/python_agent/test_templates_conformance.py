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

from a2ui.inference_formats.direct_json import DirectJsonParser
import agent
import template_registry
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


# Hosts can cite the places and routes a card shows by numbering them in the
# order they appear in the template's data. The helpers below check the data
# and layout shapes that numbering relies on.

# Keys of map-only pins: copies of the card's places drawn on the map, and
# extra pins such as an anchor location. A pin is never counted as a place.
_PIN_KEYS = frozenset({"markers", "anchor_marker", "anchorMarker"})
_ROUTE_END_KEYS = ("origin", "destination")
# Fields that name or identify a place or a route end. The model-written text
# that citations can be attached to is in the other fields.
_IDENTITY_KEYS = frozenset({"name", "label", "placeId"})


def _is_place(node: dict[str, Any]) -> bool:
  return isinstance(node.get("placeId"), str) and isinstance(
      node.get("name"), str
  )


def _has_route_end(node: dict[str, Any]) -> bool:
  return any(end in node for end in _ROUTE_END_KEYS)


def _is_route(node: dict[str, Any]) -> bool:
  return all(
      isinstance(node.get(end), dict)
      and isinstance(node[end].get("label"), str)
      for end in _ROUTE_END_KEYS
  )


def _shape_problems(node: Any, path: str = "data") -> list[str]:
  """Returns where places, routes and map pins break the citation shapes.

  A place has a string `placeId` and `name`, a route has an `origin` and a
  `destination` that each have a string `label`, and a map pin under a key in
  `_PIN_KEYS` has no `name`, so it is never counted as a place.

  Args:
    node: Template data, or a part of it.
    path: Where `node` is, for the messages.

  Returns:
    One message per problem, empty when the shapes are right.
  """
  problems = []

  def walk(node: Any, path: str, in_pin: bool) -> None:
    if isinstance(node, list):
      for index, item in enumerate(node):
        walk(item, f"{path}[{index}]", in_pin)
      return
    if not isinstance(node, dict):
      return
    if _has_route_end(node):
      for end in _ROUTE_END_KEYS:
        value = node.get(end)
        if not (
            isinstance(value, dict) and isinstance(value.get("label"), str)
        ):
          problems.append(f"{path}: route {end} needs a string label")
      return
    if "placeId" in node:
      if in_pin and "name" in node:
        problems.append(f"{path}: map pin has a name, so it counts as a place")
      if not in_pin and not _is_place(node):
        problems.append(f"{path}: place needs a string placeId and name")
    for key, value in node.items():
      walk(value, f"{path}.{key}", in_pin or key in _PIN_KEYS)

  walk(node, path, in_pin=False)
  return problems


def _has_required_string(definition: dict[str, Any], field: str) -> bool:
  return (
      field in definition.get("required", ())
      and definition.get("properties", {}).get(field, {}).get("type")
      == "string"
  )


def _named_models_without_place_id(schema: dict[str, Any]) -> list[str]:
  """Returns the JSON schema objects with a `name` but no required place shape.

  A place without a required string `placeId` and `name` is not counted, so the
  citation numbers of every place after it would point at the wrong place.

  Args:
    schema: A Pydantic model's JSON schema.
  """
  objects = {"root": schema, **schema.get("$defs", {})}
  return [
      title
      for title, definition in objects.items()
      if "name" in definition.get("properties", {})
      and not (
          _has_required_string(definition, "placeId")
          and _has_required_string(definition, "name")
      )
  ]


def _place_ids(node: Any) -> list[str]:
  """Returns the placeIds of the places in template data, in order."""
  if isinstance(node, list):
    ids = []
    for item in node:
      ids.extend(_place_ids(item))
    return ids
  if not isinstance(node, dict):
    return []
  if _is_place(node):
    return [node["placeId"]]
  if _is_route(node):
    return []
  ids = []
  for value in node.values():
    ids.extend(_place_ids(value))
  return ids


def _route_labels(node: Any) -> list[tuple[str, str]]:
  """Returns each route's (origin, destination) labels, in order."""
  if isinstance(node, list):
    routes = []
    for item in node:
      routes.extend(_route_labels(item))
    return routes
  if not isinstance(node, dict) or _is_place(node):
    return []
  if _is_route(node):
    return [(node["origin"]["label"], node["destination"]["label"])]
  routes = []
  for value in node.values():
    routes.extend(_route_labels(value))
  return routes


def _shown_place_ids(node: Any) -> list[str]:
  """Returns the placeIds rendered messages carry, in order, without pins."""
  if isinstance(node, list):
    ids = []
    for item in node:
      ids.extend(_shown_place_ids(item))
    return ids
  if not isinstance(node, dict) or _is_route(node):
    return []
  ids = []
  for key, value in node.items():
    if key == "placeId" and isinstance(value, str):
      ids.append(value)
    elif key not in _PIN_KEYS:
      ids.extend(_shown_place_ids(value))
  return ids


def _place_list_paths(node: Any, top_level: bool = True) -> set[str]:
  """Returns the data paths of every list that holds places."""
  paths = set()
  if isinstance(node, list):
    for item in node:
      paths.update(_place_list_paths(item, top_level=False))
  elif isinstance(node, dict):
    for key, value in node.items():
      if key in _PIN_KEYS:
        continue
      if isinstance(value, list) and _place_ids(value):
        paths.add(f"/{key}" if top_level else key)
      paths.update(_place_list_paths(value, top_level=False))
  return paths


def _extra_copy(node: Any) -> Any:
  """Returns `node` with `-extra` suffixed onto its placeIds and labels."""
  if isinstance(node, list):
    return [_extra_copy(item) for item in node]
  if isinstance(node, dict):
    return {
        key: (
            f"{value}-extra"
            if key in ("placeId", "label") and isinstance(value, str)
            else _extra_copy(value)
        )
        for key, value in node.items()
    }
  return node


def _bound_paths(messages: Any) -> set[str]:
  """Returns the data model paths the rendered components bind to."""
  paths = set()

  def walk(node: Any) -> None:
    if isinstance(node, list):
      for item in node:
        walk(item)
    elif isinstance(node, dict):
      if isinstance(node.get("path"), str):
        paths.add(node["path"])
      for value in node.values():
        walk(value)

  for message in messages:
    walk(message.get("updateComponents", {}))
  return paths


def _model_text(node: Any, key: str = "") -> list[tuple[str, str]]:
  """Returns (field, text) for the model-written prose in template data.

  Prose is any string with a space outside `_IDENTITY_KEYS` and map pins, so
  single-word values such as ids and enum values are skipped.

  Args:
    node: Template data, or a part of it.
    key: The field `node` is in.

  Returns:
    The (field, text) pairs, in order.
  """
  if isinstance(node, str):
    return [(key, node)] if " " in node and key not in _IDENTITY_KEYS else []
  if isinstance(node, list):
    pairs = []
    for item in node:
      pairs.extend(_model_text(item, key))
    return pairs
  if isinstance(node, dict):
    pairs = []
    for child_key, value in node.items():
      if child_key not in _PIN_KEYS:
        pairs.extend(_model_text(value, child_key))
    return pairs
  return []


def _contains_text(node: Any, text: str) -> bool:
  """Returns whether any string under `node` contains `text`."""
  if isinstance(node, str):
    return text in node
  if isinstance(node, list):
    return any(_contains_text(item, text) for item in node)
  if isinstance(node, dict):
    return any(_contains_text(value, text) for value in node.values())
  return False


def _text_component_shows(messages: Any, field: str, text: str) -> bool:
  """Returns whether a `Text` component shows `text` from `field`.

  Only `Text` turns citation markers into chips, so model-written text must be
  shown by it: literally, or bound to the field with a data path and carried in
  `updateDataModel`.

  Args:
    messages: The rendered A2UI messages.
    field: The data field the text came from.
    text: The text.
  """
  in_data_model = any(
      _contains_text(m.get("updateDataModel", {}), text) for m in messages
  )
  for message in messages:
    components = message.get("updateComponents", {}).get("components", [])
    for component in components:
      if component.get("component") != "Text":
        continue
      value = component.get("text")
      if isinstance(value, str) and text in value:
        return True
      if (
          isinstance(value, dict)
          and value.get("path") in (field, f"/{field}")
          and in_data_model
      ):
        return True
  return False


class CitationShapeHelpersTest(unittest.TestCase):
  """Checks that the citation shape helpers catch broken templates."""

  def test_shape_problems_accepts_places_routes_and_pins(self):
    data = {
        "places": [{"placeId": "a", "name": "A"}],
        "markers": [{"placeId": "a", "label": "A"}],
        "routes": [{"origin": {"label": "A"}, "destination": {"label": "B"}}],
    }

    self.assertEqual(_shape_problems(data), [])

  def test_shape_problems_flags_place_without_name(self):
    self.assertEqual(
        _shape_problems({"places": [{"placeId": "a", "title": "A"}]}),
        ["data.places[0]: place needs a string placeId and name"],
    )

  def test_shape_problems_flags_map_pin_with_name(self):
    self.assertEqual(
        _shape_problems({"markers": [{"placeId": "a", "name": "A"}]}),
        ["data.markers[0]: map pin has a name, so it counts as a place"],
    )

  def test_shape_problems_flags_route_end_without_label(self):
    self.assertEqual(
        _shape_problems(
            {"routes": [{"origin": {"lat": 1}, "destination": {"label": "B"}}]}
        ),
        ["data.routes[0]: route origin needs a string label"],
    )

  def test_named_models_without_place_id_flags_optional_place_id_or_name(self):
    """Flags place models where `placeId` or `name` is optional."""

    class Place(pydantic.BaseModel):
      placeId: str  # pylint: disable=invalid-name
      name: str

    class OptionalIdVenue(pydantic.BaseModel):
      placeId: str | None = None  # pylint: disable=invalid-name
      name: str

    class OptionalNameVenue(pydantic.BaseModel):
      placeId: str  # pylint: disable=invalid-name
      name: str | None = None

    class Card(pydantic.BaseModel):
      places: list[Place]
      venue_one: OptionalIdVenue
      venue_two: OptionalNameVenue

    self.assertEqual(
        _named_models_without_place_id(Card.model_json_schema()),
        ["OptionalIdVenue", "OptionalNameVenue"],
    )

  def test_place_ids_and_route_labels_follow_data_order(self):
    """Returns placeIds, route labels and place list paths in data order."""
    data = {
        "groups": [
            {"places": [{"placeId": "b", "name": "B"}]},
            {"places": [{"placeId": "a", "name": "A"}]},
        ],
        "markers": [{"placeId": "b", "label": "B"}],
        "routes": [{
            "origin": {"label": "X", "placeId": "x"},
            "destination": {"label": "Y"},
        }],
    }

    self.assertEqual(_place_ids(data), ["b", "a"])
    self.assertEqual(_route_labels(data), [("X", "Y")])
    self.assertEqual(_place_list_paths(data), {"/groups", "places"})

  def test_shown_place_ids_skips_pins_and_route_ends(self):
    """Returns rendered placeIds without map pins or route ends."""
    rendered = [{
        "markers": [{"placeId": "pin"}],
        "routes": [{
            "origin": {"label": "A", "placeId": "end"},
            "destination": {"label": "B"},
        }],
        "card": {"placeId": "a"},
        "places": [{"placeId": "b", "name": "B"}],
    }]

    self.assertEqual(_shown_place_ids(rendered), ["a", "b"])

  def test_bound_paths_reads_only_components(self):
    messages = [
        {
            "updateComponents": {
                "components": [{"children": {"path": "/places"}}]
            }
        },
        {"updateDataModel": {"path": "/"}},
    ]

    self.assertEqual(_bound_paths(messages), {"/places"})

  def test_model_text_skips_identity_fields_pins_and_single_words(self):
    data = {
        "heading": "Coffee near you",
        "travel_mode": "walking",
        "places": [{"name": "Blue Bottle", "description": "Cozy spot."}],
        "markers": [{"label": "Blue Bottle"}],
    }

    self.assertEqual(
        _model_text(data),
        [("heading", "Coffee near you"), ("description", "Cozy spot.")],
    )

  def test_text_component_shows_literal_and_bound_text(self):
    """Checks literal text and path-bound text present in `updateDataModel`."""
    messages = [
        {
            "updateComponents": {
                "components": [
                    {"component": "Text", "text": "### Coffee near you"},
                    {"component": "Text", "text": {"path": "description"}},
                    {"component": "Text", "text": {"path": "/summary"}},
                    {"component": "Text", "text": {"path": "dropped"}},
                    {"component": "Button", "text": "Open the map"},
                ]
            }
        },
        {
            "updateDataModel": {
                "value": {
                    "summary": "All good.",
                    "places": [{"description": "Cozy spot."}],
                }
            }
        },
    ]

    self.assertTrue(
        _text_component_shows(messages, "heading", "Coffee near you")
    )
    self.assertTrue(
        _text_component_shows(messages, "description", "Cozy spot.")
    )
    self.assertTrue(_text_component_shows(messages, "summary", "All good."))
    self.assertFalse(
        _text_component_shows(messages, "dropped", "Not in data model.")
    )
    self.assertFalse(_text_component_shows(messages, "action", "Open the map"))


class ConformanceFewShotExample(pydantic.BaseModel):
  """Strongly typed few-shot example for bundle router prompt injection."""

  model_config = pydantic.ConfigDict(extra="forbid")

  user_query: str = pydantic.Field(min_length=1)
  intent: str = pydantic.Field(min_length=1)


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
    catalog = agent.MergedCatalogProvider(
        agent.VERSION_0_9, str(extension_path)
    ).load()
    cls.parser = DirectJsonParser([catalog])

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

  def test_bundle_heading_strips_markdown_hashtags(self):
    """Verifies every bundle's ExtractorSchema strips leading markdown '#' from heading."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        manifest = self._load_bundle_manifest(bundle)
        example = dict(manifest.conformance_example)
        example["heading"] = "### Conformance Heading"
        validated = bundle.schema_cls.model_validate(example)
        self.assertEqual(validated.heading, "Conformance Heading")

  def test_bundle_summary_normalizes_markdown(self):
    """Verifies that bundles with a summary field normalize markdown bullets."""
    for bundle in self.bundles:
      if "summary" in bundle.schema_cls.model_fields:
        with self.subTest(bundle=bundle.name):
          manifest = self._load_bundle_manifest(bundle)
          example = dict(manifest.conformance_example)
          example["summary"] = "Intro overview.\\n* Bullet item"
          validated = bundle.schema_cls.model_validate(example)
          self.assertEqual(
              validated.summary, "Intro overview.\n\n* Bullet item"
          )

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

  def test_bundle_skill_instructions_exclude_mcp_tool_names(self):
    """Verifies bundle SKILL.md files do not hardcode MCP or rendering tool names."""
    forbidden_mcp_terms = (
        "search_places",
        "compute_routes",
        "radiusMeters",
        "locationBias",
        "render_local_search_template",
        "render_directions_template",
        "render_nearby_places_depth_template",
        "render_place_answer_factual_template",
    )
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        for term in forbidden_mcp_terms:
          self.assertNotIn(
              term,
              bundle.skill_instructions,
              f"Bundle '{bundle.name}' SKILL.md should not contain MCP tool"
              f" term '{term}'",
          )

  def test_bundle_catalog_schema_compliance(self):
    """Verifies that rendered layouts pass A2UI catalog schema validation."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        manifest = self._load_bundle_manifest(bundle)
        merged_messages = merge_template(
            bundle.name, manifest.conformance_example
        )
        self.parser.parse_response(json.dumps(merged_messages), wrapped=False)

  def _validated_example(
      self, bundle: template_registry.TemplateBundle
  ) -> dict[str, Any]:
    """Returns the conformance example as the template tool validates it."""
    example = self._load_bundle_manifest(bundle).conformance_example
    return bundle.schema_cls.model_validate(example).model_dump(
        exclude_none=True
    )

  def test_bundle_places_routes_and_pins_have_citation_shapes(self):
    """Verifies places, routes and map pins can be told apart and numbered."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        self.assertEqual(
            _named_models_without_place_id(
                bundle.schema_cls.model_json_schema()
            ),
            [],
        )
        data = self._validated_example(bundle)
        self.assertTrue(
            _place_ids(data) or _route_labels(data),
            "conformance_example has no places or routes to check.",
        )
        self.assertEqual(_shape_problems(data), [])

  def test_bundle_shows_places_and_routes_in_data_order(self):
    """Verifies the surface carries exactly the kept places and routes.

    Hosts cut each top-level list to `max_list_size` and number what is left,
    so the surface must carry those places and routes in data order, with no
    extras, and bind every list of places to a component.
    """
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        validated = self._validated_example(bundle)
        # The model numbers `[cite:N]` by the order of its tool call arguments,
        # and hosts number the validated data, so validation must keep that
        # order. The lists are reversed so that sorting them would show.
        example = self._load_bundle_manifest(bundle).conformance_example
        reversed_example = {
            key: value[::-1] if isinstance(value, list) else value
            for key, value in example.items()
        }
        revalidated = bundle.schema_cls.model_validate(
            reversed_example
        ).model_dump(exclude_none=True)
        self.assertEqual(_place_ids(revalidated), _place_ids(reversed_example))
        self.assertEqual(
            _route_labels(revalidated), _route_labels(reversed_example)
        )
        over_limit = {}
        cut = 1
        for key, value in validated.items():
          if (
              isinstance(value, list)
              and key not in _PIN_KEYS
              and (_place_ids(value) or _route_labels(value))
          ):
            cut = len(value)
            over_limit[key] = value + [_extra_copy(value[-1])]
          else:
            over_limit[key] = value

        for data, max_list_size in ((validated, 100), (over_limit, cut)):
          messages = merge_template(
              bundle.name, data, max_list_size=max_list_size
          )
          self.assertEqual(_shown_place_ids(messages), _place_ids(validated))
          self.assertEqual(_route_labels(messages), _route_labels(validated))
          self.assertTrue(
              _place_list_paths(validated).issubset(_bound_paths(messages))
          )

  def test_bundle_model_text_is_shown_by_text_components(self):
    """Verifies model-written text is shown by `Text`, which shows citations."""
    for bundle in self.bundles:
      with self.subTest(bundle=bundle.name):
        validated = self._validated_example(bundle)
        messages = merge_template(bundle.name, validated)
        prose = _model_text(validated)
        self.assertTrue(prose, "Found no model-written text to check.")
        for field, text in prose:
          self.assertTrue(
              _text_component_shows(messages, field, text),
              f"'{field}' text is not shown by a Text component: {text!r}",
          )

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
