"""Non-blocking in-memory publish/subscribe broker for SSE clients."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    data: Any


class EventBroker:
    """Fan events out without letting a slow browser block producers."""

    def __init__(self, queue_size: int = 200) -> None:
        self.queue_size = queue_size
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self.queue_size)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def publish(self, name: str, data: Any) -> None:
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        # Event-loop execution makes a snapshot safe; the lock is only needed
        # while clients are registered/unregistered.
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(Event(name=name, data=data))
            except asyncio.QueueFull:
                continue
