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

import type {PlaceDetailsCompact} from './place_details_compact';

describe('PlaceDetailsCompact Component', () => {
  it('uses a fallback attribution ID when the global one is missing',
     async () => {
       // 1. Explicitly remove any global attribution ID
       delete (window as any).A2UI_ATTRIBUTION_ID;

       // 2. Render the component with a place ID
       const element = document.createElement('a2ui-placedetailscompact') as PlaceDetailsCompact;
       (element as any).controller = {
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
});
