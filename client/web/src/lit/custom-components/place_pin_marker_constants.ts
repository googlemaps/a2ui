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

import {css, CSSResult} from 'lit';

const SVG_RETAIL =
    `<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10" fill="none">
<path fill-rule="evenodd" clip-rule="evenodd" d="M5 0C7.67875 0 7.86793 3.73587 8 4H9L10 10H0L1 4H2C2.21417 1.33333 3.21417 0 5 0ZM4.00122 6H3C2.9989 7.33333 3.66557 8 5 8C6.33443 8 7.0011 7.33333 7 6H6C6.01619 6.6724 5.68301 7.00574 5.00044 7C4.31787 6.99426 3.9848 6.66093 4.00122 6ZM5 1C3.73413 1 3.06746 2 3 4H7C6.93254 2 6.26587 1 5 1Z" fill="white"/>
</svg>`;
const SVG_FOOD_AND_DRINK =
    `<svg xmlns="http://www.w3.org/2000/svg" width="9" height="11" viewBox="0 0 9 11" fill="none">
  <path d="M6.5 2.53846V6H8.00226V11H9V0C7.49455 0 6.5 1.46316 6.5 2.53846ZM4 3.5H3V0H2V3.5H1V0H0V3.5C0 4.74667 0.84 6 2.04545 6V11H3V6C4.20545 6 5.0005 4.74667 5.0005 3.5V0H4V3.5Z" fill="white"/>
</svg>`;
const SVG_OUTDOOR =
    `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M4.79526 7.39011C4.77026 7.26411 4.75626 7.13311 4.75626 7.00011C4.75626 6.41911 5.00726 5.90111 5.40226 5.53511C4.70326 4.66511 3.33226 3.78411 2.61826 3.55211C1.56826 3.21111 0.440262 3.78611 0.0982625 4.83711C-0.242737 5.88711 0.332263 7.01511 1.38226 7.35711C2.09526 7.58811 3.71826 7.68111 4.79526 7.39011Z" fill="white"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M4.94388 7.83496C3.89988 8.23096 2.63988 9.26196 2.19888 9.86896C1.54988 10.763 1.74788 12.014 2.64188 12.663C3.53488 13.312 4.78588 13.114 5.43488 12.22C5.87788 11.611 6.45988 10.091 6.50988 8.97496C5.81288 8.88896 5.22788 8.44896 4.94388 7.83496Z" fill="white"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M8.56795 7.83496C8.28395 8.44896 7.69895 8.88896 7.00195 8.97496C7.05195 10.091 7.63395 11.611 8.07695 12.22C8.72595 13.114 9.97695 13.312 10.87 12.663C11.764 12.014 11.962 10.763 11.313 9.86896C10.872 9.26196 9.61195 8.23096 8.56795 7.83496Z" fill="white"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M13.4133 4.83659C13.0723 3.78659 11.9433 3.21159 8.10925 5.53559C8.50425 5.90059 8.75625 6.41959 8.75625 6.99959C8.75625 7.13359 8.74125 7.26359 8.71625 7.38959C9.79425 7.68159 11.4163 7.58859 12.1293 7.35659C13.1793 7.01559 13.7543 5.88759 13.4133 4.83659Z" fill="white"/>
  <mask id="mask0_13572_628" style="mask-type:luminance" maskUnits="userSpaceOnUse" x="4" y="0" width="5" height="6">
    <path d="M4.75586 0H8.75586V5.2628H4.75586V0Z" fill="#0000FF"/>
  </mask>
  <g mask="url(#mask0_13572_628)">
    <path fill-rule="evenodd" clip-rule="evenodd" d="M6.75586 -0.000289917C5.65086 -0.000289917 4.75586 0.89471 4.75586 1.99971C4.75586 2.75071 5.17086 4.32871 5.78286 5.26271C6.07186 5.09971 6.40086 4.99971 6.75586 4.99971C7.11086 4.99971 7.43986 5.09971 7.72886 5.26271C8.34086 4.32871 8.75586 2.75071 8.75586 1.99971C8.75586 0.89471 7.86086 -0.000289917 6.75586 -0.000289917Z" fill="white"/>
  </g>
</svg>`;
const SVG_SERVICE =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M11.9942 12.5H14V9.50323H12L11.9942 12.5ZM18 8.5V9.49518H17V12.5H18C18 13.5 17 13.5241 17 13.5241L16 13.5V8.5C16 8 15.5 7.5 15 7.5H11C10.5 7.5 10 8 10 8.5V16.5H9V17.5H9.90909H16.2727H17V16.5H16V14.5H17C17.7864 14.5 19 14.2982 19 12.5V12.0455V9.31818V8.5H18Z" fill="white"/>
</svg>`;
const SVG_LODGING =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M19 10V12C19 12 18.0076 10 13.9999 10V14H9V9H8V17H9V15H19V17H20V10H19Z" fill="white"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M13 11.5C13 10.672 12.328 10 11.5 10C10.672 10 10 10.672 10 11.5C10 12.328 10.672 13 11.5 13C12.328 13 13 12.328 13 11.5Z" fill="white"/>
</svg>`;
const SVG_EMERGENCY =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="30" viewBox="0 0 28 30" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M16 6.5V10.499H11.999V6.5H10V10.499V12.499V16.5H11.999V12.499H16V16.5H18V6.5H16Z" fill="white"/>
</svg>`;
const SVG_ENTERTAINMENT =
    `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="10" viewBox="0 0 12 10" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M4 7H5V6H4V7ZM1 7H2V6H1V7ZM0 3V7C0 7 0 10 3 10C6 10 6 7 6 7V3C6 3 5 4 3 4C1 4 0 3 0 3Z" fill="white"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M10 4H11V3H10V4ZM9 1C7 1 6 0 6 0V2H7V3H8V4H7V6.324C7.442 6.716 8.079 7 9 7C12 7 12 4 12 4V0C12 0 11 1 9 1Z" fill="white"/>
</svg>`;
const SVG_GENERIC =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M18 12C18 14.209 16.209 16 14 16C11.791 16 10 14.209 10 12C10 9.791 11.791 8 14 8C16.209 8 18 9.791 18 12Z" fill="white"/>
</svg>`;
const SVG_AIRPORT =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M13 7C13 7 13 6 14 6C15 6 15 7 15 7V10L20 13V14L15 13V15L17 17V18L15 17H13L11 18V17L13 15V13L8 14V13L13 10V7Z" fill="white"/>
</svg>`;
const SVG_PARKING =
    `<svg xmlns="http://www.w3.org/2000/svg" width="6" height="9" viewBox="0 0 6 9" fill="none">
  <path d="M0 8.592V0H3.024C3.576 0 4.072 0.116 4.512 0.348C4.952 0.572 5.3 0.888 5.556 1.296C5.82 1.704 5.952 2.176 5.952 2.712C5.952 3.248 5.82 3.724 5.556 4.14C5.3 4.548 4.952 4.868 4.512 5.1C4.072 5.324 3.576 5.436 3.024 5.436H1.62V8.592H0ZM1.62 3.9H3.072C3.352 3.9 3.588 3.844 3.78 3.732C3.972 3.62 4.116 3.476 4.212 3.3C4.308 3.116 4.356 2.92 4.356 2.712C4.356 2.504 4.308 2.312 4.212 2.136C4.116 1.96 3.972 1.816 3.78 1.704C3.588 1.592 3.352 1.536 3.072 1.536H1.62V3.9Z" fill="#4C3CFF"/>
</svg>`;
const SVG_EV =
    `<svg xmlns="http://www.w3.org/2000/svg" width="6" height="10" viewBox="0 0 6 10" fill="none">
  <path d="M1.97239 10V5.76923H0L3.94477 0V4.23077H5.91716L1.97239 10Z" fill="#218C80"/>
</svg>`;
const SVG_CLOSED =
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="32" viewBox="0 0 28 32" fill="none">
  <path fill-rule="evenodd" clip-rule="evenodd" d="M14 7C16.6788 7 16.8679 10.7359 17 11H18L19 17H9L10 11H11C11.2142 8.33333 12.2142 7 14 7ZM13.0012 13H12C11.9989 14.3333 12.6656 15 14 15C15.3344 15 16.0011 14.3333 16 13H15C15.0162 13.6724 14.683 14.0057 14.0004 14C13.3179 13.9943 12.9848 13.6609 13.0012 13ZM14 8C12.7341 8 12.0675 9 12 11H16C15.9325 9 15.2659 8 14 8Z" fill="white"/>
</svg>`;

export const PLACE_PIN_ICON_LOOKUP = new Map<string, string>([
  ['retail', SVG_RETAIL],
  ['food_and_drink', SVG_FOOD_AND_DRINK],
  ['outdoor', SVG_OUTDOOR],
  ['entertainment', SVG_ENTERTAINMENT],
  ['service', SVG_SERVICE],
  ['lodging', SVG_LODGING],
  ['emergency', SVG_EMERGENCY],
  ['generic', SVG_GENERIC],
  ['airport', SVG_AIRPORT],
  ['parking', SVG_PARKING],
  ['ev', SVG_EV],
  ['closed', SVG_CLOSED],
]);
export const PLACE_PIN_COLOR_LOOKUP = new Map<string, string>([
  ['retail', '#0597FF'],
  ['food_and_drink', '#FF8126'],
  ['outdoor', '#17A773'],
  ['service', '#7986CB'],
  ['lodging', '#F848C7'],
  ['emergency', '#F74A55'],
  ['entertainment', '#B56AFF'],
  ['generic', '#78909C'],
  ['airport', '#1A73E8'],
  ['parking', '#B3C8FF'],
  ['ev', '#C1E7CF'],
  ['closed', '#AFB2B4'],
]);
export function getPinColor(
    icon?: string|null, iconColor?: string|null): string {
  if (icon && PLACE_PIN_COLOR_LOOKUP.has(icon)) {
    return PLACE_PIN_COLOR_LOOKUP.get(icon)!;
  }
  if (iconColor && PLACE_PIN_COLOR_LOOKUP.has(iconColor)) {
    return PLACE_PIN_COLOR_LOOKUP.get(iconColor)!;
  }
  if (iconColor) {
    return iconColor;
  }
  return PLACE_PIN_COLOR_LOOKUP.get('generic') || '#78909C';
}
export function getPinIcon(icon?: string|null, iconColor?: string|null): string|
    undefined {
  if (icon && PLACE_PIN_ICON_LOOKUP.has(icon)) {
    return PLACE_PIN_ICON_LOOKUP.get(icon);
  }
  if (iconColor && PLACE_PIN_COLOR_LOOKUP.has(iconColor)) {
    return PLACE_PIN_ICON_LOOKUP.get(iconColor);
  }
  return PLACE_PIN_ICON_LOOKUP.get('generic');
}

/** Styles for place pin markers. */
export const PLACE_PIN_MARKER_STYLES: CSSResult = css`
  .custom-marker {
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
    position: relative;
  }
  .custom-marker-content {
    position: relative;
    width: 24px;
    height: 24px;
    background-color: #ffffff;
    border-radius: 12px;
    display: flex;
    align-items: center;
    padding: 2px;
    box-sizing: border-box;
    filter: drop-shadow(0 1px 2px rgba(60, 64, 67, 0.3))
            drop-shadow(0 1px 3px rgba(60, 64, 67, 0.15));
  }
  .custom-marker-content::after {
    content: "";
    position: absolute;
    bottom: -3px;
    left: 50%;
    transform: translateX(-50%) rotate(45deg);
    width: 8px;
    height: 8px;
    background-color: #ffffff;
    border-bottom-right-radius: 2px;
  }
  .custom-marker-content-icon {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    z-index: 1;
  }
  .custom-marker-content-icon svg {
    position: relative;
    left: -4px;
    top: -2px;
  }
  .custom-marker-content-label {
    color: #000;
    font-family: "Google Sans";
    font-size: 12px;
    font-style: normal;
    font-weight: 500;
    line-height: normal;
    padding-left: 5px;
  }
  .custom-marker-label-container {
    margin-top: 10px;
    border-radius: 8px;
    border: 0.5px solid #c7c7c7;
    background: #fff;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.20), 0 1px 3px 1px rgba(0, 0, 0, 0.10);
    text-align: center;
    max-width: 110px;
  }
  .custom-marker-label {
    color: #3d3833;
    font-family: "Google Sans";
    font-size: 12px;
    font-style: normal;
    font-weight: 500;
    line-height: normal;
    margin: 4px 6px;
    text-overflow: ellipsis;
    text-shadow: 1px 1px 1px #fff, -1px -1px 1px #fff;
  }
`;
