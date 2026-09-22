# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ADK Tools for MAUI template population and rendering.

This file contains a set of tools for rendering the MAUI A2UI templates.
The tools are used by the MAUI agent to render the templates based on the
user's query and the agent's extracted information.

The currently supported templates are:
- Local Search: Used to show a list of local places and a map.
- Directions: Used to show a route on a map.
- Text-only: Used to render a text-only response inside an A2UI surface.

Tools are built dynamically based on their Pydantic schema to ensure
type safety and accurate function declarations.
"""

from __future__ import annotations

import copy
import inspect
import logging
import time
from typing import Any, Optional, Union
import uuid

from a2a.types import Part
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools._automatic_function_calling_util import build_function_declaration
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset, ToolPredicate
from google.adk.tools.set_model_response_tool import _merge_json_schema_descriptions
from google.adk.tools.tool_context import ToolContext
from google.genai import types
import pydantic

from a2ui.a2a.parts import create_a2ui_part
from a2ui.schema.manager import A2uiSchemaManager
from extractor import DirectionsExtractorSchema
from extractor import LocalSearchExtractorSchema
from merger import DEFAULT_CATALOG_ID
from merger import merge_template

logger = logging.getLogger(__name__)

STATE_RENDERED_A2UI_PARTS = "rendered_a2ui_parts"
STATE_RENDERED_A2UI_DATA = "rendered_a2ui_data"


class BaseTemplateTool(BaseTool):
  """Base class for ADK tools that populate and render A2UI templates."""

  name: str = ""
  description: str = ""
  template_name: str = ""
  schema_class: type[pydantic.BaseModel] | None = None

  def __init__(
      self,
      *,
      name: str | None = None,
      description: str | None = None,
      template_name: str | None = None,
      schema_class: type[pydantic.BaseModel] | None = None,
      schema_manager: A2uiSchemaManager | None = None,
      max_list_size: int = 5,
      surface_id_prefix: str | None = None,
      catalog_id: str = DEFAULT_CATALOG_ID,
  ) -> None:
    tool_name = name or self.name
    tool_desc = description or self.description
    super().__init__(name=tool_name, description=tool_desc)
    self.template_name = template_name or self.template_name
    self.schema_class = (
        schema_class if schema_class is not None else self.schema_class
    )
    self.schema_manager = schema_manager
    self.max_list_size = max_list_size
    self.catalog_id = catalog_id
    self.surface_id_prefix = (
        surface_id_prefix or f"{self.template_name}-surface"
    )
    self._func = self._build_handler_func()

  def _build_handler_func(self) -> Any:
    """Builds the callable signature used for FunctionDeclaration generation."""
    if self.schema_class is not None:
      schema_fields = self.schema_class.model_fields
      params = []
      for field_name, field_info in schema_fields.items():
        param = inspect.Parameter(
            field_name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=field_info.annotation,
            default=(
                inspect.Parameter.empty
                if field_info.is_required()
                else field_info.get_default(call_default_factory=True)
            ),
        )
        params.append(param)

      def dynamic_tool_func(**kwargs: Any) -> str:
        del kwargs
        return f"Rendered {self.template_name} template."

      new_sig = inspect.Signature(parameters=params)
      setattr(dynamic_tool_func, "__signature__", new_sig)
      setattr(dynamic_tool_func, "__name__", self.name)
      setattr(dynamic_tool_func, "__doc__", self.description)
      return dynamic_tool_func
    else:

      def text_only_tool_func(text: str) -> str:
        """Render a text-only UI response."""
        del text
        return f"Rendered {self.template_name} template."

      setattr(text_only_tool_func, "__name__", self.name)
      setattr(text_only_tool_func, "__doc__", self.description)
      return text_only_tool_func

  def _preserve_schema_descriptions(
      self, function_decl: types.FunctionDeclaration
  ) -> None:
    """Restores field descriptions from Pydantic schema onto FunctionDeclaration."""
    if self.schema_class is not None:
      source_schema = self.schema_class.model_json_schema()
      if function_decl.parameters_json_schema is not None:
        _merge_json_schema_descriptions(
            function_decl.parameters_json_schema, source_schema
        )
      elif function_decl.parameters is not None:
        from google.adk.tools.set_model_response_tool import (  # pylint: disable=g-import-not-at-top
            _apply_descriptions_to_schema_properties,
        )

        _apply_descriptions_to_schema_properties(
            function_decl.parameters.properties,
            self.schema_class.model_fields,
        )

  def _get_declaration(self) -> Optional[types.FunctionDeclaration]:
    """Gets OpenAPI FunctionDeclaration specification for this tool."""
    function_decl = types.FunctionDeclaration.model_validate(
        build_function_declaration(
            func=self._func,
            ignore_params=[],
            variant=self._api_variant,
        )
    )
    self._preserve_schema_descriptions(function_decl)
    return function_decl

  async def run_async(
      self, *, args: dict[str, Any], tool_context: ToolContext
  ) -> dict[str, Any]:
    """Executes the template tool: validates args, merges template, and saves A2UI parts."""
    start_time = time.perf_counter()
    logger.info("--- TEMPLATE_TOOL: Invoked '%s' ---", self.name)
    logger.info("  Tool: %s (template: %s)", self.name, self.template_name)
    logger.info("  Parameters: %s", args)
    validated_data = copy.deepcopy(args)

    # 1. Validate arguments against Pydantic schema
    if self.schema_class is not None:
      try:
        model_instance = self.schema_class.model_validate(args)
        validated_data = model_instance.model_dump(exclude_none=True)
      except pydantic.ValidationError as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "--- TEMPLATE_TOOL: Validation failed for '%s' in %.2f ms: %s ---",
            self.name,
            elapsed_ms,
            e,
        )
        return {
            "error": (
                f"Validation failed for tool '{self.name}': {e}. "
                "Please fix the parameters and call the tool again."
            )
        }

    # 2. Ensure unique surface_id
    if not validated_data.get("surface_id"):
      short_id = uuid.uuid4().hex[:8]
      validated_data["surface_id"] = f"{self.surface_id_prefix}-{short_id}"

    # 3. Merge template
    try:
      merged_actions = merge_template(
          self.template_name,
          validated_data,
          max_list_size=self.max_list_size,
          catalog_id=self.catalog_id,
      )
    except Exception as e:  # pylint: disable=broad-exception-caught
      elapsed_ms = (time.perf_counter() - start_time) * 1000
      logger.warning(
          "--- TEMPLATE_TOOL: Failed to merge template '%s' in %.2f ms: %s ---",
          self.template_name,
          elapsed_ms,
          e,
      )
      return {"error": f"Failed to merge template '{self.template_name}': {e}"}

    # 4. Catalog schema validation
    if self.schema_manager:
      selected_catalog = self.schema_manager.get_selected_catalog()
      if selected_catalog:
        try:
          selected_catalog.validator.validate(merged_actions)
        except Exception as e:  # pylint: disable=broad-exception-caught
          elapsed_ms = (time.perf_counter() - start_time) * 1000
          logger.warning(
              "--- TEMPLATE_TOOL: Catalog validation failed for '%s' in %.2f"
              " ms: %s ---",
              self.template_name,
              elapsed_ms,
              e,
          )
          return {
              "error": (
                  f"A2UI catalog schema validation failed: {e}. "
                  "Please fix the parameters and retry."
              )
          }

    # 5. Convert to A2A Parts and persist to session state
    rendered_parts: list[Part] = [
        create_a2ui_part(action) for action in merged_actions
    ]
    if tool_context and getattr(tool_context, "state", None) is not None:
      tool_context.state[STATE_RENDERED_A2UI_PARTS] = rendered_parts
      tool_context.state[STATE_RENDERED_A2UI_DATA] = validated_data

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "--- TEMPLATE_TOOL: Successfully rendered '%s' (surface_id: %s) in %.2f"
        " ms (%d parts) ---",
        self.template_name,
        validated_data["surface_id"],
        elapsed_ms,
        len(rendered_parts),
    )

    return {
        "status": "success",
        "surface_id": validated_data["surface_id"],
        "template": self.template_name,
        "latency_ms": round(elapsed_ms, 2),
        "message": f"Successfully rendered {self.template_name} UI interface.",
    }


class RenderLocalSearchTemplateTool(BaseTemplateTool):
  """ADK Tool that validates and renders a local search map layout."""

  name: str = "render_local_search_template"
  description: str = (
      "Renders an interactive Google Maps local search UI component"
      " populated with places, map markers, and a summary response."
  )
  template_name: str = "local_search"
  schema_class: type[pydantic.BaseModel] | None = LocalSearchExtractorSchema

  def __init__(
      self,
      *,
      name: str | None = None,
      description: str | None = None,
      schema_manager: A2uiSchemaManager | None = None,
      max_list_size: int = 5,
      surface_id_prefix: str = "local-search-surface",
      catalog_id: str = DEFAULT_CATALOG_ID,
  ) -> None:
    super().__init__(
        name=name,
        description=description,
        schema_manager=schema_manager,
        max_list_size=max_list_size,
        surface_id_prefix=surface_id_prefix,
        catalog_id=catalog_id,
    )


class RenderDirectionsTemplateTool(BaseTemplateTool):
  """ADK Tool that validates and renders a directions and route map layout."""

  name: str = "render_directions_template"
  description: str = (
      "Renders an interactive Google Maps directions and routing UI"
      " component populated with route segments, travel mode, and a"
      " summary response."
  )
  template_name: str = "directions"
  schema_class: type[pydantic.BaseModel] | None = DirectionsExtractorSchema

  def __init__(
      self,
      *,
      name: str | None = None,
      description: str | None = None,
      schema_manager: A2uiSchemaManager | None = None,
      max_list_size: int = 5,
      surface_id_prefix: str = "directions-surface",
      catalog_id: str = DEFAULT_CATALOG_ID,
  ) -> None:
    super().__init__(
        name=name,
        description=description,
        schema_manager=schema_manager,
        max_list_size=max_list_size,
        surface_id_prefix=surface_id_prefix,
        catalog_id=catalog_id,
    )


class RenderTextOnlyTemplateTool(BaseTemplateTool):
  """ADK Tool that renders a text-only response inside an A2UI surface container."""

  name: str = "render_text_only_template"
  description: str = (
      "Renders a text response formatted inside an A2UI surface container."
  )
  template_name: str = "text_only"
  schema_class: type[pydantic.BaseModel] | None = None

  def __init__(
      self,
      *,
      name: str | None = None,
      description: str | None = None,
      schema_manager: A2uiSchemaManager | None = None,
      surface_id_prefix: str = "text-only-surface",
      catalog_id: str = DEFAULT_CATALOG_ID,
  ) -> None:
    super().__init__(
        name=name,
        description=description,
        schema_manager=schema_manager,
        max_list_size=1,
        surface_id_prefix=surface_id_prefix,
        catalog_id=catalog_id,
    )


class TemplateToolset(BaseToolset):
  """Toolset bundling all A2UI template population tools."""

  def __init__(
      self,
      *,
      schema_manager: A2uiSchemaManager | None = None,
      max_list_size: int = 5,
      tool_filter: Optional[Union[ToolPredicate, list[str]]] = None,
      tool_name_prefix: Optional[str] = None,
      catalog_id: str = DEFAULT_CATALOG_ID,
  ) -> None:
    super().__init__(tool_filter=tool_filter, tool_name_prefix=tool_name_prefix)
    self.schema_manager = schema_manager
    self.max_list_size = max_list_size
    self.catalog_id = catalog_id
    self._tools: list[BaseTool] = [
        RenderLocalSearchTemplateTool(
            schema_manager=self.schema_manager,
            max_list_size=self.max_list_size,
            catalog_id=self.catalog_id,
        ),
        RenderDirectionsTemplateTool(
            schema_manager=self.schema_manager,
            max_list_size=self.max_list_size,
            catalog_id=self.catalog_id,
        ),
        RenderTextOnlyTemplateTool(
            schema_manager=self.schema_manager,
            catalog_id=self.catalog_id,
        ),
    ]

  async def get_tools(
      self,
      readonly_context: Optional[ReadonlyContext] = None,
  ) -> list[BaseTool]:
    """Returns the template tools exposed by this toolset."""
    del readonly_context
    return list(self._tools)
