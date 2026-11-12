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
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.net.Uri
import android.util.AttributeSet
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.annotation.MainThread
import androidx.annotation.VisibleForTesting
import java.io.BufferedReader
import java.io.InputStreamReader
import org.json.JSONObject

/**
 * Android View container that renders A2UI v0.9 JSON payloads using an encapsulated [WebView].
 *
 * Call [A2UIServices.provideApiKey] before calling [render].
 */
class A2UIView
@JvmOverloads
constructor(context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0) :
  FrameLayout(context, attrs, defStyleAttr) {

  /** Listener invoked once when initial A2UI rendering completes. */
  fun interface OnRenderCompleteListener {
    fun onRenderComplete(latencyMs: Long)
  }

  /** Listener invoked when the user triggers an action inside the A2UI surface. */
  fun interface OnUserActionListener {
    fun onUserAction(actionJson: String)
  }

  private val webView: WebView = WebView(context)
  private var indexHtml: String = ""
  private var a2uiJson: String = ""
  private var startTime: Long? = null
  private var onRenderCompleteListener: OnRenderCompleteListener? = null
  private var onUserActionListener: OnUserActionListener? = null

  private var isJsReady: Boolean = false

  @VisibleForTesting internal var clock: () -> Long = System::currentTimeMillis

  private val webAppInterface = WebAppInterface(this)

  init {
    indexHtml = loadIndexHtml(context)
    setupWebView()
    addView(webView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
  }

  /** Registers a listener to be notified when initial rendering completes. */
  @MainThread
  fun setOnRenderCompleteListener(listener: OnRenderCompleteListener?) {
    onRenderCompleteListener = listener
  }

  /** Returns the currently registered [OnRenderCompleteListener], if any. */
  @MainThread
  fun getOnRenderCompleteListener(): OnRenderCompleteListener? = onRenderCompleteListener

  /** Registers a listener to be notified of user actions emitted by the rendered UI. */
  @MainThread
  fun setOnUserActionListener(listener: OnUserActionListener?) {
    onUserActionListener = listener
  }

  /** Returns the currently registered [OnUserActionListener], if any. */
  @MainThread fun getOnUserActionListener(): OnUserActionListener? = onUserActionListener

  private fun setupWebView() {
    webView.settings.javaScriptEnabled = true
    webView.settings.allowFileAccess = true
    webView.settings.allowContentAccess = true
    webView.settings.allowFileAccessFromFileURLs = true
    webView.settings.allowUniversalAccessFromFileURLs = true

    webView.addJavascriptInterface(webAppInterface, "Android")

    val isDebuggable =
      ((context.applicationInfo?.flags ?: 0) and ApplicationInfo.FLAG_DEBUGGABLE) != 0
    if (isDebuggable) {
      WebView.setWebContentsDebuggingEnabled(true)
    }

    webView.webChromeClient =
      object : WebChromeClient() {
        override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
          if (consoleMessage != null) {
            val message =
              "${consoleMessage.message()} (${consoleMessage.sourceId()}:${consoleMessage.lineNumber()})"
            when (consoleMessage.messageLevel()) {
              ConsoleMessage.MessageLevel.ERROR -> Log.e(A2UI_CONSOLE_TAG, message)
              ConsoleMessage.MessageLevel.WARNING -> Log.w(A2UI_CONSOLE_TAG, message)
              else -> Log.d(A2UI_CONSOLE_TAG, message)
            }
          }
          return true
        }
      }

    webView.webViewClient =
      object : WebViewClient() {
        override fun shouldOverrideUrlLoading(
          view: WebView?,
          request: WebResourceRequest?,
        ): Boolean {
          val url = request?.url?.toString() ?: return false
          if (url.startsWith(HTTP_SCHEME) || url.startsWith(HTTPS_SCHEME)) {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            if (context !is Activity) {
              intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            if (MAPS_HOST in url || MAPS_PATH in url) {
              intent.setPackage(MAPS_PACKAGE)
              if (intent.resolveActivity(context.packageManager) == null) {
                intent.setPackage(null)
              }
            }
            context.startActivity(intent)
            return true
          }
          return super.shouldOverrideUrlLoading(view, request)
        }

        override fun onReceivedError(
          view: WebView?,
          request: WebResourceRequest?,
          error: WebResourceError?,
        ) {
          if (request != null && error != null) {
            super.onReceivedError(view, request, error)
          }
          Log.e(
            A2UI_ERROR_TAG,
            "Error loading WebView: ${error?.description}, URL: ${request?.url}",
          )
        }
      }
  }

  private fun loadIndexHtml(context: Context): String {
    return try {
      context.assets.open("index.html").use { inputStream ->
        BufferedReader(InputStreamReader(inputStream)).use { it.readText() }
      }
    } catch (e: Exception) {
      Log.e(A2UI_ERROR_TAG, "Failed to load index.html from assets: ${e.message}")
      ""
    }
  }

  /**
   * Loads the embedded web bundle and renders [json] (an A2UI v0.9 JSON array or object string).
   *
   * @throws IllegalStateException if [A2UIServices.provideApiKey] has not been called.
   */
  @MainThread
  fun render(json: String) {
    val apiKey =
      checkNotNull(A2UIServices.apiKey) {
        "A2UIServices.provideApiKey(...) must be called before calling A2UIView.render()."
      }
    Log.d(A2UI_DEBUG_TAG, "Rendering A2UI JSON")
    this.startTime = clock()
    this.a2uiJson = json
    this.isJsReady = false
    this.webAppInterface.resized = false
    val htmlToLoad = indexHtml.replace("\$GOOGLE_MAPS_API_KEY", apiKey)
    webView.loadDataWithBaseURL("file:///android_asset/", htmlToLoad, "text/html", "UTF-8", null)
  }

  /**
   * Pushes updated A2UI JSON into the mounted web shell without reloading the underlying [WebView].
   */
  @MainThread
  fun updateA2uiJson(newJson: String) {
    this.a2uiJson = newJson
    if (!isJsReady) return

    webAppInterface.resized = false

    webView.post {
      try {
        val escapedJson = JSONObject.quote(newJson)
        val script =
          """
                try {
                  const shell = document.querySelector('a2ui-shell');
                  if (shell) {
                    // Send the raw JSON payload to the frontend.
                    // The frontend (core-shell.ts) handles key normalization and path resolution internally.
                    shell.processA2uiMessages(${escapedJson});
                  } else {
                    console.error('a2ui-shell not found');
                  }
                } catch (e) {
                  console.error('Error in evaluateJavascript: ' + e);
                }
                """
            .trimIndent()
        webView.evaluateJavascript(script, null)
      } catch (e: Exception) {
        Log.e(A2UI_ERROR_TAG, "Error processing a2ui update", e)
      }
    }
  }

  internal fun onJsReadyInternal() {
    Log.d(A2UI_DEBUG_TAG, "a2ui-shell is fully ready!")
    isJsReady = true
    if (a2uiJson.isNotEmpty()) {
      updateA2uiJson(a2uiJson)
    }
  }

  internal fun onRenderCompleteInternal() {
    startTime?.let {
      val latency = clock() - it
      onRenderCompleteListener?.onRenderComplete(latency)
      startTime = null
    }
  }

  internal fun onUserActionInternal(actionJson: String) {
    onUserActionListener?.onUserAction(actionJson)
  }

  internal fun onWebpageResizedInternal(height: Int): Boolean {
    val lp = layoutParams
    if (lp == null) {
      Log.e(A2UI_DEBUG_TAG, "A2UIView LayoutParams is null.")
      return false
    }
    val newHeight = (height * resources.displayMetrics.density).toInt()
    if (lp.height != newHeight) {
      lp.height = newHeight
      layoutParams = lp
      Log.d(A2UI_DEBUG_TAG, "A2UIView height updated to: $newHeight")
    }
    return true
  }

  private companion object {
    const val A2UI_DEBUG_TAG = "A2UIViewDebug"
    const val A2UI_CONSOLE_TAG = "A2UIViewConsole"
    const val A2UI_ERROR_TAG = "A2UIViewError"
    const val MAPS_HOST = "maps.google.com"
    const val MAPS_PATH = "google.com/maps"
    const val MAPS_PACKAGE = "com.google.android.apps.maps"
    const val HTTP_SCHEME = "http://"
    const val HTTPS_SCHEME = "https://"
  }
}
