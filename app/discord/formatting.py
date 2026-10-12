from datetime import datetime, timezone
from typing import Dict, Any, Optional

def format_vnd(amount: int) -> str:
    """Formats integer amount to Vietnamese Dong string: 2,700,000 đ."""
    return f"{amount:,.0f} đ".replace(",", ".")

def build_deal_payload(post: dict, channel_config: dict) -> dict:
    is_dealer = bool(post.get("is_dealer", 0))
    product_name = post.get("model") or post.get("product_name") or "Màn hình PC"
    deal_price = post.get("deal_price", 0)
    market_price = post.get("market_price", 0)
    dealer_buy_price = post.get("dealer_buy_price", 0)
    discount_pct = post.get("discount_pct", 0.0)
    profit = post.get("profit", max(0, market_price - deal_price))
    author_name = post.get("author_name", "Không rõ")
    group_name = post.get("group_name", "Nhóm Facebook")
    post_url = post.get("post_url", "https://facebook.com")
    content_snippet = (post.get("content", "")[:280] + "...") if len(post.get("content", "")) > 280 else post.get("content", "")

    if is_dealer:
        embed_title = f"📦 [THỢ/SHOP XẢ HÀNG] {product_name} - Giảm {discount_pct}%"
        embed_color = 0xE67E22  # Orange
    else:
        embed_title = f"⭐ [NGƯỜI DÙNG PASS] {product_name} - Rẻ hơn {discount_pct}%!"
        embed_color = 0x10B981  # Emerald green

    fields = [
        {"name": "💰 Giá người bán rao", "value": f"**{format_vnd(deal_price)}**", "inline": True},
        {"name": "🎯 Giá thợ nên thu", "value": f"**{format_vnd(dealer_buy_price)}**" if dealer_buy_price else "Thỏa thuận", "inline": True},
        {"name": "📊 Giá thị trường", "value": format_vnd(market_price), "inline": True},
        {"name": "📈 Lãi dự tính khi bán lại", "value": f"**+{format_vnd(profit)}** ({discount_pct}%)", "inline": True},
        {"name": "👤 Người bán", "value": author_name, "inline": True},
        {"name": "👥 Nhóm Facebook", "value": group_name, "inline": True},
    ]

    embed = {
        "title": embed_title,
        "url": post_url,
        "description": f"```{content_snippet}```",
        "color": embed_color,
        "fields": fields,
        "footer": {"text": f"FB Monitor Hunter v2.0 • {post.get('created_time', 'Vừa xong')}"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    thumbnail_url = post.get("thumbnail_url", "")
    if channel_config.get("show_images", 1) and thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}

    payload = {"embeds": [embed]}
    mention = channel_config.get("mention_tag", "").strip()
    if mention:
        payload["content"] = mention

    return payload

def build_buy_payload(post: dict, channel_config: dict) -> dict:
    author_name = post.get("author_name", "Không rõ")
    group_name = post.get("group_name", "Nhóm Facebook")
    post_url = post.get("post_url", "https://facebook.com")
    content_snippet = (post.get("content", "")[:350] + "...") if len(post.get("content", "")) > 350 else post.get("content", "")

    embed = {
        "title": f"🛒 [TÌM MUA] {author_name} đang tìm mua linh kiện",
        "url": post_url,
        "description": f"```{content_snippet}```",
        "color": 0x3B82F6,  # Blue
        "fields": [
            {"name": "👤 Khách hỏi mua", "value": author_name, "inline": True},
            {"name": "👥 Nhóm", "value": group_name, "inline": True},
            {"name": "🔗 Link bài viết", "value": f"[Bấm để nhắn tin chốt kèo]({post_url})", "inline": False},
        ],
        "footer": {"text": f"FB Monitor Hunter v2.0 • {post.get('created_time', 'Vừa xong')}"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    payload = {"embeds": [embed]}
    mention = channel_config.get("mention_tag", "").strip()
    if mention:
        payload["content"] = mention

    return payload

def build_log_embed(post: dict) -> dict:
    author = post.get("author_name", "Không rõ")
    group = post.get("group_name", "Nhóm Facebook")
    post_url = post.get("post_url", "https://facebook.com")
    content = post.get("content", "")
    snippet = (content[:150] + "...") if len(content) > 150 else content
    post_type = post.get("post_type", "SELL")

    return {
        "title": f"📋 [{post_type}] {author} tại {group}",
        "url": post_url,
        "description": snippet or "(Không có nội dung)",
        "color": 0x64748B,  # Slate
        "footer": {"text": f"ID: {post.get('post_id')} • {post.get('created_time', 'Vừa xong')}"}
    }
