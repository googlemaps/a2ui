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

/// Errors that can occur during A2UI response parsing.
public enum A2AParserError: Error {
  /// The raw JSON response lacks a recognized message parts structure.
  case invalidPayloadStructure
  /// The provided dictionary cannot be serialized as valid JSON.
  case invalidJSONFormat
}

/// Utility parser to process server JSON responses.
/// Declared as a case-less enum to prevent instantiation.
public enum A2AResponseParser {
  private static let a2uiJsonMimeType = "application/json+a2ui"
  private static let a2uiJsonTagOpen = "<a2ui-json>"
  private static let a2uiJsonTagClose = "</a2ui-json>"

  /// Parses a raw server response dictionary into a flat list of `ParsedA2AEvent`s.
  ///
  /// The parser checks multiple possible JSON paths (`parts`, `content.parts`, `status.message.parts`) 
  /// to support varying response structures from different server backends (e.g. standalone JSON-RPC vs. ADK Web Server).
  ///
  /// Note: Any extracted A2UI JSON payloads (mime type `application/json+a2ui`) will always be batched 
  /// and returned as an array (`[Any]`) inside `ParsedA2AEvent.data`, providing a consistent format.
  ///
  /// - Parameter rawJSON: The raw JSON dictionary received from the server.
  /// - Returns: An array of `ParsedA2AEvent` objects extracted from the payload.
  /// - Throws: `A2AParserError.invalidJSONFormat` if the input is not valid JSON, or `A2AParserError.invalidPayloadStructure` if the parts array cannot be found.
  public static func parse(_ rawJSON: [String: Any]) throws -> [ParsedA2AEvent] {
    guard JSONSerialization.isValidJSONObject(rawJSON) else {
      throw A2AParserError.invalidJSONFormat
    }

    let partsArray: [[String: Any]]?
    if let parts = rawJSON["parts"] as? [[String: Any]] {
      partsArray = parts
    } else if let content = rawJSON["content"] as? [String: Any],
              let parts = content["parts"] as? [[String: Any]] {
      partsArray = parts
    } else if let status = rawJSON["status"] as? [String: Any],
              let message = status["message"] as? [String: Any],
              let parts = message["parts"] as? [[String: Any]] {
      partsArray = parts
    } else {
      partsArray = nil
    }

    guard let parts = partsArray else {
      throw A2AParserError.invalidPayloadStructure
    }

    var sdkParts: [ParsedA2AEvent] = []
    var a2uiPayloads: [Any] = []

    // flushA2UI() batches consecutive A2UI JSON payloads together into a single ParsedA2AEvent. 
    func flushA2UI() {
      if !a2uiPayloads.isEmpty {
        let event = ParsedA2AEvent.data(
          a2uiPayloads,
          metadata: ParsedA2AEventMetadata(mimeType: a2uiJsonMimeType)
        )
        sdkParts.append(event)
        a2uiPayloads.removeAll()
      }
    }

    for part in parts {
      if let textPart = part["text"] as? String {
        flushA2UI()
        let subEvents = splitTextParts(textPart)
        sdkParts.append(contentsOf: subEvents)
      } else if let dataPayload = part["data"] as? [String: Any] {
        let metadata = part["metadata"] as? [String: Any]
        let mimeType = part["mimeType"] as? String ?? metadata?["mimeType"] as? String
        let resolvedMimeType = mimeType
          ?? (isA2UIPayload(dataPayload) ? a2uiJsonMimeType : nil)

        if resolvedMimeType == a2uiJsonMimeType {
          a2uiPayloads.append(dataPayload)
        } else {
          flushA2UI()
          let event = ParsedA2AEvent.data(
            dataPayload,
            metadata: ParsedA2AEventMetadata(mimeType: resolvedMimeType)
          )
          sdkParts.append(event)
        }
      }
    }

    flushA2UI()

    return sdkParts
  }

  private static let a2uiKeys: Set<String> = [
    "createSurface", "updateComponents", "updateDataModel",
    "beginRendering", "surfaceUpdate", "dataModelUpdate"
  ]

  /// Checks if a given dictionary represents an A2UI payload.
  ///
  /// - Parameter dict: The dictionary to check.
  /// - Returns: `true` if the dictionary contains recognizable A2UI keys; otherwise, `false`.
  private static func isA2UIPayload(_ dict: [String: Any]) -> Bool {
    return dict.keys.contains { a2uiKeys.contains($0) }
  }

  /// Parses a JSON string into a dictionary or array.
  ///
  /// - Parameter jsonStr: The JSON string to parse.
  /// - Returns: The parsed JSON object, or `nil` if parsing fails.
  private static func parseJSON(_ jsonStr: String) -> Any? {
    guard let data = jsonStr.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data, options: [])
  }

  /// Splits a text part containing embedded `<a2ui-json>` tags into separate events.
  ///
  /// - Parameter textPart: The string containing text and potentially embedded JSON.
  /// - Returns: An array of `ParsedA2AEvent`s representing the separated text and data parts.
  private static func splitTextParts(_ textPart: String) -> [ParsedA2AEvent] {
    var parts: [ParsedA2AEvent] = []
    if textPart.contains(a2uiJsonTagOpen) {
      var remainingText = textPart
      while let startRange = remainingText.range(of: a2uiJsonTagOpen) {
        let intro = String(remainingText[..<startRange.lowerBound])
          .trimmingCharacters(in: .whitespacesAndNewlines)
        if !intro.isEmpty {
          parts.append(.text(intro))
        }

        let rest = remainingText[startRange.upperBound...]
        let jsonStr: String
        if let endRange = rest.range(of: a2uiJsonTagClose) {
          jsonStr = String(rest[..<endRange.lowerBound])
          remainingText = String(rest[endRange.upperBound...])
        } else {
          jsonStr = String(rest)
          remainingText = ""
        }

        let trimmedJSON = jsonStr.trimmingCharacters(in: .whitespacesAndNewlines)
        let dataValue = parseJSON(trimmedJSON) ?? trimmedJSON
        let event = ParsedA2AEvent.data(
          [dataValue],
          metadata: ParsedA2AEventMetadata(mimeType: a2uiJsonMimeType)
        )
        parts.append(event)
      }
      let remaining = remainingText.trimmingCharacters(in: .whitespacesAndNewlines)
      if !remaining.isEmpty {
        parts.append(.text(remaining))
      }
    } else {
      if !textPart.isEmpty {
        parts.append(.text(textPart))
      }
    }
    return parts
  }
}
