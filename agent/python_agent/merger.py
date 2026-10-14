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

"""Server-Side A2UI Layout Template Merger (`merger.py`).

This module loads a declarative JSON layout skeleton, populates it with a
dictionary of extracted parameters, and returns sanitized message structures
ready for wire transmission.

The merger is template agnostic. Everything specific to one template -- its
schema, its layout, and what to say when it cannot render -- arrives as caller
arguments. Derived and repaired fields belong in the bundle's Pydantic schema,
never here.
"""

import copy
import importlib.resources
import json
import logging
import re
from typing import Any, Literal, TypedDict
import uuid

import pydantic

import (
    template_registry,
)

logger = logging.getLogger(__name__)

# The bare text surface every template degrades to when it cannot render.
_TEXT_ONLY_TEMPLATE = "text_only"

# The catalog the templates bind their surface to when the host does not name
# one. Hosts that register the Maps components in a catalog of their own (for
# example Gemini Enterprise, whose composite catalog carries `GoogleMap` and
# `PlaceDetailsCompact` alongside its Material and basic components) pass that
# catalog's id instead, because a surface resolves against exactly one catalog.
DEFAULT_CATALOG_ID = "a2ui://maps-agentic-ui-catalog.json"


class TextOutputDict(TypedDict):
  type: Literal["text"]
  text: str


SurfaceActionDict = TypedDict(
    "SurfaceActionDict",
    {
        "surfaceId": str,
        "catalogId": str,
        "root": str,
        "components": list[dict[str, Any]],
        "path": str,
        "value": Any,
    },
    total=False,
)


SurfaceOutputDict = TypedDict(
    "SurfaceOutputDict",
    {
        "version": str,
        "createSurface": SurfaceActionDict,
        "updateComponents": SurfaceActionDict,
        "updateDataModel": SurfaceActionDict,
        "deleteSurface": SurfaceActionDict,
    },
    total=False,
)


MergedMessage = TextOutputDict | SurfaceOutputDict


def _replace_placeholders(obj: Any, data: dict[str, Any]) -> Any:
  """Recursively replaces string placeholders in the template with values.

  Args:
    obj: The JSON-serializable template object.
    data: Key-value pairs used to substitute placeholders.

  Returns:
    The updated template object with resolved placeholder values.
  """
  if isinstance(obj, str):
    # Exact match: "{{key}}"
    if obj.startswith("{{") and obj.endswith("}}") and obj.count("{{") == 1:
      key = obj[2:-2]
      if key in data:
        return data[key]
      return None
    # Partial match: string formatting
    else:
      resolved = obj
      for key, value in data.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder in resolved:
          if isinstance(value, (str, int, float, bool)):
            resolved = resolved.replace(placeholder, str(value))
      return resolved
  elif isinstance(obj, list):
    return [_replace_placeholders(item, data) for item in obj]
  elif isinstance(obj, dict):
    return {k: _replace_placeholders(v, data) for k, v in obj.items()}
  else:
    return obj


def _remove_none_values(val: Any) -> Any:
  """Recursively removes None values from dicts/lists to satisfy schemas."""
  if isinstance(val, dict):
    return {k: _remove_none_values(v) for k, v in val.items() if v is not None}
  elif isinstance(val, list):
    return [_remove_none_values(item) for item in val if item is not None]
  return val


def _uniquify_surface_id(
    data: dict[str, Any], template_name: str, surface_prefix: str | None
) -> None:
  """Appends a random suffix when the surface id is a shared default.

  Surfaces keyed by a bundle's default id would collide across concurrent
  turns, so only an id the caller chose itself survives untouched.

  Args:
    data: Parameter dict, mutated in place.
    template_name: Name of the bundle being rendered.
    surface_prefix: The bundle's declared default surface id, if any.
  """
  default_ids = {
      f"{template_name}_surface",
      f"{template_name.replace('_', '-')}-surface",
      "fallback-surface",
  }
  if surface_prefix:
    default_ids.add(surface_prefix)

  surface_id = data.get("surface_id")
  if surface_id and surface_id not in default_ids:
    return
  base_id = surface_id or f"{template_name}_surface"
  data["surface_id"] = f"{base_id}_{uuid.uuid4().hex[:6]}"


def _merge_fallback(
    data: dict[str, Any],
    empty_fallback_text: str,
    catalog_id: str = DEFAULT_CATALOG_ID,
) -> list[MergedMessage]:
  """Renders a template's fallback text on a bare text-only surface."""
  return merge_template(
      _TEXT_ONLY_TEMPLATE,
      {
          "text": data.get("summary") or empty_fallback_text,
          "surface_id": data.get("surface_id") or "fallback-surface",
      },
      catalog_id=catalog_id,
  )


def merge_template(
    template_name: str,
    data: dict[str, Any],
    max_list_size: int = 5,
    catalog_id: str = DEFAULT_CATALOG_ID,
) -> list[MergedMessage]:
  """Populates a layout skeleton with extracted parameters.

  Args:
      template_name: Name of the bundle whose layout to render, or 'text_only'.
      data: Extracted parameters to populate the layout with.
      max_list_size: Maximum number of elements retained in any top-level
        collection, to bound payload size and render latency.
      catalog_id: Catalog the created surface binds to. Defaults to the Maps
        catalog; hosts that register the Maps components under a catalog of
        their own pass that id.

  Returns:
      A list of message dictionaries for A2UI transmission.

  Raises:
      FileNotFoundError: If the template or its layout file cannot be found.
  """
  # Templates ship as package data. They are resolved through
  # `importlib.resources` rather than a `__file__`-relative filesystem path
  # because the agent is also served from a zip-imported archive, where
  # `__file__` names an entry inside the archive that never exists on disk and
  # every `os.path` probe against it reports missing.
  templates_dir = importlib.resources.files(__package__).joinpath("templates")
  resource_path = f"templates/{template_name}/layout.json"
  template_path = templates_dir.joinpath(template_name, "layout.json")

  if template_name == _TEXT_ONLY_TEMPLATE:
    schema_class = None
    empty_fallback_text = ""
    surface_prefix = "text-only-surface"
  else:
    bundle = template_registry.TemplateRegistry().get_bundle(template_name)
    schema_class = bundle.schema_cls if bundle else None
    empty_fallback_text = bundle.empty_fallback_text if bundle else ""
    surface_prefix = (
        bundle.surface_prefix if bundle else f"{template_name}-surface"
    )

  if template_path.is_file():
    template_json = json.loads(template_path.read_text(encoding="utf-8"))
  elif bundle is not None and bundle.layout_path.is_file():
    template_json = json.loads(bundle.layout_path.read_text(encoding="utf-8"))
  else:
    raise FileNotFoundError(
        f"Template '{template_name}' not found: package '{__package__}'"
        f" has no '{resource_path}'"
    )

  data_copy = copy.deepcopy(data)
  data_copy["catalog_id"] = catalog_id

  # 1. Bound every top-level collection to keep payload size predictable.
  for key, value in list(data_copy.items()):
    if isinstance(value, list):
      data_copy[key] = value[:max_list_size]

  # 2. Validate through the bundle's schema. The schema owns every
  #    normalization, derived field, and non-empty constraint, so a collection
  #    the layout cannot render empty fails here and degrades to text. The
  #    dumped model -- not the raw input -- is what feeds the layout.
  if schema_class is not None:
    try:
      model_instance = schema_class.model_validate(data_copy)
    except pydantic.ValidationError:
      logger.warning(
          "Data for template '%s' failed schema validation; degrading to a"
          " text-only surface.",
          template_name,
          exc_info=True,
      )
      return _merge_fallback(data_copy, empty_fallback_text, catalog_id)
    data_copy.update(model_instance.model_dump())

  # 3. Scope the surface id to this turn so repeated renders do not collide.
  _uniquify_surface_id(data_copy, template_name, surface_prefix)

  resolved_json = _replace_placeholders(template_json, data_copy)
  # Prune keys whose optional placeholders (e.g. "{{anchorMarker}}") were
  # absent from data_copy and evaluated to None, keeping wire JSON clean.
  return _remove_none_values(resolved_json)
