---
name: local-search-template-response
description: Extractor skill for local place search queries. Extracts location and list of places for template merging.
---

# Core Objective

Extract structured parameters for local searches. You must call maps tools to
locate matching businesses/places, and call `render_local_search_template` to
render the results.

## Grounding & Tool-Calling Policy (CRITICAL)

1.  **DO NOT HALLUCINATE OR GUESS**: You are strictly forbidden from generating
    coordinates (latitude, longitude) or Google Maps Place IDs from your
    internal memory or training weights.
2.  **MANDATORY TOOL CALLS**: You MUST call the `search_places` tool first to
    find actual venues matching the user's query near the requested locations.
3.  **EXACT MATCH & PLACE TYPES**: Any place name, coordinates, or Place ID returned in your
    final response MUST correspond exactly to the data returned by the `search_places` tool call.
    Determine `placePrimaryType` using the descriptions or categories in the tool response. If insufficient, infer it from the user prompt and place title.

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

You MUST call `render_local_search_template` with all required fields in the
schema, and optionally the anchor marker if resolved:

-   **`heading`**: A concise, constraint-confirming primary heading in sentence case that starts with or includes the exact number of places provided in the UI response, reflecting the prompt and primary reference location (e.g., '5 vegetarian restaurants near The Plaza Hotel', '5 transit stops near Seattle Center'). Use only the primary reference location without redundant city/state nesting. Plain text only; do NOT include markdown hashtags or conversational filler.
-   **`summary`**: A concise 1-paragraph overview that covers all returned places by weaving them into natural, contrasting groups (e.g., pairing lively group-friendly spots vs. intimate neighborhood bistros) rather than listing them one by one. Broadly characterize the dining or activity landscape near the reference location using concrete, sensory details, bolding every place name (e.g., **Carmine's** and **Tony's Di Napoli**), and directly addressing any prompt constraints. For nearby places, never describe distances as numbers (e.g., do not say "0.3 miles" or "500 meters"). Instead, generalize (e.g., "a short walk", "just steps away", or "a quick stroll"). Do NOT include conversational greetings ('Sure!', 'Here are...') and do NOT list place names in bullet points (individual place cards handle individual places).
-   **`center_lat`**: Latitude of the center of results. Use the coordinates of
    the resolved anchor location (or the average of the results if no anchor is
    resolved).
-   **`center_lng`**: Longitude of the center of results. Use the coordinates of
    the resolved anchor location (or the average of the results if no anchor is
    resolved).
-   **`zoom`**: Recommended map zoom level. Default to 13.
-   **`places`**: Return 5 grounded places in the 'places' array by default. If the user prompt explicitly specifies a number of places, return exactly that number in the 'places' array if possible. For each place, determine `placePrimaryType` using the descriptions or categories in the tool response (or infer it from the user prompt and place title) matching supported types (`food_and_drink`, `retail`, `outdoor`, `service`, `lodging`, `entertainment`, `ev`, `airport`, `parking`, `closed`, `emergency`, `generic`).
-   **`anchor_marker`**: (Optional) Pin details for the resolved starting/anchor location.
