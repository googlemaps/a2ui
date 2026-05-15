# Google Maps Agentic UI Toolkit

> **Note:** This toolkit is in **Experimental** status.

This repository contains the A2UI reference implementation for the Google Maps Agentic UI Toolkit. It includes tools for implementing the Agent-to-User Interface (A2UI) standard, allowing agents to present rich, interactive interfaces across different platforms.

It makes use of the following technologies:

* [Google Maps Platform](https://mapsplatform.google.com/) for rendering maps and places.
* [A2UI](https://a2ui.org/) for the Agent-driven dynamic UI protocol.
* [ADK](https://google.github.io/adk-docs/) for defining the Agent implementation.
* [A2A Python](https://github.com/a2aproject/a2a-python) for the A2A server implementation.
* [Lit](https://lit.dev/) for the rendering framework for A2UI components.

## Quickstart Guide

To quickly get started, we recommend using the sample project in [a2ui-samples](https://github.com/googlemapssamples/a2ui-samples). This sample project contains the necessary components to run the Python Agent and a React web client that allows you to interact with the agent.

## MAUI Python Agent Package (`maui-a2ui-python`)

This package provides the core Python agent implementations for the Agentic UI Toolkit (MAUI). It includes the base `MAUIAgent` and the extended `MAUIAgentWithGrounding` that uses Vertex Grounding.

### File Structure

*   `agent.py`: Contains the `MAUIAgent` class, which handles session management, LLM interaction, and A2UI schema loading.
*   `agent_with_grounding.py`: Contains `MAUIAgentWithGrounding`, extending the base agent with Vertex Grounding capabilities.
*   `shared/`: Contains schema extensions (e.g., `maps_catalog_extension.json`).
*   `skills/`: Contains specific skill definitions used by the agents.
*   `pyproject.toml`: Configuration file for the package, using Hatchling as the build backend.

### How to Integrate

To integrate these agents into an existing application (like a server), you can refer to the sample in `a2ui-samples/agent/python`.

#### 1. Add Dependency
In your application's `pyproject.toml`, add `maui-a2ui-python` to your dependencies:

```toml
dependencies = [
    "maui-a2ui-python",
]

[tool.uv.sources]
maui-a2ui-python = { path = "path/to/a2ui/agent/python-agent" }
```

#### 2. Import and Use
In your Python code (e.g., `__main__.py` or `agent_executor.py`):

```python
from agent import MAUIAgent
from agent_with_grounding import MAUIAgentWithGrounding

# Initialize the agent
agent = MAUIAgent(base_url="http://localhost:10002")

# Use the agent to stream responses
async for item in agent.stream(query, session_id, ui_version):
    if "parts" in item:
        # Process A2UI parts
        pass
    elif "updates" in item:
        # Process text updates
        pass
```



## MAUI Web Client Library (`@googlemaps/a2ui`)

This package provides the Web (Lit-based) client library for the Agentic UI Toolkit (MAUI). It includes components and utilities to render A2UI surfaces and communicate with an A2A agent server.

### How to Build

To build the package for use in an application:

1.  Open this directory in a terminal.
2.  Install dependencies and link:
    ```bash
    npm run build-and-link
    ```

### How to Integrate

To integrate these components into an existing application, you can refer to the sample in `a2ui-samples/client/web/react`.

#### 1. Link or Install the Package
You can consume the package via npm linking for local development:
```bash
# In your application directory
npm link @googlemaps/a2ui
```

#### 2. Import and Use
In your application code (e.g., a React component):

```tsx
import { A2UIClient, A2UIRenderer, themeStyleSheet } from '@googlemaps/a2ui';

// 1. Adopt the theme stylesheet globally
document.adoptedStyleSheets = [...document.adoptedStyleSheets, themeStyleSheet];

// 2. Initialize client and renderer
const client = new A2UIClient("http://localhost:10002");
const renderer = new A2UIRenderer();

// 3. Add message handling
async function handleSend(messageText: string) {
    renderer.addUserMessage(messageText)

    // 1. Send the message to the A2A agent via A2UIClient
    const response = await client.send(messageText)

    // 2. Process the response (which may contain text and/or A2UI data)
    renderer.processResponse(response);
  }

// 4. Render surfaces in your HTML/JSX

return (
  // Note: <maui-providers> should wrap the area to provide markdown context
  <maui-providers>
    {for (const timelineItem of renderer.timeline) {
    if (timelineItem.type === 'user') {
      return (
        <div className="user-message">
          {timelineItem.text}
        </div>
      )
    } else if (timelineItem.type === 'surface') {
      // Render an A2UI Surface containing multiple UI components
      const surface = renderer.getSurface(timelineItem.surfaceId)
      if (!surface) return null;
      return (
        <div class="surface-message">
          <a2ui-surface
            surface={surface}
          ></a2ui-surface>
        </div>
      ); 
    }
    }}
  </maui-providers>
);
```

## Contributing

External contributions are not accepted for this repository. See [contributing guide] for more info.

## Terms of Service

This library uses Google Maps Platform services. Use of Google Maps Platform services through this library is subject to the Google Maps Platform [Terms of Service]. Some APIs and backend services, such as [Grounding Lite](https://developers.google.com/maps/ai/grounding-lite/attribution) and [Grounding with Google Maps](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-maps#google-maps-attribution-guidelines), have additional Terms of Service requirements which must also be met.

This library is not a Google Maps Platform Core Service. Therefore, the Google Maps Platform Terms of Service (e.g. Technical Support Services, Service Level Agreements, and Deprecation Policy) do not apply to the code in this library.

## Support

This library is offered via an open source [license]. It is not governed by the Google Maps Platform Support [Technical Support Services Guidelines, the SLA, or the [Deprecation Policy]. However, any Google Maps Platform services used by the library remain subject to the Google Maps Platform Terms of Service.

[contributing guide]: CONTRIBUTING.md
[license]: LICENSE
[Deprecation Policy]: https://cloud.google.com/maps-platform/terms
[Technical Support Services Guidelines]: https://cloud.google.com/maps-platform/terms/tssg
[Terms of Service]: https://cloud.google.com/maps-platform/terms
