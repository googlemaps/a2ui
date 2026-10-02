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
 * Resolves `google.maps.importLibrary` if available, waiting for a pending
 * Maps JS API `<script>` tag to finish loading if one is present in the DOM.
 */
export async function ensureImportLibrary():
    Promise<typeof google.maps.importLibrary|null> {
  if (typeof google !== 'undefined' && google.maps &&
      google.maps.importLibrary) {
    return google.maps.importLibrary;
  }
  if (typeof document !== 'undefined') {
    const script = document.querySelector<HTMLScriptElement>(
        'script[src*="maps.googleapis.com/maps/api/js"]');
    if (script) {
      await new Promise<void>((resolve) => {
        const done = () => {
          script.removeEventListener('load', done);
          script.removeEventListener('error', done);
          resolve();
        };
        script.addEventListener('load', done);
        script.addEventListener('error', done);
      });
      if (typeof google !== 'undefined' && google.maps &&
          google.maps.importLibrary) {
        return google.maps.importLibrary;
      }
    }
  }
  return null;
}

/**
 * Helper to dynamically load the maps3d library from google.maps at runtime if
 * needed.
 */
export async function loadMaps3DLibrary():
    Promise<google.maps.Maps3DLibrary|null> {
  const importLibrary = await ensureImportLibrary();
  if (importLibrary) {
    return (await importLibrary('maps3d')) as google.maps.Maps3DLibrary;
  }
  return null;
}

/**
 * Helper to dynamically load the routes library from google.maps at runtime if
 * needed.
 */
export async function loadRoutesLibrary():
    Promise<google.maps.RoutesLibrary|null> {
  const importLibrary = await ensureImportLibrary();
  if (importLibrary) {
    return (await importLibrary('routes')) as google.maps.RoutesLibrary;
  }
  return null;
}

/**
 * Helper to dynamically load the places library from google.maps at runtime if
 * needed.
 */
export async function loadPlacesLibrary():
    Promise<google.maps.PlacesLibrary|null> {
  const importLibrary = await ensureImportLibrary();
  if (importLibrary) {
    return (await importLibrary('places')) as google.maps.PlacesLibrary;
  }
  return null;
}

/**
 * Applies options to one or more Maps 3D custom elements synchronously, and if
 * the elements have not yet been upgraded (or `google.maps.CollisionBehavior`
 * is not yet available), loads the `maps3d` library, removes pre-upgrade HTML
 * element properties so prototype setters are invoked, upgrades the elements,
 * and re-applies options.
 *
 * @param elements The element(s) to upgrade and apply options to.
 * @param applyOptions A callback function that applies options to the
 *     elements. This function will be called both before and after the
 *     `maps3d` library is loaded.
 */
export function initMaps3DElement(
    elements: HTMLElement|Array<HTMLElement|null>,
    applyOptions: () => void,
    ): void {
  const list = (Array.isArray(elements) ? elements : [
                 elements
               ]).filter((el): el is HTMLElement => el !== null);

  const unupgradedAtStart = new Set<HTMLElement>(
      list.filter(
          (el) => typeof customElements === 'undefined' ||
              !customElements.get(el.localName)),
  );

  applyOptions();

  const preUpgradeOwnProps = new Map<HTMLElement, string[]>(
      list.map((el) => [el, Object.keys(el)]),
  );

  void loadMaps3DLibrary()
      .then((lib) => {
        if (!lib) return;
        if (typeof customElements !== 'undefined') {
          for (const el of list) {
            if (unupgradedAtStart.has(el) && customElements.get(el.localName)) {
              for (const key of preUpgradeOwnProps.get(el) ?? []) {
                delete (el as unknown as Record<string, unknown>)[key];
              }
            }
            customElements.upgrade?.(el);
          }
        }
        applyOptions();
      })
      .catch((err) => {
        console.error('Failed to load Google Maps 3D library:', err);
      });
}
