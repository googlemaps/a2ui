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

"""Unit tests for grounding_sources utility functions."""

from types import SimpleNamespace
import unittest

from grounding_sources import (
    enrich_grounding_sources_with_a2ui_payload,
    extract_location_from_query,
    extract_sources_from_a2ui_payload,
    extract_sources_from_grounding_chunks,
    extract_sources_from_places_data,
    format_maps_place_url,
    format_maps_search_url,
    simplify_address,
)


class TestGroundingSources(unittest.TestCase):

  def test_format_maps_place_url(self):
    url = format_maps_place_url("ChIJ12345")
    self.assertEqual(
        url, "https://www.google.com/maps/place/?q=place_id:ChIJ12345"
    )

  def test_format_maps_search_url(self):
    url = format_maps_search_url("Pike Place Market")
    self.assertEqual(
        url,
        "https://www.google.com/maps/search/?api=1&query=Pike%20Place%20Market",
    )

  def test_extract_sources_from_grounding_chunks(self):
    chunks = [
        SimpleNamespace(
            maps=SimpleNamespace(
                title="Pike Place Chowder - Google Maps",
                place_id="places/ChIJ-02xI_NqkFQR97b5eH101oY",
            )
        ),
        SimpleNamespace(
            maps=SimpleNamespace(
                title="Beecher's Handmade Cheese",
                place_id="ChIJN1t_tDeuEmsRUsoyG83frY4",
            )
        ),
        SimpleNamespace(
            web=SimpleNamespace(
                title="Seattle Dining Guide",
                uri="https://example.com/seattle-guide",
            )
        ),
    ]

    sources = extract_sources_from_grounding_chunks(chunks)
    self.assertEqual(len(sources), 3)

    self.assertEqual(sources[0]["title"], "Pike Place Chowder")
    self.assertEqual(sources[0]["placeId"], "ChIJ-02xI_NqkFQR97b5eH101oY")
    self.assertEqual(
        sources[0]["url"],
        "https://www.google.com/maps/place/?q=place_id:ChIJ-02xI_NqkFQR97b5eH101oY",
    )
    self.assertEqual(sources[0]["type"], "place")

    self.assertEqual(sources[1]["title"], "Beecher's Handmade Cheese")
    self.assertEqual(sources[1]["placeId"], "ChIJN1t_tDeuEmsRUsoyG83frY4")

    self.assertEqual(sources[2]["title"], "Seattle Dining Guide")
    self.assertEqual(sources[2]["url"], "https://example.com/seattle-guide")
    self.assertEqual(sources[2]["type"], "web")

  def test_extract_sources_from_places_data(self):
    places = [
        {
            "name": "Canlis",
            "placeId": "ChIJxyz789",
            "address": "2576 Aurora Ave N",
        },
        {
            "name": "Space Needle",
            "place_id": "ChIJabc123",
        },
    ]

    sources = extract_sources_from_places_data(places)
    self.assertEqual(len(sources), 2)
    self.assertEqual(sources[0]["title"], "Canlis · 2576 Aurora Ave N")
    self.assertEqual(sources[0]["placeId"], "ChIJxyz789")
    self.assertEqual(
        sources[0]["url"],
        "https://www.google.com/maps/search/?api=1&query=Canlis%2C%202576%20Aurora%20Ave%20N&query_place_id=ChIJxyz789",
    )
    self.assertEqual(sources[1]["title"], "Space Needle")
    self.assertEqual(sources[1]["placeId"], "ChIJabc123")
    self.assertEqual(
        sources[1]["url"],
        "https://www.google.com/maps/search/?api=1&query=Space%20Needle&query_place_id=ChIJabc123",
    )

  def test_extract_sources_from_a2ui_payload(self):
    payload = {
        "surface": {
            "components": [{
                "type": "PlaceCard",
                "props": {
                    "name": "The Pink Door",
                    "placeId": "ChIJpink123",
                },
            }]
        }
    }

    sources = extract_sources_from_a2ui_payload(payload)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["title"], "The Pink Door")
    self.assertEqual(sources[0]["placeId"], "ChIJpink123")
    self.assertEqual(
        sources[0]["url"],
        "https://www.google.com/maps/search/?api=1&query=The%20Pink%20Door&query_place_id=ChIJpink123",
    )

  def test_extract_sources_from_a2ui_payload_enrichment(self):
    # markers array comes first without address, then restaurants comes with address
    payload = [
        {
            "updateComponents": {
                "components": [{
                    "component": "GoogleMap",
                    "markers": [{
                        "lat": 47.608,
                        "lng": -122.34,
                        "label": "Sushi Kashiba",
                        "placeId": "ChIJsushi1",
                    }],
                }]
            }
        },
        {
            "updateDataModel": {
                "restaurants": [{
                    "name": "Sushi Kashiba",
                    "address": "86 Pine St, Seattle",
                    "placeId": "ChIJsushi1",
                }]
            }
        },
    ]

    sources = extract_sources_from_a2ui_payload(payload)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["title"], "Sushi Kashiba · 86 Pine St")
    self.assertEqual(sources[0]["placeId"], "ChIJsushi1")
    self.assertEqual(
        sources[0]["url"],
        "https://www.google.com/maps/search/?api=1&query=Sushi%20Kashiba%2C%2086%20Pine%20St&query_place_id=ChIJsushi1",
    )

  def test_simplify_address(self):
    self.assertEqual(
        simplify_address("23 Commerce St, New York, NY 10014"), "23 Commerce St"
    )
    self.assertEqual(
        simplify_address("173 Hester St, New York, NY 10013"), "173 Hester St"
    )
    self.assertEqual(simplify_address("3rd & L St NE"), "3rd & L St NE")
    self.assertIsNone(simplify_address(None))

  def test_extract_location_from_query(self):
    self.assertEqual(
        extract_location_from_query("sushi restaurants in Seattle"), "Seattle"
    )
    self.assertEqual(
        extract_location_from_query("Where can I get a beer in Ballard?"),
        "Ballard",
    )
    self.assertEqual(
        extract_location_from_query(
            "find hotels near Central Park, NY with pool"
        ),
        "Central Park, NY",
    )
    self.assertIsNone(extract_location_from_query("tell me a joke"))

  def test_extract_sources_from_grounding_chunks_with_query(self):
    chunks = [
        SimpleNamespace(
            maps=SimpleNamespace(
                title="Sushi Kashiba - Google Maps",
                place_id="places/ChIJsushi1",
            )
        )
    ]
    sources = extract_sources_from_grounding_chunks(
        chunks, query="Show me sushi in Seattle"
    )
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["title"], "Sushi Kashiba · Seattle")
    self.assertEqual(sources[0]["placeId"], "ChIJsushi1")
    self.assertEqual(
        sources[0]["url"],
        "https://www.google.com/maps/search/?api=1&query=Sushi%20Kashiba%2C%20Seattle&query_place_id=ChIJsushi1",
    )

  def test_extract_sources_with_canonical_uri(self):
    canonical_maps_url = (
        "https://www.google.com/maps/place/data=!4m2!3m1!1s0x54906ab2d385158b"
    )
    chunks = [
        SimpleNamespace(
            maps=SimpleNamespace(
                title="Sushi Kashiba",
                place_id="ChIJsushi1",
                uri=canonical_maps_url,
            )
        )
    ]
    sources = extract_sources_from_grounding_chunks(chunks)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0]["url"], canonical_maps_url)

  def test_enrich_grounding_sources_with_a2ui_payload(self):
    sources = [{
        "title": "The Pink Door · Seattle",
        "url": "https://www.google.com/maps/place/?q=place_id:ChIJpink123",
        "type": "place",
        "placeId": "ChIJpink123",
    }]
    a2ui_payload = [{
        "updateDataModel": {
            "value": {
                "items": [{
                    "placeId": "ChIJpink123",
                    "name": "The Pink Door",
                    "address": "1919 Post Alley, Seattle, WA 98101",
                }]
            }
        }
    }]
    enrich_grounding_sources_with_a2ui_payload(
        sources, a2ui_payload, query="italian in Seattle"
    )
    self.assertEqual(sources[0]["title"], "The Pink Door · 1919 Post Alley")
    self.assertIn("1919%20Post%20Alley", sources[0]["url"])

  def test_enrich_grounding_sources_from_plain_text(self):
    sources = [{
        "title": "Canlis · Seattle",
        "url": "https://www.google.com/maps/place/?q=place_id:ChIJcanlis",
        "type": "place",
        "placeId": "ChIJcanlis",
    }]
    plain_text = (
        "Here is what I found:\n1. Canlis: 2576 Aurora Ave N, Seattle, WA 98109"
    )
    enrich_grounding_sources_with_a2ui_payload(
        sources, None, query="fine dining in Seattle", plain_text=plain_text
    )
    self.assertEqual(sources[0]["title"], "Canlis · 2576 Aurora Ave N")


if __name__ == "__main__":
  unittest.main()
