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

import {type LitElement, type PropertyValues} from 'lit';

import type {} from './globals';
import {AndroidA2UIShell} from './main';

interface GoogleMapElement extends LitElement {
  readonly map3dElement: HTMLElement;
  prevCenter: {lat: number; lng: number}|null;
  getCenter(): {lat: number; lng: number};
}

class FakeResizeObserver implements ResizeObserver {
  static instances: FakeResizeObserver[] = [];
  readonly observedElements = new Set<Element>();

  constructor(private readonly callback: ResizeObserverCallback) {
    FakeResizeObserver.instances.push(this);
  }

  observe(target: Element): void {
    this.observedElements.add(target);
  }

  unobserve(target: Element): void {
    this.observedElements.delete(target);
  }

  disconnect(): void {
    this.observedElements.clear();
  }

  trigger(): void {
    if (this.observedElements.size > 0) {
      this.callback([], this);
    }
  }
}

// Captured before any test installs `jasmine.clock()`, which replaces the
// global `setTimeout` with a fake that only fires on `jasmine.clock().tick()`.
const nativeSetTimeout = window.setTimeout.bind(window);

/**
 * Waits one macrotask so all pending microtasks settle first, including Lit
 * re-renders and the `customElements.whenDefined()` chains used by the shell
 * patches.
 */
async function flushMicrotasks(): Promise<void> {
  await new Promise<void>((resolve) => {
    nativeSetTimeout(resolve, 0);
  });
}

describe('AndroidA2UIShell', () => {
  let container: HTMLElement;
  let originalAndroidBridge: typeof window.Android;
  let originalResizeObserver: typeof ResizeObserver;
  let originalGoogle: unknown;
  let googleMapCtor: CustomElementConstructor;
  let placeCardCtor: CustomElementConstructor;
  let originalGoogleMapGetCenter: () => {
    lat: number;
    lng: number
  };
  let originalGoogleMapUpdated: (changedProperties: PropertyValues) => void;
  let originalPlaceCardFirstUpdated: (
      changedProperties: PropertyValues,
      ) => void;

  beforeAll(async () => {
    if (!customElements.get('gmp-map-3d')) {
      customElements.define('gmp-map-3d', class extends HTMLElement {});
    }
    await customElements.whenDefined('a2ui-googlemap');
    await customElements.whenDefined('a2ui-placedetailscompact');
    googleMapCtor = customElements.get('a2ui-googlemap')!;
    placeCardCtor = customElements.get('a2ui-placedetailscompact')!;
  });

  beforeEach(() => {
    FakeResizeObserver.instances = [];
    originalResizeObserver = window.ResizeObserver;
    window.ResizeObserver =
        FakeResizeObserver as unknown as typeof ResizeObserver;
    originalAndroidBridge = window.Android;

    const windowWithGlobals = window as unknown as Record<string, unknown>;
    originalGoogle = windowWithGlobals['google'];
    windowWithGlobals['google'] = {
      maps: {
        importLibrary: () => Promise.resolve({}),
        CollisionBehavior: {
          OPTIONAL_AND_HIDES_LOWER_PRIORITY:
              'OPTIONAL_AND_HIDES_LOWER_PRIORITY',
        },
        maps3d: {AltitudeMode: {RELATIVE_TO_GROUND: 1}},
      },
    };

    const mapProto = googleMapCtor.prototype as {
      getCenter: () => {
        lat: number;
        lng: number
      };
      updated: (changedProperties: PropertyValues) => void;
    };
    originalGoogleMapGetCenter = mapProto.getCenter;
    originalGoogleMapUpdated = mapProto.updated;

    const cardProto = placeCardCtor.prototype as {
      firstUpdated: (changedProperties: PropertyValues) => void;
    };
    originalPlaceCardFirstUpdated = cardProto.firstUpdated;

    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    container.remove();
    window.Android = originalAndroidBridge;
    window.ResizeObserver = originalResizeObserver;
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;

    const mapProto = googleMapCtor.prototype as {
      getCenter: () => {
        lat: number;
        lng: number
      };
      updated: (changedProperties: PropertyValues) => void;
    };
    mapProto.getCenter = originalGoogleMapGetCenter;
    mapProto.updated = originalGoogleMapUpdated;

    const cardProto = placeCardCtor.prototype as {
      firstUpdated: (changedProperties: PropertyValues) => void;
    };
    cardProto.firstUpdated = originalPlaceCardFirstUpdated;
  });

  async function mountShell(): Promise<AndroidA2UIShell> {
    const shell = document.createElement('a2ui-shell') as AndroidA2UIShell;
    container.appendChild(shell);
    await shell.updateComplete;
    await flushMicrotasks();
    return shell;
  }

  describe('attribution and native Android bridge', () => {
    it('registers the shell without setting a window attribution global',
       () => {
         expect((window as unknown as
                 Record<string, unknown>)['A2UI_ATTRIBUTION_ID'])
             .toBeUndefined();
         expect(customElements.get('a2ui-shell')).toBe(AndroidA2UIShell);
       });

    it('sends combined web and Android attribution IDs from rendered maps',
       async () => {
         const shell = await mountShell();

         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'android-attribution-surface',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'android-attribution-surface',
               components: [{
                 id: 'root',
                 component: 'GoogleMap',
                 center: {lat: 37.7749, lng: -122.4194},
               }],
             },
             version: 'v0.9',
           },
         ]);
         await shell.updateComplete;
         const surfaceEl =
             shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
         await surfaceEl.updateComplete;
         const mapEl = surfaceEl.shadowRoot!.querySelector<GoogleMapElement>(
             'a2ui-googlemap')!;
         await mapEl.updateComplete;

         expect(
             mapEl.map3dElement.getAttribute('internal-usage-attribution-ids'))
             .toBe('gmp_web_maui_v0.1.11_atoui,gmp_android_maui_v0.1.11_atoui');
       });

    it('invokes window.Android.onJsReady when connected to the DOM',
       async () => {
         const onJsReady = jasmine.createSpy('onJsReady');
         window.Android = {onJsReady};

         await mountShell();

         expect(onJsReady).toHaveBeenCalledOnceWith();
       });

    it('connects cleanly without throwing when window.Android is undefined',
       async () => {
         window.Android = undefined;

         const shell = await mountShell();

         expect(shell.shadowRoot!.querySelector('.chat-messages'))
             .not.toBeNull();
       });

    it('forwards debounced chat container scrollHeight to window.Android.onWebpageResized',
       async () => {
         jasmine.clock().install();
         try {
           const onWebpageResized = jasmine.createSpy('onWebpageResized');
           window.Android = {onWebpageResized};
           const shell = await mountShell();
           const chatMessages =
               shell.shadowRoot!.querySelector('.chat-messages')!;
           Object.defineProperty(chatMessages, 'scrollHeight', {
             value: 512,
             configurable: true,
           });

           FakeResizeObserver.instances[0].trigger();
           jasmine.clock().tick(100);

           expect(onWebpageResized).toHaveBeenCalledOnceWith(512);
         } finally {
           jasmine.clock().uninstall();
         }
       });
  });

  describe(
      'GoogleMap Android streaming patches on real <a2ui-googlemap> elements',
      () => {
        it('guards getCenter when center data chunk has not arrived yet and coerces string coordinates',
           async () => {
             const shell = await mountShell();

             // 1. Uninitialized <a2ui-googlemap> element before controller
             // binds.
             const uninitializedMap =
                 document.createElement('a2ui-googlemap') as GoogleMapElement;
             expect(uninitializedMap.getCenter()).toEqual({lat: 0, lng: 0});

             // 2. Streaming chunk 1: updateComponents arrives with a data-model
             // path before updateDataModel arrives, so controller.props.center
             // is undefined.
             shell.processA2uiMessages([
               {
                 createSurface: {
                   surfaceId: 'map-surface',
                   catalogId: 'a2ui://maps-agentic-ui-catalog.json',
                 },
                 version: 'v0.9',
               },
               {
                 updateComponents: {
                   surfaceId: 'map-surface',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 12,
                       center: {path: '/pending/center'},
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await shell.updateComplete;
             const surfaceEl =
                 shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
             await surfaceEl.updateComplete;
             const mapEl =
                 surfaceEl.shadowRoot!.querySelector<GoogleMapElement>(
                     'a2ui-googlemap')!;
             expect(mapEl).not.toBeNull();
             await mapEl.updateComplete;

             expect(mapEl.getCenter()).toEqual({lat: 0, lng: 0});
             expect(mapEl.map3dElement.getAttribute('center')).toBe('0,0,0');

             // 3. Direct data-model update (bypassing A2UICoreShell.fixKeys)
             // with string-typed latitude/longitude keys so
             // GoogleMap.prototype.getCenter directly exercises the
             // center.latitude / center.longitude and Number(...) coercion
             // branches, followed by non-numeric values to verify the || 0
             // NaN fallback.
             const surface =
                 (surfaceEl as unknown as {
                   surface: {
                     dataModel: {set: (path: string, val: unknown) => void;};
                   };
                 }).surface;
             surface.dataModel.set('/pending/center', {
               latitude: '37.7749',
               longitude: '-122.4194',
             });
             await mapEl.updateComplete;
             await flushMicrotasks();

             expect(mapEl.getCenter()).toEqual({lat: 37.7749, lng: -122.4194});
             expect(mapEl.map3dElement.getAttribute('center'))
                 .toBe('37.7749,-122.4194,0');

             surface.dataModel.set('/pending/center', {
               lat: 'not-a-number',
               lng: 'not-a-number',
             });
             expect(mapEl.getCenter()).toEqual({lat: 0, lng: 0});
           });

        it('defers updated() until gmp-map-3d is defined, deduplicates unchanged markers and routes across chunks, and resets (0, 0) prevCenter',
           async () => {
             let resolveMap3dDefined!: (ctor: CustomElementConstructor) => void;
             const map3dDefinedPromise = new Promise<CustomElementConstructor>(
                 (resolve) => {
                   resolveMap3dDefined = resolve;
                 },
             );
             const origWhenDefined =
                 customElements.whenDefined.bind(customElements);
             spyOn(customElements, 'whenDefined')
                 .and.callFake((tagName: string) => {
                   if (tagName === 'gmp-map-3d') {
                     return map3dDefinedPromise;
                   }
                   return origWhenDefined(tagName);
                 });

             const shell = await mountShell();

             // Step 1: Render a real GoogleMap while gmp-map-3d is still
             // pending.
             shell.processA2uiMessages([
               {
                 createSurface: {
                   surfaceId: 'stream-map',
                   catalogId: 'a2ui://maps-agentic-ui-catalog.json',
                 },
                 version: 'v0.9',
               },
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 0, lng: 0},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await shell.updateComplete;
             const surfaceEl =
                 shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
             await surfaceEl.updateComplete;
             const mapEl =
                 surfaceEl.shadowRoot!.querySelector<GoogleMapElement>(
                     'a2ui-googlemap')!;
             await mapEl.updateComplete;
             await flushMicrotasks();

             // Before gmp-map-3d resolves, GoogleMap.prototype.updated is
             // deferred so no <gmp-marker> child has been appended yet.
             expect(mapEl.map3dElement.querySelector('gmp-marker')).toBeNull();

             // Resolve gmp-map-3d definition and verify the marker renders.
             resolveMap3dDefined(customElements.get('gmp-map-3d')!);
             await flushMicrotasks();

             const initialMarkerNode =
                 mapEl.map3dElement.querySelector('gmp-marker');
             expect(initialMarkerNode).not.toBeNull();

             // Step 2: While center is still (0, 0) and __gmpReadyFired is
             // already true, verify that a non-null prevCenter is reset to null
             // on update.
             mapEl.prevCenter = {lat: 10, lng: 20};
             mapEl.requestUpdate();
             await mapEl.updateComplete;
             await flushMicrotasks();

             expect(mapEl.prevCenter).toBeNull();

             // Step 3: Send a second streaming chunk with a newly allocated
             // markers array containing identical JSON and real center
             // coordinates. Verify the existing <gmp-marker> DOM node is
             // preserved (not recreated).
             shell.processA2uiMessages([
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 37.77, lng: -122.41},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await mapEl.updateComplete;
             await flushMicrotasks();

             expect(mapEl.map3dElement.querySelectorAll('gmp-marker').length)
                 .toBe(1);
             expect(mapEl.map3dElement.querySelector('gmp-marker'))
                 .toBe(initialMarkerNode);

             // Step 4: Send a chunk introducing routes (so ensureRoutesLoaded
             // finishes loading the routes library), followed by a chunk that
             // updates the route destination while keeping markers JSON
             // identical. Verify __lastRoutesJson invalidation runs
             // updateMarkers() and renders <gmp-route-3d>.
             shell.processA2uiMessages([
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 37.77, lng: -122.41},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                       ],
                       routes: [
                         {
                           origin: {lat: 37.77, lng: -122.41, label: 'Start'},
                           destination: {
                             lat: 37.78,
                             lng: -122.42,
                             label: 'End',
                           },
                         },
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await mapEl.updateComplete;
             await flushMicrotasks();
             await mapEl.updateComplete;
             await flushMicrotasks();

             shell.processA2uiMessages([
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 37.77, lng: -122.41},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                       ],
                       routes: [
                         {
                           origin: {lat: 37.77, lng: -122.41, label: 'Start'},
                           destination: {
                             lat: 37.79,
                             lng: -122.43,
                             label: 'Updated End',
                           },
                         },
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await mapEl.updateComplete;
             await flushMicrotasks();

             const markerAfterRouteUpdate =
                 mapEl.map3dElement.querySelector('gmp-marker');
             expect(markerAfterRouteUpdate).not.toBeNull();
             expect(
                 mapEl.map3dElement.querySelector('gmp-route-3d')
                     ?.getAttribute('destination'),
                 )
                 .toBe('37.79,-122.43');

             // Step 5: Send a chunk with newly allocated markers AND routes
             // arrays containing identical JSON. Verify both prevMarkers and
             // prevRoutes are synchronized so markerAfterRouteUpdate is
             // preserved in the DOM without re-creation.
             shell.processA2uiMessages([
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 37.77, lng: -122.41},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                       ],
                       routes: [
                         {
                           origin: {lat: 37.77, lng: -122.41, label: 'Start'},
                           destination: {
                             lat: 37.79,
                             lng: -122.43,
                             label: 'Updated End',
                           },
                         },
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await mapEl.updateComplete;
             await flushMicrotasks();

             expect(mapEl.map3dElement.querySelector('gmp-marker'))
                 .toBe(markerAfterRouteUpdate);

             // Step 6: Send a chunk with a modified markers array while routes
             // stay identical, and verify updateMarkers() replaces the markers.
             shell.processA2uiMessages([
               {
                 updateComponents: {
                   surfaceId: 'stream-map',
                   components: [
                     {
                       id: 'root',
                       component: 'GoogleMap',
                       zoom: 13,
                       center: {lat: 37.77, lng: -122.41},
                       markers: [
                         {lat: 37.77, lng: -122.41, label: 'Coffee Shop'},
                         {lat: 37.78, lng: -122.42, label: 'Bakery'},
                       ],
                       routes: [
                         {
                           origin: {lat: 37.77, lng: -122.41, label: 'Start'},
                           destination: {
                             lat: 37.79,
                             lng: -122.43,
                             label: 'Updated End',
                           },
                         },
                       ],
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await mapEl.updateComplete;
             await flushMicrotasks();

             expect(mapEl.map3dElement.querySelectorAll('gmp-marker').length)
                 .toBe(2);
             expect(markerAfterRouteUpdate!.isConnected).toBeFalse();
           });
      });

  describe(
      'PlaceDetailsCompact narrow-screen scaling patch on real <a2ui-placedetailscompact> elements',
      () => {
        it('scales rendered compact place card down when narrower than 350px and clears styles when wider',
           async () => {
             const shell = await mountShell();

             shell.processA2uiMessages([
               {
                 createSurface: {
                   surfaceId: 'place-surface',
                   catalogId: 'a2ui://maps-agentic-ui-catalog.json',
                 },
                 version: 'v0.9',
               },
               {
                 updateComponents: {
                   surfaceId: 'place-surface',
                   components: [
                     {
                       id: 'root',
                       component: 'PlaceDetailsCompact',
                       placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4',
                     },
                   ],
                 },
                 version: 'v0.9',
               },
             ]);
             await shell.updateComplete;
             const surfaceEl =
                 shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
             await surfaceEl.updateComplete;
             const cardEl = surfaceEl.shadowRoot!.querySelector<LitElement>(
                 'a2ui-placedetailscompact',
                 )!;
             expect(cardEl).not.toBeNull();
             await cardEl.updateComplete;

             const compactEl = cardEl.renderRoot.querySelector<HTMLElement>(
                 'gmp-place-details-compact',
                 )!;
             expect(compactEl).not.toBeNull();

             const cardResizeObserver = FakeResizeObserver.instances.find(
                 (obs) => obs.observedElements.has(cardEl),
                 )!;
             expect(cardResizeObserver).toBeDefined();

             Object.defineProperty(cardEl, 'clientWidth', {
               value: 280,
               writable: true,
               configurable: true,
             });
             Object.defineProperty(compactEl, 'offsetHeight', {
               value: 200,
               configurable: true,
             });

             cardResizeObserver.trigger();

             expect(compactEl.style.getPropertyValue('width')).toBe('350px');
             expect(compactEl.style.getPropertyPriority('width'))
                 .toBe('important');
             expect(compactEl.style.getPropertyValue('min-width'))
                 .toBe('350px');
             expect(compactEl.style.getPropertyValue('transform-origin'))
                 .toBe('left top');
             expect(compactEl.style.getPropertyValue('transform'))
                 .toBe('scale(0.8)');
             expect(compactEl.style.getPropertyValue('margin-bottom'))
                 .toBe('-40px');

             // Widen container to >= 350px and verify inline scaling styles are
             // removed.
             Object.defineProperty(cardEl, 'clientWidth', {
               value: 400,
               writable: true,
               configurable: true,
             });
             cardResizeObserver.trigger();

             expect(compactEl.style.getPropertyValue('width')).toBe('');
             expect(compactEl.style.getPropertyValue('min-width')).toBe('');
             expect(compactEl.style.getPropertyValue('transform')).toBe('');
             expect(compactEl.style.getPropertyValue('margin-bottom')).toBe('');
           });
      });
});
