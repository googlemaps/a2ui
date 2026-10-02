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

import {render, TemplateResult} from 'lit';

import {ANCHOR_PIN_SVG} from './anchor_marker_constants';
import {initMaps3DElement} from './maps_api_loader';
import {applyBaseMarkerOptions, calculateLatitudeZIndex, MarkerElementOptions, PlacePinMarkerElement} from './place_pin_marker';

export {ANCHOR_PIN_SVG} from './anchor_marker_constants';

/** Options for creating an AnchorMarker. */
export interface AnchorMarkerOptions extends MarkerElementOptions {
  svgContent?: TemplateResult;
}

/**
 * Helper to generate custom anchor marker template element containing the SVG.
 */
export function createAnchorMarkerTemplate(svgContent = ANCHOR_PIN_SVG):
    HTMLTemplateElement {
  const template = document.createElement('template');
  template.style.display = 'block';

  render(svgContent, template);
  return template;
}

/**
 * AnchorMarker wraps the creation of <gmp-marker> web component elements with
 * custom SVG anchor pin content directly using
 * google.maps.maps3d.MarkerElement.
 */
export class AnchorMarker {
  protected readonly element: HTMLElement;

  constructor(options: AnchorMarkerOptions = {}) {
    const effectiveZIndex = options.zIndex ??
        (options.position ? calculateLatitudeZIndex(options.position.lat) :
                            null);

    const marker =
        document.createElement('gmp-marker') as PlacePinMarkerElement;
    this.element = marker;

    initMaps3DElement(marker, () => {
      applyBaseMarkerOptions(marker, options, effectiveZIndex);
    });

    const template =
        options.htmlContent ?? createAnchorMarkerTemplate(options.svgContent);
    marker.append(template);
  }

  getElement(): HTMLElement {
    return this.element;
  }
}
