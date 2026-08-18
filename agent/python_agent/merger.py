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

This module loads declarative JSON layout skeletons (`templates/*.json`),
populates them with extracted parameter dictionaries (`data`), and returns
sanitized message structures ready for wire transmission.
"""

import copy
import json
import os
from typing import Any, Literal, TypedDict
import uuid

from python_agent.extractor import normalize_travel_mode


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
  """Recursively replaces string placeholders in the template with values from data."""
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
  """Recursively removes None values from dicts and lists to satisfy JSON schemas."""
  if isinstance(val, dict):
    return {k: _remove_none_values(v) for k, v in val.items() if v is not None}
  elif isinstance(val, list):
    return [_remove_none_values(item) for item in val if item is not None]
  return val


def _prepare_local_search(
    data: dict[str, Any], max_list_size: int
) -> tuple[str, dict[str, Any]]:
  """Validates and normalizes parameters for the local search template."""
  data_copy = copy.deepcopy(data)
  is_valid = True
  places = data_copy.get("places")

  # 1. Validate that places is a non-empty list
  if not isinstance(places, list) or not places:
    is_valid = False
  else:
    # Slice and sanitize places list
    sanitized_places = []
    for p in places:
      if isinstance(p, dict):
        try:
          p["lat"] = float(p["lat"])
          p["lng"] = float(p["lng"])
          sanitized_places.append(p)
        except (KeyError, ValueError, TypeError):
          pass
    if not sanitized_places:
      is_valid = False
    else:
      data_copy["places"] = sanitized_places[:max_list_size]

  # 2. Validate mandatory map centering and zoom parameters
  if is_valid:
    try:
      data_copy["center_lat"] = float(data_copy["center_lat"])
      data_copy["center_lng"] = float(data_copy["center_lng"])
      data_copy["zoom"] = int(data_copy["zoom"])
    except (KeyError, ValueError, TypeError):
      is_valid = False

  # 3. Sanitize optional anchor marker
  if is_valid and "anchor_marker" in data_copy:
    pin = data_copy["anchor_marker"]
    if isinstance(pin, dict):
      try:
        pin["lat"] = float(pin["lat"])
        pin["lng"] = float(pin["lng"])
      except (KeyError, ValueError, TypeError):
        data_copy["anchor_marker"] = None
    else:
      data_copy["anchor_marker"] = None

  # 4. Unroll maps markers array
  if is_valid:
    if "markers" not in data_copy:
      markers = []
      for p in data_copy["places"]:
        marker = {
            "lat": p["lat"],
            "lng": p["lng"],
            "label": p.get("name") or p.get("label") or "",
        }
        if "placeId" in p:
          marker["placeId"] = p["placeId"]
        markers.append(marker)
      data_copy["markers"] = markers
    else:
      markers = data_copy["markers"]
      if isinstance(markers, list):
        sanitized_markers = []
        for m in markers:
          if isinstance(m, dict):
            try:
              m["lat"] = float(m["lat"])
              m["lng"] = float(m["lng"])
              m["label"] = str(m.get("label") or "")
              sanitized_markers.append(m)
            except (KeyError, ValueError, TypeError):
              pass
        data_copy["markers"] = sanitized_markers
      else:
        data_copy["markers"] = None

  # If validation failed, fallback to text_only
  if not is_valid:
    return "text_only", {
        "text": (
            data.get("summary")
            or "No places matching your query could be found."
        ),
        "surface_id": data_copy.get("surface_id") or "fallback-surface",
    }

  return "local_search", data_copy


def _prepare_directions(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
  """Validates and normalizes parameters for the directions template."""
  data_copy = copy.deepcopy(data)
  is_valid = True

  routes = data_copy.get("routes")

  # 1. Validate that routes is a non-empty list of segment dicts
  if not isinstance(routes, list) or not routes:
    is_valid = False
  else:
    sanitized_routes = []
    for segment in routes:
      if not isinstance(segment, dict):
        is_valid = False
        break
      origin = segment.get("origin")
      destination = segment.get("destination")
      if not isinstance(origin, dict) or not isinstance(destination, dict):
        is_valid = False
        break
      try:
        sanitized_origin = {
            "lat": float(origin["lat"]),
            "lng": float(origin["lng"]),
            "label": str(origin.get("label") or ""),
        }
        if "placeId" in origin:
          sanitized_origin["placeId"] = str(origin["placeId"])

        sanitized_destination = {
            "lat": float(destination["lat"]),
            "lng": float(destination["lng"]),
            "label": str(destination.get("label") or ""),
        }
        if "placeId" in destination:
          sanitized_destination["placeId"] = str(destination["placeId"])

        sanitized_routes.append({
            "origin": sanitized_origin,
            "destination": sanitized_destination,
        })
      except (KeyError, ValueError, TypeError):
        is_valid = False
        break
    data_copy["routes"] = sanitized_routes

  # 2. Validate mandatory map centering and zoom parameters
  if is_valid:
    try:
      data_copy["center_lat"] = float(data_copy["center_lat"])
      data_copy["center_lng"] = float(data_copy["center_lng"])
      data_copy["zoom"] = int(data_copy["zoom"])
    except (KeyError, ValueError, TypeError):
      is_valid = False

  # 3. Normalize travel_mode
  if is_valid and "travel_mode" in data_copy:
    normalized = normalize_travel_mode(data_copy["travel_mode"])
    if normalized:
      data_copy["travel_mode"] = normalized
    else:
      del data_copy["travel_mode"]

  # If validation failed, fallback to text_only
  if not is_valid:
    return "text_only", {
        "text": data.get("summary") or "Could not calculate travel directions.",
        "surface_id": data_copy.get("surface_id") or "fallback-surface",
    }

  return "directions", data_copy


def merge_template(
    template_name: str, data: dict[str, Any], max_list_size: int = 5
) -> list[MergedMessage]:
  """Loads static template skeleton JSON and returns merged wire response.

  This function sanitizes extracted parameters and populates the layout
  template skeleton.

  Args:
      template_name: Target declarative layout skeleton (`local_search`,
        `directions`, or `text_only`).
      data: Raw dictionary of extracted parameters yielded by
        `TemplateExtractor` (e.g. `places`, `summary`, `center_lat`).
      max_list_size: Maximum allowable child elements in lists (`places`) to
        bound payload rendering latency.

  Returns:
      A list of message dictionaries. For `text_only`, returns the 2-part A2UI
      layout (`createSurface`, `updateComponents`).
      For `local_search` and `directions`, returns the 3-part A2UI layout
      (`createSurface`, `updateComponents`, `updateDataModel`) (`DataPart`).

  Raises:
      FileNotFoundError: If the template file cannot be found.
  """

  # Deep copy data to prevent unintended side-effects on caller dictionaries
  # across turns
  data_copy = copy.deepcopy(data)

  if template_name == "local_search":
    template_name, data_copy = _prepare_local_search(data_copy, max_list_size)
  elif template_name == "directions":
    template_name, data_copy = _prepare_directions(data_copy)
  current_dir = os.path.dirname(os.path.abspath(__file__))
  templates_dir = os.path.join(current_dir, "templates")
  template_path = os.path.join(templates_dir, f"{template_name}.json")

  if not os.path.exists(template_path):
    raise FileNotFoundError(
        f"Template '{template_name}' not found at {template_path}"
    )

  with open(template_path, "r") as f:
    template_json = json.load(f)

  # Smart Turn-Unique `surface_id` Scoping via Dynamic Template Discovery:
  default_surface_ids = set()
  if os.path.exists(templates_dir):
    for fn in os.listdir(templates_dir):
      if fn.endswith(".json"):
        base_name = fn[:-5]
        default_surface_ids.add(f"{base_name}_surface")
        default_surface_ids.add(f"{base_name.replace('_', '-')}-surface")

  if (
      not data_copy.get("surface_id")
      or data_copy.get("surface_id") in default_surface_ids
  ):
    base_id = data_copy.get("surface_id") or f"{template_name}_surface"
    data_copy["surface_id"] = f"{base_id}_{uuid.uuid4().hex[:6]}"

  resolved_json = _replace_placeholders(template_json, data_copy)
  return _remove_none_values(resolved_json)
