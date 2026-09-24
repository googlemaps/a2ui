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


import {type PropertyValues} from 'lit';
import {customElement} from 'lit/decorators.js';

import {A2UICoreShell} from './core-shell';

(window as any)['A2UI_ATTRIBUTION_ID'] =
    'gmp_web_maui_v0.1.8_atoui,gmp_android_maui_v0.1.8_atoui';

const PLACE_CARD_THUMBNAIL_MIN_WIDTH = 350;

@customElement('a2ui-shell')
export class AndroidA2UIShell extends A2UICoreShell {
  protected override notifyWebpageResized(height: number): void {
    window.Android?.onWebpageResized?.(height);
  }

  protected override notifyJsReady(): void {
    window.Android?.onJsReady?.();
  }

  override connectedCallback() {
    super.connectedCallback();
    this.setupGoogleMapAndroidFix();
    this.setupPlaceCardAndroidFix();
  }

  /**
   * Patches `<a2ui-googlemap>` for Android WebView and SSE streaming:
   * 1. Guards `getCenter()` against undefined `center` props when
   * `updateComponents` arrives before the `center` data chunk in
   * `updateDataModel`.
   * 2. Defers `GoogleMap.prototype.updated()` until `<gmp-map-3d>` is defined
   * by the external Maps 3D script to prevent `AltitudeMode` TypeErrors on
   * early streaming updates.
   * 3. Deduplicates unchanged `markers` and `routes` payloads across streaming
   * chunks to avoid clearing and redrawing map pins on every text/card update.
   * 4. Resets `prevCenter` when the initial coordinates are `(0, 0)` so the
   * camera pans once real coordinates arrive in subsequent `updateDataModel`
   * chunks.
   */
  private setupGoogleMapAndroidFix() {
    customElements.whenDefined('a2ui-googlemap').then(() => {
      const GoogleMap = customElements.get('a2ui-googlemap');
      if (!GoogleMap) return;

      GoogleMap.prototype.getCenter = function() {
        const props = this.controller?.props;
        const center = props?.center;
        if (!center) return {lat: 0, lng: 0};
        const lat = center.lat ?? (center as any).latitude ?? 0;
        const lng = center.lng ?? (center as any).longitude ?? 0;
        return {lat: Number(lat) || 0, lng: Number(lng) || 0};
      };

      const origUpdated = GoogleMap.prototype.updated;
      GoogleMap.prototype.updated = function(
          changedProperties: PropertyValues) {
        // Wait for map element to be defined before running updated()
        customElements.whenDefined('gmp-map-3d').then(() => {
          if (!this.__gmpReadyFired) {
            this.__gmpReadyFired = true;
            this.prevCenter = null;
            this.prevMarkers = null;
            this.prevRoutes = null;
          }
          const props = this.controller?.props;
          if (props) {
            const mJson = JSON.stringify(props.markers || []);
            const rJson = JSON.stringify(props.routes || []);
            if (this.__lastMarkersJson === mJson &&
                this.__lastRoutesJson === rJson) {
              this.prevMarkers = props.markers;
              this.prevRoutes = props.routes;
            } else {
              this.__lastMarkersJson = mJson;
              this.__lastRoutesJson = rJson;
            }
          }
          if (origUpdated) origUpdated.call(this, changedProperties);
          const c = this.getCenter();
          if (c && c.lat === 0 && c.lng === 0) {
            this.prevCenter = null;
          }
        });
      };
    });
  }

  /**
   * Observes `<a2ui-placedetailscompact>` width via `ResizeObserver` and scales
   * down the inner
   * `<gmp-place-details-compact>` element when the parent container is narrower
   * than `PLACE_CARD_THUMBNAIL_MIN_WIDTH` (350px), preventing thumbnail
   * clipping on narrow screens.
   */
  private setupPlaceCardAndroidFix() {
    customElements.whenDefined('a2ui-placedetailscompact').then(() => {
      const PlaceCard = customElements.get('a2ui-placedetailscompact');
      if (!PlaceCard) return;
      const orig = PlaceCard.prototype.firstUpdated;

      PlaceCard.prototype.firstUpdated = function(
          changedProperties: PropertyValues) {
        if (orig) orig.call(this, changedProperties);

        const compact = this.renderRoot?.querySelector(
                            'gmp-place-details-compact') as HTMLElement |
            null;
        if (!compact) return;

        new ResizeObserver(() => {
          const parentWidth = this.clientWidth;
          const targetWidth = PLACE_CARD_THUMBNAIL_MIN_WIDTH;

          if (parentWidth > 0 && parentWidth < targetWidth) {
            compact.style.setProperty('width', targetWidth + 'px', 'important');
            compact.style.setProperty(
                'min-width', targetWidth + 'px', 'important');

            const scale = parentWidth / targetWidth;
            compact.style.setProperty(
                'transform-origin', 'top left', 'important');
            compact.style.setProperty(
                'transform', `scale(${scale})`, 'important');

            const height = compact.offsetHeight;
            if (height > 0) {
              compact.style.setProperty(
                  'margin-bottom', `-${height * (1 - scale)}px`, 'important');
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
