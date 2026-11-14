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

import {configureMapsJsApi, ensureImportLibrary, loadMapsLibrary, resetMapsJsApiLoaderForTesting} from './maps_api_loader';

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
});
