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

import {mapsAgenticUICatalog} from './catalog';
import {type GroundingSource} from './custom-components/grounding_sources';

export class MAUIProviders extends LitElement {
  private markdownProvider = new ContextProvider(this, {
    context: Context.markdown,
    initialValue: async (
        markdown: string,
        options?: Types.MarkdownRendererOptions,
        ) => renderMarkdown(markdown, options),
  });

  protected override render() {
    return html`<slot></slot>`;
  }
}

if (!customElements.get('maui-providers')) {
  customElements.define('maui-providers', MAUIProviders);
}

export type TimelineItem =|{
  type: 'text';
  text: string;
  sources?: GroundingSource[]
}
|{
  type: 'user';
  text: string
}
|{
  type: 'action';
  text: string;
  action: string
}
|{
  type: 'surface';
  surfaceId: string;
  sources?: GroundingSource[]
}
|{
  type: 'sources';
  sources: GroundingSource[]
};

const A2UI_TOP_LEVEL_KEYS = [
  'createSurface', 'updateComponents', 'updateDataModel', 'deleteSurface',
  'beginRendering', 'surfaceUpdate', 'dataModelUpdate'
];

export class A2UIRenderer {
  private readonly messageProcessor = new v0_9.MessageProcessor(
      [mapsAgenticUICatalog],
      async(action: v0_9.A2uiClientAction):
          Promise<any> => {
            console.warn('Action handling is unimplemented', action);
          },
  );
  private timelineItems: TimelineItem[] = [];

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
   * Processes a response from the A2UI client and updates the timeline.
   */
  processResponse(
      orderedParts:
          Array<{type: 'text', text: string}|{type: 'a2ui', message: any}>) {
    const uiMessages: any[] = [];
    const newItems: TimelineItem[] = [];

    for (const part of orderedParts) {
      if (part.type === 'text') {
        const lastNewItem =
            newItems.length > 0 ? newItems[newItems.length - 1] : null;

        let lastTimelineTextIndex = -1;
        for (let j = this.timelineItems.length - 1; j >= 0; j--) {
          if (this.timelineItems[j].type === 'text') {
            lastTimelineTextIndex = j;
            break;
          }
        }

        if (lastNewItem && lastNewItem.type === 'text') {
          lastNewItem.text += part.text;
        } else if (lastTimelineTextIndex !== -1) {
          const lastTimelineTextItem =
              this.timelineItems[lastTimelineTextIndex] as
              {type: 'text', text: string};
          const updatedItem = {
            ...lastTimelineTextItem,
            text: lastTimelineTextItem.text + part.text
          };
          this.timelineItems = [
            ...this.timelineItems.slice(0, lastTimelineTextIndex), updatedItem,
            ...this.timelineItems.slice(lastTimelineTextIndex + 1)
          ];
        } else {
          newItems.push({type: 'text', text: part.text});
        }
      } else if (part.type === 'a2ui') {
        if (part.message && part.message.groundingSources) {
          const sources = part.message.groundingSources as GroundingSource[];
          let attached = false;
          for (let i = newItems.length - 1; i >= 0; i--) {
            const item = newItems[i];
            if (item.type === 'surface' || item.type === 'text') {
              item.sources = sources;
              attached = true;
              break;
            }
          }
          if (!attached) {
            for (let i = this.timelineItems.length - 1; i >= 0; i--) {
              const item = this.timelineItems[i];
              if (item.type === 'surface' || item.type === 'text') {
                const updatedItem = {...item, sources};
                this.timelineItems = [
                  ...this.timelineItems.slice(0, i),
                  updatedItem,
                  ...this.timelineItems.slice(i + 1),
                ];
                attached = true;
                break;
              }
            }
          }
          if (!attached) {
            newItems.push({type: 'sources', sources});
          }
          continue;
        }

        uiMessages.push(part.message);
        const surfaceId = this.getSurfaceId(part.message);

        // Record the surface in the timeline if it's new
        if (!this.timelineItems.find(
                t => t.type === 'surface' && t.surfaceId === surfaceId) &&
            !newItems.find(
                t => t.type === 'surface' && t.surfaceId === surfaceId)) {
          newItems.push({type: 'surface', surfaceId});
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
    this.timelineItems = [...this.timelineItems, {type: 'user', text}];
  }
}
