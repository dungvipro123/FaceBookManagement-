"""
Discord Bot Điều Khiển FB Monitor Hunter 2 Chiều (v2.0)
Hỗ trợ:
- Điều khiển từ điện thoại (Slash commands: /status, /scan, /quota, /groups, /addgroup, /toggle, /pause, /resume...)
- Thẻ Dashboard tương tác với các nút bấm trực quan
- Chạy ngầm định kỳ và quét theo yêu cầu qua Discord
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import asyncio
import os
import time
import requests
import discord
from discord.ext import commands, tasks
from rich.console import Console

import config
import database
from scraper import run_scraper

console = Console()

# Khởi tạo Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Trạng thái hệ thống trong bộ nhớ
is_scanning = False
is_paused = False
last_scan_result = {}

# ==================== VIEW TƯƠNG TÁC (BUTTONS TRÊN ĐIỆN THOẠI) ====================

class ControlDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="▶ Quét Ngay", style=discord.ButtonStyle.primary, custom_id="btn_scan_now", emoji="🚀")
    async def scan_now_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        global is_scanning
        if is_scanning:
            await interaction.response.send_message("⚠️ Hệ thống đang trong một đợt quét khác! Vui lòng chờ xong.", ephemeral=True)
            return

        await interaction.response.send_message("🚀 **Đã nhận lệnh:** Đang bắt đầu quét bài mới trên tất cả nhóm đang BẬT...", ephemeral=False)
        asyncio.create_task(execute_scan(interaction.channel))

    @discord.ui.button(label="⏸ Tạm Dừng / Tiếp Tục", style=discord.ButtonStyle.secondary, custom_id="btn_toggle_pause", emoji="⏯")
    async def toggle_pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        global is_paused
        is_paused = not is_paused
        database.set_setting("is_paused", "1" if is_paused else "0")
        state_str = "TẠM DỪNG (Sẽ không tự động quét)" if is_paused else "ĐANG HOẠT ĐỘNG (Tự động quét bình thường)"
        color = discord.Color.orange() if is_paused else discord.Color.green()
        
        embed = discord.Embed(title="⚙ Trạng Thái Hệ Thống", description=f"Hệ thống hiện tại: **{state_str}**", color=color)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="⚡ Test Quota", style=discord.ButtonStyle.success, custom_id="btn_test_quota", emoji="🔍")
    async def test_quota_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = await check_gemini_quota_embed()
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label="📊 Thống Kê", style=discord.ButtonStyle.secondary, custom_id="btn_stats", emoji="📈")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = database.get_system_stats()
        embed = discord.Embed(title="📊 Thống Kê Hoạt Động Hệ Thống", color=discord.Color.blue())
        embed.add_field(name="📦 Tổng bài đã lưu", value=f"**{stats['total_posts']}** bài", inline=True)
        embed.add_field(name="⭐ Kèo thơm tìm được", value=f"**{stats['total_deals']}** kèo", inline=True)
        embed.add_field(name="🎯 Khách tìm mua", value=f"**{stats['total_buys']}** bài", inline=True)
        embed.add_field(name="📅 Bài cào hôm nay", value=f"**{stats['today_posts']}** bài", inline=True)
        embed.add_field(name="👥 Nhóm đang theo dõi", value=f"**{stats['active_groups']}/{stats['total_groups']}** nhóm", inline=True)
        embed.add_field(name="🔄 Tiến trình quét", value="Đang chạy" if is_scanning else "Đang chờ", inline=True)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="📢 Cấu Hình Kênh", style=discord.ButtonStyle.secondary, custom_id="btn_channels", emoji="⚙")
    async def channels_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_channels_embed()
        await interaction.response.send_message(embed=embed)


# ==================== HELPER FUNCTIONS ====================

async def check_gemini_quota_embed() -> discord.Embed:
    """Kiểm tra phản hồi thực tế từ các model Gemini."""
    embed = discord.Embed(title="⚡ Kiểm Tra Hạn Mức Quota Gemini API", color=discord.Color.teal())
    models_to_test = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    
    status_lines = []
    for model in models_to_test:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={config.GEMINI_API_KEY.strip()}"
        start_t = time.time()
        try:
            # Chạy request trong threadpool để tránh chặn event loop
            resp = await asyncio.to_thread(requests.post, url, json={"contents": [{"parts": [{"text": "ping"}]}]}, timeout=8)
            duration = (time.time() - start_t) * 1000
            if resp.status_code == 200:
                status_lines.append(f"🟢 **{model}**: `200 OK` ({duration:.0f}ms) - Hoạt động hoàn hảo")
            elif resp.status_code == 429:
                status_lines.append(f"🟡 **{model}**: `429 Quota Exceeded` - Đang chạm trần RPM/RPD")
            else:
                status_lines.append(f"🔴 **{model}**: `HTTP {resp.status_code}` - {resp.text[:60]}")
        except Exception as e:
            status_lines.append(f"⚪ **{model}**: Lỗi mạng ({e})")

    embed.description = "\n".join(status_lines)
    embed.set_footer(text="Hệ thống tự động ưu tiên model 200 OK đầu tiên khi phân tích giá.")
    return embed

def build_channels_embed() -> discord.Embed:
    """Hiển thị cấu hình output chi tiết cho cả 4 kênh Discord."""
    channels = database.get_all_channel_configs()
    embed = discord.Embed(title="📢 Cấu Hình Output Từng Kênh Discord", color=discord.Color.blue())
    embed.description = "Tùy chỉnh riêng biệt việc bắn bài viết, ảnh, mention và ngưỡng giá cho từng kênh:\n"
    for c in channels:
        status_icon = "🟢 BẬT" if c.get("is_enabled", 1) == 1 else "🔴 TẮT"
        wh = c.get("webhook_url") or ""
        wh_display = f"`...{wh[-20:]}`" if len(wh) > 20 else "`Chưa cấu hình`"
        min_disc = f"{c.get('min_discount', 0)}%" if c.get("channel_key") in ("deal_1", "deal_2") else "N/A"
        mention = c.get("mention_tag") or "Không có"
        images = "Có ảnh" if c.get("show_images", 1) == 1 else "Ẩn ảnh"

        info_text = (
            f"• Trạng thái: **{status_icon}**\n"
            f"• Ngưỡng giảm giá: `{min_disc}`\n"
            f"• Tag mention: `{mention}` | Hiển thị: `{images}`\n"
            f"• Webhook: {wh_display}"
        )
        embed.add_field(name=f"[{c['channel_key']}] {c['name']}", value=info_text, inline=False)

    embed.set_footer(text="Dùng /setchannel <key> để chỉnh sửa cấu hình từng kênh từ điện thoại.")
    return embed


async def execute_scan(channel=None):
    """Thực thi quét Playwright trong luồng nền an toàn."""
    global is_scanning, last_scan_result
    if is_scanning:
        return
    is_scanning = True
    try:
        # Lấy danh sách nhóm đang kích hoạt
        active_groups = database.get_active_groups()
        if not active_groups:
            if channel:
                await channel.send("⚠️ Không có nhóm nào đang BẬT trong danh sách! Dùng `/groups` để kiểm tra.")
            return

        # Chạy scraper trên luồng riêng để không chặn bot Discord
        result = await asyncio.to_thread(run_scraper, active_groups)
        last_scan_result = result

        if channel:
            embed = discord.Embed(
                title="✅ Hoàn Tất Đợt Quét Nhóm Facebook",
                description=f"Đã duyệt qua **{len(active_groups)}** nhóm theo dõi.",
                color=discord.Color.green()
            )
            embed.add_field(name="🆕 Bài mới phát hiện", value=f"**+{result.get('new_posts', 0)}** bài", inline=True)
            embed.add_field(name="📚 Tổng bài trong DB", value=f"**{result.get('total_in_db', 0)}** bài", inline=True)
            
            detail_lines = []
            for r in result.get("results", []):
                detail_lines.append(f"• **{r.get('group')}**: {r.get('new_posts', 0)} bài mới")
            if detail_lines:
                embed.add_field(name="📋 Chi tiết từng nhóm", value="\n".join(detail_lines), inline=False)
            
            embed.set_footer(text="Các bài mới đã được gửi vào kênh Discord tương ứng.")
            await channel.send(embed=embed)

    except Exception as e:
        console.print(f"[red]X Lỗi trong quá trình quét: {e}[/red]")
        if channel:
            await channel.send(f"❌ **Lỗi khi quét:** `{e}`")
    finally:
        is_scanning = False


# ==================== TÁC VỤ ĐỊNH KỲ (BACKGROUND TASK) ====================

@tasks.loop(minutes=15)
async def automated_scraper_loop():
    """Tự động quét định kỳ mỗi 15 phút (có thể cấu hình)."""
    global is_paused, is_scanning
    if is_paused or is_scanning:
        return
    console.print("[cyan]>> [Tự Động] Bắt đầu lượt quét định kỳ...[/cyan]")
    await execute_scan()

@automated_scraper_loop.before_loop
async def before_scraper_loop():
    await bot.wait_until_ready()


# ==================== DISCORD COMMANDS (TIỆN LỢI CHO ĐIỆN THOẠI) ====================

@bot.event
async def on_ready():
    console.print(f"[bold green]✓ Discord Bot đã đăng nhập thành công với tên: {bot.user.name} ({bot.user.id})[/bold green]")
    try:
        # Đồng bộ Slash Commands với Discord
        synced = await bot.tree.sync()
        console.print(f"[bold green]✓ Đã đồng bộ {len(synced)} Slash Commands (/)[/bold green]")
    except Exception as e:
        console.print(f"[yellow]! Không thể đồng bộ Slash Commands: {e}[/yellow]")

    # Khởi chạy vòng lặp tự động nếu chưa chạy
    if not automated_scraper_loop.is_running():
        automated_scraper_loop.start()


# --- DASHBOARD CONTROL ---
@bot.command(name="dashboard")
async def cmd_dashboard(ctx):
    """Mở bảng điều khiển tương tác có nút bấm trên điện thoại."""
    embed = discord.Embed(
        title="🎮 BẢNG ĐIỀU KHIỂN FB MONITOR HUNTER",
        description="Quản trị, quét bài và theo dõi toàn bộ hệ thống trực tiếp từ điện thoại của bạn.",
        color=discord.Color.blue()
    )
    embed.add_field(name="💡 Hướng dẫn nhanh", value="Bấm các nút bên dưới hoặc gõ lệnh `!help` để xem danh sách lệnh.", inline=False)
    await ctx.send(embed=embed, view=ControlDashboardView())

@bot.tree.command(name="dashboard", description="Mở bảng điều khiển tương tác có nút bấm trên điện thoại")
async def slash_dashboard(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 BẢNG ĐIỀU KHIỂN FB MONITOR HUNTER",
        description="Quản trị, quét bài và theo dõi toàn bộ hệ thống trực tiếp từ điện thoại của bạn.",
        color=discord.Color.blue()
    )
    embed.add_field(name="💡 Hướng dẫn nhanh", value="Bấm các nút bên dưới hoặc gõ lệnh `/help` để xem chi tiết.", inline=False)
    await interaction.response.send_message(embed=embed, view=ControlDashboardView())


# --- STATUS COMMAND ---
@bot.command(name="status")
async def cmd_status(ctx):
    stats = database.get_system_stats()
    embed = discord.Embed(title="🖥️ Trạng Thái Hệ Thống", color=discord.Color.green())
    embed.add_field(name="Trạng thái", value="⏸ Tạm dừng" if is_paused else "🟢 Đang chạy", inline=True)
    embed.add_field(name="Tiến trình quét", value="Đang quét..." if is_scanning else "Rảnh", inline=True)
    embed.add_field(name="Tổng bài viết", value=f"{stats['total_posts']} bài", inline=True)
    embed.add_field(name="Kèo thơm", value=f"{stats['total_deals']} kèo", inline=True)
    embed.add_field(name="Khách tìm mua", value=f"{stats['total_buys']} bài", inline=True)
    embed.add_field(name="Nhóm đang theo dõi", value=f"{stats['active_groups']}/{stats['total_groups']} nhóm", inline=True)
    await ctx.send(embed=embed, view=ControlDashboardView())

@bot.tree.command(name="status", description="Xem trạng thái hoạt động và các thông số của hệ thống")
async def slash_status(interaction: discord.Interaction):
    stats = database.get_system_stats()
    embed = discord.Embed(title="🖥️ Trạng Thái Hệ Thống", color=discord.Color.green())
    embed.add_field(name="Trạng thái", value="⏸ Tạm dừng" if is_paused else "🟢 Đang chạy", inline=True)
    embed.add_field(name="Tiến trình quét", value="Đang quét..." if is_scanning else "Rảnh", inline=True)
    embed.add_field(name="Tổng bài viết", value=f"{stats['total_posts']} bài", inline=True)
    embed.add_field(name="Kèo thơm", value=f"{stats['total_deals']} kèo", inline=True)
    embed.add_field(name="Khách tìm mua", value=f"{stats['total_buys']} bài", inline=True)
    embed.add_field(name="Nhóm đang theo dõi", value=f"{stats['active_groups']}/{stats['total_groups']} nhóm", inline=True)
    await interaction.response.send_message(embed=embed, view=ControlDashboardView())


# --- SCAN COMMAND ---
@bot.command(name="scan")
async def cmd_scan(ctx):
    if is_scanning:
        await ctx.send("⚠️ Hệ thống đang bận quét một đợt khác! Vui lòng chờ vài phút.")
        return
    await ctx.send("🚀 **Đã nhận lệnh:** Đang bắt đầu quét bài mới...")
    asyncio.create_task(execute_scan(ctx.channel))

@bot.tree.command(name="scan", description="Ra lệnh cho bot đi cào bài viết mới ngay lập tức")
async def slash_scan(interaction: discord.Interaction):
    if is_scanning:
        await interaction.response.send_message("⚠️ Hệ thống đang bận quét một đợt khác! Vui lòng chờ vài phút.", ephemeral=True)
        return
    await interaction.response.send_message("🚀 **Đã nhận lệnh:** Đang bắt đầu quét bài mới...")
    asyncio.create_task(execute_scan(interaction.channel))


# --- QUOTA COMMAND ---
@bot.command(name="quota")
async def cmd_quota(ctx):
    embed = await check_gemini_quota_embed()
    await ctx.send(embed=embed)

@bot.tree.command(name="quota", description="Kiểm tra hạn mức và trạng thái API Gemini AI")
async def slash_quota(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await check_gemini_quota_embed()
    await interaction.followup.send(embed=embed)


# --- GROUPS COMMAND ---
@bot.command(name="groups")
async def cmd_groups(ctx):
    groups = database.get_all_monitored_groups()
    embed = discord.Embed(title="📋 Danh Sách Nhóm Đang Quản Lý", color=discord.Color.purple())
    if not groups:
        embed.description = "Chưa có nhóm nào. Dùng lệnh `!addgroup` để thêm nhóm."
    else:
        lines = []
        for g in groups:
            state_icon = "🟢 BẬT" if g["is_active"] == 1 else "🔴 TẮT"
            last_scraped = g.get("last_scraped_at") or "Chưa cào"
            lines.append(f"**#{g['id']}** | {state_icon} | **[{g['name']}]({g['url']})**\n> Lần cào gần nhất: `{last_scraped}`")
        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Dùng !toggle <id> để bật/tắt nhóm | !addgroup <tên> | <link> để thêm nhóm")
    await ctx.send(embed=embed)

@bot.tree.command(name="groups", description="Xem danh sách tất cả các nhóm Facebook đang theo dõi")
async def slash_groups(interaction: discord.Interaction):
    groups = database.get_all_monitored_groups()
    embed = discord.Embed(title="📋 Danh Sách Nhóm Đang Quản Lý", color=discord.Color.purple())
    if not groups:
        embed.description = "Chưa có nhóm nào. Dùng lệnh `/addgroup` để thêm nhóm."
    else:
        lines = []
        for g in groups:
            state_icon = "🟢 BẬT" if g["is_active"] == 1 else "🔴 TẮT"
            last_scraped = g.get("last_scraped_at") or "Chưa cào"
            lines.append(f"**#{g['id']}** | {state_icon} | **[{g['name']}]({g['url']})**\n> Lần cào gần nhất: `{last_scraped}`")
        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Dùng /toggle <id> để bật/tắt nhóm | /addgroup để thêm nhóm mới")
    await interaction.response.send_message(embed=embed)


# --- ADD GROUP COMMAND ---
@bot.command(name="addgroup")
async def cmd_addgroup(ctx, *, args: str):
    """Thêm nhóm mới: !addgroup Tên nhóm | https://facebook.com/groups/..."""
    if "|" not in args:
        await ctx.send("⚠️ Cú pháp: `!addgroup <Tên nhóm> | <URL nhóm>`\nVí dụ: `!addgroup Chợ Màn Hình | https://www.facebook.com/groups/123456`")
        return
    parts = args.split("|", 1)
    name = parts[0].strip()
    url = parts[1].strip()
    ok, msg = database.add_monitored_group(name, url)
    if ok:
        await ctx.send(f"✅ {msg}")
    else:
        await ctx.send(f"❌ {msg}")

@bot.tree.command(name="addgroup", description="Thêm một nhóm Facebook mới vào hệ thống theo dõi")
@discord.app_commands.describe(name="Tên gợi nhớ của nhóm", url="Đường link nhóm Facebook")
async def slash_addgroup(interaction: discord.Interaction, name: str, url: str):
    ok, msg = database.add_monitored_group(name, url)
    if ok:
        await interaction.response.send_message(f"✅ {msg}")
    else:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


# --- TOGGLE GROUP COMMAND ---
@bot.command(name="toggle")
async def cmd_toggle(ctx, group_id: int):
    ok, msg = database.toggle_monitored_group(group_id)
    await ctx.send(f"⚙ {msg}")

@bot.tree.command(name="toggle", description="Bật hoặc Tắt trạng thái theo dõi của một nhóm")
@discord.app_commands.describe(group_id="ID của nhóm trong danh sách /groups")
async def slash_toggle(interaction: discord.Interaction, group_id: int):
    ok, msg = database.toggle_monitored_group(group_id)
    await interaction.response.send_message(f"⚙ {msg}")


# --- DEALS COMMAND ---
@bot.command(name="deals")
async def cmd_deals(ctx, limit: int = 5):
    deals = database.get_recent_deals(limit)
    embed = discord.Embed(title=f"⭐ Top {len(deals)} Kèo Thơm Gần Nhất", color=discord.Color.gold())
    if not deals:
        embed.description = "Chưa có kèo nào trong cơ sở dữ liệu."
    else:
        for d in deals:
            embed.add_field(
                name=f"[{d.get('discount_pct', 0)}%] {d.get('model', 'Màn hình')} - {d.get('deal_price', 0):,} đ",
                value=f"• Thị trường: `{d.get('market_price', 0):,} đ`\n• Người đăng: `{d.get('author_name')}`\n• [Xem bài viết trên FB]({d.get('post_url')})",
                inline=False
            )
    await ctx.send(embed=embed)

@bot.tree.command(name="deals", description="Xem các kèo thơm mới nhất tìm thấy trong cơ sở dữ liệu")
@discord.app_commands.describe(limit="Số lượng kèo muốn xem (mặc định 5)")
async def slash_deals(interaction: discord.Interaction, limit: int = 5):
    deals = database.get_recent_deals(limit)
    embed = discord.Embed(title=f"⭐ Top {len(deals)} Kèo Thơm Gần Nhất", color=discord.Color.gold())
    if not deals:
        embed.description = "Chưa có kèo nào trong cơ sở dữ liệu."
    else:
        for d in deals:
            embed.add_field(
                name=f"[{d.get('discount_pct', 0)}%] {d.get('model', 'Màn hình')} - {d.get('deal_price', 0):,} đ",
                value=f"• Thị trường: `{d.get('market_price', 0):,} đ`\n• Người đăng: `{d.get('author_name')}`\n• [Xem bài viết trên FB]({d.get('post_url')})",
                inline=False
            )
    await interaction.response.send_message(embed=embed)


# --- CHANNELS CONFIG COMMANDS ---
@bot.command(name="channels")
async def cmd_channels(ctx):
    embed = build_channels_embed()
    await ctx.send(embed=embed)

@bot.tree.command(name="channels", description="Xem cấu hình output hiện tại của 4 kênh Discord")
async def slash_channels(interaction: discord.Interaction):
    embed = build_channels_embed()
    await interaction.response.send_message(embed=embed)

@bot.command(name="setchannel")
async def cmd_setchannel(ctx, channel_key: str, setting: str, *, value: str):
    """
    Cú pháp: !setchannel <key> <setting> <value>
    Ví dụ: 
    !setchannel deal_1 min_discount 20
    !setchannel deal_1 mention @everyone
    !setchannel log enable 0
    !setchannel buy images 1
    !setchannel deal_1 webhook https://discord.com/api/webhooks/...
    """
    key = channel_key.strip().lower()
    valid_keys = ("deal_1", "deal_2", "buy", "log")
    if key not in valid_keys:
        await ctx.send(f"⚠️ Channel key không hợp lệ! Chọn 1 trong: `{', '.join(valid_keys)}`")
        return

    s = setting.strip().lower()
    kwargs = {}
    if s in ("enable", "enabled", "status"):
        kwargs["is_enabled"] = 1 if value.strip() in ("1", "true", "on", "bat", "bật") else 0
    elif s in ("min_discount", "discount", "percent", "%"):
        try:
            kwargs["min_discount"] = float(value.strip().replace("%", ""))
        except ValueError:
            await ctx.send("⚠️ Ngưỡng giảm giá phải là số thực (ví dụ: 15 hoặc 20)!")
            return
    elif s in ("mention", "ping", "tag"):
        kwargs["mention_tag"] = value.strip() if value.strip() not in ("none", "off", "xoa", "xóa") else ""
    elif s in ("images", "image", "anh", "ảnh"):
        kwargs["show_images"] = 1 if value.strip() in ("1", "true", "on", "hien", "hiện") else 0
    elif s in ("webhook", "url"):
        kwargs["webhook_url"] = value.strip()
    else:
        await ctx.send("⚠️ Thuộc tính không hợp lệ! Có thể chỉnh: `enable`, `min_discount`, `mention`, `images`, `webhook`.")
        return

    ok, msg = database.update_channel_config(key, **kwargs)
    if ok:
        await ctx.send(f"✅ {msg}")
    else:
        await ctx.send(f"❌ {msg}")

@bot.tree.command(name="setchannel", description="Cấu hình output cho từng kênh Discord (Bật/tắt, webhook, %, mention, ảnh)")
@discord.app_commands.describe(
    channel_key="Kênh cần chỉnh: deal_1, deal_2, buy, hoặc log",
    is_enabled="Bật (1) hoặc Tắt (0) kênh này",
    min_discount="Ngưỡng giảm giá tối thiểu (%) để bắn bài vào kênh này",
    mention_tag="Tag khi có bài (ví dụ: @everyone, @here, hoặc bỏ trống)",
    show_images="Hiển thị ảnh thumbnail: 1 = Bật, 0 = Tắt",
    webhook_url="Đường link Discord Webhook mới cho kênh này"
)
@discord.app_commands.choices(channel_key=[
    discord.app_commands.Choice(name="⭐ Kèo Ngon 1 (Người Dùng Pass)", value="deal_1"),
    discord.app_commands.Choice(name="📦 Kèo Ngon 2 (Thợ / Shop Xả)", value="deal_2"),
    discord.app_commands.Choice(name="🎯 Khách Tìm Mua", value="buy"),
    discord.app_commands.Choice(name="📜 Log Toàn Bộ Bài", value="log")
])
async def slash_setchannel(
    interaction: discord.Interaction,
    channel_key: discord.app_commands.Choice[str],
    is_enabled: int = None,
    min_discount: float = None,
    mention_tag: str = None,
    show_images: int = None,
    webhook_url: str = None
):
    kwargs = {}
    if is_enabled is not None:
        kwargs["is_enabled"] = 1 if is_enabled == 1 else 0
    if min_discount is not None:
        kwargs["min_discount"] = min_discount
    if mention_tag is not None:
        kwargs["mention_tag"] = mention_tag.strip() if mention_tag.strip().lower() not in ("none", "off", "xoa") else ""
    if show_images is not None:
        kwargs["show_images"] = 1 if show_images == 1 else 0
    if webhook_url is not None:
        kwargs["webhook_url"] = webhook_url.strip()

    if not kwargs:
        await interaction.response.send_message("⚠️ Bạn chưa điền tham số nào để cập nhật!", ephemeral=True)
        return

    ok, msg = database.update_channel_config(channel_key.value, **kwargs)
    if ok:
        await interaction.response.send_message(f"✅ {msg}\n> Dùng `/channels` để xem lại toàn bộ cấu hình mới.")
    else:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)


# --- HELP COMMAND ---
def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📖 Hướng Dẫn Sử Dụng Bot Điều Khiển (FB Monitor v2.0)",
        description="Bạn có thể gõ trực tiếp **Slash Command (`/`)** hoặc **Tiền tố (`!`)** trên điện thoại / PC:\n",
        color=discord.Color.blue()
    )
    embed.add_field(name="🎮 /dashboard", value="Mở bảng điều khiển tương tác có sẵn các nút bấm (Quét, Tạm dừng, Quota...)", inline=False)
    embed.add_field(name="📢 /channels", value="Xem cấu hình output hiện tại của cả 4 kênh Discord (Trạng thái, Webhook, Ngưỡng %, Tag)", inline=False)
    embed.add_field(name="⚙ /setchannel", value="Tùy chỉnh riêng cho từng kênh (Bật/tắt, đổi Webhook, đổi Ngưỡng %, thêm Tag Mention, ẩn/hiện ảnh)", inline=False)
    embed.add_field(name="🚀 /scan", value="Ra lệnh cho bot đi cào bài viết mới nhất ngay lập tức", inline=False)
    embed.add_field(name="🖥️ /status", value="Xem trạng thái hoạt động: tiến trình quét, tổng số bài, kèo thơm...", inline=False)
    embed.add_field(name="⚡ /quota", value="Kiểm tra kết nối và độ trễ thực tế của Gemini Flash API", inline=False)
    embed.add_field(name="📋 /groups", value="Xem danh sách tất cả các nhóm Facebook đang theo dõi kèm ID và giờ cào", inline=False)
    embed.add_field(name="➕ /addgroup", value="Thêm một nhóm Facebook mới vào hệ thống theo dõi ngay từ điện thoại", inline=False)
    embed.add_field(name="🔄 /toggle <id>", value="Bật hoặc Tắt tạm thời việc theo dõi một nhóm bất kỳ", inline=False)
    embed.add_field(name="⭐ /deals", value="Xem top các kèo thơm rẻ nhất vừa tìm thấy trong cơ sở dữ liệu", inline=False)
    embed.set_footer(text="Gợi ý: Mở /dashboard để bấm nút nhanh nhất trên điện thoại!")
    return embed

@bot.command(name="help")
async def cmd_help(ctx):
    await ctx.send(embed=build_help_embed())

@bot.tree.command(name="help", description="Xem danh sách và hướng dẫn sử dụng toàn bộ các lệnh điều khiển bot")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_help_embed())



# ==================== MAIN LAUNCHER ====================

def main():
    token = config.DISCORD_BOT_TOKEN.strip()
    if not token:
        console.print("[bold red]X Chưa tìm thấy DISCORD_BOT_TOKEN trong config.py![/bold red]")
        return

    database.init_db()
    console.print(f"[bold cyan]Đang kết nối Discord Bot với token...[/bold cyan]")
    bot.run(token)

if __name__ == "__main__":
    main()
