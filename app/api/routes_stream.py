"""Server-Sent Events endpoint."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.events import EventBroker


def _encode_event(name: str, data: object) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {name}\ndata: {payload}\n\n"


def create_stream_router(event_broker: EventBroker) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["stream"])

    @router.get("/stream")
    async def stream(request: Request) -> StreamingResponse:
        async def events():  # type: ignore[no-untyped-def]
            async with event_broker.subscribe() as queue:
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _encode_event(event.name, event.data)
                    except TimeoutError:
                        yield _encode_event("ping", {"status": "ok"})

        return StreamingResponse(
            events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
