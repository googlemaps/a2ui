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
import {ComponentApi, DynamicBooleanSchema, DynamicStringListSchema, DynamicStringSchema,} from '@a2ui/web_core/v0_9';
import {ContextConsumer} from '@lit/context';
import {css, html, LitElement, nothing} from 'lit';
import {customElement, property} from 'lit/decorators.js';
import {styleMap} from 'lit/directives/style-map.js';
import {z} from 'zod';

import {attributionIdsContext, attributionIdsConverter, resolveAttributionIds} from './attribution';
import {loadMapsLibrary} from './maps_api_loader';

const sheet = new CSSStyleSheet();
sheet.replaceSync(structuralStyles);

enum UIStrings {
  PLACE_LIST = 'Place List',
}

export const AdvancedPlaceListApi = {
  name: 'AdvancedPlaceList',
  schema:
      z.object({
         places: DynamicStringListSchema.describe(
             'An array of place resource names or place IDs to display.',
             ),
         orientation: z.union([
                         z.enum(['horizontal', 'vertical']),
                         ...DynamicStringSchema.options,
                       ])
                          .optional()
                          .default('vertical')
                          .describe('The orientation of the place list.'),
         selectable: DynamicBooleanSchema.optional().default(false).describe(
             'Whether or not the list items are selectable buttons.'),
         truncationPreferred:
             DynamicBooleanSchema.optional().default(true).describe(
                 'Whether or not text fields in list items are truncated.'),
       }).strict(),
} satisfies ComponentApi;

/** Declared so Closure Compiler does not rename these schema keys. */
export declare interface AdvancedPlaceListProps {
  places: string[];
  orientation?: 'horizontal'|'vertical'|{value?: string};
  selectable?: boolean;
  truncationPreferred?: boolean;
}

interface GmpAdvancedPlaceListElement extends HTMLElement {
  places?: string|Iterable<string>;
  orientation?: string;
  selectable?: boolean;
  truncationPreferred?: boolean;
  attributionPosition?: string;
  internalUsageAttributionIds?: string|Iterable<string>;
  'truncation-preferred'?: boolean;
  'attribution-position'?: string;
  'internal-usage-attribution-ids'?: string;
}

interface GmpPlaceNameElement extends HTMLElement {}

interface GmpPlaceLinkElement extends HTMLElement {
  action?: string;
}

declare global {
  interface HTMLElementTagNameMap {
    'gmp-advanced-place-list': GmpAdvancedPlaceListElement;
    'gmp-place-name': GmpPlaceNameElement;
    'gmp-place-link': GmpPlaceLinkElement;
  }
}

/**
 * A2UI Custom Component wrapping Google Maps Places UI Kit
 * `<gmp-advanced-place-list>`.
 */
@customElement('a2ui-advancedplacelist')
export class AdvancedPlaceList extends
    A2uiLitElement<typeof AdvancedPlaceListApi> {
  static override shadowRootOptions: ShadowRootInit = {
    ...LitElement.shadowRootOptions,
    mode: 'closed',
  };

  /**
   * Maps JS API usage attribution IDs to send in addition to MAUI's own ID,
   * e.g. to identify the product embedding MAUI.
   */
  @property({
    attribute: 'additional-attribution-ids',
    converter: attributionIdsConverter,
  })
  additionalAttributionIds: readonly string[] = [];

  /** Attribution IDs provided by an ancestor `<maui-providers>`. */
  private readonly attributionIdsConsumer = new ContextConsumer(this, {
    context: attributionIdsContext,
    subscribe: true,
  });

  protected override createController() {
    return new A2uiController(this, AdvancedPlaceListApi);
  }

  override connectedCallback(): void {
    super.connectedCallback();
    void loadMapsLibrary('places').catch((err) => {
      console.error('Failed to load Google Maps Places library:', err);
    });
  }

  static override styles = [
    sheet,
    css`
      :host {
        display: block;
        width: 100%;
      }
      gmp-advanced-place-list {
        display: block;
        width: 100%;
        height: auto;
        color-scheme: var(--color-scheme);
        --gmpx-color-scheme: var(--color-scheme);
      }
    `,
  ];

  override render() {
    const props =
        this.controller.props as | Partial<AdvancedPlaceListProps>| undefined;
    if (!props || !Array.isArray(props.places)) return nothing;

    const placeIds =
        props.places.filter((p): p is string => typeof p === 'string')
            .map((p) => p.trim())
            .filter(Boolean)
            .map((p) => (p.startsWith('places/') ? p : `places/${p}`));

    if (placeIds.length === 0) {
      return nothing;
    }

    const placesStr = placeIds.join(' ');
    const rawOrientation = typeof props.orientation === 'string' ?
        props.orientation :
        props.orientation?.value;
    const orientation = (rawOrientation || 'vertical').toUpperCase();
    const isSelectable = Boolean(props.selectable);
    const isTruncationPreferred = props.truncationPreferred !== false;
    const style = {
      'width': '100%',
    };
    const attributionIds = resolveAttributionIds(
                               this.attributionIdsConsumer.value,
                               this.additionalAttributionIds,
                               )
                               .join(',');

    return html`
      <section aria-label="${UIStrings.PLACE_LIST}" style=${styleMap(style)}>
        <gmp-advanced-place-list
          style="width: 100%; height: auto;"
          places="${placesStr}"
          orientation="${orientation}"
          ?selectable=${isSelectable}
          ?truncation-preferred=${isTruncationPreferred}
          attribution-position="bottom"
          internal-usage-attribution-ids="${attributionIds}">
          <template slot="details-item">
            <gmp-place-name></gmp-place-name>
            <gmp-place-rating></gmp-place-rating>
            <gmp-place-price></gmp-place-price>
            <gmp-place-accessible-entrance-icon></gmp-place-accessible-entrance-icon>
            <gmp-place-open-now-status></gmp-place-open-now-status>
            <gmp-place-media lightbox-preferred></gmp-place-media>
            <gmp-place-link
              action="open-map"
              slot="action-corner"></gmp-place-link>
          </template>
          <gmp-place-attribution
            light-scheme-color="gray"
            dark-scheme-color="white"></gmp-place-attribution>
        </gmp-advanced-place-list>
      </section>
    `;
  }
}

/** A2UI Definition for AdvancedPlaceList component */
export const A2uiAdvancedPlaceList = {
  ...AdvancedPlaceListApi,
  tagName: 'a2ui-advancedplacelist',
};
