"""
TeraBox -> Telegram bot (Option B: native video + file upload via Pyrogram bot session)

Hosting: Render free web service (webhook mode + keep-alive).
It calls YOUR Cloudflare worker to resolve the TeraBox link, streams the
direct CDN download to disk, then uploads to Telegram as both video and file.

Required environment variables (set in Render dashboard):
  API_ID        - from https://my.telegram.org
  API_HASH      - from https://my.telegram.org
  BOT_TOKEN     - from @BotFather
  WORKER_URL    - your worker base, e.g. https://tboxair.worksbeyondworks.workers.dev
  WEBHOOK_BASE  - your Render external URL, e.g. https://your-bot.onrender.com
  PORT          - provided automatically by Render
"""

import os
import re
import asyncio
import time
import logging
from urllib.parse import quote

import aiohttp
from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tbox-bot")

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WORKER_URL = os.environ.get("WORKER_URL", "").rstrip("/")
WEBHOOK_BASE = os.environ.get("WEBHOOK_BASE", "").rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))

DOWNLOAD_DIR = "/tmp/tbox"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Pyrogram bot client (in-memory session so no file persistence needed)
app = Client(
    "tbox-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    workers=4,
)

TERABOX_LINK_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def human(n):
    n = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


async def resolve_link(session: aiohttp.ClientSession, link: str):
    """Call the Cloudflare worker to resolve the TeraBox share link."""
    api = f"{WORKER_URL}/api?url={quote(link, safe='')}"
    async with session.get(api, timeout=aiohttp.ClientTimeout(total=60)) as r:
        data = await r.json()
    if data.get("status") != "success" or not data.get("files"):
        raise RuntimeError(data.get("message") or "Could not resolve link")
    return data["files"][0]


async def download_file(session, url, dest, status_msg):
    """Stream the CDN download to disk with periodic progress edits."""
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.terabox.com/"}
    last_edit = 0
    downloaded = 0
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as r:
        total = int(r.headers.get("Content-Length", 0))
        with open(dest, "wb") as f:
            async for chunk in r.content.iter_chunked(1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_edit > 4:  # throttle edits to avoid rate limits
                    last_edit = now
                    pct = (downloaded / total * 100) if total else 0
                    try:
                        await status_msg.edit_text(
                            f"⬇️ Downloading… {human(downloaded)}"
                            + (f" / {human(total)} ({pct:.0f}%)" if total else "")
                        )
                    except Exception:
                        pass
    return dest


@app.on_message(filters.command("start"))
async def start(_, m: Message):
    await m.reply_text(
        "👋 Send me a TeraBox share link and I'll fetch the video.\n\n"
        "I'll send it back as a streamable video **and** a downloadable file.\n"
        "Large files take a little time — I'll keep you posted."
    )


@app.on_message(filters.text & ~filters.command(["start"]))
async def handle_link(_, m: Message):
    match = TERABOX_LINK_RE.search(m.text or "")
    if not match:
        await m.reply_text("Please send a valid TeraBox share link.")
        return
    link = match.group(0)
    status = await m.reply_text("🔎 Resolving link…")

    dest = None
    try:
        async with aiohttp.ClientSession() as session:
            info = await resolve_link(session, link)
            name = info.get("file_name", "video.mp4")
            size = info.get("size_bytes", 0)
            dl = info.get("direct_link") or info.get("download_link")
            if not dl:
                await status.edit_text("❌ No download link found.")
                return

            await status.edit_text(
                f"📄 **{name}**\n📦 {human(size)}\n\n⬇️ Starting download…"
            )

            safe_name = re.sub(r"[^\w.\-]", "_", name)
            dest = os.path.join(DOWNLOAD_DIR, safe_name)
            await download_file(session, dl, dest, status)

        await status.edit_text("⬆️ Uploading to Telegram…")

        thumb = info.get("thumbnail") or None

        # Send as streamable video
        try:
            await m.reply_video(
                dest,
                caption=f"🎬 {name}",
                supports_streaming=True,
            )
        except Exception as e:
            log.warning(f"video send failed: {e}")

        # Send as downloadable document/file
        await m.reply_document(dest, caption=f"📁 {name}")

        await status.delete()

    except Exception as e:
        log.exception("handle_link error")
        try:
            await status.edit_text(f"❌ Error: {e}")
        except Exception:
            pass
    finally:
        if dest and os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception:
                pass


# ---------- Web server (Render needs a bound port) + webhook ----------

async def health(request):
    return web.Response(text="TeraBox bot alive")


async def run():
    await app.start()
    me = await app.get_me()
    log.info(f"Bot started as @{me.username}")

    # Minimal HTTP server so Render's web service has a bound port,
    # and so an external uptime pinger can keep the instance awake.
    server = web.Application()
    server.router.add_get("/", health)
    server.router.add_get("/health", health)

    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"HTTP server on :{PORT}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
