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

import Foundation
import OSLog

/// Global services and configuration for the A2UI SDK.
/// Declared as a case-less enum to prevent instantiation.
/// It primarily holds the Google Maps API Key required to render the maps inside the WKWebView,
/// and caches the resolved HTML template to avoid redundant disk reads and string replacements.
public enum A2UIServices {
  private static let logger = Logger(subsystem: "com.google.maps.a2ui", category: "Configuration")
  /// The configured Google Maps API key, or `nil` if `provideAPIKey(_:)` has not been called yet.
  @MainActor public private(set) static var apiKey: String?
  @MainActor private static var cachedContent: String?
  @MainActor private static var cachedForApiKey: String?

  /// Provides the Google Maps API key to be used by the A2UI SDK.
  ///
  /// Must be called on the main actor with a non-empty key before rendering `A2UIView`.
  /// Subsequent calls after initialization are ignored and return `false`.
  ///
  /// - Parameter apiKey: The Google Maps API key string.
  /// - Returns: `true` if the key was accepted; `false` if blank or already initialized.
  @discardableResult
  @MainActor
  public static func provideAPIKey(_ apiKey: String) -> Bool {
    if apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      logger.error("A2UIServices.provideAPIKey(_:) requires a non-empty API key.")
      return false
    }
    if self.apiKey != nil {
      logger.error("A2UIServices.provideAPIKey(_:) should be called at most once.")
      return false
    }
    self.apiKey = apiKey
    self.cachedContent = nil
    self.cachedForApiKey = nil
    return true
  }

  @MainActor
  internal static func resetForTesting() {
    self.apiKey = nil
    self.cachedContent = nil
    self.cachedForApiKey = nil
  }

  /// Reads the local HTML template from the bundle and injects the Maps API key.
  /// The result is cached internally, so it avoids redundant file system reads.
  ///
  /// Note: This method is not thread-safe and should only be called from the main thread.
  ///
  /// - Returns: A tuple containing the HTML string and the base URL, or `nil` on failure.
  @MainActor
  static func getLocalHTMLContent() -> (html: String, baseURL: URL?)? {
    assert(
      Thread.isMainThread, "A2UIServices.getLocalHTMLContent() must be called from the main thread."
    )
    if self.apiKey == nil {
      logger.error("A2UIServices.provideAPIKey(_:) was not called before rendering A2UIView.")
    }
    let currentKey = self.apiKey ?? ""
    // Return the cached HTML if we've already resolved it for the current API key
    if let cached = self.cachedContent, self.cachedForApiKey == currentKey {
      return (html: cached, baseURL: Bundle.module.resourceURL)
    }

    guard let templateUrl = Bundle.module.url(forResource: "index", withExtension: "html") else {
      logger.error("Failed to find index.html in GoogleMapsA2UI module bundle")
      return nil
    }

    guard let templateContent = try? String(contentsOf: templateUrl, encoding: .utf8) else {
      logger.error("Failed to read local index.html content")
      return nil
    }

    // Inject the API key directly into the HTML string.
    // This allows the Maps JavaScript API inside the web component to authenticate successfully.
    let resolvedHtml = templateContent.replacingOccurrences(
      of: "$GOOGLE_MAPS_API_KEY",
      with: currentKey
    )

    self.cachedContent = resolvedHtml
    self.cachedForApiKey = currentKey

    return (html: resolvedHtml, baseURL: Bundle.module.resourceURL)
  }
}
