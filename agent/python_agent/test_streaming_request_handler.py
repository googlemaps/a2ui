# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import unittest
from unittest import mock

import streaming_request_handler

class QueueBridgeTest(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_event(self):
        queue = asyncio.Queue()
        bridge = streaming_request_handler.QueueBridge(queue)

        # Test normal put
        mock_event = mock.MagicMock()
        await bridge.enqueue_event(mock_event)
        self.assertEqual(await queue.get(), mock_event)

    async def test_close_queue(self):
        queue = asyncio.Queue()
        bridge = streaming_request_handler.QueueBridge(queue)

        # Test close behavior
        await bridge.close()
        self.assertTrue(bridge.is_closed())
        self.assertIsNone(await queue.get())

        # Test putting after close raises error
        with self.assertRaises(RuntimeError):
            await bridge.enqueue_event(mock.MagicMock())

if __name__ == '__main__':
  unittest.main()
