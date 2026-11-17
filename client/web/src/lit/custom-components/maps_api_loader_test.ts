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

import {flushEventLoop} from '../testing/event_loop';

import {addContentTokens, configureMapsJsApi, ensureImportLibrary, loadMapsLibrary, resetMapsJsApiLoaderForTesting} from './maps_api_loader';

describe('maps_api_loader', () => {
  let originalGoogle: unknown;

  beforeEach(() => {
    originalGoogle = (window as unknown as Record<string, unknown>)['google'];
    resetMapsJsApiLoaderForTesting();
  });

  afterEach(() => {
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;
    resetMapsJsApiLoaderForTesting();
  });

  it('returns null and logs an error when google.maps.importLibrary is unavailable',
     async () => {
       const errorSpy = spyOn(console, 'error');
       delete (window as unknown as Record<string, unknown>)['google'];
       expect(await ensureImportLibrary()).toBeNull();
       expect(errorSpy).toHaveBeenCalledTimes(1);
       expect(await loadMapsLibrary('maps3d')).toBeNull();
     });

  it('calls google.maps.importLibrary with expected library names',
     async () => {
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({loaded: true});
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {importLibrary: importLibrarySpy},
       };

       await loadMapsLibrary('maps3d');
       expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');

       await loadMapsLibrary('routes');
       expect(importLibrarySpy).toHaveBeenCalledWith('routes');

       await loadMapsLibrary('places');
       expect(importLibrarySpy).toHaveBeenCalledWith('places');
     });

  describe('with configureMapsJsApi', () => {
    let appendedScripts: HTMLScriptElement[];
    let importLibrarySpy: jasmine.Spy;

    /**
     * Simulates the Maps JS API finishing loading: it replaces the bootstrap's
     * `importLibrary` with the real one, then calls the `callback=` function.
     */
    function simulateApiLoaded(script: HTMLScriptElement) {
      (google.maps as unknown as Record<string, unknown>)['importLibrary'] =
          importLibrarySpy;
      const callbackPath = new URL(script.src).searchParams.get('callback')!;
      let callback: unknown = window;
      for (const key of callbackPath.split('.')) {
        callback = (callback as Record<string, unknown>)[key];
      }
      (callback as () => void)();
    }

    beforeEach(() => {
      delete (window as unknown as Record<string, unknown>)['google'];
      appendedScripts = [];
      importLibrarySpy =
          jasmine.createSpy('importLibrary').and.resolveTo({loaded: true});
      // Record injected scripts without attaching them, so the real API is
      // never fetched.
      spyOn(document.head, 'append').and.callFake((...nodes) => {
        appendedScripts.push(...(nodes as HTMLScriptElement[]));
      });
    });

    it('installs google.maps.importLibrary without a network request',
       async () => {
         configureMapsJsApi({apiKey: 'test-key', version: 'alpha'});
         await flushEventLoop();

         expect(typeof google.maps.importLibrary).toBe('function');
         expect(appendedScripts.length).toBe(0);
       });

    it('injects the API on first import and resolves once it has loaded',
       async () => {
         configureMapsJsApi({apiKey: 'test-key', version: 'alpha'});

         const promise = loadMapsLibrary('maps3d');
         await flushEventLoop();

         expect(appendedScripts.length).toBe(1);
         const url = new URL(appendedScripts[0].src);
         expect(url.origin + url.pathname)
             .toBe('https://maps.googleapis.com/maps/api/js');
         expect(url.searchParams.get('key')).toBe('test-key');
         expect(url.searchParams.get('v')).toBe('alpha');
         expect(url.searchParams.get('callback')).toBeTruthy();

         simulateApiLoaded(appendedScripts[0]);
         expect(await promise).toEqual({
           loaded: true
         } as unknown as google.maps.Maps3DLibrary);
         expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');
       });

    it('defaults to the alpha channel when no version is given', async () => {
      const options = {apiKey: 'test-key'};
      configureMapsJsApi(options);

      void loadMapsLibrary('maps3d');
      await flushEventLoop();

      expect(appendedScripts.length).toBe(1);
      expect(new URL(appendedScripts[0].src).searchParams.get('v'))
          .toBe('alpha');
      expect(options).toEqual({apiKey: 'test-key'});
    });

    it('uses the given version instead of the default', async () => {
      configureMapsJsApi({apiKey: 'test-key', version: 'weekly'});

      void loadMapsLibrary('maps3d');
      await flushEventLoop();

      expect(appendedScripts.length).toBe(1);
      expect(new URL(appendedScripts[0].src).searchParams.get('v'))
          .toBe('weekly');
    });

    it('injects only one script for concurrent imports', async () => {
      configureMapsJsApi({apiKey: 'test-key'});

      const first = loadMapsLibrary('maps3d');
      const second = loadMapsLibrary('places');
      await flushEventLoop();

      expect(appendedScripts.length).toBe(1);

      simulateApiLoaded(appendedScripts[0]);
      await Promise.all([first, second]);
      expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');
      expect(importLibrarySpy).toHaveBeenCalledWith('places');
      expect(appendedScripts.length).toBe(1);
    });

    it('copies the CSP nonce from an existing script', async () => {
      const nonceScript = document.createElement('script');
      nonceScript.type = 'text/plain';
      nonceScript.setAttribute('nonce', 'test-nonce');
      document.head.prepend(nonceScript);

      try {
        configureMapsJsApi({apiKey: 'test-key'});
        void loadMapsLibrary('maps3d');
        await flushEventLoop();

        expect(appendedScripts.length).toBe(1);
        expect(appendedScripts[0].nonce).toBe('test-nonce');
      } finally {
        nonceScript.remove();
      }
    });

    it('rejects imports when the API script fails to load', async () => {
      configureMapsJsApi({apiKey: 'test-key'});

      const promise = loadMapsLibrary('maps3d');
      await flushEventLoop();
      appendedScripts[0].dispatchEvent(new Event('error'));

      await expectAsync(promise).toBeRejected();
    });

    it('does nothing when the page already has a Maps JS API script',
       async () => {
         spyOn(console, 'error');
         const existingScript = document.createElement('script');
         existingScript.type = 'text/plain';
         existingScript.setAttribute(
             'src',
             'https://maps.googleapis.com/maps/api/js?v=alpha&loading=async');
         document.head.prepend(existingScript);

         try {
           configureMapsJsApi({apiKey: 'test-key'});

           expect((window as unknown as Record<string, unknown>)['google'])
               .toBeUndefined();
           expect(await ensureImportLibrary()).toBeNull();
           expect(appendedScripts.length).toBe(0);
         } finally {
           existingScript.remove();
         }
       });

    it('does nothing when the API is already loaded', async () => {
      (window as unknown as Record<string, unknown>)['google'] = {
        maps: {importLibrary: importLibrarySpy},
      };

      configureMapsJsApi({apiKey: 'test-key'});

      expect(await ensureImportLibrary()).toBe(importLibrarySpy);
      expect(appendedScripts.length).toBe(0);
    });
  });

  describe('addContentTokens', () => {
    it('registers unique non-empty tokens synchronously when Settings is available',
       () => {
         const mockAddContentTokens = jasmine.createSpy('addContentTokens');
         const importLibrarySpy = jasmine.createSpy('importLibrary');
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {
             importLibrary: importLibrarySpy,
             Settings: {
               getInstance: () => ({
                 addContentTokens: mockAddContentTokens,
               }),
             },
           },
         };

         void addContentTokens({
           place_1: 'token_1',
           place_2: 'token_2',
           place_3: 'token_1',
           '': ['fallback_1', '', 123, 'token_2'],
           empty: '',
           invalid: null,
         });

         expect(mockAddContentTokens).toHaveBeenCalledOnceWith([
           'token_1',
           'token_2',
           'fallback_1',
         ]);
         expect(importLibrarySpy).not.toHaveBeenCalled();
       });

    it('skips loading core when no valid string tokens are present',
       async () => {
         const importLibrarySpy = jasmine.createSpy('importLibrary');
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };

         await addContentTokens({
           empty: '',
           list: ['', 42],
           invalid: null,
         });

         expect(importLibrarySpy).not.toHaveBeenCalled();
       });

    it('gates non-core loadMapsLibrary calls behind in-flight addContentTokens',
       async () => {
         const callOrder: string[] = [];
         const mockAddContentTokens =
             jasmine.createSpy('addContentTokens').and.callFake(() => {
               callOrder.push('addContentTokens');
             });
         let resolveCore!: (value: unknown) => void;
         const corePromise = new Promise((resolve) => {
           resolveCore = resolve;
         });
         const placesLib = {PlaceDetailsCompactElement: class {}};
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.callFake((lib: string) => {
               callOrder.push(`import:${lib}`);
               if (lib === 'core') {
                 return corePromise;
               }
               return Promise.resolve(placesLib);
             });
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };

         const tokenPromise = addContentTokens({place_1: 'tok_1'});
         const placesPromise = loadMapsLibrary('places');
         await flushEventLoop();

         expect(importLibrarySpy).toHaveBeenCalledOnceWith('core');

         resolveCore({
           Settings: {
             getInstance: () => ({
               addContentTokens: mockAddContentTokens,
             }),
           },
         });
         const resolvedPlaces = await placesPromise;
         await tokenPromise;

         expect(resolvedPlaces)
             .toBe(placesLib as unknown as google.maps.PlacesLibrary);
         expect(callOrder).toEqual([
           'import:core',
           'addContentTokens',
           'import:places',
         ]);
         expect(mockAddContentTokens).toHaveBeenCalledOnceWith(['tok_1']);
       });

    it('does not block loadMapsLibrary("core") while addContentTokens is in flight',
       async () => {
         let resolveFirstCore!: (value: unknown) => void;
         const firstCorePromise = new Promise((resolve) => {
           resolveFirstCore = resolve;
         });
         const secondCoreLib = {Settings: {getInstance: () => ({})}};
         let coreCalls = 0;
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.callFake(() => {
               coreCalls++;
               return coreCalls === 1 ? firstCorePromise :
                                        Promise.resolve(secondCoreLib);
             });
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };

         const tokenPromise = addContentTokens({place_1: 'tok_1'});
         const directCorePromise = loadMapsLibrary('core');

         expect(await directCorePromise)
             .toBe(secondCoreLib as unknown as google.maps.CoreLibrary);
         expect(importLibrarySpy.calls.allArgs()).toEqual([
           ['core'],
           ['core'],
         ]);

         resolveFirstCore(secondCoreLib);
         await tokenPromise;
       });

    it('waits for overlapping addContentTokens calls before loading non-core libraries',
       async () => {
         const callOrder: string[] = [];
         const coreResolvers: Array<(value: unknown) => void> = [];
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.callFake((lib: string) => {
               callOrder.push(`import:${lib}`);
               if (lib === 'core') {
                 return new Promise((resolve) => {
                   coreResolvers.push(resolve);
                 });
               }
               return Promise.resolve({loaded: true});
             });
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };

         const makeCoreLib = (label: string) => ({
           Settings: {
             getInstance: () => ({
               addContentTokens: () => {
                 callOrder.push(label);
               },
             }),
           },
         });

         const firstTokens = addContentTokens({place_1: 'tok_1'});
         const placesPromise = loadMapsLibrary('places');
         await flushEventLoop();

         const secondTokens = addContentTokens({place_2: 'tok_2'});
         await flushEventLoop();

         coreResolvers[0](makeCoreLib('tokens_1'));
         await flushEventLoop();
         expect(callOrder).not.toContain('import:places');

         coreResolvers[1](makeCoreLib('tokens_2'));
         await Promise.all([firstTokens, secondTokens, placesPromise]);

         expect(callOrder).toEqual([
           'import:core',
           'import:core',
           'tokens_1',
           'tokens_2',
           'import:places',
         ]);
       });

    it('unblocks non-core loadMapsLibrary calls when loading core fails',
       async () => {
         const loadError = new Error('Network error');
         const placesLib = {loaded: true};
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.callFake((lib: string) => {
               if (lib === 'core') {
                 return Promise.reject(loadError);
               }
               return Promise.resolve(placesLib);
             });
         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };
         const consoleErrorSpy = spyOn(console, 'error');

         const tokenPromise = addContentTokens({place_1: 'tok_1'});
         const placesPromise = loadMapsLibrary('places');
         const resolvedPlaces = await placesPromise;
         await tokenPromise;

         expect(consoleErrorSpy)
             .toHaveBeenCalledOnceWith(
                 'Failed to load Google Maps Core library:',
                 loadError,
             );
         expect(resolvedPlaces)
             .toBe(placesLib as unknown as google.maps.PlacesLibrary);
       });
  });
});
