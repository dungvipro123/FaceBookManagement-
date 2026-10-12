import json
import asyncio
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional
from app.state import state_manager, utc_iso_now

MAX_SSE_CLIENTS = 5

class SSEManager:
    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()
        self._next_id: int = 1
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def add_client(self) -> Optional[asyncio.Queue]:
        if len(self._queues) >= MAX_SSE_CLIENTS:
            return None
        q = asyncio.Queue(maxsize=100)
        self._queues.add(q)
        return q

    def remove_client(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def publish_threadsafe(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publishes an event from any background thread to all connected SSE clients."""
        if not self._queues or not self._loop or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._broadcast_event, event_type, data)

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        event_id = self._next_id
        self._next_id += 1
        payload = f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        
        for q in list(self._queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def get_init_payload(self) -> str:
        state = state_manager.get_state()
        init_data = {
            "boot_id": state.boot_id,
            "replay_logs": state.recent_logs[-30:],
            "state": state_manager.to_dict()
        }
        return f"id: 0\nevent: init\ndata: {json.dumps(init_data, ensure_ascii=False)}\n\n"

# Global SSE Manager singleton
sse_manager = SSEManager()
