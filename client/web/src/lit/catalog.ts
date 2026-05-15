import { basicCatalog } from "@a2ui/lit/v0_9";
import { A2uiGoogleMap } from "./custom-components/google_map";
import { A2uiPlaceCard } from "./custom-components/place_card";
import { Catalog } from "@a2ui/web_core/v0_9";
// import { Column, Row } from "@a2ui/lit/ui";
// import { css } from "lit";

const mapsAgenticUICatalog = new Catalog(
  'a2ui://maps-agentic-ui-catalog.json',
  [
    A2uiGoogleMap,
    A2uiPlaceCard,
    ...basicCatalog.components.values(),
  ],
  Array.from(basicCatalog.functions.values())
)

export { mapsAgenticUICatalog };