//
// Copyright 2026 Google Inc.
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
//

import SwiftUI
import WebKit

/// Main entry point for rendering GoogleMapsA2UI message parts.
/// Renders the parsed A2UI event using a WKWebView wrapper.
/// The WKWebView is used to securely execute the `a2ui-shell` web component,
/// which interprets the declarative JSON payload and renders interactive maps and UI elements.
public struct A2UIView: View {
  private let part: ParsedA2AEvent
  private let id: String
  private let onUserAction: (String) -> Void
  private let onRenderComplete: ((String, Double, String) -> Void)?

  /// Initializes the A2UIView.
  /// - Parameters:
  ///   - part: The parsed A2A event containing the declarative UI payload.
  ///   - id: A unique identifier for this view or web component instance.
  ///   - onUserAction: Callback invoked when the user interacts with the UI (e.g., clicks a button).
  ///   - onRenderComplete: Optional callback invoked when rendering is complete.
  public init(
    part: ParsedA2AEvent,
    id: String,
    onUserAction: @escaping (String) -> Void,
    onRenderComplete: ((String, Double, String) -> Void)? = nil
  ) {
    self.part = part
    self.id = id
    self.onUserAction = onUserAction
    self.onRenderComplete = onRenderComplete
  }

  public var body: some View {
    if case let .data(payloadData, _) = part {
      A2UIMessageInnerWrapper(
        webViewID: id,
        payload: payloadData,
        onUserAction: onUserAction,
        onRenderComplete: onRenderComplete
      )
    } else {
      EmptyView()
    }
  }
}


/// An internal wrapper View that manages the dynamic height state of the WKWebView
/// and applies standard styling like shadows and rounded corners to the message container.
struct A2UIMessageInnerWrapper: View {
  let webViewID: String
  let payload: Any
  let onUserAction: (String) -> Void
  let onRenderComplete: ((String, Double, String) -> Void)?

  @State private var height: CGFloat = 100 // Default height

  var body: some View {
    A2UIMessageRepresentableView(
      webViewID: webViewID,
      payload: payload,
      dynamicHeight: $height,
      onUserAction: onUserAction,
      onRenderComplete: onRenderComplete
    )
    .frame(maxWidth: .infinity)
    .frame(height: height)
    .clipShape(RoundedRectangle(cornerRadius: 16))
    .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: 2)
  }
}

/// Internal UIViewRepresentable view to construct and manage the lifecycle of the WKWebView.
/// This acts as the bridge between SwiftUI and the underlying UIKit/WebKit components.
struct A2UIMessageRepresentableView: UIViewRepresentable {
  let webViewID: String
  let payload: Any
  @Binding var dynamicHeight: CGFloat
  let onUserAction: (String) -> Void
  let onRenderComplete: ((String, Double, String) -> Void)?
  
  /// Creates the WKWebView instance and configures its bridge to the web component.
  /// - Parameter context: The SwiftUI context.
  /// - Returns: A configured WKWebView.
  func makeUIView(context: Context) -> WKWebView {
    let config = WKWebViewConfiguration()
    let contentController = WKUserContentController()

    // Expose iOS bridge to JS (window.webkit.messageHandlers.iOS)
    // This allows the web component to communicate user interactions (like "get_directions") back to Swift.
    contentController.add(context.coordinator, name: "iOS")
    
    // Allows the JS ResizeObserver to notify Swift when the content height changes
    contentController.add(context.coordinator, name: "heightObserver")

    // Inject a script to intercept console.log and console.error output from the WKWebView.
    // This forwards JS logs to the native bridge, making it much easier to debug the web component in Xcode.
    let consoleScriptSource = """
      const origLog = console.log;
      console.log = function() {
          origLog.apply(console, arguments);
          var msg = Array.from(arguments).map(a => String(a)).join(' ');
          window.webkit.messageHandlers.iOS.postMessage({action: 'log', data: msg});
      };
      const origError = console.error;
      console.error = function() {
          origError.apply(console, arguments);
          var msg = Array.from(arguments).map(a => String(a)).join(' ');
          window.webkit.messageHandlers.iOS.postMessage({action: 'error', data: msg});
      };
      window.addEventListener('error', function(e) {
          window.webkit.messageHandlers.iOS.postMessage({action: 'error', data: 'Global Error: ' + e.message + ' at line ' + e.lineno});
      """
    let consoleScript = WKUserScript(
      source: consoleScriptSource, injectionTime: .atDocumentStart, forMainFrameOnly: true)
    contentController.addUserScript(consoleScript)

    config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
    config.setValue(true, forKey: "allowUniversalAccessFromFileURLs")
    config.userContentController = contentController

    // Enable HTML5 Fullscreen API
    if #available(iOS 16.4, *) {
      config.preferences.isElementFullscreenEnabled = true
    }

    let webView = WKWebView(frame: UIScreen.main.bounds, configuration: config)
    if #available(iOS 16.4, *) {
      webView.isInspectable = true
    }

    webView.navigationDelegate = context.coordinator
    webView.uiDelegate = context.coordinator
    webView.scrollView.isScrollEnabled = false  // Prevent double scrolling inside the chat list
    
    // Fix for the gray background sometimes seen at the boundaries of WKWebViews.
    // Setting the view and its scroll view to clear ensures our SwiftUI styling (shadows/corners) looks correct.
    webView.isOpaque = false
    webView.backgroundColor = .clear
    webView.scrollView.backgroundColor = .clear
    if #available(iOS 11.0, *) {
      webView.scrollView.contentInsetAdjustmentBehavior = .never
    }

    // Load local HTML resource content which contains the A2UI web components.
    if let localContent = A2UIServices.getLocalHTMLContent() {
      webView.loadHTMLString(localContent.html, baseURL: localContent.baseURL)
    } else {
      print("ERROR: Failed to load local HTML content from bundle")
    }

    return webView
  }

  /// Updates the WKWebView when SwiftUI state changes.
  /// Injects the latest payload if the JavaScript context is ready.
  /// - Parameters:
  ///   - uiView: The WKWebView instance to update.
  ///   - context: The SwiftUI context.
  func updateUIView(_ uiView: WKWebView, context: Context) {
    // If the view updates and JS is ready, push the JSON
    if context.coordinator.isJSReady {
      context.coordinator.injectJSON(uiView, payload: payload)
    }
  }

  /// Creates the coordinator that delegates WKWebView and JavaScript message handling.
  /// - Returns: A new Coordinator instance.
  func makeCoordinator() -> Coordinator {
    Coordinator(self)
  }

  class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
    var parent: A2UIMessageRepresentableView
    var isJSReady = false
    var lastInjectedPayload: String?

    /// Initializes the coordinator with a reference to its parent view.
    /// - Parameter parent: The parent A2UIMessageRepresentableView.
    init(_ parent: A2UIMessageRepresentableView) {
      self.parent = parent
    }

    /// Intercepts navigation actions to handle external links.
    /// - Parameters:
    ///   - webView: The web view invoking the delegate method.
    ///   - navigationAction: Descriptive information about the action triggering the navigation request.
    ///   - decisionHandler: The closure to call to allow or cancel the navigation.
    func webView(
      _ webView: WKWebView,
      decidePolicyFor navigationAction: WKNavigationAction,
      decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
      if navigationAction.navigationType == .linkActivated, let url = navigationAction.request.url {
        if let scheme = url.scheme, ["http", "https"].contains(scheme.lowercased()) {
          UIApplication.shared.open(url)
          decisionHandler(.cancel)
          return
        }
      }
      decisionHandler(.allow)
    }

    /// Handles requests to open a new window.
    /// - Parameters:
    ///   - webView: The web view invoking the delegate method.
    ///   - configuration: The configuration to use when creating the new web view.
    ///   - navigationAction: The navigation action causing the new web view to be created.
    ///   - windowFeatures: Window features requested by the webpage.
    /// - Returns: A new web view, or `nil` if the request is handled natively.
    func webView(
      _ webView: WKWebView,
      createWebViewWith configuration: WKWebViewConfiguration,
      for navigationAction: WKNavigationAction,
      windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
      if let url = navigationAction.request.url {
        UIApplication.shared.open(url)
      }
      return nil
    }

    /// Safely serializes and injects the JSON payload into the `a2ui-shell` web component.
    /// - Parameters:
    ///   - webView: The web view hosting the component.
    ///   - payload: The dictionary payload to serialize and inject.
    func injectJSON(_ webView: WKWebView, payload: Any) {
      // Use JSONSerialization to safely escape the native Swift object for inclusion in JavaScript.
      let jsonString: String
      if let jsonData = try? JSONSerialization.data(withJSONObject: payload, options: []),
         let str = String(data: jsonData, encoding: .utf8) {
        jsonString = str
      } else {
        jsonString = "[]"
      }

      if jsonString == lastInjectedPayload { return }
      lastInjectedPayload = jsonString

      // Use https://developer.apple.com/documentation/foundation/jsonencoder to safely escape
      // the JSON string as a JavaScript string literal.
      let encodedString: String
      if let encodedData = try? JSONEncoder().encode(jsonString),
         let str = String(data: encodedData, encoding: .utf8) {
        encodedString = str
      } else {
        encodedString = "\"[]\""
      }

      let script = """
            try {
                const shell = document.querySelector('a2ui-shell');
                if (shell) {
                    console.log('iOS Native Bridge: Calling processA2uiMessages');
                    shell.processA2uiMessages(\(encodedString));
                } else {
                    console.error('iOS Native Bridge: a2ui-shell not found');
                }
            } catch (e) {
                console.error('iOS WebKit Injection Error: ' + e.message);
            }
        """
      webView.evaluateJavaScript(script)
    }

    /// Receives messages sent from JavaScript via the `window.webkit.messageHandlers` bridge.
    /// Handles logging, errors, height observation, and custom user actions.
    /// - Parameters:
    ///   - userContentController: The user content controller invoking the delegate method.
    ///   - message: The message received from the webpage.
    func userContentController(
      _ userContentController: WKUserContentController,
      didReceive message: WKScriptMessage
    ) {
      if message.name == "heightObserver", let newHeight = message.body as? CGFloat {
        if newHeight > 50 {
          let targetHeight = newHeight
          // Only update if difference > 5 to prevent infinite SwiftUI layout loops
          if abs(parent.dynamicHeight - targetHeight) > 5 {
            parent.dynamicHeight = targetHeight
            parent.onRenderComplete?(parent.webViewID, 0.0, "success")
          }
        }
      } else if message.name == "iOS",
        let body = message.body as? [String: Any],
        let action = body["action"] as? String,
        let data = body["data"] as? String
      {
        switch action {
        case "log":
          print("JS LOG: \(data)")
        case "error":
          print("JS ERROR: \(data)")
        case "onGetDirections":
          parent.onUserAction(data)
        case "onJsReady":
          isJSReady = true
          if let webView = message.webView {
            injectJSON(webView, payload: parent.payload)
          }
        default:
          break
        }
      }
    }
  }
}