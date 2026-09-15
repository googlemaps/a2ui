/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {css, html, LitElement, nothing} from 'lit';
import {customElement, property, state} from 'lit/decorators.js';

export interface GroundingSource {
  title: string;
  url: string;
  type?: string;
  placeId?: string;
}

const GOOGLE_MAPS_PIN_DATA_URL =
    'data:image/png;base64,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' +
    'AASUVORK5CYII=';

@customElement('maui-grounding-sources')
export class MauiGroundingSources extends LitElement {
  @property({type: Array}) sources: GroundingSource[] = [];

  @state() private isExpanded: boolean = false;

  static override styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;
      margin-top: 8px;
    }

    .grounding-sources-section {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      width: 100%;
    }

    .grounding-sources-toggle-btn {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 5px 12px;
      background: light-dark(var(--n-95, #f1f3f4), var(--n-20, #2d2e30));
      border-radius: 9999px;
      border: none;
      font-family: inherit;
      font-size: 0.75rem;
      font-weight: 600;
      color: light-dark(var(--n-10, #202124), var(--n-90, #e8eaed));
      cursor: pointer;
      user-select: none;
      transition: background-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }

    .grounding-sources-toggle-btn:hover {
      background: light-dark(var(--n-90, #e8eaed), var(--n-30, #3c4043));
      color: light-dark(var(--n-0, #000000), #ffffff);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    }

    .grounding-sources-toggle-btn:focus-visible {
      outline: 2px solid light-dark(#1a73e8, #8ab4f8);
      outline-offset: 1px;
    }

    .sources-btn-label {
      line-height: 1;
    }

    .sources-btn-cluster {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .google-maps-pin-logo {
      object-fit: contain;
      flex-shrink: 0;
      display: inline-block;
      vertical-align: middle;
      width: 15px;
      height: 15px;
    }

    .sources-btn-count {
      font-size: 0.75rem;
      font-weight: 600;
      line-height: 1;
      color: var(--a2ui-primary-color, light-dark(#1a73e8, #8ab4f8));
    }

    .sources-chevron-icon {
      font-size: 0.7rem;
      line-height: 1;
      transition: transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);
      display: inline-block;
    }

    .sources-chevron-icon.rotated {
      transform: rotate(180deg);
    }

    .grounding-sources-drawer {
      width: 100%;
      margin-top: 8px;
      overflow: hidden;
      transition: max-height 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease;
    }

    .grounding-sources-drawer.collapsed {
      max-height: 0;
      opacity: 0;
      margin-top: 0;
      pointer-events: none;
    }

    .grounding-sources-drawer.expanded {
      max-height: 2000px;
      opacity: 1;
    }

    .grounding-sources-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      width: 100%;
      padding: 4px 2px 6px 2px;
      box-sizing: border-box;
    }

    .grounding-sources-grid.single-item {
      grid-template-columns: minmax(0, 240px);
    }

    @media (max-width: 400px) {
      .grounding-sources-grid {
        grid-template-columns: 1fr;
      }
    }

    .grounding-source-card {
      background: light-dark(var(--n-95, #f1f3f4), var(--n-20, #2d2e30));
      border: none;
      border-radius: 16px;
      padding: 9px 12px 10px 12px;
      text-decoration: none;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      gap: 6px;
      min-height: 64px;
      box-sizing: border-box;
      transition: background-color 0.15s ease;
      cursor: pointer;
      position: relative;
    }

    .grounding-source-card:hover {
      background: light-dark(var(--n-90, #e8eaed), var(--n-30, #3c4043));
    }

    .grounding-source-card:hover .grounding-source-title {
      color: var(--a2ui-primary-color, light-dark(#1a73e8, #8ab4f8));
    }

    .grounding-source-card:active {
      background: light-dark(var(--n-80, #dadce0), var(--n-40, #525252));
    }

    .grounding-source-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      width: 100%;
    }

    .grounding-source-meta {
      display: flex;
      align-items: center;
      gap: 5px;
      min-width: 0;
    }

    .GMP-attribution {
      font-style: normal;
      font-weight: 500;
      font-size: 0.68rem;
      letter-spacing: normal;
      white-space: nowrap;
      color: light-dark(var(--slate-550, #64748b), var(--n-70, #9e9e9e));
      line-height: 1.2;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .grounding-source-title {
      font-size: 0.75rem;
      font-weight: 600;
      line-height: 1.25;
      color: light-dark(var(--slate-900, #0f172a), var(--n-100, #ffffff));
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      text-overflow: ellipsis;
      word-break: break-word;
      text-align: left;
      flex: 1;
      transition: color 0.15s ease;
    }
  `;

  private toggleExpanded() {
    this.isExpanded = !this.isExpanded;
  }

  override render() {
    if (!this.sources || this.sources.length === 0) {
      return nothing;
    }

    return html`
      <section class="grounding-sources-section" aria-label="Grounding Sources">
        <button
          type="button"
          class="grounding-sources-toggle-btn"
          @click=${this.toggleExpanded}
          aria-expanded="${this.isExpanded}"
        >
          <span class="sources-btn-label">Sources</span>
          <span class="sources-btn-cluster">
            <img
              src="${GOOGLE_MAPS_PIN_DATA_URL}"
              alt=""
              class="google-maps-pin-logo"
              aria-hidden="true"
            />
            <span class="sources-btn-count">${this.sources.length}</span>
          </span>
          <svg
            class="sources-chevron-icon ${this.isExpanded ? 'rotated' : ''}"
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </button>

        <div class="grounding-sources-drawer ${
        this.isExpanded ? 'expanded' : 'collapsed'}">
          <div class="grounding-sources-grid ${
        this.sources.length === 1 ? 'single-item' : ''}" role="list">
            ${
        this.sources.map(
            (source) => html`
                <a
                  class="grounding-source-card"
                  href="${source.url}"
                  target="_blank"
                  rel="noopener noreferrer"
                  role="listitem"
                  title="View ${source.title} on Google Maps"
                >
                  <div class="grounding-source-header">
                    <div class="grounding-source-meta">
                      <img
                        src="${GOOGLE_MAPS_PIN_DATA_URL}"
                        alt=""
                        class="google-maps-pin-logo"
                        aria-hidden="true"
                      />
                      <span class="GMP-attribution" translate="no">Google Maps</span>
                    </div>
                  </div>
                  <div class="grounding-source-title" title="${source.title}">${
                source.title}</div>
                </a>
              `)}
          </div>
        </div>
      </section>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'maui-grounding-sources': MauiGroundingSources;
  }
}
