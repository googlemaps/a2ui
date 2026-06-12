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
import {css, html, nothing, unsafeCSS} from 'lit';
import {customElement} from 'lit/decorators.js';
import {styleMap} from 'lit/directives/style-map.js';
import {z} from 'zod'


export const PlaceCardApi = {
  name: 'PlaceCard',
  schema: z
    .object({
      placeId: DynamicStringSchema.describe('The ID of the place to display.'),
    })
    .strict(),
} satisfies ComponentApi;

declare global {
  interface HTMLElementTagNameMap {
    "gmpx-place-details-compact": HTMLElement & {
      place: string | object | null;
    };
  }
}

/** A2UI Custom Component for PlaceCard */
@customElement('a2ui-placecard')
export class PlaceCard extends A2uiLitElement<typeof PlaceCardApi> {
  protected override createController() {
    return new A2uiController(this, PlaceCardApi);
  }

  static styles = [
    unsafeCSS(structuralStyles),
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

    const style = {
      "width": "100%",
    };

    if (!placeId) {
      return nothing;
    }

    return html`
      <section style=${styleMap(style)}>
        <gmp-place-details-compact orientation="horizontal"
            place="${placeId}"
            internal-usage-attribution-ids="gmp_web_maui_v0.1.7_exp">
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

/** A2UI Definition for PlaceCard component */
export const A2uiPlaceCard = {
  ...PlaceCardApi,
  tagName: "a2ui-placecard",
};
