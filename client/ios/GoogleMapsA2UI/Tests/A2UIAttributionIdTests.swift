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

import XCTest

@testable import GoogleMapsA2UI

final class A2UIAttributionIdTests: XCTestCase {

  func testIOSAttributionIdIsGenerated() throws {
    let localContent = try XCTUnwrap(
      A2UIServices.getLocalHTMLContent(), "Failed to load local index.html")

    let htmlString = localContent.html

    XCTAssertTrue(
      htmlString.contains("gmp_web_maui_v0.1.8_atoui"),
      "Expected the generated attribution ID to contain the Web identifier 'gmp_web_maui_v0.1.8_atoui'"
    )
    XCTAssertTrue(
      htmlString.contains("gmp_ios_maui_v0.1.8_atoui"),
      "Expected the generated attribution ID to contain the iOS identifier 'gmp_ios_maui_v0.1.8_atoui'"
    )
    XCTAssertTrue(
      htmlString.contains("gmp_web_maui_v0.1.8_atoui,gmp_ios_maui_v0.1.8_atoui"),
      "Expected the generated attribution ID to contain the combined Web and iOS identifier string 'gmp_web_maui_v0.1.8_atoui,gmp_ios_maui_v0.1.8_atoui'"
    )
  }
}
