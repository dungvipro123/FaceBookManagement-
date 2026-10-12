import hmac
import socket
from typing import Set
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config import get_setting
from app.api.auth import is_loopback, is_valid_session, verify_pin

def get_lan_ip() -> str:
    """Detects local LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def make_error_response(code: str, message: str, status_code: int, details: dict = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {}
            }
        }
    )

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "127.0.0.1"
        lan_enabled = get_setting("lan_access_enabled", False)
        web_port = get_setting("web_port", 8080)

        # 1. Host Allow-List on ALL HTTP methods
        host_header = request.headers.get("host", "").split(":")[0].strip().lower()
        allowed_hosts = {"127.0.0.1", "localhost", "testclient", "testserver"}
        if lan_enabled:
            allowed_hosts.add(get_lan_ip())
            # Also allow whatever host the server is bound to if LAN mode is on
            if request.url.hostname:
                allowed_hosts.add(request.url.hostname.lower())

        if host_header not in allowed_hosts:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"Host '{host_header}' is not permitted by host allow-list.",
                        "details": {"host": host_header}
                    }
                }
            )

        # 2. Origin/Referer check on non-GET methods
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                origin_host = origin.split("://")[-1].split(":")[0].strip().lower()
                if origin_host not in allowed_hosts:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "error": {
                                "code": "FORBIDDEN",
                                "message": f"Origin '{origin}' is not permitted.",
                                "details": {"origin": origin}
                            }
                        }
                    )

        # 3. Authentication check for LAN clients
        path = request.url.path
        if not is_loopback(client_ip):
            if not lan_enabled:
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": {
                            "code": "FORBIDDEN",
                            "message": "Mạng LAN chưa được kích hoạt trong cài đặt.",
                            "details": {}
                        }
                    }
                )

            # Public paths on LAN
            if path in ("/api/auth/login", "/api/health") or not path.startswith("/api/"):
                return await call_next(request)

            # Check Cookie session_token
            session_token = request.cookies.get("session_token")
            if session_token and is_valid_session(session_token):
                return await call_next(request)

            # Check X-Dashboard-PIN header
            pin_header = request.headers.get("x-dashboard-pin")
            if pin_header and verify_pin(pin_header, client_ip):
                return await call_next(request)

            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Yêu cầu đăng nhập hoặc mã PIN để truy cập qua mạng LAN.",
                        "details": {}
                    }
                }
            )

        return await call_next(request)
