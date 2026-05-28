# TeraBox → Telegram Bot (Render free)

Sends a TeraBox video into Telegram as a **streamable video** + a **downloadable file**.
Uses Pyrogram bot session (up to ~2 GB) and calls your Cloudflare Worker to resolve links.

## 1. Get your credentials

- **API_ID** and **API_HASH**: go to https://my.telegram.org → API development tools → create an app.
- **BOT_TOKEN**: message @BotFather → /newbot → copy the token.
- **WORKER_URL**: your worker, e.g. `https://tboxair.worksbeyondworks.workers.dev`

## 2. Push this folder to GitHub

Put `bot.py`, `requirements.txt`, and this README in a repo.

## 3. Deploy on Render

1. Render → **New +** → **Web Service** → connect the repo.
2. **Runtime:** Python 3
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `python bot.py`
5. **Instance type:** Free

### Environment variables (Settings → Environment)

| Key          | Value                                              |
|--------------|----------------------------------------------------|
| API_ID       | (number from my.telegram.org)                      |
| API_HASH     | (hash from my.telegram.org)                        |
| BOT_TOKEN    | (token from BotFather)                             |
| WORKER_URL   | https://tboxair.worksbeyondworks.workers.dev       |

Do NOT set PORT — Render provides it automatically.

6. Create Web Service. Watch logs for `Bot started as @yourbot`.

## 4. Keep it awake (important on free tier)

Render free sleeps after 15 min idle. To keep the bot responsive:

1. Copy your Render URL (e.g. `https://your-bot.onrender.com`).
2. Go to https://cron-job.org (free), create a job that GETs that URL every 10 minutes.

This pings the health endpoint and keeps the instance from sleeping.

## 5. Use it

Open your bot in Telegram → /start → paste a TeraBox link.

## Honest limits on Render free

- ~512 MB RAM and a shared CPU: very large files (multi-GB) may fail mid-transfer.
- Speed depends on Render's bandwidth, not your code — expect tens of seconds to
  minutes per file. For faster/larger, move to a small VPS later (same code).
- The file is downloaded to /tmp then deleted after sending.
