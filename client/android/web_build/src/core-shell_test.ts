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

import {type LitElement} from 'lit';

import {A2UICoreShell, type A2UIMessage} from './core-shell';

class TestA2UICoreShell extends A2UICoreShell {
  readonly resizedHeights: number[] = [];
  jsReadyCalls = 0;

  protected override readonly platformAttributionIds = [
    'test_platform_attribution_id',
  ];

  protected override notifyWebpageResized(height: number): void {
    this.resizedHeights.push(height);
  }

  protected override notifyJsReady(): void {
    this.jsReadyCalls++;
  }

  getRenderer() {
    return this.rendererRef;
  }

  getGlobalDataModel(): Record<string, unknown> {
    return this.globalDataModelRef;
  }
}

if (!customElements.get('test-a2ui-core-shell')) {
  customElements.define('test-a2ui-core-shell', TestA2UICoreShell);
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

describe('A2UICoreShell', () => {
  let container: HTMLElement;
  let originalResizeObserver: typeof ResizeObserver;
  let originalAdoptedStyleSheets: CSSStyleSheet[];
  let originalGoogle: unknown;

  beforeAll(() => {
    if (!customElements.get('gmp-map-3d')) {
      customElements.define('gmp-map-3d', class extends HTMLElement {});
    }
  });

  beforeEach(() => {
    FakeResizeObserver.instances = [];
    originalResizeObserver = window.ResizeObserver;
    window.ResizeObserver =
        FakeResizeObserver as unknown as typeof ResizeObserver;
    originalAdoptedStyleSheets = [...document.adoptedStyleSheets];

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

    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    container.remove();
    window.ResizeObserver = originalResizeObserver;
    document.adoptedStyleSheets = originalAdoptedStyleSheets;
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;
  });

  async function mountShell(): Promise<TestA2UICoreShell> {
    const shell =
        document.createElement('test-a2ui-core-shell') as TestA2UICoreShell;
    container.appendChild(shell);
    await shell.updateComplete;
    return shell;
  }

  describe('lifecycle and rendering', () => {
    it('notifies native host that JS is ready and renders loading state on connect',
       async () => {
         const shell = await mountShell();

         const loadingEl = shell.shadowRoot!.querySelector('.loading');
         expect(shell.jsReadyCalls).toBe(1);
         expect(loadingEl?.textContent).toBe('Waiting for payload...');
       });

    it('adopts theme and horizontal scroll stylesheets onto document without duplicates',
       async () => {
         document.adoptedStyleSheets = [];

         await mountShell();
         const countAfterFirstMount = document.adoptedStyleSheets.length;
         await mountShell();

         expect(countAfterFirstMount).toBe(2);
         expect(document.adoptedStyleSheets.length).toBe(2);
       });

    it('debounces resize notifications by 100ms and reports chat container scrollHeight',
       async () => {
         jasmine.clock().install();
         try {
           const shell = await mountShell();
           const chatMessages =
               shell.shadowRoot!.querySelector('.chat-messages')!;
           Object.defineProperty(chatMessages, 'scrollHeight', {
             value: 420,
             configurable: true,
           });
           const observer = FakeResizeObserver.instances[0];

           observer.trigger();
           jasmine.clock().tick(50);
           observer.trigger();
           jasmine.clock().tick(50);
           expect(shell.resizedHeights).toEqual([]);

           jasmine.clock().tick(50);
           expect(shell.resizedHeights).toEqual([420]);
         } finally {
           jasmine.clock().uninstall();
         }
       });

    it('disconnects ResizeObserver and clears pending debounce timer on disconnect',
       async () => {
         jasmine.clock().install();
         try {
           const shell = await mountShell();
           const observer = FakeResizeObserver.instances[0];

           observer.trigger();
           shell.remove();
           jasmine.clock().tick(200);

           expect(observer.observedElements.size).toBe(0);
           expect(shell.resizedHeights).toEqual([]);
         } finally {
           jasmine.clock().uninstall();
         }
       });
  });

  describe('processA2uiMessages', () => {
    it('ignores payloads without UI instruction keys', async () => {
      const shell = await mountShell();
      const processSpy =
          spyOn(shell.getRenderer(), 'processResponse').and.callThrough();

      shell.processA2uiMessages([{text: 'Pure conversational reply'}]);
      await shell.updateComplete;

      expect(processSpy).not.toHaveBeenCalled();
      expect(shell.shadowRoot!.querySelector('.loading')).not.toBeNull();
      expect(shell.shadowRoot!.querySelector('a2ui-surface')).toBeNull();
    });

    it('logs an error and preserves state when given malformed JSON',
       async () => {
         const shell = await mountShell();
         const consoleErrorSpy = spyOn(console, 'error');
         const processSpy =
             spyOn(shell.getRenderer(), 'processResponse').and.callThrough();

         shell.processA2uiMessages('{not-valid-json');
         await shell.updateComplete;

         expect(consoleErrorSpy)
             .toHaveBeenCalledWith(
                 'Failed to process A2UI JSON:', jasmine.any(SyntaxError));
         expect(processSpy).not.toHaveBeenCalled();
         expect(shell.shadowRoot!.querySelector('.loading')).not.toBeNull();
       });

    it('parses double-encoded JSON strings and single message objects into a rendered surface',
       async () => {
         const shell = await mountShell();
         const doubleEncoded = JSON.stringify(JSON.stringify({
           createSurface: {
             surfaceId: 'surf-double',
             catalogId: 'a2ui://maps-agentic-ui-catalog.json',
           },
           version: 'v0.9',
         }));

         shell.processA2uiMessages(doubleEncoded);
         await shell.updateComplete;

         expect(shell.shadowRoot!.querySelector('.loading')).toBeNull();
         const surfaceEl =
             shell.shadowRoot!.querySelector<LitElement>('a2ui-surface');
         expect(surfaceEl).not.toBeNull();
         expect(surfaceEl!.shadowRoot!.adoptedStyleSheets.length)
             .toBeGreaterThan(0);
       });

    it('recursively normalizes latitude, longitude, and title keys onto a rendered GoogleMap while preserving existing labels',
       async () => {
         const shell = await mountShell();
         const payload: A2UIMessage[] = [
           {
             createSurface: {
               surfaceId: 'surf-norm',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateDataModel: {
               surfaceId: 'surf-norm',
               value: {
                 place: {
                   title: 'Ignored Title',
                   label: 'Preserved Label',
                 },
               },
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'surf-norm',
               components: [
                 {
                   id: 'root',
                   component: 'GoogleMap',
                   zoom: 12,
                   center: {latitude: 37.7749, longitude: -122.4194} as
                       unknown as {
                         lat: number;
                         lng: number;
                       },
                   markers: [
                     {
                       latitude: 37.78,
                       longitude: -122.41,
                       title: 'Ferry Building',
                     },
                     {
                       latitude: 37.8,
                       longitude: -122.42,
                       label: 'Preserved Label',
                     },
                   ],
                 },
               ],
             },
             version: 'v0.9',
           },
         ];

         shell.processA2uiMessages(payload);
         await shell.updateComplete;
         const surfaceEl =
             shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
         await surfaceEl.updateComplete;
         const mapEl =
             surfaceEl.shadowRoot!.querySelector<LitElement>('a2ui-googlemap')!;
         expect(mapEl).not.toBeNull();
         await mapEl.updateComplete;
         await flushMicrotasks();

         expect(shell.getGlobalDataModel()).toEqual({
           place: {
             title: 'Ignored Title',
             label: 'Preserved Label',
           },
         });

         const gmpMap3d = mapEl.renderRoot.querySelector('gmp-map-3d')!;
         expect(gmpMap3d.getAttribute('center')).toBe('37.7749,-122.4194,0');

         const renderedMarkers = Array.from(
             gmpMap3d.querySelectorAll<HTMLElement&{label?: string}>(
                 'gmp-marker'),
         );
         expect(renderedMarkers.map((m) => m.label)).toEqual([
           'Preserved Label',
           'Ferry Building',
         ]);
       });

    it('passes platform attribution IDs to rendered MAUI components without a window global',
       async () => {
         const shell = await mountShell();

         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'surf-attribution',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'surf-attribution',
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
         const mapEl =
             surfaceEl.shadowRoot!.querySelector<LitElement>('a2ui-googlemap')!;
         await mapEl.updateComplete;

         const gmpMap3d = mapEl.renderRoot.querySelector('gmp-map-3d')!;
         expect(gmpMap3d.getAttribute('internal-usage-attribution-ids'))
             .toBe('gmp_web_maui_v0.1.10_atoui,test_platform_attribution_id');
         expect((window as unknown as
                 Record<string, unknown>)['A2UI_ATTRIBUTION_ID'])
             .toBeUndefined();
       });

    it('accumulates globalDataModel across chunks, resolves GoogleMap center paths, and preserves unresolved paths',
       async () => {
         const shell = await mountShell();

         // Chunk 1: Data model arrives first using both .data and .value
         // payload keys across messages.
         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'surf-paris',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateDataModel: {
               surfaceId: 'surf-paris',
               data: {city: 'Paris'},
             } as unknown as A2UIMessage['updateDataModel'],
             version: 'v0.9',
           },
           {
             updateDataModel: {
               surfaceId: 'surf-paris',
               value: {
                 trip: {
                   mapCenter: {latitude: 48.8566, longitude: 2.3522},
                 },
               },
             },
             version: 'v0.9',
           },
         ]);

         // Chunk 2: Components arrive in a subsequent SSE chunk referencing
         // a resolved path (/trip/mapCenter), an unresolved path
         // (/trip/laterCenter), a relative path without a leading slash
         // (trip/mapCenter), and an inline GoogleMap child inside a container.
         shell.processA2uiMessages([
           {
             updateComponents: {
               surfaceId: 'surf-paris',
               components: [
                 {
                   id: 'root',
                   component: 'Column',
                   children: ['map-resolved', 'map-later'],
                 },
                 {
                   id: 'map-resolved',
                   component: 'GoogleMap',
                   zoom: 12,
                   center: {path: '/trip/mapCenter'},
                 },
                 {
                   id: 'map-later',
                   component: 'GoogleMap',
                   zoom: 12,
                   center: {path: '/trip/laterCenter'},
                 },
                 {
                   id: 'map-relative-path',
                   component: 'GoogleMap',
                   zoom: 12,
                   center: {path: 'trip/mapCenter'},
                 },
                 {
                   id: 'inline-map-container',
                   component: 'CustomContainer',
                   children: [
                     {
                       id: 'nested-inline-map',
                       component: 'GoogleMap',
                       zoom: 12,
                       center: {path: '/trip/mapCenter'},
                     },
                   ],
                 },
               ],
             },
             version: 'v0.9',
           },
         ]);

         // Verify synchronously that globalDataModel accumulated both chunks,
         // the resolved path (both top-level and nested inline child) was
         // replaced by {lat, lng}, and both the unresolved path
         // (/trip/laterCenter) and non-slash path (trip/mapCenter) were
         // preserved on the component model.
         expect(shell.getGlobalDataModel()).toEqual({
           city: 'Paris',
           trip: {
             mapCenter: {lat: 48.8566, lng: 2.3522},
           },
         });
         const surfaceModel = shell.getRenderer().getSurface('surf-paris')!;
         expect(
             surfaceModel.componentsModel.get('map-resolved')
                 ?.properties['center'],
             )
             .toEqual({lat: 48.8566, lng: 2.3522});
         expect(
             surfaceModel.componentsModel.get('map-later')
                 ?.properties['center'],
             )
             .toEqual({path: '/trip/laterCenter'});
         expect(
             surfaceModel.componentsModel.get('map-relative-path')
                 ?.properties['center'],
             )
             .toEqual({path: 'trip/mapCenter'});
         const inlineContainerChildren =
             surfaceModel.componentsModel.get('inline-map-container')
                 ?.properties['children'] as Array<{center?: unknown}>;
         expect(inlineContainerChildren[0].center).toEqual({
           lat: 48.8566,
           lng: 2.3522,
         });

         // Chunk 3: Supply /trip/laterCenter in the data model before Lit
         // renders the DOM so both GoogleMap components render valid centers.
         shell.processA2uiMessages([
           {
             updateDataModel: {
               surfaceId: 'surf-paris',
               path: '/trip/laterCenter',
               value: {lat: 51.5074, lng: -0.1278},
             } as unknown as A2UIMessage['updateDataModel'],
             version: 'v0.9',
           },
         ]);

         await shell.updateComplete;
         const surfaceEl =
             shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
         await surfaceEl.updateComplete;
         const columnEl = surfaceEl.shadowRoot!.querySelector<LitElement>(
             'a2ui-basic-column',
             )!;
         expect(columnEl).not.toBeNull();
         await columnEl.updateComplete;
         const mapEls = Array.from(
             columnEl.querySelectorAll<LitElement>('a2ui-googlemap'),
         );
         expect(mapEls.length).toBe(2);
         await Promise.all(mapEls.map((el) => el.updateComplete));
         await flushMicrotasks();

         const resolvedGmpMap =
             mapEls[0].renderRoot.querySelector('gmp-map-3d')!;
         expect(resolvedGmpMap.getAttribute('center')).toBe('48.8566,2.3522,0');
         const laterGmpMap = mapEls[1].renderRoot.querySelector('gmp-map-3d')!;
         expect(laterGmpMap.getAttribute('center')).toBe('51.5074,-0.1278,0');
       });

    it('synthesizes a root Column containing only unreferenced top-level components when root is missing',
       async () => {
         const shell = await mountShell();

         shell.processA2uiMessages([
           {
             createSurface: {
               surfaceId: 'surf-auto-root',
               catalogId: 'a2ui://maps-agentic-ui-catalog.json',
             },
             version: 'v0.9',
           },
           {
             updateComponents: {
               surfaceId: 'surf-auto-root',
               components: [
                 {
                   id: 'card-wrapper',
                   component: 'Card',
                   child: 'nested-text',
                 },
                 {
                   id: 'nested-text',
                   component: 'Text',
                   text: 'Inside card',
                 },
                 {
                   id: 'list-wrapper',
                   component: 'List',
                   children: {
                     componentId: 'template-item',
                     path: '/items',
                   } as unknown as {componentId: string},
                 },
                 {
                   id: 'template-item',
                   component: 'Text',
                   text: 'Template row',
                 },
                 {
                   id: 'row-wrapper',
                   component: 'Row',
                   children: ['row-child-id'],
                 },
                 {
                   id: 'row-child-id',
                   component: 'Text',
                   text: 'Row child',
                 },
                 {
                   id: 'custom-group',
                   component: 'CustomGroup',
                   children: [
                     {
                       id: 'inline-group-child',
                       component: 'Text',
                       text: 'Inline child',
                     },
                   ],
                 },
                 {
                   id: 'inline-group-child',
                   component: 'Text',
                   text: 'Claimed by inline object reference',
                 },
                 {
                   id: 'standalone-map',
                   component: 'GoogleMap',
                   zoom: 10,
                   center: {lat: 37.77, lng: -122.41},
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

         const rootComponentModel = shell.getRenderer()
                                        .getSurface('surf-auto-root')
                                        ?.componentsModel.get('root');
         expect(rootComponentModel?.type).toBe('Column');
         expect(rootComponentModel?.properties).toEqual({
           children: [
             'card-wrapper',
             'list-wrapper',
             'row-wrapper',
             'custom-group',
             'standalone-map',
           ],
         });
         expect(surfaceEl.shadowRoot!.querySelector('a2ui-basic-column'))
             .not.toBeNull();
       });

    it('auto-injects a v0.9 createSurface command for an unknown surfaceId and does not duplicate it on later chunks',
       async () => {
         const shell = await mountShell();

         shell.processA2uiMessages([
           {
             updateComponents: {
               surfaceId: 'isolated-surface',
               components: [
                 {
                   id: 'root',
                   component: 'Column',
                   children: [],
                 },
               ],
             },
             version: 'v0.9',
           },
         ]);
         await shell.updateComplete;
         const surfaceEl =
             shell.shadowRoot!.querySelector<LitElement>('a2ui-surface')!;
         expect(surfaceEl).not.toBeNull();
         await surfaceEl.updateComplete;
         expect(surfaceEl.shadowRoot!.querySelector('a2ui-basic-column'))
             .not.toBeNull();

         // Subsequent chunk for the same surfaceId must update the existing
         // surface rather than injecting a second createSurface command.
         shell.processA2uiMessages([
           {
             updateDataModel: {
               surfaceId: 'isolated-surface',
               value: {status: 'updated'},
             },
             version: 'v0.9',
           },
         ]);
         await shell.updateComplete;

         expect(shell.shadowRoot!.querySelectorAll('a2ui-surface').length)
             .toBe(1);
         expect(shell.getRenderer().getSurface('isolated-surface_1'))
             .toBeUndefined();

         // Also verify createSurface auto-injection when the first message for
         // a new surfaceId is a raw (non-array) updateDataModel object.
         shell.processA2uiMessages({
           updateDataModel: {
             surfaceId: 'data-first-surface',
             value: {ready: true},
           },
           version: 'v0.9',
         });
         await shell.updateComplete;

         expect(shell.getRenderer().getSurface('data-first-surface'))
             .toBeDefined();
         expect(shell.shadowRoot!.querySelectorAll('a2ui-surface').length)
             .toBe(2);
       });
  });
});
