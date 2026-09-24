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

"""Dynamic Template Registry and Router Instruction Compiler for MAUI Agent."""

import dataclasses
import enum
import importlib
import json
import logging
import pathlib
from typing import Any

import pydantic

INTENT_OTHER_SPATIAL = "OTHER_SPATIAL"
INTENT_TEXT_ONLY = "TEXT_ONLY"


class RouterClassification(pydantic.BaseModel):
  """Classification output schema for the query intent router."""

  intent: str = pydantic.Field(
      description="The classified intent archetype name."
  )
  query: str = pydantic.Field(description="The cleaned user query")


class FewShotExample(pydantic.BaseModel):
  """A few-shot query-intent example for router instructions."""

  model_config = pydantic.ConfigDict(extra="ignore")

  user_query: str
  intent: str | None = None
  query: str | None = None

  def __getitem__(self, key: str) -> Any:
    return getattr(self, key)

  def get(self, key: str, default: Any = None) -> Any:
    return getattr(self, key, default)


class TemplateManifest(pydantic.BaseModel):
  """Strongly-typed metadata schema parsed from a bundle's manifest.json."""

  model_config = pydantic.ConfigDict(extra="ignore")

  intent: str = ""
  surface_prefix: str | None = None
  archetype: str = ""
  few_shot_examples: list[FewShotExample] = pydantic.Field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class RouterIntentSpec:
  """Specification for a router intent archetype and its few-shot examples."""

  intent: str
  archetype: str
  few_shot_examples: list[FewShotExample] = dataclasses.field(
      default_factory=list
  )


_BUILTIN_FALLBACK_ROUTER_INTENTS: tuple[RouterIntentSpec, ...] = (
    RouterIntentSpec(
        intent=INTENT_OTHER_SPATIAL,
        archetype=(
            "Queries requiring rich map-based visualization, boundaries,"
            " coordinates, specific geographic displays, or complex"
            " navigation combining routes with secondary overlays (e.g.,"
            " weather, air quality forecasts, displaying all available"
            " charging stations along a route)."
        ),
        few_shot_examples=[
            FewShotExample(
                user_query=(
                    "Walking route from Central Park to Times Square, but show"
                    " coffee shops and rain forecasts along the way"
                ),
                intent=INTENT_OTHER_SPATIAL,
                query=(
                    "walking route from Central Park to Times Square with"
                    " coffee shop stops and rain forecast"
                ),
            ),
            FewShotExample(
                user_query=(
                    "show the boundary of Yosemite National Park on the map"
                ),
                intent=INTENT_OTHER_SPATIAL,
                query="boundary of Yosemite National Park",
            ),
        ],
    ),
    RouterIntentSpec(
        intent=INTENT_TEXT_ONLY,
        archetype=(
            "General information retrieval, questions, or requests for data"
            " associated with locations that can be answered fully with text"
            " without requiring a map interface."
        ),
        few_shot_examples=[],
    ),
)


logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class TemplateBundle:
  """Metadata and assets representing a self-contained template intent."""

  name: str
  intent: str
  surface_prefix: str
  archetype: str
  few_shot_examples: list[FewShotExample | dict[str, Any]]
  schema_cls: type[pydantic.BaseModel]
  layout_path: pathlib.Path
  skill_dir: pathlib.Path
  bundle_dir: pathlib.Path
  skill_instructions: str = ""


def _read_skill_instructions(skill_dir: pathlib.Path) -> str:
  """Reads instructions body from SKILL.md directly, stripping frontmatter."""
  skill_file = skill_dir / "SKILL.md"
  if not skill_file.exists():
    return ""
  content = skill_file.read_text(encoding="utf-8")
  if content.startswith("---"):
    parts = content.split("---", 2)
    if len(parts) >= 3:
      return parts[2].strip()
  return content.strip()


_TEMPLATES_PACKAGE = (
    "templates"
)


def _resolve_schema(bundle_name: str) -> type[pydantic.BaseModel]:
  """Imports the ExtractorSchema class declared by a built-in bundle.

  Dynamically resolves the schema module from the templates package
  (e.g., templates.<bundle_name>.schema) without requiring manual allowlist
  registration.

  Args:
    bundle_name: Directory name of the bundle under templates/.

  Returns:
    The bundle's ExtractorSchema class.

  Raises:
    KeyError: The bundle has no importable schema module.
    TypeError: The module does not export an ExtractorSchema that subclasses
      pydantic.BaseModel.
  """
  module_name = f"{_TEMPLATES_PACKAGE}.{bundle_name}.schema"
  try:
    module = importlib.import_module(module_name)
  except ImportError as e:
    raise KeyError(
        f"Bundle '{bundle_name}' has no importable schema module at"
        f" '{module_name}': {e}. Ensure templates/{bundle_name}/schema.py"
        " exists, or build a TemplateBundle and pass it to"
        " TemplateRegistry.register_bundle()."
    ) from e
  schema_cls = getattr(module, "ExtractorSchema", None)
  if not (
      isinstance(schema_cls, type)
      and issubclass(schema_cls, pydantic.BaseModel)
  ):
    raise TypeError(
        f"{module_name} must export 'ExtractorSchema' subclassing"
        " pydantic.BaseModel"
    )
  return schema_cls


class TemplateRegistry:
  """Registry for discovering, caching, and querying template bundles."""

  def __init__(self) -> None:
    self._bundles: dict[str, TemplateBundle] = {}
    self._bundles_by_intent: dict[str, TemplateBundle] = {}
    self._cached_router_classification: type[RouterClassification] | None = None
    self._templates_dir = pathlib.Path(__file__).parent / "templates"

    self._discover_bundles()

  def _discover_bundles(self) -> None:
    """Loads every built-in bundle directory under templates/."""
    if not self._templates_dir.exists():
      logger.warning(
          "Templates directory '%s' does not exist.", self._templates_dir
      )
      return

    for item in sorted(self._templates_dir.iterdir()):
      if item.is_dir() and (item / "manifest.json").exists():
        self._load_bundle(item)

  def _load_bundle(self, bundle_dir: pathlib.Path) -> None:
    """Loads one built-in bundle directory.

    Args:
      bundle_dir: Directory holding the bundle's manifest, layout, and schema.

    Raises:
      ValueError: The manifest is unreadable or malformed.
      KeyError: The bundle has no importable schema module.
      TypeError: The bundle's schema module exports the wrong thing.
      ImportError: The bundle's schema module does not import.
    """
    manifest_path = bundle_dir / "manifest.json"
    try:
      manifest_json = manifest_path.read_text(encoding="utf-8")
      manifest = TemplateManifest.model_validate_json(manifest_json)
    except (OSError, pydantic.ValidationError, ValueError) as e:
      # Built-in bundles ship inside this build target, so an unreadable
      # manifest is a build defect. Booting without the intent would degrade
      # every query that needed it, with nothing but a log line to say why.
      raise ValueError(f"Unreadable bundle manifest at {manifest_path}") from e

    name = bundle_dir.name
    intent = manifest.intent or name.upper()

    surface_prefix = manifest.surface_prefix or f"{name}-surface"
    schema_cls = _resolve_schema(name)

    bundle = TemplateBundle(
        name=name,
        intent=intent,
        surface_prefix=surface_prefix,
        archetype=manifest.archetype,
        few_shot_examples=manifest.few_shot_examples,
        schema_cls=schema_cls,
        layout_path=bundle_dir / "layout.json",
        skill_dir=bundle_dir,
        bundle_dir=bundle_dir,
        skill_instructions=_read_skill_instructions(bundle_dir),
    )
    self.register_bundle(bundle)

  def register_bundle(self, bundle: TemplateBundle) -> None:
    """Registers a constructed TemplateBundle.

    The caller owns importing the bundle's schema class and constructing the
    TemplateBundle. The registry never loads code from a path.

    Args:
      bundle: The bundle to register. It displaces any bundle already holding
        its name or its intent, and the collision is logged. A displaced bundle
        is removed from both indexes so it cannot be routed to or advertised to
        the router afterwards.
    """
    displaced = self._bundles.get(bundle.name)
    if displaced is not None:
      logger.warning(
          "Bundle '%s' is already registered; replacing it.", bundle.name
      )
      self._bundles_by_intent.pop(displaced.intent, None)

    claimant = self._bundles_by_intent.get(bundle.intent)
    if claimant is not None and claimant.name != bundle.name:
      logger.warning(
          "Intent '%s' was claimed by bundle '%s'; bundle '%s' now owns it."
          " Bundle '%s' is dropped, since an unroutable bundle would still"
          " show up in the router prompt.",
          bundle.intent,
          claimant.name,
          bundle.name,
          claimant.name,
      )
      self._bundles.pop(claimant.name, None)

    self._bundles[bundle.name] = bundle
    self._bundles_by_intent[bundle.intent] = bundle
    self._cached_router_classification = None
    logger.info(
        "Registered template bundle: %s (intent: %s)",
        bundle.name,
        bundle.intent,
    )

  def get_bundle(self, name: str) -> TemplateBundle | None:
    """Looks up a bundle by its primary directory/bundle name (e.g., 'local_search')."""
    return self._bundles.get(name)

  def get_bundle_by_intent(
      self, intent: str | enum.Enum
  ) -> TemplateBundle | None:
    """Looks up a bundle by its intent (e.g., 'LOCAL_SEARCH' or an enum member)."""
    key = intent.value if hasattr(intent, "value") else str(intent)
    return self._bundles_by_intent.get(key)

  @property
  def bundles(self) -> dict[str, TemplateBundle]:
    return dict(self._bundles)

  def list_bundles(self) -> list[TemplateBundle]:
    return list(self._bundles.values())

  @property
  def supported_intents(self) -> set[str]:
    return set(self._bundles_by_intent.keys())

  @property
  def router_classification(self) -> type[RouterClassification]:
    """Dynamically constructs a constrained response schema enforcing valid intents."""
    if self._cached_router_classification is not None:
      return self._cached_router_classification

    all_intents = sorted(
        self.supported_intents | {INTENT_OTHER_SPATIAL, INTENT_TEXT_ONLY}
    )
    dynamic_intent_enum = enum.Enum(
        "RouterIntent",
        {intent: intent for intent in all_intents},
        type=str,
    )
    self._cached_router_classification = pydantic.create_model(
        "RouterClassification",
        __base__=RouterClassification,
        intent=(
            dynamic_intent_enum,
            pydantic.Field(description="The classified intent archetype name."),
        ),
        query=(str, pydantic.Field(description="The cleaned user query")),
    )
    return self._cached_router_classification

  def compile_router_instruction(self) -> str:
    """Compiles the dynamic router instruction from the registered bundles.

    Bundles appear in the prompt ordered by intent, so the instruction text
    depends only on which bundles are registered and not on the order they
    were discovered or registered in. Two processes holding the same bundles
    therefore send the model the same bytes.
    """
    ordered_bundles = sorted(
        self._bundles.values(), key=lambda bundle: bundle.intent
    )
    all_intent_specs: list[TemplateBundle | RouterIntentSpec] = [
        *ordered_bundles,
        *_BUILTIN_FALLBACK_ROUTER_INTENTS,
    ]

    archetype_lines = [
        f"- **{spec.intent}**: {spec.archetype}" for spec in all_intent_specs
    ]

    registered_intents_str = (
        " or ".join(sorted(self._bundles_by_intent.keys()))
        or "registered templates"
    )

    examples_blocks = []
    example_index = 1

    for spec in all_intent_specs:
      for example in spec.few_shot_examples:
        user_query = (
            example.user_query
            if isinstance(example, FewShotExample)
            else example.get("user_query", "")
        )
        intent = (
            (example.intent or spec.intent)
            if isinstance(example, FewShotExample)
            else example.get("intent", spec.intent)
        )
        extracted_query = (
            (example.query or user_query)
            if isinstance(example, FewShotExample)
            else example.get("query", user_query)
        )
        output_json = json.dumps(
            {"intent": intent, "query": extracted_query}, indent=2
        )
        examples_blocks.append(
            f"### Example {example_index}\n"
            f'**User Query:** "{user_query}"\n'
            f"**Output:**\n{output_json}\n"
        )
        example_index += 1

    archetypes_str = "\n".join(archetype_lines)
    examples_str = "\n".join(examples_blocks)

    return (
        "## Role\nYou are an expert query intent router.\n\n## Task"
        " Definition\nAnalyze a user's input and classify it into the most"
        " appropriate intent category based on the structural complexity and"
        " data requirements of the request.\n\n## Intent"
        f" Archetypes\n{archetypes_str}\n\n## Classification Policy:"
        " Conservative Routing\nIf a query satisfies the structure of a base"
        f" intent (such as {registered_intents_str}) but also includes any"
        " Auxiliary Data (e.g., weather forecasts, environmental factors), you"
        " MUST promote the classification to OTHER_SPATIAL.\nNote: Simple"
        ' multi-stop routes or routes with specified waypoints (e.g., "A to B'
        ' via C") should be classified as DIRECTIONS, unless they require'
        ' searching for stops along the way (e.g., "find coffee shops along'
        ' the route") which requires LOCAL_SEARCH overlays and should be'
        f" promoted to OTHER_SPATIAL.\n\n## Few-shot Examples\n\n{examples_str}"
    )
