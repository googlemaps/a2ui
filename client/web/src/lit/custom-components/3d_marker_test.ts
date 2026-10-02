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

import {loadMaps3DLibrary, ThreeDMarker} from './3d_marker';

describe('ThreeDMarker Class', () => {
  let originalGoogle: unknown;

  beforeEach(() => {
    originalGoogle = (window as unknown as Record<string, unknown>)['google'];
  });

  afterEach(() => {
    (window as unknown as Record<string, unknown>)['google'] = originalGoogle;
  });

  it('creates gmp-marker-3d element with correct properties', () => {
    const marker = new ThreeDMarker({
      id: 'test-marker',
      position: {lat: 37.7749, lng: -122.4194},
      autofitsCamera: true,
      zIndex: 10,
    });
    const el = marker.getElement() as any;
    expect(el.tagName.toLowerCase()).toBe('gmp-marker-3d');
    expect(el.id).toBe('test-marker');
    expect(el.position).toEqual({lat: 37.7749, lng: -122.4194});
    expect(el.autofitsCamera).toBeTrue();
    expect(el.zIndex).toBe(10);
  });

  it('creates associated gmp-label-3d element when label prop is provided',
     () => {
       const marker = new ThreeDMarker({
         id: 'store-marker',
         label: 'SF Flagship Store',
       });
       const labelEl = marker.getLabel() as any;
       expect(labelEl).not.toBeNull();
       expect(labelEl.tagName.toLowerCase()).toBe('gmp-label-3d');
       expect(labelEl.id).toBe('store-marker-label');
       expect(labelEl.getAttribute('for')).toBe('store-marker');
       expect(labelEl.textContent).toBe('SF Flagship Store');
     });

  it('returns null for getLabel() when no label prop is provided', () => {
    const marker = new ThreeDMarker({
      id: 'unlabeled-marker',
      position: {lat: 37.7749, lng: -122.4194},
    });
    expect(marker.getLabel()).toBeNull();
  });

  it('lazyloads maps3d library via google.maps.importLibrary when constructed',
     async () => {
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({});
       (window as unknown as Record<string, unknown>)['google'] = {
         maps: {importLibrary: importLibrarySpy},
       };

       const marker = new ThreeDMarker({
         id: 'lazy-marker',
         position: {lat: 37.7749, lng: -122.4194},
       });
       await Promise.resolve();

       expect(importLibrarySpy).toHaveBeenCalledWith('maps3d');
       const el = marker.getElement() as unknown as Record<string, unknown>;
       expect(el['position']).toEqual({lat: 37.7749, lng: -122.4194});
     });

  it('waits for a pending Maps JS API script tag before calling importLibrary',
     async () => {
       delete (window as unknown as Record<string, unknown>)['google'];
       const fakeScript = document.createElement('script');
       fakeScript.setAttribute(
           'src',
           'https://maps.googleapis.com/maps/api/js?v=alpha&loading=async');
       // Prevent actual network request by not setting src property before
       // overriding or dispatching load event manually.
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
});
