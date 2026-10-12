import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from datetime import datetime, timezone
from rich.console import Console
from config import (
    DISCORD_DEAL_WEBHOOK_URL,
    DISCORD_DEAL_2_WEBHOOK_URL,
    DISCORD_BUY_WEBHOOK_URL,
    DISCORD_LOG_WEBHOOK_URL,
    DISCORD_WEBHOOK_URL
)

console = Console()

def send_deal_to_discord(deal_info: dict) -> bool:
    """
    Gửi thông báo 'Kèo Thơm' qua Discord:
    - Nếu là THỢ / SHOP đăng bài -> Đẩy vào KÊNH KÈO NGON 2 (deal_2)
    - Nếu là NGƯỜI DÙNG THỰC SỰ -> Đẩy vào KÊNH KÈO NGON 1 (deal_1)
    Đọc cấu hình động từ database (bật/tắt, webhook, ngưỡng %, mention, ảnh).
    """
    import database
    is_dealer = deal_info.get("is_dealer", False)
    channel_key = "deal_2" if is_dealer else "deal_1"

    cfg = database.get_channel_config(channel_key)
    if cfg and not cfg.get("is_enabled", 1):
        return False

    min_disc = cfg.get("min_discount", 15.0) if cfg else 15.0
    discount_pct = deal_info.get("discount_pct", 0)
    if discount_pct < min_disc:
        return False

    target_webhook = (cfg.get("webhook_url") if cfg else "").strip()
    if not target_webhook:
        target_webhook = (DISCORD_DEAL_2_WEBHOOK_URL if is_dealer else (DISCORD_DEAL_WEBHOOK_URL or DISCORD_WEBHOOK_URL)).strip()

    if not target_webhook:
        return False

    channel_tag = "KÈO NGON 2 (THỢ / SHOP XẢ)" if is_dealer else "KÈO NGON 1 (NGƯỜI DÙNG PASS)"

    product_name = deal_info.get("product_name", "Màn hình PC")
    deal_price = deal_info.get("deal_price", 0)
    market_price = deal_info.get("market_price", 0)
    discount_pct = deal_info.get("discount_pct", 0)
    save_amount = deal_info.get("save_amount", 0)
    author_name = deal_info.get("author_name", "Không rõ")
    group_name = deal_info.get("group_name", "Nhóm Facebook")
    post_url = deal_info.get("post_url", "https://facebook.com")
    content_snippet = deal_info.get("content", "")[:280] + ("..." if len(deal_info.get("content", "")) > 280 else "")

    if is_dealer:
        embed_title = f"📦 [THỢ/SHOP XẢ HÀNG] {product_name} - Chênh lệch {discount_pct}%"
        embed_color = 0xE67E22  # Màu cam đậm cho Thợ xả
    else:
        embed_title = f"⭐ [NGƯỜI DÙNG PASS ĐỒ] {product_name} - Rẻ hơn {discount_pct}%!"
        embed_color = 0xFF0033  # Màu đỏ rực cho Kèo người dùng xịn

    embed = {
        "title": embed_title,
        "url": post_url,
        "description": f"```{content_snippet}```",
        "color": embed_color,
        "fields": [
            {
                "name": "💰 Giá người bán rao",
                "value": f"**{deal_price:,.0f} đ**",
                "inline": True
            },
            {
                "name": "🎯 Giá thợ nên thu (để có lãi)",
                "value": f"**{deal_info.get('dealer_buy_price', market_price * 0.8):,.0f} đ**" if deal_info.get('dealer_buy_price') else "Thỏa thuận",
                "inline": True
            },
            {
                "name": "📊 Giá thị trường (bán lẻ cũ)",
                "value": f"{market_price:,.0f} đ",
                "inline": True
            },
            {
                "name": "📈 Lãi dự tính khi bán lại",
                "value": f"**+{deal_info.get('profit', save_amount):,.0f} đ** (Rẻ hơn {discount_pct}%)",
                "inline": True
            },
            {
                "name": "👤 Người bán",
                "value": author_name,
                "inline": True
            },
            {
                "name": "👥 Nhóm Facebook",
                "value": group_name,
                "inline": True
            },
            {
                "name": "🔗 Đường dẫn bài viết",
                "value": f"[👉 Bấm vào đây để mở đúng bài viết và inbox ngay]({post_url})",
                "inline": False
            }
        ],
        "footer": {
            "text": "Facebook Monitor Deal Sniper • Tự động dò kèo"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Đính kèm ảnh sản phẩm nếu kênh cho phép hiển thị ảnh
    show_images = cfg.get("show_images", 1) if cfg else 1
    if show_images:
        media_urls = deal_info.get("media_urls", [])
        if media_urls and len(media_urls) > 0:
            embed["image"] = {"url": media_urls[0]}

    payload = {
        "username": "Monitor Deal Sniper Bot",
        "avatar_url": "https://img.icons8.com/fluency/96/monitor.png",
        "embeds": [embed]
    }

    # Đính kèm tag mention nếu kênh có cấu hình (ví dụ: @everyone hoặc @here)
    mention_tag = (cfg.get("mention_tag") if cfg else "").strip()
    if mention_tag:
        payload["content"] = mention_tag

    try:
        response = requests.post(target_webhook.strip(), json=payload, timeout=10)
        if response.status_code in (200, 204):
            console.print(f"[bold green]✓ Đã bắn thông báo Kèo Thơm qua Discord Webhook ({channel_tag}) thành công![/bold green]")
            return True
        else:
            console.print(f"[yellow]! Discord Webhook trả về mã lỗi: {response.status_code} - {response.text}[/yellow]")
            return False
    except Exception as e:
        console.print(f"[red]X Lỗi khi gửi Discord Webhook: {e}[/red]")
        return False

def send_log_to_discord(post_data: dict) -> bool:
    """
    Gửi thông báo 'Log Bài Cào Mới' vào KÊNH LOG Discord cho mọi bài cào được.
    Đọc cấu hình động từ database (bật/tắt, webhook, mention, ảnh).
    """
    import database
    cfg = database.get_channel_config("log")
    if cfg and not cfg.get("is_enabled", 1):
        # Kênh Log đã bị người dùng TẮT
        return False

    target_webhook = (cfg.get("webhook_url") if cfg else "").strip()
    if not target_webhook:
        target_webhook = (DISCORD_LOG_WEBHOOK_URL or "").strip()

    if not target_webhook:
        return False

    group_name = post_data.get("group_name", "Nhóm Facebook")
    author_name = post_data.get("author_name", "Ẩn danh")
    created_time = post_data.get("created_time", "Vừa xong")
    post_url = post_data.get("post_url", "https://facebook.com")
    raw_content = post_data.get("content", "")
    content_snippet = raw_content[:260] + ("..." if len(raw_content) > 260 else "") if raw_content else "(Không có chữ, bài chỉ gồm ảnh/video)"

    # Phân loại bài viết Đăng Bán vs Tìm Mua
    from ai_appraiser import detect_post_type
    post_type = post_data.get("post_type") or detect_post_type(raw_content)

    if post_type == "BUY":
        embed_title = f"🔵 [TÌM MUA] - {group_name}"
        embed_color = 0x3498DB  # Xanh dương cho người tìm mua
        action_text = f"[👉 Bấm vào đây để xem và inbox báo giá ngay]({post_url})"
        role_label = "👤 Người tìm mua"
    else:
        embed_title = f"🟢 [ĐĂNG BÁN] - {group_name}"
        embed_color = 0x2ECC71  # Xanh lá cho người đăng bán
        action_text = f"[👉 Bấm vào đây để xem bài viết trên Facebook]({post_url})"
        role_label = "👤 Người đăng bán"

    embed = {
        "title": embed_title,
        "url": post_url,
        "description": f"```{content_snippet}```",
        "color": embed_color,
        "fields": [
            {
                "name": role_label,
                "value": author_name,
                "inline": True
            },
            {
                "name": "⏰ Thời gian",
                "value": created_time or "Mới đăng",
                "inline": True
            },
            {
                "name": "🔗 Đường dẫn",
                "value": action_text,
                "inline": False
            }
        ],
        "footer": {
            "text": "Facebook Scraper Live Feed Log"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    show_images = cfg.get("show_images", 1) if cfg else 1
    if show_images:
        media_urls = post_data.get("media_urls", [])
        if media_urls and len(media_urls) > 0:
            embed["thumbnail"] = {"url": media_urls[0]}

    payload = {
        "username": "Facebook Scraper Feed Bot",
        "avatar_url": "https://img.icons8.com/fluency/96/rss.png",
        "embeds": [embed]
    }

    mention_tag = (cfg.get("mention_tag") if cfg else "").strip()
    if mention_tag:
        payload["content"] = mention_tag

    try:
        response = requests.post(target_webhook.strip(), json=payload, timeout=8)
        return response.status_code in (200, 204)
    except Exception:
        return False

def send_buy_lead_to_discord(post_data: dict) -> bool:
    """
    Gửi thông báo bài TÌM MUA vào KÊNH KHÁCH TÌM MUA riêng biệt (buy).
    Đọc cấu hình động từ database (bật/tắt, webhook, mention, ảnh).
    """
    import database
    cfg = database.get_channel_config("buy")
    if cfg and not cfg.get("is_enabled", 1):
        # Kênh Khách Tìm Mua đã bị người dùng TẮT
        return False

    target_webhook = (cfg.get("webhook_url") if cfg else "").strip()
    if not target_webhook:
        target_webhook = (DISCORD_BUY_WEBHOOK_URL or "").strip()

    if not target_webhook:
        return False

    group_name = post_data.get("group_name", "Nhóm Facebook")
    author_name = post_data.get("author_name", "Ẩn danh")
    created_time = post_data.get("created_time", "Vừa xong")
    post_url = post_data.get("post_url", "https://facebook.com")
    raw_content = post_data.get("content", "")
    content_snippet = raw_content[:280] + ("..." if len(raw_content) > 280 else "")

    embed = {
        "title": f"🎯 [KHÁCH CẦN TÌM MUA] - {group_name}",
        "url": post_url,
        "description": f"```{content_snippet}```",
        "color": 0x00A8FF,  # Xanh Cyan cho Lead khách mua
        "fields": [
            {
                "name": "👤 Khách tìm mua",
                "value": f"**{author_name}**",
                "inline": True
            },
            {
                "name": "⏰ Thời gian đăng",
                "value": created_time or "Mới đăng",
                "inline": True
            },
            {
                "name": "💬 Hành động",
                "value": f"[👉 Bấm vào đây để mở bài viết và inbox chào hàng ngay]({post_url})",
                "inline": False
            }
        ],
        "footer": {
            "text": "Facebook Buyer Leads Sniper"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    show_images = cfg.get("show_images", 1) if cfg else 1
    if show_images:
        media_urls = post_data.get("media_urls", [])
        if media_urls and len(media_urls) > 0:
            embed["thumbnail"] = {"url": media_urls[0]}

    payload = {
        "username": "Buyer Lead Hunter",
        "avatar_url": "https://img.icons8.com/fluency/96/customer-insight.png",
        "embeds": [embed]
    }

    mention_tag = (cfg.get("mention_tag") if cfg else "").strip()
    if mention_tag:
        payload["content"] = mention_tag

    try:
        response = requests.post(target_webhook.strip(), json=payload, timeout=8)
        if response.status_code in (200, 204):
            console.print(f"[bold cyan]✓ Đã bắn bài TÌM MUA qua Discord Webhook (Kênh Tìm Mua) thành công![/bold cyan]")
            return True
        return False
    except Exception as e:
        console.print(f"[red]X Lỗi gửi Kênh Tìm Mua: {e}[/red]")
        return False

def send_quota_alert_to_discord(model_name: str, status_code: int, message: str = "") -> bool:
    """Gửi tin nhắn cảnh báo hạn mức API / Quota Gemini về kênh Log trên Discord."""
    if not DISCORD_LOG_WEBHOOK_URL or not DISCORD_LOG_WEBHOOK_URL.strip():
        return False

    embed = {
        "title": f"⚠️ CẢNH BÁO QUOTA GEMINI API (HTTP {status_code})",
        "description": f"Model **{model_name}** vừa gặp sự cố hạn mức request.\nChi tiết: ```{message[:300]}```",
        "color": 0xF1C40F if status_code in (429, 503) else 0xE74C3C,
        "fields": [
            {
                "name": "⚙ Hành động xử lý",
                "value": "Hệ thống tự động chuyển đổi sang model tiếp theo trong danh sách hoặc chuyển sang bộ định giá tĩnh Regex.",
                "inline": False
            }
        ],
        "footer": {
            "text": "FB Monitor Hunter • Quota Monitor"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    payload = {
        "username": "AI Quota Alert",
        "avatar_url": "https://img.icons8.com/fluency/96/high-priority.png",
        "embeds": [embed]
    }

    try:
        requests.post(DISCORD_LOG_WEBHOOK_URL.strip(), json=payload, timeout=5)
        return True
    except Exception:
        return False

def test_discord_webhook():
    """Hàm chạy thử gửi thông báo mẫu vào kênh Discord của bạn."""
    sample_deal = {
        "product_name": "Dell Ultrasharp U2422H",
        "deal_price": 2700000,
        "dealer_buy_price": 3000000,
        "market_price": 3600000,
        "discount_pct": 25.0,
        "profit": 900000,
        "save_amount": 900000,
        "author_name": "Vũ Trường Sơn",
        "group_name": "Màn Hình Hà Nội",
        "post_url": "https://www.facebook.com/groups/manhinhhanoi/posts/2450297459048381/",
        "content": "Cầu Diễn Sẵn Dell P3223Qe -32 inch 4k đồ hoạ cao cấp type C sạc 90w đẹp 99% fullbox bh 2026 giá chỉ 8tr5!",
        "media_urls": ["https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=500"]
    }
    console.print("[cyan]>> Đang gửi tin nhắn thử nghiệm tới Discord...[/cyan]")
    success = send_deal_to_discord(sample_deal)
    if not success and (not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.strip()):
        console.print("[yellow]Chưa cấu hình DISCORD_WEBHOOK_URL trong config.py. Hãy dán link Webhook vào trước.[/yellow]")

if __name__ == "__main__":
    test_discord_webhook()
