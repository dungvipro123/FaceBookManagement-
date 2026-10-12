import pytest
from app.state import AppState, health_color, StateManager

def test_app_state_defaults():
    state = AppState()
    assert state.boot_id != ""
    assert state.is_paused is False
    assert state.is_scanning is False
    assert state.fb_status == "unknown"
    assert state.gemini_status == "untested"
    # By default, unknown fb_status and untested gemini_status -> amber
    assert health_color(state) == "amber"
    assert state.status == "paused"

def test_health_color_rules():
    # 1. Critical Errors -> RED
    red_cases = [
        AppState(fb_status="logged_out", gemini_status="ok"),
        AppState(fb_status="checkpoint", gemini_status="ok"),
        AppState(fb_status="captcha", gemini_status="ok"),
        AppState(fb_status="ok", gemini_status="quota_exceeded"),
        AppState(fb_status="ok", gemini_status="model_not_found"),
        AppState(fb_status="ok", gemini_status="network_error"),
    ]
    for s in red_cases:
        assert health_color(s) == "red"
        assert s.status == "error"

    # 2. Warnings / untested / rate limited / paused / scanning -> AMBER
    amber_cases = [
        AppState(fb_status="rate_limited", gemini_status="ok"),
        AppState(fb_status="unknown", gemini_status="ok"),
        AppState(fb_status="ok", gemini_status="untested"),
        AppState(fb_status="ok", gemini_status="ok", is_paused=True),
        AppState(fb_status="ok", gemini_status="ok", is_scanning=True),
    ]
    for s in amber_cases:
        assert health_color(s) == "amber"

    # 3. Fully Healthy -> GREEN
    green_state = AppState(fb_status="ok", gemini_status="ok", is_paused=False, is_scanning=False)
    assert health_color(green_state) == "green"
    assert green_state.status == "idle"

def test_state_manager_ring_buffer():
    mgr = StateManager()
    for i in range(150):
        mgr.add_log("INFO", f"Message {i}", "test")
    state = mgr.get_state()
    assert len(state.recent_logs) == 100
    assert state.recent_logs[-1]["message"] == "Message 149"

def test_gemini_latency_history_limit():
    mgr = StateManager()
    for i in range(30):
        mgr.record_gemini_latency(float(i * 10), "ok")
    state = mgr.get_state()
    assert len(state.gemini_latency_history) == 20
    assert state.gemini_latency_ms == 290.0
