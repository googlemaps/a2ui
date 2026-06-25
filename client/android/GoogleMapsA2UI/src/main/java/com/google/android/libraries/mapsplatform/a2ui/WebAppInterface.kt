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

import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebView
import org.json.JSONException
import org.json.JSONObject

class WebAppInterface(
    private val webView: WebView,
    private val a2uiView: A2UIView
) {
    private val TAG = "A2UIWebAppInterface"
    var resized = false

    @JavascriptInterface
    fun sendA2uiMessages(jsonMessages: String) {
        Log.d(TAG, "sendA2uiMessages called with: $jsonMessages")
        resized = false
        webView.post {
            val escapedJson = JSONObject.quote(jsonMessages)
            val script = """
            try {
              const shell = document.querySelector('a2ui-shell');
              if (shell) {
                console.log('WebAppInterface: Calling processA2uiMessages');
                shell.processA2uiMessages($escapedJson);
              } else {
                console.error('WebAppInterface: a2ui-shell element not found.');
              }
            } catch (e) {
              console.error('WebAppInterface: Error in evaluateJavascript: ' + e.message);
            }
            """.trimIndent()
            webView.evaluateJavascript(script, ValueCallback { value ->
                Log.d(TAG, "JavaScript evaluation result: $value")
            })
        }
    }

    @JavascriptInterface
    fun onGetDirections(jsonString: String) {
        Log.d(TAG, "onGetDirections: $jsonString")
        a2uiView.onUserAction?.invoke(jsonString)
    }

    @JavascriptInterface
    fun onWebpageResized(height: Int) {
        Log.d(TAG, "onWebpageResized: $height")
        if (!resized) {
            webView.post {
                val layoutParams = webView.layoutParams
                if (layoutParams != null) {
                    val newHeight = (height * webView.resources.displayMetrics.density).toInt()
                    layoutParams.height = newHeight
                    webView.layoutParams = layoutParams
                    resized = true
                    Log.d("A2UIViewDebug", "WebView height updated to: $newHeight")
                    a2uiView.onRenderCompleteInternal()
                } else {
                    Log.e("A2UIViewDebug", "WebView LayoutParams is null.")
                }
            }
        }
    }

    @JavascriptInterface
    fun onJsReady() {
        Log.d(TAG, "onJsReady")
        Handler(Looper.getMainLooper()).post {
            a2uiView.onJsReadyInternal()
        }
    }
}
