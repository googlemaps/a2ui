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

import XCTest

@testable import GoogleMapsA2UI

/// Unit tests for `A2UIServices`.
///
/// Verifies Google Maps API key configuration and HTML template resolution and caching.
@MainActor
final class A2UIServicesTests: XCTestCase {

  override func setUp() {
    super.setUp()
    A2UIServices.resetForTesting()
  }

  override func tearDown() {
    A2UIServices.resetForTesting()
    super.tearDown()
  }

  /// Tests that `apiKey` defaults to `nil` before initialization.
  func testDefaultState_ApiKeyIsNil() {
    XCTAssertNil(A2UIServices.apiKey)
  }

  /// Tests that providing an API key stores it and injects it into the resolved HTML template.
  func testProvideAPIKey_SetsKeyAndInjectsIntoHtml() throws {
    XCTAssertTrue(A2UIServices.provideAPIKey("AIzaSyTestKey123"))
    XCTAssertEqual(A2UIServices.apiKey, "AIzaSyTestKey123")
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(content.html.contains("AIzaSyTestKey123"))
    XCTAssertFalse(content.html.contains("$GOOGLE_MAPS_API_KEY"))
  }

  /// Tests that blank or whitespace-only keys are rejected without overwriting state.
  func testProvideAPIKey_RejectsEmptyAndWhitespaceKeys() {
    XCTAssertFalse(A2UIServices.provideAPIKey(""))
    XCTAssertFalse(A2UIServices.provideAPIKey("   "))
    XCTAssertNil(A2UIServices.apiKey)
  }

  /// Tests that repeat calls after initialization return false and preserve the first key.
  func testProvideAPIKey_RepeatCallReturnsFalseAndPreservesFirstKey() {
    XCTAssertTrue(A2UIServices.provideAPIKey("FirstKey"))
    XCTAssertFalse(A2UIServices.provideAPIKey("FirstKey"))
    XCTAssertFalse(A2UIServices.provideAPIKey("SecondKey"))
    XCTAssertEqual(A2UIServices.apiKey, "FirstKey")
  }

  /// Tests that missing API key falls back to an empty placeholder without crashing.
  func testGetLocalHTMLContent_WhenApiKeyNil_RemovesPlaceholder() throws {
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertFalse(content.html.contains("$GOOGLE_MAPS_API_KEY"))
  }

  /// Tests that getLocalHTMLContent returns the module bundle's resourceURL as baseURL.
  func testGetLocalHTMLContent_ReturnsModuleBaseURL() throws {
    XCTAssertTrue(A2UIServices.provideAPIKey("TestKey"))
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertEqual(content.baseURL, Bundle.module.resourceURL)
  }

  /// Tests that the resolved HTML template is cached when the API key does not change,
  /// and invalidated when resetForTesting() is called.
  func testGetLocalHTMLContent_CachesResultAndResetsOnResetForTesting() throws {
    XCTAssertTrue(A2UIServices.provideAPIKey("KeyAlpha"))
    let first = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    let second = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertEqual(first.html, second.html)

    A2UIServices.resetForTesting()
    XCTAssertTrue(A2UIServices.provideAPIKey("KeyBeta"))
    let third = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(third.html.contains("KeyBeta"))
    XCTAssertFalse(third.html.contains("KeyAlpha"))
  }

  /// Tests that an API key containing special characters is injected verbatim without breaking HTML template resolution.
  func testProvideAPIKey_SpecialCharacters_InjectsVerbatim() throws {
    XCTAssertTrue(A2UIServices.provideAPIKey("AIzaSyTest-Key_123$!@#"))
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(content.html.contains("AIzaSyTest-Key_123$!@#"))
  }
}
