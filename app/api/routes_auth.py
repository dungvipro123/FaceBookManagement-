from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from app.api.auth import is_loopback, is_ip_locked, verify_pin, create_session, revoke_session, rotate_pin
from app.api.middleware import make_error_response

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    pin: str

@router.post("/login")
async def login(req: Request, body: LoginRequest, response: Response):
    client_ip = req.client.host if req.client else "127.0.0.1"
    
    if is_ip_locked(client_ip):
        return make_error_response(
            code="RATE_LIMITED",
            message="Đã thử sai quá nhiều lần. Vui lòng thử lại sau 15 phút.",
            status_code=429
        )
    
    if not verify_pin(body.pin, client_ip):
        return make_error_response(
            code="FORBIDDEN",
            message="Mã PIN không chính xác.",
            status_code=403
        )
    
    token = create_session()
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=30 * 86400,
        httponly=True,
        samesite="lax",
        path="/"
    )
    return {"success": True, "data": {"message": "Đăng nhập thành công"}}

@router.post("/logout")
async def logout(req: Request, response: Response):
    token = req.cookies.get("session_token")
    if token:
        revoke_session(token)
    response.delete_cookie("session_token", path="/")
    return {"success": True, "data": {"message": "Đã đăng xuất"}}

@router.post("/rotate-pin")
async def handle_rotate_pin(req: Request):
    client_ip = req.client.host if req.client else "127.0.0.1"
    if not is_loopback(client_ip):
        return make_error_response(
            code="FORBIDDEN",
            message="Thao tác xoay vòng PIN chỉ được phép thực hiện từ loopback (localhost).",
            status_code=403
        )
    
    new_pin = rotate_pin()
    return {
        "success": True,
        "data": {
            "pin": new_pin,
            "message": "Mã PIN mới đã được tạo và toàn bộ session cũ đã bị thu hồi."
        }
    }
