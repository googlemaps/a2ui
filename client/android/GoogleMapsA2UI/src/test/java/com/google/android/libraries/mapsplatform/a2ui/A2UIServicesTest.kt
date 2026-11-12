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
import org.junit.Assert.assertThrows
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
    A2UIServices.resetForTesting()
  }

  @After
  fun tearDown() {
    A2UIServices.resetForTesting()
  }

  /** Verifies that the default API key is null when initialized/reset. */
  @Test
  fun defaultState_apiKeyIsNull() {
    assertThat(A2UIServices.apiKey).isNull()
  }

  /** Verifies that provideApiKey() correctly sets the static apiKey property. */
  @Test
  fun provideApiKey_setsApiKey() {
    A2UIServices.provideApiKey("AIzaSyTestApiKey")
    assertThat(A2UIServices.apiKey).isEqualTo("AIzaSyTestApiKey")
  }

  /** Verifies that repeated calls with the identical key are idempotent no-ops. */
  @Test
  fun provideApiKey_identicalKey_isIdempotent() {
    A2UIServices.provideApiKey("SameKey")
    A2UIServices.provideApiKey("SameKey")
    assertThat(A2UIServices.apiKey).isEqualTo("SameKey")
  }

  /** Verifies that calling provideApiKey() with a different key throws IllegalStateException. */
  @Test
  fun provideApiKey_differentKey_throwsIllegalStateException() {
    A2UIServices.provideApiKey("FirstKey")
    assertThrows(IllegalStateException::class.java) { A2UIServices.provideApiKey("SecondKey") }
    assertThat(A2UIServices.apiKey).isEqualTo("FirstKey")
  }

  /** Verifies that empty or whitespace-only keys throw IllegalArgumentException. */
  @Test
  fun provideApiKey_blankKey_throwsIllegalArgumentException() {
    assertThrows(IllegalArgumentException::class.java) { A2UIServices.provideApiKey("") }
    assertThrows(IllegalArgumentException::class.java) { A2UIServices.provideApiKey("   ") }
    assertThat(A2UIServices.apiKey).isNull()
  }

  /** Verifies that special character keys are stored verbatim. */
  @Test
  fun provideApiKey_specialCharacters_storesExactString() {
    A2UIServices.provideApiKey("AIzaSyTest-Key_123$!@#")
    assertThat(A2UIServices.apiKey).isEqualTo("AIzaSyTest-Key_123$!@#")
  }
}
