import time
from fastapi import APIRouter, Query, Request
from app.state import state_manager
from app.db import get_connection
from app.config import get_setting
from app.api.middleware import make_error_response

router = APIRouter(prefix="/api", tags=["status"])
_APP_START_TIME = time.time()

# Hooks to trigger external background actions
SCAN_TRIGGER_CALLBACK = None
RESTART_SERVER_CALLBACK = None

def set_scan_trigger(callback):
    global SCAN_TRIGGER_CALLBACK
    SCAN_TRIGGER_CALLBACK = callback

def set_restart_callback(callback):
    global RESTART_SERVER_CALLBACK
    RESTART_SERVER_CALLBACK = callback

@router.get("/health")
async def health():
    uptime = int(time.time() - _APP_START_TIME)
    return {"status": "ok", "uptime_seconds": uptime}

@router.get("/status")
async def get_status():
    data = state_manager.to_dict()
    # Ensure active groups count is up to date from DB
    conn = get_connection()
    count_row = conn.execute("SELECT COUNT(*) FROM monitored_groups WHERE is_active = 1").fetchone()
    if count_row:
        data["active_groups_count"] = count_row[0]
        state_manager.update(active_groups_count=count_row[0])
    return {"success": True, "data": data}

@router.get("/deals")
async def get_deals(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_dealer: int = Query(None)
):
    conn = get_connection()
    offset = (page - 1) * limit
    
    where_clauses = ["is_deal = 1"]
    params = []
    if is_dealer is not None:
        where_clauses.append("is_dealer = ?")
        params.append(is_dealer)
        
    where_sql = " AND ".join(where_clauses)
    total_row = conn.execute(f"SELECT COUNT(*) FROM posts WHERE {where_sql}", params).fetchone()
    total = total_row[0] if total_row else 0
    
    query = f"""
    SELECT post_id, group_name, group_url, author_name, author_url, post_url,
           created_time, content, media_urls, model, deal_price, market_price,
           discount_pct, is_deal, post_type, is_dealer, dealer_buy_price, profit,
           thumbnail_url, crawled_at
    FROM posts
    WHERE {where_sql}
    ORDER BY crawled_at DESC
    LIMIT ? OFFSET ?
    """
    rows = conn.execute(query, params + [limit, offset]).fetchall()
    deals = [dict(r) for r in rows]
    
    return {
        "success": True,
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "deals": deals
        }
    }

@router.post("/actions/scan-now")
async def scan_now():
    state = state_manager.get_state()
    if state.is_scanning:
        return make_error_response(
            code="CONFLICT",
            message="Tiến trình quét đang chạy dở, vui lòng chờ hoàn thành.",
            status_code=409
        )
    
    if SCAN_TRIGGER_CALLBACK:
        SCAN_TRIGGER_CALLBACK()
        return {"success": True, "data": {"message": "Đã kích hoạt quét ngay lập tức"}}
    
    return {"success": True, "data": {"message": "Lệnh quét đã được tiếp nhận"}}

@router.post("/actions/pause")
async def pause_scan():
    state_manager.update(is_paused=True)
    state_manager.add_log("INFO", "Người dùng đã tạm dừng quét tự động", "scheduler")
    return {"success": True, "data": {"is_paused": True, "message": "Đã tạm dừng quét"}}

@router.post("/actions/resume")
async def resume_scan():
    state_manager.update(is_paused=False)
    state_manager.add_log("INFO", "Người dùng đã tiếp tục quét tự động", "scheduler")
    return {"success": True, "data": {"is_paused": False, "message": "Đã tiếp tục quét"}}

@router.post("/actions/test-quota")
async def test_quota():
    """
    Tests Gemini API key and model connectivity.
    Always returns HTTP 200 with status field according to CONTRACTS v2.1.
    """
    import os
    import requests
    import time
    
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = get_setting("gemini_model", "gemini-3.1-flash-lite")
    
    if not api_key:
        state_manager.record_gemini_latency(0.0, "network_error")
        return {
            "success": True,
            "data": {
                "status": "network_error",
                "message": "GEMINI_API_KEY chưa được cấu hình trong .env"
            }
        }
        
    start_time = time.time()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 5}
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=10)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        if resp.status_code == 200:
            state_manager.record_gemini_latency(latency_ms, "ok")
            return {
                "success": True,
                "data": {
                    "status": "ok",
                    "latency_ms": latency_ms,
                    "model": model
                }
            }
        elif resp.status_code == 429:
            state_manager.record_gemini_latency(latency_ms, "quota_exceeded")
            return {
                "success": True,
                "data": {
                    "status": "quota_exceeded",
                    "message": "Quá hạn mức API Gemini (HTTP 429 Rate Limited)"
                }
            }
        elif resp.status_code == 404:
            state_manager.record_gemini_latency(latency_ms, "model_not_found")
            return {
                "success": True,
                "data": {
                    "status": "model_not_found",
                    "message": f"Không tìm thấy model '{model}' (HTTP 404). Hãy đổi sang 'gemini-3.1-flash-lite' hoặc 'gemini-2.0-flash'."
                }
            }
        elif resp.status_code in (400, 403):
            err_details = ""
            try:
                err_data = resp.json().get("error", {})
                err_details = err_data.get("message", "")
                if "API_KEY_INVALID" in str(err_data) or "API key not valid" in err_details:
                    state_manager.record_gemini_latency(latency_ms, "invalid_key")
                    return {
                        "success": True,
                        "data": {
                            "status": "invalid_key",
                            "message": "GEMINI_API_KEY không hợp lệ hoặc chưa được nhập đúng (API_KEY_INVALID). Vui lòng cập nhật API Key từ Google AI Studio vào tab Cài Đặt Hệ Thống."
                        }
                    }
            except Exception:
                pass
            state_manager.record_gemini_latency(latency_ms, "network_error")
            return {
                "success": True,
                "data": {
                    "status": "network_error",
                    "message": f"Gemini API từ chối ({resp.status_code}): {err_details or resp.text[:120]}"
                }
            }
        else:
            state_manager.record_gemini_latency(latency_ms, "network_error")
            return {
                "success": True,
                "data": {
                    "status": "network_error",
                    "message": f"Gemini API phản hồi lỗi HTTP {resp.status_code}"
                }
            }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        state_manager.record_gemini_latency(latency_ms, "network_error")
        return {
            "success": True,
            "data": {
                "status": "network_error",
                "message": f"Lỗi kết nối tới Gemini API: {str(e)}"
            }
        }

@router.post("/actions/restart-server")
async def restart_server():
    if RESTART_SERVER_CALLBACK:
        RESTART_SERVER_CALLBACK()
    return {
        "success": True,
        "data": {
            "message": "Yêu cầu khởi động lại máy chủ đã được gửi tới supervisor."
        }
    }
