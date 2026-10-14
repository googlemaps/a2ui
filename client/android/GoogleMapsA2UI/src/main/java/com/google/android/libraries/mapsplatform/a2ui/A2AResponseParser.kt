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

sealed class A2AParserException(message: String) : Exception(message) {
  class InvalidPayloadStructure(
    message: String = "The raw JSON response lacks a recognized message parts structure."
  ) : A2AParserException(message)
}

data class ParsedA2AEventMetadata(val mimeType: String?)

sealed interface ParsedA2AEvent {
  data class Text(val text: String) : ParsedA2AEvent

  data class Data(val data: String, val metadata: ParsedA2AEventMetadata? = null) : ParsedA2AEvent
}

object A2AResponseParser {

  private const val KEY_TEXT = "text"
  private const val KEY_KIND = "kind"
  private const val KEY_DATA = "data"
  private const val KEY_HISTORY = "history"
  private const val KEY_ROLE = "role"
  private const val VAL_USER = "user"
  private const val VAL_AGENT = "agent"
  private const val KEY_PARTS = "parts"
  private const val KEY_CONTENT = "content"
  private const val KEY_STATUS = "status"
  private const val KEY_MESSAGE = "message"

  private const val KEY_CREATE_SURFACE = "createSurface"
  private const val KEY_UPDATE_COMPONENTS = "updateComponents"
  private const val KEY_UPDATE_DATA_MODEL = "updateDataModel"
  private const val KEY_DELETE_SURFACE = "deleteSurface"
  private const val KEY_SURFACE_ID = "surfaceId"

  private val A2UI_PATTERN = "<a2ui-json>(.*?)</a2ui-json>".toRegex(RegexOption.DOT_MATCHES_ALL)

  fun parse(rawJson: JSONObject): List<ParsedA2AEvent> {
    val partsArray =
      extractPartsArray(rawJson) ?: throw A2AParserException.InvalidPayloadStructure()

    val partsList = mutableListOf<ParsedA2AEvent>()
    var currentTextBuilder = java.lang.StringBuilder()
    var currentUiElements = JSONArray()

    for (i in 0 until partsArray.length()) {
      val part = partsArray.getJSONObject(i)
      val textPart =
        if (part.has(KEY_TEXT)) part.optString(KEY_TEXT)
        else if (part.optString(KEY_KIND) == KEY_TEXT) part.optString(KEY_TEXT) else null

      if (textPart != null) {
        if (currentUiElements.length() > 0) {
          partsList.add(ParsedA2AEvent.Data(currentUiElements.toString()))
          currentUiElements = JSONArray()
        }

        if (textPart.contains("<a2ui-json>")) {
          extractJsonBlocks(textPart, currentTextBuilder, partsList)
        } else if (textPart.isNotEmpty()) {
          if (currentTextBuilder.isNotEmpty()) currentTextBuilder.append("\n")
          currentTextBuilder.append(textPart)
        }
      }

      val dataPayload =
        if (part.has(KEY_DATA)) part.optJSONObject(KEY_DATA)
        else if (part.optString(KEY_KIND) == KEY_DATA) part.optJSONObject(KEY_DATA) else null
      if (dataPayload != null && isUiElement(dataPayload)) {
        if (currentTextBuilder.isNotEmpty()) {
          partsList.add(ParsedA2AEvent.Text(currentTextBuilder.toString()))
          currentTextBuilder = java.lang.StringBuilder()
        }
        currentUiElements.put(dataPayload)
      }
    }

    if (currentTextBuilder.isNotEmpty()) {
      partsList.add(ParsedA2AEvent.Text(currentTextBuilder.toString()))
    }
    if (currentUiElements.length() > 0) {
      partsList.add(ParsedA2AEvent.Data(currentUiElements.toString()))
    }

    val deduplicatedParts = mutableListOf<ParsedA2AEvent>()
    val seenSurfaces = mutableSetOf<String>()
    var lastSeenText: String? = null

    for (part in partsList) {
      val finalText: String? =
        if (part is ParsedA2AEvent.Text) {
          part.text.trim().takeIf { it.isNotEmpty() }
        } else null

      // Deduplicate consecutive identical text blocks
      if (finalText != null && finalText != lastSeenText) {
        deduplicatedParts.add(ParsedA2AEvent.Text(finalText))
        lastSeenText = finalText
      }

      if (part is ParsedA2AEvent.Data && part.data != "[]") {
        try {
          val array = JSONArray(part.data)
          val newArray = JSONArray()
          for (i in 0 until array.length()) {
            val obj = array.getJSONObject(i)
            val sid = obj.optJSONObject(KEY_CREATE_SURFACE)?.optString(KEY_SURFACE_ID)
            if (sid != null) {
              if (seenSurfaces.contains(sid)) {
                continue
              }
              seenSurfaces.add(sid)
            }
            newArray.put(obj)
          }
          if (newArray.length() > 0) {
            deduplicatedParts.add(ParsedA2AEvent.Data(newArray.toString(), part.metadata))
          }
        } catch (e: Exception) {
          if (part.data.isNotEmpty()) {
            deduplicatedParts.add(part)
          }
        }
      }
    }

    return deduplicatedParts
  }

  private fun isUiElement(obj: JSONObject): Boolean {
    return obj.has(KEY_CREATE_SURFACE) ||
      obj.has(KEY_UPDATE_COMPONENTS) ||
      obj.has(KEY_UPDATE_DATA_MODEL) ||
      obj.has(KEY_DELETE_SURFACE)
  }

  private fun extractPartsArray(rawJson: JSONObject): JSONArray? {
    val finalParts = JSONArray()

    if (rawJson.has(KEY_HISTORY)) {
      val history = rawJson.optJSONArray(KEY_HISTORY)
      if (history != null) {
        var lastUserIndex = -1
        for (i in 0 until history.length()) {
          val msg = history.optJSONObject(i)
          if (msg?.optString(KEY_ROLE) == VAL_USER) {
            lastUserIndex = i
          }
        }

        for (i in (lastUserIndex + 1) until history.length()) {
          val msg = history.optJSONObject(i)
          if (msg?.optString(KEY_ROLE) == VAL_AGENT) {
            val parts = msg.optJSONArray(KEY_PARTS)
            if (parts != null) {
              for (j in 0 until parts.length()) {
                finalParts.put(parts.getJSONObject(j))
              }
            }
          }
        }
      }
    }

    val additionalParts =
      when {
        rawJson.has(KEY_PARTS) -> rawJson.optJSONArray(KEY_PARTS)
        rawJson.has(KEY_CONTENT) -> rawJson.optJSONObject(KEY_CONTENT)?.optJSONArray(KEY_PARTS)
        rawJson.has(KEY_STATUS) ->
          rawJson.optJSONObject(KEY_STATUS)?.optJSONObject(KEY_MESSAGE)?.optJSONArray(KEY_PARTS)
        else -> null
      }

    if (additionalParts != null) {
      for (i in 0 until additionalParts.length()) {
        finalParts.put(additionalParts.getJSONObject(i))
      }
    }

    val hasRecognizedStructure =
      rawJson.optJSONArray(KEY_HISTORY) != null || additionalParts != null
    return if (hasRecognizedStructure) finalParts else null
  }

  private fun extractJsonBlocks(
    textPart: String,
    textBuilder: java.lang.StringBuilder,
    partsList: MutableList<ParsedA2AEvent>,
  ) {
    val allMatches = A2UI_PATTERN.findAll(textPart).toList()

    if (allMatches.isEmpty()) {
      if (textBuilder.isNotEmpty()) textBuilder.append("\n")
      textBuilder.append(textPart)
      return
    }

    var lastEnd = 0
    for (match in allMatches) {
      val beforeText = textPart.substring(lastEnd, match.range.first).trim()
      if (beforeText.isNotEmpty()) {
        if (textBuilder.isNotEmpty()) textBuilder.append("\n")
        textBuilder.append(beforeText)
      }

      val jsonString = match.groupValues[1].trim()
      try {
        val firstChar = jsonString.firstOrNull()
        if (firstChar == '[') {
          val array = JSONArray(jsonString)
          val localUiElements = JSONArray()
          for (i in 0 until array.length()) {
            localUiElements.put(array.getJSONObject(i))
          }
          if (textBuilder.isNotEmpty()) {
            partsList.add(ParsedA2AEvent.Text(textBuilder.toString()))
            textBuilder.clear()
          }
          partsList.add(ParsedA2AEvent.Data(localUiElements.toString()))
        } else if (firstChar == '{') {
          val jsonObj = JSONObject(jsonString)
          if (textBuilder.isNotEmpty()) {
            partsList.add(ParsedA2AEvent.Text(textBuilder.toString()))
            textBuilder.clear()
          }
          val localUiElements = JSONArray()
          localUiElements.put(jsonObj)
          partsList.add(ParsedA2AEvent.Data(localUiElements.toString()))
        } else {
          if (textBuilder.isNotEmpty()) textBuilder.append("\n")
          textBuilder.append(match.value)
        }
      } catch (e: Exception) {
        if (textBuilder.isNotEmpty()) textBuilder.append("\n")
        textBuilder.append(match.value)
      }
      lastEnd = match.range.last + 1
    }

    val remainingText = textPart.substring(lastEnd).trim()
    if (remainingText.isNotEmpty()) {
      if (textBuilder.isNotEmpty()) textBuilder.append("\n")
      textBuilder.append(remainingText)
    }
  }
}
