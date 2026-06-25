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

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class A2AResponseParserTest {

    @Test
    fun testParse_InvalidPayloadStructure() {
        // Test that an unexpected payload format returns an empty event list safely
        val payloadWithNoParts = JSONObject().apply {
            put("status", "ok")
        }
        val events = A2AResponseParser.parse(payloadWithNoParts)
        assertEquals(0, events.size)
    }

    @Test
    fun testParse_SimpleTextPart() {
        // Test standard text extraction from a standard payload structure
        val payload = JSONObject("""
            {
              "parts": [
                {"text": "Show me some good sushi in Seattle"}
              ]
            }
        """.trimIndent())

        val events = A2AResponseParser.parse(payload)
        assertEquals(1, events.size)
        val textEvent = events[0] as ParsedA2AEvent.Text
        assertEquals("Show me some good sushi in Seattle", textEvent.text)
    }

    @Test
    fun testParse_TextConcatenation() {
        // Android parser concatenates all text elements within a JSONArray into a single text event
        val payload = JSONObject("""
            {
              "result": [
                {"text": "Hello Seattle!"},
                {"text": "Hello Seattle!"},
                {"text": "Different text."}
              ]
            }
        """.trimIndent())

        val events = A2AResponseParser.parse(payload)
        assertEquals(1, events.size) // Expecting 1 because texts are concatenated
        assertEquals("Hello Seattle!\nHello Seattle!\nDifferent text.", (events[0] as ParsedA2AEvent.Text).text)
    }

    @Test
    fun testParse_StringifiedJsonResultArray() {
        // Tests the scenario where 'result' contains a stringified JSON array starting with '['
        val stringifiedArray = """[{"createSurface": {"surfaceId": "sushi-seattle"}}]"""
        val payload = JSONObject().apply {
            put("result", stringifiedArray)
        }

        val events = A2AResponseParser.parse(payload)
        assertEquals(1, events.size)

        val dataEvent = events[0] as ParsedA2AEvent.Data
        val a2uiArray = JSONArray(dataEvent.data)
        assertEquals(1, a2uiArray.length())
        assertTrue(a2uiArray.getJSONObject(0).has("createSurface"))
    }

    @Test
    fun testParse_NativeJsonResultArray() {
        // Tests the newly added support for native JSONArray inside the 'result' key (from PR #311 fixes)
        val payload = JSONObject("""
            {
              "result": [
                {
                  "text": "Here is your native array map"
                },
                {
                  "updateComponents": {
                    "surfaceId": "sushi-seattle",
                    "components": []
                  }
                }
              ]
            }
        """.trimIndent())

        val events = A2AResponseParser.parse(payload)
        
        // We expect one Text event and one Data event
        assertEquals(2, events.size)

        val textEvent = events[0] as ParsedA2AEvent.Text
        assertEquals("Here is your native array map", textEvent.text)

        val dataEvent = events[1] as ParsedA2AEvent.Data
        val a2uiArray = JSONArray(dataEvent.data)
        assertEquals(1, a2uiArray.length())
        assertTrue(a2uiArray.getJSONObject(0).has("updateComponents"))
    }
}