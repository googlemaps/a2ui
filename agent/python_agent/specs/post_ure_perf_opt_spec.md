# Implementation Spec: MAUI Post-URE Payload Decimation & Intent Model Routing

- **Status**: Implemented / Verified
- **Target Package**: `//third_party/googlemaps/a2ui/agent/python_agent`
- **Owner**: `hungmn@google.com`
- **Related Issues / Tasks**: b/546203225

---

## 1. Problem Statement & Scope

During the Post-User Request Execution (URE) phase of the MAUI template agent pipeline, two primary latency bottlenecks were identified:
1. **Uncompressed MCP Tool Prefill Overhead**: Tool payloads from Places and Directions MCP servers return extensive polyline coordinate arrays and verbose metadata (`photos`, `photos_url`, `reviews_url`, `write_a_review_url`), pushing LLM prefill context from ~8k tokens up to ~25k tokens. This adds 400ms–600ms to Time-to-First-Token (TTFT).
2. **Compute Over-Provisioning on Simple Spatial Queries**: Single-constraint spatial queries (`OTHER_SPATIAL`) are routed to `gemini-3.7-flash` with unconstrained turn limits, incurring unnecessary model latency when `gemini-3.5-flash-lite` with a 2-step iteration cap satisfies intent fulfillment with lower latency.

---

## 2. Architecture & Component Contracts

### 2.1 Tool Payload Pruning (`after_tools_callback.py`)
Intercept tool responses prior to LLM prefill:
- **Directions & Routes**:
  - Strip full-resolution coordinate arrays (`polyline`, `encoded_polyline`) from routes, legs, and individual navigation steps.
  - Preserve step-by-step textual guidance strings (`navigation_instruction`, `distance`, `duration`) required for conversational grounding.
- **Places**:
  - Strip photo metadata arrays (`photos`, `photos_url`).
  - Strip review action URLs (`reviews_url`, `write_a_review_url`).
  - Cap review lists to the top 2 entries.

### 2.2 Intent Router Complexity Classification (`template_registry.py`)
Add query complexity classification to the intent router:
- Schema extension on `RouterClassification`:
  ```python
  class RouterClassification(pydantic.BaseModel):
    intent: IntentType
    use_case: str
    complexity: Literal["simple", "complex"] = "complex"
    confidence: float
  ```
- Few-shot instructions in `compile_router_instruction()` directing the model to classify single-entity, direct queries as `"simple"` and multi-stop or constraint-heavy queries as `"complex"`.

### 2.3 Dynamic Model Routing & Guardrails (`agent_with_templates.py`)
- For `intent == IntentType.OTHER_SPATIAL` and `complexity == "simple"`:
  - Route to `_grounded_text_runner` using `gemini-3.5-flash-lite`.
  - Enforce `max_llm_calls = 2` to prevent runaway reasoning loops.
- For `complexity == "complex"`:
  - Retain `_fallback_text_runner` using `gemini-3.7-flash`.
- **Rule 6 Zero-Retry Invariant**: In `_GROUNDED_TEXT_BASE_INSTRUCTION`, terminate immediately with an informational message when tool results are empty or missing; do not retry with alternative names.

---

## 3. Invariants & Backward Compatibility

1. **Schema Non-Regression**: Pruning must not remove fields used by A2UI card schemas (`formatted_address`, `place_id`, `rating`, `user_ratings_total`).
2. **Defensive Defaults**: Default `complexity = "complex"` ensures backward compatibility if the router fails or emits unparseable JSON.
3. **Hermetic Test Coverage**: Ensure all existing unit tests in `//third_party/googlemaps/a2ui/agent/python_agent:all` continue to pass without network dependencies.

---

## 4. Verification & Empirical Acceptance Criteria

- **Hermetic Tests**:
  - `test_after_tools_callback.py`: Tests `test_after_tools_callback_decimates_places` and `test_after_tools_callback_decimates_routes`.
  - `test_agent_with_templates.py`: Tests `test_grounded_text_run_config_simple_lite` and `test_grounded_text_run_config_complex_pro`.
  - Golden files: Synchronized `testdata/router_instruction.golden.txt`.
- **Empirical SLA Gates (`references/eval_playbook.md`)**:
  - **Tier 1 Screening (N=16)**: TTFT reduction $\ge 25\%$; zero template regressions.
  - **Tier 2 Stratified Split (N=50)**: Statistically significant latency reduction ($p < 0.05$); catalog adherence 100%.
  - **Test Suite**: `/google/bin/releases/arca9-local-blaze-cli/blaze-for-agents test //third_party/googlemaps/a2ui/agent/python_agent:all` (13/13 targets green).
