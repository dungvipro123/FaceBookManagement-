import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import json
from playwright.sync_api import sync_playwright
from rich.console import Console
from config import COOKIES_FILE, PROXY_SERVER

console = Console()

def login_and_save():
    console.print("[bold yellow]>> Khởi động trình duyệt để đăng nhập Facebook...[/bold yellow]")
    console.print("[dim]Hãy đăng nhập tài khoản phụ/clone của bạn trên cửa sổ vừa mở ra.[/dim]")
    console.print("[dim]Sau khi đăng nhập xong vào bảng tin, quay lại đây và nhấn phím ENTER để lưu cookie.[/dim]\n")

    with sync_playwright() as p:
        launch_kwargs = {"headless": False}
        if PROXY_SERVER and PROXY_SERVER.strip():
            launch_kwargs["proxy"] = {"server": PROXY_SERVER.strip()}
            console.print(f"[green]✓ Đang mở trình duyệt qua Proxy:[/green] [cyan]{PROXY_SERVER.strip()}[/cyan]")

        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="vi-VN"
        )
        page = context.new_page()
        page.goto("https://www.facebook.com/")

        input(">> Nhấn ENTER tại đây sau khi bạn đã đăng nhập thành công trên trình duyệt... ")

        cookies = context.cookies()
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

        console.print(f"[bold green]✓ Đã lưu {len(cookies)} cookies vào file {COOKIES_FILE} thành công![/bold green]")
        console.print("[green]Từ bây giờ bạn có thể chạy scraper tự động mà không lo bị Facebook hỏi đăng nhập.[/green]")
        browser.close()

if __name__ == "__main__":
    login_and_save()
