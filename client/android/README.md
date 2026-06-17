# GoogleMapsA2UI Android Library

![Alpha](https://img.shields.io/badge/release-alpha-orange)

## Overview
The **GoogleMapsA2UI** library is an Android SDK designed to encapsulate the parsing and rendering of Google Maps Platform Agent-to-UI (A2UI) payloads. It seamlessly converts complex A2A JSON responses into native-friendly, rich map interfaces using a specialized WebView-based component.

It makes use of the following technologies:
*   **Google Maps Platform** for rendering maps and places.
*   **A2UI** for the Agent-driven dynamic UI protocol.
*   **React** for the underlying web-based rendering engine.

## Prerequisites
*   **Protocol Version:** This library is built based on the **v0.9 A2UI protocol** and is **not backward compatible** with the v0.8 protocol. Ensure your backend server uses the v0.9 protocol format.
*   **Android Studio:** Koala (2024.1.1) or later.
*   **Android SDK:** 
    *   **Library:** API Level 24 or later.
    *   **Sample App:** API Level 26 or later.
*   **Java:** JDK 17.
*   **Google Maps API Key:** Required for rendering map components.

## Build the Library

Before building any sample applications that depend on this library, you must build and publish it to your local Maven repository.

1. Open a terminal and navigate to the Library directory:
   ```bash
   cd ~/ai-kit/a2ui/client/android/GoogleMapsA2UI
   ```
2. Publish the Library to your local Maven repository:
   ```bash
   ./gradlew publishToMavenLocal
   ```

## SDK Reference & Usage

### 1. Global Initialization
Configure the Google Maps API Key once at the application level (e.g., in `MainActivity.onCreate` or a custom `Application` class) before any A2UI components are rendered.

```kotlin
import com.google.android.gms.maps.a2ui.A2UIServices

// Initialize the SDK configuration globally once
A2UIServices.provideAPIKey("YOUR_GOOGLE_MAPS_API_KEY")
```

### 2. Parse the Server Response
Use the `A2AResponseParser` to safely extract payloads from the raw backend JSON tree into an ordered list of `ParsedA2AEvent` objects. This preserves the sequential order of conversational text and rich UI. *(Note: The snippet below is simplified pseudocode. For the complete implementation handling streaming aggregation, refer to `MainActivity.kt` in the sample app).*

```kotlin
import com.google.android.gms.maps.a2ui.A2AResponseParser

// SDK parses the response into an ordered list of parts
val parsedParts = A2AResponseParser.parse(rawJson)

for (part in parsedParts) {
    when (part) {
        is ParsedA2AEvent.Text -> {
            // Render plain conversational text in your native chat bubbles
            chatAdapter.addTextMessage(part.text)
        }
        is ParsedA2AEvent.Data -> {
            // Feed the structured data into A2UIView
            chatAdapter.addGmpA2UIViewMessage(part.data)
        }
    }
}
```

### 3. Rendering the View
The library provides `A2UIView`, a custom component that manages the rendering of rich map interfaces. It handles dynamic height resizing and user interaction callbacks automatically.

**XML Layout:**
```xml
<com.google.android.libraries.mapsplatform.a2ui.A2UIView
    android:id="@+id/gmpA2UIView"
    android:layout_width="match_parent"
    android:layout_height="wrap_content" />
```

**ViewHolder Implementation:**
```kotlin
class GmpA2UIViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
    val gmpA2UIView: A2UIView = itemView.findViewById(R.id.gmpA2UIView)

    fun bind(a2uiJson: String) {
        gmpA2UIView.render(a2uiJson)
    }

    // Support real-time SSE streaming updates
    fun updateStreamingJson(newJson: String) {
        gmpA2UIView.updateA2uiJson(newJson)
    }
}
```

## Architecture Deep Dive

The SDK encapsulates all complex parsing and rendering logic into four core components:

1.  **Data Model (`ParsedA2AEvent`)**: A standardized, ordered sealed interface outputting plain text and extracted JSON (data), supporting sequential rendering for the host app.
2.  **The Parser (`A2AResponseParser`)**: A static utility that navigates complex JSON trees, uses Regex to extract payloads from Markdown blocks, and handles deduplication of redundant UI commands.
3.  **Core Visual Component (`A2UIView`)**: A custom WebView-based component that handles local asset loading, API key injection, and URL interception (launching the native Maps app).
4.  **JS Communication Bridge (`WebAppInterface`)**: Manages bidirectional communication. It sends data from Android to JS and receives callbacks for events like webpage resizing and user actions.


## Updating the React Frontend (React Renderer Updates)

The `GoogleMapsA2UI` library relies on a pre-built React web frontend bundle (`index.html`) which is shipped inside its `assets` folder.

If you have customized your `internal-usage-attribution-ids` or modified the underlying web components, you must recompile the frontend and bundle it back into this Android Library.

Steps to update the React renderer with your customizations:

1. **Build the local A2UI web library:**
   ```bash
   cd ~/ai-kit/a2ui/client/web
   npm run build-and-link
   ```

2. **Rebuild the React app and bundle it into a single HTML file:**
   ```bash
   cd ~/ai-kit/a2ui-samples/client/web/react
   npm install
   npm link @googlemaps/a2ui
   npm run build:mobile
   ```

3. **Copy the compiled `index.html` into the Android Library's assets folder:**
   ```bash
   cp ~/ai-kit/a2ui-samples/client/web/react/dist/index.html ~/ai-kit/a2ui/client/android/GoogleMapsA2UI/src/main/assets/
   ```

4. **Re-publish the Library:**
   Finally, re-publish the SDK to Maven Local (Step 2 above) and reinstall your Android application to see the changes.