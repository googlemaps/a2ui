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

"""Utility functions for extracting and formatting Google Maps Grounding Sources."""

import re
from typing import Any
import urllib.parse


def extract_location_from_query(query: str | None) -> str | None:
  """Extracts city, neighborhood, or region name from user query string."""
  if not query:
    return None
  cleaned = re.sub(r"^\[.*?\]\s*", "", query).strip()
  first_clause = re.split(r"[.!?\n]", cleaned)[0].strip()
  patterns = [
      r"\b(?:in|near|around|at)\s+([A-Za-z0-9\s,-]+?)(?:\s+(?:with|that|for|and|or|please)|\?|$)",
      r"\bto\s+(?:the\s+)?([A-Za-z0-9\s,-]+?)(?:\s+(?:from|with|for)|\?|$)",
  ]
  for pat in patterns:
    m = re.search(pat, first_clause, re.IGNORECASE)
    if m:
      loc = m.group(1).strip()
      loc = re.sub(r"[,.!?]+$", "", loc).strip()
      if loc.lower().startswith("the "):
        loc = loc[4:].strip()
      if (
          loc
          and len(loc) > 1
          and loc.lower()
          not in (
              "the area",
              "town",
              "my area",
              "here",
          )
      ):
        return loc.title() if loc.islower() else loc
  return None


def simplify_address(address: str | None) -> str | None:
  """Extracts the first line / street address from a full address string."""
  if not address or not isinstance(address, str):
    return None
  first_part = re.split(r"[\n,]", address)[0].strip()
  return first_part if first_part else address.strip()


def format_maps_place_url(place_id: str, query: str | None = None) -> str:
  """Formats a direct canonical URL to a Google Maps place with optional query fallback."""
  clean_place_id = str(place_id).strip()
  if clean_place_id.startswith("places/"):
    clean_place_id = clean_place_id[len("places/") :]

  if query:
    query_for_search = query.replace(" · ", ", ").strip()
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={urllib.parse.quote(query_for_search)}"
        f"&query_place_id={urllib.parse.quote(clean_place_id)}"
    )
  return f"https://www.google.com/maps/place/?q=place_id:{clean_place_id}"


def format_maps_search_url(query: str) -> str:
  """Formats a Google Maps search URL for a query string."""
  return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"


def extract_sources_from_grounding_chunks(
    grounding_chunks: list[Any],
    query: str | None = None,
) -> list[dict[str, str]]:
  """Extracts structured sources from Vertex AI Grounding chunks."""
  sources: list[dict[str, str]] = []
  seen_urls: set[str] = set()
  ignore_title_suffix = " - Google Maps"
  loc_from_query = extract_location_from_query(query)

  for chunk in grounding_chunks:
    if hasattr(chunk, "maps") and chunk.maps:
      title = getattr(chunk.maps, "title", None) or "Google Maps Place"
      place_id = getattr(chunk.maps, "place_id", None)
      uri = getattr(chunk.maps, "uri", None)
      if title.endswith(ignore_title_suffix):
        title = title[: -len(ignore_title_suffix)].strip()

      if place_id and str(place_id).startswith("places/"):
        place_id = str(place_id)[len("places/") :]

      if " · " not in title and loc_from_query:
        display_title = f"{title} · {loc_from_query}"
      else:
        display_title = title

      if uri and ("maps.google." in uri or "google.com/maps" in uri):
        url = uri
      elif place_id:
        url = format_maps_place_url(
            place_id, query=display_title if query else None
        )
      else:
        url = format_maps_search_url(display_title)

      if url not in seen_urls:
        seen_urls.add(url)
        source_entry = {
            "title": display_title,
            "url": url,
            "type": "place",
        }
        if place_id:
          source_entry["placeId"] = place_id
        sources.append(source_entry)

    elif hasattr(chunk, "web") and chunk.web:
      web_title = getattr(chunk.web, "title", None) or "Web Source"
      web_uri = getattr(chunk.web, "uri", None)
      if web_uri and web_uri not in seen_urls:
        seen_urls.add(web_uri)
        sources.append({
            "title": web_title,
            "url": web_uri,
            "type": "web",
        })

  return sources


def extract_sources_from_places_data(
    places: list[dict[str, Any]],
    query: str | None = None,
) -> list[dict[str, str]]:
  """Extracts structured sources from a list of Place objects (e.g.

  from templates).
  """
  sources: list[dict[str, str]] = []
  seen_urls: set[str] = set()
  loc_from_query = extract_location_from_query(query)

  for p in places:
    if not isinstance(p, dict):
      continue
    name = (
        p.get("name") or p.get("title") or p.get("label") or "Google Maps Place"
    )
    address = (
        p.get("formatted_address")
        or p.get("address")
        or p.get("vicinity")
        or p.get("short_formatted_address")
        or p.get("street")
        or p.get("location")
    )
    if not isinstance(address, str):
      address = None

    clean_address = simplify_address(address)
    if clean_address and clean_address not in name:
      display_title = f"{name} · {clean_address}"
    elif loc_from_query and " · " not in name:
      display_title = f"{name} · {loc_from_query}"
    else:
      display_title = name

    place_id = p.get("placeId") or p.get("place_id")
    if place_id and not str(place_id).startswith("PLACE_ID_FOR_"):
      url = format_maps_place_url(str(place_id), query=display_title)
    else:
      url = format_maps_search_url(display_title)

    if url not in seen_urls:
      seen_urls.add(url)
      source_entry = {
          "title": display_title,
          "url": url,
          "type": "place",
      }
      if place_id and not str(place_id).startswith("PLACE_ID_FOR_"):
        source_entry["placeId"] = str(place_id)
      sources.append(source_entry)

  return sources


def extract_sources_from_a2ui_payload(
    payload: Any,
    query: str | None = None,
) -> list[dict[str, str]]:
  """Recursively scans an A2UI message payload or data structure for place sources."""
  sources_by_id: dict[str, dict[str, str]] = {}
  sources_by_name: dict[str, dict[str, str]] = {}
  loc_from_query = extract_location_from_query(query)

  def _scan(obj: Any):
    if isinstance(obj, dict):
      place_id = obj.get("placeId") or obj.get("place_id")
      name = obj.get("name") or obj.get("title") or obj.get("label")
      address = (
          obj.get("formatted_address")
          or obj.get("address")
          or obj.get("vicinity")
          or obj.get("short_formatted_address")
          or obj.get("street")
          or obj.get("streetAddress")
          or obj.get("street_address")
          or obj.get("location")
      )
      if not address and isinstance(obj.get("subtitle"), str):
        # Use subtitle if it looks like a street address (contains digits or street suffix)
        sub = obj.get("subtitle", "")
        if re.search(r"\b\d+\s+[A-Za-z]", sub):
          address = sub
      if not isinstance(address, str):
        address = None

      clean_name = (name or "").strip() if isinstance(name, str) else ""
      clean_address = simplify_address(address)

      if (
          place_id
          and isinstance(place_id, str)
          and not place_id.startswith("PLACE_ID_FOR_")
      ):
        display_name = clean_name or "Google Maps Place"
        if clean_address and clean_address not in display_name:
          display_title = f"{display_name} · {clean_address}"
        elif loc_from_query and " · " not in display_name:
          display_title = f"{display_name} · {loc_from_query}"
        else:
          display_title = display_name

        url = format_maps_place_url(place_id, query=display_title)

        if place_id not in sources_by_id:
          entry = {
              "title": display_title,
              "url": url,
              "type": "place",
              "placeId": place_id,
          }
          if clean_address:
            entry["streetAddress"] = clean_address
          sources_by_id[place_id] = entry
        else:
          existing = sources_by_id[place_id]
          # If current object has real street address, unconditionally enrich the existing entry!
          if clean_address:
            existing_name = display_name
            if (
                existing["title"].split(" · ")[0] != "Google Maps Place"
                and display_name == "Google Maps Place"
            ):
              existing_name = existing["title"].split(" · ")[0]
            new_title = f"{existing_name} · {clean_address}"
            existing["title"] = new_title
            existing["url"] = format_maps_place_url(place_id, query=new_title)
            existing["streetAddress"] = clean_address
          elif (
              existing["title"] == "Google Maps Place"
              and display_name != "Google Maps Place"
          ):
            existing["title"] = display_title
            existing["url"] = url
      elif clean_name and clean_address:
        # Also record name -> streetAddress even if placeId wasn't attached on this inner node
        norm_name = clean_name.lower()
        sources_by_name[norm_name] = {
            "name": clean_name,
            "streetAddress": clean_address,
        }

      for v in obj.values():
        _scan(v)
    elif isinstance(obj, list):
      for item in obj:
        _scan(item)

  _scan(payload)

  # Apply any name-based street addresses to entries in sources_by_id that lacked streetAddress
  for entry in sources_by_id.values():
    if "streetAddress" not in entry:
      base_name = entry["title"].split(" · ")[0].strip().lower()
      if base_name in sources_by_name:
        street_addr = sources_by_name[base_name]["streetAddress"]
        orig_name = entry["title"].split(" · ")[0].strip()
        entry["title"] = f"{orig_name} · {street_addr}"
        entry["url"] = format_maps_place_url(
            entry["placeId"], query=entry["title"]
        )
        entry["streetAddress"] = street_addr

  return list(sources_by_id.values())


def extract_addresses_from_plain_text(
    plain_text: str | None,
    place_names: list[str],
) -> dict[str, str]:
  """Extracts street addresses for specific place names from LLM plain-text summary."""
  result: dict[str, str] = {}
  if not plain_text or not isinstance(plain_text, str):
    return result

  for raw_name in place_names:
    name = raw_name.strip()
    if not name or name == "Google Maps Place":
      continue
    escaped = re.escape(name)
    # Match patterns like: "1. The Pink Door: 1919 Post Alley, Seattle" or "**The Pink Door** - 1919 Post Alley"
    patterns = [
        (
            rf"{escaped}(?:\*\*)?\s*(?:[-–—:]|\bat\b|\blocated"
            r" at\b|\()\s*([0-9]+\s+[^,\n\)]+)"
        ),
        rf"{escaped}[^\n]*?\b(\d+\s+[A-Za-z0-9.\s]+?(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Way|Ln|Lane|Dr|Drive|Alley|Pl|Place|Ct|Court|Pkwy|Parkway|Hwy|Highway|Pike|Broadway|Real|Camino|Square|Sq|Terrace|Ter|Cir|Circle)\b[^,\n\)]*)",
    ]
    for pat in patterns:
      m = re.search(pat, plain_text, re.IGNORECASE)
      if m:
        candidate = simplify_address(m.group(1))
        if candidate and len(candidate) > 3:
          result[name.lower()] = candidate
          break
  return result


def enrich_grounding_sources_with_a2ui_payload(
    sources: list[dict[str, str]],
    a2ui_payload: Any,
    query: str | None = None,
    plain_text: str | None = None,
) -> list[dict[str, str]]:
  """Enriches existing grounding sources (e.g.

  from Vertex chunks) with street addresses from A2UI payload or text.
  """
  a2ui_sources = extract_sources_from_a2ui_payload(a2ui_payload, query=query)
  by_place_id: dict[str, dict[str, str]] = {}
  by_name: dict[str, str] = {}

  for item in a2ui_sources:
    pid = item.get("placeId")
    if pid:
      by_place_id[pid] = item
    base_name = item.get("title", "").split(" · ")[0].strip().lower()
    street_addr = item.get("streetAddress")
    if base_name and street_addr:
      by_name[base_name] = street_addr

  # Also scan plain text summary (before <a2ui-json>) if provided
  place_names_to_check = [
      s.get("title", "").split(" · ")[0].strip()
      for s in sources
      if s.get("title")
  ]
  text_addresses = extract_addresses_from_plain_text(
      plain_text, place_names_to_check
  )
  for k, v in text_addresses.items():
    if k not in by_name:
      by_name[k] = v

  loc_from_query = extract_location_from_query(query)
  existing_place_ids: set[str] = set()

  for s in sources:
    pid = s.get("placeId")
    if pid:
      existing_place_ids.add(pid)
    base_name = s.get("title", "").split(" · ")[0].strip()
    norm_name = base_name.lower()

    street_addr = None
    if pid and pid in by_place_id and by_place_id[pid].get("streetAddress"):
      street_addr = by_place_id[pid]["streetAddress"]
    elif norm_name in by_name:
      street_addr = by_name[norm_name]

    if street_addr and street_addr not in base_name:
      s["title"] = f"{base_name} · {street_addr}"
      if pid:
        s["url"] = format_maps_place_url(pid, query=s["title"])
      else:
        s["url"] = format_maps_search_url(s["title"])
    elif " · " not in s.get("title", "") and loc_from_query:
      s["title"] = f"{base_name} · {loc_from_query}"
      if pid:
        s["url"] = format_maps_place_url(pid, query=s["title"])
    s.pop("streetAddress", None)

  # Append any additional places from A2UI payload not already in sources
  for item in a2ui_sources:
    pid = item.get("placeId")
    item_copy = dict(item)
    item_copy.pop("streetAddress", None)
    if pid and pid not in existing_place_ids:
      existing_place_ids.add(pid)
      sources.append(item_copy)

  return sources
