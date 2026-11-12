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

import SwiftUI
import WebKit
import XCTest

@testable import GoogleMapsA2UI

/// Unit tests for `A2UIView` and its internal coordinator.
///
/// Verifies JSON payload serialization, JavaScript injection deduplication,
/// and SwiftUI view hierarchy configuration for data vs text events.
@MainActor
final class A2UIViewTests: XCTestCase {

  /// Tests that the coordinator's injectJSON method correctly preserves complex JSON string
  /// payloads containing special characters, quotes, and newlines into lastInjectedPayload.
  func testCoordinator_InjectJSON_SerializesComplexPayload() throws {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()

    let payload =
      #"[{"createSurface":{"description":"Text with \"double quotes\" and 'single' and \n newline.","surfaceId":"sushi-1"}}]"#

    coordinator.injectJSON(webView, payload: payload)

    let injected = try XCTUnwrap(coordinator.lastInjectedPayload)
    XCTAssertTrue(injected.contains("sushi-1"))
    XCTAssertTrue(injected.contains("double quotes"))
  }

  /// Tests that the coordinator deduplicates subsequent identical JSON payload injections.
  func testCoordinator_InjectJSON_DeduplicatesIdenticalPayload() throws {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()

    let payload = #"[{"surfaceId":"test-dedupe"}]"#
    coordinator.injectJSON(webView, payload: payload)
    let firstInjected = try XCTUnwrap(coordinator.lastInjectedPayload)

    // Second call with same payload
    coordinator.injectJSON(webView, payload: payload)
    XCTAssertEqual(coordinator.lastInjectedPayload, firstInjected)
  }

  /// Tests that initializing `A2UIView` with an A2UI Data event produces a non-empty SwiftUI View body.
  func testA2UIView_BodyStructure_WithDataEvent() {
    let event = ParsedA2AEvent.data(
      #"[{"createSurface":{"surfaceId":"test"}}]"#,
      metadata: ParsedA2AEventMetadata(mimeType: "application/json+a2ui")
    )

    let view = A2UIView(part: event)

    let mirror = Mirror(reflecting: view.body)
    let bodyDesc = String(describing: mirror.children.first?.value ?? "")
    XCTAssertTrue(bodyDesc.contains("A2UIMessageInnerWrapper"))
  }

  /// Tests that initializing `A2UIView` with a Text event safely defaults to an EmptyView.
  func testA2UIView_BodyStructure_WithTextEvent() {
    let event = ParsedA2AEvent.text("Just text")
    let view = A2UIView(part: event)

    let mirror = Mirror(reflecting: view.body)
    let bodyDesc = String(describing: mirror.children.first?.value ?? "")
    XCTAssertTrue(bodyDesc.contains("EmptyView"))
  }

  /// Tests that receiving an onGetDirections action via the iOS bridge triggers onUserAction callback.
  func testCoordinator_UserContentController_OnGetDirections() {
    var receivedAction: String?
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { action in receivedAction = action },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let message = MockScriptMessage(
      name: "iOS",
      body: ["action": "onGetDirections", "data": "{\"placeId\": \"123\"}"]
    )

    coordinator.userContentController(WKUserContentController(), didReceive: message)

    XCTAssertEqual(receivedAction, "{\"placeId\": \"123\"}")
  }

  /// Tests that heightObserver updates dynamic height and fires onRenderComplete once on first resize.
  func testCoordinator_UserContentController_HeightObserver_FiresOnRenderCompleteOnce() {
    var height: CGFloat = 100
    var renderCallCount = 0
    var renderLatency: TimeInterval?
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: { latency in
        renderCallCount += 1
        renderLatency = latency
      }
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let firstMessage = MockScriptMessage(name: "heightObserver", body: CGFloat(250))

    coordinator.userContentController(WKUserContentController(), didReceive: firstMessage)

    XCTAssertEqual(height, 250)
    XCTAssertEqual(renderCallCount, 1)
    XCTAssertNotNil(renderLatency)
    XCTAssertGreaterThanOrEqual(renderLatency ?? -1, 0)

    // Subsequent height delta > 5 updates height without firing a redundant 0.0 callback.
    let secondMessage = MockScriptMessage(name: "heightObserver", body: CGFloat(400))
    coordinator.userContentController(WKUserContentController(), didReceive: secondMessage)

    XCTAssertEqual(height, 400)
    XCTAssertEqual(renderCallCount, 1)
  }

  /// Tests that heightObserver ignores small height changes (<= 5) to prevent layout thrashing.
  func testCoordinator_UserContentController_HeightObserver_SuppressesSmallChanges() {
    var height: CGFloat = 100
    var renderCalled = false
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: { _ in renderCalled = true }
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let message = MockScriptMessage(name: "heightObserver", body: CGFloat(103))

    coordinator.userContentController(WKUserContentController(), didReceive: message)

    XCTAssertEqual(height, 100)
    XCTAssertFalse(renderCalled)
  }

  /// Tests that heightObserver ignores invalid/small heights (<= 50).
  func testCoordinator_UserContentController_HeightObserver_IgnoresSmallHeights() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let message = MockScriptMessage(name: "heightObserver", body: CGFloat(30))

    coordinator.userContentController(WKUserContentController(), didReceive: message)

    XCTAssertEqual(height, 100)
  }

  /// Tests that onJsReady sets isJSReady flag and injects payload.
  func testCoordinator_UserContentController_OnJsReady_SetsReadyAndInjects() {
    var height: CGFloat = 100
    let webView = WKWebView()
    let parent = A2UIMessageRepresentableView(
      payload: #"[{"createSurface":{"surfaceId":"ready-test"}}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let message = MockScriptMessage(
      name: "iOS",
      body: ["action": "onJsReady", "data": ""],
      webView: webView
    )

    XCTAssertFalse(coordinator.isJSReady)
    coordinator.userContentController(WKUserContentController(), didReceive: message)

    XCTAssertTrue(coordinator.isJSReady)
    XCTAssertNotNil(coordinator.lastInjectedPayload)
  }

  /// Tests that injectJSON falls back safely to "[]" when given an empty payload string.
  func testCoordinator_InjectJSON_EmptyPayload_FallsBackSafely() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()

    coordinator.injectJSON(webView, payload: "   ")

    XCTAssertEqual(coordinator.lastInjectedPayload, "[]")
  }

  /// Tests that the coordinator handles JavaScript logging and error messages without crashing.
  func testCoordinator_UserContentController_LogAndErrorMessages() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)

    let logMessage = MockScriptMessage(
      name: "iOS",
      body: ["action": "log", "data": "Test log output"]
    )
    coordinator.userContentController(WKUserContentController(), didReceive: logMessage)

    let errorMessage = MockScriptMessage(
      name: "iOS",
      body: ["action": "error", "data": "Test JS error"]
    )
    coordinator.userContentController(WKUserContentController(), didReceive: errorMessage)
  }

  /// Tests that malformed or unrecognized script messages are handled safely without throwing.
  func testCoordinator_UserContentController_MalformedMessages_HandledGracefully() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)

    // 1. Missing action/data keys
    let missingKeysMessage = MockScriptMessage(
      name: "iOS",
      body: ["invalid": "value"]
    )
    coordinator.userContentController(WKUserContentController(), didReceive: missingKeysMessage)

    // 2. Unknown action string
    let unknownActionMessage = MockScriptMessage(
      name: "iOS",
      body: ["action": "unknownCustomAction", "data": "{}"]
    )
    coordinator.userContentController(WKUserContentController(), didReceive: unknownActionMessage)

    // 3. Height observer with non-numeric body
    let badHeightMessage = MockScriptMessage(
      name: "heightObserver",
      body: "not-a-number"
    )
    coordinator.userContentController(WKUserContentController(), didReceive: badHeightMessage)

    XCTAssertEqual(height, 100)
  }

  /// Tests that external HTTP/HTTPS link clicks trigger navigation cancellation in decidePolicyFor.
  func testCoordinator_DecidePolicyForNavigationAction_ExternalLink_CancelsPolicy() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()

    let url = URL(string: "https://www.google.com")!
    let action = MockNavigationAction(
      navigationType: .linkActivated,
      request: URLRequest(url: url)
    )

    var decidedPolicy: WKNavigationActionPolicy?
    coordinator.webView(webView, decidePolicyFor: action) { policy in
      decidedPolicy = policy
    }

    XCTAssertEqual(decidedPolicy, .cancel)
  }

  /// Tests that non-link navigation actions (e.g. other/reload) are allowed in decidePolicyFor.
  func testCoordinator_DecidePolicyForNavigationAction_OtherNavigation_AllowsPolicy() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()

    let url = URL(string: "https://www.google.com")!
    let action = MockNavigationAction(
      navigationType: .other,
      request: URLRequest(url: url)
    )

    var decidedPolicy: WKNavigationActionPolicy?
    coordinator.webView(webView, decidePolicyFor: action) { policy in
      decidedPolicy = policy
    }

    XCTAssertEqual(decidedPolicy, .allow)
  }

  /// Tests that createWebViewWith returns nil when intercepting window.open popup requests.
  func testCoordinator_CreateWebViewWith_ReturnsNil() {
    var height: CGFloat = 100
    let parent = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = A2UIMessageRepresentableView.Coordinator(parent)
    let webView = WKWebView()
    let config = WKWebViewConfiguration()

    let url = URL(string: "https://maps.google.com")!
    let action = MockNavigationAction(
      navigationType: .linkActivated,
      request: URLRequest(url: url)
    )

    let createdView = coordinator.webView(
      webView,
      createWebViewWith: config,
      for: action,
      windowFeatures: WKWindowFeatures()
    )

    XCTAssertNil(createdView)
  }

  /// Tests that mounting A2UIView with modifiers in a UIHostingController updates cleanly.
  func testA2UIView_UIHostingController_MountsWithModifiersAndUpdatesRootView() {
    let event1 = ParsedA2AEvent.data(
      #"[{"createSurface":{"surfaceId":"mount-test"}}]"#,
      metadata: ParsedA2AEventMetadata(mimeType: "application/json+a2ui")
    )
    let view1 = A2UIView(part: event1)
      .onUserAction { _ in }
      .onRenderComplete { _ in }

    let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 375, height: 667))
    let hostingController = UIHostingController(rootView: AnyView(view1))
    window.rootViewController = hostingController
    window.makeKeyAndVisible()
    hostingController.loadViewIfNeeded()
    hostingController.view.layoutIfNeeded()

    let event2 = ParsedA2AEvent.data(
      #"[{"updateComponents":{"surfaceId":"mount-test","components":[]}}]"#,
      metadata: ParsedA2AEventMetadata(mimeType: "application/json+a2ui")
    )
    let view2 = A2UIView(part: event2)
      .onRenderComplete { _ in }
      .onUserAction { _ in }
    hostingController.rootView = AnyView(view2)
    hostingController.view.layoutIfNeeded()

    XCTAssertNotNil(hostingController.view)
  }

  /// Tests that mounting A2UIView with a Text event renders an EmptyView inside a UIHostingController.
  func testA2UIView_UIHostingController_WithTextEvent_MountsEmptyView() {
    let event = ParsedA2AEvent.text("mount text test")
    let view = A2UIView(part: event)

    let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 375, height: 667))
    let hostingController = UIHostingController(rootView: view)
    window.rootViewController = hostingController
    window.makeKeyAndVisible()
    hostingController.loadViewIfNeeded()
    hostingController.view.layoutIfNeeded()

    XCTAssertNotNil(hostingController.view)
  }

  /// Tests that A2UIMessageRepresentableView creates a configured coordinator instance.
  func testA2UIMessageRepresentableView_MakeCoordinator_InitializesCorrectly() {
    var height: CGFloat = 100
    let view = A2UIMessageRepresentableView(
      payload: #"[{"surfaceId":"test"}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )

    let coordinator = view.makeCoordinator()
    XCTAssertEqual(coordinator.parent.payload, #"[{"surfaceId":"test"}]"#)
    XCTAssertFalse(coordinator.isJSReady)
  }

  /// Tests that configureWebView properly sets up WKWebView properties, delegates, and configuration.
  func testA2UIMessageRepresentableView_ConfigureWebView_InitializesConfigurationAndDelegates() {
    var height: CGFloat = 100
    let view = A2UIMessageRepresentableView(
      payload: #"[{"surfaceId":"test"}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = view.makeCoordinator()
    let webView = view.configureWebView(coordinator: coordinator)

    XCTAssertFalse(webView.isOpaque)
    XCTAssertEqual(webView.backgroundColor, .clear)
    XCTAssertFalse(webView.scrollView.isScrollEnabled)
    XCTAssertTrue(webView.navigationDelegate === coordinator)
    XCTAssertTrue(webView.uiDelegate === coordinator)
    #if DEBUG
      if #available(iOS 16.4, *) {
        XCTAssertTrue(webView.isInspectable)
      }
    #endif
  }

  /// Tests that dismantleUIView unregisters message handlers and clears delegates.
  func testA2UIMessageRepresentableView_DismantleUIView_ClearsDelegates() {
    var height: CGFloat = 100
    let view = A2UIMessageRepresentableView(
      payload: "[]",
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: nil,
      onRenderComplete: nil
    )
    let coordinator = view.makeCoordinator()
    let webView = view.configureWebView(coordinator: coordinator)

    A2UIMessageRepresentableView.dismantleUIView(webView, coordinator: coordinator)

    XCTAssertNil(webView.navigationDelegate)
    XCTAssertNil(webView.uiDelegate)
  }

  /// Tests that updateWebView injects JSON when JS is ready, and skips when not ready.
  func testA2UIMessageRepresentableView_UpdateWebView_InjectsWhenJSReady() {
    var height: CGFloat = 100
    let view = A2UIMessageRepresentableView(
      payload: #"[{"surfaceId":"update-test"}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in },
      onRenderComplete: nil
    )
    let coordinator = view.makeCoordinator()
    let webView = WKWebView()

    // 1. When not ready, updateWebView does nothing
    coordinator.isJSReady = false
    view.updateWebView(webView, coordinator: coordinator)
    XCTAssertNil(coordinator.lastInjectedPayload)

    // 2. When ready, updateWebView injects JSON
    coordinator.isJSReady = true
    view.updateWebView(webView, coordinator: coordinator)
    XCTAssertNotNil(coordinator.lastInjectedPayload)
  }

  /// Tests that updating the representable view refreshes `coordinator.parent` payload and callbacks.
  func testA2UIMessageRepresentableView_UpdateWebView_RefreshesCoordinatorParent() {
    var height: CGFloat = 100
    var firstCallbackCalled = false
    var secondCallbackCalled = false
    let initialView = A2UIMessageRepresentableView(
      payload: #"[{"surfaceId":"initial"}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in firstCallbackCalled = true },
      onRenderComplete: nil
    )
    let coordinator = initialView.makeCoordinator()
    let webView = WKWebView()

    let updatedView = A2UIMessageRepresentableView(
      payload: #"[{"surfaceId":"updated"}]"#,
      dynamicHeight: Binding(get: { height }, set: { height = $0 }),
      onUserAction: { _ in secondCallbackCalled = true },
      onRenderComplete: nil
    )
    updatedView.updateWebView(webView, coordinator: coordinator)

    XCTAssertEqual(coordinator.parent.payload, #"[{"surfaceId":"updated"}]"#)
    coordinator.userContentController(
      WKUserContentController(),
      didReceive: MockScriptMessage(
        name: "iOS", body: ["action": "onGetDirections", "data": "{}"]))
    XCTAssertFalse(firstCallbackCalled)
    XCTAssertTrue(secondCallbackCalled)
  }
}

private class MockNavigationAction: WKNavigationAction {
  private let _navigationType: WKNavigationType
  private let _request: URLRequest

  init(navigationType: WKNavigationType, request: URLRequest) {
    self._navigationType = navigationType
    self._request = request
    super.init()
  }

  override var navigationType: WKNavigationType { _navigationType }
  override var request: URLRequest { _request }
}

private class MockScriptMessage: WKScriptMessage {
  private let _name: String
  private let _body: Any
  private weak var _webView: WKWebView?

  init(name: String, body: Any, webView: WKWebView? = nil) {
    self._name = name
    self._body = body
    self._webView = webView
    super.init()
  }

  override var name: String { _name }
  override var body: Any { _body }
  override var webView: WKWebView? { _webView }
}
