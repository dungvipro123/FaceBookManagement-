import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import re
import json
import os
from typing import Optional, Tuple, Dict, Any

MARKET_PRICE_FILE = os.path.join(os.path.dirname(__file__), "market_prices.json")

def load_market_prices() -> Dict[str, Any]:
    """Tải bảng giá tham chiếu màn hình."""
    if os.path.exists(MARKET_PRICE_FILE):
        try:
            with open(MARKET_PRICE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception:
            pass
    return {}

def extract_prices_from_text(text: str) -> list[int]:
    """
    Trích xuất tất cả các mức giá tiềm năng (VND) từ nội dung bài viết.
    Hỗ trợ các định dạng: '2tr7', '2tr700k', '4500k', '2.5 củ', '3m2', '3.500.000đ'...
    """
    if not text:
        return []

    prices = []
    clean_text = text.lower()

    # 1. Định dạng: 2tr7, 2tr700, 2tr700k, 2.7tr, 2,7tr, 3tr, 2 củ 7, 2.5 củ, 3 củ
    # Regex bắt: (số nguyên) + (tr|triệu|củ|m) + (số lẻ tùy chọn)
    pattern_tr = r'(?:giá|pass|bán|chỉ)?\s*(\d+)(?:[.,](\d+))?\s*(?:tr|triệu|củ|m)(?:\s*(\d{1,3})(?:k|lít)?)?'
    for match in re.finditer(pattern_tr, clean_text):
        main_num = int(match.group(1))
        decimal_part = match.group(2)
        tail_num = match.group(3)

        if main_num > 50:  # Không phải số triệu hợp lệ cho màn hình PC
            continue

        price = main_num * 1_000_000
        if decimal_part:
            # ví dụ: 2.7tr -> decimal_part = '7' -> 700,000
            dec_val = float("0." + decimal_part)
            price = int((main_num + dec_val) * 1_000_000)
        elif tail_num:
            # ví dụ: 2tr7 -> tail_num = 7 -> 2.700.000; 2tr700 -> tail_num = 700 -> 2.700.000
            tail_int = int(tail_num)
            if tail_int < 10:
                price += tail_int * 100_000
            elif tail_int < 100:
                price += tail_int * 10_000
            else:
                price += tail_int * 1_000

        if 500_000 <= price <= 40_000_000:
            prices.append(price)

    # 2. Định dạng theo 'k': 4500k, 2400k, 1850k, 900k (loại trừ các thông số hz như 144hz, 165hz, 4k, 2k)
    pattern_k = r'(?<!\d)(?<![a-z])([1-9]\d{2,4})\s*(?:k|lít|nghìn)\b'
    for match in re.finditer(pattern_k, clean_text):
        val = int(match.group(1))
        # Bỏ qua nếu là số 4k hoặc 2k độ phân giải màn hình
        if val in [2, 4] and clean_text[match.start():match.end()].strip().lower() in ['2k', '4k']:
            continue
        price = val * 1_000
        # Bỏ qua nếu trùng các từ khóa độ phân giải như '2k', '4k'
        if 500_000 <= price <= 40_000_000 and price not in prices:
            prices.append(price)

    # 3. Định dạng đầy đủ có dấu chấm: 2.500.000 hoặc 3,200,000
    pattern_full = r'(?<!\d)([1-3]?\d)[.,](\d{3})[.,](\d{3})(?:\s*đ|\s*vnd)?\b'
    for match in re.finditer(pattern_full, clean_text):
        p_str = f"{match.group(1)}{match.group(2)}{match.group(3)}"
        price = int(p_str)
        if 500_000 <= price <= 40_000_000 and price not in prices:
            prices.append(price)

    return prices

def match_monitor_model(text: str, market_data: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Tìm kiếm xem bài viết có đề cập đến model màn hình nào trong danh sách theo dõi hay không.
    """
    if not text:
        return None

    clean_text = text.upper()

    # Sắp xếp các model dài trước để tránh khớp nhầm model con
    sorted_models = sorted(market_data.keys(), key=lambda x: len(x), reverse=True)

    for model_key in sorted_models:
        # Regex tìm chính xác mã model (ví dụ tìm U2422H không khớp bừa bãi)
        pattern = r'\b' + re.escape(model_key.upper()) + r'\b'
        if re.search(pattern, clean_text):
            return model_key, market_data[model_key]

    return None

def analyze_post_deal(post: dict, min_discount_pct: float = 15.0) -> Optional[dict]:
    """
    Phân tích bài viết:
    - Nhận diện model màn hình
    - Trích xuất giá rao bán
    - So sánh với giá thị trường
    - Nếu rẻ hơn >= min_discount_pct (%) -> Trả về thông tin Deal
    """
    content = post.get("content", "")
    if not content:
        return None

    market_data = load_market_prices()
    matched = match_monitor_model(content, market_data)

    if not matched:
        return None

    model_key, model_info = matched
    market_price = model_info.get("market_price", 0)

    extracted_prices = extract_prices_from_text(content)
    if not extracted_prices:
        return None

    # Lấy mức giá thấp nhất hoặc hợp lý nhất tìm được trong bài
    deal_price = min(extracted_prices)

    # Tính tỷ lệ giảm giá so với giá thị trường
    discount_pct = ((market_price - deal_price) / market_price) * 100.0

    if discount_pct >= min_discount_pct:
        return {
            "post_id": post.get("post_id"),
            "model_key": model_key,
            "product_name": model_info.get("name", model_key),
            "brand": model_info.get("brand", ""),
            "market_price": market_price,
            "deal_price": deal_price,
            "discount_pct": round(discount_pct, 1),
            "save_amount": market_price - deal_price,
            "author_name": post.get("author_name", ""),
            "group_name": post.get("group_name", ""),
            "post_url": post.get("post_url", ""),
            "created_time": post.get("created_time", ""),
            "content": content,
            "media_urls": post.get("media_urls", [])
        }

    return None

if __name__ == "__main__":
    # Test một số mẫu câu thực tế
    sample_texts = [
        "Pass nhanh em Dell U2422H fullbox bh 2025 giá 2tr7 gdtt HN",
        "Thanh lý gấp LG 27GP850 đẹp keng giá 4500k",
        "Bán màn hình AOC 24G2 giá 1.600.000đ tại Cầu Giấy",
        "Cần mua màn hình 24 inch ai có không"
    ]

    for t in sample_texts:
        print(f"\n[Test] Văn bản: {t}")
        res = analyze_post_deal({"content": t, "post_url": "https://facebook.com", "author_name": "Nguyen Van A"})
        if res:
            print(f"🔥 PHÁT HIỆN KÈO THƠM: {res['product_name']} | Giá bán: {res['deal_price']:,}đ (Thị trường: {res['market_price']:,}đ, Rẻ hơn {res['discount_pct']}%)")
        else:
            print("Không phát hiện kèo hoặc không khớp model/giá.")
