# MAUI Python Agent Package (`maui-a2ui-python`)

This package provides the core Python agent implementations for the Agentic UI Toolkit (MAUI). It includes the base `MAUIAgent` and the extended `MAUIAgentWithGrounding` that uses Vertex Grounding.

## File Structure

*   `agent.py`: Contains the `MAUIAgent` class, which handles session management, LLM interaction, and A2UI schema loading.
*   `agent_with_grounding.py`: Contains `MAUIAgentWithGrounding`, extending the base agent with Vertex Grounding capabilities.
*   `shared/`: Contains schema extensions (e.g., `maps_catalog_extension.json`).
*   `skills/`: Contains specific skill definitions used by the agents.
*   `pyproject.toml`: Configuration file for the package, using Hatchling as the build backend.

## How to Integrate

To integrate these agents into an existing application (like a server), you can refer to the sample in `a2ui-samples/agent/python`.

### 1. Add Dependency
In your application's `pyproject.toml`, add `maui-a2ui-python` to your dependencies:

```toml
dependencies = [
    "maui-a2ui-python",
]

[tool.uv.sources]
maui-a2ui-python = { path = "path/to/a2ui/agent/python-agent" }
```

### 2. Import and Use

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
