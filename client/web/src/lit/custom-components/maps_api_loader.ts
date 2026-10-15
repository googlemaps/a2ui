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

let warnedUnavailable = false;

/** Resets the loader state. For tests only. */
export function resetMapsJsApiLoaderForTesting(): void {
  warnedUnavailable = false;
}

function getImportLibrary(): typeof google.maps.importLibrary|null {
  if (typeof google !== 'undefined' && google.maps &&
      google.maps.importLibrary) {
    return google.maps.importLibrary;
  }
  return null;
}

/**
 * Resolves the page's `google.maps.importLibrary`, or `null` if it is not
 * available.
 *
 * Pages must load the Maps JS API with the Dynamic Library Import bootstrap (or
 * a synchronous script tag), so that `google.maps.importLibrary` exists by the
 * time MAUI components render.
 */
export async function ensureImportLibrary():
    Promise<typeof google.maps.importLibrary|null> {
  const importLibrary = getImportLibrary();
  if (!importLibrary && !warnedUnavailable) {
    warnedUnavailable = true;
    console.error(
        'google.maps.importLibrary is unavailable, so Maps components will ' +
        'not render. Load the Maps JavaScript API with the Dynamic Library ' +
        'Import bootstrap.');
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
 * Loads a Maps JS API library. Resolves to the library, or `null` if the Maps
 * JS API is unavailable.
 */
export async function loadMapsLibrary<K extends MapsLibraryName>(
    library: K,
    ): Promise<google.maps.ImportLibraryMap[K]|null> {
  const importLibrary = await ensureImportLibrary();
  if (!importLibrary) {
    return null;
  }
  return await importLibrary(library);
}
