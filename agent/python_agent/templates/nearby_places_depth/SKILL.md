---
name: nearby_places_depth
description: Guidelines and rules for extracting structured parameters for nearby places depth queries (2 to 4 places, default 3).
---

# Nearby Places Depth Guidelines

## Core Objective (Nearby Places Depth: 2-4 Places, Default 3)

*   Curate **2 to 4 grounded places** (default to **3 places** unless the user
    specifies an exact count like 2 or 4) that best match the user's bespoke
    needs, occasion, or qualitative criteria.
*   Start with a single plain-sentence `preamble` that directly answers the
    prompt and clarifies what kind of places these are, the primary reference
    location, and the range or variety covered (no title-case headline, no
    markdown, no second sentence).
*   Ensure the list order in `places` matches the order of markers on the map,
    populate `placePrimaryType` for every place using the closest matching
    category (`food_and_drink`, `outdoor`, `retail`, `gas_station`, `ev`,
    `bank`, `lodging`, `emergency`, `entertainment`, `airport`, `parking`, or
    `generic`), and populate `anchor_marker` when searching near a landmark.
*   Every `placeId`, coordinate, and fact must come directly from grounded
    Google Maps results—never invent or recall Place IDs from memory, and
    exclude permanently closed venues.

## Guidelines for `intro` and `description`

1.  **`intro` (Rendered Above the Place Card)**: ONE vivid, sensory opening hook
    sentence highlighting the place's defining character, unique identity, and
    why it specifically answers the user's constraints. Do NOT put bullet points
    in `intro`, and do NOT repeat the numeric star rating (e.g., `4.8★`) or
    review count in the text, as the `PlaceDetailsCompact` card already displays
    them.
2.  **`description` — Contextual Bullet Points (Rendered Below the Place
    Card)**: Provide 1 to 2 concise markdown bullet points (`* **Label**: ...`)
    using bold, domain-appropriate labels (e.g., **The Vibe**, **Standout
    Feature**, **Pet Suitability**, **Timing & Crowds**). Choose whatever angles
    best capture what makes the place special and how it fits the user's
    specific request—whether that's atmosphere, signature offerings, terrain, or
    insider tips—while avoiding generic labels like "Highlights" or "Details".
3.  **`description` — Proactive Logistics**: ALWAYS include at least 1 concise
    markdown bullet in `description` covering actionable logistical needs:
    ticketing or fees, operating hours, parking, peak vs. quiet times, leash
    rules, or dress codes.
