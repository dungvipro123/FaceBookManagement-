import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import re
import json
import requests
from typing import Optional, Dict, Any
from rich.console import Console

from config import GEMINI_API_KEY, MIN_DISCOUNT_PERCENT
import database
from price_parser import analyze_post_deal as fallback_regex_deal

console = Console()

# Danh sách từ khóa loại trừ ngay lập tức bằng code (tiết kiệm 100% token)
SKIP_BUY_KEYWORDS = [
    "cần mua", "tìm mua", "ai có", "mua màn", "hỏi", "xin tư vấn",
    "mua case", "tìm case", "mua vga", "thu mua"
]

# Từ khóa nhận diện THỢ / SHOP / CỬA HÀNG (trong tên người dùng)
DEALER_NAME_KEYWORDS = [
    "pc", "máy tính", "computer", "store", "shop", "linh kiện", 
    "máy in", "net", "gaming", "laptop", "thanh lý", "thu mua", 
    "rẻ bền", "phụ kiện"
]

# Từ khóa nhận diện THỢ / SHOP xả hàng (trong nội dung bài viết)
DEALER_CONTENT_KEYWORDS = [
    "dọn kho", "xả kho", "ôm lô", "sẵn sl", "sẵn vài chục", 
    "bảo hành cửa hàng", "bh 1 tháng", "bh 3 tháng", "bh 6 tháng", 
    "1 đổi 1", "nhận build pc", "thu cũ đổi mới", "đồng kiểm", 
    "ship cod toàn quốc", "sẵn sll", "giá thợ", "giá sỉ", "lô màn"
]

def check_is_dealer(post: dict, ai_data: Optional[dict] = None) -> bool:
    """
    Kiểm tra xem người đăng có phải là Thợ / Cửa hàng hay không:
    1. AI phân tích phong cách bài viết (is_dealer)
    2. Tên tác giả chứa từ khóa shop/máy tính
    3. Nội dung bài chứa từ khóa buôn/sỉ/dọn kho
    4. Tần suất tác giả đã từng đăng >= 3 bài trong database
    """
    author_name = (post.get("author_name") or "").lower()
    author_url = post.get("author_url", "")
    content = (post.get("content") or "").lower()

    # 1. Tần suất đăng nhiều bài trong quá khứ
    try:
        past_count = database.get_author_post_count(author_name, author_url)
        if past_count >= 3:
            return True
    except Exception:
        pass

    # 2. Tên tác giả là tên Shop / Cửa hàng
    clean_name = author_name.replace(" ", "")
    for kw in DEALER_NAME_KEYWORDS:
        clean_kw = kw.replace(" ", "")
        if kw in author_name or clean_kw in clean_name:
            return True

    # 3. Nội dung có từ ngữ thợ xả lô/dọn kho/bảo hành cửa hàng
    for kw in DEALER_CONTENT_KEYWORDS:
        if kw in content:
            return True

    # 4. Đánh giá từ Gemini AI
    if ai_data and ai_data.get("is_dealer"):
        return True

    return False

def is_worth_appraising(text: str) -> bool:
    """
    Bộ lọc trước bằng Python (0 Token):
    Chỉ gửi tới AI các bài BÁN và có dấu hiệu giá tiền, bỏ qua 100% bài hỏi mua/hỏi đáp/spam.
    """
    if not text or len(text.strip()) < 10:
        return False

    clean_text = text.lower()

    # Bỏ qua nếu là bài tìm mua
    for kw in SKIP_BUY_KEYWORDS:
        if kw in clean_text:
            return False

    # Phải có số hoặc dấu hiệu giá tiền (k, tr, củ, triệu, m, đ)
    has_price_sign = bool(re.search(r'\d+\s*(?:k|lít|tr|triệu|củ|m|đ|\.000)', clean_text))
    return has_price_sign

def appraise_with_gemini(post_text: str) -> Optional[Dict[str, Any]]:
    """
    Gọi Gemini 1.5/2.0 Flash với prompt nén siêu ngắn (< 70 tokens) và JSON Mode.
    Tổng token cho 1 lần gọi chỉ khoảng 80-100 tokens.
    """
    if not GEMINI_API_KEY or not GEMINI_API_KEY.strip():
        return None

    # Rút gọn nội dung bài viết tối đa 260 ký tự (loại bỏ địa chỉ/chính sách dài dòng)
    compact_text = post_text.strip().replace("\n", " ")[:260]

    # Danh sách model theo thứ tự ưu tiên (Tự động chuyển đổi nếu gặp 429 Quota Exceeded)
    CANDIDATE_MODELS = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]

    payload = {
        "contents": [
            {
                "parts": [{"text": system_instruction}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json"
        }
    }

    _LAST_ALERT_TIME = getattr(call_gemini_flash, "_last_alert_time", 0)
    import time

    for model_name in CANDIDATE_MODELS:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY.strip()}"
        try:
            resp = requests.post(endpoint, json=payload, timeout=12)
            if resp.status_code == 200:
                result_json = resp.json()
                raw_content = result_json["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(raw_content)
                return data
            elif resp.status_code in (429, 503):
                # Quota hoặc Server bận -> Bắn cảnh báo về Discord Log (tối đa 1 lần mỗi 5 phút)
                now = time.time()
                if now - _LAST_ALERT_TIME > 300:
                    setattr(call_gemini_flash, "_last_alert_time", now)
                    try:
                        from discord_notifier import send_quota_alert_to_discord
                        send_quota_alert_to_discord(model_name, resp.status_code, resp.text[:200])
                    except Exception:
                        pass
                # Thử sang model tiếp theo trong danh sách
                continue
            else:
                console.print(f"[dim red]! Gemini ({model_name}) status {resp.status_code}: {resp.text[:120]}[/dim red]")
        except Exception as e:
            continue

    return None

BUY_PATTERNS = [
    r'\b(?:cần|tìm|hỏi)\s+(?:mua|tìm|kiếm)\b',
    r'\b(?:tìm|cần)\s+(?:màn|case|vga|card|pc|bộ|con|e)\b',
    r'\b(?:ai\s+có|bác\s+nào\s+có|ai\s+bán|ai\s+pass)\b',
    r'\btài\s+chính\b',
    r'\bthu\s+mua\b',
    r'\bxin\s+tư\s+vấn\b',
    r'\bở\s+đâu\s+bán\b',
    r'\bngân\s+sách\b'
]

def detect_post_type(content: str) -> str:
    """Phân loại bài viết: 'BUY' (Tìm mua) hoặc 'SELL' (Đăng bán)."""
    if not content:
        return "SELL"
    c_lower = content.lower()
    for pat in BUY_PATTERNS:
        if re.search(pat, c_lower):
            return "BUY"
    return "SELL"

def analyze_and_appraise_deal(post: dict, min_discount_pct: float = MIN_DISCOUNT_PERCENT) -> Optional[dict]:
    """
    Bộ điều phối thẩm định giá:
    1. Phân loại bài bán (SELL) vs bài tìm mua (BUY)
    2. Nếu có GEMINI_API_KEY -> Dùng Gemini Flash siêu tiết kiệm token
    3. Nếu không có hoặc lỗi -> Fallback về bảng tĩnh regex
    4. Tự động lưu mọi kết quả định giá vào Database để tích lũy dữ liệu cho Hệ thống 2
    """
    content = post.get("content", "")
    post_id = post.get("post_id", "")

    # Phân loại bài viết
    post_type = detect_post_type(content)
    post["post_type"] = post_type

    # Nếu là bài TÌM MUA -> Bỏ qua không thẩm định giá bán
    if post_type == "BUY":
        return None

    # Bước 1: Lọc nhanh bằng code
    if not is_worth_appraising(content):
        return None

    deal_result = None

    # Bước 2: Thử thẩm định bằng Gemini Flash
    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        ai_data = appraise_with_gemini(content)
        if ai_data and ai_data.get("is_sell") and ai_data.get("price", 0) > 0:
            deal_price = ai_data.get("price", 0)
            market_price = ai_data.get("market_price", 0)
            model_name = ai_data.get("model", "Màn hình PC")

            dealer_buy_price = ai_data.get("dealer_buy_price", 0)
            profit = ai_data.get("profit", max(0, market_price - deal_price))

            # Tính discount %
            discount_pct = 0.0
            if market_price > deal_price > 0:
                discount_pct = round(((market_price - deal_price) / market_price) * 100, 1)

            # Đạt tiêu chuẩn kèo khi AI đánh giá có lãi hoặc giá bán <= giá thợ thu
            is_deal = ai_data.get("is_deal", False) or (dealer_buy_price > 0 and deal_price <= dealer_buy_price) or (discount_pct >= MIN_DISCOUNT_PERCENT)
            is_dealer = check_is_dealer(post, ai_data)

            # Lưu vào Database phục vụ tích lũy dữ liệu cho Hệ thống 2
            database.update_deal_info(post_id, {
                "model": model_name,
                "deal_price": deal_price,
                "market_price": market_price,
                "discount_pct": discount_pct,
                "is_deal": is_deal
            })

            if is_deal:
                deal_result = {
                    "post_id": post_id,
                    "product_name": model_name,
                    "market_price": market_price,
                    "dealer_buy_price": dealer_buy_price,
                    "deal_price": deal_price,
                    "discount_pct": discount_pct,
                    "profit": profit,
                    "is_dealer": is_dealer,
                    "save_amount": max(0, market_price - deal_price),
                    "author_name": post.get("author_name", ""),
                    "group_name": post.get("group_name", ""),
                    "post_url": post.get("post_url", ""),
                    "created_time": post.get("created_time", ""),
                    "content": content,
                    "media_urls": post.get("media_urls", [])
                }
            return deal_result

    # Bước 3: Dự phòng (Fallback) sang regex bảng tĩnh nếu chưa cấu hình key
    regex_res = fallback_regex_deal(post, min_discount_pct=MIN_DISCOUNT_PERCENT)
    if regex_res:
        regex_res["is_dealer"] = check_is_dealer(post, None)
        database.update_deal_info(post_id, {
            "model": regex_res.get("product_name", ""),
            "deal_price": regex_res.get("deal_price", 0),
            "market_price": regex_res.get("market_price", 0),
            "discount_pct": regex_res.get("discount_pct", 0.0),
            "is_deal": 1
        })
    return regex_res

if __name__ == "__main__":
    console.print("[cyan]Kiểm tra bộ lọc trước (0-token filter):[/cyan]")
    test_samples = [
        "Cần mua màn hình 24 inch ai có bán em",
        "Pass nhanh em Dell U2422H fullbox bh 2025 giá 2tr7 gdtt HN",
        "Hỏi các bác màn này bị sọc sửa hết bao nhiêu",
        "Thanh lý màn Xiaomi 27 inch 165hz 2k giá 2tr4"
    ]
    for s in test_samples:
        worth = is_worth_appraising(s)
        console.print(f" - [italic]'{s[:45]}...'[/italic] -> {'[green]GỬI AI[/green]' if worth else '[yellow]BỎ QUA (0 TOKEN)[/yellow]'}")
