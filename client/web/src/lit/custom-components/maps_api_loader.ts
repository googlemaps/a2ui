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

import {bootstrapMapsJsApi} from './maps_js_api_bootstrap.js';

/** Options for letting MAUI load the Maps JS API on demand. */
export interface MapsJsApiOptions {
  /** Maps JS API key. */
  apiKey: string;
  /**
   * Maps JS API version or release channel, e.g. `'alpha'`. The `maps3d`
   * library used by `GoogleMap` currently requires `'alpha'`, which is the
   * default.
   */
  version?: string;
}

const MAPS_JS_API_SCRIPT_SELECTOR =
    'script[src*="maps.googleapis.com/maps/api/js"]';

/** Set by `configureMapsJsApi` when MAUI installed the bootstrap. */
let configuredImportLibrary: typeof google.maps.importLibrary|undefined;
let warnedUnavailable = false;
/**
 * In-flight content-token registrations that non-`core` library loads wait for.
 */
const pendingContentTokens = new Set<Promise<void>>();

/**
 * Opts in to MAUI loading the Maps JS API the first time a component needs a
 * library, using the official Dynamic Library Import bootstrap.
 *
 * Does nothing if the page already loads the API itself, to avoid loading it
 * twice. Such pages must use the Dynamic Library Import bootstrap (or a
 * synchronous script tag) so that `google.maps.importLibrary` exists by the
 * time MAUI components render.
 */
export function configureMapsJsApi(options: MapsJsApiOptions): void {
  if (getImportLibrary() ||
      (typeof document !== 'undefined' &&
       document.querySelector(MAPS_JS_API_SCRIPT_SELECTOR))) {
    return;
  }
  const version = options.version ?? 'alpha';
  configuredImportLibrary = bootstrapMapsJsApi(options.apiKey, version);
}

/** Resets the loader configuration. For tests only. */
export function resetMapsJsApiLoaderForTesting(): void {
  configuredImportLibrary = undefined;
  warnedUnavailable = false;
  pendingContentTokens.clear();
}

function getImportLibrary(): typeof google.maps.importLibrary|null {
  if (typeof google !== 'undefined' && google.maps &&
      google.maps.importLibrary) {
    return google.maps.importLibrary;
  }
  return null;
}

/**
 * Resolves the function to import Maps JS API libraries with: the page's
 * `google.maps.importLibrary`, or the bootstrap installed by
 * `configureMapsJsApi`. Resolves to `null` if neither is available.
 */
export async function ensureImportLibrary():
    Promise<typeof google.maps.importLibrary|null> {
  const importLibrary = getImportLibrary() ?? configuredImportLibrary ?? null;
  if (!importLibrary && !warnedUnavailable) {
    warnedUnavailable = true;
    console.error(
        'google.maps.importLibrary is unavailable, so Maps components will ' +
        'not render. Load the Maps JavaScript API with the Dynamic Library ' +
        'Import bootstrap, or call configureMapsJsApi().');
  }
  return importLibrary;
}

/** A Maps JS API library name accepted by `google.maps.importLibrary`. */
export type MapsLibraryName = keyof google.maps.ImportLibraryMap;

/** The library types for a tuple of library names, in the same order. */
export type MapsLibraries<T extends readonly MapsLibraryName[]> = {
  -readonly[I in keyof T]: google.maps.ImportLibraryMap[T[I]];
};

/**
 * Loads several Maps JS API libraries in parallel. Resolves to the libraries in
 * the same order as `libraries`, or `null` if the Maps JS API is unavailable.
 */
export async function
loadMapsLibraries<const T extends readonly MapsLibraryName[]>(
    libraries: T,
    ): Promise<MapsLibraries<T>|null> {
  const importLibrary = await ensureImportLibrary();
  if (!importLibrary) {
    return null;
  }
  return (await Promise.all(libraries.map(loadMapsLibrary))) as
      MapsLibraries<T>;
}

/**
 * Registers Maps content tokens on `google.maps.Settings`, loading the `core`
 * library first if `google.maps.Settings` is not yet available.
 */
export function addContentTokens(
    tokens: Record<string, unknown>,
    ): Promise<void> {
  const tokenSet = new Set<string>();
  for (const value of Object.values(tokens)) {
    if (typeof value === 'string' && value.length > 0) {
      tokenSet.add(value);
    } else if (Array.isArray(value)) {
      for (const token of value) {
        if (typeof token === 'string' && token.length > 0) {
          tokenSet.add(token);
        }
      }
    }
  }
  if (tokenSet.size === 0) {
    return Promise.resolve();
  }

  const registerTokens =
      (settingsClass: typeof google.maps.Settings|undefined) => {
        const settings = settingsClass?.getInstance() as unknown as | {
          addContentTokens?: (tokens: Iterable<string>) => void;
        }
        |undefined;
        settings?.addContentTokens?.(Array.from(tokenSet));
      };

  const settingsClass =
      typeof google !== 'undefined' ? google.maps?.Settings : undefined;
  if (settingsClass) {
    registerTokens(settingsClass);
    return Promise.resolve();
  }

  let resolveRegistration!: () => void;
  const registration = new Promise<void>((resolve) => {
    resolveRegistration = resolve;
  });
  pendingContentTokens.add(registration);

  void (async () => {
    try {
      const coreLib = await loadMapsLibrary('core');
      registerTokens(coreLib?.Settings);
    } catch (err) {
      console.error('Failed to load Google Maps Core library:', err);
    } finally {
      pendingContentTokens.delete(registration);
      resolveRegistration();
    }
  })();

  return registration;
}

/**
 * Loads a Maps JS API library. Resolves to the library, or `null` if the Maps
 * JS API is unavailable.
 */
export async function loadMapsLibrary<K extends MapsLibraryName>(
    library: K,
    ): Promise<google.maps.ImportLibraryMap[K]|null> {
  if (library !== 'core') {
    while (pendingContentTokens.size > 0) {
      await Promise.all(pendingContentTokens);
    }
  }
  const importLibrary = await ensureImportLibrary();
  if (!importLibrary) {
    return null;
  }
  return await importLibrary(library);
}
