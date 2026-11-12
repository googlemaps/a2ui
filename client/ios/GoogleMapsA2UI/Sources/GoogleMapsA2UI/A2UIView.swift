//
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
//

import OSLog
import SwiftUI
import WebKit

/// Protocol implemented by views that accept `A2UIView` modifier callbacks.
public protocol A2UIViewModifiable {}

private struct A2UIOnUserActionKey: EnvironmentKey {
  static let defaultValue: ((String) -> Void)? = nil
}

private struct A2UIOnRenderCompleteKey: EnvironmentKey {
  static let defaultValue: ((TimeInterval) -> Void)? = nil
}

extension EnvironmentValues {
  fileprivate var a2uiOnUserAction: ((String) -> Void)? {
    get { self[A2UIOnUserActionKey.self] }
    set { self[A2UIOnUserActionKey.self] = newValue }
  }

  fileprivate var a2uiOnRenderComplete: ((TimeInterval) -> Void)? {
    get { self[A2UIOnRenderCompleteKey.self] }
    set { self[A2UIOnRenderCompleteKey.self] = newValue }
  }
}

private struct A2UIUserActionModifier: ViewModifier {
  let action: (String) -> Void

  func body(content: Content) -> some View {
    content.environment(\.a2uiOnUserAction, action)
  }
}

private struct A2UIRenderCompleteModifier: ViewModifier {
  let action: (TimeInterval) -> Void

  func body(content: Content) -> some View {
    content.environment(\.a2uiOnRenderComplete, action)
  }
}

extension View where Self: A2UIViewModifiable {
  /// Registers a handler called when the user triggers an action inside the A2UI surface.
  ///
  /// - Parameter action: Closure invoked with the action JSON string.
  public func onUserAction(_ action: @escaping (_ actionJSON: String) -> Void)
    -> some View & A2UIViewModifiable
  {
    modifier(A2UIUserActionModifier(action: action))
  }

  /// Registers a handler called once when the A2UI surface finishes its initial render.
  ///
  /// - Parameter action: Closure invoked with the render latency in seconds (`TimeInterval`).
  public func onRenderComplete(_ action: @escaping (_ latency: TimeInterval) -> Void)
    -> some View & A2UIViewModifiable
  {
    modifier(A2UIRenderCompleteModifier(action: action))
  }
}

/// :nodoc:
extension ModifiedContent: A2UIViewModifiable
where Content: View & A2UIViewModifiable, Modifier: ViewModifier {}

/// Main entry point for rendering GoogleMapsA2UI message parts.
/// Renders the parsed A2UI event using a WKWebView wrapper.
/// The WKWebView is used to securely execute the `a2ui-shell` web component,
/// which interprets the declarative JSON payload and renders interactive maps and UI elements.
public struct A2UIView: View, A2UIViewModifiable {
  @Environment(\.a2uiOnUserAction) private var onUserAction
  @Environment(\.a2uiOnRenderComplete) private var onRenderComplete
  private let part: ParsedA2AEvent

  /// Initializes the `A2UIView`.
  ///
  /// - Parameter part: The parsed A2A event containing the declarative UI payload.
  public init(part: ParsedA2AEvent) {
    self.part = part
  }

  public var body: some View {
    if case .data(let payloadJSON, _) = part {
      A2UIMessageInnerWrapper(
        payload: payloadJSON,
        onUserAction: onUserAction,
        onRenderComplete: onRenderComplete
      )
    } else {
      EmptyView()
    }
  }
}

/// An internal wrapper View that manages the dynamic height state of the WKWebView.
struct A2UIMessageInnerWrapper: View {
  let payload: String
  let onUserAction: ((String) -> Void)?
  let onRenderComplete: ((TimeInterval) -> Void)?

  @State private var height: CGFloat = 100  // Default height

  var body: some View {
    A2UIMessageRepresentableView(
      payload: payload,
      dynamicHeight: $height,
      onUserAction: onUserAction,
      onRenderComplete: onRenderComplete
    )
    .frame(maxWidth: .infinity)
    .frame(height: height)
  }
}

/// Internal UIViewRepresentable view to construct and manage the lifecycle of the WKWebView.
/// This acts as the bridge between SwiftUI and the underlying UIKit/WebKit components.
struct A2UIMessageRepresentableView: UIViewRepresentable {
  private static let logger = Logger(subsystem: "com.google.maps.a2ui", category: "A2UIView")

  let payload: String
  @Binding var dynamicHeight: CGFloat
  let onUserAction: ((String) -> Void)?
  let onRenderComplete: ((TimeInterval) -> Void)?

  /// Creates the WKWebView instance and configures its bridge to the web component.
  /// - Parameter context: The SwiftUI context.
  /// - Returns: A configured WKWebView.
  func makeUIView(context: Context) -> WKWebView {
    configureWebView(coordinator: context.coordinator)
  }

  /// Configures the WKWebView instance with user scripts, bridge message handlers, and local HTML assets.
  /// - Parameter coordinator: The coordinator handling navigation and message callbacks.
  /// - Returns: A configured WKWebView instance.
  func configureWebView(coordinator: Coordinator) -> WKWebView {
    let config = WKWebViewConfiguration()
    let contentController = WKUserContentController()

    // Expose iOS bridge to JS (window.webkit.messageHandlers.iOS)
    // This allows the web component to communicate user interactions (like "get_directions") back to Swift.
    contentController.add(coordinator, name: "iOS")

    // Allows the JS ResizeObserver to notify Swift when the content height changes
    contentController.add(coordinator, name: "heightObserver")

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
      });
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
    #if DEBUG
      if #available(iOS 16.4, *) {
        webView.isInspectable = true
      }
    #endif

    webView.navigationDelegate = coordinator
    webView.uiDelegate = coordinator
    webView.scrollView.isScrollEnabled = false  // Prevent double scrolling inside the chat list

    // Fix for the gray background sometimes seen at the boundaries of WKWebViews.
    // Setting the view and its scroll view to clear ensures external SwiftUI styling looks clean.
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
      Self.logger.error("Failed to load local HTML content from bundle")
    }

    return webView
  }

  /// Updates the WKWebView when SwiftUI state changes.
  /// Refreshes the coordinator's parent reference and injects the latest payload if JS is ready.
  /// - Parameters:
  ///   - uiView: The WKWebView instance to update.
  ///   - context: The SwiftUI context.
  func updateUIView(_ uiView: WKWebView, context: Context) {
    updateWebView(uiView, coordinator: context.coordinator)
  }

  /// Removes registered `WKScriptMessageHandler`s and delegates to break retain cycles on teardown.
  static func dismantleUIView(_ uiView: WKWebView, coordinator: Coordinator) {
    uiView.configuration.userContentController.removeScriptMessageHandler(forName: "iOS")
    uiView.configuration.userContentController.removeScriptMessageHandler(forName: "heightObserver")
    uiView.navigationDelegate = nil
    uiView.uiDelegate = nil
  }

  /// Refreshes the coordinator's parent snapshot and pushes the latest JSON payload when JS is ready.
  /// - Parameters:
  ///   - uiView: The WKWebView instance to update.
  ///   - coordinator: The coordinator tracking the JavaScript ready state.
  func updateWebView(_ uiView: WKWebView, coordinator: Coordinator) {
    coordinator.parent = self
    if coordinator.isJSReady {
      coordinator.injectJSON(uiView, payload: payload)
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
    var startTime: CFAbsoluteTime? = CFAbsoluteTimeGetCurrent()

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

    /// Safely escapes and injects the JSON payload string into the `a2ui-shell` web component.
    /// - Parameters:
    ///   - webView: The web view hosting the component.
    ///   - payload: The UTF-8 JSON string payload to inject.
    func injectJSON(_ webView: WKWebView, payload: String) {
      let trimmed = payload.trimmingCharacters(in: .whitespacesAndNewlines)
      let jsonString = trimmed.isEmpty ? "[]" : payload

      if jsonString == lastInjectedPayload { return }
      lastInjectedPayload = jsonString

      // Use JSONEncoder to safely escape the JSON string as a JavaScript string literal.
      let encodedString: String
      if let encodedData = try? JSONEncoder().encode(jsonString),
        let str = String(data: encodedData, encoding: .utf8)
      {
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
            if let startTime {
              let latency = CFAbsoluteTimeGetCurrent() - startTime
              parent.onRenderComplete?(latency)
              self.startTime = nil
            }
          }
        }
      } else if message.name == "iOS",
        let body = message.body as? [String: Any],
        let action = body["action"] as? String,
        let data = body["data"] as? String
      {
        switch action {
        case "log":
          A2UIMessageRepresentableView.logger.debug("JS LOG: \(data, privacy: .public)")
        case "error":
          A2UIMessageRepresentableView.logger.error("JS ERROR: \(data, privacy: .public)")
        case "onGetDirections":
          parent.onUserAction?(data)
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
