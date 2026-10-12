import os
import re
import json
import time
import requests
from typing import Optional, Dict, Any, List
from app.db import get_connection
from app.config import get_setting
from app.state import state_manager
from app.scraper.price_parser import analyze_post_deal as fallback_regex_deal

SKIP_BUY_KEYWORDS = [
    "cần mua", "tìm mua", "ai có", "mua màn", "hỏi", "xin tư vấn",
    "mua case", "tìm case", "mua vga", "thu mua"
]

DEALER_NAME_KEYWORDS = [
    "pc", "máy tính", "computer", "store", "shop", "linh kiện",
    "máy in", "net", "gaming", "laptop", "thanh lý", "thu mua",
    "rẻ bền", "phụ kiện"
]

DEALER_CONTENT_KEYWORDS = [
    "dọn kho", "xả kho", "ôm lô", "sẵn sl", "sẵn vài chục",
    "bảo hành cửa hàng", "bh 1 tháng", "bh 3 tháng", "bh 6 tháng",
    "1 đổi 1", "nhận build pc", "thu cũ đổi mới", "đồng kiểm",
    "ship cod toàn quốc", "sẵn sll", "giá thợ", "giá sỉ", "lô màn"
]

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

BATCH_SYSTEM_PROMPT = """Bạn là chuyên gia định giá màn hình máy tính cũ tại VN.
Phân tích danh sách các bài đăng sau (gồm id và text) và trả về JSON Array:
[
  {
    "id": "post_id",
    "is_sell": true,
    "is_dealer": false,
    "model": "Dell U2422H",
    "price": 2700000,
    "market_price": 3600000,
    "dealer_buy_price": 3000000,
    "profit": 900000,
    "is_deal": true
  }
]
Nếu bài viết không phải bán màn hình hoặc không có giá: {"id": "post_id", "is_sell": false}."""

def detect_post_type(content: str) -> str:
    """Classifies post as 'BUY' or 'SELL'."""
    if not content:
        return "SELL"
    c_lower = content.lower()
    for pat in BUY_PATTERNS:
        if re.search(pat, c_lower):
            return "BUY"
    return "SELL"

def check_is_dealer(post: dict, ai_data: Optional[dict] = None) -> bool:
    author_name = (post.get("author_name") or "").lower()
    content = (post.get("content") or "").lower()

    # 1. Past post count check from DB
    try:
        conn = get_connection()
        count_row = conn.execute("SELECT COUNT(*) FROM posts WHERE author_name = ?", (post.get("author_name", ""),)).fetchone()
        if count_row and count_row[0] >= 3:
            return True
    except Exception:
        pass

    # 2. Author name contains shop/store keywords
    clean_name = author_name.replace(" ", "")
    for kw in DEALER_NAME_KEYWORDS:
        clean_kw = kw.replace(" ", "")
        if kw in author_name or clean_kw in clean_name:
            return True

    # 3. Post content contains bulk/wholesale keywords
    for kw in DEALER_CONTENT_KEYWORDS:
        if kw in content:
            return True

    # 4. AI judgment
    if ai_data and ai_data.get("is_dealer"):
        return True

    return False

def is_worth_appraising(text: str) -> bool:
    if not text or len(text.strip()) < 10:
        return False
    clean_text = text.lower()
    for kw in SKIP_BUY_KEYWORDS:
        if kw in clean_text:
            return False
    return bool(re.search(r'\d+\s*(?:k|lít|tr|triệu|củ|m|đ|\.000)', clean_text))

def extract_thumbnail_url(post: dict) -> str:
    media = post.get("media_urls", [])
    if isinstance(media, list) and media:
        return media[0]
    elif isinstance(media, str) and media:
        try:
            urls = json.loads(media)
            if isinstance(urls, list) and urls:
                return urls[0]
        except Exception:
            return media
    return ""

def call_gemini_batch(items: List[Dict[str, str]]) -> Optional[List[Dict[str, Any]]]:
    """
    Calls Gemini API with a BATCH of multiple posts in a single request.
    Massively saves RPD quota by a factor of 5-8x!
    """
    if not items:
        return []

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    configured_model = get_setting("gemini_model", "gemini-3.1-flash-lite")
    # Priority ordered: gemini-3.1-flash-lite (500 RPD) prioritized first!
    candidate_models = [configured_model]
    for m in ["gemini-3.1-flash-lite", "gemini-3.8-flash"]:
        if m not in candidate_models:
            candidate_models.append(m)

    payload_text = f"{BATCH_SYSTEM_PROMPT}\n\nDanh sách bài đăng cần định giá:\n{json.dumps(items, ensure_ascii=False)}"
    payload = {
        "contents": [
            {"parts": [{"text": payload_text}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json"
        }
    }

    start_time = time.time()
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json=payload, timeout=14)
            latency_ms = (time.time() - start_time) * 1000

            if resp.status_code == 200:
                state_manager.record_gemini_latency(latency_ms, "ok")
                raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict):
                    # Handle single object wrapper
                    return [parsed]
            elif resp.status_code == 429:
                state_manager.record_gemini_latency(latency_ms, "quota_exceeded")
                continue
            elif resp.status_code == 404:
                state_manager.record_gemini_latency(latency_ms, "model_not_found")
                continue
            else:
                state_manager.record_gemini_latency(latency_ms, "network_error")
        except Exception:
            latency_ms = (time.time() - start_time) * 1000
            state_manager.record_gemini_latency(latency_ms, "network_error")
            continue

    return None

def appraise_posts_batch(posts: List[dict], batch_size: int = 6) -> List[dict]:
    """
    Batched appraisal coordinator:
    1. Rapid 0-token pre-filter (classifies BUY vs SELL, skips non-price posts).
    2. Batches candidates into chunks of 6-8 posts.
    3. Sends 1 single Gemini request per batch to save RPD.
    4. Falls back to local regex appraiser if Gemini quota exceeded or offline.
    5. Updates all results into SQLite database.
    """
    if not posts:
        return []

    candidates_to_appraise = []
    enriched_map = {}

    for post in posts:
        content = post.get("content", "")
        pid = post.get("post_id", "")
        post["thumbnail_url"] = extract_thumbnail_url(post)
        post_type = detect_post_type(content)
        post["post_type"] = post_type

        if post_type == "BUY":
            post.update({
                "model": "Yêu cầu tìm mua",
                "deal_price": 0,
                "market_price": 0,
                "discount_pct": 0.0,
                "profit": 0,
                "dealer_buy_price": 0,
                "is_deal": 0,
                "is_dealer": 0
            })
            save_post_analysis(post)
            enriched_map[pid] = post
            continue

        if not is_worth_appraising(content):
            post.update({
                "model": "Không rõ",
                "deal_price": 0,
                "market_price": 0,
                "discount_pct": 0.0,
                "profit": 0,
                "dealer_buy_price": 0,
                "is_deal": 0,
                "is_dealer": 0
            })
            save_post_analysis(post)
            enriched_map[pid] = post
            continue

        # Candidate for AI valuation
        candidates_to_appraise.append(post)

    # Process candidates in batches
    for i in range(0, len(candidates_to_appraise), batch_size):
        chunk = candidates_to_appraise[i:i + batch_size]
        items_payload = [
            {"id": str(p["post_id"]), "text": p.get("content", "").replace("\n", " ")[:240]}
            for p in chunk
        ]

        # Call Gemini in batch
        ai_results = call_gemini_batch(items_payload)
        ai_by_id = {}
        if ai_results:
            for res in ai_results:
                if isinstance(res, dict) and "id" in res:
                    ai_by_id[str(res["id"])] = res

        # Process each post in the chunk
        for post in chunk:
            pid = str(post.get("post_id", ""))
            ai_data = ai_by_id.get(pid)

            if ai_data and ai_data.get("is_sell") and ai_data.get("price", 0) > 0:
                deal_price = ai_data.get("price", 0)
                market_price = ai_data.get("market_price", 0)
                model_name = ai_data.get("model", "Màn hình PC")
                dealer_buy_price = ai_data.get("dealer_buy_price", 0)
                profit = ai_data.get("profit", max(0, market_price - deal_price))

                discount_pct = 0.0
                if market_price > deal_price > 0:
                    discount_pct = round(((market_price - deal_price) / market_price) * 100, 1)

                is_deal = 1 if (ai_data.get("is_deal", False) or discount_pct >= 15.0) else 0
                is_dealer = 1 if check_is_dealer(post, ai_data) else 0

                post.update({
                    "model": model_name,
                    "deal_price": deal_price,
                    "market_price": market_price,
                    "discount_pct": discount_pct,
                    "is_deal": is_deal,
                    "is_dealer": is_dealer,
                    "dealer_buy_price": dealer_buy_price,
                    "profit": profit
                })
                save_post_analysis(post)
                enriched_map[pid] = post
            else:
                # Fallback to local regex appraiser
                regex_res = fallback_regex_deal(post, min_discount_pct=15.0)
                if regex_res:
                    is_dealer = 1 if check_is_dealer(post, None) else 0
                    post.update({
                        "model": regex_res.get("product_name", "Màn hình PC"),
                        "deal_price": regex_res.get("deal_price", 0),
                        "market_price": regex_res.get("market_price", 0),
                        "discount_pct": regex_res.get("discount_pct", 0.0),
                        "is_deal": 1,
                        "is_dealer": is_dealer,
                        "dealer_buy_price": regex_res.get("dealer_buy_price", 0),
                        "profit": regex_res.get("profit", 0)
                    })
                else:
                    post.update({
                        "model": "Không rõ",
                        "deal_price": 0,
                        "market_price": 0,
                        "discount_pct": 0.0,
                        "is_deal": 0,
                        "is_dealer": 0,
                        "dealer_buy_price": 0,
                        "profit": 0
                    })
                save_post_analysis(post)
                enriched_map[pid] = post

    return [enriched_map.get(str(p.get("post_id")), p) for p in posts]

def appraise_post(post: dict) -> dict:
    """Convenience wrapper for single post appraisal."""
    results = appraise_posts_batch([post])
    return results[0] if results else post

def save_post_analysis(post: dict) -> None:
    conn = get_connection()
    conn.execute("""
    UPDATE posts
    SET model = ?,
        deal_price = ?,
        market_price = ?,
        discount_pct = ?,
        is_deal = ?,
        post_type = ?,
        is_dealer = ?,
        dealer_buy_price = ?,
        profit = ?,
        thumbnail_url = ?
    WHERE post_id = ?
    """, (
        post.get("model", ""),
        post.get("deal_price", 0),
        post.get("market_price", 0),
        post.get("discount_pct", 0.0),
        post.get("is_deal", 0),
        post.get("post_type", "SELL"),
        post.get("is_dealer", 0),
        post.get("dealer_buy_price", 0),
        post.get("profit", 0),
        post.get("thumbnail_url", ""),
        post.get("post_id")
    ))
    conn.commit()
