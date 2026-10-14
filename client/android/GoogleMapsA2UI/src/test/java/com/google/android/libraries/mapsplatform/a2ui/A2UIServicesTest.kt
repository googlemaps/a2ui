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

import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.JUnit4

/**
 * Unit tests for [A2UIServices].
 *
 * Verifies global configuration, including Google Maps API Key provisioning.
 */
@RunWith(JUnit4::class)
class A2UIServicesTest {

  @Before
  fun setUp() {
    A2UIServices.provideAPIKey("")
  }

  @After
  fun tearDown() {
    A2UIServices.provideAPIKey("")
  }

  /** Verifies that the default API key is empty when initialized/reset. */
  @Test
  fun defaultState_apiKeyIsEmpty() {
    assertThat(A2UIServices.apiKey).isEmpty()
  }

  /** Verifies that provideAPIKey() correctly sets the static apiKey property. */
  @Test
  fun provideAPIKey_setsApiKey() {
    A2UIServices.provideAPIKey("AIzaSyTestApiKey")
    assertThat(A2UIServices.apiKey).isEqualTo("AIzaSyTestApiKey")
  }

  /** Verifies that subsequent calls to provideAPIKey() override previous keys. */
  @Test
  fun provideAPIKey_consecutiveUpdates_overridesKey() {
    A2UIServices.provideAPIKey("FirstKey")
    assertThat(A2UIServices.apiKey).isEqualTo("FirstKey")

    A2UIServices.provideAPIKey("SecondKey")
    assertThat(A2UIServices.apiKey).isEqualTo("SecondKey")
  }

  /** Verifies that blank or special character keys are stored verbatim. */
  @Test
  fun provideAPIKey_blankOrSpecialCharacters_storesExactString() {
    A2UIServices.provideAPIKey("AIzaSyTest-Key_123$!@#")
    assertThat(A2UIServices.apiKey).isEqualTo("AIzaSyTest-Key_123$!@#")

    A2UIServices.provideAPIKey("")
    assertThat(A2UIServices.apiKey).isEmpty()
  }
}
