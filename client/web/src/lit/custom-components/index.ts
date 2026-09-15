/*
 Copyright 2026 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import {type Marker3DElementOptions, ThreeDMarker} from './3d_marker.js';
import {AnchorMarker, type AnchorMarkerOptions} from './anchor_marker.js';
import {A2uiGoogleMap, GoogleMap} from './google_map.js';
import {GroundingSource, MauiGroundingSources} from './grounding_sources.js';
import {A2uiPlaceDetailsCompact, PlaceDetailsCompact} from './place_details_compact.js';
import {calculateLatitudeZIndex, type MarkerElementOptions, PlacePinMarker} from './place_pin_marker.js';
import {getPinColor, getPinIcon, PLACE_PIN_COLOR_LOOKUP, PLACE_PIN_ICON_LOOKUP, PLACE_PIN_MARKER_STYLES} from './place_pin_marker_constants.js';

export {type Marker3DElementOptions, ThreeDMarker} from './3d_marker.js';
export {AnchorMarker, type AnchorMarkerOptions} from './anchor_marker.js';
export {A2uiGoogleMap, GoogleMap} from './google_map.js';
export {type GroundingSource, MauiGroundingSources} from './grounding_sources.js';
export {A2uiPlaceDetailsCompact, PlaceDetailsCompact} from './place_details_compact.js';
export {calculateLatitudeZIndex, type MarkerElementOptions, PlacePinMarker} from './place_pin_marker.js';
export {getPinColor, getPinIcon, PLACE_PIN_COLOR_LOOKUP, PLACE_PIN_ICON_LOOKUP, PLACE_PIN_MARKER_STYLES} from './place_pin_marker_constants.js';

export function registerA2UICustomElements(): void {
  if (typeof customElements === 'undefined') return;
  if (!customElements.get('a2ui-googlemap')) {
    customElements.define('a2ui-googlemap', GoogleMap);
  }
  if (!customElements.get('a2ui-placedetailscompact')) {
    customElements.define('a2ui-placedetailscompact', PlaceDetailsCompact);
  }
  if (!customElements.get('maui-grounding-sources')) {
    customElements.define('maui-grounding-sources', MauiGroundingSources);
  }
}