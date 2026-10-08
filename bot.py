"""Telegram bot 主逻辑。

交互：
  /s <番号>      搜番：封面（遮罩）+ 中文简介 + 磁力 Top5
  @bot <番号>    任意聊天里内联搜索
"""
import asyncio
import html
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from functools import lru_cache

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
)

import javdb_client as jdb
from config import config
from translator import translate

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("javdb_bot")

# ---- 简单内存缓存 & 限流 ----
_cache: dict[str, tuple[float, dict]] = {}
_last_query: dict[int, float] = {}


def _cache_get(key: str):
    item = _cache.get(key)
    if item and time.time() - item[0] < config.CACHE_TTL:
        return item[1]
    _cache.pop(key, None)
    return None


def _cache_set(key: str, value: dict):
    if len(_cache) > 500:  # 防内存膨胀
        _cache.clear()
    _cache[key] = (time.time(), value)


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    last = _last_query.get(user_id, 0)
    if now - last < config.RATE_LIMIT_SECONDS:
        return True
    _last_query[user_id] = now
    return False


# ---- 文案 ----
HELP_TEXT = """🎬 <b>JavDB 搜番 Bot</b>

<b>用法</b>
/s <code>番号</code> — 搜索番号，看简介、封面、磁力
例：<code>/s MIDA-497</code>

💡 在群里也能用，把我拉进群就行（记得在 BotFather 关掉 Privacy Mode）
💡 任意聊天输入 <code>@本Bot 番号</code> 可内联搜索

返回内容：遮罩封面 · 中文简介 · 磁力 Top5（中字优先）
数据来源：JavDB"""

WELCOME_TEXT = """👋 欢迎使用 <b>JavDB 搜番 Bot</b>！

直接发：
<code>/s MIDA-497</code>

我会返回遮罩封面、中文简介和磁力链接。
输入 /help 查看完整说明。"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def build_caption(d: dict) -> str:
    """封面图的 caption（1024 字符以内）：标题 + 关键信息。"""
    number = _esc(d.get("number"))
    title_cn = _esc(translate(d.get("title") or "", src="ja"))
    score = d.get("score")
    date = _esc(d.get("release_date"))
    dur = d.get("duration")
    actors = ", ".join(_esc(a.get("name")) for a in (d.get("actors") or [])[:4])

    lines = [f"🎬 <b>{number}</b>"]
    if title_cn:
        lines.append(f"<i>{title_cn}</i>")
    meta = []
    if score:
        meta.append(f"⭐ {score}")
    if date:
        meta.append(f"📅 {date}")
    if dur:
        meta.append(f"⏱️ {dur}分钟")
    if meta:
        lines.append(" | ".join(meta))
    if actors:
        lines.append(f"👩 {actors}")
    return "\n".join(lines)[:1000]


def build_detail(d: dict, magnets: list[dict]) -> str:
    """详情消息：中文简介 + 标签/片商 + 磁力列表。"""
    parts: list[str] = []

    # 简介：优先 summary，没有就翻译标题
    summary = (d.get("summary") or "").strip()
    if summary:
        parts.append(f"📝 <b>简介</b>\n{_esc(translate(summary, src='ja'))}\n")
    else:
        title_cn = translate(d.get("title") or "", src="ja")
        if title_cn:
            parts.append(f"📝 <b>标题翻译</b>\n{_esc(title_cn)}\n")

    # 标签 / 片商 / 系列
    tags = [_esc(t.get("name")) for t in (d.get("tags") or []) if t.get("name")]
    if tags:
        parts.append(f"🏷️ {' · '.join(tags[:10])}")
    maker = _esc(d.get("maker_name"))
    if maker:
        parts.append(f"🏢 {maker}")
    series = _esc(d.get("series_name"))
    if series:
        parts.append(f"📚 {series}")

    # 磁力
    if magnets:
        parts.append(f"\n🧲 <b>磁力 Top{len(magnets)}</b>（中字优先）")
        for i, m in enumerate(magnets, 1):
            name = _esc(m.get("name") or "未知")
            size = jdb.format_size(m.get("size"))
            flags = []
            if m.get("cnsub"):
                flags.append("中字")
            if m.get("hd"):
                flags.append("高清")
            flag = f" <i>[{'·'.join(flags)}]</i>" if flags else ""
            link = jdb.magnet_link(m)
            parts.append(f"\n{i}️⃣ <b>{name}</b>{flag}\n📦 {size}\n<code>{_esc(link)}</code>")
    else:
        parts.append("\n🧲 暂无磁力")

    parts.append(f'\n🔗 <a href="https://javdb.com/v/{_esc(d.get("id"))}">JavDB 详情页</a>')
    return "\n".join(parts)


async def fetch_movie(code: str) -> dict | None:
    """搜番全流程（带缓存）：search → detail → magnets。"""
    key = code.strip().upper()
    hit = _cache_get(key)
    if hit:
        return hit
    movie = await jdb.search_movie(key)
    if not movie:
        return None
    detail = await jdb.get_detail(movie["id"]) or movie
    magnets = await jdb.get_magnets(movie["id"], config.MAGNET_COUNT)
    result = {"detail": detail, "magnets": magnets}
    _cache_set(key, result)
    return result


async def _download_cover(movie_number: str, cover_url: str) -> str | None:
    """用 javdb assets download 拿解密后的封面（图床图片是加密的，直接下是乱码）。
    返回本地文件路径；失败返回 None。"""
    if not cover_url or not movie_number:
        return None
    try:
        def _fetch():
            tmpdir = tempfile.mkdtemp(prefix="jdbcover_")
            # assets list 接番号（不支持 -i），输出 TYPE<TAB>URL，过滤出大封面
            p1 = subprocess.Popen(
                [config.JAVDB_BIN, "assets", "list", movie_number],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            cover_line = ""
            for raw in p1.stdout:
                line = raw.decode().strip()
                if line.startswith("image\t") and "/covers/" in line:
                    cover_line = line
                    break
            p1.wait()
            if not cover_line:
                return None
            p2 = subprocess.run(
                [config.JAVDB_BIN, "assets", "download", "--dir", tmpdir],
                input=(cover_line + "\n").encode(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60,
            )
            if p2.returncode != 0:
                return None
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
            return files[0] if files else None
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        log.warning("download cover failed: %s", e)
        return None


async def send_result(update: Update, code: str):
    msg = update.effective_message
    thinking = await msg.reply_text(f"🔍 正在搜索 <code>{_esc(code)}</code>…", parse_mode=ParseMode.HTML)

    try:
        result = await fetch_movie(code)
    except Exception as e:
        log.exception("fetch failed")
        await thinking.edit_text("⚠️ 搜索出错，稍后再试。")
        return

    if not result:
        await thinking.edit_text(
            f"❌ 没找到 <code>{_esc(code)}</code>\n"
            "检查下番号是否写对（例：<code>MIDA-497</code>）",
            parse_mode=ParseMode.HTML,
        )
        return

    d, magnets = result["detail"], result["magnets"]
    await thinking.delete()

    # 1) 遮罩封面（javdb assets download 解密后上传）
    cover = d.get("cover_url")
    cover_path = await _download_cover(d.get("number") or "", cover) if cover else None
    cover_dir = os.path.dirname(cover_path) if cover_path else None
    if cover_path:
        try:
            with open(cover_path, "rb") as f:
                await msg.reply_photo(
                    photo=f,
                    caption=build_caption(d),
                    parse_mode=ParseMode.HTML,
                    has_spoiler=True,  # 遮罩图片
                )
        except Exception as e:
            log.warning("send cover failed: %s", e)
        finally:
            if cover_dir:
                shutil.rmtree(cover_dir, ignore_errors=True)

    # 2) 详情 + 磁力
    text = build_detail(d, magnets)
    # TG 消息上限 4096，按需截断磁力部分
    await msg.reply_text(text[:4000], parse_mode=ParseMode.HTML,
                         disable_web_page_preview=True)


# ---- handlers ----
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if _rate_limited(user_id):
        await update.message.reply_text("⏳ 太快了，歇几秒再搜。")
        return
    if not ctx.args:
        await update.message.reply_text(
            "用法：<code>/s 番号</code>\n例：<code>/s MIDA-497</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    await send_result(update, " ".join(ctx.args))


async def inline_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """@bot 番号 → 内联返回简介卡片。"""
    query = (update.inline_query.query or "").strip()
    if len(query) < 3:
        return
    if _rate_limited(update.effective_user.id):
        return
    result = await fetch_movie(query)
    if not result:
        return
    d = result["detail"]
    number = d.get("number") or query.upper()
    title_cn = translate(d.get("title") or "", src="ja")
    text = build_detail(d, result["magnets"])
    results = [
        InlineQueryResultArticle(
            id=number,
            title=f"🎬 {number}",
            description=title_cn[:80],
            thumbnail_url=d.get("thumb_url"),
            input_message_content=InputTextMessageContent(
                text[:4000], parse_mode=ParseMode.HTML, disable_web_page_preview=True
            ),
        )
    ]
    await update.inline_query.answer(results, cache_time=300)


def main():
    if not config.BOT_TOKEN:
        raise SystemExit("请设置环境变量 BOT_TOKEN（从 @BotFather 获取）")
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("s", cmd_search))
    app.add_handler(InlineQueryHandler(inline_search))
    log.info("bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
