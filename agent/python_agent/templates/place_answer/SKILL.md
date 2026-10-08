---
name: place_answer
description: Extractor skill for single-place question answering and details lookup queries.
---

# Place Answer Guidelines

## Core Objective

Extract structured parameters to answer user questions about a single specific
place or landmark using verified Google Maps search results, and call
`render_place_answer_template` to render the answer and place card.

## Grounding & Tool-Calling Policy (CRITICAL)

1.  **DO NOT HALLUCINATE OR GUESS**: You are strictly forbidden from generating
    coordinates (latitude, longitude) or Google Maps Place IDs from your
    internal memory or training weights.
2.  **MANDATORY TOOL CALLS**: You MUST call the `search_places` tool first to
    resolve the exact place details, coordinates, and Place ID.
3.  **EXACT MATCH**: Any place name, coordinates, or Place ID returned in your
    final response MUST correspond exactly to the data returned by the
    `search_places` tool call.

## Output Fields

You MUST call `render_place_answer_template` with all required fields:

-   **`heading`**: A concise sentence-case heading naming the place or inquiry
    (e.g., 'Space Needle'). Plain text only; do NOT include markdown hashtags or
    conversational filler.
-   **`summary`**: A concise paragraph directly answering the user's question
    about this specific place with grounded details (e.g., operating hours,
    parking, accessibility, amenities, or atmosphere). Do NOT include
    conversational greetings ('Sure!', 'Here is...').
-   **`place_id`**: The unique Google Maps Place ID for the place.
-   **`name`**: The official name of the place.
-   **`lat`**: Latitude coordinate of the place.
-   **`lng`**: Longitude coordinate of the place.
-   **`zoom`**: Recommended map zoom level. Default to 16 for single-place focus.
