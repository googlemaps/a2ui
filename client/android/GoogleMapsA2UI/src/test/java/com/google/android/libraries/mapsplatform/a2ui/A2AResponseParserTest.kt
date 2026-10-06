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

package com.google.android.libraries.mapsplatform.a2ui

import com.google.common.truth.Truth.assertThat
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class A2AResponseParserTest {

  /**
   * Verifies that parsing an unexpected payload structure without message parts or results throws
   * [A2AParserException.InvalidPayloadStructure].
   */
  @Test
  fun parse_invalidPayloadStructure_throwsException() {
    val payloadWithNoParts = JSONObject().apply { put("status", "ok") }
    val thrown =
      assertThrows(A2AParserException.InvalidPayloadStructure::class.java) {
        A2AResponseParser.parse(payloadWithNoParts)
      }
    assertThat(thrown).hasMessageThat().contains("lacks a recognized message parts structure")
  }

  /**
   * Verifies that when "history" is present but not an array, the parser throws
   * [A2AParserException.InvalidPayloadStructure].
   */
  @Test
  fun parse_invalidHistoryType_throwsException() {
    val payloadWithInvalidHistory = JSONObject().apply { put("history", "not_an_array") }
    val thrown =
      assertThrows(A2AParserException.InvalidPayloadStructure::class.java) {
        A2AResponseParser.parse(payloadWithInvalidHistory)
      }
    assertThat(thrown).hasMessageThat().contains("lacks a recognized message parts structure")
  }

  /** Verifies that when the parts array is empty, the parser returns an empty list. */
  @Test
  fun parse_emptyParts_returnsEmptyList() {
    val emptyPartsPayload = JSONObject("""{"parts": []}""")
    val emptyEvents = A2AResponseParser.parse(emptyPartsPayload)
    assertThat(emptyEvents).isEmpty()
  }

  /**
   * Verifies that when the parts array contains unknown types, the parser returns an empty list
   * safely without throwing an exception.
   */
  @Test
  fun parse_unknownParts_returnsEmptyList() {
    val unknownPartsPayload = JSONObject("""{"parts": [{"kind": "unsupported_media"}]}""")
    val unknownEvents = A2AResponseParser.parse(unknownPartsPayload)
    assertThat(unknownEvents).isEmpty()
  }

  /** Verifies that a simple text part in the "parts" array is parsed into a single text event. */
  @Test
  fun parse_simpleTextPart_returnsSingleTextEvent() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"text": "Show me some good sushi in Seattle"}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).containsExactly(ParsedA2AEvent.Text("Show me some good sushi in Seattle"))
  }

  /** Verifies that the parser resolves message parts nested under "content.parts". */
  @Test
  fun parse_contentPartsPath_resolvesTextEvent() {
    val payload =
      JSONObject(
        """
        {
          "content": {
            "parts": [
              {"text": "Welcome to Seattle!"}
            ]
          }
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).containsExactly(ParsedA2AEvent.Text("Welcome to Seattle!"))
  }

  /** Verifies that the parser resolves message parts nested under "status.message.parts". */
  @Test
  fun parse_statusMessagePartsPath_resolvesTextEvent() {
    val payload =
      JSONObject(
        """
        {
          "status": {
            "message": {
              "parts": [
                {"text": "Status message text"}
              ]
            }
          }
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).containsExactly(ParsedA2AEvent.Text("Status message text"))
  }

  /**
   * Verifies that the parser resolves message parts from the "history" array, extracting agent
   * parts that appear after the last user message.
   */
  @Test
  fun parse_historyPayload_resolvesAgentPartsAfterLastUser() {
    val payload =
      JSONObject(
        """
        {
          "history": [
            {
              "role": "user",
              "parts": [{"text": "First query"}]
            },
            {
              "role": "agent",
              "parts": [{"text": "First answer"}]
            },
            {
              "role": "user",
              "parts": [{"text": "Show me Seattle maps"}]
            },
            {
              "role": "agent",
              "parts": [{"text": "Here is Seattle!"}]
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).containsExactly(ParsedA2AEvent.Text("Here is Seattle!"))
  }

  /**
   * Verifies that when a history payload has only user messages and no agent reply yet, the parser
   * returns an empty list.
   */
  @Test
  fun parse_historyPayloadWithNoAgentResponse_returnsEmptyList() {
    val payload =
      JSONObject(
        """
        {
          "history": [
            {
              "role": "user",
              "parts": [{"text": "Hello, agent!"}]
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).isEmpty()
  }

  /**
   * Verifies that multiple text parts in the payload are concatenated with newlines into a single
   * text event.
   */
  @Test
  fun parse_multipleTextParts_concatenatesIntoSingleTextEvent() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"text": "Hello Seattle!"},
            {"text": "Hello Seattle!"},
            {"text": "Different text."}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events)
      .containsExactly(ParsedA2AEvent.Text("Hello Seattle!\nHello Seattle!\nDifferent text."))
  }

  /** Verifies that parts containing empty text strings produce an empty event list. */
  @Test
  fun parse_emptyTextPart_returnsEmptyList() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"text": ""}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).isEmpty()
  }

  /**
   * Verifies that non-array parts structure throws [A2AParserException.InvalidPayloadStructure].
   */
  @Test
  fun parse_invalidPartsType_throwsException() {
    val payload = JSONObject("""{"parts": "not_an_array"}""")
    assertThrows(A2AParserException.InvalidPayloadStructure::class.java) {
      A2AResponseParser.parse(payload)
    }
  }

  /**
   * Verifies that embedded '<a2ui-json>' tags within a text body are extracted into discrete text
   * and A2UI data events in sequential order.
   */
  @Test
  fun parse_embeddedA2UIJSON_extractsTextAndDataEventsSequentially() {
    val textWithJson =
      "Here is the map: <a2ui-json>[{\"createSurface\": {\"surfaceId\": \"seattle-map\"}}]</a2ui-json> Hope this helps!"
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"kind": "text", "text": ${JSONObject.quote(textWithJson)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(3)
    assertThat(events[0]).isEqualTo(ParsedA2AEvent.Text("Here is the map:"))

    val dataEvent = events[1] as ParsedA2AEvent.Data
    val arr = JSONArray(dataEvent.data)
    assertThat(arr.getJSONObject(0).getJSONObject("createSurface").getString("surfaceId"))
      .isEqualTo("seattle-map")

    assertThat(events[2]).isEqualTo(ParsedA2AEvent.Text("Hope this helps!"))
  }

  /**
   * Verifies that an A2UI JSON array embedded inside a text part is parsed into a flat array of
   * components.
   */
  @Test
  fun parse_embeddedA2UIJSONArray_flattensToSingleArray() {
    val textWithJsonArray =
      "Here is the map: <a2ui-json>[{\"createSurface\": {\"surfaceId\": \"sushi-seattle\"}}, {\"updateComponents\": {\"surfaceId\": \"sushi-seattle\"}}]</a2ui-json> Done."
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"kind": "text", "text": ${JSONObject.quote(textWithJsonArray)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(3)
    assertThat(events[0]).isEqualTo(ParsedA2AEvent.Text("Here is the map:"))

    val dataEvent = events[1] as ParsedA2AEvent.Data
    val arr = JSONArray(dataEvent.data)
    assertThat(arr.length()).isEqualTo(2)
    assertThat(arr.getJSONObject(0).has("createSurface")).isTrue()
    assertThat(arr.getJSONObject(1).has("updateComponents")).isTrue()

    assertThat(events[2]).isEqualTo(ParsedA2AEvent.Text("Done."))
  }

  /**
   * Verifies that malformed JSON inside an embedded '<a2ui-json>' tag falls back gracefully to
   * plain text without crashing.
   */
  @Test
  fun parse_malformedEmbeddedA2UITag_fallsBackToPlainText() {
    val textWithMalformedJson = "Intro text <a2ui-json>{not_valid_json</a2ui-json> outro text"
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"kind": "text", "text": ${JSONObject.quote(textWithMalformedJson)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events)
      .containsExactly(
        ParsedA2AEvent.Text("Intro text\n<a2ui-json>{not_valid_json</a2ui-json>\noutro text")
      )
  }

  /**
   * Verifies that non-object/non-array JSON inside an embedded '<a2ui-json>' tag falls back to
   * plain text.
   */
  @Test
  fun parse_nonObjectOrArrayEmbeddedA2UITag_fallsBackToPlainText() {
    val textWithPrimitiveJson = "Intro text <a2ui-json>12345</a2ui-json> outro text"
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"kind": "text", "text": ${JSONObject.quote(textWithPrimitiveJson)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events)
      .containsExactly(ParsedA2AEvent.Text("Intro text\n<a2ui-json>12345</a2ui-json>\noutro text"))
  }

  /** Verifies that an unclosed '<a2ui-json>' tag remains as plain text. */
  @Test
  fun parse_unclosedA2UITag_fallsBackToPlainText() {
    val unclosedTagText = "Before <a2ui-json>{\"createSurface\": {}} without closing tag"
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"text": ${JSONObject.quote(unclosedTagText)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events)
      .containsExactly(
        ParsedA2AEvent.Text("Before <a2ui-json>{\"createSurface\": {}} without closing tag")
      )
  }

  /**
   * Verifies that duplicate surface creation definitions with identical surface IDs are
   * deduplicated within the payload.
   */
  @Test
  fun parse_duplicateSurfaceIds_deduplicatesSurfaces() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {
              "data": {
                "createSurface": {"surfaceId": "dup-surface"}
              }
            },
            {
              "data": {
                "createSurface": {"surfaceId": "dup-surface"}
              }
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(1)
    val dataEvent = events[0] as ParsedA2AEvent.Data
    val arr = JSONArray(dataEvent.data)
    assertThat(arr.length()).isEqualTo(1)
  }

  /**
   * Verifies that multiple '<a2ui-json>' tags within a single text part are all extracted
   * sequentially.
   */
  @Test
  fun parse_multipleEmbeddedA2UITags_extractsAllSequentially() {
    val textWithMultipleTags =
      "First map: <a2ui-json>{\"createSurface\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Then: <a2ui-json>{\"updateComponents\": {\"surfaceId\": \"sushi\"}}</a2ui-json> Done."
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {"kind": "text", "text": ${JSONObject.quote(textWithMultipleTags)}}
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(5)
    assertThat(events[0]).isEqualTo(ParsedA2AEvent.Text("First map:"))

    val dataEvent1 = events[1] as ParsedA2AEvent.Data
    val arr1 = JSONArray(dataEvent1.data)
    assertThat(arr1.getJSONObject(0).getJSONObject("createSurface").getString("surfaceId"))
      .isEqualTo("sushi")

    assertThat(events[2]).isEqualTo(ParsedA2AEvent.Text("Then:"))

    val dataEvent2 = events[3] as ParsedA2AEvent.Data
    val arr2 = JSONArray(dataEvent2.data)
    assertThat(arr2.getJSONObject(0).getJSONObject("updateComponents").getString("surfaceId"))
      .isEqualTo("sushi")

    assertThat(events[4]).isEqualTo(ParsedA2AEvent.Text("Done."))
  }

  /**
   * Verifies that consecutive data parts identified as A2UI payloads are batched together into a
   * single data event.
   */
  @Test
  fun parse_consecutiveA2UIPayloads_batchesIntoSingleEvent() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {
              "kind": "data",
              "data": {
                "createSurface": {
                  "surfaceId": "sushi-seattle",
                  "catalogId": "a2ui://maps-agentic-ui-catalog.json"
                }
              }
            },
            {
              "kind": "data",
              "data": {
                "updateComponents": {
                  "surfaceId": "sushi-seattle",
                  "components": []
                }
              }
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(1)
    val dataEvent = events[0] as ParsedA2AEvent.Data
    val arr = JSONArray(dataEvent.data)
    assertThat(arr.length()).isEqualTo(2)
    assertThat(arr.getJSONObject(0).has("createSurface")).isTrue()
    assertThat(arr.getJSONObject(1).has("updateComponents")).isTrue()
  }

  /**
   * Verifies that an A2UI batch is finalized and a new one starts if interrupted by a text part.
   */
  @Test
  fun parse_a2uiBatchInterruptedByTextPart_createsSeparateBatches() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {
              "kind": "data",
              "data": {"createSurface": {"surfaceId": "sushi-seattle"}}
            },
            {"kind": "text", "text": "Middle Text explaining the surface"},
            {
              "kind": "data",
              "data": {"updateComponents": {"surfaceId": "sushi-seattle"}}
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(3)

    val data1 = events[0] as ParsedA2AEvent.Data
    assertThat(JSONArray(data1.data).length()).isEqualTo(1)

    assertThat(events[1]).isEqualTo(ParsedA2AEvent.Text("Middle Text explaining the surface"))

    val data2 = events[2] as ParsedA2AEvent.Data
    assertThat(JSONArray(data2.data).length()).isEqualTo(1)
  }

  /**
   * Verifies that a data part is recognized as an A2UI payload if it contains recognized keys, even
   * without a mime type.
   */
  @Test
  fun parse_dataPartWithImplicitA2UIKey_returnsDataEvent() {
    val payload =
      JSONObject(
        """
        {
          "parts": [
            {
              "kind": "data",
              "data": {
                "createSurface": {
                  "surfaceId": "sushi-seattle",
                  "catalogId": "a2ui://maps-agentic-ui-catalog.json"
                }
              }
            }
          ]
        }
        """
          .trimIndent()
      )

    val events = A2AResponseParser.parse(payload)
    assertThat(events).hasSize(1)
    val dataEvent = events[0] as ParsedA2AEvent.Data
    val arr = JSONArray(dataEvent.data)
    assertThat(arr.length()).isEqualTo(1)
    assertThat(arr.getJSONObject(0).has("createSurface")).isTrue()
  }
}
