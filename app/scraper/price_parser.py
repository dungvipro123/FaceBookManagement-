import re
from typing import Optional, Dict, Any, List

def extract_prices_from_text(text: str) -> List[int]:
    """
    Trích xuất các mức giá tiềm năng (VND) từ nội dung bài viết.
    Hỗ trợ: '2tr7', '2tr700k', '4500k', '2.5 củ', '3m2', '3.500.000đ'...
    """
    if not text:
        return []

    prices = []
    clean_text = text.lower()

    pattern_tr = r'(?:giá|pass|bán|chỉ)?\s*(\d+)(?:[.,](\d+))?\s*(?:tr|triệu|củ|m)(?:\s*(\d{1,3})(?:k|lít)?)?'
    for match in re.finditer(pattern_tr, clean_text):
        main_num = int(match.group(1))
        decimal_part = match.group(2)
        tail_num = match.group(3)

        if main_num > 50:
            continue

        price = main_num * 1_000_000
        if decimal_part:
            dec_val = float("0." + decimal_part)
            price = int((main_num + dec_val) * 1_000_000)
        elif tail_num:
            tail_int = int(tail_num)
            if tail_int < 10:
                price += tail_int * 100_000
            elif tail_int < 100:
                price += tail_int * 10_000
            else:
                price += tail_int * 1_000

        if 500_000 <= price <= 50_000_000:
            prices.append(price)

    pattern_k = r'(?:giá|pass|bán|chỉ)?\s*(\d{3,5})\s*(?:k|lít)\b'
    for match in re.finditer(pattern_k, clean_text):
        k_val = int(match.group(1))
        price = k_val * 1_000
        if 500_000 <= price <= 50_000_000:
            prices.append(price)

    pattern_full = r'(?:giá|pass|bán|chỉ)?\s*(\d{1,2}(?:[.,]\d{3}){2})\s*(?:vnđ|vnd|đ)?'
    for match in re.finditer(pattern_full, clean_text):
        digits_str = re.sub(r'[.,]', '', match.group(1))
        price = int(digits_str)
        if 500_000 <= price <= 50_000_000:
            prices.append(price)

    return sorted(list(set(prices)))

FALLBACK_MODELS = {
    "u2422h": {"name": "Dell UltraSharp U2422H 24\" IPS", "market_price": 3800000},
    "u2419h": {"name": "Dell UltraSharp U2419H 24\" IPS", "market_price": 2700000},
    "u2414h": {"name": "Dell UltraSharp U2414H 24\" IPS", "market_price": 1800000},
    "u2720q": {"name": "Dell UltraSharp U2720Q 27\" 4K", "market_price": 8500000},
    "p2419h": {"name": "Dell Professional P2419H 24\"", "market_price": 2000000},
    "p2422h": {"name": "Dell Professional P2422H 24\"", "market_price": 2700000},
    "24g2": {"name": "AOC 24G2 24\" IPS 144Hz", "market_price": 2200000},
    "24gn600": {"name": "LG 24GN600 24\" IPS 144Hz", "market_price": 2300000},
    "27gp850": {"name": "LG 27GP850 27\" Nano IPS 2K 165Hz", "market_price": 6200000},
    "vg249q": {"name": "ASUS TUF VG249Q 24\" IPS 144Hz", "market_price": 2200000},
    "g24f": {"name": "Gigabyte G24F 24\" IPS 165Hz", "market_price": 2200000},
}

def analyze_post_deal(post: dict, min_discount_pct: float = 15.0) -> Optional[dict]:
    content = post.get("content", "")
    if not content:
        return None

    clean_content = content.lower()
    matched_model = None
    market_price = 0

    for key, info in FALLBACK_MODELS.items():
        if key in clean_content:
            matched_model = info["name"]
            market_price = info["market_price"]
            break

    if not matched_model or market_price <= 0:
        return None

    prices = extract_prices_from_text(content)
    if not prices:
        return None

    deal_price = prices[0]
    if deal_price >= market_price:
        return None

    discount_pct = round(((market_price - deal_price) / market_price) * 100, 1)
    if discount_pct < min_discount_pct:
        return None

    return {
        "post_id": post.get("post_id"),
        "product_name": matched_model,
        "market_price": market_price,
        "deal_price": deal_price,
        "discount_pct": discount_pct,
        "dealer_buy_price": int(market_price * 0.75),
        "profit": max(0, market_price - deal_price),
        "author_name": post.get("author_name", ""),
        "group_name": post.get("group_name", ""),
        "post_url": post.get("post_url", ""),
        "created_time": post.get("created_time", ""),
        "content": content,
        "thumbnail_url": (post.get("media_urls") or [""])[0] if isinstance(post.get("media_urls"), list) else "",
        "is_dealer": 0
    }
