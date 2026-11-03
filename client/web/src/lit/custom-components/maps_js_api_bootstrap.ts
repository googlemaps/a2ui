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

/*
 * Installs the official Maps JS API Dynamic Library Import
 * bootstrap, using `@googlemaps/js-api-loader`.
 *
 * Not built in google3. The GitHub/npm export moves this file over
 * `maps_js_api_bootstrap.ts`, which uses the google3 inline Maps loader. Keep
 * both files' exports identical.
 */

import {importLibrary, setOptions} from '@googlemaps/js-api-loader';

/**
 * Installs the Maps JS API bootstrap. No network request is made until a
 * library is imported.
 *
 * @param apiKey Maps JS API key.
 * @param version Maps JS API version or release channel, e.g. `'alpha'`.
 * @return The function to import Maps JS API libraries with. Its promises
 *     resolve once the API has fully loaded.
 */
export function bootstrapMapsJsApi(
    apiKey: string,
    version?: string,
    ): typeof google.maps.importLibrary {
  setOptions({key: apiKey, ...(version ? {v: version} : {})});
  return importLibrary as unknown as typeof google.maps.importLibrary;
}
