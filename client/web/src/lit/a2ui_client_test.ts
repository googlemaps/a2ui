/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {A2AClient} from '@a2a-js/sdk/client';

import {A2UIClient} from './a2ui_client';

describe('A2UIClient', () => {
  let client: A2UIClient;
  let mockA2AClient: any;
  let mockAddContentTokens: jasmine.Spy;
  let originalGoogle: unknown;

  beforeEach(() => {
    if (!globalThis.crypto) {
      (globalThis as any).crypto = {};
    }
    globalThis.crypto.randomUUID = () => '11111111-2222-3333-4444-555555555555';

    const windowWithGlobals = window as unknown as Record<string, unknown>;
    originalGoogle = windowWithGlobals['google'];
    mockAddContentTokens = jasmine.createSpy('addContentTokens');
    windowWithGlobals['google'] = {
      maps: {
        Settings: {
          getInstance: () => ({
            addContentTokens: mockAddContentTokens,
          }),
        },
      },
    };

    client = new A2UIClient('http://fake-server.com');

    mockA2AClient = {
      sendMessage: jasmine.createSpy('sendMessage'),
      sendMessageStream: jasmine.createSpy('sendMessageStream'),
    };

    spyOn(A2AClient, 'fromCardUrl')
        .and.resolveTo(
            mockA2AClient as unknown as A2AClient,
        );
  });

  afterEach(() => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    windowWithGlobals['google'] = originalGoogle;
  });

  it('should process traditional blocking response correctly', async () => {
    mockA2AClient.sendMessage.and.resolveTo({
      result: {
        kind: 'task',
        status: {
          message: {
            parts: [
              {kind: 'text', text: 'Here is your map.'},
              {
                kind: 'data',
                data: {createSurface: {surfaceId: 'map_1'}},
                root: {
                  metadata: {
                    maps_tools_content_tokens: ['token_1', 'token_2'],
                  },
                },
              },
            ],
          },
        },
      },
    });

    const result = await client.send('Show me a map');

    expect(result.length).toBe(2);
    expect(result[0]).toEqual({type: 'text', text: 'Here is your map.'});
    expect(result[1]).toEqual({
      type: 'a2ui',
      message: {createSurface: {surfaceId: 'map_1'}},
    });
    expect(mockAddContentTokens).toHaveBeenCalledOnceWith([
      'token_1',
      'token_2',
    ]);
  });

  it('should parse and yield chunked stream correctly, handling text deltas and dropping status updates',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue(
           (async function*() {
             yield {
               kind: 'status-update',
               status: {message: {parts: [{kind: 'text', text: 'Hello '}]}},
             };
             yield {
               kind: 'status-update',
               status: {message: {parts: [{kind: 'text', text: 'World!'}]}},
             };

             yield {
               kind: 'status-update',
               status: {
                 message: {
                   parts: [
                     {
                       kind: 'data',
                       data: {updateDataModel: {foo: 'bar'}},
                       root: {
                         metadata: {
                           maps_tools_content_tokens: ['stream_token_1'],
                         },
                       },
                     },
                   ],
                 },
               },
             };
           })(),
       );

       const generator = client.sendStream('Say hello and show card');
       const yieldedItems = [];

       for await (const item of generator) {
         yieldedItems.push(item);
       }

       expect(yieldedItems.length).toBe(3);
       expect(yieldedItems[0]).toEqual({type: 'text', text: 'Hello '});
       expect(yieldedItems[1]).toEqual({type: 'text', text: 'World!'});
       expect(yieldedItems[2]).toEqual({
         type: 'a2ui',
         message: {updateDataModel: {foo: 'bar'}},
       });
       expect(mockAddContentTokens).toHaveBeenCalledOnceWith([
         'stream_token_1'
       ]);
     });

  it('should not call addContentTokens when maps_tools_content_tokens is absent',
     async () => {
       mockA2AClient.sendMessage.and.resolveTo({
         result: {
           kind: 'task',
           status: {
             message: {
               parts: [
                 {kind: 'data', data: {createSurface: {surfaceId: 'map_1'}}},
               ],
             },
           },
         },
       });

       await client.send('Show me a map');

       expect(mockAddContentTokens).not.toHaveBeenCalled();
     });

  it('should load core library via importLibrary when google.maps.Settings is not yet loaded',
     async () => {
       const windowWithGlobals = window as unknown as Record<string, unknown>;
       const importLibrarySpy =
           jasmine.createSpy('importLibrary').and.resolveTo({
             Settings: {
               getInstance: () => ({
                 addContentTokens: mockAddContentTokens,
               }),
             },
           });
       windowWithGlobals['google'] = {
         maps: {
           importLibrary: importLibrarySpy,
         },
       };

       mockA2AClient.sendMessage.and.resolveTo({
         result: {
           kind: 'task',
           status: {
             message: {
               parts: [
                 {
                   kind: 'data',
                   data: {createSurface: {surfaceId: 'map_1'}},
                   root: {
                     metadata: {
                       maps_tools_content_tokens: ['lazy_token_1'],
                     },
                   },
                 },
               ],
             },
           },
         },
       });

       await client.send('Show me a map');

       expect(importLibrarySpy).toHaveBeenCalledOnceWith('core');
       expect(mockAddContentTokens).toHaveBeenCalledOnceWith(['lazy_token_1']);
     });

  it('should log an error when loading the core library fails', async () => {
    const windowWithGlobals = window as unknown as Record<string, unknown>;
    const loadError = new Error('Network error');
    const importLibrarySpy =
        jasmine.createSpy('importLibrary').and.rejectWith(loadError);
    windowWithGlobals['google'] = {
      maps: {
        importLibrary: importLibrarySpy,
      },
    };
    const consoleErrorSpy = spyOn(console, 'error');

    mockA2AClient.sendMessage.and.resolveTo({
      result: {
        kind: 'task',
        status: {
          message: {
            parts: [
              {
                kind: 'data',
                data: {createSurface: {surfaceId: 'map_1'}},
                root: {
                  metadata: {
                    maps_tools_content_tokens: ['lazy_token_1'],
                  },
                },
              },
            ],
          },
        },
      },
    });

    await client.send('Show me a map');

    expect(importLibrarySpy).toHaveBeenCalledOnceWith('core');
    expect(consoleErrorSpy)
        .toHaveBeenCalledOnceWith(
            'Failed to load Google Maps Core library:',
            loadError,
        );
    expect(mockAddContentTokens).not.toHaveBeenCalled();
  });
});
