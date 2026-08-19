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
import {A2UICoreShell} from '../../../mobile_core/web_build/src/core-shell';

(window as any)['A2UI_ATTRIBUTION_ID'] = 'gmp_web_maui_v0.1.7_exp,gmp_android_maui_v0.1.7_exp';

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
  }
}

