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
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.widget.FrameLayout
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Assert.assertThrows
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
 * Verifies FrameLayout composition, rendering configuration, HTML asset loading, JavaScript
 * injection, latency measurement, console forwarding, and URL navigation overriding.
 */
@RunWith(RobolectricTestRunner::class)
class A2UIViewTest {

  private lateinit var activity: Activity
  private lateinit var a2uiView: A2UIView
  private lateinit var webView: WebView

  @Before
  fun setUp() {
    A2UIServices.resetForTesting()
    activity = Robolectric.buildActivity(Activity::class.java).setup().get()
    A2UIServices.provideApiKey("AIzaSyValidKey")
    a2uiView = A2UIView(activity)
    webView = a2uiView.getChildAt(0) as WebView
    activity.setContentView(a2uiView)
  }

  @After
  fun tearDown() {
    A2UIServices.resetForTesting()
  }

  private fun createMockRequest(urlStr: String?, isMainFrame: Boolean = true): WebResourceRequest {
    val request = mock<WebResourceRequest>()
    whenever(request.url).thenReturn(urlStr?.let { Uri.parse(it) })
    whenever(request.isForMainFrame).thenReturn(isMainFrame)
    whenever(request.method).thenReturn("GET")
    whenever(request.requestHeaders).thenReturn(emptyMap<String, String>())
    return request
  }

  /** Verifies that A2UIView is a FrameLayout wrapping a single MATCH_PARENT WebView child. */
  @Test
  fun viewHierarchy_isFrameLayoutWrappingSingleMatchParentWebView() {
    assertThat(a2uiView).isInstanceOf(FrameLayout::class.java)
    assertThat(a2uiView).isNotInstanceOf(WebView::class.java)
    assertThat(a2uiView.childCount).isEqualTo(1)
    assertThat(a2uiView.getChildAt(0)).isSameInstanceAs(webView)
    assertThat(webView.layoutParams.width).isEqualTo(ViewGroup.LayoutParams.MATCH_PARENT)
    assertThat(webView.layoutParams.height).isEqualTo(ViewGroup.LayoutParams.MATCH_PARENT)
  }

  /** Verifies that render() fails fast when A2UIServices.provideApiKey() was not called. */
  @Test
  fun render_withoutApiKey_throwsIllegalStateException() {
    A2UIServices.resetForTesting()
    assertThrows(IllegalStateException::class.java) {
      a2uiView.render("""[{"createSurface": {"surfaceId": "test"}}]""")
    }
  }

  /**
   * Verifies that render() injects the API key into HTML and evaluates the payload once JS is
   * ready.
   */
  @Test
  fun render_withApiKey_loadsInjectedHtmlAndQueuesPayload() {
    val payload = """[{"createSurface": {"surfaceId": "test"}}]"""

    a2uiView.render(payload)

    val shadowWebView = shadowOf(webView)
    val lastLoadedData = shadowWebView.lastLoadDataWithBaseURL
    assertThat(lastLoadedData).isNotNull()
    assertThat(lastLoadedData.baseUrl).isEqualTo("file:///android_asset/")
    assertThat(lastLoadedData.mimeType).isEqualTo("text/html")
    assertThat(lastLoadedData.encoding).isEqualTo("UTF-8")
    assertThat(lastLoadedData.data).contains("AIzaSyValidKey")

    a2uiView.onJsReadyInternal()
    ShadowLooper.idleMainLooper()
    assertThat(shadowWebView.lastEvaluatedJavascript).contains("test")
  }

  /**
   * Verifies that updateA2uiJson() schedules JavaScript evaluation with safely escaped JSON when JS
   * is ready.
   */
  @Test
  fun updateA2uiJson_complexJsonPayload_executesEscapedJs() {
    val complexJson =
      """[{"text": "Line 1\nLine 2 with \"quotes\" and 'single' and \\backslash"}]"""
    a2uiView.onJsReadyInternal()
    a2uiView.updateA2uiJson(complexJson)
    ShadowLooper.idleMainLooper()

    val lastEvaluatedJs = shadowOf(webView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNotNull()
    assertThat(lastEvaluatedJs).contains("shell.processA2uiMessages")
    assertThat(lastEvaluatedJs).contains("Line 1")
    assertThat(lastEvaluatedJs).contains("quotes")
  }

  /**
   * Verifies that updateA2uiJson() when JS is not ready defers execution until onJsReadyInternal().
   */
  @Test
  fun updateA2uiJson_whenJsNotReady_defersUntilJsReady() {
    val payload = """[{"createSurface": {"surfaceId": "pending"}}]"""

    a2uiView.updateA2uiJson(payload)
    ShadowLooper.idleMainLooper()
    assertThat(shadowOf(webView).lastEvaluatedJavascript).isNull()

    a2uiView.onJsReadyInternal()
    ShadowLooper.idleMainLooper()
    assertThat(shadowOf(webView).lastEvaluatedJavascript).contains("pending")
  }

  /**
   * Verifies that OnRenderCompleteListener receives latency from the clock and resets startTime so
   * subsequent calls are ignored.
   */
  @Test
  fun onRenderCompleteInternal_computesLatencyAndInvokesListenerOnce() {
    var nowMs = 1_000L
    a2uiView.clock = { nowMs }

    var callCount = 0
    var invokedLatency: Long? = null
    a2uiView.setOnRenderCompleteListener { latency ->
      callCount++
      invokedLatency = latency
    }

    a2uiView.render("[]")
    nowMs = 1_175L
    a2uiView.onRenderCompleteInternal()

    assertThat(invokedLatency).isEqualTo(175L)
    assertThat(callCount).isEqualTo(1)

    // Second call should not invoke listener because startTime was reset to null
    a2uiView.onRenderCompleteInternal()
    assertThat(callCount).isEqualTo(1)
  }

  /** Verifies that onRenderCompleteInternal() does not throw when no listener is registered. */
  @Test
  fun onRenderCompleteInternal_withNullListener_doesNotCrash() {
    a2uiView.setOnRenderCompleteListener(null)
    a2uiView.render("[]")
    a2uiView.onRenderCompleteInternal()
  }

  /** Verifies listener getters and setters round-trip cleanly. */
  @Test
  fun listeners_setAndGet_roundTrip() {
    val renderListener = A2UIView.OnRenderCompleteListener {}
    val actionListener = A2UIView.OnUserActionListener {}

    a2uiView.setOnRenderCompleteListener(renderListener)
    a2uiView.setOnUserActionListener(actionListener)

    assertThat(a2uiView.getOnRenderCompleteListener()).isSameInstanceAs(renderListener)
    assertThat(a2uiView.getOnUserActionListener()).isSameInstanceAs(actionListener)
  }

  /** Verifies that WebChromeClient handles console messages without crashing. */
  @Test
  fun webChromeClient_onConsoleMessage_returnsTrue() {
    val chromeClient = shadowOf(webView).webChromeClient
    assertThat(chromeClient).isNotNull()

    assertThat(chromeClient.onConsoleMessage(null)).isTrue()
    assertThat(
        chromeClient.onConsoleMessage(
          ConsoleMessage("info", "core-shell.ts", 10, ConsoleMessage.MessageLevel.LOG)
        )
      )
      .isTrue()
    assertThat(
        chromeClient.onConsoleMessage(
          ConsoleMessage("warn", "core-shell.ts", 20, ConsoleMessage.MessageLevel.WARNING)
        )
      )
      .isTrue()
    assertThat(
        chromeClient.onConsoleMessage(
          ConsoleMessage("err", "core-shell.ts", 30, ConsoleMessage.MessageLevel.ERROR)
        )
      )
      .isTrue()
  }

  /**
   * Verifies that shouldOverrideUrlLoading intercepts web and maps URLs to launch ACTION_VIEW
   * intents.
   */
  @Test
  fun shouldOverrideUrlLoading_webUrl_startsActionViewIntent() {
    val request = createMockRequest("https://www.google.com")

    val client = shadowOf(webView).webViewClient
    val handled = client.shouldOverrideUrlLoading(webView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.action).isEqualTo(Intent.ACTION_VIEW)
    assertThat(startedIntent.data).isEqualTo(Uri.parse("https://www.google.com"))
    assertThat(startedIntent.flags and Intent.FLAG_ACTIVITY_NEW_TASK).isEqualTo(0)
  }

  /**
   * Verifies that shouldOverrideUrlLoading adds FLAG_ACTIVITY_NEW_TASK when constructed with a
   * non-Activity context.
   */
  @Test
  fun shouldOverrideUrlLoading_withApplicationContext_addsNewTaskFlag() {
    val appView = A2UIView(activity.applicationContext)
    val appWebView = appView.getChildAt(0) as WebView
    val request = createMockRequest("https://www.google.com")

    val handled = shadowOf(appWebView).webViewClient.shouldOverrideUrlLoading(appWebView, request)
    assertThat(handled).isTrue()

    val startedIntent =
      shadowOf(activity.applicationContext as android.app.Application).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.flags and Intent.FLAG_ACTIVITY_NEW_TASK)
      .isEqualTo(Intent.FLAG_ACTIVITY_NEW_TASK)
  }

  /**
   * Verifies that shouldOverrideUrlLoading with Google Maps URLs falls back to browser (null
   * package) when the Maps app is not installed on the device.
   */
  @Test
  fun shouldOverrideUrlLoading_mapsUrlWithoutMapsApp_fallsBackToBrowser() {
    val request = createMockRequest("https://maps.google.com/?q=sushi")

    val client = shadowOf(webView).webViewClient
    val handled = client.shouldOverrideUrlLoading(webView, request)
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

    val client = shadowOf(webView).webViewClient
    val handled = client.shouldOverrideUrlLoading(webView, request)
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

    val client = shadowOf(webView).webViewClient
    val handled = client.shouldOverrideUrlLoading(webView, request)
    assertThat(handled).isFalse()
  }

  /** Verifies that onReceivedError handles resource loading errors gracefully without crashing. */
  @Test
  fun onReceivedError_withNullRequestAndError_logsAndDoesNotCrash() {
    val client = shadowOf(webView).webViewClient
    client.onReceivedError(webView, null, null)
  }

  @Test
  fun onReceivedError_withValidRequestAndError_delegatesAndDoesNotCrash() {
    val request = createMockRequest("https://maps.googleapis.com/test", isMainFrame = true)
    val error = mock<WebResourceError>()
    whenever(error.description).thenReturn("Connection failed")
    whenever(error.errorCode).thenReturn(-2)

    val client = shadowOf(webView).webViewClient
    client.onReceivedError(webView, request, error)

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
    val client = shadowOf(webView).webViewClient
    val requestWithNullUrl = createMockRequest(null)

    assertThat(client.shouldOverrideUrlLoading(webView, null as WebResourceRequest?)).isFalse()
    assertThat(client.shouldOverrideUrlLoading(webView, requestWithNullUrl)).isFalse()
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

    val client = shadowOf(webView).webViewClient
    val handled = client.shouldOverrideUrlLoading(webView, request)
    assertThat(handled).isTrue()

    val startedIntent = shadowOf(activity).nextStartedActivity
    assertThat(startedIntent).isNotNull()
    assertThat(startedIntent.`package`).isEqualTo("com.google.android.apps.maps")
  }

  /** Verifies that onJsReadyInternal does not evaluate JS when a2uiJson is empty. */
  @Test
  fun onJsReadyInternal_withEmptyPayload_doesNotTriggerUpdate() {
    a2uiView.onJsReadyInternal()
    ShadowLooper.idleMainLooper()

    val lastEvaluatedJs = shadowOf(webView).lastEvaluatedJavascript
    assertThat(lastEvaluatedJs).isNull()
  }
}
