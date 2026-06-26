# GoogleMapsA2UI iOS Library

> **Note:** This toolkit is in **Experimental** status.

The `GoogleMapsA2UI` library is an iOS library designed to encapsulate the parsing and rendering of Maps Agent-to-UI (A2UI) payloads. It seamlessly converts complex A2A JSON responses into native-friendly, rich map interfaces using SwiftUI and WKWebView.

It makes use of the following technologies:
* [Google Maps Platform](https://mapsplatform.google.com/) for rendering maps and places.
* [A2UI](https://a2ui.org/) for the Agent-driven dynamic UI protocol.
* [SwiftUI](https://developer.apple.com/swiftui/) for the native UI layer.
* `WKWebView` for rendering the web-based A2UI components securely.

## Quickstart Guide

To quickly get started, we recommend using the iOS sample project located in the [GoogleMapsA2UI Samples repository](https://github.com/googlemaps-samples/a2ui). This sample project demonstrates how to connect to the Python Agent and use the library to render chat bubbles and map interfaces.

### Prerequisites and Tool Setup

*   **Protocol Version:** This library is built based on the **v0.9 A2UI protocol** and is **not backward compatible** with the v0.8 protocol. Ensure your backend server uses the v0.9 protocol format.
*   **Xcode:** Xcode 15 or later (requires Swift 5.9+).
*   **iOS Target:** iOS 16.0 or later.
*   **Google Maps API Key:** You must have a Google Maps Platform API key to render the maps inside the A2UI web views. You can create one and enable the Maps JavaScript API in the [Google Cloud Console](https://mapsplatform.google.com/).

---

## `GoogleMapsA2UI` iOS Library Package

This package provides the core iOS components for the Maps Agentic UI Toolkit. It handles parsing standard A2A backend responses and rendering the dynamic map payloads.

### File Structure / Architecture

* **`A2AResponseParser`**: A utility that standardizes backend responses into an array of `ParsedA2AEvent` objects.
* **`ParsedA2AEvent`**: An enum representing an extracted payload chunk (`.text` or `.data`).
* **Single-File Web Bundle (`index.html`)**: The library uses a compiled, single-file HTML bundle. This bundle executes a lightweight React application that orchestrates the rendering of the underlying Lit web components.
* **`A2UIView`**: A custom SwiftUI view that wraps an underlying `WKWebView`. It mounts the single-file web bundle, dynamically resizes to fit the rendered content, and bridges native JavaScript callbacks back to Swift.
* **`A2UIServices`**: A global configuration enum used to provide the Maps API key. It efficiently reads the local web bundle, injects your API key directly into the HTML string, and caches the result for high-performance rendering.

### How to Integrate

> **Note** Because `Package.swift` is not located at the root of this repository, you cannot add the package directly via its Git URL. You must **clone the repository locally** first, then add the package using its local path.

The library can be installed via Swift Package Manager (SPM).

#### Using Xcode
1. Clone the repository to your local machine.
2. In Xcode, select **File > Add Package Dependencies...**
3. Click **Add Local...** and select the cloned `a2ui/client/ios/GoogleMapsA2UI` directory.
4. Add the `GoogleMapsA2UI` library to your app's target.

#### Using Package.swift
If you are building your own Swift Package or using a modular architecture, add the package to your `Package.swift` dependencies:

```swift
dependencies: [
    // Replace with actual local path
    .package(path: "path/to/a2ui/client/ios/GoogleMapsA2UI") 
]
```

### Usage

#### 1. Global Initialization
Call `A2UIServices.provideApiKey()` at application startup to configure your Google Maps API Key.

```swift
import SwiftUI
import GoogleMapsA2UI

@main
struct MyApp: App {
    init() {
        A2UIServices.provideApiKey("YOUR_GOOGLE_MAPS_API_KEY")
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

#### 2. Parse the Response
Use the `A2AResponseParser` to safely extract payloads from the raw backend JSON tree into an array of strictly typed events.

The parser searches for the message parts array at the following paths within the dictionary you provide:
* `rawJSON["parts"]`
* `rawJSON["content"]["parts"]`
* `rawJSON["status"]["message"]["parts"]`

> **Note:** If your server wraps the A2A response inside a custom envelope or protocol, ensure to strip the outer wrapper and pass only the inner A2A payload to the parser so it can find the `parts` array at one of the paths above.

```swift
import GoogleMapsA2UI

// Extract standard JSON into A2A events
let parsedParts = (try? A2AResponseParser.parse(rawServerJson)) ?? []
```

#### 3. Render the UI
Feed the parsed events into your SwiftUI layout. The library provides an `A2UIView` that automatically renders rich map interfaces for `.data` events containing an A2UI payload.

```swift
import SwiftUI
import GoogleMapsA2UI

struct ChatMessageView: View {
    let parsedParts: [ParsedA2AEvent]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(parsedParts.enumerated()), id: \.offset) { index, part in
                switch part {
                case .text(let text):
                    // Render plain conversational text in your native chat bubbles
                    Text(text)
                        .padding()
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(8)
                        
                case .data(_, let metadata):
                    if metadata?.mimeType == "application/json+a2ui" {
                        // Let the library render the rich map UI
                        A2UIView(
                            part: part,
                            id: "unique-message-id-\(index)",
                            onUserAction: { actionData in
                                print("User interacted with the map: \(actionData)")
                            }
                        )
                    }
                }
            }
        }
    }
}
```
