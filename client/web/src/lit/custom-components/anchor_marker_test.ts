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

import {ANCHOR_PIN_SVG, AnchorMarker, createAnchorMarkerTemplate} from './anchor_marker';

describe('AnchorMarker Module', () => {
  it('creates gmp-marker element with SVG content', () => {
    const marker = new AnchorMarker({
      position: {lat: 37.7749, lng: -122.4194},
      label: 'Anchor Label',
      zIndex: 1,
    });
    const el = marker.getElement() as any;
    expect(el.tagName.toLowerCase()).toBe('gmp-marker');
    expect(el.position).toEqual({lat: 37.7749, lng: -122.4194});

    const template = el.querySelector('template') as HTMLTemplateElement;
    expect(template).not.toBeNull();
    const svg = (template.content?.querySelector('svg') ||
                 template.querySelector('svg')) as SVGElement |
        null;
    expect(svg).not.toBeNull();
  });

  it('creates custom template with provided SVG content', () => {
    const template = createAnchorMarkerTemplate(ANCHOR_PIN_SVG);
    expect(template).toBeDefined();
    const svg = (template.content?.querySelector('svg') ||
                 template.querySelector('svg')) as SVGElement |
        null;
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('viewBox')).toBe('0 0 64 40');
  });
});
