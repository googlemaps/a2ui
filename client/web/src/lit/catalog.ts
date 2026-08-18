// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
 // You may obtain a copy of the License at
//
//      https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { basicCatalog } from "@a2ui/lit/v0_9";
import { A2uiGoogleMap } from "./custom-components/google_map";
import { A2uiPlaceDetailsCompact } from "./custom-components/place_details_compact";
import { Catalog } from "@a2ui/web_core/v0_9";
// import { Column, Row } from "@a2ui/lit/ui";
// import { css } from "lit";

const mapsAgenticUICatalog = new Catalog(
  'a2ui://maps-agentic-ui-catalog.json',
  [
    A2uiGoogleMap,
    A2uiPlaceDetailsCompact,
    ...basicCatalog.components.values(),
  ],
  Array.from(basicCatalog.functions.values())
)

export { mapsAgenticUICatalog };
