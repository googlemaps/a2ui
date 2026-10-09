/*
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { Part, SendMessageSuccessResponse, Task } from "@a2a-js/sdk";
import { A2AClient } from "@a2a-js/sdk/client";
import * as v0_9 from "@a2ui/web_core/v0_9";

const A2UI_MIME_TYPE = "application/json+a2ui";

export class A2UIClient {
  private serverUrl: string;
  private client: A2AClient | null = null;

  constructor(serverUrl: string = "") {
    this.serverUrl = serverUrl;
  }

  private readonly readyPromise: Promise<void> = Promise.resolve();
  get ready() {
    return this.readyPromise;
  }

  private async getClient() {
    if (!this.client) {
      // Default to localhost:10002 if no URL provided (fallback for restaurant app default)
      const baseUrl = this.serverUrl || "http://localhost:10002";

      this.client = await A2AClient.fromCardUrl(
        `${baseUrl}/.well-known/agent-card.json`,
        {
          fetchImpl: async (url: RequestInfo | URL, init?: RequestInit) => {
            const headers = new Headers(init?.headers);
            headers.set(
              "X-A2A-Extensions",
              "https://a2ui.org/a2a-extension/a2ui/v0.9",
            );
            return fetch(url, { ...init, headers });
          }
        }
      );
    }
    return this.client;
  }

  private _buildMessageParts(message: any | string): Part[] {
    if (typeof message !== 'string') {
      return [{
        kind: "data",
        data: message as unknown as Record<string, unknown>,
        mimeType: A2UI_MIME_TYPE,
      } as Part];
    }

    try {
      const parsed = JSON.parse(message);
      if (typeof parsed === 'object' && parsed !== null) {
        return [{
          kind: "data",
          data: parsed as unknown as Record<string, unknown>,
          mimeType: A2UI_MIME_TYPE,
        } as Part];
      }
    } catch {
      // Ignore JSON parse error, fall through to text
    }

    return [{ kind: "text", text: message }];
  }

  async send(
    message: any | string
  ): Promise<Array<{ type: "text", text: string } | { type: "a2ui", message: any }>> {
    const client = await this.getClient();
    const parts = this._buildMessageParts(message);

    const response = await client.sendMessage({
      message: {
        messageId: crypto.randomUUID(),
        role: "user",
        parts: parts,
        kind: "message",
      },
    });

    if ("error" in response) {
      throw new Error(response.error.message);
    }

    const result = (response as SendMessageSuccessResponse).result as Task;
    if (result.kind === "task" && result.status.message?.parts) {
      const orderedParts: Array<{ type: "text", text: string } | { type: "a2ui", message: any }> = [];
      for (const part of result.status.message.parts) {
        if (part.kind === 'data') {
          orderedParts.push({ type: "a2ui", message: part.data });
        } else if (part.kind === 'text') {
          orderedParts.push({ type: "text", text: part.text });
        }
      }
      return orderedParts;
    }

    return [];
  }

  private isAlreadyYieldedText(
      trimmedNew: string,
      priorSegments: string[],
      priorYieldedTrimmed: string,
      priorCompletedCount: number,
      isTerminalEvent: boolean,
      state: string|undefined,
      partsCount: number,
      ): boolean {
    if (!trimmedNew || priorSegments.length === 0) return false;
    const matchesPriorSegment = priorSegments.some(
        (seg) => seg.trim() === trimmedNew,
    );
    if (isTerminalEvent) {
      return matchesPriorSegment || priorYieldedTrimmed.includes(trimmedNew);
    }
    if (!state) {
      return (
          matchesPriorSegment && (partsCount > 1 || priorCompletedCount > 0));
    }
    return false;
  }

  async *sendStream(
    message: any | string
  ): AsyncGenerator<{ type: "text"; text: string } | { type: "a2ui"; message: any }> {
    const client = await this.getClient();
    const parts = this._buildMessageParts(message);

    const stream = client.sendMessageStream({
      message: {
        messageId: crypto.randomUUID(),
        role: "user",
        parts: parts,
        kind: "message",
      },
    });

    const yieldedDataPayloads = new Set<string>();
    const completedTextSegments: string[] = [];
    let currentSegmentText = '';

    for await (const event of stream) {
      if (event.kind !== 'status-update' || !event.status) continue;
      const parts = event.status.message?.parts;
      if (!parts) continue;

      const state = event.status.state;
      const isTerminalEvent =
          Boolean(state && state !== 'working') || Boolean(event.final);

      // Snapshot text segments yielded in prior events so terminal summary
      // deduplication only compares against prior events, never against earlier
      // parts within the same status-update event.
      const priorCompletedCount = completedTextSegments.length;
      const priorSegments = currentSegmentText ?
          [...completedTextSegments, currentSegmentText] :
          [...completedTextSegments];
      let priorYieldedTrimmed = priorSegments.join('').trim();

      for (const part of parts) {
        if (part.kind === 'text' && part.text) {
          const newText = part.text;
          const trimmedNew = newText.trim();

          let deltaText = '';
          if (currentSegmentText.trim() &&
              newText.startsWith(currentSegmentText)) {
            deltaText = newText.substring(currentSegmentText.length);
          } else if (
              this.isAlreadyYieldedText(
                  trimmedNew,
                  priorSegments,
                  priorYieldedTrimmed,
                  priorCompletedCount,
                  isTerminalEvent,
                  state,
                  parts.length,
                  )) {
            // Final task completion events re-send the full parsed text parts
            // with leading/trailing whitespace stripped; skip already-yielded
            // text segments so they are not duplicated.
            deltaText = '';
          } else {
            deltaText = newText;
          }
          if (deltaText) {
            yield { type: "text", text: deltaText };
            currentSegmentText += deltaText;
          }
        } else if (part.kind === 'data' && part.data) {
          if (currentSegmentText) {
            completedTextSegments.push(currentSegmentText);
            currentSegmentText = '';
          }
          if ('deleteSurface' in part.data) {
            yieldedDataPayloads.clear();
            completedTextSegments.length = 0;
            currentSegmentText = '';
            priorSegments.length = 0;
            priorYieldedTrimmed = '';
          }
          const payloadStr = JSON.stringify(part.data);
          if (!yieldedDataPayloads.has(payloadStr)) {
            yield { type: "a2ui", message: part.data };
            yieldedDataPayloads.add(payloadStr);
          }
        }
      }
    }
  }
}
