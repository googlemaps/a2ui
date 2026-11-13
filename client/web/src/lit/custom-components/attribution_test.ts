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

import {attributionIdsConverter, MAUI_WEB_ATTRIBUTION_ID, resolveAttributionIds} from './attribution';

describe('resolveAttributionIds', () => {
  const windowWithGlobals = window as unknown as Record<string, unknown>;
  let originalLegacyId: unknown;

  beforeEach(() => {
    originalLegacyId = windowWithGlobals['A2UI_ATTRIBUTION_ID'];
    delete windowWithGlobals['A2UI_ATTRIBUTION_ID'];
  });

  afterEach(() => {
    if (originalLegacyId === undefined) {
      delete windowWithGlobals['A2UI_ATTRIBUTION_ID'];
    } else {
      windowWithGlobals['A2UI_ATTRIBUTION_ID'] = originalLegacyId;
    }
  });

  it('returns only the MAUI web ID when no extra IDs are given', () => {
    expect(resolveAttributionIds()).toEqual([MAUI_WEB_ATTRIBUTION_ID]);
    expect(MAUI_WEB_ATTRIBUTION_ID).toBe('gmp_web_maui_v0.1.11_atoui');
  });

  it('appends extra IDs from each source in order', () => {
    expect(resolveAttributionIds(['context_id'], ['element_id'])).toEqual([
      MAUI_WEB_ATTRIBUTION_ID,
      'context_id',
      'element_id',
    ]);
  });

  it('accepts comma-separated strings, trims IDs, and drops blanks', () => {
    expect(resolveAttributionIds(' a , ,b ', null, undefined, [
      '', ' c '
    ])).toEqual([MAUI_WEB_ATTRIBUTION_ID, 'a', 'b', 'c']);
  });

  it('removes duplicates, keeping the first occurrence', () => {
    expect(resolveAttributionIds(
               ['a', MAUI_WEB_ATTRIBUTION_ID], ['a', 'b'], 'b,a'))
        .toEqual([MAUI_WEB_ATTRIBUTION_ID, 'a', 'b']);
  });

  it('merges the deprecated window global instead of replacing the MAUI ID',
     () => {
       windowWithGlobals['A2UI_ATTRIBUTION_ID'] =
           `${MAUI_WEB_ATTRIBUTION_ID},legacy_id`;

       expect(resolveAttributionIds(['element_id'])).toEqual([
         MAUI_WEB_ATTRIBUTION_ID,
         'element_id',
         'legacy_id',
       ]);
     });

  it('ignores a non-string window global', () => {
    windowWithGlobals['A2UI_ATTRIBUTION_ID'] = 42;

    expect(resolveAttributionIds()).toEqual([MAUI_WEB_ATTRIBUTION_ID]);
  });
});

describe('attributionIdsConverter', () => {
  it('parses comma-separated attribute values', () => {
    expect(attributionIdsConverter.fromAttribute(' a, b ,,c')).toEqual([
      'a',
      'b',
      'c',
    ]);
    expect(attributionIdsConverter.fromAttribute(null)).toEqual([]);
  });
});
