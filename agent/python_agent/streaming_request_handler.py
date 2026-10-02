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
import logging
from collections.abc import AsyncGenerator
from typing import Any, cast

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.context import ServerCallContext
from a2a.types import (
    Message,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TaskState,
)
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskManager
from a2a.utils.errors import ServerError
from a2a.utils.errors import TaskNotFoundError, InvalidParamsError

logger = logging.getLogger(__name__)

class QueueBridge(EventQueue):
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self._queue = queue
        self._is_closed = False

    async def enqueue_event(
        self,
        event: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
    ) -> None:
        if self._is_closed:
            raise RuntimeError("Queue is closed")
        await self._queue.put(event)

    async def close(self, immediate: bool = False) -> None:
        if self._is_closed:
            return
        self._is_closed = True
        await self._queue.put(None)

    def is_closed(self) -> bool:
        return self._is_closed

class StreamingRequestHandler(DefaultRequestHandler):
    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> AsyncGenerator[Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent, None]:
        task_manager = TaskManager(
            task_id=params.message.task_id,
            context_id=params.message.context_id,
            task_store=self.task_store,
            initial_message=params.message,
            context=context,
        )
        task: Task | None = await task_manager.get_task()

        TERMINAL_TASK_STATES = {
            TaskState.completed,
            TaskState.canceled,
            TaskState.failed,
            TaskState.rejected,
        }

        if task:
            if task.status.state in TERMINAL_TASK_STATES:
                raise ServerError(
                    error=InvalidParamsError(
                        message=f'Task {task.id} is in terminal state: {task.status.state.value}'
                    )
                )
            task = task_manager.update_with_message(params.message, task)
        elif params.message.task_id:
            raise ServerError(
                error=TaskNotFoundError(
                    message=f'Task {params.message.task_id} was specified but does not exist'
                )
            )

        request_context = await self._request_context_builder.build(
            params=params,
            task_id=task.id if task else None,
            context_id=params.message.context_id,
            task=task,
            context=context,
        )

        task_id = cast('str', request_context.task_id)

        if (
            self._push_config_store
            and params.configuration
            and params.configuration.push_notification_config
        ):
            await self._push_config_store.set_info(
                task_id, params.configuration.push_notification_config
            )

        queue = asyncio.Queue()
        queue_bridge = QueueBridge(queue)

        async def run_producer():
            try:
                await self.agent_executor.execute(request_context, queue_bridge)
            except Exception as e:
                logger.exception("Error in Streaming agent execution producer task")
                await queue.put(e)
            finally:
                await queue_bridge.close()

        producer_task = asyncio.create_task(run_producer())
        producer_task.set_name(f"streaming_producer:{task_id}")

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass