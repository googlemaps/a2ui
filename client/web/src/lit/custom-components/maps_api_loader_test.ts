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

import {ensureImportLibrary, loadMapsLibrary, resetMapsJsApiLoaderForTesting} from './maps_api_loader';

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
});
