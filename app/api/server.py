import asyncio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from app.paths import get_static_dir
from app.db import init_db
from app.api.sse import sse_manager
from app.api.middleware import SecurityMiddleware, make_error_response
from app.api.routes_auth import router as auth_router
from app.api.routes_status import router as status_router
from app.api.routes_groups import router as groups_router
from app.api.routes_channels import router as channels_router
from app.api.routes_settings import router as settings_router
from app.api.routes_logs import router as logs_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="FB Monitor Hunter API",
        version="2.0.0",
        docs_url=None,    # Disable default swagger docs in production command-center
        redoc_url=None,
    )

    # 1. Mount Security Middleware
    app.add_middleware(SecurityMiddleware)

    # 2. Unified Exception Handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Dữ liệu đầu vào không hợp lệ.",
                    "details": {"errors": exc.errors()}
                }
            }
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code_map = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
            500: "INTERNAL_ERROR"
        }
        err_code = code_map.get(exc.status_code, "ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": err_code,
                    "message": str(exc.detail),
                    "details": {}
                }
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Đã xảy ra lỗi nội bộ máy chủ.",
                    "details": {"exception": str(exc)}
                }
            }
        )

    # 3. Mount Routers
    app.include_router(auth_router)
    app.include_router(status_router)
    app.include_router(groups_router)
    app.include_router(channels_router)
    app.include_router(settings_router)
    app.include_router(logs_router)

    # 4. Mount Static Assets
    static_dir = get_static_dir()
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    @app.on_event("startup")
    async def on_startup():
        init_db()
        loop = asyncio.get_running_loop()
        sse_manager.set_loop(loop)

    return app

app = create_app()
