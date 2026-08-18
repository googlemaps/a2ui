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

import {A2uiController, A2uiLitElement} from '@a2ui/lit/v0_9';
import {structuralStyles} from '@a2ui/web_core';
import {ComponentApi, DynamicStringSchema} from '@a2ui/web_core/v0_9';
import {css, html, LitElement, nothing} from 'lit';
import {customElement} from 'lit/decorators.js';
import {styleMap} from 'lit/directives/style-map.js';
import {z} from 'zod'

const sheet = new CSSStyleSheet();
sheet.replaceSync(structuralStyles);

export const PlaceDetailsCompactApi = {
  name: 'PlaceDetailsCompact',
  schema: z
    .object({
      placeId: DynamicStringSchema.describe('The ID of the place to display.'),
      orientation: z
        .enum(['horizontal', 'vertical'])
        .optional()
        .default('horizontal')
        .describe('The orientation of the place card.'),
    })
    .strict(),
} satisfies ComponentApi;

declare global {
  interface HTMLElementTagNameMap {
    "gmpx-place-details-compact": HTMLElement & {
      place: string | object | null;
      orientation: "horizontal" | "vertical";
    };
  }
}

/** A2UI Custom Component for PlaceDetailsCompact */
@customElement('a2ui-placedetailscompact')
export class PlaceDetailsCompact extends
    A2uiLitElement<typeof PlaceDetailsCompactApi> {
  static override shadowRootOptions: ShadowRootInit = {
    ...LitElement.shadowRootOptions,
    mode: 'closed',
  };

  protected override createController() {
    return new A2uiController(this, PlaceDetailsCompactApi);
  }

  static override styles = [
    sheet,
    css`
      :host {
        display: block;
        width: 100%;
      }
      gmp-place-details-compact {
        color-scheme: var(--color-scheme);
        --gmpx-color-scheme: var(--color-scheme);
      }
    `,
  ];

  override render() {
    const props = this.controller.props;
    if (!props) return nothing;

    const placeId = props.placeId;

    // Default to 'vertical' if this is the only a2ui-placedetailscompact component among its siblings,
    // otherwise default to 'horizontal'. AI can still override this.
    const siblingCards = Array.from(this.parentElement?.children || [])
      .filter(c => c.tagName.toLowerCase() === 'a2ui-placedetailscompact');
    const autoOrientation = siblingCards.length === 1 ? 'vertical' : 'horizontal';

    const orientation = (props.orientation ?? autoOrientation).toUpperCase() as google.maps.places.PlaceDetailsOrientationString;

    const style = {
      'width': '100%',
    };

    if (!placeId) {
      return nothing;
    }

    return html`
      <section style=${styleMap(style)}>
        <gmp-place-details-compact orientation="${orientation}"
            place="${placeId}"
            internal-usage-attribution-ids="${
        (window as any)['A2UI_ATTRIBUTION_ID'] || 'gmp_web_maui_v0.1.7_exp'}">
          <gmp-place-details-place-request place="${placeId}">
          </gmp-place-details-place-request>
            <gmp-place-content-config>
              <gmp-place-media lightbox-preferred></gmp-place-media>
              <gmp-place-rating></gmp-place-rating>
              <gmp-place-type></gmp-place-type>
              <gmp-place-price></gmp-place-price>
              <gmp-place-accessible-entrance-icon></gmp-place-accessible-entrance-icon>
              <gmp-place-attribution
                  light-scheme-color="gray"
                  dark-scheme-color="white"></gmp-place-attribution>
            </gmp-place-content-config>
        </gmp-place-details-compact>
      </section>
    `;
  }
}

/** A2UI Definition for PlaceDetailsCompact component */
export const A2uiPlaceDetailsCompact = {
  ...PlaceDetailsCompactApi,
  tagName: 'a2ui-placedetailscompact',
};
