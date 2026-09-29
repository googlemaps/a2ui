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

final class A2AResponseParserTests: XCTestCase {
  /// Tests that an error is thrown when the input is not valid JSON text.
  func testParse_invalidJSONFormat() {
    XCTAssertThrowsError(try A2AResponseParser.parse(#"{"parts": ["#)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidJSONFormat)
    }
  }

  /// Tests that an error is thrown when the top-level JSON value is not an object.
  func testParse_topLevelArray_throwsInvalidJSONFormat() {
    XCTAssertThrowsError(try A2AResponseParser.parse(#"[{"text": "hi"}]"#)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidJSONFormat)
    }
  }

  /// Tests that an error is thrown when the JSON payload lacks a recognizable `parts` structure.
  func testParse_invalidPayloadStructure() {
    XCTAssertThrowsError(try A2AResponseParser.parse(#"{"status": "ok"}"#)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidPayloadStructure)
    }
  }

  /// Tests that an error is thrown when `parts` is not an array of dictionaries.
  func testParse_invalidPartsType_throwsError() {
    XCTAssertThrowsError(try A2AResponseParser.parse(#"{"parts": "not_an_array"}"#)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidPayloadStructure)
    }
  }

  /// Tests that a JSON-RPC `result` wrapper is unwrapped before parsing.
  func testParse_jsonRPCResultWrapper_unwrapsResult() throws {
    let payload = """
      {"jsonrpc": "2.0", "id": 1, "result": {"kind": "status-update", "status": {"message": \
      {"role": "agent", "parts": [{"text": "Top coffee shops in Seattle:"}]}}}}
      """

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.map(\.textValue), ["Top coffee shops in Seattle:"])
  }

  /// Tests that a JSON-RPC error object is surfaced as `A2AParserError.serverError`.
  func testParse_jsonRPCError_throwsServerError() {
    let payload =
      #"{"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "Internal error"}}"#
    XCTAssertThrowsError(try A2AResponseParser.parse(payload)) { error in
      XCTAssertEqual(
        error as? A2AParserError, .serverError(code: -32603, message: "Internal error"))
    }
  }

  /// Tests that an error nested inside `result` is also surfaced as a server error.
  func testParse_errorInsideResult_throwsServerError() {
    XCTAssertThrowsError(try A2AResponseParser.parse(#"{"result": {"error": "quota exceeded"}}"#)) {
      error in
      XCTAssertEqual(error as? A2AParserError, .serverError(code: nil, message: "quota exceeded"))
    }
  }

  /// Tests that a null `error` field is ignored.
  func testParse_nullError_isIgnored() throws {
    let payload = #"{"error": null, "result": {"parts": [{"text": "ok"}]}}"#
    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.map(\.textValue), ["ok"])
  }

  /// Tests that streaming events without message parts, such as a task snapshot or a final status
  /// update, produce an empty list instead of throwing.
  func testParse_partlessStreamingEvents_returnEmptyList() throws {
    let taskSnapshot = #"{"result": {"kind": "task", "id": "task-123"}}"#
    let finalStatusUpdate =
      #"{"result": {"kind": "status-update", "final": true, "status": {"state": "completed"}}}"#

    XCTAssertTrue(try A2AResponseParser.parse(taskSnapshot).isEmpty)
    XCTAssertTrue(try A2AResponseParser.parse(finalStatusUpdate).isEmpty)
  }

  /// Tests that a single text part is parsed correctly into a text event.
  func testParse_simpleTextPart() throws {
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": "Show me some good sushi in Seattle"]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.textValue, "Show me some good sushi in Seattle")
  }

  /// Tests that parts containing empty text strings produce an empty event list.
  func testParse_emptyTextPart_returnsEmptyList() throws {
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": ""]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertTrue(events.isEmpty)
  }

  /// Tests that multiple text parts within the `content.parts` path are parsed into separate text events.
  func testParse_multipleTextParts() throws {
    let payload: [String: Any] = [
      "content": [
        "parts": [
          ["kind": "text", "text": "Show me some good sushi in Seattle"],
          ["kind": "text", "text": "What are their ratings?"],
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(
      events.map(\.textValue),
      [
        "Show me some good sushi in Seattle",
        "What are their ratings?",
      ])
  }

  /// Tests that an A2UI JSON payload embedded inside a text part using `<a2ui-json>` tags is extracted.
  func testParse_embeddedA2UIJSON() throws {
    let textWithJSON =
      "Here is the Seattle map <a2ui-json>{\"createSurface\": {\"surfaceId\": \"sushi-seattle\"}}</a2ui-json> Hope you like it!"
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithJSON]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 3)
    XCTAssertEqual(events[0].textValue, "Here is the Seattle map")
    XCTAssertEqual(events[1].metadataMimeType, "application/json+a2ui")
    let dict = try XCTUnwrap(events[1].dataDictionaries?.first)
    XCTAssertNotNil(dict["createSurface"])
    XCTAssertEqual(events[2].textValue, "Hope you like it!")
  }

  /// Tests that an A2UI JSON array embedded inside a text part is parsed into a flat array of components.
  func testParse_embeddedA2UIJSONArray_flattensToSingleArray() throws {
    let textWithJSONArray =
      "Here is the map: <a2ui-json>[{\"createSurface\": {\"surfaceId\": \"sushi-seattle\"}}, {\"updateComponents\": {\"surfaceId\": \"sushi-seattle\"}}]</a2ui-json> Done."
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithJSONArray]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 3)
    XCTAssertEqual(events[0].textValue, "Here is the map:")
    XCTAssertEqual(events[1].metadataMimeType, "application/json+a2ui")
    let array = try XCTUnwrap(events[1].dataDictionaries)
    XCTAssertEqual(array.count, 2)
    XCTAssertNotNil(array[0]["createSurface"])
    XCTAssertNotNil(array[1]["updateComponents"])
    XCTAssertEqual(events[2].textValue, "Done.")
  }

  /// Tests that malformed JSON inside an embedded '<a2ui-json>' tag falls back gracefully to plain text.
  func testParse_malformedEmbeddedA2UITag_fallsBackToPlainText() throws {
    let textWithMalformedJSON = "Intro text <a2ui-json>{not_valid_json</a2ui-json> outro text"
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithMalformedJSON]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(
      events.map(\.textValue),
      [
        "Intro text",
        "<a2ui-json>{not_valid_json</a2ui-json>",
        "outro text",
      ])
  }

  /// Tests that an unclosed '<a2ui-json>' tag remains as plain text.
  func testParse_unclosedA2UITag_fallsBackToPlainText() throws {
    let unclosedTagText = "Before <a2ui-json>{\"createSurface\": {}} without closing tag"
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": unclosedTagText]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.textValue, unclosedTagText)
  }

  /// Tests that a data part with an explicit A2UI mime type is parsed and batched into an array.
  func testParse_dataPartWithA2UIMimeType() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "version": "v0.9",
            "updateComponents": [
              "surfaceId": "sushi-seattle",
              "components": [],
            ],
          ],
          "metadata": ["mimeType": "application/json+a2ui"],
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.metadataMimeType, "application/json+a2ui")

    let a2uiArray = try XCTUnwrap(events.first?.dataArray)
    XCTAssertEqual(a2uiArray.count, 1)
  }

  /// Tests that a data part is inferred as A2UI if it contains recognized keys, even without a mime type.
  func testParse_dataPartWithImplicitA2UIKey() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "createSurface": [
              "surfaceId": "sushi-seattle",
              "catalogId": "a2ui://maps-agentic-ui-catalog.json",
            ]
          ],
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.metadataMimeType, "application/json+a2ui")
    let a2uiArray = try XCTUnwrap(events.first?.dataArray)
    XCTAssertEqual(a2uiArray.count, 1)
  }

  /// Tests that the parser can successfully locate and extract parts from the `status.message.parts` JSON path.
  func testParse_statusMessagePartsPath() throws {
    let payload: [String: Any] = [
      "status": [
        "message": [
          "parts": [
            ["kind": "text", "text": "Seattle is home to a world-class sushi scene"]
          ]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.textValue, "Seattle is home to a world-class sushi scene")
  }

  /// Tests that consecutive data parts identified as A2UI payloads are batched together into a single data event.
  func testParse_consecutiveA2UIPayloadsAreBatched() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "createSurface": [
              "surfaceId": "sushi-seattle",
              "catalogId": "a2ui://maps-agentic-ui-catalog.json",
            ]
          ],
          "metadata": ["mimeType": "application/json+a2ui"],
        ],
        [
          "kind": "data",
          "data": [
            "updateComponents": [
              "surfaceId": "sushi-seattle",
              "components": [],
            ]
          ],
          "metadata": ["mimeType": "application/json+a2ui"],
        ],
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events.first?.metadataMimeType, "application/json+a2ui")

    let a2uiArray = try XCTUnwrap(events.first?.dataDictionaries)
    XCTAssertEqual(a2uiArray.count, 2)
    XCTAssertNotNil(a2uiArray[0]["createSurface"])
    XCTAssertNotNil(a2uiArray[1]["updateComponents"])
  }

  /// Tests that an A2UI batch is finalized and a new one starts if interrupted by a text part.
  func testParse_a2uiBatchInterruptedByTextPart() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": ["createSurface": ["surfaceId": "sushi-seattle"]],
          "metadata": ["mimeType": "application/json+a2ui"],
        ],
        ["kind": "text", "text": "Middle Text explaining the surface"],
        [
          "kind": "data",
          "data": ["updateComponents": ["surfaceId": "sushi-seattle"]],
          "metadata": ["mimeType": "application/json+a2ui"],
        ],
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 3)

    XCTAssertEqual(events[0].metadataMimeType, "application/json+a2ui")
    XCTAssertEqual(events[0].dataArray?.count, 1)

    XCTAssertEqual(events[1].textValue, "Middle Text explaining the surface")

    XCTAssertEqual(events[2].metadataMimeType, "application/json+a2ui")
    XCTAssertEqual(events[2].dataArray?.count, 1)
  }

  /// Tests that multiple `<a2ui-json>` tags within a single text part are all extracted sequentially.
  func testParse_multipleEmbeddedA2UITags() throws {
    let textWithMultipleTags =
      "First map: <a2ui-json>{\"createSurface\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Then: <a2ui-json>{\"updateComponents\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Done."
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithMultipleTags]
      ]
    ]

    let events = try A2AResponseParser.parse(jsonString(payload))
    XCTAssertEqual(events.count, 5)

    XCTAssertEqual(events[0].textValue, "First map:")
    XCTAssertEqual(events[1].metadataMimeType, "application/json+a2ui")
    let dict1 = try XCTUnwrap(events[1].dataDictionaries?.first)
    XCTAssertNotNil(dict1["createSurface"])

    XCTAssertEqual(events[2].textValue, "Then:")
    XCTAssertEqual(events[3].metadataMimeType, "application/json+a2ui")
    let dict2 = try XCTUnwrap(events[3].dataDictionaries?.first)
    XCTAssertNotNil(dict2["updateComponents"])

    XCTAssertEqual(events[4].textValue, "Done.")
  }

  /// Tests that when the parts array is present but empty or contains unknown types,
  /// the parser returns an empty list safely without throwing an exception.
  func testParse_emptyOrUnknownParts_returnsEmptyList() throws {
    let emptyPartsPayload: [String: Any] = ["parts": []]
    let emptyEvents = try A2AResponseParser.parse(jsonString(emptyPartsPayload))
    XCTAssertEqual(emptyEvents.count, 0)

    let unknownPartsPayload: [String: Any] = [
      "parts": [["kind": "unsupported_media"]]
    ]
    let unknownEvents = try A2AResponseParser.parse(jsonString(unknownPartsPayload))
    XCTAssertEqual(unknownEvents.count, 0)
  }
}

// MARK: - Test Helpers

/// Serializes a JSON dictionary into the raw text form accepted by `A2AResponseParser.parse`.
private func jsonString(_ object: [String: Any]) throws -> String {
  let data = try JSONSerialization.data(withJSONObject: object)
  return try XCTUnwrap(String(data: data, encoding: .utf8))
}

extension ParsedA2AEvent {
  fileprivate var textValue: String? {
    guard case .text(let text) = self else { return nil }
    return text
  }

  fileprivate var dataArray: [Any]? {
    guard case .data(let data, _) = self else { return nil }
    return data as? [Any]
  }

  fileprivate var dataDictionaries: [[String: Any]]? {
    guard case .data(let data, _) = self else { return nil }
    return data as? [[String: Any]]
  }

  fileprivate var metadataMimeType: String? {
    guard case .data(_, let metadata) = self else { return nil }
    return metadata?.mimeType
  }
}
