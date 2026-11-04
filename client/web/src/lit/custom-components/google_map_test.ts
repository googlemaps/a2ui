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
import '../a2ui_renderer';

import {flushEventLoop} from '../testing/event_loop';

import {type GoogleMap, GoogleMapApi, type GoogleMapProps, type MapPinProps} from './google_map';
import {calculateLatitudeZIndex, PlacePinMarker, type PlacePinMarkerElement} from './place_pin_marker';

interface GoogleMapInternals {
  _controller: {
    props: {
      center?: {lat: number; lng: number};
      markers?: unknown[];
      anchorMarker?: {lat?: number; lng?: number; label?: string};
      travelMode?: string | null;
      routes?: Array<{
        origin: {lat: number; lng: number; label: string};
        destination: {lat: number; lng: number; label: string};
      }>;
    };
  };
  prevCenter: {lat: number; lng: number}|null;
  prevMarkers: unknown;
  prevRoutes: unknown;
  ensureRoutesLoaded: () => Promise<google.maps.RoutesLibrary|null>;
  updateMarkers: () => Promise<void>;
}

/**
 * Renders an `a2ui-googlemap` with `props` and waits until its markers are
 * appended. The caller removes the element.
 */
async function renderMapWithProps(
    props: GoogleMapInternals['_controller']['props']): Promise<GoogleMap> {
  const element = document.createElement('a2ui-googlemap') as GoogleMap;
  const internals = element as unknown as GoogleMapInternals;
  internals._controller = {
    props: {center: {lat: 47.61, lng: -122.34}, ...props}
  };
  internals.prevCenter = {lat: 47.61, lng: -122.34};
  document.body.appendChild(element);
  // Routes render `gmp-map-3d` only after the (mocked) routes library
  // resolves, so flush once more before updating markers.
  await element.updateComplete;
  await flushEventLoop();
  await element.updateComplete;
  await internals.updateMarkers();
  return element;
}

/** The map's `gmp-marker`s in DOM order: later entries draw in front. */
function readRenderedMarkers(element: GoogleMap) {
  return Array.from(
      element.map3dElement.querySelectorAll('gmp-marker'), (el) => {
        const marker = el as PlacePinMarkerElement;
        return {
          // Place pins render a `template.custom-marker`; the anchor does not.
          isAnchor: marker.querySelector('template.custom-marker') === null,
          lat: marker.position?.lat,
          zIndex: Number(marker.zIndex),
        };
      });
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

  describe('attribution IDs', () => {
    async function renderMap(
        configure: (element: GoogleMap) => void = () => {},
        parent: HTMLElement = document.body): Promise<GoogleMap> {
      const element = document.createElement('a2ui-googlemap') as GoogleMap;
      const internals = element as unknown as GoogleMapInternals;
      internals._controller = {
        props: {
          markers: [],
          center: {lat: 0, lng: 0},
          routes: [{
            origin: {lat: 1, lng: 1, label: 'Origin'},
            destination: {lat: 2, lng: 2, label: 'Destination'},
          }],
        },
      };
      internals.prevCenter = {lat: 0, lng: 0};
      configure(element);
      parent.appendChild(element);
      // Wait for the initial render and the routes library load.
      await element.updateComplete;
      await flushEventLoop();
      await element.updateComplete;
      return element;
    }

    function renderedIds(element: GoogleMap, selector: string): string|null {
      return element.renderRoot.querySelector(selector)!.getAttribute(
          'internal-usage-attribution-ids');
    }

    beforeEach(() => {
      delete (
          window as unknown as Record<string, unknown>)['A2UI_ATTRIBUTION_ID'];
    });

    it('sends only the MAUI web ID by default', async () => {
      const element = await renderMap();

      expect(renderedIds(element, 'gmp-map-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui');
      expect(renderedIds(element, 'gmp-route-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui');
      element.remove();
    });

    it('appends additionalAttributionIds set as a property', async () => {
      const element = await renderMap((map) => {
        map.additionalAttributionIds = ['host_id'];
      });

      expect(renderedIds(element, 'gmp-map-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui,host_id');
      expect(renderedIds(element, 'gmp-route-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui,host_id');
      element.remove();
    });

    it('appends additional-attribution-ids set as an attribute', async () => {
      const element = await renderMap((map) => {
        map.setAttribute('additional-attribution-ids', 'a, b');
      });

      expect(renderedIds(element, 'gmp-map-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui,a,b');
      element.remove();
    });

    it('merges IDs from <maui-providers> before per-element IDs', async () => {
      const providers =
          document.createElement('maui-providers') as HTMLElement &
          {additionalAttributionIds: readonly string[]};
      providers.additionalAttributionIds = ['context_id'];
      document.body.appendChild(providers);

      const element = await renderMap((map) => {
        map.additionalAttributionIds = ['element_id', 'context_id'];
      }, providers);

      expect(renderedIds(element, 'gmp-map-3d'))
          .toBe('gmp_web_maui_v0.1.10_atoui,context_id,element_id');
      providers.remove();
    });

    it('merges the deprecated window global instead of replacing the MAUI ID',
       async () => {
         (window as unknown as Record<string, unknown>)['A2UI_ATTRIBUTION_ID'] =
             'legacy_id';

         const element = await renderMap();

         expect(renderedIds(element, 'gmp-map-3d'))
             .toBe('gmp_web_maui_v0.1.10_atoui,legacy_id');
         element.remove();
       });
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

    // Wait for lit to finish initial render and route library load
    await element.updateComplete;
    await flushEventLoop();
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

  it('automatically follows the host page CSS color-scheme and updates on toggle',
     async () => {
       const prevDocColorScheme = document.documentElement.style.colorScheme;
       const prevBodyColorScheme = document.body.style.colorScheme;
       try {
         document.documentElement.style.colorScheme = 'dark';
         const element = document.createElement('a2ui-googlemap') as GoogleMap;
         const internals = element as unknown as GoogleMapInternals;
         internals._controller = {
           props: {markers: [], center: {lat: 0, lng: 0}},
         };
         internals.prevCenter = {lat: 0, lng: 0};
         document.body.appendChild(element);
         await element.updateComplete;

         const gmpMap3d = element.renderRoot.querySelector('gmp-map-3d')!;
         expect(gmpMap3d.getAttribute('color-scheme')).toBe('DARK');
         expect(getComputedStyle(gmpMap3d).colorScheme).toBe('dark');

         // Toggle page theme to light on document.body (like MAUI ThemeToggle)
         document.documentElement.style.colorScheme = 'light';
         document.body.style.colorScheme = 'light';
         // Wait a microtask for MutationObserver + Lit update
         await flushEventLoop();
         await element.updateComplete;

         expect(gmpMap3d.getAttribute('color-scheme')).toBe('LIGHT');
         expect(getComputedStyle(gmpMap3d).colorScheme).toBe('light');

         // Reset to dual 'light dark' — attribute should be removed
         document.documentElement.style.colorScheme = 'light dark';
         document.body.style.colorScheme = 'light dark';
         await flushEventLoop();
         await element.updateComplete;

         expect(gmpMap3d.getAttribute('color-scheme')).toBeNull();

         document.body.removeChild(element);
       } finally {
         document.documentElement.style.colorScheme = prevDocColorScheme;
         document.body.style.colorScheme = prevBodyColorScheme;
       }
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

    // Wait for lit to finish initial render and route library load
    await element.updateComplete;
    await flushEventLoop();
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

    // Wait for lit to finish initial render and route library load
    await element.updateComplete;
    await flushEventLoop();
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

    // Wait for lit to finish initial render and route library load
    await element.updateComplete;
    await flushEventLoop();
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

  it('validates payload without center and zoom in GoogleMapApi.schema', () => {
    const validPayload = {
      markers: [{lat: 6.4485, lng: 3.449, label: 'Sample'}],
    };
    const result = GoogleMapApi.schema.safeParse(validPayload);
    expect(result.success).toBeTrue();
  });

  it('falls back to (0, 0) center when center prop is omitted', async () => {
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {props: {markers: []}};
    document.body.appendChild(element);

    await element.updateComplete;

    expect(element.getCenter()).toEqual({lat: 0, lng: 0});
    const gmpMap3d = element.renderRoot.querySelector('gmp-map-3d');
    expect(gmpMap3d?.getAttribute('center')).toBe('0,0,0');

    document.body.removeChild(element);
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

  it('draws the anchor in front of pins north of it and behind pins south of it',
     async () => {
       const element = await renderMapWithProps({
         markers: [
           {lat: 47.62, lng: -122.34, label: 'North'},
           {lat: 47.60, lng: -122.34, label: 'South'},
         ],
         anchorMarker: {lat: 47.61, lng: -122.34, label: 'Anchor'},
       });

       const rendered = readRenderedMarkers(element);
       expect(rendered.map((m) => m.isAnchor)).toEqual([false, true, false]);
       expect(rendered.map((m) => m.lat)).toEqual([47.62, 47.61, 47.60]);
       expect(rendered[1].zIndex).toBe(calculateLatitudeZIndex(47.61));
       expect(rendered[0].zIndex).toBeLessThan(rendered[1].zIndex);
       expect(rendered[1].zIndex).toBeLessThan(rendered[2].zIndex);

       document.body.removeChild(element);
     });

  it('draws the anchor behind every pin when it is the northernmost marker',
     async () => {
       const element = await renderMapWithProps({
         markers: [
           {lat: 47.60, lng: -122.34, label: 'Pin A'},
           {lat: 47.59, lng: -122.34, label: 'Pin B'},
         ],
         anchorMarker: {lat: 47.65, lng: -122.34},
       });

       const rendered = readRenderedMarkers(element);
       expect(rendered.map((m) => m.isAnchor)).toEqual([true, false, false]);
       expect(rendered.map((m) => m.lat)).toEqual([47.65, 47.60, 47.59]);
       expect(rendered[0].zIndex).toBe(calculateLatitudeZIndex(47.65));
       expect(rendered[0].zIndex).toBeLessThan(rendered[1].zIndex);

       document.body.removeChild(element);
     });

  it('draws the anchor behind a pin at the same latitude', async () => {
    const element = await renderMapWithProps({
      markers: [{lat: 47.61, lng: -122.34, label: 'Pin'}],
      anchorMarker: {lat: 47.61, lng: -122.30, label: 'Anchor'},
    });

    const rendered = readRenderedMarkers(element);
    expect(rendered.map((m) => m.isAnchor)).toEqual([true, false]);
    expect(rendered.map((m) => m.zIndex)).toEqual([
      calculateLatitudeZIndex(47.61),
      calculateLatitudeZIndex(47.61),
    ]);

    document.body.removeChild(element);
  });

  it('draws the anchor in front of every pin when it is the southernmost marker',
     async () => {
       const element = await renderMapWithProps({
         markers: [
           {lat: 47.62, lng: -122.34, label: 'Pin A'},
           {lat: 47.61, lng: -122.34, label: 'Pin B'},
         ],
         anchorMarker: {lat: 47.55, lng: -122.34, label: 'Anchor'},
       });

       const rendered = readRenderedMarkers(element);
       expect(rendered.map((m) => m.isAnchor)).toEqual([false, false, true]);
       expect(rendered.map((m) => m.lat)).toEqual([47.62, 47.61, 47.55]);
       expect(rendered[2].zIndex).toBe(calculateLatitudeZIndex(47.55));
       expect(rendered[1].zIndex).toBeLessThan(rendered[2].zIndex);

       document.body.removeChild(element);
     });

  it('does not render the anchor marker when routes are present', async () => {
    const element = await renderMapWithProps({
      markers: [{lat: 47.61, lng: -122.34, label: 'Pin'}],
      anchorMarker: {lat: 47.60, lng: -122.34, label: 'Anchor'},
      routes: [{
        origin: {lat: 1, lng: 1, label: 'Origin'},
        destination: {lat: 2, lng: 2, label: 'Destination'},
      }],
    });

    expect(element.map3dElement).not.toBeNull();
    expect(readRenderedMarkers(element).map((m) => m.isAnchor)).toEqual([
      false,
    ]);

    document.body.removeChild(element);
  });

  it('declares every schema key in the Closure props interfaces', () => {
    // Fails to compile if a schema key is added/removed without updating the
    // `declare` interface, which would let Closure rename it again.
    const pinShape = GoogleMapApi.schema.shape.markers.unwrap().element.shape;
    const mapKeysMatch:
        SameKeys<typeof GoogleMapApi.schema.shape, GoogleMapProps> = true;
    const pinKeysMatch: SameKeys<typeof pinShape, MapPinProps> = true;
    expect(mapKeysMatch && pinKeysMatch).toBeTrue();
  });

  it('lazyloads maps3d on connect and does not load routes when routes are empty',
     async () => {
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({});
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {
           importLibrary: importLibrarySpy,
           maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}},
         },
       };

       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as GoogleMapInternals;
       const markers: unknown[] = [];
       internals._controller = {props: {markers, center: {lat: 0, lng: 0}}};
       // Nothing changed since the last render, so only connecting can trigger
       // the maps3d load.
       internals.prevCenter = {lat: 0, lng: 0};
       internals.prevMarkers = markers;
       internals.prevRoutes = undefined;
       expect(importLibrarySpy).not.toHaveBeenCalled();
       document.body.appendChild(element);

       await element.updateComplete;
       await flushEventLoop();

       expect(importLibrarySpy).toHaveBeenCalledOnceWith('maps3d');

       document.body.removeChild(element);
     });

  it('lazyloads maps3d before routes and waits for both before rendering gmp-map-3d when routes are provided',
     async () => {
       const callOrder: string[] = [];
       let resolveMaps3d!: (val: unknown) => void;
       const maps3dPromise = new Promise((resolve) => {
         resolveMaps3d = resolve;
       });
       let resolveRoutes!: (val: unknown) => void;
       const routesPromise = new Promise((resolve) => {
         resolveRoutes = resolve;
       });

       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.callFake((lib: string) => {
             callOrder.push(lib);
             if (lib === 'maps3d') {
               return maps3dPromise;
             }
             if (lib === 'routes') {
               return routesPromise;
             }
             return Promise.resolve({});
           });

       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {
           importLibrary: importLibrarySpy,
           maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}},
         },
       };

       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as GoogleMapInternals;
       internals._controller = {
         props: {
           center: {lat: 0, lng: 0},
           routes: [{
             origin: {lat: 1, lng: 1, label: 'Origin'},
             destination: {lat: 2, lng: 2, label: 'Destination'},
           }],
         },
       };
       internals.prevCenter = {lat: 0, lng: 0};
       document.body.appendChild(element);

       await element.updateComplete;
       // Before maps3d resolves, routes must not be requested yet, and
       // gmp-map-3d must not be rendered yet.
       expect(callOrder).toEqual(['maps3d']);
       expect(element.renderRoot.querySelector('gmp-map-3d')).toBeNull();

       resolveMaps3d({});
       await flushEventLoop();
       await element.updateComplete;

       // While routes is still loading, gmp-map-3d must remain unrendered so it
       // does not initialize its camera before gmp-route-3d upgrades.
       expect(callOrder).toEqual(['maps3d', 'routes']);
       expect(element.renderRoot.querySelector('gmp-map-3d')).toBeNull();

       const fakeRoutesLib = {Route: class {}} as unknown as
           google.maps.RoutesLibrary;
       resolveRoutes(fakeRoutesLib);
       await flushEventLoop();
       await element.updateComplete;

       expect(await internals.ensureRoutesLoaded()).toBe(fakeRoutesLib);
       expect(element.renderRoot.querySelector('gmp-map-3d')).not.toBeNull();
       expect(element.renderRoot.querySelector('gmp-route-3d')).not.toBeNull();

       document.body.removeChild(element);
     });

  it('does not render gmp-map-3d and logs an error when loading the routes library fails',
     async () => {
       const routesError = new Error('routes network error');
       const consoleErrorSpy = spyOn(console, 'error');
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.callFake((lib: string) => {
             if (lib === 'routes') {
               return Promise.reject(routesError);
             }
             return Promise.resolve({});
           });
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {
           importLibrary: importLibrarySpy,
           maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}},
         },
       };

       const element = document.createElement('a2ui-googlemap') as GoogleMap;
       const internals = element as unknown as GoogleMapInternals;
       internals._controller = {
         props: {
           center: {lat: 0, lng: 0},
           routes: [{
             origin: {lat: 1, lng: 1, label: 'Origin'},
             destination: {lat: 2, lng: 2, label: 'Destination'},
           }],
         },
       };
       internals.prevCenter = {lat: 0, lng: 0};
       document.body.appendChild(element);

       await element.updateComplete;
       const routesLibPromise = internals.ensureRoutesLoaded();
       await flushEventLoop();
       await element.updateComplete;

       expect(await routesLibPromise).toBeNull();
       expect(consoleErrorSpy)
           .toHaveBeenCalledWith(
               'Failed to load Google Maps Routes library:', routesError);
       expect(element.renderRoot.querySelector('gmp-map-3d')).toBeNull();

       document.body.removeChild(element);
     });

  it('updates markers when only the markers change', async () => {
    (window as unknown as Record<string, unknown>)['google'] = {
      maps: {
        importLibrary: jasmine.createSpy('importLibrary').and.resolveTo({}),
        maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}},
      },
    };

    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals._controller = {props: {markers: [], center: {lat: 0, lng: 0}}};
    internals.prevCenter = {lat: 0, lng: 0};
    document.body.appendChild(element);
    await element.updateComplete;
    await flushEventLoop();

    const updateMarkersSpy =
        spyOn(
            element as unknown as {updateMarkers: () => Promise<void>},
            'updateMarkers')
            .and.callThrough();
    // New markers array; routes are unchanged (still undefined).
    internals._controller.props.markers = [];
    element.requestUpdate();
    await element.updateComplete;

    expect(updateMarkersSpy).toHaveBeenCalledTimes(1);

    document.body.removeChild(element);
  });
});

/** `true` only if A and B have exactly the same keys. */
type SameKeys<A, B> =
    [Exclude<keyof A, keyof B>| Exclude<keyof B, keyof A>] extends [never] ?
    true :
    false;
