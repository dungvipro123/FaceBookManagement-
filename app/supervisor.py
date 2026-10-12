import os
import sys
import time
import threading
import uvicorn
from app.config import get_setting
from app.state import state_manager
from app.db import init_db
from app.scraper.scheduler import scraper_scheduler
from app.tray import SystemTrayApp
from app.api.routes_status import set_restart_callback

class WindowsMutex:
    """Single-instance Windows mutex to prevent multiple instances."""
    def __init__(self, name="FBMonitorHunterSingleInstanceMutex"):
        self.mutex_name = name
        self.mutex = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        try:
            import win32event
            import winerror
            self.mutex = win32event.CreateMutex(None, False, self.mutex_name)
            if win32event.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                return False
            return True
        except ImportError:
            # Fallback if pywin32 is not installed
            return True

class AppSupervisor:
    def __init__(self, enable_tray: bool = True):
        self.enable_tray = enable_tray
        self.mutex = WindowsMutex()
        self._server = None
        self._server_thread = None
        self._stop_event = threading.Event()
        self.tray = None

    def start_api_server(self):
        port = get_setting("web_port", 8080)
        lan_enabled = get_setting("lan_access_enabled", False)
        host = "0.0.0.0" if lan_enabled else "127.0.0.1"

        config = uvicorn.Config(
            "app.api.server:app",
            host=host,
            port=port,
            log_level="warning",
            access_log=False
        )
        self._server = uvicorn.Server(config)
        self._server_thread = threading.Thread(target=self._server.run, daemon=True, name="ApiServerThread")
        self._server_thread.start()
        state_manager.add_log("INFO", f"Máy chủ Dashboard API đã lắng nghe tại http://{host}:{port}", "supervisor")

    def restart_api_server(self):
        if self._server:
            self._server.should_exit = True
            time.sleep(1.0)
            self.start_api_server()

    def shutdown(self):
        state_manager.add_log("INFO", "Đang dừng các tiến trình và thoát ứng dụng...", "supervisor")
        self._stop_event.set()
        scraper_scheduler.stop()
        if self._server:
            self._server.should_exit = True

    def run(self):
        # 1. Acquire single-instance mutex
        if not self.mutex.acquire():
            print("(!) FB Monitor Hunter v2.0 đang chạy ở một tiến trình khác.")
            return

        # 2. Initialize Database & Migrations
        init_db()

        # 3. Setup restart callback
        set_restart_callback(self.restart_api_server)

        # 4. Start Background Workers
        self.start_api_server()
        scraper_scheduler.start()

        # 5. Run Tray or CLI loop
        if self.enable_tray:
            self.tray = SystemTrayApp(
                on_scan_now=scraper_scheduler.trigger_scan_now,
                on_quit=self.shutdown
            )
            # pystray blocks on MAIN thread
            self.tray.run()
        else:
            # Headless / Console mode loop
            try:
                while not self._stop_event.is_set():
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.shutdown()
