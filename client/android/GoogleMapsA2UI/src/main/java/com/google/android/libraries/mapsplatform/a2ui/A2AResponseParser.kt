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
import org.json.JSONException
import org.json.JSONObject

/** Errors thrown by [A2AResponseParser.parse]. */
abstract class A2AParserException private constructor(message: String, cause: Throwable? = null) :
  Exception(message, cause) {
  /** The input is not valid JSON text, or its top-level value is not a JSON object. */
  class InvalidJsonFormat
  @JvmOverloads
  constructor(
    message: String = "The raw response is not a valid JSON object.",
    cause: Throwable? = null,
  ) : A2AParserException(message, cause)

  /** The JSON object lacks a recognized message parts structure. */
  class InvalidPayloadStructure
  @JvmOverloads
  constructor(
    message: String = "The raw JSON response lacks a recognized message parts structure.",
    cause: Throwable? = null,
  ) : A2AParserException(message, cause)

  /** The server returned a JSON-RPC `error` object instead of a result. */
  class ServerError(
    /** The JSON-RPC error code, or `null` if the server did not provide one. */
    val code: Int?,
    message: String,
  ) : A2AParserException(message)
}

/** Metadata associated with a [ParsedA2AEvent.Data] payload. */
class ParsedA2AEventMetadata @JvmOverloads constructor(val mimeType: String? = null) {
  override fun equals(other: Any?): Boolean {
    if (this === other) return true
    if (other !is ParsedA2AEventMetadata) return false
    return mimeType == other.mimeType
  }

  override fun hashCode(): Int = mimeType?.hashCode() ?: 0

  override fun toString(): String = "ParsedA2AEventMetadata(mimeType=$mimeType)"
}

/** Represents a parsed output chunk extracted from an A2A server response. */
abstract class ParsedA2AEvent private constructor() {
  /** Conversational text extracted from the server response. */
  class Text(val text: String) : ParsedA2AEvent() {
    override fun equals(other: Any?): Boolean {
      if (this === other) return true
      if (other !is Text) return false
      return text == other.text
    }

    override fun hashCode(): Int = text.hashCode()

    override fun toString(): String = "Text(text=$text)"
  }

  /** Structured data payload extracted from the server response. */
  class Data
  @JvmOverloads
  constructor(val data: String, val metadata: ParsedA2AEventMetadata? = null) : ParsedA2AEvent() {
    override fun equals(other: Any?): Boolean {
      if (this === other) return true
      if (other !is Data) return false
      return data == other.data && metadata == other.metadata
    }

    override fun hashCode(): Int {
      var result = data.hashCode()
      result = 31 * result + (metadata?.hashCode() ?: 0)
      return result
    }

    override fun toString(): String = "Data(data=$data, metadata=$metadata)"
  }
}

object A2AResponseParser {

  private const val KEY_TEXT = "text"
  private const val KEY_KIND = "kind"
  private const val KEY_DATA = "data"
  private const val KEY_METADATA = "metadata"
  private const val KEY_MIME_TYPE = "mimeType"
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

  private const val KEY_RESULT = "result"
  private const val KEY_ERROR = "error"
  private const val KEY_CODE = "code"

  private const val A2UI_JSON_MIME_TYPE = "application/json+a2ui"
  private const val A2UI_V1_MIME_TYPE = "application/a2ui+json"

  /** A2A event kinds that may legitimately carry no message parts, e.g. a final status update. */
  private val PARTLESS_EVENT_KINDS = setOf("task", "status-update", "artifact-update")

  /** A2A event kinds whose agent reply, if any, is carried in `status.message`. */
  private val STATUS_EVENT_KINDS = setOf("task", "status-update")

  private val A2UI_PATTERN = "<a2ui-json>(.*?)</a2ui-json>".toRegex(RegexOption.DOT_MATCHES_ALL)

  /**
   * Parses one A2A server response into an ordered list of events.
   *
   * [rawJson] is the JSON text of a single response: a JSON-RPC response (the body of a
   * `message/send` call, or the payload of one `message/stream` SSE `data:` line), or a bare A2A
   * `Message`, `Task`, or `TaskStatusUpdateEvent` object. A JSON-RPC `result` wrapper is unwrapped
   * automatically, and for `task` and `status-update` objects the agent reply in `status.message`
   * is parsed. Streaming events that carry no message parts, such as an initial `task` snapshot or
   * a final `status-update`, produce an empty list.
   *
   * @throws A2AParserException.InvalidJsonFormat if [rawJson] is not a valid JSON object.
   * @throws A2AParserException.ServerError if the response contains a JSON-RPC `error`.
   * @throws A2AParserException.InvalidPayloadStructure if no message parts structure is found.
   */
  @JvmStatic
  @Throws(A2AParserException::class)
  fun parse(rawJson: String): List<ParsedA2AEvent> {
    val root =
      try {
        JSONObject(rawJson)
      } catch (e: JSONException) {
        throw A2AParserException.InvalidJsonFormat(cause = e)
      }
    var payload = root.optJSONObject(KEY_RESULT) ?: root
    throwIfServerError(payload)
    // For task snapshots and status updates, the agent's reply is the status message.
    if (payload.optString(KEY_KIND) in STATUS_EVENT_KINDS) {
      payload.optJSONObject(KEY_STATUS)?.optJSONObject(KEY_MESSAGE)?.let { payload = it }
    }
    return try {
      parsePayload(payload)
    } catch (e: JSONException) {
      throw A2AParserException.InvalidPayloadStructure(cause = e)
    }
  }

  private fun throwIfServerError(obj: JSONObject) {
    if (obj.isNull(KEY_ERROR)) return
    val error = obj.opt(KEY_ERROR)
    val errorObj = error as? JSONObject
    val message = errorObj?.optNonEmptyString(KEY_MESSAGE) ?: error.toString()
    val code = errorObj?.takeIf { !it.isNull(KEY_CODE) && it.has(KEY_CODE) }?.optInt(KEY_CODE)
    throw A2AParserException.ServerError(code, message)
  }

  private fun parsePayload(rawJson: JSONObject): List<ParsedA2AEvent> {
    val partsArray = extractPartsArray(rawJson)
    if (partsArray == null) {
      if (rawJson.optString(KEY_KIND) in PARTLESS_EVENT_KINDS) return emptyList()
      throw A2AParserException.InvalidPayloadStructure()
    }

    val partsList = mutableListOf<ParsedA2AEvent>()
    var currentTextBuilder = java.lang.StringBuilder()
    var currentUiElements = JSONArray()

    fun flushA2uiElements() {
      if (currentUiElements.length() > 0) {
        partsList.add(
          ParsedA2AEvent.Data(
            currentUiElements.toString(),
            ParsedA2AEventMetadata(A2UI_JSON_MIME_TYPE),
          )
        )
        currentUiElements = JSONArray()
      }
    }

    fun flushTextBuilder() {
      if (currentTextBuilder.isNotEmpty()) {
        partsList.add(ParsedA2AEvent.Text(currentTextBuilder.toString()))
        currentTextBuilder = java.lang.StringBuilder()
      }
    }

    for (i in 0 until partsArray.length()) {
      val part = partsArray.getJSONObject(i)
      val textPart =
        when {
          part.has(KEY_TEXT) && !part.isNull(KEY_TEXT) -> part.optString(KEY_TEXT)
          part.optString(KEY_KIND) == KEY_TEXT && !part.isNull(KEY_TEXT) -> part.optString(KEY_TEXT)
          else -> null
        }

      if (textPart != null) {
        flushA2uiElements()

        when {
          "<a2ui-json>" in textPart -> extractJsonBlocks(textPart, currentTextBuilder, partsList)
          textPart.isNotEmpty() -> {
            if (currentTextBuilder.isNotEmpty()) currentTextBuilder.append("\n")
            currentTextBuilder.append(textPart)
          }
        }
      }

      val dataPayload =
        when {
          part.has(KEY_DATA) -> part.optJSONObject(KEY_DATA)
          part.optString(KEY_KIND) == KEY_DATA -> part.optJSONObject(KEY_DATA)
          else -> null
        }
      if (dataPayload != null) {
        val metadataObj = part.optJSONObject(KEY_METADATA)
        val rawMimeType =
          part.optNonEmptyString(KEY_MIME_TYPE) ?: metadataObj?.optNonEmptyString(KEY_MIME_TYPE)
        val resolvedMimeType =
          when {
            rawMimeType == A2UI_V1_MIME_TYPE -> A2UI_JSON_MIME_TYPE
            rawMimeType != null -> rawMimeType
            isUiElement(dataPayload) -> A2UI_JSON_MIME_TYPE
            else -> null
          }

        flushTextBuilder()
        if (resolvedMimeType == A2UI_JSON_MIME_TYPE) {
          currentUiElements.put(dataPayload)
        } else {
          flushA2uiElements()
          partsList.add(
            ParsedA2AEvent.Data(dataPayload.toString(), ParsedA2AEventMetadata(resolvedMimeType))
          )
        }
      }
    }

    flushTextBuilder()
    flushA2uiElements()

    val deduplicatedParts = mutableListOf<ParsedA2AEvent>()
    val seenSurfaces = mutableSetOf<String>()
    var lastSeenText: String? = null

    for (part in partsList) {
      when (part) {
        is ParsedA2AEvent.Text -> {
          val finalText = part.text.trim().takeIf { it.isNotEmpty() }
          // Deduplicate consecutive identical text blocks
          if (finalText != null && finalText != lastSeenText) {
            deduplicatedParts.add(ParsedA2AEvent.Text(finalText))
            lastSeenText = finalText
          }
        }
        is ParsedA2AEvent.Data -> {
          when {
            part.metadata?.mimeType == A2UI_JSON_MIME_TYPE -> {
              if (part.data != "[]") {
                try {
                  val array = JSONArray(part.data)
                  val newArray = JSONArray()
                  for (i in 0 until array.length()) {
                    val obj = array.getJSONObject(i)
                    val sid =
                      obj.optJSONObject(KEY_CREATE_SURFACE)?.optNonEmptyString(KEY_SURFACE_ID)
                    if (sid != null) {
                      if (sid in seenSurfaces) {
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
            part.data.isNotEmpty() -> deduplicatedParts.add(part)
          }
        }
      }
    }

    return deduplicatedParts
  }

  private fun JSONObject.optNonEmptyString(key: String): String? {
    if (isNull(key)) return null
    return optString(key).takeIf { it.isNotEmpty() }
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
        when (jsonString.firstOrNull()) {
          '[' -> {
            val array = JSONArray(jsonString)
            val localUiElements = JSONArray()
            for (i in 0 until array.length()) {
              localUiElements.put(array.getJSONObject(i))
            }
            if (textBuilder.isNotEmpty()) {
              partsList.add(ParsedA2AEvent.Text(textBuilder.toString()))
              textBuilder.clear()
            }
            partsList.add(
              ParsedA2AEvent.Data(
                localUiElements.toString(),
                ParsedA2AEventMetadata(A2UI_JSON_MIME_TYPE),
              )
            )
          }
          '{' -> {
            val jsonObj = JSONObject(jsonString)
            if (textBuilder.isNotEmpty()) {
              partsList.add(ParsedA2AEvent.Text(textBuilder.toString()))
              textBuilder.clear()
            }
            val localUiElements = JSONArray()
            localUiElements.put(jsonObj)
            partsList.add(
              ParsedA2AEvent.Data(
                localUiElements.toString(),
                ParsedA2AEventMetadata(A2UI_JSON_MIME_TYPE),
              )
            )
          }
          else -> {
            if (textBuilder.isNotEmpty()) textBuilder.append("\n")
            textBuilder.append(match.value)
          }
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
