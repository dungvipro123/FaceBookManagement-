import os
from typing import Optional, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.config import (
    get_all_settings,
    get_setting,
    set_setting,
    update_env_file,
    mask_secret,
    REGEX_GEMINI_MODEL
)
from app.api.sse import sse_manager
from app.api.middleware import make_error_response

router = APIRouter(prefix="/api", tags=["settings"])

class UpdateSettingsRequest(BaseModel):
    scan_interval_minutes: Optional[int] = Field(None, ge=10, le=1440)
    headless: Optional[bool] = None
    gemini_model: Optional[str] = None
    lan_access_enabled: Optional[bool] = None
    web_port: Optional[int] = Field(None, ge=1024, le=65535)
    autostart: Optional[bool] = None

class UpdateSecretsRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    discord_bot_token: Optional[str] = None
    discord_bot_app_id: Optional[str] = None
    lan_pin: Optional[str] = None

@router.get("/settings")
async def get_settings():
    settings = get_all_settings()
    
    # Include masked secrets from .env
    settings["secrets"] = {
        "GEMINI_API_KEY": mask_secret(os.getenv("GEMINI_API_KEY", "")),
        "DISCORD_BOT_TOKEN": mask_secret(os.getenv("DISCORD_BOT_TOKEN", "")),
        "DISCORD_BOT_APP_ID": mask_secret(os.getenv("DISCORD_BOT_APP_ID", "")),
    }
    return {"success": True, "data": settings}

@router.post("/settings")
async def update_settings(body: UpdateSettingsRequest):
    updated = {}

    if body.scan_interval_minutes is not None:
        set_setting("scan_interval_minutes", body.scan_interval_minutes)
        updated["scan_interval_minutes"] = body.scan_interval_minutes
        sse_manager.publish_threadsafe("settings", {"key": "scan_interval_minutes", "value": body.scan_interval_minutes})

    if body.headless is not None:
        set_setting("headless", body.headless)
        updated["headless"] = body.headless
        sse_manager.publish_threadsafe("settings", {"key": "headless", "value": body.headless})

    if body.gemini_model is not None:
        clean_model = body.gemini_model.strip()
        if not REGEX_GEMINI_MODEL.match(clean_model):
            return make_error_response(
                code="VALIDATION_ERROR",
                message="Tên model Gemini không hợp lệ. Chỉ chấp nhận ký tự chữ, số, dấu gạch nối và dấu chấm.",
                status_code=422,
                details={"field": "gemini_model", "received": clean_model}
            )
        set_setting("gemini_model", clean_model)
        updated["gemini_model"] = clean_model
        sse_manager.publish_threadsafe("settings", {"key": "gemini_model", "value": clean_model})

    if body.lan_access_enabled is not None:
        set_setting("lan_access_enabled", body.lan_access_enabled)
        updated["lan_access_enabled"] = body.lan_access_enabled
        sse_manager.publish_threadsafe("settings", {"key": "lan_access_enabled", "value": body.lan_access_enabled})

    if body.web_port is not None:
        set_setting("web_port", body.web_port)
        updated["web_port"] = body.web_port
        sse_manager.publish_threadsafe("settings", {"key": "web_port", "value": body.web_port})

    if body.autostart is not None:
        set_setting("autostart", body.autostart)
        updated["autostart"] = body.autostart
        sse_manager.publish_threadsafe("settings", {"key": "autostart", "value": body.autostart})

    return {
        "success": True,
        "data": {
            "updated": updated,
            "requires_restart": any(k in ("lan_access_enabled", "web_port") for k in updated)
        }
    }

@router.put("/secrets")
async def update_secrets(body: UpdateSecretsRequest):
    """
    Write-only secrets endpoint.
    Updates .env safely and returns masked values only.
    """
    env_updates = {}
    if body.gemini_api_key is not None:
        env_updates["GEMINI_API_KEY"] = body.gemini_api_key.strip()
    if body.discord_bot_token is not None:
        env_updates["DISCORD_BOT_TOKEN"] = body.discord_bot_token.strip()
    if body.discord_bot_app_id is not None:
        env_updates["DISCORD_BOT_APP_ID"] = body.discord_bot_app_id.strip()

    if env_updates:
        update_env_file(env_updates)

    if body.lan_pin is not None:
        clean_pin = body.lan_pin.strip()
        if len(clean_pin) < 4:
            return make_error_response(
                code="VALIDATION_ERROR",
                message="Mã PIN tối thiểu phải có 4 ký tự.",
                status_code=422
            )
        set_setting("lan_pin", clean_pin)

    # Return masked secrets response
    return {
        "success": True,
        "data": {
            "GEMINI_API_KEY": mask_secret(os.getenv("GEMINI_API_KEY", "")),
            "DISCORD_BOT_TOKEN": mask_secret(os.getenv("DISCORD_BOT_TOKEN", "")),
            "DISCORD_BOT_APP_ID": mask_secret(os.getenv("DISCORD_BOT_APP_ID", "")),
            "lan_pin_set": bool(get_setting("lan_pin", ""))
        }
    }
