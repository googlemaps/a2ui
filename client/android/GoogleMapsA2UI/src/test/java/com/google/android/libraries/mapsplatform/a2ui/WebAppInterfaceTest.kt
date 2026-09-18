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
 * Verifies Web-to-Native event bridging, including user action callbacks (directions requests),
 * JavaScript ready signaling, and WebView dynamic height adjustment.
 */
@RunWith(RobolectricTestRunner::class)
class WebAppInterfaceTest {

  private lateinit var context: Context
  private lateinit var a2uiView: A2UIView
  private lateinit var webAppInterface: WebAppInterface

  @Before
  fun setUp() {
    val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
    context = activity
    A2UIServices.provideAPIKey("test-api-key")
    a2uiView = A2UIView(context)
    activity.setContentView(a2uiView)
    webAppInterface = WebAppInterface(a2uiView, a2uiView)
  }

  @After
  fun tearDown() {
    A2UIServices.provideAPIKey("")
  }

  /** Verifies that sendA2uiMessages posts JavaScript evaluation and resets the resized state. */
  @Test
  fun sendA2uiMessages_validPayload_postsJsEvaluationAndResetsResizeState() {
    webAppInterface.resized = true
    val payload = """[{"createSurface": {"surfaceId": "msg-1"}}]"""

    webAppInterface.sendA2uiMessages(payload)
    ShadowLooper.idleMainLooper()

    assertThat(webAppInterface.resized).isFalse()
    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("shell.processA2uiMessages")
    assertThat(lastEvaluatedJs).contains("msg-1")
  }

  /**
   * Verifies that when the web layer triggers onGetDirections(), the user action callback on
   * [A2UIView] is notified with the exact action JSON payload.
   */
  @Test
  fun onGetDirections_actionPayload_surfacesActionToCallback() {
    var receivedAction: String? = null
    a2uiView.onUserAction = { actionJson -> receivedAction = actionJson }

    val actionPayload = """{"placeId": "ChIJN1t_tDeuEmsRUsoyG83frY4", "action": "get_directions"}"""
    webAppInterface.onGetDirections(actionPayload)

    assertThat(receivedAction).isEqualTo(actionPayload)
  }

  /** Verifies that onGetDirections() does not throw when no user action callback is registered. */
  @Test
  fun onGetDirections_withNullActionCallback_doesNotCrash() {
    a2uiView.onUserAction = null
    webAppInterface.onGetDirections("""{"action": "test"}""")
  }

  /** Verifies that onJsReady() triggers the JS ready lifecycle on A2UIView. */
  @Test
  fun onJsReady_withQueuedPayload_triggersJsReadyOnA2uiView() {
    val payload = """[{"createSurface": {"surfaceId": "test"}}]"""
    a2uiView.a2uiJson = payload

    webAppInterface.onJsReady()
    ShadowLooper.idleMainLooper()

    assertThat(a2uiView.a2uiJson).isEqualTo(payload)
    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("test")
  }

  /**
   * Verifies that onWebpageResized() updates the WebView layout parameters to match the content
   * height and fires the onRenderComplete callback.
   */
  @Test
  fun onWebpageResized_newHeight_updatesLayoutAndTriggersRenderComplete() {
    var renderCompleteInvoked = false
    var completedStatus: String? = null
    a2uiView.onRenderComplete = { _, status ->
      renderCompleteInvoked = true
      completedStatus = status
    }

    a2uiView.layoutParams = FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, 100)

    a2uiView.render("""[{"createSurface": {"surfaceId": "test"}}]""")
    webAppInterface.onWebpageResized(350)
    ShadowLooper.idleMainLooper()

    val expectedHeight = (350 * a2uiView.resources.displayMetrics.density).toInt()
    assertThat(a2uiView.layoutParams.height).isEqualTo(expectedHeight)
    assertThat(renderCompleteInvoked).isTrue()
    assertThat(completedStatus).isEqualTo("A2UI Render Complete")
    assertThat(webAppInterface.resized).isTrue()
  }

  /** Verifies that subsequent onWebpageResized calls are ignored once resized is true. */
  @Test
  fun onWebpageResized_whenAlreadyResized_isIdempotent() {
    var renderCount = 0
    a2uiView.onRenderComplete = { _, _ -> renderCount++ }

    a2uiView.layoutParams = FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, 100)

    a2uiView.render("""[{"createSurface": {"surfaceId": "test"}}]""")
    webAppInterface.onWebpageResized(300)
    ShadowLooper.idleMainLooper()

    assertThat(renderCount).isEqualTo(1)

    // Second resize call while resized == true should be ignored
    webAppInterface.onWebpageResized(500)
    ShadowLooper.idleMainLooper()

    assertThat(renderCount).isEqualTo(1)
  }

  /**
   * Verifies that onWebpageResized handles null layoutParams on the WebView gracefully without
   * crashing.
   */
  @Test
  fun onWebpageResized_withNullLayoutParams_doesNotCrash() {
    val unattachedView = A2UIView(context)
    unattachedView.layoutParams = null
    val customInterface = WebAppInterface(unattachedView, unattachedView)
    customInterface.resized = false

    customInterface.onWebpageResized(300)
    ShadowLooper.idleMainLooper()

    assertThat(customInterface.resized).isFalse()
  }
}
