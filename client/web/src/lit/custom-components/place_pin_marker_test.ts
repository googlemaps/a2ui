// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {calculateLatitudeZIndex, createPlacePinMarkerTemplate, getPinColor, getPinIcon, PlacePinMarker} from './place_pin_marker';

describe('PlacePinMarker Module', () => {
  it('creates gmp-marker element with correct properties', () => {
    const marker = new PlacePinMarker({
      position: {lat: 37.7749, lng: -122.4194},
      label: 'SF Store',
      zIndex: 10,
      autofitsCamera: true,
    });
    const el = marker.getElement() as any;
    expect(el.tagName.toLowerCase()).toBe('gmp-marker');
    expect(el.position).toEqual({lat: 37.7749, lng: -122.4194});
    expect(el.label).toBe('SF Store');
    expect(el.zIndex).toBe(10);
  });

  it('correctly builds HTML custom marker template', () => {
    const template = createPlacePinMarkerTemplate({
      label: 'Retail Store',
      icon: 'retail',
      zIndex: 5,
    });
    expect(template.style.zIndex).toBe('5');
    const labelEl =
        (template.content?.querySelector('.custom-marker-label') ||
         template.querySelector('.custom-marker-label')) as HTMLElement;
    expect(labelEl).not.toBeNull();
    expect(labelEl?.textContent).toBe('Retail Store');

    const iconEl =
        (template.content?.querySelector('.custom-marker-content-icon') ||
         template.querySelector('.custom-marker-content-icon')) as HTMLElement;
    expect(iconEl).not.toBeNull();
    expect(iconEl.style.backgroundColor).toBe('rgb(5, 151, 255)');
  });

  it('resolves POI color and icon lookup with fallbacks', () => {
    expect(getPinColor('retail')).toBe('#0597FF');
    expect(getPinColor('unknown_category')).toBe('#78909C');
    expect(getPinIcon('retail')).toBeDefined();
  });

  it('calculates latitude z-index so southern position gets higher z-index',
     () => {
       const northZ = calculateLatitudeZIndex(47.6062);  // Seattle
       const southZ = calculateLatitudeZIndex(34.0522);  // LA
       expect(southZ).toBeGreaterThan(northZ);
     });
});
