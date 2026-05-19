# Maps Agentic UI Toolkit

![Alpha](https://img.shields.io/badge/release-alpha-orange)
[![Python CI](https://github.com/googlemaps/a2ui/actions/workflows/python-ci.yml/badge.svg)](https://github.com/googlemaps/a2ui/actions/workflows/python-ci.yml)
[![Web CI](https://github.com/googlemaps/a2ui/actions/workflows/web-ci.yml/badge.svg)](https://github.com/googlemaps/a2ui/actions/workflows/web-ci.yml)
[![GitHub License](https://img.shields.io/github/license/googlemaps/a2ui?color=blue&v=1)](LICENSE)

> **Note:** This toolkit is in **Experimental** status.

This repository contains the A2UI implementation for the Maps Agentic UI Toolkit. It includes components and handlers implementing the Agent-to-User Interface (A2UI) standard, allowing agents to present rich, interactive interfaces across different platforms.

It makes use of the following technologies:

* [Google Maps Platform](https://mapsplatform.google.com/) for rendering maps and places.
* [A2UI](https://a2ui.org/) for the Agent-driven dynamic UI protocol.
* [ADK](https://google.github.io/adk-docs/) for defining the Agent implementation.
* [A2A Python](https://github.com/a2aproject/a2a-python) for the A2A server implementation.
* [Lit](https://lit.dev/) for the rendering framework for A2UI components.

## Quickstart Guide

To quickly get started, we recommend using the [Agentic UI Toolkit samples project](https://github.com/googlemaps-samples/a2ui). This sample project contains the necessary components to run the Python Agent and a React web client that allows you to interact with the agent.

### Prerequisites and Tool Setup

If you are new to any of these tools or services, here is exactly what you need and how to set them up:

#### 1. Google API Keys
You need two API keys configured as environment variables for the agent to function and render maps correctly:

*   **`GEMINI_API_KEY`**: Your Google Gemini API key. You can get one for free at [Google AI Studio](https://aistudio.google.com/).
*   **`GOOGLE_MAPS_API_KEY`**: Your Google Maps Platform API key. You can create one and enable the Maps JavaScript API in the [Google Cloud Console](https://mapsplatform.google.com/).

These variables must be configured for _both_ your backend (Python agent) and frontend (Web frontend).

For more information about the environment variables, see the **Google API Key Configuration** below.

**How to set your environment variables:**

* **macOS / Linux (Terminal):**
  ```bash
  export GEMINI_API_KEY="your_gemini_api_key_here"
  export GOOGLE_MAPS_API_KEY="your_google_maps_api_key_here"
  ```
* **Windows (PowerShell):**
  ```powershell
  $env:GEMINI_API_KEY="your_gemini_api_key_here"
  $env:GOOGLE_MAPS_API_KEY="your_google_maps_api_key_here"
  ```
* **Windows (Command Prompt):**
  ```cmd
  set GEMINI_API_KEY=your_gemini_api_key_here
  set GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
  ```

#### 2. `uv` (Python Package Manager)
`uv` is an extremely fast Python package and environment manager. It automatically handles creating virtual environments and installing dependencies so you don't have to do it manually.
*   **Installation:** If you do not have `uv` installed, you can install it easily following the official guide at [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/) (for example, on macOS/Linux run `curl -LsSf https://astral.sh/uv/install.sh | sh`).

#### 3. `Node.js` and `npm` (JavaScript Runtime & Package Manager)
`npm` is the standard package manager for JavaScript and TypeScript web applications, used to download frontend libraries and run development servers.
*   **Installation:** Download and install Node.js (which includes `npm`) from [https://nodejs.org/](https://nodejs.org/).

---

## MAUI Python Agent Package (`maui-a2ui-python`)

This package provides the core Python agent implementations for the Agentic UI Toolkit (MAUI). It includes the base `MAUIAgent` and the extended `MAUIAgentWithGrounding` that uses Vertex Grounding.

### File Structure

*   `agent.py`: Contains the `MAUIAgent` class, which handles session management, LLM interaction, and A2UI schema loading.
*   `agent_with_grounding.py`: Contains `MAUIAgentWithGrounding`, extending the base agent with Vertex Grounding capabilities.
*   `shared/`: Contains schema extensions (e.g., `maps_catalog_extension.json`).
*   `skills/`: Contains specific skill definitions used by the agents.
*   `pyproject.toml`: Configuration file for the package, using Hatchling as the build backend.

### How to Integrate

To integrate these agents into an existing application (like a server), you can refer to the sample in [Agentic UI Toolkit Samples](https://github.com/googlemaps-samples/a2ui).

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

The Agentic UI Toolkit includes two agents, one that uses Grounding Lite and one that uses Grounding with Google Maps. The Python integration steps are the same for each, but if you use Grounding with Google Maps, you must follow the instructions to configure your local environment. See the [Accessing Google Maps grounding data](#accessing-google-maps-grounding-data) section below for more information on configuring these services.

Tip: See the [agent_executor.py](https://github.com/googlemaps-samples/a2ui/blob/main/agent/python/agent_executor.py) example in the Agentic UI Toolkit Samples repository for a working example.

Import the MAUIAgent into your Python code (e.g., `__main__.py` or `agent_executor.py`) and
configure the ADK Agent Executor to call it.

```python
# A2UI, ADK, and A2A imports
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    Part,
    Task,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_parts_message,
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from a2ui.a2a.extension import try_activate_a2ui_extension

# MAUI Agent import
from agent import MAUIAgent

class MAUIAgentExecutor(AgentExecutor):

  def __init__(self, agent: MAUIAgent):
    self.agent = agent

  async def execute(
      self,
      context: RequestContext,
      event_queue: EventQueue,
  ) -> None:
    query = context.get_user_input()
    active_ui_version = try_activate_a2ui_extension(context, self.agent.agent_card)
    task = context.current_task

    # Create a new task if necessary
    if not task:
      task = new_task(context.message)
      await event_queue.enqueue_event(task)
    updater = TaskUpdater(event_queue, task.id, task.context_id)

    # Handle each item in the streamed response.
    async for item in self.agent.stream(query, task.context_id, active_ui_version):
      is_task_complete = item["is_task_complete"]
      if not is_task_complete:
        message = None
        if "parts" in item:
          message = new_agent_parts_message(item["parts"], task.context_id, task.id)
        elif "updates" in item:
          message = new_agent_text_message(item["updates"], task.context_id, task.id)

        if message:
          await updater.update_status(TaskState.working, message)
        continue

      final_parts = item["parts"]

      await updater.update_status(
          TaskState.completed,
          new_agent_parts_message(final_parts, task.context_id, task.id),
          final=True,
      )
      break

  async def cancel(
      self, request: RequestContext, event_queue: EventQueue
  ) -> Task | None:
    raise ServerError(error=UnsupportedOperationError())
```

## Agentic UI Toolkit Web Client Library

This package provides the Web (Lit-based) client library for the Maps Agentic UI Toolkit (MAUI). It includes components and utilities to render A2UI surfaces and communicate with an A2A agent server.

### How to Integrate

To integrate these components into an existing application, you can refer to the [Agentic UI Toolkit samples project](https://github.com/googlemaps-samples/a2ui).

#### 1. Install

```bash
npm i @googlemaps/a2ui
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

### Local Development

To make changes to this package and test them in an application:

#### 1. Build and Prepare the Package

To build the package for use in an application:

1.  Open this directory in a terminal.
2.  Install dependencies and link:
    ```bash
    npm run build-and-link
    ```


#### 2. Link the Package
You can consume the package via npm linking for local development:
```bash
# In your application directory
npm link @googlemaps/a2ui
```
## Google API Keys

### Google Maps API Key

Agentic UI Toolkit requires an API Key to use Google Maps Platform products. To create a Google Maps API Key, follow the instructions in the [Google Maps Platform documentation](https://developers.google.com/maps/documentation/javascript/get-api-key).

Your API Key must have the following APIs enabled in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

* Geocoding API  
* Maps JavaScript API  
* Places UI Kit  
* Routes API

To use Grounding Lite MCP, you must also enable:

* Maps Grounding Lite API

To support the use of Grounding Lite within the Python ADK backend, this API Key must be exported or contained within a `.env` file as `GOOGLE_MAPS_API_KEY`.

**Loading the Google Maps JavaScript API**

Your API Key must also be included when loading the Google Maps JavaScript API code. See the [Google Maps Platform Documentation](https://developers.google.com/maps/documentation/javascript/load-maps-js-api) for instructions on how to load the API, including configuring the API Key.

Agentic UI Toolkit requires features available in the Alpha channel. You must use `v=alpha` when loading the Maps JavaScript API. Learn more about versions in the [Google Maps Platform Documentation](https://developers.google.com/maps/documentation/javascript/versions).

Use of Agentic UI Toolkit requires several [Maps JavaScript API libraries](https://developers.google.com/maps/documentation/javascript/libraries). When loading the Google Maps JavaScript API, you must include the following libraries:

* maps  
* maps3d  
* marker  
* places  
* routes

### Gemini API Key

*Note: This API is variously referred to in Google Cloud as the* Gemini API *and the* Generative Language API.

If you are using Gemini as your LLM, you will also need a Google Cloud API Key with the *Generative Language API* enabled. In order to enable this API for your API Key, the *Gemini API* must be enabled for your Google Cloud project. You can enable this API in the [API Library](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com).

To create a new Google Cloud API Key, follow the instructions here in the [Google Cloud docs](https://docs.cloud.google.com/docs/authentication/api-keys#create).

This key must be exported or contained within a `.env` file as `GEMINI_API_KEY`

## Accessing Google Maps grounding data

Your agent can access Google Maps grounding data in two ways, depending on your project setup and needs: 

1. [Grounding Lite MCP](https://developers.google.com/maps/ai/grounding-lite)
2. [Grounding with Google Maps](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-maps)

### Grounding Lite MCP

To use Grounding Lite MCP, you must first enable the Maps Grounding Lite API and create or update an API Key to support the required APIs following the [documentation](https://developers.google.com/maps/ai/grounding-lite#configure_llms_to_use_the_mcp_server).

### Grounding with Google Maps

To use Grounding with Google Maps, there are additional steps you must take to configure your environment:

1. Ensure you have the latest version of the genai python package.
```bash
pip install --upgrade google-genai
```

2. Configure additional environment variables to connect to your project.
```bash
## Replace the `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` values
## with appropriate values for your project.
export GOOGLE_CLOUD_PROJECT=GOOGLE_CLOUD_PROJECT
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_VERTEXAI=True
```

3. Ensure you are authenticated to Google Cloud.
```bash
gcloud auth application-default login
```

See the [documentation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-maps#googlegenaisdk_tools_google_maps_with_txt-python_genai_sdk) for more information.

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
