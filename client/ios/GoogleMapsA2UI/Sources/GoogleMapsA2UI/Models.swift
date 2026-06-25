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

import Foundation

/// Metadata associated with a message part.
public struct ParsedA2AEventMetadata {
  public let mimeType: String?

  /// Initializes the metadata.
  ///
  /// - Parameter mimeType: The optional MIME type of the payload.
  public init(mimeType: String? = nil) {
    self.mimeType = mimeType
  }
}

/// Represents the parsed output chunk extracted from the raw server JSON.
public enum ParsedA2AEvent {
  /// A conversational text block.
  case text(String)

  /// A structured data payload to be fed into A2UIView.
  /// When `metadata?.mimeType` is `"application/json+a2ui"`, the payload is guaranteed
  /// to be an Array containing one or more A2UI JSON components (e.g., `[[String: Any]]`),
  /// ensuring a consistent structure for downstream UI rendering.
  case data(Any, metadata: ParsedA2AEventMetadata? = nil)
}
