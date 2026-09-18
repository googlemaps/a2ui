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

import {calculateLatitudeZIndex, createPlacePinMarkerTemplate, getPinColor, getPinDarkColor, getPinIcon, PLACE_PIN_COLOR_DARK_LOOKUP, PLACE_PIN_COLOR_LOOKUP, PLACE_PIN_ICON_LOOKUP, PLACE_PIN_MARKER_STYLES, PlacePinMarker} from './place_pin_marker';

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
      placePrimaryType: 'retail',
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
    expect(iconEl.style.getPropertyValue('--maui-place-pin-color'))
        .toBe('#0597FF');
    expect(iconEl.style.getPropertyValue('--maui-place-pin-color-dark'))
        .toBe('#68AFF0');
  });

  it('resolves POI color and icon lookup with fallbacks', () => {
    expect(getPinColor('retail')).toBe('#0597FF');
    expect(getPinColor('unknown_category')).toBe('#78909C');
    expect(getPinIcon('retail')).toBeDefined();
  });

  it('resolves dark POI colors with fallbacks', () => {
    expect(getPinDarkColor('retail')).toBe('#68AFF0');
    expect(getPinDarkColor('unknown_category')).toBe('#8DA6B2');
    expect(getPinDarkColor(null)).toBe('#8DA6B2');
  });

  it('keeps the light and dark palettes in sync', () => {
    expect([...PLACE_PIN_COLOR_DARK_LOOKUP.keys()]).toEqual([
      ...PLACE_PIN_COLOR_LOOKUP.keys()
    ]);
    expect([...PLACE_PIN_COLOR_LOOKUP.keys()]).toEqual([
      ...PLACE_PIN_ICON_LOOKUP.keys()
    ]);
  });

  it('supports the gas_station and bank categories', () => {
    // `gas_station` replaces the former `service` category and keeps its color.
    expect(getPinColor('gas_station')).toBe('#7986CB');
    expect(getPinIcon('gas_station')).toBeDefined();
    expect(PLACE_PIN_ICON_LOOKUP.has('bank')).toBeTrue();
    expect(PLACE_PIN_COLOR_LOOKUP.has('bank')).toBeTrue();
  });

  it('no longer supports the removed service and closed categories', () => {
    expect(PLACE_PIN_ICON_LOOKUP.has('service')).toBeFalse();
    expect(PLACE_PIN_ICON_LOOKUP.has('closed')).toBeFalse();
    // Removed categories fall back to generic rather than rendering nothing.
    expect(getPinColor('closed')).toBe('#78909C');
    expect(getPinIcon('closed')).toBe(PLACE_PIN_ICON_LOOKUP.get('generic'));
  });

  it('renders glyphs with currentColor so they follow the color scheme', () => {
    const template = createPlacePinMarkerTemplate({
      label: 'Cafe',
      placePrimaryType: 'food_and_drink',
    });
    const iconEl =
        (template.content?.querySelector('.custom-marker-content-icon') ||
         template.querySelector('.custom-marker-content-icon')) as HTMLElement;
    const paths = iconEl.querySelectorAll('path');
    expect(paths.length).toBeGreaterThan(0);
    for (const path of Array.from(paths)) {
      expect(path.getAttribute('fill')).toBe('currentColor');
    }
  });

  it('pins the ev and parking glyph colors across both color schemes', () => {
    const css = PLACE_PIN_MARKER_STYLES.cssText;
    // These two categories reuse one disc color in light and dark, so their
    // glyphs must not resolve through light-dark().
    expect(css).toContain('.custom-marker-content-icon--ev');
    expect(css).toContain('#218c80');
    expect(css).toContain('.custom-marker-content-icon--parking');
    expect(css).toContain('#4c3cff');
    expect(css).not.toContain('light-dark(#218c80');
    expect(css).not.toContain('light-dark(#4c3cff');
  });

  it('calculates latitude z-index so southern position gets higher z-index',
     () => {
       const northZ = calculateLatitudeZIndex(47.6062);  // Seattle
       const southZ = calculateLatitudeZIndex(34.0522);  // LA
       expect(southZ).toBeGreaterThan(northZ);
     });
});
