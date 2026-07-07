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
import {ComponentApi, DynamicNumberSchema, DynamicStringSchema} from '@a2ui/web_core/v0_9';
import {css, html, LitElement, nothing, PropertyValues} from 'lit';
import {customElement} from 'lit/decorators.js';
import {styleMap} from 'lit/directives/style-map.js';
import {z} from 'zod';

const sheet = new CSSStyleSheet();
sheet.replaceSync(structuralStyles);

const LatLngSchema = z.object({
  lat: DynamicNumberSchema,
  lng: DynamicNumberSchema,
}).strict();

const DynamicLatLngSchema = z.union([
  LatLngSchema,
  z.object({ path: z.string() }).strict(),
]);

const MapPinSchema = z.object({
  lat: DynamicNumberSchema,
  lng: DynamicNumberSchema,
  label: DynamicStringSchema,
  placeId: DynamicStringSchema.optional(),
}).strict();

/** A2UI GoogleMap interface. */
export const GoogleMapApi = {
  name: 'GoogleMap',
  schema: z
    .object({
      center: DynamicLatLngSchema.describe('The center point of the map.'),
      zoom: DynamicNumberSchema.describe('The zoom level.'),
      tilt: DynamicNumberSchema.describe('The tilt angle.').optional(),
      heading: DynamicNumberSchema.describe('The heading angle.').optional(),
      mode: z.enum(['roadmap', 'satellite']).default('roadmap').describe('The map mode.').optional(),
      anchorMarker: MapPinSchema.describe('The anchor marker location.').optional(),
      markers: z.array(MapPinSchema).describe('List of markers.').optional(),
      origin: DynamicLatLngSchema.describe('Origin for routes.').optional(),
      destination: DynamicLatLngSchema.describe('Destination for routes.').optional(),
      travelMode: z.enum(['driving', 'walking', 'bicycling', 'transit']).describe('Travel mode for routes.').optional(),
      routes: z.array(z.object({
        origin: MapPinSchema,
        destination: MapPinSchema,
      })).describe('Array of routes.').optional(),
    })
    .strict(),
} satisfies ComponentApi;

declare global {

  interface Map3DElement {
    center: { lat: number, lng: number, altitude?: number };
    range: number;
    tilt: number;
    heading: number;
    maxTilt: number;
    flyCameraTo(options: {
      endCamera: {
        center: { lat: number; lng: number; altitude: number };
        tilt?: number;
        heading?: number;
        altitudeMode: string;
      };
    }): void;
  }

  interface HTMLElementTagNameMap {
    "gmp-map-3d": HTMLElement & Map3DElement;
    "gmp-advanced-marker": HTMLElement & {
      position: google.maps.LatLng | google.maps.LatLngLiteral;
    };
    "gmp-marker-3d": HTMLElement & {
      position: { lat: number, lng: number, altitude?: number };
    };
  }
}

interface ResolvedMarker {
  lat: number;
  lng: number;
  label: string;
  placeId?: string;
  collisionBehavior?: google.maps.CollisionBehavior;
}

/** A2UI Custom Component for GoogleMap */
@customElement("a2ui-googlemap")
export class GoogleMap extends A2uiLitElement<typeof GoogleMapApi> {
  static override shadowRootOptions: ShadowRootInit = {
    ...LitElement.shadowRootOptions,
    mode: 'closed',
  };

  get map3dElement(): HTMLElement&Map3DElement {
    return this.renderRoot.querySelector('gmp-map-3d') as HTMLElement &
        Map3DElement;
  }

  protected override createController() {
    return new A2uiController(this, GoogleMapApi);
  }

  private markers: HTMLElement[] = [];
  private prevCenter: { lat: number; lng: number } | null = null;
  private prevMarkers: unknown = null;
  private prevRoutes: unknown = null;

  static override styles = [
    sheet,
    css`
      :host {
        display: block;
        height: 400px;
        width: 100%;
      }
      gmp-map-3d {
        height: 400px;
        display: block;
        width: 100%;
      }
    `,
  ];

  getCenter() {
    const props = this.controller.props;
    if (!props) return { lat: 0, lng: 0 };

    const center = props.center;

    const lat = center.lat ?? (center as any).latitude ?? 0;
    const lng = center?.lng ?? (center as any).longitude ?? 0;
    return { lat: lat as number, lng: lng as number };
  }

  private resolveMarkers(): ResolvedMarker[] {
    const props = this.controller.props;
    if (!props || !props.markers) return [];

    const markers = props.markers;

    function filterMarkerFn(marker: any): boolean {
      return !!marker.lat || !!marker.lng || !!marker.placeId || !!marker.label;
    }

    if (Array.isArray(markers)) {
      return markers.map((marker: any) => ({
        lat: marker.lat ?? 0 as number,
        lng: marker.lng ?? 0 as number,
        label: marker.label as string,
        placeId: marker.placeId as string,
        collisionBehavior: marker.collisionBehavior as google.maps.CollisionBehavior | undefined,
      })).filter(filterMarkerFn);
    }

    return [];
  }

  private create3DMarkerElement({ position, placeId, label, zIndex, collisionBehavior }: {
    position?: google.maps.LatLngLiteral,
    placeId?: string | null,
    label?: string | null,
    zIndex?: number | null,
    collisionBehavior?: google.maps.CollisionBehavior,
  }) {
    const marker = document.createElement("gmp-marker-3d") as any;
    marker.autofitsCamera = true;

    position && (marker.position = position);
    placeId && (marker.placeId = placeId);
    label && (marker.label = label);
    collisionBehavior && (marker.collisionBehavior = collisionBehavior);
    (zIndex != null) && (marker.zIndex = zIndex);

    return marker;
  }

  override updated(changedProperties: PropertyValues): void {
    super.updated(changedProperties);
    const props = this.controller.props;
    if (!props) return;

    const center = this.getCenter();
    const markers = props.markers;
    const routes = props.routes;

    if (center && (!this.prevCenter || this.prevCenter.lat !== center.lat || this.prevCenter.lng !== center.lng)) {
      console.log('updating camera');
      this.map3dElement.flyCameraTo({
        endCamera: {
          center: { lat: center.lat, lng: center.lng, altitude: 2400 },
          tilt: this.map3dElement.tilt,
          heading: this.map3dElement.heading,
          altitudeMode: (google as any).maps.maps3d.AltitudeMode.RELATIVE_TO_GROUND
        }
      });
      this.prevCenter = { lat: center.lat, lng: center.lng };
    }

    if (markers !== this.prevMarkers || routes !== this.prevRoutes) {
      this.prevMarkers = markers;
      this.prevRoutes = routes;
      this.updateMarkers();
    }
  }

  private async updateMarkers() {
    const props = this.controller.props;
    if (!props || !this.map3dElement) return;

    // Clear existing markers
    this.markers.forEach(marker => marker.remove());
    this.markers = [];

    const markers = this.resolveMarkers();
    const anchorMarker = props.anchorMarker;
    const destination = props.destination;
    const routes = props.routes || [];

    // Add markers from props.markers
    for (const { lat, lng, label, placeId } of markers) {
      const marker = this.create3DMarkerElement({
        position: { lat, lng },
        placeId,
        label,
      });
      this.map3dElement.appendChild(marker);
      this.markers.push(marker);
    }

    // Add destination marker if available
    if (destination) {
      const marker = this.create3DMarkerElement({
        position: { lat: destination.lat as number, lng: destination.lng as number },
        label: 'Destination',
      });
      this.map3dElement.appendChild(marker);
      this.markers.push(marker);
    }

    // Add anchor marker if available and no routes
    if (anchorMarker && !routes.length) {
      const marker = this.create3DMarkerElement({
        position: { lat: anchorMarker.lat as number, lng: anchorMarker.lng as number },
        placeId: anchorMarker.placeId as string,
        label: anchorMarker.label as string,
        zIndex: 1,
      });
      if (typeof google !== "undefined" && google.maps && google.maps.marker && google.maps.marker.PinElement) {
        const pin = new google.maps.marker.PinElement({
          background: "#5b99f6ff",
          borderColor: "#2f79e8ff",
          glyphColor: "#ffffff"
        });
        marker.append(pin as any);
      }
      this.map3dElement.appendChild(marker);
      this.markers.push(marker);
    }

    // Add pins for each route origin and destination
    for (const route of routes) {
      const originMarker = this.create3DMarkerElement({
        position: { lat: route.origin.lat as number, lng: route.origin.lng as number },
        label: route.origin.label as string || "Origin",
        collisionBehavior: google.maps.CollisionBehavior.OPTIONAL_AND_HIDES_LOWER_PRIORITY,
        placeId: route.origin.placeId as string,
      });
      this.map3dElement.appendChild(originMarker);
      this.markers.push(originMarker);

      const destMarker = this.create3DMarkerElement({
        position: { lat: route.destination.lat as number, lng: route.destination.lng as number },
        label: route.destination.label as string || "Destination",
        collisionBehavior: google.maps.CollisionBehavior.OPTIONAL_AND_HIDES_LOWER_PRIORITY,
        placeId: route.destination.placeId as string,
      });
      this.map3dElement.appendChild(destMarker);
      this.markers.push(destMarker);
    }
  }

  override render() {
    const props = this.controller.props;
    if (!props) return nothing;

    const center = this.getCenter();
    const lat = center.lat ?? (center as any).latitude;
    const lng = center.lng ?? (center as any).longitude;

    let zoom = props.zoom ?? 8;
    if (zoom > 16) {
      zoom = 16;
    }
    const heading = props.heading ?? 0;
    const mode = props.mode ?? 'roadmap';

    let tilt = props.tilt ?? 0;
    if (mode !== 'satellite') {
      tilt = 0;
    }

    const routes = props.routes || [];

    const style = {
      "height": "400px",
      "width": "100%",
      "margin-bottom": "16px",
      "border-radius": "16px",
      "overflow": "hidden",
      "border": "1px solid var(--gmp-mat-color-outline-decorative, light-dark(#ccc, #333))"
    };

    return html`
      <section style=${styleMap(style)}>
        <gmp-map-3d
          center="${lat},${lng},0"
          tilt="${tilt}"
          mode="${mode}"
          max-tilt=${mode === 'roadmap' ? '0' : nothing}
          heading="${heading}"
          map-id="2d6e1a27a57efe3c9479f6fc"
          internal-usage-attribution-ids="${(window as any).A2UI_ATTRIBUTION_ID || 'gmp_web_maui_v0.1.7_exp'}"
        >${routes.map((route: any) => html`
          <gmp-route-3d
            origin="${route.origin.lat},${route.origin.lng}"
            destination="${route.destination.lat},${route.destination.lng}"
            autofits-camera
            internal-usage-attribution-ids="${(window as any).A2UI_ATTRIBUTION_ID || 'gmp_web_maui_v0.1.7_exp'}"
          ></gmp-route-3d>`)}
        </gmp-map-3d>
      </section>
    `;
  }
}

/** A2UI Definition for GoogleMap component */
export const A2uiGoogleMap = {
  ...GoogleMapApi,
  tagName: "a2ui-googlemap",
};
