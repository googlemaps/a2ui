---
name: local_search
description: Extractor skill for local place search queries. Extracts location and list of places for template merging.
---

# Local Search Guidelines

## Core Objective

Extract structured parameters for local searches using verified Google Maps
results. Return 5 grounded places in `places` by default (or the exact count
requested by the user if possible), and follow `LocalSearchExtractorSchema`
field descriptions and the shared style guidelines.

## Multi-Step Location Resolution Policy (Anchored Search)

If the user's query references a starting point, landmark, hotel, or specific
address as a geographical anchor (e.g., "Space Needle", "Hyatt hotel", "1600
Amphitheatre Pkwy"):

1.  **Resolve Anchor Coordinates First**: Resolve the exact center coordinates,
    name, and Place ID of the anchor location first.
2.  **Execute Proximity Search (Pivot on Anchor)**: Search for matching venues
    around the resolved anchor coordinates according to the user's distance
    constraint:
    *   **Explicit Distance**: Honor explicit distance bounds in the query
        (e.g., "within 5 miles", "2 km").
    *   **Implicit Walking**: If the query implies walking (e.g., "walk to",
        "walking distance"), focus on venues within roughly 1 km (a 10-15 minute
        walk) of the anchor.
    *   **No Specific Constraint**: If no distance constraint is specified
        (e.g., "near", "around"), bias results dynamically around the anchor
        center point.
3.  **Handle Non-Geographic Filters**: Keep the search query focused on the core
    category and key searchable features or amenities (e.g., "restaurant outdoor
    seating", "cafe wifi"). Strip conversational filler words (e.g., "with",
    "that has", "places offering") to maximize search relevance and matching
    accuracy.
4.  **Set Anchor Marker**: Populate the `anchor_marker` response parameter with
    the resolved coordinates, name, and Place ID of the anchor location.

## Multiple Named Places / Comparison on One Map

When the user asks to show or compare multiple specific named places,
buildings, landmarks, or addresses on a map (e.g., "Show me GWC2 and google
1950 in the same map"):

1.  **Parallel Place Lookups**: Issue place lookups in parallel for each
    requested place.
2.  **Disambiguation Retry**: If a lookup for an abbreviation or building code
    returns empty results, retry once with a broader or disambiguated query
    (e.g., adding the campus or city name).
3.  **Render Partial Results**: As long as at least one place resolves, you
    MUST populate the output schema with all resolved places in `places` (using
    the average of resolved coordinates for `center_lat` and `center_lng`) and
    note any unresolved place in `summary`.

## Handling Failures & Empty Results (CRITICAL)

If search queries return empty results (`{}`) or fail:

1.  Retry at most **once** with a broader or disambiguated query if the initial
    query used an abbreviation or building code.
2.  If at least one requested place resolved, populate the output schema with
    the resolved subset and mention any unfound place in `summary`.
3.  Only if **no** places can be resolved at all, exit the tool-calling loop
    and return a user-friendly summary explaining that no results were found.
