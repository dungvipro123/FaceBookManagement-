import sqlite3
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.db import get_connection
from app.config import REGEX_FB_GROUP_URL
from app.api.middleware import make_error_response

router = APIRouter(prefix="/api/groups", tags=["groups"])

class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str
    priority: int = Field(1, ge=1, le=5)

class UpdateGroupRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=5)

@router.get("")
async def list_groups():
    conn = get_connection()
    rows = conn.execute("""
    SELECT id, name, url, is_active, priority, last_scraped_at
    FROM monitored_groups
    ORDER BY priority ASC, id ASC
    """).fetchall()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("")
async def create_group(body: CreateGroupRequest):
    # Validate Facebook Group URL
    clean_url = body.url.strip()
    if not REGEX_FB_GROUP_URL.match(clean_url):
        return make_error_response(
            code="VALIDATION_ERROR",
            message="URL nhóm không hợp lệ. Chỉ chấp nhận định dạng https://facebook.com/groups/...",
            status_code=422,
            details={"field": "url", "received": clean_url}
        )

    conn = get_connection()
    # Check if URL already exists
    existing = conn.execute("SELECT id FROM monitored_groups WHERE url = ?", (clean_url,)).fetchone()
    if existing:
        return make_error_response(
            code="CONFLICT",
            message="Nhóm này đã tồn tại trong danh sách theo dõi.",
            status_code=409,
            details={"url": clean_url}
        )

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO monitored_groups (name, url, is_active, priority)
    VALUES (?, ?, 1, ?)
    """, (body.name.strip(), clean_url, body.priority))
    conn.commit()
    new_id = cursor.lastrowid

    row = conn.execute("SELECT id, name, url, is_active, priority, last_scraped_at FROM monitored_groups WHERE id = ?", (new_id,)).fetchone()
    return {"success": True, "data": dict(row)}

@router.patch("/{group_id}")
async def update_group(group_id: int, body: UpdateGroupRequest):
    conn = get_connection()
    existing = conn.execute("SELECT id, name, url, is_active, priority, last_scraped_at FROM monitored_groups WHERE id = ?", (group_id,)).fetchone()
    if not existing:
        return make_error_response(
            code="NOT_FOUND",
            message=f"Không tìm thấy nhóm với ID {group_id}.",
            status_code=404
        )

    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name.strip())
    if body.url is not None:
        clean_url = body.url.strip()
        if not REGEX_FB_GROUP_URL.match(clean_url):
            return make_error_response(
                code="VALIDATION_ERROR",
                message="URL nhóm không hợp lệ. Chỉ chấp nhận định dạng https://facebook.com/groups/...",
                status_code=422,
                details={"field": "url", "received": clean_url}
            )
        # Check collision with other group
        dup = conn.execute("SELECT id FROM monitored_groups WHERE url = ? AND id != ?", (clean_url, group_id)).fetchone()
        if dup:
            return make_error_response(
                code="CONFLICT",
                message="URL nhóm này đã được sử dụng bởi nhóm khác.",
                status_code=409
            )
        updates.append("url = ?")
        params.append(clean_url)
    if body.priority is not None:
        updates.append("priority = ?")
        params.append(body.priority)

    if updates:
        params.append(group_id)
        conn.execute(f"UPDATE monitored_groups SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    updated = conn.execute("SELECT id, name, url, is_active, priority, last_scraped_at FROM monitored_groups WHERE id = ?", (group_id,)).fetchone()
    return {"success": True, "data": dict(updated)}

@router.patch("/{group_id}/toggle")
async def toggle_group(group_id: int):
    conn = get_connection()
    row = conn.execute("SELECT is_active FROM monitored_groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        return make_error_response(
            code="NOT_FOUND",
            message=f"Không tìm thấy nhóm với ID {group_id}.",
            status_code=404
        )

    new_active = 0 if row["is_active"] == 1 else 1
    conn.execute("UPDATE monitored_groups SET is_active = ? WHERE id = ?", (new_active, group_id))
    conn.commit()

    updated = conn.execute("SELECT id, name, url, is_active, priority, last_scraped_at FROM monitored_groups WHERE id = ?", (group_id,)).fetchone()
    return {"success": True, "data": dict(updated)}

@router.delete("/{group_id}")
async def delete_group(group_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM monitored_groups WHERE id = ?", (group_id,))
    if cursor.rowcount == 0:
        return make_error_response(
            code="NOT_FOUND",
            message=f"Không tìm thấy nhóm với ID {group_id}.",
            status_code=404
        )
    conn.commit()
    return {"success": True, "data": {"id": group_id, "message": "Đã xóa nhóm theo dõi thành công"}}
