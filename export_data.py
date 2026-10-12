import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import csv
import json
from rich.console import Console
import database

console = Console()

def export_to_csv(output_path: str = "facebook_posts.csv"):
    """
    Xuất toàn bộ bài viết từ SQLite ra file CSV với định dạng UTF-8-SIG (chuẩn mở trên Excel tiếng Việt không bị lỗi font).
    """
    posts = database.get_all_posts(limit=10000)
    if not posts:
        console.print("[yellow]Chưa có dữ liệu bài viết nào trong cơ sở dữ liệu để xuất.[/yellow]")
        return

    fieldnames = [
        "post_id",
        "group_name",
        "group_url",
        "author_name",
        "author_url",
        "model",
        "deal_price",
        "market_price",
        "discount_pct",
        "is_deal",
        "created_time",
        "content",
        "media_urls",
        "post_url",
        "crawled_at"
    ]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in posts:
            writer.writerow({
                "post_id": p.get("post_id"),
                "group_name": p.get("group_name"),
                "group_url": p.get("group_url"),
                "author_name": p.get("author_name"),
                "author_url": p.get("author_url"),
                "model": p.get("model", ""),
                "deal_price": p.get("deal_price", 0),
                "market_price": p.get("market_price", 0),
                "discount_pct": p.get("discount_pct", 0),
                "is_deal": p.get("is_deal", 0),
                "created_time": p.get("created_time"),
                "content": p.get("content"),
                "media_urls": p.get("media_urls"),
                "post_url": p.get("post_url"),
                "crawled_at": p.get("crawled_at")
            })

    console.print(f"[bold green]✓ Đã xuất {len(posts)} bài viết ra file CSV:[/bold green] [cyan]{output_path}[/cyan]")

def export_to_json(output_path: str = "facebook_posts.json"):
    """
    Xuất dữ liệu bài viết ra file JSON có format thụt lề dễ đọc.
    """
    posts = database.get_all_posts(limit=10000)
    if not posts:
        console.print("[yellow]Chưa có dữ liệu bài viết nào trong cơ sở dữ liệu để xuất.[/yellow]")
        return

    formatted_posts = []
    for p in posts:
        p_dict = dict(p)
        try:
            p_dict["media_urls"] = json.loads(p_dict.get("media_urls", "[]"))
        except Exception:
            p_dict["media_urls"] = []
        formatted_posts.append(p_dict)

    with open(output_path, mode="w", encoding="utf-8") as f:
        json.dump(formatted_posts, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]✓ Đã xuất {len(posts)} bài viết ra file JSON:[/bold green] [cyan]{output_path}[/cyan]")

if __name__ == "__main__":
    export_to_csv()
    export_to_json()
