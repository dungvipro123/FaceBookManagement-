import pytest
import os
from pathlib import Path
from starlette.testclient import TestClient
from app.api.server import create_app
from app.db import init_db

@pytest.fixture(scope="module")
def client():
    init_db()
    env_path = Path(".env")
    original_env = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    
    app = create_app()
    yield TestClient(app)
    
    if original_env is not None:
        env_path.write_text(original_env, encoding="utf-8")

def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data

def test_host_allow_list(client):
    # Forbidden host
    resp = client.get("/api/health", headers={"Host": "malicious-site.com"})
    assert resp.status_code == 403
    data = resp.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FORBIDDEN"

    # Allowed loopback host
    resp = client.get("/api/health", headers={"Host": "127.0.0.1:8080"})
    assert resp.status_code == 200

def test_rotate_pin_loopback_only(client):
    resp = client.post("/api/auth/rotate-pin", headers={"Host": "localhost:8080"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    pin = data["data"]["pin"]
    assert len(pin) >= 4

    # Verify that GET /api/settings never exposes the pin
    settings_resp = client.get("/api/settings", headers={"Host": "localhost:8080"})
    assert settings_resp.status_code == 200
    s_data = settings_resp.json()["data"]
    assert "lan_pin" not in s_data
    assert s_data["lan_pin_set"] is True

def test_put_secrets(client):
    resp = client.put(
        "/api/secrets",
        json={"gemini_api_key": "AIzaSyD-sampletestkey1234"},
        headers={"Host": "localhost:8080"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    masked = data["data"]["GEMINI_API_KEY"]
    assert masked.startswith("••••••••")
    assert masked.endswith("1234")

def test_test_quota_always_returns_200(client):
    resp = client.post("/api/actions/test-quota", headers={"Host": "localhost:8080"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "status" in data["data"]
    assert data["data"]["status"] in ("ok", "quota_exceeded", "model_not_found", "network_error", "invalid_key")

def test_group_crud_and_validation(client):
    # Invalid URL regex
    bad_resp = client.post(
        "/api/groups",
        json={"name": "Bad Group", "url": "https://google.com/test", "priority": 1},
        headers={"Host": "localhost:8080"}
    )
    assert bad_resp.status_code == 422
    assert bad_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Valid group creation
    valid_url = "https://www.facebook.com/groups/testuniquegroup12345/"
    good_resp = client.post(
        "/api/groups",
        json={"name": "Test Group", "url": valid_url, "priority": 2},
        headers={"Host": "localhost:8080"}
    )
    assert good_resp.status_code == 200
    new_group = good_resp.json()["data"]
    group_id = new_group["id"]

    # Duplicate URL -> 409 CONFLICT
    dup_resp = client.post(
        "/api/groups",
        json={"name": "Duplicate", "url": valid_url, "priority": 1},
        headers={"Host": "localhost:8080"}
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["error"]["code"] == "CONFLICT"

    # Toggle group
    toggle_resp = client.patch(f"/api/groups/{group_id}/toggle", headers={"Host": "localhost:8080"})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["data"]["is_active"] == 0

    # Delete group
    del_resp = client.delete(f"/api/groups/{group_id}", headers={"Host": "localhost:8080"})
    assert del_resp.status_code == 200

def test_channel_update_and_masking(client):
    resp = client.get("/api/channels", headers={"Host": "localhost:8080"})
    assert resp.status_code == 200
    channels = resp.json()["data"]
    assert len(channels) >= 4

    # Invalid webhook URL
    bad_wh = client.patch(
        "/api/channels/deal_1",
        json={"webhook_url": "https://badurl.com/notdiscord"},
        headers={"Host": "localhost:8080"}
    )
    assert bad_wh.status_code == 422
    assert bad_wh.json()["error"]["code"] == "VALIDATION_ERROR"

    # Valid webhook update
    good_wh = "https://discord.com/api/webhooks/1234567890/tokenAbcdef1234"
    update_resp = client.patch(
        "/api/channels/deal_1",
        json={"webhook_url": good_wh, "min_discount": 20.0},
        headers={"Host": "localhost:8080"}
    )
    assert update_resp.status_code == 200
    res_data = update_resp.json()["data"]
    assert res_data["webhook_url_masked"].endswith("1234")

def test_deals_endpoint(client):
    resp = client.get("/api/deals?page=1&limit=10", headers={"Host": "localhost:8080"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total" in data
    assert "deals" in data
    assert isinstance(data["deals"], list)
