---
name: directions
description: Extractor skill for directions and routing queries. Extracts routing details for template merging.
---

# Directions Guidelines

## Directions Template Response Skill

## Core Objective

Extract structured parameters to populate the `DirectionsExtractorSchema` for
rendering directions on a map.

## Multi-Step Route Resolution Policy

If the user's query requests a scenic bypass or detour:

1.  **Resolve Place Coordinates and IDs (Parallel Search)**: Concurrently search
    for the origin, destination, and any identified detour waypoints along the
    corridor.
2.  **Compute Route Segments (Parallel Routing)**: Concurrently compute routes
    for all sequential legs connecting the resolved stops (Origin -> Waypoint,
    Waypoint -> Destination).
3.  **Dispatch Response**: Populate the output schema with the compiled routes
    and pins.

## Step-by-Step Workflow

1.  **Analyze the Query & Constraints**:

    *   Identify the origin and destination names.
    *   **Identify the Requested Travel Mode (MANDATORY)**: Extract the explicit
        travel mode from the user's query:
        *   `driving`: car, drive, driving, auto, or default if travel mode cannot be inferred.
        *   `walking`: walk, walking, on foot, pedestrian, foot.
        *   `bicycling`: bike, biking, bicycle, bicycling, cycling.
        *   `transit`: bus, train, subway, metro, tube, public transit.
    *   **Option Comparisons & Constraints**:
        *   **Option Comparisons**: When comparing multiple travel modes or routes (e.g., driving vs. transit), set `travel_mode` to the primary or recommended mode for map rendering, and compute routes for each option in parallel. In `summary`, provide an intro duration comparison, dedicated bullets for each option (duration, distance, primary roads or transit lines), and an actionable recommendation bullet (`* **Recommendation**: ...`).
        *   **Temporal & Route Constraints**: When the prompt specifies departure times, rush hour, scenic preferences, or road/transit avoidances, explicitly reflect traffic-adjusted duration ranges or confirm how requested avoidances/preferences are met in `summary`.

2.  **Resolve Place Coordinates and IDs (Parallel Search)**:

    *   Issue ALL place searches concurrently for the origin,
        destination, and all intermediate waypoints or scenic stops along the
        corridor.
    *   **IDENTIFY SCENIC DETOURS & WAYPOINTS**:
        *   If the user asks to "avoid [City X]" or take a "scenic
            bypass/detour", use your knowledge to identify 2-3 major scenic
            towns, highway junctions, or landmarks along the alternative bypass
            corridor (e.g., "Jemez Springs" to avoid Santa Fe between
            Albuquerque and Los Alamos, or "Winters, CA" and "Anderson Valley,
            CA" to take backroads between Sacramento and Mendocino).
        *   Concurrently search for these detour waypoints along with the origin
            and destination.
        *   **STABLE SEARCH QUERIES**: Use specific place or town names (e.g.,
            search for "Anderson Valley, CA" or "Jemez Springs, NM") instead of
            generic road descriptors (e.g. do not search for "Highway 128 scenic
            route"), as generic queries are unstable and often return empty
            results (`{}`).
    *   Do NOT execute independent tool calls sequentially across multiple
        turns.
    *   Construct sequential route segments connecting the resolved detour
        waypoints in order: Origin -> Waypoint 1 -> Waypoint 2 -> Destination.

3.  **Compute Routes and Dispatch Response (Parallel Routing)**:

    *   Verify route availability for the requested `travel_mode`. When the user
        compares multiple travel modes or route options, compute routes in
        parallel for each compared mode or option so `summary` compares grounded
        durations and distances for all options.
    *   **CONSTRUCT THE ROUTES ARRAY**: You MUST compile the computed segments
        into the `routes` array of the output schema. The array must contain all
        segments sequentially (e.g. `[{"origin": Origin, "destination": Waypoint
        1}, {"origin": Waypoint 1, "destination": Destination}]`). Do NOT omit
        the `routes` array or leave it empty if you successfully computed
        routes.
    *   **MANDATORY TRAVEL MODE IN DISPATCH**: `travel_mode` is REQUIRED and
        must NEVER be omitted. Always supply the normalized mode string
        (`driving`, `walking`, `transit`, or `bicycling`).
    *   Populate `DirectionsExtractorSchema` parameters (`heading`, `summary`,
        `center_lat`, `center_lng`, `zoom`, `routes`, `travel_mode`).

## Handling Routing Failures & Regional Limitations (CRITICAL)

Google Maps routing (driving, walking) is not supported in certain regions (such
as South Korea). If route computation returns empty results (`{}`) or fails:

1.  **Do NOT retry** with alternative queries or locations.
2.  Immediately exit the tool-calling loop.
3.  Return a user-friendly summary explaining the regional limitation (e.g.
    "Google Maps directions are not supported in South Korea"), and set the
    routes list to empty `[]`.

## Examples

### Example 1: Driving Route

User Query: "Directions from San Francisco to San Jose by car"
Extracted Parameters:
`{"heading": "Driving directions from San Francisco to San Jose", "summary": "Driving from **San Francisco** to **San Jose** takes **about 50 minutes** (**48 miles**) via US-101 S.\n\n* **Route details**: Follow US-101 S down the Peninsula, or take I-280 S for a scenic freeway alternative.\n* **Arrival & logistics**: Exiting onto I-880 S or CA-87 S connects directly into downtown San Jose.", "center_lat": 37.55, "center_lng": -122.15, "zoom": 10, "routes": [{"origin": {"lat": 37.7749, "lng": -122.4194, "label": "San Francisco", "placeId": "ChIJIQBpAG2ahYAR_6128GcTUEo"}, "destination": {"lat": 37.3382, "lng": -121.8863, "label": "San Jose", "placeId": "ChIJ9T_nxcC1j4ARmMo7S4ABIdM"}}], "travel_mode": "driving"}`

### Example 2: Walking Route

User Query: "How do I walk from Central Park to Times Square?"
Extracted Parameters:
`{"heading": "Walking route from Central Park to Times Square", "summary": "Walking from **Central Park South** to **Times Square** takes **about 18 minutes** (**0.9 miles**) heading south down 7th Ave.\n\n* **Route details**: Head south from 59th St & 7th Ave straight down 7th Ave or Broadway into the Theater District.\n* **Arrival & logistics**: **Times Square** (Manhattan, NY 10036) is open 24 hours with pedestrian plazas between 42nd and 47th Streets.", "center_lat": 40.765, "center_lng": -73.978, "zoom": 14, "routes": [{"origin": {"lat": 40.768, "lng": -73.974, "label": "Central Park South", "placeId": "ChIJN1t_tDeuEmsRUsoyG83frY4"}, "destination": {"lat": 40.758, "lng": -73.985, "label": "Times Square", "placeId": "ChIJmQJItx6vwokRLxVi2JyuzRo"}}], "travel_mode": "walking"}`

### Example 3: Bicycling Route

User Query: "Bike directions from Venice Beach to Santa Monica Pier"
Extracted Parameters:
`{"heading": "Biking route from Venice Beach to Santa Monica Pier", "summary": "Biking from **Venice Beach** to **Santa Monica Pier** takes **around 15 minutes** (**2.4 miles**) along the beachfront Marvin Braude Bike Trail.\n\n* **Route details**: Follow the paved oceanfront bike path north from Venice Boardwalk directly to the pier ramp.\n* **Arrival & logistics**: **Santa Monica Pier** (200 Santa Monica Pier, Santa Monica, CA 90401) is open daily from 6 AM to 10 PM with bike racks near the entrance.", "center_lat": 33.998, "center_lng": -118.483, "zoom": 13, "routes": [{"origin": {"lat": 33.985, "lng": -118.469, "label": "Venice Beach", "placeId": "ChIJ-wjh2I-6woARx3H-n9uVn4A"}, "destination": {"lat": 34.009, "lng": -118.497, "label": "Santa Monica Pier", "placeId": "ChIJw8g0Xbm7woARQY1Xq41qB2M"}}], "travel_mode": "bicycling"}`

### Example 4: Transit Route

User Query: "Take the subway from Grand Central to Brooklyn Bridge"
Extracted Parameters:
`{"heading": "Transit directions from Grand Central to Brooklyn Bridge", "summary": "Taking the subway from **Grand Central Terminal** to **Brooklyn Bridge - City Hall** takes **about 12 minutes** (**3 miles**).\n\n* **Route details**: Board the downtown 4 or 5 express train at Grand Central–42 St and ride 2 stops south to Brooklyn Bridge–City Hall.\n* **Arrival & logistics**: Exit at Centre St to access the **Brooklyn Bridge** pedestrian walkway (open 24 hours).", "center_lat": 40.731, "center_lng": -73.988, "zoom": 12, "routes": [{"origin": {"lat": 40.7527, "lng": -73.9772, "label": "Grand Central Terminal", "placeId": "ChIJ4zBEaKZQwokREuE50bbCGYs"}, "destination": {"lat": 40.7126, "lng": -74.0049, "label": "Brooklyn Bridge - City Hall", "placeId": "ChIJ40i5iRZawokRHqGfF2b_3yI"}}], "travel_mode": "transit"}`

### Example 5: Unspecified Travel Mode (Defaults to Driving)

User Query: "Directions from Austin to San Antonio"
Extracted Parameters:
`{"heading": "Driving directions from Austin to San Antonio", "summary": "Driving from **Austin** to **San Antonio** takes **about 1 hour and 20 minutes** (**80 miles**) via I-35 S.\n\n* **Route details**: Follow I-35 S past San Marcos and New Braunfels directly into downtown San Antonio.\n* **Arrival & logistics**: Expect heavier commuter traffic along the I-35 corridor during peak weekday hours.", "center_lat": 29.85, "center_lng": -98.15, "zoom": 9, "routes": [{"origin": {"lat": 30.2672, "lng": -97.7431, "label": "Austin", "placeId": "ChIJLwW05NsQW4YRtxm00DkzqlU"}, "destination": {"lat": 29.4241, "lng": -98.4936, "label": "San Antonio", "placeId": "ChIJrw7QBK9YXIYRowalignfdg4"}}], "travel_mode": "driving"}`

### Example 6: Multi-Modal Route Comparison (Transit vs Driving)

User Query: "Traveling from Johannesburg to Sandton: should I take the Gautrain or drive during morning rush hour?"
Extracted Parameters:
`{"heading": "Johannesburg to Sandton: Gautrain vs Driving", "summary": "During morning rush hour, taking the **Gautrain** is significantly faster (**~15 minutes**) compared to driving (**45–60+ minutes**) due to heavy highway congestion.\n\n* **Gautrain (Transit)**: Takes **~15 minutes** from **Park Station** to **Sandton Station**. Trains run every 10 minutes during peak hours, completely bypassing highway traffic.\n* **Driving (Car)**: Takes **45 to 60+ minutes** (**14 miles**) via the M1 North under heavy morning commuter gridlock.\n* **Recommendation**: Take the **Gautrain** for a fast, predictable commute during morning peak hours.", "center_lat": -26.15, "center_lng": 28.05, "zoom": 12, "routes": [{"origin": {"lat": -26.196, "lng": 28.041, "label": "Johannesburg Park Station", "placeId": "ChIJb_8q6o4NlR4R-kP-7p3ePzs"}, "destination": {"lat": -26.108, "lng": 28.054, "label": "Sandton Station", "placeId": "ChIJcffh_sMPlR4RvX2hBqV8k78"}}], "travel_mode": "transit"}`
