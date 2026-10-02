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

import {ensureImportLibrary, initMaps3DElement, loadMaps3DLibrary, loadPlacesLibrary, loadRoutesLibrary} from './maps_api_loader';

describe('maps_api_loader', () => {
  let originalGoogle: unknown;

  beforeEach(() => {
    originalGoogle = (window as unknown as Record<string, unknown>)['google'];
  });

  afterEach(() => {
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;
  });

  it('returns null when google.maps.importLibrary and script tag are absent',
     async () => {
       delete (window as unknown as Record<string, unknown>)['google'];
       expect(await ensureImportLibrary()).toBeNull();
       expect(await loadMaps3DLibrary()).toBeNull();
       expect(await loadRoutesLibrary()).toBeNull();
       expect(await loadPlacesLibrary()).toBeNull();
     });

  it('calls google.maps.importLibrary with expected library names',
     async () => {
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({loaded: true});
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {importLibrary: importLibrarySpy},
       };

       await loadMaps3DLibrary();
       expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');

       await loadRoutesLibrary();
       expect(importLibrarySpy).toHaveBeenCalledWith('routes');

       await loadPlacesLibrary();
       expect(importLibrarySpy).toHaveBeenCalledWith('places');
     });

  it('waits for a pending Maps JS API script tag before calling importLibrary',
     async () => {
       delete (window as unknown as Record<string, unknown>)['google'];
       const fakeScript = document.createElement('script');
       fakeScript.setAttribute(
           'src',
           'https://maps.googleapis.com/maps/api/js?v=alpha&loading=async');
       document.head.appendChild(fakeScript);

       try {
         const importLibrarySpy =
             jasmine.createSpy('importLibrary').and.resolveTo({loaded: true});
         const loadPromise = loadMaps3DLibrary();

         (window as unknown as Record<string, unknown>)['google'] = {
           maps: {importLibrary: importLibrarySpy},
         };
         fakeScript.dispatchEvent(new Event('load'));

         const result = await loadPromise;
         expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');
         expect(result).toEqual(
             {loaded: true} as unknown as google.maps.Maps3DLibrary);
       } finally {
         fakeScript.remove();
       }
     });

  it('initMaps3DElement applies options synchronously and re-applies after upgrade',
     async () => {
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({loaded: true});
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {importLibrary: importLibrarySpy},
       };

       const el = document.createElement('gmp-marker-3d') as HTMLElement & {
         position?: {lat: number; lng: number};
       };
       let applyCount = 0;

       initMaps3DElement(el, () => {
         applyCount++;
         el.position = {lat: 37.7749, lng: -122.4194};
       });

       expect(applyCount).toBe(1);
       expect(el.position).toEqual({lat: 37.7749, lng: -122.4194});

       await new Promise((resolve) => setTimeout(resolve, 0));

       expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');
       expect(applyCount).toBe(2);
       expect(el.position).toEqual({lat: 37.7749, lng: -122.4194});
     });
});
