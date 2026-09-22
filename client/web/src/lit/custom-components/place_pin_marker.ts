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

import {render} from 'lit';

import {getPinColor, getPinDarkColor, getPinIcon, PLACE_PIN_ICON_LOOKUP} from './place_pin_marker_constants';

export {getPinColor, getPinDarkColor, getPinIcon, PLACE_PIN_COLOR_DARK_LOOKUP, PLACE_PIN_COLOR_LOOKUP, PLACE_PIN_ICON_LOOKUP, PLACE_PIN_MARKER_STYLES} from './place_pin_marker_constants';

/**
 * Helper to dynamically load the maps3d library from google.maps at runtime if
 * needed.
 */
export async function loadMaps3DLibrary():
    Promise<google.maps.Maps3DLibrary|null> {
  if (typeof google !== 'undefined' && google.maps &&
      google.maps.importLibrary) {
    return (await google.maps.importLibrary('maps3d')) as
        google.maps.Maps3DLibrary;
  }
  return null;
}

/**
 * Calculates z-index based on latitude so southern-most markers have higher
 * z-index.
 */
export function calculateLatitudeZIndex(lat: number): number {
  return Math.round((90 - lat) * 10000);
}

/**
 * MarkerElementOptions extending official
 * google.maps.maps3d.MarkerElementOptions.
 */
export interface MarkerElementOptions extends google.maps.maps3d
                                                  .MarkerElementOptions {
  label?: string|null;
  zIndex?: number|null;
  placePrimaryType?: string|null;
  htmlContent?: HTMLElement|HTMLTemplateElement|null;
}

/**
 * Interface extending google.maps.maps3d.MarkerElement with additional custom
 * web component properties.
 */
export type PlacePinMarkerElement = google.maps.maps3d.MarkerElement&{
  label?: string|null;
  zIndex?: number|null;
};

/** Helper to generate custom place pin marker template element. */
export function createPlacePinMarkerTemplate(options: {
  label?: string|null;
  placePrimaryType?: string | null;
  zIndex?: number | null;
}): HTMLTemplateElement {
  const customMarker = document.createElement('template');
  customMarker.classList.add('custom-marker');
  customMarker.style.zIndex = options.zIndex?.toString() || '0';

  const customMarkerContent = document.createElement('div');
  customMarkerContent.classList.add('custom-marker-content');

  const iconContent = getPinIcon(options.placePrimaryType);
  if (iconContent) {
    const customMarkerContentIcon = document.createElement('div');
    customMarkerContentIcon.classList.add('custom-marker-content-icon');
    const safeTypeClass =
        (options.placePrimaryType &&
         PLACE_PIN_ICON_LOOKUP.has(options.placePrimaryType)) ?
        options.placePrimaryType :
        'generic';
    customMarkerContentIcon.classList.add(
        `custom-marker-content-icon--${safeTypeClass}`);

    // Publish both palettes so the stylesheet can resolve the active one via
    // light-dark() without rebuilding the marker on a color scheme change.
    customMarkerContentIcon.style.setProperty(
        '--maui-place-pin-color', getPinColor(options.placePrimaryType));
    customMarkerContentIcon.style.setProperty(
        '--maui-place-pin-color-dark',
        getPinDarkColor(options.placePrimaryType));

    render(iconContent, customMarkerContentIcon);
    customMarkerContent.append(customMarkerContentIcon);
  }

  const customMarkerLabelContainer = document.createElement('div');
  customMarkerLabelContainer.classList.add('custom-marker-label-container');

  const customMarkerLabel = document.createElement('div');
  customMarkerLabel.classList.add('custom-marker-label');
  customMarkerLabel.textContent = options.label || '';
  // Truncate label to 2 lines max, and add ellipsis to overflowing text.
  // https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/line-clamp
  customMarkerLabel.style.display = '-webkit-box';
  customMarkerLabel.style.webkitBoxOrient = 'vertical';
  customMarkerLabel.style.webkitLineClamp = '2';
  customMarkerLabel.style.overflow = 'hidden';

  customMarkerLabelContainer.append(customMarkerLabel);
  customMarkerContent.append(customMarkerLabelContainer);

  customMarker.appendChild(customMarkerContent);
  customMarker.append(customMarkerLabelContainer);

  return customMarker;
}

/**
 * PlacePinMarker wraps the creation of <gmp-marker> web component elements
 * based on MarkerElementOptions.
 */
export class PlacePinMarker {
  protected readonly element: HTMLElement;

  constructor(options: MarkerElementOptions = {}) {
    const effectiveZIndex = options.zIndex ??
        (options.position ? calculateLatitudeZIndex(options.position.lat) :
                            null);

    const marker =
        document.createElement('gmp-marker') as PlacePinMarkerElement;

    // Ensure the marker is autofitted.
    marker.autofitsCamera = options.autofitsCamera ?? true;

    // Pin SVG size is 28px, so subtract that from anchorTop to ensure the
    // marker beak is positioned correctly on the anchor point.
    marker.anchorTop = '-28px';

    // Pass through options to the marker element.
    if (options.position) marker.position = options.position;
    if (options.label) marker.label = options.label;
    if (options.title) marker.title = options.title;
    if (options.collisionBehavior) {
      marker.collisionBehavior =
          options.collisionBehavior as google.maps.CollisionBehaviorString;
    }
    if (options.collisionPriority != null)
      marker.collisionPriority = options.collisionPriority;
    if (effectiveZIndex != null) marker.zIndex = effectiveZIndex;

    const template = options.htmlContent ?? createPlacePinMarkerTemplate({
                       label: options.label,
                       placePrimaryType: options.placePrimaryType,
                       zIndex: effectiveZIndex,
                     });

    marker.append(template);

    this.element = marker;
  }

  getElement(): HTMLElement {
    return this.element;
  }
}
