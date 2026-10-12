from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
import requests
from app.db import get_connection
from app.config import (
    mask_secret,
    REGEX_DISCORD_WEBHOOK,
    REGEX_MENTION_TAG
)
from app.api.middleware import make_error_response

router = APIRouter(prefix="/api/channels", tags=["channels"])

class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    webhook_url: Optional[str] = None
    is_enabled: Optional[bool] = None
    min_discount: Optional[float] = Field(None, ge=0.0, le=99.0)
    mention_tag: Optional[str] = None
    show_images: Optional[bool] = None

@router.get("")
async def list_channels():
    conn = get_connection()
    rows = conn.execute("""
    SELECT channel_key, name, webhook_url, is_enabled, min_discount, mention_tag, show_images
    FROM channel_configs
    ORDER BY CASE channel_key
        WHEN 'deal_1' THEN 1
        WHEN 'deal_2' THEN 2
        WHEN 'buy' THEN 3
        WHEN 'log' THEN 4
        ELSE 5 END
    """).fetchall()
    
    channels = []
    for r in rows:
        d = dict(r)
        d["webhook_url_masked"] = mask_secret(d.get("webhook_url", ""))
        d["has_webhook"] = bool(d.get("webhook_url"))
        channels.append(d)
    return {"success": True, "data": channels}

@router.patch("/{channel_key}")
async def update_channel(channel_key: str, body: UpdateChannelRequest):
    conn = get_connection()
    existing = conn.execute("SELECT * FROM channel_configs WHERE channel_key = ?", (channel_key,)).fetchone()
    if not existing:
        return make_error_response(
            code="NOT_FOUND",
            message=f"Không tìm thấy cấu hình kênh '{channel_key}'.",
            status_code=404
        )

    updates = []
    params = []

    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name.strip())

    if body.webhook_url is not None:
        clean_webhook = body.webhook_url.strip()
        if clean_webhook and not REGEX_DISCORD_WEBHOOK.match(clean_webhook):
            return make_error_response(
                code="VALIDATION_ERROR",
                message="Discord Webhook URL không hợp lệ. Phải khớp định dạng https://discord.com/api/webhooks/{id}/{token}",
                status_code=422,
                details={"field": "webhook_url", "received": clean_webhook}
            )
        updates.append("webhook_url = ?")
        params.append(clean_webhook)

    if body.is_enabled is not None:
        updates.append("is_enabled = ?")
        params.append(1 if body.is_enabled else 0)

    if body.min_discount is not None:
        if not (0.0 <= body.min_discount <= 99.0):
            return make_error_response(
                code="VALIDATION_ERROR",
                message="Mức giảm giá tối thiểu phải từ 0% đến 99%.",
                status_code=422,
                details={"field": "min_discount", "received": body.min_discount}
            )
        updates.append("min_discount = ?")
        params.append(body.min_discount)

    if body.mention_tag is not None:
        clean_tag = body.mention_tag.strip()
        if clean_tag and not REGEX_MENTION_TAG.match(clean_tag):
            return make_error_response(
                code="VALIDATION_ERROR",
                message="Mention tag không hợp lệ. Chỉ chấp nhận rỗng, @everyone, @here, hoặc <@&role_id> / <@user_id>.",
                status_code=422,
                details={"field": "mention_tag", "received": clean_tag}
            )
        updates.append("mention_tag = ?")
        params.append(clean_tag)

    if body.show_images is not None:
        updates.append("show_images = ?")
        params.append(1 if body.show_images else 0)

    if updates:
        params.append(channel_key)
        conn.execute(f"UPDATE channel_configs SET {', '.join(updates)} WHERE channel_key = ?", params)
        conn.commit()

    updated = conn.execute("SELECT * FROM channel_configs WHERE channel_key = ?", (channel_key,)).fetchone()
    d = dict(updated)
    d["webhook_url_masked"] = mask_secret(d.get("webhook_url", ""))
    return {"success": True, "data": d}

@router.post("/{channel_key}/test")
async def test_channel(channel_key: str):
    conn = get_connection()
    row = conn.execute("SELECT webhook_url, name FROM channel_configs WHERE channel_key = ?", (channel_key,)).fetchone()
    if not row or not row["webhook_url"]:
        return make_error_response(
            code="NOT_FOUND",
            message=f"Kênh '{channel_key}' chưa được cấu hình Webhook URL.",
            status_code=404
        )

    webhook_url = row["webhook_url"]
    payload = {
        "content": f"🧪 **Test Webhook từ FB Monitor Hunter v2.0**\nKênh kiểm tra: `{row['name']}` ({channel_key})\nKết nối Webhook hoạt động bình thường!",
        "embeds": [{
            "title": "✅ Kiểm tra thành công",
            "description": f"Hệ thống đã kết nối thành công tới Discord Webhook của kênh **{row['name']}**.",
            "color": 0x10B981,
            "footer": {"text": "FB Monitor Hunter v2.0 • Test Message"}
        }]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return {"success": True, "data": {"message": f"Đã gửi tin nhắn test thành công tới kênh {row['name']}"}}
        elif resp.status_code == 429:
            return make_error_response(
                code="RATE_LIMITED",
                message="Discord phản hồi 429 Too Many Requests khi test webhook.",
                status_code=429
            )
        else:
            return make_error_response(
                code="VALIDATION_ERROR",
                message=f"Discord từ chối webhook: HTTP {resp.status_code}",
                status_code=422
            )
    except Exception as e:
        return make_error_response(
            code="INTERNAL_ERROR",
            message=f"Không thể gửi tin nhắn test tới Discord: {str(e)}",
            status_code=500
        )
