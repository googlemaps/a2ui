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

import './grounding_sources';

import type {MauiGroundingSources} from './grounding_sources';

describe('MauiGroundingSources Component', () => {
  it('renders nothing when sources array is empty', async () => {
    const element = document.createElement('maui-grounding-sources') as
        MauiGroundingSources;
    element.sources = [];
    document.body.appendChild(element);

    await element.updateComplete;

    const section =
        element.renderRoot.querySelector('.grounding-sources-section');
    expect(section).toBeNull();

    document.body.removeChild(element);
  });

  it('renders sources pill button and drawer when sources are provided',
     async () => {
       const element = document.createElement('maui-grounding-sources') as
           MauiGroundingSources;
       element.sources = [
         {
           title: 'Pike Place Market',
           url:
               'https://www.google.com/maps/place/?q=place_id:ChIJp2t_tDeuEmsR',
           type: 'place',
           placeId: 'ChIJp2t_tDeuEmsR',
         },
         {
           title: 'Space Needle',
           url:
               'https://www.google.com/maps/place/?q=place_id:ChIJx3t_tDeuEmsR',
           type: 'place',
           placeId: 'ChIJx3t_tDeuEmsR',
         },
       ];
       document.body.appendChild(element);

       await element.updateComplete;

       const count = element.renderRoot.querySelector('.sources-btn-count');
       expect(count).not.toBeNull();
       expect(count!.textContent?.trim()).toBe('2');

       const cards =
           element.renderRoot.querySelectorAll('.grounding-source-card');
       expect(cards.length).toBe(2);

       const firstCardTitle = cards[0].querySelector('.grounding-source-title');
       expect(firstCardTitle?.textContent?.trim()).toBe('Pike Place Market');

       const firstCardAttribution = cards[0].querySelector('.GMP-attribution');
       expect(firstCardAttribution?.textContent?.trim()).toBe('Google Maps');
       expect(firstCardAttribution?.getAttribute('translate')).toBe('no');

       document.body.removeChild(element);
     });
});
