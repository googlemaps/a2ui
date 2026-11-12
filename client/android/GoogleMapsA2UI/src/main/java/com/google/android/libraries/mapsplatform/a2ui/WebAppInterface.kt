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
import androidx.annotation.RestrictTo

@RestrictTo(RestrictTo.Scope.LIBRARY)
internal class WebAppInterface(private val a2uiView: A2UIView) {
  private val mainHandler = Handler(Looper.getMainLooper())
  internal var resized = false

  @JavascriptInterface
  fun onGetDirections(jsonString: String) {
    Log.d(TAG, "onGetDirections: $jsonString")
    mainHandler.post { a2uiView.onUserActionInternal(jsonString) }
  }

  @JavascriptInterface
  fun onWebpageResized(height: Int) {
    Log.d(TAG, "onWebpageResized: $height")
    mainHandler.post {
      if (a2uiView.onWebpageResizedInternal(height) && !resized) {
        resized = true
        a2uiView.onRenderCompleteInternal()
      }
    }
  }

  @JavascriptInterface
  fun onJsReady() {
    Log.d(TAG, "onJsReady")
    mainHandler.post { a2uiView.onJsReadyInternal() }
  }

  private companion object {
    const val TAG = "A2UIWebAppInterface"
  }
}
