import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import argparse
from rich.console import Console
from rich.table import Table

from config import TARGET_GROUPS
from scraper import run_scraper
import database
import export_data

console = Console()

def display_recent_posts(limit: int = 10):
    """Hiển thị bảng tóm tắt các bài viết gần nhất trong database."""
    database.init_db()
    posts = database.get_all_posts(limit=limit)
    if not posts:
        console.print("[yellow]Chưa có bài viết nào trong Database. Hãy chạy cào dữ liệu trước.[/yellow]")
        return

    table = Table(title=f"Danh Sách {len(posts)} Bài Viết Gần Nhất Đã Lưu")
    table.add_column("Post ID", style="cyan", no_wrap=True)
    table.add_column("Nhóm", style="magenta")
    table.add_column("Tác giả", style="green")
    table.add_column("Thời gian", style="yellow")
    table.add_column("Nội dung trích đoạn", style="white")

    for p in posts:
        content_preview = (p["content"][:45] + "...") if p["content"] else "(Ảnh / Video)"
        table.add_row(
            p["post_id"],
            p["group_name"],
            p["author_name"],
            p["created_time"] or "N/A",
            content_preview.replace("\n", " ")
        )

    console.print(table)

def display_monitored_groups():
    """Hiển thị bảng danh sách các nhóm đang quản lý trong database."""
    database.init_db()
    groups = database.get_all_monitored_groups()
    if not groups:
        console.print("[yellow]Chưa có nhóm nào trong danh sách theo dõi.[/yellow]")
        return

    table = Table(title=f"Danh Sách Nhóm Facebook Theo Dõi ({len(groups)} nhóm)")
    table.add_column("ID", style="cyan", justify="center", no_wrap=True)
    table.add_column("Tên Nhóm", style="magenta")
    table.add_column("Trạng Thái", justify="center")
    table.add_column("Đường Link (URL)", style="blue")
    table.add_column("Lần cào gần nhất", style="yellow")

    for g in groups:
        status_text = "[bold green]BẬT[/bold green]" if g["is_active"] == 1 else "[bold red]TẮT[/bold red]"
        last_scraped = g.get("last_scraped_at") or "Chưa cào"
        table.add_row(
            str(g["id"]),
            g["name"],
            status_text,
            g["url"],
            str(last_scraped)
        )
    console.print(table)

def manage_groups_menu():
    """Menu tương tác quản lý nhóm: Xem, Thêm nhóm, Bật/Tắt, Xóa nhóm."""
    while True:
        console.print("\n[bold purple]------------- QUẢN LÝ NHÓM THEO DÕI FACEBOOK -------------[/bold purple]")
        display_monitored_groups()
        console.print("\n1. [bold green]Thêm nhóm Facebook mới[/bold green]")
        console.print("2. [bold yellow]Bật / Tắt theo dõi một nhóm (Toggle)[/bold yellow]")
        console.print("3. [bold red]Xóa nhóm khỏi danh sách theo dõi[/bold red]")
        console.print("0. Quay lại menu chính")
        sub_choice = input("Chọn thao tác (1/2/3/0): ").strip()

        if sub_choice == "1":
            name = input("Nhập tên hiển thị của nhóm: ").strip()
            if not name:
                console.print("[red]Tên nhóm không được để trống![/red]")
                continue
            url = input("Nhập URL nhóm Facebook (https://www.facebook.com/groups/...): ").strip()
            if not url:
                console.print("[red]URL nhóm không được để trống![/red]")
                continue
            ok, msg = database.add_monitored_group(name, url)
            if ok:
                console.print(f"[bold green]✓ {msg}[/bold green]")
            else:
                console.print(f"[bold red]X {msg}[/bold red]")
        elif sub_choice == "2":
            gid = input("Nhập ID của nhóm muốn Bật/Tắt: ").strip()
            if gid.isdigit():
                ok, msg = database.toggle_monitored_group(int(gid))
                console.print(f"[bold cyan]>> {msg}[/bold cyan]")
            else:
                console.print("[red]ID phải là số nguyên![/red]")
        elif sub_choice == "3":
            gid = input("Nhập ID của nhóm muốn XÓA: ").strip()
            if gid.isdigit():
                confirm = input(f"Bạn có chắc muốn xóa nhóm #{gid}? (y/N): ").strip().lower()
                if confirm == "y":
                    ok, msg = database.delete_monitored_group(int(gid))
                    console.print(f"[bold yellow]>> {msg}[/bold yellow]")
            else:
                console.print("[red]ID phải là số nguyên![/red]")
def display_channel_configs():
    """Hiển thị bảng cấu hình output của 4 kênh Discord."""
    database.init_db()
    channels = database.get_all_channel_configs()
    table = Table(title="Cấu Hình Output Từng Kênh Discord (Webhooks & Bộ Lọc)")
    table.add_column("Key", style="cyan", justify="center", no_wrap=True)
    table.add_column("Tên Kênh", style="magenta")
    table.add_column("Trạng Thái", justify="center")
    table.add_column("Ngưỡng % Giảm", justify="center", style="yellow")
    table.add_column("Mention Tag", style="green")
    table.add_column("Hình Ảnh", justify="center")
    table.add_column("Webhook URL", style="blue")

    for c in channels:
        status_text = "[bold green]BẬT[/bold green]" if c.get("is_enabled", 1) == 1 else "[bold red]TẮT[/bold red]"
        min_disc = f"{c.get('min_discount', 0)}%" if c.get("channel_key") in ("deal_1", "deal_2") else "N/A"
        img_text = "Hiện ảnh" if c.get("show_images", 1) == 1 else "Ẩn ảnh"
        wh = c.get("webhook_url") or ""
        wh_display = (wh[:32] + "...") if len(wh) > 35 else (wh or "Chưa có")
        table.add_row(
            c["channel_key"],
            c["name"],
            status_text,
            min_disc,
            c.get("mention_tag") or "(Không)",
            img_text,
            wh_display
        )
    console.print(table)

def manage_channels_menu():
    """Menu tương tác tùy chỉnh cấu hình kênh Discord."""
    while True:
        console.print("\n[bold blue]------------- CẤU HÌNH OUTPUT TỪNG KÊNH DISCORD -------------[/bold blue]")
        display_channel_configs()
        console.print("\n1. [bold yellow]Bật / Tắt một kênh[/bold yellow]")
        console.print("2. [bold cyan]Thay đổi Webhook URL cho kênh[/bold cyan]")
        console.print("3. [bold green]Chỉnh ngưỡng chiết khấu tối thiểu (%) cho kênh Kèo[/bold green]")
        console.print("4. [bold magenta]Cài đặt Tag Mention (@everyone, @here hoặc ID Role)[/bold magenta]")
        console.print("5. [bold white]Bật / Tắt hiển thị ảnh thumbnail cho kênh[/bold white]")
        console.print("0. Quay lại menu chính")
        sub = input("Chọn thao tác (1/2/3/4/5/0): ").strip()

        if sub == "1":
            key = input("Nhập Key của kênh (deal_1 / deal_2 / buy / log): ").strip().lower()
            cfg = database.get_channel_config(key)
            if not cfg:
                console.print("[red]Key kênh không tồn tại![/red]")
                continue
            new_state = 0 if cfg.get("is_enabled", 1) == 1 else 1
            ok, msg = database.update_channel_config(key, is_enabled=new_state)
            console.print(f"[bold cyan]>> {msg}[/bold cyan]")
        elif sub == "2":
            key = input("Nhập Key của kênh (deal_1 / deal_2 / buy / log): ").strip().lower()
            new_wh = input("Dán link Discord Webhook URL mới: ").strip()
            if not new_wh.startswith("http"):
                console.print("[red]Link Webhook không hợp lệ![/red]")
                continue
            ok, msg = database.update_channel_config(key, webhook_url=new_wh)
            console.print(f"[bold green]✓ {msg}[/bold green]")
        elif sub == "3":
            key = input("Nhập Key kênh kèo (deal_1 hoặc deal_2): ").strip().lower()
            val = input("Nhập mức giảm giá tối thiểu mong muốn (ví dụ: 15 hoặc 20): ").strip()
            try:
                disc = float(val)
                ok, msg = database.update_channel_config(key, min_discount=disc)
                console.print(f"[bold green]✓ {msg}[/bold green]")
            except ValueError:
                console.print("[red]Giá trị phải là số thực![/red]")
        elif sub == "4":
            key = input("Nhập Key của kênh (deal_1 / deal_2 / buy / log): ").strip().lower()
            val = input("Nhập chuỗi Mention (ví dụ: @everyone, @here, hoặc bấm Enter để xóa tag): ").strip()
            ok, msg = database.update_channel_config(key, mention_tag=val)
            console.print(f"[bold green]✓ {msg}[/bold green]")
        elif sub == "5":
            key = input("Nhập Key của kênh (deal_1 / deal_2 / buy / log): ").strip().lower()
            cfg = database.get_channel_config(key)
            if not cfg:
                console.print("[red]Key kênh không tồn tại![/red]")
                continue
            new_img = 0 if cfg.get("show_images", 1) == 1 else 1
            ok, msg = database.update_channel_config(key, show_images=new_img)
            console.print(f"[bold cyan]>> {msg}[/bold cyan]")
        elif sub == "0":
            break
        else:
            console.print("[red]Lựa chọn không hợp lệ![/red]")

def main():
    parser = argparse.ArgumentParser(description="Tool Scrape Bài Viết Mới Nhất Facebook Group")
    parser.add_argument("--run", action="store_true", help="Chạy cào dữ liệu 1 lượt ngay lập tức")
    parser.add_argument("--loop", type=int, nargs="?", const=10, help="Chạy tự động liên tục mỗi N phút (mặc định 10 phút)")
    parser.add_argument("--export", action="store_true", help="Xuất dữ liệu ra file CSV và JSON")
    parser.add_argument("--view", action="store_true", help="Xem các bài viết đã lưu gần đây")
    parser.add_argument("--groups", action="store_true", help="Xem danh sách nhóm đang theo dõi")
    parser.add_argument("--channels", action="store_true", help="Xem cấu hình output hiện tại của 4 kênh Discord")
    parser.add_argument("--add-group", nargs=2, metavar=("NAME", "URL"), help="Thêm nhóm mới: --add-group 'Tên Nhóm' 'https://facebook.com/groups/...'")
    parser.add_argument("--toggle-group", type=int, metavar="ID", help="Bật/Tắt theo dõi nhóm theo ID")
    parser.add_argument("--app", action="store_true", help="Khởi động FB Monitor Hunter v2.0 (System Tray + 3D Dashboard)")
    parser.add_argument("--dashboard", action="store_true", help="Khởi động FB Monitor Hunter v2.0")

    args = parser.parse_args()

    if args.app or args.dashboard:
        from app.supervisor import AppSupervisor
        AppSupervisor().run()
        return

    database.init_db()

    if args.channels:
        display_channel_configs()
        return

    if args.add_group:
        name, url = args.add_group
        ok, msg = database.add_monitored_group(name, url)
        if ok:
            console.print(f"[bold green]✓ {msg}[/bold green]")
        else:
            console.print(f"[bold red]X {msg}[/bold red]")
        return

    if args.toggle_group is not None:
        ok, msg = database.toggle_monitored_group(args.toggle_group)
        console.print(f"[bold cyan]>> {msg}[/bold cyan]")
        return

    if args.groups:
        display_monitored_groups()
        return

    if args.loop:
        interval_min = args.loop
        console.print(f"[bold green]>> Bật chế độ chạy tự động liên tục: Mỗi {interval_min} phút quét 1 lần.[/bold green]")
        console.print("[dim]Nhấn Ctrl + C để dừng bất kỳ lúc nào.[/dim]\n")
        import time
        while True:
            try:
                run_scraper()
                export_data.export_to_csv()
                console.print(f"[bold cyan]>> Hoàn thành lượt quét. Nghỉ {interval_min} phút trước chu kỳ tiếp theo...[/bold cyan]\n")
                time.sleep(interval_min * 60)
            except KeyboardInterrupt:
                console.print("\n[yellow]Đã dừng vòng lặp tự động.[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]X Lỗi trong chu kỳ: {e}[/red]")
                time.sleep(30)
        return

    if args.run:
        run_scraper()
        export_data.export_to_csv()
        export_data.export_to_json()
        return

    if args.export:
        export_data.export_to_csv()
        export_data.export_to_json()
        return

    if args.view:
        display_recent_posts()
        return

    # Menu tương tác mặc định nếu không truyền tham số dòng lệnh
    while True:
        stats = database.get_system_stats()
        console.print("\n[bold cyan]================ MÀN HÌNH ĐIỀU KHIỂN CÀO FACEBOOK GROUP ================[/bold cyan]")
        console.print(f"Tổng bài trong DB: [bold]{stats['total_posts']}[/bold] | Kèo thơm: [bold green]{stats['total_deals']}[/bold green] | Đang theo dõi: [bold magenta]{stats['active_groups']}/{stats['total_groups']} nhóm[/bold magenta]")
        console.print("────────────────────────────────────────────────────────────────────────")
        console.print("1. [bold green]Bắt đầu cào bài viết mới nhất ngay[/bold green] (Tất cả nhóm đang BẬT)")
        console.print("2. [bold purple]Quản lý nhóm Facebook[/bold purple] (Xem danh sách / Thêm nhóm / Bật tắt / Xóa)")
        console.print("3. [bold blue]Cấu hình Output từng kênh Discord[/bold blue] (Bật/tắt, đổi Webhook, đổi Ngưỡng %, Mention...)")
        console.print("4. [bold yellow]Xem các bài viết đã lưu trong Database[/bold yellow]")
        console.print("5. [bold cyan]Xuất dữ liệu ra file Excel (CSV) và JSON[/bold cyan]")
        console.print("6. [bold magenta]Gửi thử thông báo mẫu qua Discord Webhook[/bold magenta]")
        console.print("7. [bold red]Bật chế độ săn kèo tự động liên tục 24/7[/bold red] (Quét định kỳ)")
        console.print("8. [bold green]Khởi động FB Monitor Hunter v2.0 (System Tray + 3D Dashboard)[/bold green]")
        console.print("0. Thoát")
        choice = input("Vui lòng chọn (1/2/3/4/5/6/7/8/0): ").strip()

        if choice == "8":
            from app.supervisor import AppSupervisor
            AppSupervisor().run()
            break

        if choice == "1":
            run_scraper()
            export_data.export_to_csv()
            export_data.export_to_json()
        elif choice == "2":
            manage_groups_menu()
        elif choice == "3":
            manage_channels_menu()
        elif choice == "4":
            display_recent_posts(limit=15)
        elif choice == "5":
            export_data.export_to_csv()
            export_data.export_to_json()
        elif choice == "6":
            import discord_notifier
            discord_notifier.test_discord_webhook()
        elif choice == "7":
            mins_str = input("Nhập số phút giữa các lần quét (mặc định 10 phút): ").strip()
            mins = int(mins_str) if mins_str.isdigit() and int(mins_str) > 0 else 10
            console.print(f"[bold green]>> Đang chạy săn kèo tự động: Cứ {mins} phút quét 1 lần.[/bold green]")
            console.print("[dim]Nhấn phím Ctrl + C để dừng bất kỳ lúc nào.[/dim]\n")
            import time
            while True:
                try:
                    run_scraper()
                    export_data.export_to_csv()
                    console.print(f"[bold cyan]>> Đang nghỉ {mins} phút trước lượt quét tiếp theo...[/bold cyan]\n")
                    time.sleep(mins * 60)
                except KeyboardInterrupt:
                    console.print("\n[yellow]Đã dừng chế độ tự động.[/yellow]")
                    break
                except Exception as e:
                    console.print(f"[red]X Lỗi trong chu kỳ: {e}[/red]")
                    time.sleep(30)
        elif choice == "0":
            console.print("[dim]Tạm biệt![/dim]")
            break
        else:
            console.print("[red]Lựa chọn không hợp lệ, vui lòng chọn lại.[/red]")

if __name__ == "__main__":
    main()
