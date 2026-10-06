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

  override func tearDown() {
    super.tearDown()
    A2UIServices.provideApiKey("")
  }

  /// Tests that providing an API key injects the key into the resolved HTML content template.
  func testProvideApiKey_SetsKeyAndInjectsIntoHtml() throws {
    A2UIServices.provideApiKey("AIzaSyTestKey123")
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(content.html.contains("AIzaSyTestKey123"))
    XCTAssertFalse(content.html.contains("$GOOGLE_MAPS_API_KEY"))
  }

  /// Tests that providing an empty API key clears the placeholder without crashing.
  func testProvideApiKey_SetsEmptyKey_RemovesPlaceholder() throws {
    A2UIServices.provideApiKey("")
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertFalse(content.html.contains("$GOOGLE_MAPS_API_KEY"))
  }

  /// Tests that getLocalHTMLContent returns the module bundle's resourceURL as baseURL.
  func testGetLocalHTMLContent_ReturnsModuleBaseURL() throws {
    A2UIServices.provideApiKey("TestKey")
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertEqual(content.baseURL, Bundle.module.resourceURL)
  }

  /// Tests that the resolved HTML template is cached when the API key does not change,
  /// and invalidated/recalculated when a new key is provided.
  func testGetLocalHTMLContent_CachesResultWhenKeyUnchanged() throws {
    A2UIServices.provideApiKey("KeyAlpha")
    let first = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    let second = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertEqual(first.html, second.html)

    A2UIServices.provideApiKey("KeyBeta")
    let third = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(third.html.contains("KeyBeta"))
    XCTAssertFalse(third.html.contains("KeyAlpha"))
  }

  /// Tests that an API key containing special characters is injected verbatim without breaking HTML template resolution.
  func testProvideApiKey_SpecialCharacters_InjectsVerbatim() throws {
    A2UIServices.provideApiKey("AIzaSyTest-Key_123$!@#")
    let content = try XCTUnwrap(A2UIServices.getLocalHTMLContent())
    XCTAssertTrue(content.html.contains("AIzaSyTest-Key_123$!@#"))
  }
}
