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
import {IOSA2UIShell} from './main';

interface GoogleMapElement extends LitElement {
  readonly map3dElement: HTMLElement;
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

describe('IOSA2UIShell', () => {
  let container: HTMLElement;
  let originalWebkit: typeof window.webkit;
  let originalResizeObserver: typeof ResizeObserver;
  let originalGoogle: unknown;
  let googleMapCtor: CustomElementConstructor;
  let placeCardCtor: CustomElementConstructor;
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
    originalWebkit = window.webkit;

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
      updated: (changedProperties: PropertyValues) => void;
    };
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
    window.webkit = originalWebkit;
    window.ResizeObserver = originalResizeObserver;
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;

    const mapProto = googleMapCtor.prototype as {
      updated: (changedProperties: PropertyValues) => void;
    };
    mapProto.updated = originalGoogleMapUpdated;

    const cardProto = placeCardCtor.prototype as {
      firstUpdated: (changedProperties: PropertyValues) => void;
    };
    cardProto.firstUpdated = originalPlaceCardFirstUpdated;
  });

  async function mountShell(): Promise<IOSA2UIShell> {
    const shell = document.createElement('a2ui-shell') as IOSA2UIShell;
    container.appendChild(shell);
    await shell.updateComplete;
    await flushMicrotasks();
    return shell;
  }

  describe('attribution and native WKWebView bridge', () => {
    it('registers the shell without setting a window attribution global',
       () => {
         expect((window as unknown as
                 Record<string, unknown>)['A2UI_ATTRIBUTION_ID'])
             .toBeUndefined();
         expect(customElements.get('a2ui-shell')).toBe(IOSA2UIShell);
       });

    it('sends combined web and iOS attribution IDs from rendered maps',
       async () => {
         const shell = await mountShell();

         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'ios-attribution-surface',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'ios-attribution-surface',
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
             .toBe('gmp_web_maui_v0.1.11_atoui,gmp_ios_maui_v0.1.11_atoui');
       });

    it('posts onJsReady action to window.webkit.messageHandlers.iOS on connect',
       async () => {
         const postMessage = jasmine.createSpy('postMessage');
         window.webkit = {
           messageHandlers: {
             iOS: {postMessage},
           },
         };

         await mountShell();

         expect(postMessage).toHaveBeenCalledOnceWith({
           action: 'onJsReady',
           data: '',
         });
       });

    it('connects cleanly without throwing when window.webkit is undefined',
       async () => {
         window.webkit = undefined;

         const shell = await mountShell();

         expect(shell.shadowRoot!.querySelector('.chat-messages'))
             .not.toBeNull();
       });

    it('posts debounced chat container scrollHeight to window.webkit.messageHandlers.heightObserver',
       async () => {
         jasmine.clock().install();
         try {
           const postHeightMessage = jasmine.createSpy('postHeightMessage');
           window.webkit = {
             messageHandlers: {
               heightObserver: {postMessage: postHeightMessage},
             },
           };
           const shell = await mountShell();
           const chatMessages =
               shell.shadowRoot!.querySelector('.chat-messages')!;
           Object.defineProperty(chatMessages, 'scrollHeight', {
             value: 640,
             configurable: true,
           });

           FakeResizeObserver.instances[0].trigger();
           jasmine.clock().tick(100);

           expect(postHeightMessage).toHaveBeenCalledOnceWith(640);
         } finally {
           jasmine.clock().uninstall();
         }
       });
  });

  describe('GoogleMap iOS readiness patch on real <a2ui-googlemap> elements', () => {
    it('defers GoogleMap.updated until gmp-map-3d is defined before rendering markers',
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

         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'ios-map-surface',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'ios-map-surface',
               components: [
                 {
                   id: 'root',
                   component: 'GoogleMap',
                   zoom: 12,
                   center: {lat: 37.7749, lng: -122.4194},
                   markers: [
                     {lat: 37.7749, lng: -122.4194, label: 'Golden Gate'},
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
         const mapEl = surfaceEl.shadowRoot!.querySelector<GoogleMapElement>(
             'a2ui-googlemap')!;
         expect(mapEl).not.toBeNull();
         await mapEl.updateComplete;
         await flushMicrotasks();

         // While gmp-map-3d definition is still pending, GoogleMap.updated is
         // held back so no <gmp-marker> child is appended yet.
         expect(mapEl.map3dElement.querySelector('gmp-marker')).toBeNull();

         resolveMap3dDefined(customElements.get('gmp-map-3d')!);
         await flushMicrotasks();

         const renderedMarker =
             mapEl.map3dElement.querySelector<HTMLElement&{label?: string}>(
                 'gmp-marker');
         expect(renderedMarker).not.toBeNull();
         expect(renderedMarker?.label).toBe('Golden Gate');
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
                   surfaceId: 'ios-place-surface',
                   catalogId: 'a2ui://maps-agentic-ui-catalog.json',
                 },
                 version: 'v0.9',
               },
               {
                 updateComponents: {
                   surfaceId: 'ios-place-surface',
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
