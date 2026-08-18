---
name: local-search-template-response
description: Extractor skill for local place search queries. Extracts location and list of places for template merging.
---

# Core Objective

Extract structured parameters for local searches. You must call maps tools to
locate matching businesses/places, and populate the response fields.

## Grounding & Tool-Calling Policy (CRITICAL)

1.  **DO NOT HALLUCINATE OR GUESS**: You are strictly forbidden from generating
    coordinates (latitude, longitude) or Google Maps Place IDs from your
    internal memory or training weights.
2.  **MANDATORY TOOL CALLS**: You MUST call the `search_places` tool first to
    find actual venues matching the user's query near the requested locations.
3.  **EXACT MATCH**: Any place name, coordinates, or Place ID returned in your
    final response MUST correspond exactly to the data returned by the
    `search_places` tool call.

## Multi-Step Location Resolution Policy (Anchored Search)

If the user's query references a starting point, landmark, hotel, or specific
address as a geographical anchor (e.g., "Space Needle", "Hyatt hotel", "1600
Amphitheatre Pkwy"):

1.  **Resolve Anchor Coordinates First**: Make a tool call to `search_places`
    with the anchor name as `textQuery` to resolve its exact center coordinates.
2.  **Execute Proximity Search (Pivot on Anchor)**: Use the resolved latitude
    and longitude of the anchor as the center of a `locationBias` circle. Set
    the `radiusMeters` parameter based on the user's query:
    *   **Explicit Distance**: If the query specifies a distance (e.g., "within
        5 miles", "2 km"), parse and convert it to meters (e.g., `8000` or
        `2000`).
    *   **Implicit Walking**: If the query implies walking (e.g., "walk to",
        "walking distance"), default to `1000` meters.
    *   **No Specific Constraint**: If no distance constraint is specified
        (e.g., "near", "around"), omit the `radiusMeters` field to let the
        search engine bias results dynamically around the center point.
3.  **Handle Non-Geographic Filters**: Keep the search query focused on the core
    category and key searchable features or amenities (e.g., "restaurant outdoor
    seating", "cafe wifi"). Strip conversational filler words (e.g., "with",
    "that has", "places offering") to maximize search relevance and matching
    accuracy.
4.  **Set Anchor Marker**: Populate the `anchor_marker` response parameter with
    the resolved coordinates, name, and Place ID of the anchor location.

## Handling Failures & Empty Results (CRITICAL)

If search queries return empty results (`{}`) or fail:

1.  **Do NOT retry** repeatedly with alternative queries.
2.  Immediately exit the tool-calling loop.
3.  Return a user-friendly summary explaining that no results were found, and
    leave the `places` list empty.

## Output Fields

You MUST populate all required fields in the output schema, and optionally the anchor marker if resolved:

-   **`summary`**: A detailed response summarizing the search results, following the **Conversational Text Style Guidelines** below.
-   **`center_lat`**: Latitude of the center of results. Use the coordinates of
    the resolved anchor location (or the average of the results if no anchor is
    resolved).
-   **`center_lng`**: Longitude of the center of results. Use the coordinates of
    the resolved anchor location (or the average of the results if no anchor is
    resolved).
-   **`zoom`**: Recommended map zoom level. Default to 13.
-   **`places`**: A list of places found (limit to max list size, e.g. 3).
-   **`anchor_marker`**: (Optional) Pin details for the resolved starting/anchor location.
