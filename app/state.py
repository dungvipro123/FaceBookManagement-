import uuid
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

def utc_iso_now() -> str:
    """Returns current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()

@dataclass
class AppState:
    boot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_paused: bool = False
    is_scanning: bool = False

    # Facebook Session & Crawler
    fb_status: str = "unknown"          # "ok" | "checkpoint" | "captcha" | "rate_limited" | "logged_out" | "unknown"
    current_group: Optional[str] = None
    scan_progress: Optional[Dict[str, Any]] = None
    last_scan_time: Optional[str] = None
    next_scan_time: Optional[str] = None

    # Gemini AI Status
    gemini_status: str = "untested"     # "ok" | "quota_exceeded" | "model_not_found" | "network_error" | "untested"
    gemini_model: str = "gemini-3.5-flash"
    gemini_latency_ms: float = 0.0
    gemini_latency_history: List[float] = field(default_factory=list) # Max 20 points

    # Thống kê nhanh
    total_posts: int = 0
    total_deals: int = 0
    total_buys: int = 0
    today_posts: int = 0
    active_groups_count: int = 0

    # Lỗi gần nhất
    last_error: Optional[Dict[str, str]] = None

    # Realtime logs buffer (Ring buffer: max 100 entries)
    recent_logs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        color = health_color(self)
        if color == "red":
            return "error"
        if self.is_scanning:
            return "scanning"
        if self.is_paused or color == "amber":
            return "paused"
        return "idle"


def health_color(state: AppState) -> str:
    """
    Returns single unified health color ('green' | 'amber' | 'red')
    Used by both AppState.status and system tray icon.
    """
    # 1. Critical errors -> RED
    if state.fb_status in ("logged_out", "checkpoint", "captcha"):
        return "red"
    if state.gemini_status in ("quota_exceeded", "model_not_found", "network_error"):
        return "red"

    # 2. Warnings / untested / busy / paused -> AMBER
    if state.fb_status in ("unknown", "rate_limited"):
        return "amber"
    if state.gemini_status in ("untested",):
        return "amber"
    if state.is_scanning or state.is_paused:
        return "amber"

    # 3. Healthy / operational -> GREEN
    return "green"


class StateManager:
    """Thread-safe manager for shared AppState."""
    def __init__(self, initial_state: Optional[AppState] = None):
        self._lock = threading.RLock()
        self._state = initial_state or AppState()

    def get_state(self) -> AppState:
        with self._lock:
            return self._state

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            data = asdict(self._state)
            data["status"] = self._state.status
            data["health_color"] = health_color(self._state)
            return data

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._state, k):
                    setattr(self._state, k, v)

    def record_gemini_latency(self, latency_ms: float, status: str = "ok") -> None:
        with self._lock:
            self._state.gemini_status = status
            self._state.gemini_latency_ms = round(latency_ms, 2)
            self._state.gemini_latency_history.append(round(latency_ms, 2))
            if len(self._state.gemini_latency_history) > 20:
                self._state.gemini_latency_history.pop(0)

    def set_error(self, module: str, message: str) -> None:
        with self._lock:
            self._state.last_error = {
                "timestamp": utc_iso_now(),
                "module": module,
                "message": message
            }

    def add_log(self, level: str, message: str, module: str = "system") -> Dict[str, Any]:
        entry = {
            "timestamp": utc_iso_now(),
            "level": level.upper(),
            "module": module,
            "message": message
        }
        with self._lock:
            self._state.recent_logs.append(entry)
            if len(self._state.recent_logs) > 100:
                self._state.recent_logs.pop(0)
        return entry

# Global singleton instance
state_manager = StateManager()
