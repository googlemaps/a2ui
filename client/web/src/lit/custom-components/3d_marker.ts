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

let nextMarkerId = 0;

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
 * Marker3DElementOptions extending official
 * google.maps.maps3d.Marker3DElementOptions.
 */
export interface Marker3DElementOptions extends google.maps.maps3d
                                                    .Marker3DElementOptions {
  id?: string;
  label?: string|null;
  labelCollisionBehavior?: google.maps.CollisionBehavior;
}

/**
 * ThreeDMarker wraps the creation of <gmp-marker-3d> web component elements
 * based on Marker3DElementOptions, and optionally creates an associated
 * <gmp-label-3d> element if a label is supplied.
 */
export class ThreeDMarker {
  protected readonly element: HTMLElement;
  protected readonly labelElement: HTMLElement|null;

  constructor(options: Marker3DElementOptions = {}) {
    const markerId = options.id ?? `marker-${nextMarkerId++}`;
    const marker = document.createElement('gmp-marker-3d') as
        google.maps.maps3d.Marker3DElement;

    marker.id = markerId;
    if (options.autofitsCamera != null) {
      marker.autofitsCamera = options.autofitsCamera;
    }
    if (options.position) marker.position = options.position;
    if (options.altitudeMode) marker.altitudeMode = options.altitudeMode;
    if (options.collisionBehavior) {
      marker.collisionBehavior = options.collisionBehavior;
    }
    if (options.collisionPriority != null) {
      marker.collisionPriority = options.collisionPriority;
    }
    if (options.drawsWhenOccluded != null) {
      marker.drawsWhenOccluded = options.drawsWhenOccluded;
    }
    if (options.extruded != null) marker.extruded = options.extruded;
    if (options.sizePreserved != null) {
      marker.sizePreserved = options.sizePreserved;
    }
    if (options.zIndex != null) marker.zIndex = options.zIndex;

    this.element = marker;

    if (options.label) {
      const labelEl = document.createElement('gmp-label-3d') as any;
      labelEl.id = `${markerId}-label`;
      labelEl.setAttribute('for', markerId);
      labelEl.collisionBehavior = options.labelCollisionBehavior ??
          (typeof google !== 'undefined' && google.maps &&
                   google.maps.CollisionBehavior ?
               google.maps.CollisionBehavior.OPTIONAL_AND_HIDES_LOWER_PRIORITY :
               'OPTIONAL_AND_HIDES_LOWER_PRIORITY');
      labelEl.textContent = options.label;
      this.labelElement = labelEl;
    } else {
      this.labelElement = null;
    }
  }

  getElement(): HTMLElement {
    return this.element;
  }

  getLabel(): HTMLElement|null {
    return this.labelElement;
  }
}
