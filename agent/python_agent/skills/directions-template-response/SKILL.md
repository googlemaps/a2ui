---
name: directions-template-response
description: Extractor skill for directions and routing queries. Extracts routing details for template merging.
---

# Directions Template Response Skill

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
3.  **Dispatch Response**: Call `set_model_response` with the compiled routes
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

2.  **Resolve Place Coordinates and IDs (Parallel Search)**:

    *   Issue ALL `search_places` calls concurrently for the origin,
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

    *   Issue `compute_routes` calls concurrently for all route segment pairs.
    *   **STRICT TOOL PARAMETERS**: When calling `compute_routes`, ensure that
        `origin` and `destination` objects conform to the maps tool contract.
        Specify **exactly one** identifier:
        *   `placeId`: Use the resolved place ID (e.g., `{"placeId":
            "ChIJ-ZeD..."}`). This is highly preferred if available.
        *   `address`: Use the address string.
        *   `location`: Use latitude/longitude inside a location sub-object
            (e.g., `{"location": {"latLng": {"latitude": 37.7, "longitude":
            -122.4}}}`). Do **NOT** pass `latLng` directly as a root key inside
            `origin` or `destination` (e.g. do not call
            `compute_routes(origin={"placeId": "...", "latLng": ...})`).
    *   Verify route availability for requested `travel_mode`.
    *   **CONSTRUCT THE ROUTES ARRAY**: You MUST compile the computed segments
        into the `routes` array of the final `set_model_response` payload. The
        array must contain all segments sequentially (e.g. `[{"origin": Origin,
        "destination": Waypoint 1}, {"origin": Waypoint 1, "destination":
        Destination}]`). Do NOT omit the `routes` array or leave it empty if you
        successfully computed routes.
    *   **MANDATORY TRAVEL MODE IN DISPATCH**: `travel_mode` is REQUIRED and
        must NEVER be omitted in `set_model_response`. Always supply the
        normalized mode string (`driving`, `walking`, `transit`, or `bicycling`).
    *   Call `set_model_response` with `DirectionsExtractorSchema` parameters
        (`summary`, `center_lat`, `center_lng`, `zoom`, `routes`,
        `travel_mode`).

## Handling Routing Failures & Regional Limitations (CRITICAL)

Google Maps routing (driving, walking) is not supported in certain regions (such
as South Korea). If a tool call to `compute_routes` returns empty results (`{}`)
or fails:

1.  **Do NOT retry** with alternative queries or locations.
2.  Immediately exit the tool-calling loop.
3.  Return a user-friendly summary explaining the regional limitation (e.g.
    "Google Maps directions are not supported in South Korea"), and set the
    routes list to empty `[]`.

## Output Fields

You MUST populate all required fields in the output schema:

-   **`summary`**: A detailed response summarizing the travel directions, following the **Conversational Text Style Guidelines** below.
-   **`center_lat`**: Latitude of the center of the route map.
-   **`center_lng`**: Longitude of the center of the route map.
-   **`zoom`**: Recommended map zoom level. Default to 12.
-   **`routes`**: A list of route segments connecting the origin, intermediate
    waypoints, and the destination in order.
-   **`travel_mode`**: (REQUIRED) The transit travel mode (`driving`, `walking`, `transit`, `bicycling`). Must match the user's requested travel mode and must never be omitted.

## Examples

### Example 1: Driving Route
User Query: "Directions from San Francisco to San Jose by car"
Tool Call:
`set_model_response(summary="Driving from San Francisco to San Jose takes about 50 minutes via US-101 S.", center_lat=37.55, center_lng=-122.15, zoom=10, routes=[{"origin": {"lat": 37.7749, "lng": -122.4194, "label": "San Francisco", "placeId": "ChIJIQBpAG2ahYAR_6128GcTUEo"}, "destination": {"lat": 37.3382, "lng": -121.8863, "label": "San Jose", "placeId": "ChIJ9T_nxcC1j4ARmMo7S4ABIdM"}}], travel_mode="driving")`

### Example 2: Walking Route
User Query: "How do I walk from Central Park to Times Square?"
Tool Call:
`set_model_response(summary="Walking from Central Park to Times Square takes about 18 minutes (0.9 miles) down 7th Ave.", center_lat=40.765, center_lng=-73.978, zoom=14, routes=[{"origin": {"lat": 40.768, "lng": -73.974, "label": "Central Park South", "placeId": "ChIJN1t_tDeuEmsRUsoyG83frY4"}, "destination": {"lat": 40.758, "lng": -73.985, "label": "Times Square", "placeId": "ChIJmQJItx6vwokRLxVi2JyuzRo"}}], travel_mode="walking")`

### Example 3: Bicycling Route
User Query: "Bike directions from Venice Beach to Santa Monica Pier"
Tool Call:
`set_model_response(summary="Biking from Venice Beach to Santa Monica Pier takes around 15 minutes along the Marvin Braude Bike Trail.", center_lat=33.998, center_lng=-118.483, zoom=13, routes=[{"origin": {"lat": 33.985, "lng": -118.469, "label": "Venice Beach", "placeId": "ChIJ-wjh2I-6woARx3H-n9uVn4A"}, "destination": {"lat": 34.009, "lng": -118.497, "label": "Santa Monica Pier", "placeId": "ChIJw8g0Xbm7woARQY1Xq41qB2M"}}], travel_mode="bicycling")`

### Example 4: Transit Route
User Query: "Take the subway from Grand Central to Brooklyn Bridge"
Tool Call:
`set_model_response(summary="Take the 4 or 5 subway line south from Grand Central - 42 St to Brooklyn Bridge - City Hall (approx. 12 minutes).", center_lat=40.731, center_lng=-73.988, zoom=12, routes=[{"origin": {"lat": 40.7527, "lng": -73.9772, "label": "Grand Central Terminal", "placeId": "ChIJ4zBEaKZQwokREuE50bbCGYs"}, "destination": {"lat": 40.7126, "lng": -74.0049, "label": "Brooklyn Bridge - City Hall", "placeId": "ChIJ40i5iRZawokRHqGfF2b_3yI"}}], travel_mode="transit")`

### Example 5: Unspecified Travel Mode (Defaults to Driving)
User Query: "Directions from Austin to San Antonio"
Tool Call:
`set_model_response(summary="Driving from Austin to San Antonio takes about 1 hour and 20 minutes via I-35 S.", center_lat=29.85, center_lng=-98.15, zoom=9, routes=[{"origin": {"lat": 30.2672, "lng": -97.7431, "label": "Austin", "placeId": "ChIJLwW05NsQW4YRtxm00DkzqlU"}, "destination": {"lat": 29.4241, "lng": -98.4936, "label": "San Antonio", "placeId": "ChIJrw7QBK9YXIYRowalignfdg4"}}], travel_mode="driving")`
