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

