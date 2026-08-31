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

import {ThreeDMarker} from './3d_marker';

describe('ThreeDMarker Class', () => {
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
});
