import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import re
import os
import json
import time
import random
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from playwright.sync_api import sync_playwright, Page, BrowserContext
from rich.console import Console

from config import (
    MAX_POSTS_PER_GROUP,
    MAX_SCROLLS_PER_GROUP,
    HEADLESS,
    SCROLL_DELAY_MIN,
    SCROLL_DELAY_MAX,
    GROUP_DELAY_MIN,
    GROUP_DELAY_MAX,
    COOKIES_FILE,
    PROXY_SERVER,
    MIN_DISCOUNT_PERCENT,
    DISCORD_WEBHOOK_URL,
)
import database
from ai_appraiser import analyze_and_appraise_deal as analyze_post_deal, detect_post_type
from discord_notifier import send_deal_to_discord, send_log_to_discord, send_buy_lead_to_discord

console = Console()

def format_chronological_url(group_url: str) -> str:
    """
    Chuẩn hoá URL nhóm với query `sorting_setting=CHRONOLOGICAL` để đảm bảo bài viết mới nhất luôn lên đầu.
    """
    clean_url = group_url.strip().rstrip("/")
    parsed = urlparse(clean_url)
    query_params = parse_qs(parsed.query)
    query_params["sorting_setting"] = ["CHRONOLOGICAL"]
    new_query = urlencode(query_params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def dismiss_fb_popups(page: Page):
    """
    Đóng các popup phiền toái của Facebook (như popup Đăng nhập, Xem thêm, Cookies banner).
    """
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    close_selectors = [
        'div[aria-label="Đóng"][role="button"]',
        'div[aria-label="Close"][role="button"]',
        'div[aria-label="Đóng"]',
        'div[aria-label="Close"]',
        'div[role="dialog"] div[aria-label="Đóng"]',
        'div[role="dialog"] div[aria-label="Close"]',
        'div[role="dialog"] svg',
    ]

    for sel in close_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=800)
                break
        except Exception:
            pass

def expand_see_more(page: Page):
    """
    Tự động bấm nút 'Xem thêm' / 'See more' để hiển thị toàn bộ nội dung bài viết bị cắt ngắn.
    """
    try:
        see_more_buttons = page.locator('div[role="button"]:has-text("Xem thêm"), span:has-text("Xem thêm"), div[role="button"]:has-text("See more"), span:has-text("See more")')
        count = see_more_buttons.count()
        for i in range(min(count, 5)):
            try:
                btn = see_more_buttons.nth(i)
                if btn.is_visible():
                    btn.click(timeout=500)
            except Exception:
                continue
    except Exception:
        pass

def extract_posts_from_page(page: Page, group_info: dict) -> list:
    """
    Trích xuất danh sách các bài viết đang hiển thị trên DOM bằng JavaScript evaluation.
    """
    js_code = """
    () => {
        const posts = [];
        // Tìm tất cả các thẻ có role="article" hoặc các khối bài viết
        const articles = document.querySelectorAll('div[role="article"], div[role="feed"] > div');
        
        articles.forEach(art => {
            // 1. Tìm link bài viết (permalink / posts)
            let postLinkEl = art.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="multi_permalinks="]');
            if (!postLinkEl) return;
            
            const rawHref = postLinkEl.getAttribute('href') || '';
            let fullPostUrl = rawHref;
            if (rawHref.startsWith('/')) {
                fullPostUrl = 'https://www.facebook.com' + rawHref;
            }
            
            // Xóa các tracking param rườm rà (?__cft__...)
            let cleanPostUrl = fullPostUrl.split('?')[0];
            if (rawHref.includes('multi_permalinks=')) {
                const matchM = rawHref.match(/multi_permalinks=(\\d+)/);
                if (matchM) {
                    cleanPostUrl = 'https://www.facebook.com/groups/posts/' + matchM[1];
                }
            }

            // 2. Trích xuất Post ID
            let postId = '';
            const m1 = cleanPostUrl.match(/posts\\/(\\d+)/);
            const m2 = rawHref.match(/permalink\\/(\\d+)/);
            const m3 = rawHref.match(/multi_permalinks=(\\d+)/);
            const m4 = rawHref.match(/story_fbid=(\\d+)/);
            
            if (m1) postId = m1[1];
            else if (m2) postId = m2[1];
            else if (m3) postId = m3[1];
            else if (m4) postId = m4[1];
            
            if (!postId) return;

            // 3. Tìm tác giả (Author)
            let authorName = '';
            let authorUrl = '';

            // Kiểm tra xem bài có phải là "Người tham gia ẩn danh" thật hay không
            const headerEl = art.querySelector('h2, h3, h4, [role="heading"]');
            const headerText = headerEl ? headerEl.innerText.trim() : '';
            if (headerText.includes('Người tham gia ẩn danh') || headerText.includes('Thành viên ẩn danh') || headerText.includes('Anonymous participant')) {
                authorName = 'Thành viên ẩn danh';
                authorUrl = '';
            } else {
                // Ưu tiên 1: Tìm link trỏ tới profile người dùng (/user/ hoặc profile.php)
                const userLink = art.querySelector('h2 a[href*="/user/"], h3 a[href*="/user/"], h4 a[href*="/user/"], a[href*="/user/"], a[href*="profile.php"]');
                if (userLink && userLink.innerText.trim().length > 1) {
                    authorName = userLink.innerText.trim();
                    const rawH = userLink.getAttribute('href') || '';
                    authorUrl = rawH.startsWith('/') ? 'https://www.facebook.com' + rawH.split('?')[0] : rawH.split('?')[0];
                }

                // Ưu tiên 2: Duyệt các thẻ a trong header (bỏ qua link bài viết và link thuần của nhóm)
                if (!authorName && headerEl) {
                    const links = headerEl.querySelectorAll('a');
                    for (let l of links) {
                        const href = l.getAttribute('href') || '';
                        const txt = l.innerText.trim();
                        const isPostLink = href.includes('/posts/') || href.includes('/permalink/') || href.includes('multi_permalinks=');
                        const isPureGroup = (href.match(/\\/groups\\/[^\\/]+\\/?$/) && !href.includes('/user/'));
                        if (txt && !isPostLink && !isPureGroup && txt !== 'Facebook' && txt.length > 1) {
                            authorName = txt;
                            authorUrl = href.startsWith('/') ? 'https://www.facebook.com' + href.split('?')[0] : href.split('?')[0];
                            break;
                        }
                    }
                    if (!authorName && headerText) {
                        authorName = headerText.split('\\n')[0].trim();
                    }
                }

                // Ưu tiên 3: Tìm link ứng viên khác trong article
                if (!authorName) {
                    const candidateLinks = art.querySelectorAll('strong a, a[role="link"]');
                    for (let l of candidateLinks) {
                        const href = l.getAttribute('href') || '';
                        const txt = l.innerText.trim();
                        const isPostLink = href.includes('/posts/') || href.includes('/permalink/');
                        if (txt && !isPostLink && !href.includes('#') && txt !== 'Facebook' && txt.length > 1) {
                            authorName = txt;
                            authorUrl = href.startsWith('/') ? 'https://www.facebook.com' + href.split('?')[0] : href.split('?')[0];
                            break;
                        }
                    }
                }
            }

            if (!authorName || authorName.length < 2) {
                authorName = 'Ẩn danh / Không rõ';
            }

            // 4. Thời gian đăng bài (Created Time)
            let createdTime = postLinkEl.innerText.trim() || postLinkEl.getAttribute('aria-label') || '';
            // Thỉnh thoảng text timestamp nằm trong thẻ con
            if (!createdTime && postLinkEl.parentElement) {
                createdTime = postLinkEl.parentElement.innerText.trim();
            }

            // 5. Nội dung bài viết (Content)
            // Tìm tất cả các container text có dir="auto"
            let content = '';
            const messageContainers = art.querySelectorAll('div[dir="auto"]');
            const contentParts = [];
            messageContainers.forEach(div => {
                const txt = div.innerText.trim();
                // Loại trừ các chữ ngắn như tên tác giả, nút hành động, reaction
                if (txt && txt !== authorName && txt !== createdTime && txt !== 'Thích' && txt !== 'Bình luận' && txt !== 'Chia sẻ') {
                    // Tránh lặp lại cha - con
                    let isParentOrChild = false;
                    for (let existing of contentParts) {
                        if (existing.includes(txt) || txt.includes(existing)) {
                            isParentOrChild = true;
                            if (txt.length > existing.length) {
                                contentParts[contentParts.indexOf(existing)] = txt;
                            }
                            break;
                        }
                    }
                    if (!isParentOrChild && txt.length > 5) {
                        contentParts.push(txt);
                    }
                }
            });
            content = contentParts.join('\\n').trim();

            // 6. Hình ảnh đính kèm (Media URLs)
            const mediaUrls = [];
            const imgEls = art.querySelectorAll('img');
            imgEls.forEach(img => {
                const src = img.getAttribute('src') || '';
                const width = img.naturalWidth || img.width || 0;
                // Lọc bỏ avatar nhỏ và emoji icon
                if (src.includes('fbcdn.net') && !src.includes('/static.xx/') && width > 120) {
                    if (!mediaUrls.includes(src)) {
                        mediaUrls.push(src);
                    }
                }
            });

            posts.push({
                post_id: postId,
                author_name: authorName,
                author_url: authorUrl,
                post_url: cleanPostUrl,
                created_time: createdTime,
                content: content,
                media_urls: mediaUrls
            });
        });

        return posts;
    }
    """
    raw_posts = page.evaluate(js_code)
    cleaned_posts = []
    seen_ids = set()

    clean_group_base = group_info.get("url", "").split("?")[0].rstrip("/")
    for p in raw_posts:
        pid = p.get("post_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            p["group_name"] = group_info.get("name", "")
            p["group_url"] = group_info.get("url", "")
            # Luôn đảm bảo 100% link là đường dẫn trực tiếp mở đúng bài viết
            p["post_url"] = f"{clean_group_base}/posts/{pid}/"
            cleaned_posts.append(p)

    return cleaned_posts

def scrape_group(page: Page, group_info: dict) -> dict:
    """
    Cào các bài viết mới nhất từ 1 nhóm Facebook với logic Incremental Scraping:
    - Khi gặp bài viết đã có trong Database -> Dừng cuộn ngay lập tức.
    """
    group_name = group_info.get("name", "Unknown")
    raw_url = group_info.get("url", "")
    chrono_url = format_chronological_url(raw_url)

    console.print(f"\n[bold cyan]>> Đang truy cập nhóm:[/bold cyan] [yellow]{group_name}[/yellow]")
    console.print(f"   URL chế độ bài mới nhất: [dim]{chrono_url}[/dim]")

    try:
        page.goto(chrono_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        console.print(f"[red]X Không thể tải trang nhóm: {e}[/red]")
        return {"group": group_name, "new_posts": 0, "status": "failed"}

    # Chờ 3-5 giây để Facebook load nội dung và popup
    time.sleep(3.5)
    dismiss_fb_popups(page)

    new_posts_saved = 0
    hit_existing_post = False
    scroll_count = 0

    while scroll_count < MAX_SCROLLS_PER_GROUP:
        dismiss_fb_popups(page)
        expand_see_more(page)

        # Trích xuất các bài viết hiện diện
        extracted_posts = extract_posts_from_page(page, group_info)

        for post in extracted_posts:
            pid = post.get("post_id")
            
            # KIỂM TRA ĐIỀU KIỆN DỪNG: Đã từng cào bài này trước đó
            if database.is_post_exists(pid):
                console.print(f"   [yellow]ℹ Gặp bài viết cũ (ID: {pid}) đã được lưu trước đó. Dừng cuộn nhóm này![/yellow]")
                hit_existing_post = True
                break

            # Lưu bài viết mới vào SQLite
            saved = database.save_post(post)
            if saved:
                new_posts_saved += 1
                short_content = (post.get('content', '').replace('\n', ' ')[:60] + '...') if post.get('content') else '(Không có nội dung chữ)'
                console.print(f"   [green]+ Đã lưu bài mới:[/green] [white]{post.get('author_name', '')}[/white] | [dim]{short_content}[/dim] (ID: {pid})")

                # 1. Gửi mọi bài mới cào được vào KÊNH LOG Discord
                try:
                    send_log_to_discord(post)
                except Exception:
                    pass

                # 2. Phân loại bài viết: TÌM MUA vs ĐĂNG BÁN
                post_type = detect_post_type(post.get("content", ""))
                post["post_type"] = post_type

                if post_type == "BUY":
                    # Bắn ngay vào KÊNH KHÁCH TÌM MUA để thợ/shop vào chào hàng
                    try:
                        send_buy_lead_to_discord(post)
                    except Exception as e:
                        console.print(f"   [dim red]! Lỗi gửi Kênh Tìm Mua: {e}[/dim red]")
                else:
                    # 3. Thẩm định giá bài ĐĂNG BÁN: Nếu là KÈO HỜI THỢ NHẬP CÓ LÃI -> Bắn vào KÊNH KÈO NGON 1 hoặc 2
                    try:
                        deal_info = analyze_post_deal(post, min_discount_pct=MIN_DISCOUNT_PERCENT)
                        if deal_info:
                            console.print(f"   [bold red]🔥 PHÁT HIỆN KÈO THƠM:[/bold red] [bold yellow]{deal_info['product_name']}[/bold yellow] - Giá: [bold cyan]{deal_info['deal_price']:,.0f}đ[/bold cyan] (Rẻ hơn {deal_info['discount_pct']}%)")
                            send_deal_to_discord(deal_info)
                    except Exception as e:
                        console.print(f"   [dim red]! Lỗi kiểm tra kèo giá: {e}[/dim red]")

            # Đạt giới hạn bài viết tối đa mỗi lần cào
            if new_posts_saved >= MAX_POSTS_PER_GROUP:
                console.print(f"   [green]✓ Đã đạt giới hạn {MAX_POSTS_PER_GROUP} bài mới cho nhóm này.[/green]")
                hit_existing_post = True
                break

        if hit_existing_post:
            break

        # Cuộn trang xuống để load thêm bài tiếp theo
        scroll_count += 1
        console.print(f"   [dim]Cuộn trang lần {scroll_count}/{MAX_SCROLLS_PER_GROUP}...[/dim]")
        page.mouse.wheel(0, random.randint(900, 1400))
        time.sleep(random.uniform(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))

    console.print(f"[bold green]>> Hoàn thành nhóm {group_name}:[/bold green] Thêm mới [bold]{new_posts_saved}[/bold] bài viết.")
    return {"group": group_name, "new_posts": new_posts_saved, "status": "success"}

def run_scraper(groups: list = None) -> dict:
    """
    Khởi chạy Playwright và duyệt qua toàn bộ danh sách các nhóm.
    Nếu groups là None, tự động lấy danh sách các nhóm đang BẬT từ database.
    """
    database.init_db()
    if groups is None:
        groups = database.get_active_groups()
        if not groups:
            from config import TARGET_GROUPS
            groups = TARGET_GROUPS

    console.print(f"[bold blue]═══════════════════════════════════════════════════════════════[/bold blue]")
    console.print(f"[bold blue]   BẮT ĐẦU CÀO BÀI VIẾT MỚI NHẤT TRÊN {len(groups)} NHÓM FACEBOOK   [/bold blue]")
    console.print(f"[bold blue]═══════════════════════════════════════════════════════════════[/bold blue]")

    with sync_playwright() as p:
        # Cấu hình browser chống bị nhận diện bot
        launch_kwargs = {
            "headless": HEADLESS,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-notifications",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized"
            ]
        }

        # Nếu có cấu hình Proxy trong config.py
        if PROXY_SERVER and PROXY_SERVER.strip():
            launch_kwargs["proxy"] = {"server": PROXY_SERVER.strip()}
            console.print(f"[green]✓ Đang sử dụng Proxy:[/green] [cyan]{PROXY_SERVER.strip()}[/cyan]")

        browser = p.chromium.launch(**launch_kwargs)

        context_kwargs = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh"
        }

        context = browser.new_context(**context_kwargs)

        # Nạp Cookie nếu có file cookies.json
        if os.path.exists(COOKIES_FILE):
            try:
                with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    context.add_cookies(cookies)
                console.print(f"[green]✓ Đã nạp cookie thành công từ {COOKIES_FILE}[/green]")
            except Exception as e:
                console.print(f"[yellow]! Không thể nạp cookie ({e}), tiếp tục với chế độ Guest.[/yellow]")
        else:
            console.print(f"[dim]ℹ Không tìm thấy {COOKIES_FILE}. Đang chạy ở chế độ Khách (Guest Mode).[/dim]")

        page = context.new_page()

        results = []
        for i, grp in enumerate(groups):
            res = scrape_group(page, grp)
            results.append(res)
            # Cập nhật thời gian vừa quét xong vào database
            try:
                database.update_group_last_scraped(grp.get("url", ""))
            except Exception:
                pass

            # Nghỉ ngẫu nhiên giữa các nhóm (trừ nhóm cuối cùng)
            if i < len(groups) - 1:
                delay = random.uniform(GROUP_DELAY_MIN, GROUP_DELAY_MAX)
                console.print(f"[dim]Nghỉ {delay:.1f}s trước khi chuyển sang nhóm tiếp theo...[/dim]")
                time.sleep(delay)

        browser.close()

    total_new = sum(r.get("new_posts", 0) for r in results)
    total_in_db = database.get_total_posts_count()

    console.print(f"\n[bold green]════════════════ TỔNG KẾT LƯỢT CHẠY ════════════════[/bold green]")
    for r in results:
        console.print(f" - {r['group']}: [bold]{r['new_posts']}[/bold] bài mới")
    console.print(f"Tổng số bài mới thêm đợt này: [bold cyan]{total_new}[/bold cyan]")
    console.print(f"Tổng số bài hiện có trong Database: [bold cyan]{total_in_db}[/bold cyan]")
    console.print(f"[bold green]════════════════════════════════════════════════════[/bold green]\n")

    return {
        "new_posts": total_new,
        "total_in_db": total_in_db,
        "results": results
    }

