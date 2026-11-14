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
import android.content.Intent
import android.net.Uri
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowLooper

/**
 * Unit tests for [A2UIView].
 *
 * Verifies rendering configuration, HTML asset loading, JavaScript injection, deduplication,
 * latency measurement, and URL navigation overriding.
 */
@RunWith(RobolectricTestRunner::class)
class A2UIViewTest {

  private lateinit var activity: Activity
  private lateinit var a2uiView: A2UIView

  @Before
  fun setUp() {
    activity = Robolectric.buildActivity(Activity::class.java).setup().get()
    A2UIServices.provideAPIKey("AIzaSyValidKey")
    a2uiView = A2UIView(activity)
    activity.setContentView(a2uiView)
  }

  @After
  fun tearDown() {
    A2UIServices.provideAPIKey("")
  }

  private fun createMockRequest(urlStr: String?, isMainFrame: Boolean = true): WebResourceRequest {
    val request = mock<WebResourceRequest>()
    whenever(request.url).thenReturn(urlStr?.let { Uri.parse(it) })
    whenever(request.isForMainFrame).thenReturn(isMainFrame)
    whenever(request.method).thenReturn("GET")
    whenever(request.requestHeaders).thenReturn(emptyMap<String, String>())
    return request
  }

  /**
   * Verifies that render() stores the A2UI payload and loads the HTML asset with the API key
   * injected.
   */
  @Test
  fun render_withApiKey_storesPayloadAndLoadsInjectedHtml() {
    val payload = """[{"createSurface": {"surfaceId": "test"}}]"""

    a2uiView.render(payload)
    assertThat(a2uiView.a2uiJson).isEqualTo(payload)

    val shadowWebView = shadowOf(a2uiView)
    val lastLoadedData = shadowWebView.lastLoadDataWithBaseURL
    assertThat(lastLoadedData).isNotNull()
    assertThat(lastLoadedData.baseUrl).isEqualTo("file:///android_asset/")
    assertThat(lastLoadedData.mimeType).isEqualTo("text/html")
    assertThat(lastLoadedData.encoding).isEqualTo("UTF-8")
    assertThat(lastLoadedData.data).contains("AIzaSyValidKey")
  }

  /**
   * Verifies that updateA2uiJson() properly updates the a2uiJson property and schedules JavaScript
   * evaluation with safely escaped JSON when JS is ready.
   */
  @Test
  fun updateA2uiJson_complexJsonPayload_updatesPayloadAndExecutes() {
    val complexJson =
      """[{"text": "Line 1\nLine 2 with \"quotes\" and 'single' and \\backslash"}]"""
    a2uiView.onJsReadyInternal()
    a2uiView.updateA2uiJson(complexJson)
    ShadowLooper.idleMainLooper()

    assertThat(a2uiView.a2uiJson).isEqualTo(complexJson)
    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("shell.processA2uiMessages")
    assertThat(lastEvaluatedJs).contains("Line 1")
    assertThat(lastEvaluatedJs).contains("quotes")
  }

  /**
   * Verifies that updateA2uiJson() when JS is not ready only stores the payload without executing
   * JS.
   */
  @Test
  fun updateA2uiJson_whenJsNotReady_storesPayloadWithoutEvaluating() {
    val payload = """[{"createSurface": {"surfaceId": "pending"}}]"""

    a2uiView.updateA2uiJson(payload)
    assertThat(a2uiView.a2uiJson).isEqualTo(payload)
    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNull()
  }

  /** Verifies that onJsReadyInternal() marks the view ready and pushes queued payloads. */
  @Test
  fun onJsReadyInternal_withQueuedPayload_triggersUpdate() {
    val payload = """[{"createSurface": {"surfaceId": "queued"}}]"""
    a2uiView.a2uiJson = payload

    a2uiView.onJsReadyInternal()
    ShadowLooper.idleMainLooper()

    assertThat(a2uiView.a2uiJson).isEqualTo(payload)
    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("queued")
  }

  /**
   * Verifies that onRenderComplete callback correctly computes latency and receives status, and
   * resets startTime so subsequent calls are ignored.
   */
  @Test
  fun onRenderCompleteInternal_computesLatencyAndInvokesCallback() {
    var callCount = 0
    var invokedLatency: Long? = null
    var invokedStatus: String? = null
    a2uiView.onRenderComplete = { latency, status ->
      callCount++
      invokedLatency = latency
      invokedStatus = status
    }

    val pastStartTime = System.currentTimeMillis() - 150
    a2uiView.render("[]", startTimeMs = pastStartTime)
    a2uiView.onRenderCompleteInternal()

    assertThat(invokedLatency).isNotNull()
    val latency = checkNotNull(invokedLatency)
    assertThat(latency).isAtLeast(150L)
    assertThat(invokedStatus).isEqualTo("A2UI Render Complete")
    assertThat(callCount).isEqualTo(1)

    // Second call should not invoke callback because startTime was reset to null
    a2uiView.onRenderCompleteInternal()
    assertThat(callCount).isEqualTo(1)
  }

  /** Verifies that onRenderCompleteInternal() does not throw when no callback is registered. */
  @Test
  fun onRenderCompleteInternal_withNullCallback_doesNotCrash() {
    a2uiView.onRenderComplete = null
    a2uiView.render("[]")
    a2uiView.onRenderCompleteInternal()
  }

  /**
   * Verifies that shouldOverrideUrlLoading intercepts web and maps URLs to launch ACTION_VIEW
   * intents.
   */
  @Test
  fun shouldOverrideUrlLoading_webUrl_startsActionViewIntent() {
    val request = createMockRequest("https://www.google.com")

    val client = shadowOf(a2uiView).webViewClient
    val handled = client.shouldOverrideUrlLoading(a2uiView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.action).isEqualTo(Intent.ACTION_VIEW)
    assertThat(startedIntent.data).isEqualTo(Uri.parse("https://www.google.com"))
  }

  /**
   * Verifies that shouldOverrideUrlLoading with Google Maps URLs falls back to browser (null
   * package) when the Maps app is not installed on the device.
   */
  @Test
  fun shouldOverrideUrlLoading_mapsUrlWithoutMapsApp_fallsBackToBrowser() {
    val request = createMockRequest("https://maps.google.com/?q=sushi")

    val client = shadowOf(a2uiView).webViewClient
    val handled = client.shouldOverrideUrlLoading(a2uiView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.action).isEqualTo(Intent.ACTION_VIEW)
    assertThat(startedIntent.data).isEqualTo(Uri.parse("https://maps.google.com/?q=sushi"))
    assertThat(startedIntent.`package`).isNull()
  }

  /**
   * Verifies that shouldOverrideUrlLoading also recognizes path-based maps URLs (google.com/maps).
   */
  @Test
  fun shouldOverrideUrlLoading_pathBasedMapsUrl_interceptsIntent() {
    val request = createMockRequest("https://www.google.com/maps/search/pizza")

    val client = shadowOf(a2uiView).webViewClient
    val handled = client.shouldOverrideUrlLoading(a2uiView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.action).isEqualTo(Intent.ACTION_VIEW)
    assertThat(startedIntent.data).isEqualTo(Uri.parse("https://www.google.com/maps/search/pizza"))
  }

  /**
   * Verifies that non-http and non-https schemes (e.g. javascript:, about:blank) are not handled.
   */
  @Test
  fun shouldOverrideUrlLoading_nonHttpScheme_returnsFalse() {
    val request = createMockRequest("javascript:void(0)")

    val client = shadowOf(a2uiView).webViewClient
    val handled = client.shouldOverrideUrlLoading(a2uiView, request)
    assertThat(handled).isFalse()
  }

  /** Verifies that onReceivedError handles resource loading errors gracefully without crashing. */
  @Test
  fun onReceivedError_withNullRequestAndError_logsAndDoesNotCrash() {
    val client = shadowOf(a2uiView).webViewClient
    client.onReceivedError(a2uiView, null, null)
  }

  @Test
  fun onReceivedError_withValidRequestAndError_delegatesAndDoesNotCrash() {
    val request = createMockRequest("https://maps.googleapis.com/test", isMainFrame = true)
    val error = mock<WebResourceError>()
    whenever(error.description).thenReturn("Connection failed")
    whenever(error.errorCode).thenReturn(-2)

    val client = shadowOf(a2uiView).webViewClient
    client.onReceivedError(a2uiView, request, error)

    verify(request).isForMainFrame
    verify(error).errorCode
  }

  /** Verifies that secondary constructors initialize without errors. */
  @Test
  fun constructor_withAttributeSetAndDefStyle_initializesSuccessfully() {
    val viewWithAttrs = A2UIView(activity, null)
    val viewWithStyle = A2UIView(activity, null, 0)
    assertThat(viewWithAttrs).isNotNull()
    assertThat(viewWithStyle).isNotNull()
  }

  /** Verifies that shouldOverrideUrlLoading returns false when request or URL is null. */
  @Test
  fun shouldOverrideUrlLoading_nullRequestOrUrl_returnsFalse() {
    val client = shadowOf(a2uiView).webViewClient
    val requestWithNullUrl = createMockRequest(null)

    assertThat(client.shouldOverrideUrlLoading(a2uiView, null as WebResourceRequest?)).isFalse()
    assertThat(client.shouldOverrideUrlLoading(a2uiView, requestWithNullUrl)).isFalse()
  }

  /** Verifies that shouldOverrideUrlLoading preserves Maps package when Maps app is installed. */
  @Test
  fun shouldOverrideUrlLoading_mapsUrlWithInstalledMapsApp_setsMapsPackage() {
    val mapsIntent =
      Intent(Intent.ACTION_VIEW, Uri.parse("https://maps.google.com/?q=coffee")).apply {
        `package` = "com.google.android.apps.maps"
      }
    val resolveInfo =
      android.content.pm.ResolveInfo().apply {
        activityInfo =
          android.content.pm.ActivityInfo().apply {
            packageName = "com.google.android.apps.maps"
            name = "com.google.android.maps.MapsActivity"
          }
      }
    shadowOf(activity.packageManager).addResolveInfoForIntent(mapsIntent, resolveInfo)

    val request = createMockRequest("https://maps.google.com/?q=coffee")

    val client = shadowOf(a2uiView).webViewClient
    val handled = client.shouldOverrideUrlLoading(a2uiView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.`package`).isEqualTo("com.google.android.apps.maps")
  }

  /** Verifies that onJsReadyInternal does not evaluate JS when a2uiJson is empty. */
  @Test
  fun onJsReadyInternal_withEmptyPayload_doesNotTriggerUpdate() {
    a2uiView.a2uiJson = ""
    a2uiView.onJsReadyInternal()
    ShadowLooper.idleMainLooper()

    val lastEvaluatedJs = shadowOf(a2uiView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNull()
  }
}
