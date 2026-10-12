import os
import sys
import time
import threading
import webbrowser
from typing import Optional
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu
from app.config import get_setting, set_setting
from app.state import state_manager, health_color
from app.paths import get_app_dir

def create_color_icon(color_hex: str) -> Image.Image:
    """Generates a dynamic 64x64 smooth circular tray icon with a colored core."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer dark glass rim
    draw.ellipse([4, 4, size - 4, size - 4], fill=(15, 23, 42, 230), outline=(255, 255, 255, 40), width=2)
    # Inner vibrant status core
    draw.ellipse([16, 16, size - 16, size - 16], fill=color_hex)
    return image

ICONS = {
    "green": create_color_icon("#10B981"),
    "amber": create_color_icon("#F59E0B"),
    "red": create_color_icon("#EF4444")
}

class SystemTrayApp:
    def __init__(self, on_scan_now=None, on_quit=None):
        self.on_scan_now = on_scan_now
        self.on_quit = on_quit
        self.icon: Optional[pystray.Icon] = None
        self._current_color = "amber"
        self._monitor_running = False

    def open_dashboard(self, icon=None, item=None):
        port = get_setting("web_port", 8080)
        webbrowser.open(f"http://127.0.0.1:{port}")

    def trigger_scan(self, icon=None, item=None):
        if self.on_scan_now:
            self.on_scan_now()
        else:
            state_manager.add_log("INFO", "Kích hoạt quét nhanh từ Khay hệ thống", "tray")

    def toggle_pause(self, icon=None, item=None):
        state = state_manager.get_state()
        new_paused = not state.is_paused
        state_manager.update(is_paused=new_paused)
        state_manager.add_log("INFO", f"Đã {'tạm dừng' if new_paused else 'tiếp tục'} quét từ khay hệ thống", "tray")

    def toggle_autostart(self, icon=None, item=None):
        current = get_setting("autostart", False)
        set_setting("autostart", not current)
        # Apply to Windows Registry if running on Windows
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.HKEY_CURRENT_USER
                sub_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(key, sub_key, 0, winreg.KEY_SET_VALUE) as reg:
                    if not current:
                        exe_path = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
                        winreg.SetValueEx(reg, "FBMonitorHunter", 0, winreg.REG_SZ, f'"{exe_path}"')
                    else:
                        try:
                            winreg.DeleteValue(reg, "FBMonitorHunter")
                        except FileNotFoundError:
                            pass
            except Exception:
                pass

    def quit_app(self, icon=None, item=None):
        if self.icon:
            self.icon.stop()
        if self.on_quit:
            self.on_quit()

    def _build_menu(self) -> Menu:
        return Menu(
            item("📊 Mở Dashboard", self.open_dashboard, default=True),
            item("⚡ Quét Ngay", self.trigger_scan),
            item(
                lambda text: "▶️ Tiếp Tục Quét" if state_manager.get_state().is_paused else "⏸️ Tạm Dừng Quét",
                self.toggle_pause
            ),
            Menu.SEPARATOR,
            item(
                "🚀 Khởi Động Cùng Windows",
                self.toggle_autostart,
                checked=lambda item: get_setting("autostart", False)
            ),
            Menu.SEPARATOR,
            item("❌ Thoát", self.quit_app)
        )

    def _status_monitor_loop(self):
        while self._monitor_running:
            state = state_manager.get_state()
            color = health_color(state)
            if color != self._current_color and self.icon:
                self._current_color = color
                self.icon.icon = ICONS.get(color, ICONS["amber"])
                self.icon.title = f"FB Monitor Hunter ({state.status.upper()})"
            time.sleep(2.0)

    def run(self):
        """Runs the pystray loop on the MAIN THREAD (blocking until quit)."""
        initial_img = ICONS.get("amber")
        self.icon = pystray.Icon(
            "FBMonitorHunter",
            initial_img,
            "FB Monitor Hunter v2.0",
            menu=self._build_menu()
        )

        self._monitor_running = True
        monitor_thread = threading.Thread(target=self._status_monitor_loop, daemon=True, name="TrayMonitor")
        monitor_thread.start()

        self.icon.run()
