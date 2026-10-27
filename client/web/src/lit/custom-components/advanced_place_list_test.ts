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

import './advanced_place_list';
import '../a2ui_renderer';

import {type AdvancedPlaceList, AdvancedPlaceListApi, type AdvancedPlaceListProps,} from './advanced_place_list';

describe('AdvancedPlaceList Component', () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    container.remove();
  });

  function createList(
      props: Partial<AdvancedPlaceListProps>,
      ): AdvancedPlaceList {
    const element = document.createElement(
                        'a2ui-advancedplacelist',
                        ) as AdvancedPlaceList;
    (element as unknown as {
      _controller: {props: Partial<AdvancedPlaceListProps>};
    })._controller = {
      props: {
        places: ['ChIJN1t_tDeuEmsRUsoyG83frY4', 'ChIJP3Sa8ziYEmsRUKgyFmh9AQM'],
        ...props,
      },
    };
    container.appendChild(element);
    return element;
  }

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
        configure: (element: AdvancedPlaceList) => void = () => {},
        parent: HTMLElement = document.body,
        ): Promise<string|null> {
      const element = document.createElement(
                          'a2ui-advancedplacelist',
                          ) as AdvancedPlaceList;
      (element as unknown as {
        _controller: {props: Partial<AdvancedPlaceListProps>};
      })._controller = {
        props: {
          places: ['ChIJN1t_tDeuEmsRUsoyG83frY4'],
        },
      };
      configure(element);
      parent.appendChild(element);
      await element.updateComplete;
      const ids = element.renderRoot.querySelector('gmp-advanced-place-list')!
                      .getAttribute('internal-usage-attribution-ids');
      element.remove();
      return ids;
    }

    it('sends only the MAUI web ID by default', async () => {
      expect(await renderedIds()).toBe('gmp_web_maui_v0.1.11_atoui');
    });

    it('appends additionalAttributionIds set as a property', async () => {
      expect(
          await renderedIds((list) => {
            list.additionalAttributionIds = ['host_id'];
          }),
          )
          .toBe('gmp_web_maui_v0.1.11_atoui,host_id');
    });

    it('appends additional-attribution-ids set as an attribute', async () => {
      expect(
          await renderedIds((list) => {
            list.setAttribute('additional-attribution-ids', 'a,b');
          }),
          )
          .toBe('gmp_web_maui_v0.1.11_atoui,a,b');
    });

    it('merges IDs from <maui-providers> before per-element IDs', async () => {
      const providers =
          document.createElement('maui-providers') as HTMLElement &
          {additionalAttributionIds: readonly string[]};
      providers.setAttribute('additional-attribution-ids', 'context_id');
      document.body.appendChild(providers);

      expect(
          await renderedIds(
              (list) => {
                list.additionalAttributionIds = ['element_id'];
              },
              providers),
          )
          .toBe('gmp_web_maui_v0.1.11_atoui,context_id,element_id');
      providers.remove();
    });

    it('re-renders when <maui-providers> IDs change', async () => {
      const providers =
          document.createElement('maui-providers') as HTMLElement &
          {additionalAttributionIds: readonly string[]};
      document.body.appendChild(providers);
      const list = document.createElement(
                       'a2ui-advancedplacelist',
                       ) as AdvancedPlaceList;
      (list as unknown as {
        _controller: {props: Partial<AdvancedPlaceListProps>};
      })._controller = {
        props: {places: ['ChIJN1t_tDeuEmsRUsoyG83frY4']},
      };
      providers.appendChild(list);
      await list.updateComplete;

      providers.additionalAttributionIds = ['late_id'];
      await list.updateComplete;

      expect(
          list.renderRoot.querySelector('gmp-advanced-place-list')!
              .getAttribute('internal-usage-attribution-ids'),
          )
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
    const keysMatch: SameKeys<
        typeof AdvancedPlaceListApi.schema.shape, AdvancedPlaceListProps> =
        true;
    expect(keysMatch).toBeTrue();
  });

  it('normalizes array of place IDs and resource names into space-separated place resource names',
     async () => {
       const element = createList({
         places: [
           'ChIJ1',
           'places/ChIJ2',
           '  ChIJ3  ',
         ],
       });
       await element.updateComplete;

       const placeList = element.renderRoot.querySelector(
           'gmp-advanced-place-list',
           )!;
       expect(placeList.getAttribute('places'))
           .toBe(
               'places/ChIJ1 places/ChIJ2 places/ChIJ3',
           );
     });

  it('renders nothing when places is empty', async () => {
    const element = createList({places: []});
    await element.updateComplete;

    expect(
        element.renderRoot.querySelector('gmp-advanced-place-list'),
        )
        .toBeNull();
  });

  describe('orientation, selectable, and truncationPreferred', () => {
    it('defaults to VERTICAL, non-selectable, and truncation-preferred',
       async () => {
         const element = createList({});
         await element.updateComplete;

         const placeList = element.renderRoot.querySelector(
             'gmp-advanced-place-list',
             )!;
         expect(placeList.getAttribute('orientation')).toBe('VERTICAL');
         expect(placeList.hasAttribute('selectable')).toBeFalse();
         expect(placeList.hasAttribute('truncation-preferred')).toBeTrue();
         expect(placeList.getAttribute('attribution-position')).toBe('bottom');
       });

    it('respects explicit horizontal orientation, selectable=true, and truncationPreferred=false',
       async () => {
         const element = createList({
           orientation: 'horizontal',
           selectable: true,
           truncationPreferred: false,
         });
         await element.updateComplete;

         const placeList = element.renderRoot.querySelector(
             'gmp-advanced-place-list',
             )!;
         expect(placeList.getAttribute('orientation')).toBe('HORIZONTAL');
         expect(placeList.hasAttribute('selectable')).toBeTrue();
         expect(placeList.hasAttribute('truncation-preferred')).toBeFalse();
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

         const element = document.createElement(
                             'a2ui-advancedplacelist',
                             ) as AdvancedPlaceList;
         (element as unknown as {
           _controller: {props: Partial<AdvancedPlaceListProps>};
         })._controller = {
           props: {places: ['ChIJN1t_tDeuEmsRUsoyG83frY4']},
         };
         expect(importLibrarySpy).not.toHaveBeenCalled();
         container.appendChild(element);

         await element.updateComplete;
         await Promise.resolve();

         expect(importLibrarySpy).toHaveBeenCalledOnceWith('places');
       } finally {
         windowWithGlobals['google'] = originalGoogle;
       }
     });
});

/** `true` only if A and B have exactly the same keys. */
type SameKeys<A, B> = [
  Exclude<keyof A, keyof B>| Exclude<keyof B, keyof A>,
] extends [never] ? true : false;
