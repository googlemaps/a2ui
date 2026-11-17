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
import '../a2ui_renderer';

import {type PlaceDetailsCompact, PlaceDetailsCompactApi, type PlaceDetailsCompactProps} from './place_details_compact';

describe('PlaceDetailsCompact Component', () => {
  describe('attribution IDs', () => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    let originalLegacyId: unknown;

    beforeEach(() => {
      originalLegacyId = windowWithGlobals['A2UI_ATTRIBUTION_ID'];
      delete windowWithGlobals['A2UI_ATTRIBUTION_ID'];
    });

    afterEach(() => {
      windowWithGlobals['A2UI_ATTRIBUTION_ID'] = originalLegacyId;
    });

    async function renderedIds(
        configure: (element: PlaceDetailsCompact) => void = () => {},
        parent: HTMLElement = document.body): Promise<string|null> {
      const element = document.createElement('a2ui-placedetailscompact') as
          PlaceDetailsCompact;
      (element as unknown as {
        _controller: {props: Partial<PlaceDetailsCompactProps>};
      })._controller = {props: {placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4'}};
      configure(element);
      parent.appendChild(element);
      await element.updateComplete;
      const ids = element.renderRoot.querySelector('gmp-place-details-compact')!
                      .getAttribute('internal-usage-attribution-ids');
      element.remove();
      return ids;
    }

    it('sends only the MAUI web ID by default', async () => {
      expect(await renderedIds()).toBe('gmp_web_maui_v0.1.11_atoui');
    });

    it('appends additionalAttributionIds set as a property', async () => {
      expect(await renderedIds((card) => {
        card.additionalAttributionIds = ['host_id'];
      })).toBe('gmp_web_maui_v0.1.11_atoui,host_id');
    });

    it('appends additional-attribution-ids set as an attribute', async () => {
      expect(await renderedIds((card) => {
        card.setAttribute('additional-attribution-ids', 'a,b');
      })).toBe('gmp_web_maui_v0.1.11_atoui,a,b');
    });

    it('merges IDs from <maui-providers> before per-element IDs', async () => {
      const providers =
          document.createElement('maui-providers') as HTMLElement &
          {additionalAttributionIds: readonly string[]};
      providers.setAttribute('additional-attribution-ids', 'context_id');
      document.body.appendChild(providers);

      expect(await renderedIds((card) => {
        card.additionalAttributionIds = ['element_id'];
      }, providers)).toBe('gmp_web_maui_v0.1.11_atoui,context_id,element_id');
      providers.remove();
    });

    it('re-renders when <maui-providers> IDs change', async () => {
      const providers =
          document.createElement('maui-providers') as HTMLElement &
          {additionalAttributionIds: readonly string[]};
      document.body.appendChild(providers);
      const card = document.createElement('a2ui-placedetailscompact') as
          PlaceDetailsCompact;
      (card as unknown as {
        _controller: {props: Partial<PlaceDetailsCompactProps>};
      })._controller = {props: {placeId: 'ChIJN1t_tDeuEmsRUsoyG83frY4'}};
      providers.appendChild(card);
      await card.updateComplete;

      providers.additionalAttributionIds = ['late_id'];
      await card.updateComplete;

      expect(card.renderRoot.querySelector('gmp-place-details-compact')!
                 .getAttribute('internal-usage-attribution-ids'))
          .toBe('gmp_web_maui_v0.1.11_atoui,late_id');
      providers.remove();
    });

    it('merges the deprecated window global instead of replacing the MAUI ID',
       async () => {
         windowWithGlobals['A2UI_ATTRIBUTION_ID'] = 'legacy_id';

         expect(await renderedIds())
             .toBe('gmp_web_maui_v0.1.11_atoui,legacy_id');
       });
  });

  it('declares every schema key in the Closure props interface', () => {
    // Fails to compile if a schema key is added/removed without updating the
    // `declare` interface, which would let Closure rename it again.
    const keysMatch: SameKeys<
        typeof PlaceDetailsCompactApi.schema.shape, PlaceDetailsCompactProps> =
        true;
    expect(keysMatch).toBeTrue();
  });

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

  describe('orientation', () => {
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

  describe('container styling', () => {
    it('uses default container border, border-radius, and box-shadow when custom properties are unset',
       async () => {
         const card = createCard({});
         await card.updateComplete;
         const detailsCompact =
             card.renderRoot.querySelector('gmp-place-details-compact')!;

         const computed = getComputedStyle(detailsCompact);

         expect(computed.borderTopStyle).toBe('solid');
         expect(computed.borderTopWidth).toBe('1px');
         expect(computed.borderRadius).toBe('16px');
         expect(computed.boxShadow).toBe('none');
       });

    it('applies custom container border, border-radius, and box-shadow properties',
       async () => {
         const card = createCard({});
         card.style.setProperty('--gmp-card-border', 'none');
         card.style.setProperty('--gmp-card-border-radius', '20px');
         card.style.setProperty(
             '--gmp-card-box-shadow', '0px 0px 20px rgba(0, 0, 0, 0.04)');
         await card.updateComplete;
         const detailsCompact =
             card.renderRoot.querySelector('gmp-place-details-compact')!;

         const computed = getComputedStyle(detailsCompact);

         expect(computed.borderTopStyle).toBe('none');
         expect(computed.borderRadius).toBe('20px');
         expect(computed.boxShadow)
             .toBe('rgba(0, 0, 0, 0.04) 0px 0px 20px 0px');
       });
  });
});

/** `true` only if A and B have exactly the same keys. */
type SameKeys<A, B> =
    [Exclude<keyof A, keyof B>| Exclude<keyof B, keyof A>] extends [never] ?
    true :
    false;
