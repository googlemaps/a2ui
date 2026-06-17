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

import XCTest
@testable import GoogleMapsA2UI

final class A2AResponseParserTests: XCTestCase {

  /// Tests that an error is thrown when the input payload is not a valid JSON object.
  func testParse_InvalidJSONFormat() {
    let invalidPayload: [String: Any] = ["key": Date()] // Date is not valid JSON
    XCTAssertThrowsError(try A2AResponseParser.parse(invalidPayload)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidJSONFormat)
    }
  }

  /// Tests that an error is thrown when the JSON payload lacks a recognizable `parts` structure.
  func testParse_InvalidPayloadStructure() {
    let payloadWithNoParts: [String: Any] = ["status": "ok"]
    XCTAssertThrowsError(try A2AResponseParser.parse(payloadWithNoParts)) { error in
      XCTAssertEqual(error as? A2AParserError, .invalidPayloadStructure)
    }
  }

  /// Tests that a single text part is parsed correctly into a text event.
  func testParse_SimpleTextPart() throws {
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": "Show me some good sushi in Seattle"]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 1)

    guard case let .text(text) = events[0] else {
      XCTFail("Expected text event")
      return
    }
    XCTAssertEqual(text, "Show me some good sushi in Seattle")
  }

  /// Tests that multiple text parts within the `content.parts` path are parsed into separate text events.
  func testParse_MultipleTextParts() throws {
    let payload: [String: Any] = [
      "content": [
        "parts": [
          ["kind": "text", "text": "Show me some good sushi in Seattle"],
          ["kind": "text", "text": "What are their ratings?"]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 2)

    if case let .text(text1) = events[0] {
      XCTAssertEqual(text1, "Show me some good sushi in Seattle")
    } else {
      XCTFail("Expected first event to be text")
    }

    if case let .text(text2) = events[1] {
      XCTAssertEqual(text2, "What are their ratings?")
    } else {
      XCTFail("Expected second event to be text")
    }
  }

  /// Tests that an A2UI JSON payload embedded inside a text part using `<a2ui-json>` tags is extracted.
  func testParse_EmbeddedA2UIJSON() throws {
    let textWithJSON = "Here is the Seattle map <a2ui-json>{\"createSurface\": {\"surfaceId\": \"sushi-seattle\"}}</a2ui-json> Hope you like it!"
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithJSON]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 3)

    guard case let .text(prefix) = events[0] else {
      return XCTFail("Expected text event")
    }
    XCTAssertEqual(prefix, "Here is the Seattle map")

    guard case let .data(data, metadata) = events[1] else {
      return XCTFail("Expected data event")
    }
    XCTAssertEqual(metadata?.mimeType, "application/json+a2ui")
    let array = data as? [Any]
    let dict = array?.first as? [String: Any]
    XCTAssertNotNil(dict?["createSurface"])
    
    guard case let .text(suffix) = events[2] else {
      return XCTFail("Expected text event")
    }
    XCTAssertEqual(suffix, "Hope you like it!")
  }

  /// Tests that a data part with an explicit A2UI mime type is parsed and batched into an array.
  func testParse_DataPartWithA2UIMimeType() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "version": "v0.9",
            "updateComponents": [
              "surfaceId": "sushi-seattle",
              "components": []
            ]
          ],
          "metadata": ["mimeType": "application/json+a2ui"]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 1)

    guard case let .data(data, metadata) = events[0] else {
      return XCTFail("Expected data event")
    }
    XCTAssertEqual(metadata?.mimeType, "application/json+a2ui")
    
    let a2uiArray = data as? [Any]
    XCTAssertNotNil(a2uiArray, "A2UI payload should be batched into an array")
    XCTAssertEqual(a2uiArray?.count, 1)
  }

  /// Tests that a data part is inferred as A2UI if it contains recognized keys, even without a mime type.
  func testParse_DataPartWithImplicitA2UIKey() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "createSurface": [
              "surfaceId": "sushi-seattle",
              "catalogId": "a2ui://maps-agentic-ui-catalog.json"
            ]
          ]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 1)

    guard case let .data(data, metadata) = events[0] else {
      return XCTFail("Expected data event")
    }
    XCTAssertEqual(metadata?.mimeType, "application/json+a2ui")
    let a2uiArray = data as? [Any]
    XCTAssertNotNil(a2uiArray)
    XCTAssertEqual(a2uiArray?.count, 1)
  }

  /// Tests that the parser can successfully locate and extract parts from the `status.message.parts` JSON path.
  func testParse_StatusMessagePartsPath() throws {
    let payload: [String: Any] = [
      "status": [
        "message": [
          "parts": [
            ["kind": "text", "text": "Seattle is home to a world-class sushi scene"]
          ]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 1)

    guard case let .text(text) = events[0] else {
      XCTFail("Expected text event")
      return
    }
    XCTAssertEqual(text, "Seattle is home to a world-class sushi scene")
  }

  /// Tests that consecutive data parts identified as A2UI payloads are batched together into a single data event.
  func testParse_ConsecutiveA2UIPayloadsAreBatched() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": [
            "createSurface": [
              "surfaceId": "sushi-seattle",
              "catalogId": "a2ui://maps-agentic-ui-catalog.json"
            ]
          ],
          "metadata": ["mimeType": "application/json+a2ui"]
        ],
        [
          "kind": "data",
          "data": [
            "updateComponents": [
              "surfaceId": "sushi-seattle",
              "components": []
            ]
          ],
          "metadata": ["mimeType": "application/json+a2ui"]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 1)

    guard case let .data(data, metadata) = events[0] else {
      XCTFail("Expected data event")
      return
    }
    XCTAssertEqual(metadata?.mimeType, "application/json+a2ui")

    guard let a2uiArray = data as? [Any] else {
      XCTFail("Expected data payload to be an array of batched items")
      return
    }
    XCTAssertEqual(a2uiArray.count, 2)
    
    guard let dict1 = a2uiArray[0] as? [String: Any],
          let dict2 = a2uiArray[1] as? [String: Any] else {
      XCTFail("Expected array elements to be dictionaries")
      return
    }
    XCTAssertNotNil(dict1["createSurface"])
    XCTAssertNotNil(dict2["updateComponents"])
  }

  /// Tests that an A2UI batch is finalized and a new one starts if interrupted by a text part.
  func testParse_A2UIBatchInterruptedByTextPart() throws {
    let payload: [String: Any] = [
      "parts": [
        [
          "kind": "data",
          "data": ["createSurface": ["surfaceId": "sushi-seattle"]],
          "metadata": ["mimeType": "application/json+a2ui"]
        ],
        ["kind": "text", "text": "Middle Text explaining the surface"],
        [
          "kind": "data",
          "data": ["updateComponents": ["surfaceId": "sushi-seattle"]],
          "metadata": ["mimeType": "application/json+a2ui"]
        ]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 3)

    guard case let .data(data1, metadata1) = events[0] else {
      XCTFail("Expected first event to be data")
      return
    }
    XCTAssertEqual(metadata1?.mimeType, "application/json+a2ui")
    let batch1 = data1 as? [Any]
    XCTAssertEqual(batch1?.count, 1)

    guard case let .text(text) = events[1] else {
      XCTFail("Expected second event to be text")
      return
    }
    XCTAssertEqual(text, "Middle Text explaining the surface")

    guard case let .data(data2, metadata2) = events[2] else {
      XCTFail("Expected third event to be data")
      return
    }
    XCTAssertEqual(metadata2?.mimeType, "application/json+a2ui")
    let batch2 = data2 as? [Any]
    XCTAssertEqual(batch2?.count, 1)
  }

  /// Tests that multiple `<a2ui-json>` tags within a single text part are all extracted sequentially.
  func testParse_MultipleEmbeddedA2UITags() throws {
    let textWithMultipleTags = "First map: <a2ui-json>{\"createSurface\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Then: <a2ui-json>{\"updateComponents\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Done."
    let payload: [String: Any] = [
      "parts": [
        ["kind": "text", "text": textWithMultipleTags]
      ]
    ]

    let events = try A2AResponseParser.parse(payload)
    XCTAssertEqual(events.count, 5)

    guard case let .text(t1) = events[0],
          case let .data(d1, m1) = events[1],
          case let .text(t2) = events[2],
          case let .data(d2, m2) = events[3],
          case let .text(t3) = events[4] else {
      XCTFail("Expected sequence: [text, data, text, data, text]")
      return
    }

    XCTAssertEqual(t1, "First map:")
    XCTAssertEqual(m1?.mimeType, "application/json+a2ui")
    XCTAssertNotNil((d1 as? [Any])?.first as? [String: Any])

    XCTAssertEqual(t2, "Then:")
    XCTAssertEqual(m2?.mimeType, "application/json+a2ui")
    XCTAssertNotNil((d2 as? [Any])?.first as? [String: Any])

    XCTAssertEqual(t3, "Done.")
  }
}

