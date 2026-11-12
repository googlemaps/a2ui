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

import android.app.Activity
import android.content.Context
import android.webkit.WebView
import android.widget.FrameLayout
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowLooper

/**
 * Unit tests for [WebAppInterface].
 *
 * Verifies Web-to-Native event bridging, including main-looper user action callbacks, JavaScript
 * ready signaling, and [A2UIView] dynamic height adjustment.
 */
@RunWith(RobolectricTestRunner::class)
class WebAppInterfaceTest {

  private lateinit var context: Context
  private lateinit var a2uiView: A2UIView
  private lateinit var webView: WebView
  private lateinit var webAppInterface: WebAppInterface

  @Before
  fun setUp() {
    A2UIServices.resetForTesting()
    val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
    context = activity
    A2UIServices.provideApiKey("test-api-key")
    a2uiView = A2UIView(context)
    webView = a2uiView.getChildAt(0) as WebView
    activity.setContentView(a2uiView)
    webAppInterface = WebAppInterface(a2uiView)
  }

  @After
  fun tearDown() {
    A2UIServices.resetForTesting()
  }

  /**
   * Verifies that when the web layer triggers onGetDirections(), the user action listener on
   * [A2UIView] is notified on the main looper with the exact action JSON payload.
   */
  @Test
  fun onGetDirections_actionPayload_surfacesActionOnMainLooper() {
    var receivedAction: String? = null
    a2uiView.setOnUserActionListener { actionJson -> receivedAction = actionJson }

    val actionPayload = """{"placeId": "ChIJN1t_tDeuEmsRUsoyG83frY4", "action": "get_directions"}"""
    webAppInterface.onGetDirections(actionPayload)
    assertThat(receivedAction).isNull()

    ShadowLooper.idleMainLooper()
    assertThat(receivedAction).isEqualTo(actionPayload)
  }

  /** Verifies that onGetDirections() does not throw when no user action listener is registered. */
  @Test
  fun onGetDirections_withNullActionListener_doesNotCrash() {
    a2uiView.setOnUserActionListener(null)
    webAppInterface.onGetDirections("""{"action": "test"}""")
    ShadowLooper.idleMainLooper()
  }

  /** Verifies that onJsReady() triggers the JS ready lifecycle on A2UIView. */
  @Test
  fun onJsReady_withQueuedPayload_triggersJsReadyOnA2uiView() {
    val payload = """[{"createSurface": {"surfaceId": "test"}}]"""
    a2uiView.render(payload)

    webAppInterface.onJsReady()
    ShadowLooper.idleMainLooper()

    val lastEvaluatedJs = shadowOf(webView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("test")
  }

  /**
   * Verifies that onWebpageResized() updates A2UIView's layout parameters to match the content
   * height and fires the OnRenderCompleteListener.
   */
  @Test
  fun onWebpageResized_newHeight_updatesLayoutAndTriggersRenderComplete() {
    var renderCompleteInvoked = false
    var completedLatency: Long? = null
    a2uiView.setOnRenderCompleteListener { latencyMs ->
      renderCompleteInvoked = true
      completedLatency = latencyMs
    }

    a2uiView.layoutParams = FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, 100)

    a2uiView.render("""[{"createSurface": {"surfaceId": "test"}}]""")
    webAppInterface.onWebpageResized(350)
    ShadowLooper.idleMainLooper()

    val expectedHeight = (350 * a2uiView.resources.displayMetrics.density).toInt()
    assertThat(a2uiView.layoutParams.height).isEqualTo(expectedHeight)
    assertThat(renderCompleteInvoked).isTrue()
    assertThat(completedLatency).isNotNull()
    assertThat(webAppInterface.resized).isTrue()
  }

  /**
   * Verifies that subsequent onWebpageResized calls are idempotent for OnRenderCompleteListener.
   */
  @Test
  fun onWebpageResized_whenAlreadyResized_isIdempotent() {
    var renderCount = 0
    a2uiView.setOnRenderCompleteListener { _ -> renderCount++ }

    a2uiView.layoutParams = FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, 100)

    a2uiView.render("""[{"createSurface": {"surfaceId": "test"}}]""")
    webAppInterface.onWebpageResized(300)
    ShadowLooper.idleMainLooper()

    assertThat(renderCount).isEqualTo(1)

    // Second resize updates height but should not fire OnRenderCompleteListener again.
    webAppInterface.onWebpageResized(500)
    ShadowLooper.idleMainLooper()

    val expectedHeight = (500 * a2uiView.resources.displayMetrics.density).toInt()
    assertThat(a2uiView.layoutParams.height).isEqualTo(expectedHeight)
    assertThat(renderCount).isEqualTo(1)
  }

  /**
   * Verifies that onWebpageResized handles null layoutParams on A2UIView gracefully without
   * crashing.
   */
  @Test
  fun onWebpageResized_withNullLayoutParams_doesNotCrash() {
    val unattachedView = A2UIView(context)
    assertThat(unattachedView.layoutParams).isNull()
    val customInterface = WebAppInterface(unattachedView)
    customInterface.resized = false

    customInterface.onWebpageResized(300)
    ShadowLooper.idleMainLooper()

    assertThat(customInterface.resized).isFalse()
  }
}
