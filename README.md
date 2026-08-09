# PieappleDietBot

Personal Telegram bot: upload a nutrition-plan PDF (Italian, Spanish or English), get a
structured weekly meal plan synced to Google Calendar, and ask the bot about your meals
(today's dish, recipe, substitutions, nutrition) or tell it what you actually ate.

The bot only responds to authorized Telegram accounts (`OWNER_TELEGRAM_ID` /
`EXTRA_TELEGRAM_IDS` in `.env`) — everyone else is silently ignored.

See [CONFIGURATION.md](CONFIGURATION.md) for the full list of configuration parameters.

## 1. Prerequisites

- Python 3.11+
- A Telegram bot registered in [@BotFather](https://t.me/BotFather) as `@PieappleDietBot`
  (the token was already issued — see step 2)
- An Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
- A Google account, for the Calendar integration (step 4)

## 2. Install

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## 3. Configure `.env`

Copy `.env.example` to `.env` and fill in:

- `TELEGRAM_BOT_TOKEN` — from BotFather.
- `OWNER_TELEGRAM_ID` — your numeric Telegram user id. If you don't know it, leave it
  blank, run the bot (step 6), send it `/start`, and it will reply with your id. Put
  that id in `.env` and restart the bot.
- `ANTHROPIC_API_KEY` — your Claude API key.

## 4. Set up Google Calendar access

The bot writes events to your primary Google Calendar via OAuth (no server-side secrets
beyond your own Google account):

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project
   (or reuse one).
2. In **APIs & Services > Library**, enable the **Google Calendar API**.
3. In **APIs & Services > Credentials**, click **Create Credentials > OAuth client ID**.
   - If prompted, configure the OAuth consent screen first (choose "External", add
     yourself as a test user — this is fine for personal use).
   - Application type: **Desktop app**.
4. Download the resulting JSON and save it as `client_secret.json` in this project folder
   (the filename is referenced by `GOOGLE_CLIENT_SECRETS_PATH` in `.env`).
5. Run the one-time consent script — it opens a browser window for you to sign in and
   approve access, then caches a refresh token locally:

   ```bash
   python setup_google_auth.py
   ```

   This creates `token.json`. You won't need to repeat this unless you delete that file.

## 5. Run

```bash
python bot.py
```

The bot polls Telegram for updates; keep this process running while you want to use it.

## 6. Using the bot

- Send a PDF (weekly plan or single recipe) — the bot extracts it with Claude, shows you
  a summary, and on confirmation saves it and creates Google Calendar events for each
  meal.
- `/today` — today's breakfast/lunch/dinner, with buttons for recipe details,
  substitution, and nutrition info.
- `/week` — the full week's plan with recipe links.
- Just type what you ate (e.g. "ho mangiato una pizza invece della pasta") — the bot
  matches it against today's plan and logs whether you stayed on plan.
- `/report` — adherence summary for the current week.

## 7. Deploying on a Raspberry Pi 5 (always-on)

The bot is lightweight (Telegram polling + SQLite + occasional HTTPS calls) — a Pi 5
with 8GB RAM is comfortably more than enough. It still calls the Anthropic and Google
APIs over the internet as it does on your PC; nothing runs "more locally" by moving to
the Pi, this just makes it always-on instead of only running while your PC does.

1. **Raspberry Pi OS**: use the 64-bit version. Confirm Python 3.11+ is available
   (`python3 --version`); if needed: `sudo apt update && sudo apt install python3-venv python3-pip`.

2. **Set the timezone** (separate from the `TIMEZONE` env var, which only affects how
   Calendar events display their time) — the bot uses the Pi's system clock for "today"
   in day-off/next-Monday/week logic:
   ```bash
   sudo raspi-config   # Localisation Options > Timezone
   ```

3. **Copy the project over** (this folder is not a git repo, so use `scp`/`rsync`/WinSCP
   from your PC). Skip `.venv` and `__pycache__` — you'll recreate the venv on the Pi:
   ```powershell
   # from Windows PowerShell, run in this project folder
   scp -r * pi@<pi-ip-address>:/home/pi/pieapple-diet-bot/
   ```
   Also copy your **already-configured secrets** so you don't have to redo Google OAuth:
   `.env`, `client_secret.json`, `token.json`, and `data/pieapple.db` (your existing plan
   data) if you want to keep it.

4. **Install dependencies on the Pi**:
   ```bash
   cd /home/pi/pieapple-diet-bot
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

5. **Test it manually first**:
   ```bash
   .venv/bin/python bot.py
   ```
   Confirm it starts without errors, then Ctrl+C.

6. **Install as a systemd service** so it starts on boot and restarts if it crashes.
   A template is in `deploy/pieappledietbot.service` — edit `User=`/`WorkingDirectory=`/
   `ExecStart=` if your username or path differs from `pi` / `/home/pi/pieapple-diet-bot`:
   ```bash
   sudo cp deploy/pieappledietbot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now pieappledietbot
   sudo systemctl status pieappledietbot   # confirm it's running
   journalctl -u pieappledietbot -f        # follow logs
   ```

## Notes

- `.env`, `client_secret.json`, `token.json` and the SQLite database are all gitignored
  — never commit them, and transfer them to the Pi over a secure channel (`scp`, not
  email/chat).
