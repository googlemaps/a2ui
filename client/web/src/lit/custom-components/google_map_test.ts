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
import type {GoogleMap} from './google_map';

interface GoogleMapInternals {
  controller: {
    props: {
      center: { lat: number; lng: number };
      markers?: unknown[];
      travelMode?: string | null;
      routes?: Array<{
        origin: { lat: number; lng: number; label: string };
        destination: { lat: number; lng: number; label: string };
      }>;
    };
  };
  prevCenter: { lat: number; lng: number } | null;
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
        maps3d: { AltitudeMode: { RELATIVE_TO_GROUND: 1 } }
      }
    };
  });

  afterEach(() => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    windowWithGlobals['google'] = originalGoogle;
    windowWithGlobals['A2UI_ATTRIBUTION_ID'] = originalAttributionId;
  });

  it('uses a fallback attribution ID when the global one is missing', async () => {
    // 1. Explicitly remove any global attribution ID
    delete (window as unknown as Record<string, unknown>)['A2UI_ATTRIBUTION_ID'];

    // 2. Render the component with empty props so it falls back to defaults
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals.controller = { props: { markers: [], center: { lat: 0, lng: 0 } } };
    internals.prevCenter = { lat: 0, lng: 0 };
    document.body.appendChild(element);

    // Wait for lit to finish initial render
    await element.updateComplete;

    // 3. Query the rendered map using renderRoot (since shadowRoot is closed)
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
    internals.controller = {
      props: {
        center: { lat: 0, lng: 0 },
        travelMode: 'driving',
        routes: [
          {
            origin: { lat: 1, lng: 1, label: 'Origin' },
            destination: { lat: 2, lng: 2, label: 'Destination' },
          }
        ]
      }
    };
    internals.prevCenter = { lat: 0, lng: 0 };
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

  it('does not propagate travelMode if it is not provided', async () => {
    // 1. Render the component without travelMode but with routes
    const element = document.createElement('a2ui-googlemap') as GoogleMap;
    const internals = element as unknown as GoogleMapInternals;
    internals.controller = {
      props: {
        center: { lat: 0, lng: 0 },
        routes: [
          {
            origin: { lat: 1, lng: 1, label: 'Origin' },
            destination: { lat: 2, lng: 2, label: 'Destination' },
          }
        ]
      }
    };
    internals.prevCenter = { lat: 0, lng: 0 };
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
    internals.controller = {
      props: {
        center: { lat: 0, lng: 0 },
        travelMode: null,
        routes: [
          {
            origin: { lat: 1, lng: 1, label: 'Origin' },
            destination: { lat: 2, lng: 2, label: 'Destination' },
          }
        ]
      }
    };
    internals.prevCenter = { lat: 0, lng: 0 };
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
    internals.controller = {
      props: {
        center: { lat: 0, lng: 0 },
        travelMode: '',
        routes: [
          {
            origin: { lat: 1, lng: 1, label: 'Origin' },
            destination: { lat: 2, lng: 2, label: 'Destination' },
          }
        ]
      }
    };
    internals.prevCenter = { lat: 0, lng: 0 };
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
});
