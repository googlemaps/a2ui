/*
 Copyright 2026 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import {basicCatalog, Context} from '@a2ui/lit/v0_9';
import {renderMarkdown} from '@a2ui/markdown-it';
import * as Types from '@a2ui/web_core/types/types';
import * as v0_9 from '@a2ui/web_core/v0_9';
import {ContextProvider} from '@lit/context';
import {html, LitElement} from 'lit';
import {property} from 'lit/decorators.js';

import {mapsAgenticUICatalog} from './catalog';
import {attributionIdsContext, attributionIdsConverter} from './custom-components/attribution';
import {loadMapsLibrary} from './custom-components/maps_api_loader';

export class MAUIProviders extends LitElement {
  private attributionIdsValue: readonly string[] = [];

  private markdownProvider = new ContextProvider(this, {
    context: Context.markdown,
    initialValue: async (
        markdown: string,
        options?: Types.MarkdownRendererOptions,
        ) => renderMarkdown(markdown, options),
  });

  private attributionIdsProvider = new ContextProvider(this, {
    context: attributionIdsContext,
    initialValue: this.attributionIdsValue,
  });

  /**
   * Maps JS API usage attribution IDs that every MAUI component inside this
   * element sends in addition to MAUI's own ID. Also settable as a
   * comma-separated `additional-attribution-ids` attribute.
   */
  @property({
    attribute: 'additional-attribution-ids',
    converter: attributionIdsConverter,
    noAccessor: true,
  })
  get additionalAttributionIds(): readonly string[] {
    return this.attributionIdsValue;
  }

  set additionalAttributionIds(ids: readonly string[]) {
    const oldIds = this.attributionIdsValue;
    this.attributionIdsValue = ids ?? [];
    // Update consumers synchronously, so that MAUI components rendered in the
    // same pass see the IDs before they first render. Maps JS API elements may
    // ignore attribution ID changes after they are instantiated.
    this.attributionIdsProvider?.setValue(this.attributionIdsValue);
    this.requestUpdate('additionalAttributionIds', oldIds);
  }

  protected override render() {
    return html`<slot></slot>`;
  }
}

if (!customElements.get("maui-providers")) {
  customElements.define("maui-providers", MAUIProviders);
}

export type TimelineItem =
  | { type: "text"; text: string }
  | { type: "user"; text: string }
  | { type: "action"; text: string; action: string }
  | { type: "surface"; surfaceId: string };

const A2UI_TOP_LEVEL_KEYS = ['createSurface', 'updateComponents', 'updateDataModel', 'deleteSurface', 'beginRendering', 'surfaceUpdate', 'dataModelUpdate'];

export class A2UIRenderer {
  private readonly messageProcessor = new v0_9.MessageProcessor(
    [mapsAgenticUICatalog],
    async (action: v0_9.A2uiClientAction): Promise<any> => {
      console.warn("Action handling is unimplemented", action);
    },
  );
  private timelineItems: TimelineItem[] = [];
  // Maps duplicate incoming surfaceIds to unique aliases so repeated surfaceIds
  // across turns do not collide in the shared MessageProcessor.
  private readonly surfaceIdAliases = new Map<string, string>();
  private surfaceCollisionCounter = 0;

  /**
   * Returns the current timeline of messages and surfaces.
   */
  get timeline() {
    return this.timelineItems;
  }

  /**
   * Returns the A2UI message processor.
   */
  get processor() {
    return this.messageProcessor;
  }

  /**
   * Gets a surface by it's ID.
   */
  getSurface(surfaceId: string) {
    return this.messageProcessor.model.surfacesMap.get(surfaceId);
  }

  private getSurfaceId(msg: any) {
    for (const kind of A2UI_TOP_LEVEL_KEYS) {
      if (msg[kind]) {
        return msg[kind].surfaceId;
      }
    }
    return 'default';
  }

  /**
   * Registers Maps content tokens on `google.maps.Settings`.
   */
  async addContentTokens(
      tokens: Record<string, unknown>,
      ): Promise<void> {
    const tokenSet = new Set<string>();
    for (const value of Object.values(tokens)) {
      if (typeof value === 'string' && value.length > 0) {
        tokenSet.add(value);
      } else if (Array.isArray(value)) {
        value.forEach((t) => {
          if (typeof t === 'string' && t.length > 0) {
            tokenSet.add(t);
          }
        });
      }
    }
    if (tokenSet.size === 0) return;
    let settingsClass =
        typeof google !== 'undefined' ? google.maps?.Settings : undefined;
    if (!settingsClass) {
      try {
        const coreLib = await loadMapsLibrary('core');
        settingsClass = coreLib?.Settings;
      } catch (err) {
        console.error('Failed to load Google Maps Core library:', err);
        return;
      }
    }
    const settings = settingsClass?.getInstance() as unknown as | {
      addContentTokens?: (tokens: Iterable<string>) => void;
    }
    |undefined;
    settings?.addContentTokens?.(Array.from(tokenSet));
  }

  /**
   * Processes a response from the A2UI client and updates the timeline.
   */
  processResponse(
      orderedParts: Array<|{
        type: 'text';
        text: string
      }|{
        type: 'a2ui';
        message: any;
        contentTokens?: Record<string, unknown>;
      }>,
  ) {
    const uiMessages: any[] = [];
    const newItems: TimelineItem[] = [];

    for (const part of orderedParts) {
      if (part.type === "text") {
        const lastNewItem = newItems.length > 0 ? newItems[newItems.length - 1] : null;

        let lastTimelineTextIndex = -1;
        for (let j = this.timelineItems.length - 1; j >= 0; j--) {
          if (this.timelineItems[j].type === "text") {
            lastTimelineTextIndex = j;
            break;
          }
        }

        if (lastNewItem && lastNewItem.type === "text") {
          lastNewItem.text += part.text;
        } else if (lastTimelineTextIndex !== -1) {
          const lastTimelineTextItem = this.timelineItems[lastTimelineTextIndex] as { type: "text", text: string };
          const updatedItem = { ...lastTimelineTextItem, text: lastTimelineTextItem.text + part.text };
          this.timelineItems = [
            ...this.timelineItems.slice(0, lastTimelineTextIndex),
            updatedItem,
            ...this.timelineItems.slice(lastTimelineTextIndex + 1)
          ];
        } else {
          newItems.push({ type: "text", text: part.text });
        }
      } else if (part.type === "a2ui") {
        if (part.contentTokens) {
          void this.addContentTokens(part.contentTokens);
        }
        const msg = part.message;
        const rawSurfaceId = this.getSurfaceId(msg);
        if (msg.createSurface && this.getSurface(rawSurfaceId)) {
          this.surfaceIdAliases.set(
              rawSurfaceId,
              `${rawSurfaceId}_${++this.surfaceCollisionCounter}`,
          );
        }
        const surfaceId =
            this.surfaceIdAliases.get(rawSurfaceId) ?? rawSurfaceId;
        for (const kind of A2UI_TOP_LEVEL_KEYS) {
          if (msg[kind]?.surfaceId) {
            msg[kind].surfaceId = surfaceId;
          }
        }
        uiMessages.push(msg);

        // Record the surface in the timeline if it's new
        if (!this.timelineItems.find(t => t.type === "surface" && t.surfaceId === surfaceId) &&
          !newItems.find(t => t.type === "surface" && t.surfaceId === surfaceId)) {
          newItems.push({ type: "surface", surfaceId });
        }
      }
    }

    this.timelineItems = [...this.timelineItems, ...newItems];
    this.messageProcessor.processMessages(uiMessages);

    return newItems;
  }

  /**
   * Adds a user message to the timeline.
   */
  addUserMessage(text: string) {
    this.timelineItems = [...this.timelineItems, { type: "user", text }];
  }
}
