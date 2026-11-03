/*
 Copyright 2026 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

/**
 * @fileoverview Maps JS API usage attribution IDs for MAUI components.
 *
 * Every MAUI component sends `MAUI_WEB_ATTRIBUTION_ID`. Hosts can append their
 * own IDs either per element (`additionalAttributionIds`) or for a whole
 * subtree through `<maui-providers additional-attribution-ids="...">`.
 */

import {createContext} from '@lit/context';

/** Sent by every MAUI web component. Bump on release. */
export const MAUI_WEB_ATTRIBUTION_ID = 'gmp_web_maui_v0.1.10_atoui';

/**
 * Additional attribution IDs provided by an ancestor `<maui-providers>`.
 *
 * Uses `Symbol.for` so that separately bundled copies of MAUI still agree on
 * the context key.
 */
export const attributionIdsContext =
    createContext<readonly string[]>(Symbol.for('MAUIAttributionIds'));

/** Attribution IDs as a list, or as a comma-separated string. */
export type AttributionIdsInput = Iterable<string>|string|null|undefined;

/**
 * Name of the legacy page-wide global that used to replace MAUI's default ID.
 *
 * TODO: Remove once the samples React app stops setting it.
 */
const LEGACY_ATTRIBUTION_ID_GLOBAL = 'A2UI_ATTRIBUTION_ID';

function normalizeAttributionIds(input: AttributionIdsInput): string[] {
  if (input == null) return [];
  const ids = typeof input === 'string' ? input.split(',') : [...input];
  return ids.map((id) => String(id).trim()).filter((id) => id.length > 0);
}

function getLegacyAttributionIds(): string[] {
  const legacy =
      (globalThis as Record<string, unknown>)[LEGACY_ATTRIBUTION_ID_GLOBAL];
  return typeof legacy === 'string' ? normalizeAttributionIds(legacy) : [];
}

/**
 * Returns the attribution IDs to send: `MAUI_WEB_ATTRIBUTION_ID` first, then
 * the IDs from each source in order, then any IDs from the deprecated
 * `window.A2UI_ATTRIBUTION_ID` global. Duplicates and blanks are dropped.
 */
export function resolveAttributionIds(...sources: AttributionIdsInput[]):
    string[] {
  return [...new Set([
    MAUI_WEB_ATTRIBUTION_ID,
    ...sources.flatMap(normalizeAttributionIds),
    ...getLegacyAttributionIds(),
  ])];
}

/**
 * Lit property converter that accepts `additional-attribution-ids="a, b"` as
 * an attribute. The property is not reflected, so no `toAttribute` is needed.
 */
export const attributionIdsConverter = {
  fromAttribute: (value: string|null): readonly string[] =>
      normalizeAttributionIds(value),
};
