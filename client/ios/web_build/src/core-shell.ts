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


import {css, html, LitElement, nothing, type PropertyValues} from 'lit';
import {state} from 'lit/decorators.js';

import {A2UIRenderer, type TimelineItem, themeStyleSheet} from '@googlemaps/a2ui/lit';

// In single-file Closure bundles where all modules are already inlined,
// register resolved import handlers so dynamic import() calls succeed.
interface GoogDynamicImport {
  setImportHandlerInternalDoNotCallOrElse?:
      (handler: (chunkId: string) => Promise<unknown>) => void;
  setUncompiledChunkIdHandlerInternalDoNotCallOrElse?:
      (handler: (name: string) => string) => void;
}
declare const goog: unknown;
const googDynamicImport =
    typeof goog === 'undefined' ? null : (goog as GoogDynamicImport);
googDynamicImport?.setImportHandlerInternalDoNotCallOrElse?.(
    () => Promise.resolve(null));
googDynamicImport?.setUncompiledChunkIdHandlerInternalDoNotCallOrElse?.(
    (name) => name);

export interface A2UIComponentNode {
  id?: string;
  component: string;
  child?: string;
  children?: string[] | A2UIComponentNode[] | { componentId: string };
  center?: { path?: string; lat?: number; lng?: number };
  [key: string]: unknown;
}

export interface A2UIMessage {
  createSurface?: { surfaceId: string; catalogId: string };
  updateComponents?: { surfaceId?: string; components: A2UIComponentNode[] };
  updateDataModel?: { surfaceId?: string; data?: Record<string, unknown>; value?: Record<string, unknown> };
  version?: string;
  [key: string]: unknown;
}

// Override default A2UI horizontal list styling on narrow mobile WebViews.
// Without explicit scroll and card width bounds, side-by-side cards (such as
// PlaceDetailsCompact) collapse below 350px width and trigger a ResizeObserver
// flickering loop. Since <a2ui-list> renders inside <a2ui-surface>'s Shadow DOM
// with inline styles, these rules use !important and are injected via
// adoptedStyleSheets.
const HORIZONTAL_SCROLL_CSS = css`
  .a2ui-list.horizontal {
    flex-direction: row !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    -webkit-overflow-scrolling: touch !important;
    scroll-snap-type: x mandatory !important;
    padding-bottom: 8px !important;
    scrollbar-width: none !important;
  }
  .a2ui-list.horizontal::-webkit-scrollbar {
    display: none !important;
  }
  .a2ui-list.horizontal > div,
  .a2ui-list.horizontal > .a2ui-list-item-none {
    flex: 0 0 85% !important;
    min-width: 280px !important;
    max-width: 360px !important;
    scroll-snap-align: start !important;
    box-sizing: border-box !important;
  }
  a2ui-placedetailscompact {
    width: 100% !important;
    min-width: 0 !important;
  }
`;

export abstract class A2UICoreShell extends LitElement {
  @state()
  protected timeline: TimelineItem[] = [];

  protected rendererRef = new A2UIRenderer();
  protected globalDataModelRef: Record<string, unknown> = {};
  protected resizeObserver!: ResizeObserver;
  protected timeoutId: ReturnType<typeof setTimeout> | null = null;

  static override styles = [
    themeStyleSheet, css`
    :host {
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100vh;
      overflow-y: auto;
      overflow-x: hidden;
      background: var(--social-bg, #f1f3f4);
    }
    .chat-messages {
      height: auto;
      padding: 16px;
      overflow: visible;
      display: block;
    }
    .surface-message {
      margin-bottom: 16px;
    }
    .loading {
      opacity: 0.5;
      text-align: center;
      margin-top: 20px;
      font-family: sans-serif;
    }
    ${HORIZONTAL_SCROLL_CSS}
  `
  ];

  private static horizontalScrollSheet: CSSStyleSheet|null = null;

  private static getHorizontalScrollSheet(): CSSStyleSheet {
    if (!A2UICoreShell.horizontalScrollSheet) {
      A2UICoreShell.horizontalScrollSheet = new CSSStyleSheet();
      A2UICoreShell.horizontalScrollSheet.replaceSync(
          HORIZONTAL_SCROLL_CSS.cssText);
    }
    return A2UICoreShell.horizontalScrollSheet;
  }

  override connectedCallback() {
    super.connectedCallback();

    // Ensure global typography and Material theme definitions are present on
    // the document
    if (!document.adoptedStyleSheets.includes(themeStyleSheet)) {
      document.adoptedStyleSheets =
          [...document.adoptedStyleSheets, themeStyleSheet];
    }
    const scrollSheet = A2UICoreShell.getHorizontalScrollSheet();
    if (document.adoptedStyleSheets &&
        !document.adoptedStyleSheets.includes(scrollSheet)) {
      document.adoptedStyleSheets =
          [...document.adoptedStyleSheets, scrollSheet];
    }

    this.setupResizer();
    this.notifyJsReady();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
    }
  }

  protected abstract notifyWebpageResized(height: number): void;
  protected abstract notifyJsReady(): void;

  processA2uiMessages(json: unknown) {
    try {
        let messages: A2UIMessage[] = (typeof json === 'string' ? JSON.parse(json) : json) as A2UIMessage[];
        if (typeof messages === 'string') {
            messages = JSON.parse(messages as string) as A2UIMessage[];
        }

        if (!Array.isArray(messages)) {
            messages = [messages];
        }

        // 1. Auto-fix common LLM hallucinated keys ('latitude' -> 'lat',
        // 'title' -> 'label').
        const fixKeys = (obj: any) => {
          if (Array.isArray(obj)) {
            obj.forEach(fixKeys);
          } else if (obj !== null && typeof obj === 'object') {
            if (obj.latitude !== undefined) {
              obj.lat = obj.latitude;
              delete obj.latitude;
            }
            if (obj.longitude !== undefined) {
              obj.lng = obj.longitude;
              delete obj.longitude;
            }
            if (obj.title !== undefined && obj.label === undefined) {
              obj.label = obj.title;
              delete obj.title;
            }
            Object.values(obj).forEach(fixKeys);
          }
        };
        fixKeys(messages);


        // 2. Track global data model and resolve 'path' references (e.g., Paris
        // map bug). We must track the model globally because components and
        // data often arrive in separate SSE chunks.
        let hasUiInstructions = false;
        const UI_KEYS = ['createSurface', 'updateComponents', 'updateDataModel', 'deleteSurface', 'beginRendering', 'surfaceUpdate'];

        messages.forEach((item) => {
            if (UI_KEYS.some(key => Object.prototype.hasOwnProperty.call(item, key))) {
                hasUiInstructions = true;
            }
            if (item.updateDataModel) {
                const payload = item.updateDataModel.data || item.updateDataModel.value;
                if (payload) {
                    this.globalDataModelRef = { ...this.globalDataModelRef, ...payload };
                }
            }
        });

        // 3. Deduplication: Only process this chunk in the WebView IF it
        // contains actual UI instructions. If it's just pure conversational
        // text, we ignore it here because Android's native bubble handles it.
        if (!hasUiInstructions) {
            return;
        }

        const resolvePath = (pathStr: string) => {
          if (!pathStr || !pathStr.startsWith('/')) return null;
          let parts = pathStr.split('/').filter(Boolean);
          let curr: any = this.globalDataModelRef;
          for (let p of parts) {
            if (curr && Object.prototype.hasOwnProperty.call(curr, p))
              curr = curr[p];
            else
              return null;
          }
          return curr;
        };

        const fixGoogleMap = (comp: any) => {
          if (comp.component === 'GoogleMap') {
            if (comp.center && comp.center.path) {
              let resolved = resolvePath(comp.center.path);
              if (resolved) comp.center = resolved;
            }
          }
          if (comp.children && Array.isArray(comp.children)) {
            comp.children.forEach((c: any) => {
              if (typeof c === 'object') fixGoogleMap(c);
            });
          }
        };

        messages.forEach((item: any) => {
          if (item.updateComponents && item.updateComponents.components) {
            let comps = item.updateComponents.components;
            comps.forEach(fixGoogleMap);

            // Ensure 'root' Column exists for the A2UI Renderer
            let hasRoot = comps.some((c: any) => c.id === 'root');
            if (!hasRoot && comps.length > 0) {
              // If no "root" exists, generating a new "root" container.
              let referencedChildIds = new Set<string>();
              comps.forEach((c: any) => {
                if (typeof c.child === 'string')
                  referencedChildIds.add(c.child);
                if (c.children) {
                  if (Array.isArray(c.children)) {
                    c.children.forEach((child: any) => {
                      if (typeof child === 'string')
                        referencedChildIds.add(child);
                      else if (child && typeof child === 'object' && child.id)
                        referencedChildIds.add(child.id);
                    });
                  } else if (
                      typeof c.children === 'object' &&
                      c.children.componentId) {
                    referencedChildIds.add(c.children.componentId);
                  }
                }
              });

              // Filter the components that are not claimed as a child by anyone
              let rootChildren =
                  comps
                      .filter((c: any) => c.id && !referencedChildIds.has(c.id))
                      .map((c: any) => c.id);

              comps.unshift(
                  {id: 'root', component: 'Column', children: rootChildren});
            }
          }
        });

        // Injects a mandatory createSurface command if missing so isolated
        // WebView chunks won't render blank.
        const hasCreate = messages.some((item) => item.createSurface);
        if (!hasCreate) {
            let surfaceId: string | undefined = undefined;
            for (const m of messages) {
                if (m.updateComponents) surfaceId = m.updateComponents.surfaceId;
                if (m.updateDataModel) surfaceId = m.updateDataModel.surfaceId;
                if (surfaceId) break;
            }
            if (surfaceId && !this.rendererRef.getSurface(surfaceId)) {
                messages.unshift({
                    createSurface: {
                        surfaceId,
                        catalogId: 'a2ui://maps-agentic-ui-catalog.json'
                    },
                    version: 'v0.9'
                });
            }
        }

        this.rendererRef.processResponse(messages.map((msg) => ({ type: "a2ui", message: msg })));
        this.timeline = [...this.rendererRef.timeline];
    } catch (e) {
        console.error("Failed to process A2UI JSON:", e);
    }
  }

  private adoptScrollStylesheets() {
    const sheet = A2UICoreShell.getHorizontalScrollSheet();
    const surfaces = this.shadowRoot?.querySelectorAll('a2ui-surface');
    if (!surfaces) return;
    surfaces.forEach((surface) => {
      const sr = surface.shadowRoot;
      if (sr && sr.adoptedStyleSheets &&
          !sr.adoptedStyleSheets.includes(sheet)) {
        sr.adoptedStyleSheets = [...sr.adoptedStyleSheets, sheet];
      }
    });
  }

  private setupResizer() {
    this.resizeObserver = new ResizeObserver(() => {
      this.adoptScrollStylesheets();
      if (this.timeoutId) {
        clearTimeout(this.timeoutId);
      }
      this.timeoutId = setTimeout(() => {
        const rootWrapper = this.shadowRoot?.querySelector('.chat-messages');
        if (rootWrapper) {
          const newHeight = rootWrapper.scrollHeight;
          this.notifyWebpageResized(newHeight);
        }
      }, 100);
    });


    const chatMessagesEl = this.shadowRoot?.querySelector('.chat-messages');
    if (chatMessagesEl) {
      this.resizeObserver.observe(chatMessagesEl);
    }
  }

  protected override updated(changedProperties: PropertyValues) {
    super.updated(changedProperties);

    // Fallback: If setupResizer ran before shadow DOM rendered chat-messages, observe it now.
    const chatMessagesEl = this.shadowRoot?.querySelector('.chat-messages');
    if (chatMessagesEl && this.resizeObserver) {
      this.resizeObserver.observe(chatMessagesEl);
    }

    this.adoptScrollStylesheets();
  }

  override render() {
    return html`
      <div class="chat-messages">
        <maui-providers>
          ${this.timeline.length === 0 ? html`<p class="loading">Waiting for payload...</p>` : nothing}
          ${this.timeline.map((item) => {
            if (item.type === 'surface') {
              const surface = this.rendererRef.getSurface(item.surfaceId);
              if (!surface) return nothing;
              return html`
                <div class="surface-message">
                  <a2ui-surface .surface=${surface}></a2ui-surface>
                </div>
              `;
            }
            return nothing;
          })}
        </maui-providers>
      </div>
    `;
  }
}
