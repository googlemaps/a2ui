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


import {customElement} from 'lit/decorators.js';
import {type PropertyValues} from 'lit';
import {A2UICoreShell} from '../../../mobile_core/web_build/src/core-shell';

(window as any)['A2UI_ATTRIBUTION_ID'] = 'gmp_web_maui_v0.1.7_exp,gmp_ios_maui_v0.1.7_exp';

const PLACE_CARD_THUMBNAIL_MIN_WIDTH = 350;

@customElement('a2ui-shell')
export class IOSA2UIShell extends A2UICoreShell {

  protected override notifyWebpageResized(height: number): void {
      window.webkit?.messageHandlers?.heightObserver?.postMessage(height);
  }

  protected override notifyJsReady(): void {
      window.webkit?.messageHandlers?.iOS?.postMessage({ action: 'onJsReady', data: '' });
  }

  override connectedCallback() {
    super.connectedCallback();
    this.setupGoogleMapIOSFix();
    this.setupPlaceCardIOSFix();
  }

  private setupGoogleMapIOSFix() {
    customElements.whenDefined('a2ui-googlemap').then(() => {
      const GoogleMap = customElements.get('a2ui-googlemap');
      if (!GoogleMap) return;

      const origUpdated = GoogleMap.prototype.updated;
      GoogleMap.prototype.updated = function (changedProperties: PropertyValues) {
        // Fix for iOS crash: Wait for map element to be defined before running updated()
        customElements.whenDefined('gmp-map-3d').then(() => {
          if (origUpdated) origUpdated.call(this, changedProperties);
        });
      };
    });
  }

  private setupPlaceCardIOSFix() {
    customElements.whenDefined('a2ui-placedetailscompact').then(() => {
      const PlaceCard = customElements.get('a2ui-placedetailscompact');
      if (!PlaceCard) return;
      const orig = PlaceCard.prototype.firstUpdated;

      PlaceCard.prototype.firstUpdated = function (changedProperties: PropertyValues) {
        if (orig) orig.call(this, changedProperties);

        const compact = this.renderRoot?.querySelector('gmp-place-details-compact') as HTMLElement | null;
        if (!compact) return;

        new ResizeObserver(() => {
          const parentWidth = this.clientWidth;
          const targetWidth = PLACE_CARD_THUMBNAIL_MIN_WIDTH;

          if (parentWidth > 0 && parentWidth < targetWidth) {
            compact.style.setProperty('width', targetWidth + 'px', 'important');
            compact.style.setProperty('min-width', targetWidth + 'px', 'important');

            const scale = parentWidth / targetWidth;
            compact.style.setProperty('transform-origin', 'top left', 'important');
            compact.style.setProperty('transform', `scale(${scale})`, 'important');

            const height = compact.offsetHeight;
            if (height > 0) {
              compact.style.setProperty('margin-bottom', `-${height * (1 - scale)}px`, 'important');
            }
          } else {
            compact.style.removeProperty('width');
            compact.style.removeProperty('min-width');
            compact.style.removeProperty('transform');
            compact.style.removeProperty('margin-bottom');
          }
        }).observe(this);
      };
    });
  }
}

