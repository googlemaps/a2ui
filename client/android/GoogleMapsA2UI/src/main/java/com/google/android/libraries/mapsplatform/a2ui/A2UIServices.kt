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

package com.google.android.libraries.mapsplatform.a2ui

import androidx.annotation.VisibleForTesting

/** Global services and configuration for the GoogleMapsA2UI SDK. */
object A2UIServices {
  /** The configured Google Maps API key, or `null` if [provideApiKey] has not been called yet. */
  @get:JvmStatic
  @Volatile
  var apiKey: String? = null
    private set

  /**
   * Configures the Google Maps API key used by [A2UIView].
   *
   * Must be called with a non-blank key before rendering any [A2UIView]. Repeated calls with the
   * identical key are idempotent no-ops.
   *
   * @throws IllegalArgumentException if [apiKey] is blank.
   * @throws IllegalStateException if already initialized with a different key.
   */
  @Synchronized
  @JvmStatic
  fun provideApiKey(apiKey: String) {
    require(apiKey.isNotBlank()) { "API key must not be blank." }
    val existingKey = this.apiKey
    if (existingKey != null) {
      check(existingKey == apiKey) {
        "A2UIServices has already been initialized with a different API key."
      }
      return
    }
    this.apiKey = apiKey
  }

  @Synchronized
  @VisibleForTesting
  internal fun resetForTesting() {
    apiKey = null
  }
}
