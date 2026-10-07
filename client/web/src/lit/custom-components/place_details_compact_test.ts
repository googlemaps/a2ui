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

import './place_details_compact';

import {type PlaceDetailsCompact, PlaceDetailsCompactApi, type PlaceDetailsCompactProps} from './place_details_compact';

describe('PlaceDetailsCompact Component', () => {
  it('uses a fallback attribution ID when the global one is missing',
     async () => {
       // 1. Explicitly remove any global attribution ID
       delete (window as any).A2UI_ATTRIBUTION_ID;

       // 2. Render the component with a place ID
       const element = document.createElement('a2ui-placedetailscompact') as
           PlaceDetailsCompact;
       (element as any)._controller = {
         props: {placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4'}
       };
       document.body.appendChild(element);

       // Wait for lit to finish initial render
       await element.updateComplete;

       // 3. Query the rendered place details using renderRoot
       const detailsCompact =
           element.renderRoot.querySelector('gmp-place-details-compact');

       // 4. Assert that the attribute has the correct fallback ID
       const attrId =
           detailsCompact!.getAttribute('internal-usage-attribution-ids');
       expect(attrId).toBe('gmp_web_maui_v0.1.8_atoui');

       // Cleanup
       document.body.removeChild(element);
     });

  it('declares every schema key in the Closure props interface', () => {
    // Fails to compile if a schema key is added/removed without updating the
    // `declare` interface, which would let Closure rename it again.
    const keysMatch: SameKeys<
        typeof PlaceDetailsCompactApi.schema.shape, PlaceDetailsCompactProps> =
        true;
    expect(keysMatch).toBeTrue();
  });

  describe('orientation', () => {
    let container: HTMLElement;

    beforeEach(() => {
      container = document.createElement('div');
      document.body.appendChild(container);
    });

    afterEach(() => {
      container.remove();
    });

    function createCard(props: Partial<PlaceDetailsCompactProps>):
        PlaceDetailsCompact {
      const element = document.createElement('a2ui-placedetailscompact') as
          PlaceDetailsCompact;
      (element as unknown as {
        _controller: {props: Partial<PlaceDetailsCompactProps>};
      })._controller = {
        props: {placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4', ...props},
      };
      container.appendChild(element);
      return element;
    }

    async function renderedOrientation(element: PlaceDetailsCompact):
        Promise<string|null> {
      await element.updateComplete;
      return element.renderRoot.querySelector('gmp-place-details-compact')!
          .getAttribute('orientation');
    }

    it('renders horizontal for a single card with no orientation', async () => {
      const card = createCard({});

      expect(await renderedOrientation(card)).toBe('HORIZONTAL');
    });

    it('renders horizontal for multiple sibling cards', async () => {
      const first = createCard({});
      const second = createCard({});

      expect(await renderedOrientation(first)).toBe('HORIZONTAL');
      expect(await renderedOrientation(second)).toBe('HORIZONTAL');
    });

    it('respects an explicit vertical orientation', async () => {
      const card = createCard({orientation: 'vertical'});

      expect(await renderedOrientation(card)).toBe('VERTICAL');
    });

    it('renders horizontal for an explicit horizontal orientation',
       async () => {
         const card = createCard({orientation: 'horizontal'});

         expect(await renderedOrientation(card)).toBe('HORIZONTAL');
       });
  });

  it('lazyloads places library via google.maps.importLibrary on connect',
     async () => {
       const windowWithGlobals = window as unknown as Record<string, unknown>;
       const originalGoogle = windowWithGlobals['google'];
       try {
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.resolveTo({});
         windowWithGlobals['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };

         const element = document.createElement('a2ui-placedetailscompact') as
             PlaceDetailsCompact;
         (element as unknown as {
           _controller: {props: Partial<PlaceDetailsCompactProps>};
         })._controller = {
           props: {placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4'},
         };
         expect(importLibrarySpy).not.toHaveBeenCalled();
         document.body.appendChild(element);

         await element.updateComplete;
         await Promise.resolve();

         expect(importLibrarySpy).toHaveBeenCalledOnceWith('places');
         document.body.removeChild(element);
       } finally {
         windowWithGlobals['google'] = originalGoogle;
       }
     });
});

/** `true` only if A and B have exactly the same keys. */
type SameKeys<A, B> =
    [Exclude<keyof A, keyof B>| Exclude<keyof B, keyof A>] extends [never] ?
    true :
    false;
