import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse
from app.api.sse import sse_manager
from app.api.middleware import make_error_response
from app.state import utc_iso_now

router = APIRouter(prefix="/api/logs", tags=["logs"])

@router.get("/stream")
async def stream_logs(request: Request):
    q = sse_manager.add_client()
    if q is None:
        return make_error_response(
            code="RATE_LIMITED",
            message="Đã đạt giới hạn tối đa 5 kết nối SSE đồng thời.",
            status_code=429
        )

    async def event_generator():
        try:
            # First SSE event carries boot_id and replay logs
            yield sse_manager.get_init_payload()

            last_heartbeat = asyncio.get_event_loop().time()
            while True:
                # Check client disconnect
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield payload
                except asyncio.TimeoutError:
                    pass

                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= 15.0:
                    last_heartbeat = now
                    yield f": heartbeat {utc_iso_now()}\n\n"

        finally:
            sse_manager.remove_client(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
