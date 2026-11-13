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

import android.content.Context
import android.content.Intent
import android.util.AttributeSet
import android.util.Log
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.net.toUri
import java.io.BufferedReader
import java.io.InputStreamReader

class A2UIView
@JvmOverloads
constructor(context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0) :
  WebView(context, attrs, defStyleAttr) {

  private val A2UI_DEBUG_TAG = "A2UIViewDebug"
  private val A2UI_CONSOLE_TAG = "A2UIViewConsole"
  private val A2UI_ERROR_TAG = "A2UIViewError"
  private val MAPS_HOST = "maps.google.com"
  private val MAPS_PATH = "google.com/maps"
  private val MAPS_PACKAGE = "com.google.android.apps.maps"
  private val HTTP_SCHEME = "http://"
  private val HTTPS_SCHEME = "https://"

  private var indexHtml: String = ""
  var a2uiJson: String = ""
  var metadata: ParsedA2AEventMetadata? = null
  private var startTime: Long? = null
  var onRenderComplete: ((latencyMs: Long, status: String) -> Unit)? = null
  var onUserAction: ((actionJson: String) -> Unit)? = null

  private var isJsReady: Boolean = false
  private var lastInjectedElementCount: Int = 0

  private val webAppInterface = WebAppInterface(this, this)

  init {
    indexHtml = loadIndexHtml(context)
    setupWebView()
  }

  private fun setupWebView() {
    settings.javaScriptEnabled = true
    settings.allowFileAccess = true
    settings.allowContentAccess = true

    addJavascriptInterface(webAppInterface, "Android")

    setWebContentsDebuggingEnabled(true)

    webViewClient =
      object : WebViewClient() {
        override fun shouldOverrideUrlLoading(
          view: WebView?,
          request: WebResourceRequest?,
        ): Boolean {
          val url = request?.url?.toString() ?: return false
          if (url.startsWith(HTTP_SCHEME) || url.startsWith(HTTPS_SCHEME)) {
            val intent = Intent(Intent.ACTION_VIEW, url.toUri())
            if (url.contains(MAPS_HOST) || url.contains(MAPS_PATH)) {
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
      val inputStream = context.assets.open("index.html")
      val reader = BufferedReader(InputStreamReader(inputStream))
      reader.readText()
    } catch (e: Exception) {
      Log.e(A2UI_ERROR_TAG, "Failed to load index.html from assets: ${e.message}")
      ""
    }
  }

  @JvmOverloads
  fun render(json: String, startTimeMs: Long? = null, metadata: ParsedA2AEventMetadata? = null) {
    Log.d(A2UI_DEBUG_TAG, "Rendering A2UI JSON")
    this.startTime = startTimeMs ?: System.currentTimeMillis()
    this.a2uiJson = json
    this.metadata = metadata
    this.isJsReady = false
    this.lastInjectedElementCount = 0
    val apiKey = A2UIServices.apiKey
    val htmlToLoad = indexHtml.replace("\$GOOGLE_MAPS_API_KEY", apiKey)
    loadDataWithBaseURL("file:///android_asset/", htmlToLoad, "text/html", "UTF-8", null)
  }

  @JvmOverloads
  fun updateA2uiJson(newJson: String, newMetadata: ParsedA2AEventMetadata? = this.metadata) {
    this.a2uiJson = newJson
    this.metadata = newMetadata
    if (!isJsReady) return

    newMetadata?.contentTokens?.let { addContentTokens(it) }

    webAppInterface.resized = false

    post {
      try {
        val escapedJson = org.json.JSONObject.quote(newJson)
        val script =
          """
                try {
                  const shell = document.querySelector('a2ui-shell');
                  if (shell) {
                    // Send the raw JSON payload to the frontend.
                    // The frontend (AppMobile.tsx) now handles hallucination fixes and path resolution internally.
                    shell.processA2uiMessages(${escapedJson});
                  } else {
                    console.error('a2ui-shell not found');
                  }
                } catch (e) {
                  console.error('Error in evaluateJavascript: ' + e);
                }
                """
            .trimIndent()
        evaluateJavascript(script, null)
      } catch (e: Exception) {
        Log.e(A2UI_ERROR_TAG, "Error processing a2ui update", e)
      }
    }
  }

  fun addContentTokens(tokensJson: String) {
    if (tokensJson.isEmpty() || !isJsReady) return

    post {
      try {
        val script =
          """
                try {
                  const shell = document.querySelector('a2ui-shell');
                  if (shell) {
                    shell.addContentTokens($tokensJson);
                  } else {
                    console.error('a2ui-shell not found');
                  }
                } catch (e) {
                  console.error('Error registering content tokens: ' + e);
                }
                """
            .trimIndent()
        evaluateJavascript(script, null)
      } catch (e: Exception) {
        Log.e(A2UI_ERROR_TAG, "Error registering content tokens", e)
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
      val latency = System.currentTimeMillis() - it
      onRenderComplete?.invoke(latency, "A2UI Render Complete")
      startTime = null
    }
  }
}
