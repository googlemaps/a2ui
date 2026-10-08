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

import { A2AClient } from "@a2a-js/sdk/client";
import { A2UIClient } from "./a2ui_client";

describe("A2UIClient", () => {
  let client: A2UIClient;
  let mockA2AClient: any;

  beforeEach(() => {
    if (!globalThis.crypto) {
      (globalThis as any).crypto = {};
    }
    globalThis.crypto.randomUUID = () => "11111111-2222-3333-4444-555555555555";

    client = new A2UIClient("http://fake-server.com");

    mockA2AClient = {
      sendMessage: jasmine.createSpy("sendMessage"),
      sendMessageStream: jasmine.createSpy("sendMessageStream"),
    };

    spyOn(A2AClient, "fromCardUrl").and.resolveTo(mockA2AClient as unknown as A2AClient);
  });

  it("should process traditional blocking response correctly", async () => {
    mockA2AClient.sendMessage.and.resolveTo({
      result: {
        kind: "task",
        status: {
          message: {
            parts: [
              { kind: "text", text: "Here is your map." },
              { kind: "data", data: { createSurface: { surfaceId: "map_1" } } }
            ]
          }
        }
      }
    });

    const result = await client.send("Show me a map");

    expect(result.length).toBe(2);
    expect(result[0]).toEqual({ type: "text", text: "Here is your map." });
    expect(result[1]).toEqual({ type: "a2ui", message: { createSurface: { surfaceId: "map_1" } } });
  });

  it("should parse and yield chunked stream correctly, handling text deltas and dropping status updates", async () => {
    mockA2AClient.sendMessageStream.and.returnValue((async function* () {
      yield {
        kind: "status-update",
        status: { message: { parts: [{ kind: "text", text: "Hello " }] } }
      };

      yield {
        kind: "status-update",
        status: { message: { parts: [{ kind: "text", text: "Hello World!" }] } }
      };

      yield {
        kind: "status-update",
        status: { message: { parts: [{ kind: "data", data: { updateDataModel: { foo: "bar" } } }] } }
      };
    })());

    const generator = client.sendStream("Say hello and show card");
    const yieldedItems = [];

    for await (const item of generator) {
      yieldedItems.push(item);
    }

    expect(yieldedItems.length).toBe(3);
    expect(yieldedItems[0]).toEqual({ type: "text", text: "Hello " });
    expect(yieldedItems[1]).toEqual({ type: "text", text: "World!" });
    expect(yieldedItems[2]).toEqual({ type: "a2ui", message: { updateDataModel: { foo: "bar" } } });
  });

  it('should not duplicate already-streamed text when final status update sends trimmed text parts',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Here are 3 places:\n\n'}]}
           }
         };

         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [{kind: 'data', data: {createSurface: {surfaceId: 's1'}}}]
             }
           }
         };

         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [{kind: 'text', text: '\n\nWould you like directions?'}]
             }
           }
         };

         // Final task completion event re-sends all parsed final parts with
         // leading/trailing whitespace stripped.
         yield {
           kind: 'status-update',
           final: true,
           status: {
             state: 'input-required',
             message: {
               parts: [
                 {kind: 'text', text: 'Here are 3 places:'},
                 {kind: 'data', data: {createSurface: {surfaceId: 's1'}}},
                 {kind: 'text', text: 'Would you like directions?'},
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Find places')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Here are 3 places:\n\n'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's1'}}},
         {type: 'text', text: '\n\nWould you like directions?'},
       ]);
     });

  it('should preserve streaming token deltas that are substrings of earlier text and deduplicate final summary',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Sushi in Seattle:'}]}
           }
         };

         // Short token delta " in " is a substring of "Sushi in Seattle:",
         // which must still be yielded during `working` streaming!
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: ' in '}]}
           }
         };

         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'downtown.'}]}
           }
         };

         yield {
           kind: 'status-update',
           final: true,
           status: {
             state: 'input-required',
             message: {
               parts: [
                 {kind: 'text', text: 'Sushi in Seattle: in downtown.'},
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Find sushi')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Sushi in Seattle:'},
         {type: 'text', text: ' in '},
         {type: 'text', text: 'downtown.'},
       ]);
     });

  it('should handle cumulative streaming across both pre-surface and post-surface text segments',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Intro '}]}
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Intro text.'}]}
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [{kind: 'data', data: {createSurface: {surfaceId: 's1'}}}]
             }
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Outro '}]}
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: 'Outro text.'}]}
           }
         };
         yield {
           kind: 'status-update',
           final: true,
           status: {
             state: 'completed',
             message: {
               parts: [
                 {kind: 'text', text: 'Intro text.'},
                 {kind: 'data', data: {createSurface: {surfaceId: 's1'}}},
                 {kind: 'text', text: 'Outro text.'},
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Find places')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Intro '},
         {type: 'text', text: 'text.'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's1'}}},
         {type: 'text', text: 'Outro '},
         {type: 'text', text: 'text.'},
       ]);
     });

  it('should yield text and data when a single terminal status update is sent without prior working chunks',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           final: true,
           status: {
             state: 'input-required',
             message: {
               parts: [
                 {kind: 'text', text: 'Here is your template card:'},
                 {
                   kind: 'data',
                   data: {createSurface: {surfaceId: 's_template'}}
                 },
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Show template')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Here is your template card:'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's_template'}}},
       ]);
     });

  it('should not self-deduplicate follow-up text within a single terminal status update when it is a substring of intro text',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           final: true,
           status: {
             state: 'input-required',
             message: {
               parts: [
                 {kind: 'text', text: 'Places in Seattle:'},
                 {
                   kind: 'data',
                   data: {createSurface: {surfaceId: 's_template'}}
                 },
                 {kind: 'text', text: 'Seattle'},
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Show template')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Places in Seattle:'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's_template'}}},
         {type: 'text', text: 'Seattle'},
       ]);
     });

  it('should preserve leading newline token deltas after a data part without treating whitespace as a cumulative prefix',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [{kind: 'data', data: {createSurface: {surfaceId: 's1'}}}]
             }
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {parts: [{kind: 'text', text: '\n'}]}
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message:
                 {parts: [{kind: 'text', text: '\nWould you like directions?'}]}
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Show card')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'a2ui', message: {createSurface: {surfaceId: 's1'}}},
         {type: 'text', text: '\n'},
         {type: 'text', text: '\nWould you like directions?'},
       ]);
     });

  it('should reset deduplication state when deleteSurface is received during a retry',
     async () => {
       mockA2AClient.sendMessageStream.and.returnValue((async function*() {
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [
                 {kind: 'text', text: 'Here are the results:'},
                 {kind: 'data', data: {createSurface: {surfaceId: 's1'}}},
               ]
             }
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [
                 {kind: 'data', data: {deleteSurface: {surfaceId: 's1'}}},
               ]
             }
           }
         };
         yield {
           kind: 'status-update',
           status: {
             state: 'working',
             message: {
               parts: [
                 {kind: 'text', text: 'Here are the results:'},
                 {kind: 'data', data: {createSurface: {surfaceId: 's1'}}},
               ]
             }
           }
         };
       })());

       const yieldedItems = [];
       for await (const item of client.sendStream('Retry query')) {
         yieldedItems.push(item);
       }

       expect(yieldedItems).toEqual([
         {type: 'text', text: 'Here are the results:'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's1'}}},
         {type: 'a2ui', message: {deleteSurface: {surfaceId: 's1'}}},
         {type: 'text', text: 'Here are the results:'},
         {type: 'a2ui', message: {createSurface: {surfaceId: 's1'}}},
       ]);
     });
});
