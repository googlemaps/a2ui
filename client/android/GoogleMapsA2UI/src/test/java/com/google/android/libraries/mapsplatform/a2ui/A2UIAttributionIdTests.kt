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

import java.io.InputStreamReader
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class A2UIAttributionIdTests {

  @Test
  fun testAndroidAttributionIdIsGenerated() {
    // Read index.html from Android assets
    val context = org.robolectric.RuntimeEnvironment.getApplication()
    val inputStream = context.assets.open("index.html")
    requireNotNull(inputStream) { "Failed to load local index.html" }

    val htmlContent = InputStreamReader(inputStream).readText()

    assertTrue(
      "Expected the generated attribution ID to contain the Web identifier 'gmp_web_maui_v0.1.7_exp'",
      htmlContent.contains("gmp_web_maui_v0.1.7_exp"),
    )
    assertTrue(
      "Expected the generated attribution ID to contain the Android identifier 'gmp_android_maui_v0.1.7_exp'",
      htmlContent.contains("gmp_android_maui_v0.1.7_exp"),
    )
    assertTrue(
      "Expected the generated attribution ID to contain the combined Web and Android identifier string 'gmp_web_maui_v0.1.7_exp,gmp_android_maui_v0.1.7_exp'",
      htmlContent.contains("gmp_web_maui_v0.1.7_exp,gmp_android_maui_v0.1.7_exp"),
    )
  }
}
