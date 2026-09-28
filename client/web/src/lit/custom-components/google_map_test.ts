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

import './google_map';

import {type GoogleMap, GoogleMapApi} from './google_map';
import {PlacePinMarker} from './place_pin_marker';

interface GoogleMapInternals {
  _controller: {
    props: {
      center: {lat: number; lng: number};
      markers?: unknown[];
      travelMode?: string | null;
      routes?: Array<{
        origin: {lat: number; lng: number; label: string};
        destination: {lat: number; lng: number; label: string};
      }>;
    };
  };
  prevCenter: {lat: number; lng: number}|null;
}

describe('GoogleMap Component', () => {
  let originalGoogle: unknown;
  let originalAttributionId: unknown;

  beforeEach(() => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    originalGoogle = windowWithGlobals['google'];
    originalAttributionId = windowWithGlobals['A2UI_ATTRIBUTION_ID'];

    // Common google mock setup
    windowWithGlobals['google'] = {
      maps: {
        CollisionBehavior: {
          OPTIONAL_AND_HIDES_LOWER_PRIORITY: 'OPTIONAL_AND_HIDES_LOWER_PRIORITY'
        },
        maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}}
      }
    };
  });

  afterEach(() => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    windowWithGlobals['google'] = originalGoogle;
    windowWithGlobals['A2UI_ATTRIBUTION_ID'] = originalAttributionId;
  });

  it('uses a fallback attribution ID when the global one is missing',
     async () => {
       // 1. Explicitly remove any global attribution ID
       delete (
           window as unknown as Record<string, unknown>)['A2UI_ATTRIBUTION_ID'];

       // 2. Render the component with empty props so it falls back to defaults
       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as GoogleMapInternals;
       internals._controller = {props: {markers: [], center: {lat: 0, lng: 0}}};
       internals.prevCenter = {lat: 0, lng: 0};
       document.body.appendChild(element);

       // Wait for lit to finish initial render
       await element.updateComplete;

       // 3. Query the rendered map using renderRoot (since shadowRoot is
       // closed)
       const gmpMap3d = element.renderRoot.querySelector('gmp-map-3d');

       // 4. Assert that the attribute has the correct fallback ID
       const attrId = gmpMap3d!.getAttribute('internal-usage-attribution-ids');
       expect(attrId).toBe('gmp_web_maui_v0.1.8_atoui');

       // Cleanup
       document.body.removeChild(element);
     });

  it('propagates travelMode to gmp-route-3d', async () => {
    // 1. Render the component with travelMode and routes
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {
      props: {
        center: {lat: 0, lng: 0},
        travelMode: 'driving',
        routes: [{
          origin: {lat: 1, lng: 1, label: 'Origin'},
          destination: {lat: 2, lng: 2, label: 'Destination'},
        }]
      }
    };
    internals.prevCenter = {lat: 0, lng: 0};
    document.body.appendChild(element);

    // Wait for lit to finish initial render
    await element.updateComplete;

    // 2. Query the rendered route
    const gmpRoute3d = element.renderRoot.querySelector('gmp-route-3d');
    expect(gmpRoute3d).not.toBeNull();

    // 3. Assert that travel-mode attribute is set to 'driving'
    const travelModeAttr = gmpRoute3d!.getAttribute('travel-mode');
    expect(travelModeAttr).toBe('driving');

    // Cleanup
    document.body.removeChild(element);
  });

  it('mirrors an explicit map color scheme onto the CSS color-scheme',
     async () => {
       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as GoogleMapInternals;
       internals._controller = {props: {markers: [], center: {lat: 0, lng: 0}}};
       internals.prevCenter = {lat: 0, lng: 0};
       document.body.appendChild(element);
       await element.updateComplete;

       const gmpMap3d = element.renderRoot.querySelector('gmp-map-3d')!;
       // Place pins resolve their light-dark() tokens against this property,
       // so an explicit map-level scheme must reach it.
       expect(getComputedStyle(gmpMap3d).colorScheme).not.toBe('dark');

       gmpMap3d.setAttribute('color-scheme', 'DARK');
       expect(getComputedStyle(gmpMap3d).colorScheme).toBe('dark');

       gmpMap3d.setAttribute('color-scheme', 'LIGHT');
       expect(getComputedStyle(gmpMap3d).colorScheme).toBe('light');

       // Cleanup
       document.body.removeChild(element);
     });

  it('does not propagate travelMode if it is not provided', async () => {
    // 1. Render the component without travelMode but with routes
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {
      props: {
        center: {lat: 0, lng: 0},
        routes: [{
          origin: {lat: 1, lng: 1, label: 'Origin'},
          destination: {lat: 2, lng: 2, label: 'Destination'},
        }]
      }
    };
    internals.prevCenter = {lat: 0, lng: 0};
    document.body.appendChild(element);

    // Wait for lit to finish initial render
    await element.updateComplete;

    // 2. Query the rendered route
    const gmpRoute3d = element.renderRoot.querySelector('gmp-route-3d');
    expect(gmpRoute3d).not.toBeNull();

    // 3. Assert that travel-mode attribute is not set
    const travelModeAttr = gmpRoute3d!.getAttribute('travel-mode');
    expect(travelModeAttr).toBeNull();

    // Cleanup
    document.body.removeChild(element);
  });

  it('does not propagate travelMode if it is null', async () => {
    // 1. Render the component with travelMode set to null
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {
      props: {
        center: {lat: 0, lng: 0},
        travelMode: null,
        routes: [{
          origin: {lat: 1, lng: 1, label: 'Origin'},
          destination: {lat: 2, lng: 2, label: 'Destination'},
        }]
      }
    };
    internals.prevCenter = {lat: 0, lng: 0};
    document.body.appendChild(element);

    // Wait for lit to finish initial render
    await element.updateComplete;

    // 2. Query the rendered route
    const gmpRoute3d = element.renderRoot.querySelector('gmp-route-3d');
    expect(gmpRoute3d).not.toBeNull();

    // 3. Assert that travel-mode attribute is not set
    const travelModeAttr = gmpRoute3d!.getAttribute('travel-mode');
    expect(travelModeAttr).toBeNull();

    // Cleanup
    document.body.removeChild(element);
  });

  it('does not propagate travelMode if it is an empty string', async () => {
    // 1. Render the component with travelMode set to empty string
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {
      props: {
        center: {lat: 0, lng: 0},
        travelMode: '',
        routes: [{
          origin: {lat: 1, lng: 1, label: 'Origin'},
          destination: {lat: 2, lng: 2, label: 'Destination'},
        }]
      }
    };
    internals.prevCenter = {lat: 0, lng: 0};
    document.body.appendChild(element);

    // Wait for lit to finish initial render
    await element.updateComplete;

    // 2. Query the rendered route
    const gmpRoute3d = element.renderRoot.querySelector('gmp-route-3d');
    expect(gmpRoute3d).not.toBeNull();

    // 3. Assert that travel-mode attribute is not set
    const travelModeAttr = gmpRoute3d!.getAttribute('travel-mode');
    expect(travelModeAttr).toBeNull();

    // Cleanup
    document.body.removeChild(element);
  });

  it('falls back to generic pin color when icon/iconColor is not provided',
     () => {
       const markerEl = new PlacePinMarker({label: 'Sample'}).getElement();
       const template =
           markerEl.querySelector('template') as HTMLTemplateElement;
       expect(template).not.toBeNull();
       const iconDiv =
           (template.content?.querySelector('.custom-marker-content-icon') ||
            template.querySelector('.custom-marker-content-icon')) as
           HTMLElement;
       expect(iconDiv).not.toBeNull();
       expect(iconDiv.style.getPropertyValue('--maui-place-pin-color'))
           .toBe('#78909C');
       expect(iconDiv.style.getPropertyValue('--maui-place-pin-color-dark'))
           .toBe('#8DA6B2');
     });

  it('uses lookup color when icon matches a known POI category', () => {
    const markerEl = new PlacePinMarker({
                       label: 'Shop',
                       placePrimaryType: 'retail'
                     }).getElement();
    const template = markerEl.querySelector('template') as HTMLTemplateElement;
    expect(template).not.toBeNull();
    const iconDiv =
        (template.content?.querySelector('.custom-marker-content-icon') ||
         template.querySelector('.custom-marker-content-icon')) as HTMLElement;
    expect(iconDiv).not.toBeNull();
    expect(iconDiv.style.getPropertyValue('--maui-place-pin-color'))
        .toBe('#0597FF');
    expect(iconDiv.style.getPropertyValue('--maui-place-pin-color-dark'))
        .toBe('#68AFF0');
  });

  it('correctly parses and renders SVG icon content without sanitization error',
     () => {
       const markerEl = new PlacePinMarker({
                          label: 'Shop',
                          placePrimaryType: 'retail',
                        }).getElement();
       const template =
           markerEl.querySelector('template') as HTMLTemplateElement;
       expect(template).not.toBeNull();
       const iconDiv =
           (template.content?.querySelector('.custom-marker-content-icon') ||
            template.querySelector('.custom-marker-content-icon')) as
           HTMLElement;
       expect(iconDiv).not.toBeNull();
       const svg = iconDiv.querySelector('svg');
       expect(svg).not.toBeNull();
     });

  it('assigns higher z-index to southern markers than northern markers', () => {
    const northMarker =
        new PlacePinMarker({
          position: {lat: 47.6062, lng: -122.3321},  // Seattle (North)
          label: 'North',
        }).getElement();
    const southMarker =
        new PlacePinMarker({
          position: {lat: 34.0522, lng: -118.2437},  // Los Angeles (South)
          label: 'South',
        }).getElement();
    const northZ = Number(
        (northMarker as any).zIndex ?? northMarker.getAttribute('z-index') ??
        0);
    const southZ = Number(
        (southMarker as any).zIndex ?? southMarker.getAttribute('z-index') ??
        0);
    expect(southZ).toBeGreaterThan(northZ);
  });

  it('sorts markers from North to South in resolveMarkers', () => {
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    (element as any)._controller = {
      props: {
        markers: [
          {lat: 34.0522, lng: -118.2437, label: 'LA (South)'},
          {lat: 47.6062, lng: -122.3321, label: 'Seattle (North)'},
          {lat: 37.7749, lng: -122.4194, label: 'SF (Middle)'},
        ],
      },
    };
    const resolved = (element as any).resolveMarkers();
    expect(resolved.map((m: any) => m.label)).toEqual([
      'Seattle (North)',
      'SF (Middle)',
      'LA (South)',
    ]);
  });

  it('validates anchorMarker with only lat and lng (no label) in GoogleMapApi.schema',
     () => {
       const validPayload = {
         center: {lat: 6.4485, lng: 3.449},
         zoom: 16,
         mode: 'satellite',
         anchorMarker: {lat: 6.4485, lng: 3.449},
       };
       const result = GoogleMapApi.schema.safeParse(validPayload);
       expect(result.success).toBeTrue();
     });

  it('validates anchorMarker with DataBinding path in GoogleMapApi.schema',
     () => {
       const validPayload = {
         center: {lat: 6.4485, lng: 3.449},
         zoom: 16,
         anchorMarker: {path: '/data/anchor'},
       };
       const result = GoogleMapApi.schema.safeParse(validPayload);
       expect(result.success).toBeTrue();
     });

  it('requires label for markers (MapPinSchema) in GoogleMapApi.schema', () => {
    const invalidPayload = {
      center: {lat: 6.4485, lng: 3.449},
      zoom: 16,
      markers: [{lat: 6.4485, lng: 3.449}],
    };
    const result = GoogleMapApi.schema.safeParse(invalidPayload);
    expect(result.success).toBeFalse();
  });

  it('renders AnchorMarker element when anchorMarker has only lat/lng and no label',
     async () => {
       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as {
         _controller: {props: Record<string, unknown>};
         prevCenter: {lat: number; lng: number};
         updateMarkers: () => Promise<void>;
       };
       internals._controller = {
         props: {
           center: {lat: 6.4485, lng: 3.449},
           zoom: 16,
           anchorMarker: {lat: 6.4485, lng: 3.449},
         },
       };
       internals.prevCenter = {lat: 6.4485, lng: 3.449};
       document.body.appendChild(element);

       await element.updateComplete;
       await internals.updateMarkers();

       const gmpMarker =
           element.map3dElement.querySelector('gmp-marker') as unknown as {
         position?: {lat: number; lng: number};
       }
       |null;
       expect(gmpMarker).not.toBeNull();
       expect(gmpMarker?.position).toEqual({lat: 6.4485, lng: 3.449});

       document.body.removeChild(element);
     });
});
