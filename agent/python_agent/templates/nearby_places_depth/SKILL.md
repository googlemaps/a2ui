---
name: nearby_places_depth
description: Guidelines and rules for extracting structured parameters for nearby places depth queries (2 to 4 places, default 3).
---

# Nearby Places Depth Guidelines

## Core Objective (Nearby Places Depth: 2-4 Places)

*   Curate **2 to 4 grounded places** (default to **3 places** unless the user
    specifies an exact count like 2 or 4) that best match the user's qualitative
    criteria or activity request.
*   Ensure the list order in `places` matches the order of markers on the map,
    and populate all `NearbyPlacesDepthExtractorSchema` fields (and optional
    `anchor_marker` when searching near a landmark) following the schema field
    descriptions and shared style guidelines.
