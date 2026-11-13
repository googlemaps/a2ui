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

"""After-tool callback for grounding tools in MAUI Agent."""

from collections.abc import Callable
import json
import logging
import re
from typing import Any

from templates.common import haversine_distance
from templates.common import is_superlative_proximity_query
from templates.common import parse_user_coordinates
from templates.common import sort_extracted_places_by_proximity

logger = logging.getLogger(__name__)

# Tracks the current prompt invocation_id per underlying state dictionary so
# maps_tools_content_tokens is only kept in tool_context for a single prompt.
_state_invocation_ids: dict[int, Any] = {}

# Road network detour and average travel speed constants for routing.
# Empirical urban street network factor relative to great-circle distance.
_ROAD_DETOUR_FACTOR = 1.3
# Average urban pedestrian walking speed: 4.8 km/h = 80.0 m/min.
_WALK_METERS_PER_MIN = 80.0
# Average urban automobile driving speed: 32 km/h = 533.33 m/min.
_DRIVE_METERS_PER_MIN = 533.33


def extract_user_query(tool_context: Any) -> str:
  """Extracts user query string from tool context state or user_content."""
  if tool_context is None:
    return ""

  state = getattr(tool_context, "state", None)
  if state is not None:
    get_fn = getattr(state, "get", None)
    if callable(get_fn):
      uq = get_fn("user_query")
      if isinstance(uq, str) and uq:
        return uq

  user_content = getattr(tool_context, "user_content", None)
  if user_content is not None:
    parts = getattr(user_content, "parts", None)
    if isinstance(parts, (list, tuple)):
      for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text:
          lines = text.splitlines()
          if lines and lines[0].strip().startswith("[TARGET_INTENT:"):
            return "\n".join(lines[1:]).strip()
          return text.strip()

  return ""


def _extract_place_label(place: dict[str, Any]) -> str:
  """Extracts display label from PlaceView following real Maps MCP schema."""
  attribution = place.get("attribution")
  if isinstance(attribution, dict):
    title = attribution.get("title")
    if isinstance(title, str) and title:
      if title.endswith(" - Google Maps"):
        return title[: -len(" - Google Maps")].strip()
      return title.strip()

  display_name = place.get("displayName")
  if isinstance(display_name, dict):
    text = display_name.get("text")
    if isinstance(text, str) and text:
      return text.strip()

  name = place.get("name")
  if isinstance(name, str) and name:
    return name.strip()

  place_id = place.get("id") or place.get("place")
  if isinstance(place_id, str) and place_id:
    return place_id.strip()

  return "Place"


def enrich_search_places_with_routing(
    tool_response: dict[str, Any],
    origin: tuple[float, float],
    *,
    sort_closest_first: bool = False,
    route_matrix_fn: Callable[..., Any] | None = None,
) -> bool:
  """Enriches places in tool_response with travel metrics and optionally sorts closest first.

  Args:
      tool_response: The Maps MCP tool response dictionary.
      origin: Origin coordinate tuple (latitude, longitude).
      sort_closest_first: If True, sorts places ascending by proximity.
      route_matrix_fn: Optional injectable route matrix provider function.

  Returns:
      True if places were enriched, False otherwise.
  """
  if not tool_response or not isinstance(tool_response, dict):
    return False

  structured_content = tool_response.get("structuredContent")
  if not isinstance(structured_content, dict):
    return False

  places = structured_content.get("places")
  if not isinstance(places, list) or not places:
    return False

  destinations: list[tuple[int, tuple[float, float]]] = []
  for idx, place in enumerate(places):
    if not isinstance(place, dict):
      continue
    loc = place.get("location")
    if isinstance(loc, dict):
      lat = loc.get("latitude")
      lng = loc.get("longitude")
      if lat is not None and lng is not None:
        try:
          destinations.append((idx, (float(lat), float(lng))))
        except (ValueError, TypeError):
          pass

  if not destinations:
    return False

  place_dist_m: dict[int, float] = {}

  if callable(route_matrix_fn):
    try:
      custom_metrics = route_matrix_fn(origin, [d[1] for d in destinations])
      if isinstance(custom_metrics, list):
        for d_idx, item in enumerate(custom_metrics):
          if d_idx < len(destinations) and isinstance(item, dict):
            orig_place_idx = destinations[d_idx][0]
            dist_m = item.get("distanceMeters")
            if dist_m is not None:
              place_dist_m[orig_place_idx] = float(dist_m)
              km = dist_m / 1000.0
              miles = km * 0.621371
              places[orig_place_idx][
                  "distanceFromQueryLocation"
              ] = f"{miles:.1f} mi ({km:.1f} km)"
              drive_mins = item.get("driveMinutes")
              walk_mins = item.get("walkMinutes")
              if walk_mins is None:
                walk_mins = max(1, round(float(dist_m) / _WALK_METERS_PER_MIN))
              if drive_mins is None:
                drive_mins = max(
                    1, round(float(dist_m) / _DRIVE_METERS_PER_MIN)
                )
              places[orig_place_idx][
                  "travelTimeFromQueryLocation"
              ] = f"{walk_mins} mins walk, {drive_mins} mins drive"
    except Exception as e:  # pylint: disable=broad-exception-caught
      logger.debug("Custom route_matrix_fn failed: %s", e)

  # Fallback to deterministic road-adjusted Haversine
  for orig_place_idx, coords in destinations:
    if orig_place_idx not in place_dist_m:
      h_dist = haversine_distance(origin, coords)
      place_dist_m[orig_place_idx] = h_dist
      road_m = h_dist * _ROAD_DETOUR_FACTOR
      km = road_m / 1000.0
      miles = km * 0.621371
      walk_mins = max(1, round(road_m / _WALK_METERS_PER_MIN))
      drive_mins = max(1, round(road_m / _DRIVE_METERS_PER_MIN))
      places[orig_place_idx][
          "distanceFromQueryLocation"
      ] = f"{miles:.1f} mi ({km:.1f} km)"
      places[orig_place_idx][
          "travelTimeFromQueryLocation"
      ] = f"{walk_mins} mins walk, {drive_mins} mins drive"

  existing_summary = structured_content.get("summary")
  summary_text = existing_summary if isinstance(existing_summary, str) else ""

  # Sort closest first if requested
  original_order = list(places)
  if sort_closest_first and len(places) >= 2:
    self_anchors = []
    others = []
    for p in places:
      orig_idx = original_order.index(p)
      d = place_dist_m.get(orig_idx, float("inf"))
      if d < 15.0:
        self_anchors.append((d, p))
      else:
        others.append((d, p))
    others.sort(key=lambda item: item[0])
    places[:] = [item[1] for item in self_anchors] + [
        item[1] for item in others
    ]

    # If places order changed, remap [0], [1] citations in existing summary
    if places != original_order and summary_text:
      old_to_new = {
          orig_idx: places.index(p) for orig_idx, p in enumerate(original_order)
      }

      def _remap_match(m: re.Match[str]) -> str:
        try:
          old_idx = int(m.group(1))
          return f"[{old_to_new.get(old_idx, old_idx)}]"
        except ValueError:
          return m.group(0)

      summary_text = re.sub(r"\[(\d+)\]", _remap_match, summary_text)

  # Build and append proximity block on both sort_closest_first=True and False
  proximity_places = [p for p in places if p.get("distanceFromQueryLocation")]
  if proximity_places:
    proximity_lines = "\n".join(
        f"- **{_extract_place_label(p)}**: "
        f"{p.get('distanceFromQueryLocation', '')}, "
        f"{p.get('travelTimeFromQueryLocation', '')}"
        for p in proximity_places
    )
    proximity_block = f"Proximity from origin:\n{proximity_lines}"
    structured_content["summary"] = (
        f"{summary_text}\n\n{proximity_block}"
        if summary_text.strip()
        else proximity_block
    )
  elif summary_text:
    structured_content["summary"] = summary_text

  # Update content text preserving JSON structure
  content = tool_response.get("content")
  if isinstance(content, list):
    for content_item in content:
      if not isinstance(content_item, dict):
        continue
      raw_text = content_item.get("text")
      if not isinstance(raw_text, str):
        continue
      if raw_text.lstrip().startswith("{"):
        try:
          parsed = json.loads(raw_text)
          if isinstance(parsed, dict) and "places" in parsed:
            content_item["text"] = json.dumps(structured_content)
            continue
        except (ValueError, TypeError):
          pass
      current_summary = structured_content.get("summary")
      if isinstance(current_summary, str):
        content_item["text"] = current_summary

  return True


def after_tools_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
    **kwargs: Any,
) -> Any:
  """Callback to aggregate grounding_content_token into session state."""
  # pylint: disable=unused-argument
  after_maps_tools_callback(tool_context, tool_response, tool=tool, args=args)
  return None


def after_maps_tools_callback(
    tool_context: Any,
    tool_response: Any,
    tool: Any = None,
    args: dict[str, Any] | None = None,
) -> Any:
  """Callback to aggregate content tokens from Maps Tools for one prompt."""
  # pylint: disable=unused-argument
  if tool_context is None or getattr(tool_context, "state", None) is None:
    return None

  # 1. Reset collected tokens when a new prompt turn (invocation_id) starts.
  state_obj = getattr(tool_context.state, "_value", tool_context.state)
  state_id = id(state_obj)
  invocation_id = getattr(tool_context, "invocation_id", None)
  if invocation_id is not None:
    if (
        state_id in _state_invocation_ids
        and _state_invocation_ids[state_id] != invocation_id
    ):
      if "maps_tools_content_tokens" in tool_context.state:
        tool_context.state["maps_tools_content_tokens"] = []
      if "last_anchor_location" in tool_context.state:
        del tool_context.state["last_anchor_location"]
      if "_pending_place_responses" in tool_context.state:
        tool_context.state["_pending_place_responses"] = []

    while len(_state_invocation_ids) >= 1024:
      _state_invocation_ids.pop(next(iter(_state_invocation_ids)))
    _state_invocation_ids[state_id] = invocation_id

  if not tool_response or not isinstance(tool_response, dict):
    return None

  # 2. Extract contentToken from the Maps Grounding Lite MCP tool response.
  structured_content = tool_response.get("structuredContent")
  token = (
      structured_content.get("contentToken")
      if isinstance(structured_content, dict)
      else None
  )
  if isinstance(token, str) and token:
    content_tokens = tool_context.state.get("maps_tools_content_tokens", [])
    if not isinstance(content_tokens, list):
      content_tokens = []
    if token not in content_tokens:
      content_tokens.append(token)
    tool_context.state["maps_tools_content_tokens"] = content_tokens
    logger.info(
        "--- after_maps_tools_callback: Aggregated content token into"
        " content_tokens. ---"
    )

  # 3. Proximity enrichment and closest-first sorting
  tool_name = getattr(tool, "name", None)
  if tool_name not in (None, "search_places"):
    return None

  if isinstance(structured_content, dict):
    places = structured_content.get("places")
    if isinstance(places, list) and places:
      user_query = extract_user_query(tool_context)
      sort_closest_first = is_superlative_proximity_query(user_query)

      origin = None
      has_location_bias = False
      if isinstance(args, dict):
        loc_bias = args.get("locationBias") or args.get("location_bias")
        if isinstance(loc_bias, dict):
          circle = loc_bias.get("circle")
          if isinstance(circle, dict):
            center = circle.get("center")
            if isinstance(center, dict):
              lat = center.get("latitude")
              lng = center.get("longitude")
              if lat is not None and lng is not None:
                try:
                  origin = (float(lat), float(lng))
                  has_location_bias = True
                except (ValueError, TypeError):
                  pass

      explicit_query_origin = parse_user_coordinates(user_query)
      if origin is None:
        last_anchor = tool_context.state.get("last_anchor_location")
        if (
            isinstance(last_anchor, (tuple, list))
            and len(last_anchor) == 2
            and all(isinstance(v, (int, float)) for v in last_anchor)
        ):
          origin = (float(last_anchor[0]), float(last_anchor[1]))
        elif explicit_query_origin is not None:
          origin = explicit_query_origin

      if len(places) == 1:
        p0 = places[0]
        p0_loc = p0.get("location") if isinstance(p0, dict) else None
        p0_coords = None
        if isinstance(p0_loc, dict):
          p0_lat = p0_loc.get("latitude")
          p0_lng = p0_loc.get("longitude")
          if p0_lat is not None and p0_lng is not None:
            try:
              p0_coords = (float(p0_lat), float(p0_lng))
            except (ValueError, TypeError):
              pass

        explicit_origin = (
            origin
            if (has_location_bias or explicit_query_origin is not None)
            else None
        )
        if (
            explicit_origin is not None
            and p0_coords is not None
            and haversine_distance(explicit_origin, p0_coords) >= 15.0
        ):
          enrich_search_places_with_routing(
              tool_response,
              explicit_origin,
              sort_closest_first=sort_closest_first,
          )
        elif not has_location_bias and p0_coords is not None:
          if "last_anchor_location" not in tool_context.state:
            tool_context.state["last_anchor_location"] = p0_coords
          pending_list = tool_context.state.get("_pending_place_responses", [])
          for pending in pending_list:
            enrich_search_places_with_routing(
                pending,
                p0_coords,
                sort_closest_first=sort_closest_first,
            )
          if "_pending_place_responses" in tool_context.state:
            tool_context.state["_pending_place_responses"] = []
      else:
        if origin is not None:
          enrich_search_places_with_routing(
              tool_response, origin, sort_closest_first=sort_closest_first
          )
        else:
          pending_list = tool_context.state.setdefault(
              "_pending_place_responses", []
          )
          if len(pending_list) < 16:
            pending_list.append(tool_response)

  return None


def _add_maps_tools_tokens_to_part(part: Any, session: Any) -> None:
  """Adds maps_tools_content_tokens from session state to part metadata."""
  if session is None or getattr(session, "state", None) is None:
    return
  maps_tools_content_tokens = session.state.get("maps_tools_content_tokens")
  if maps_tools_content_tokens:
    if getattr(part, "root", None) is not None:
      if getattr(part.root, "metadata", None) is None:
        part.root.metadata = {}
      part.root.metadata["maps_tools_content_tokens"] = (
          maps_tools_content_tokens
      )


__all__ = [
    "after_maps_tools_callback",
    "after_tools_callback",
    "enrich_search_places_with_routing",
    "extract_user_query",
    "haversine_distance",
    "is_superlative_proximity_query",
    "sort_extracted_places_by_proximity",
]
