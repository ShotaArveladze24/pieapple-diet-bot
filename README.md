# PieappleDietBot

Personal Telegram bot: manage your meal plan with SQLite-backed storage, import a weekly plan
from a PDF, and ask the bot about your meals (today's dish, recipe, substitutions,
nutrition). URL import and Google Calendar sync are disabled.

The bot only responds to authorized Telegram accounts (`OWNER_TELEGRAM_ID` /
`EXTRA_TELEGRAM_IDS` in `.env`) — everyone else is silently ignored.

**No Anthropic API key is used anywhere.** PDF plan upload and recipe Scan (`/scan`,
`/scan_week`, `/scan_all`, `/edit_recipe`'s Scan button) write a request file instead of
calling Claude over the network; a separately scheduled Claude Code run (billed to a
Claude Pro subscription, not metered API usage) picks it up and writes back a response
file. See [ai_queue/SPEC.md](ai_queue/SPEC.md) for the mechanism and step 7 below for
how it's scheduled on the Pi.

See [CONFIGURATION.md](CONFIGURATION.md) for the full list of configuration parameters.

## 1. Prerequisites

- Python 3.11+
- A Telegram bot registered in [@BotFather](https://t.me/BotFather) as `@PieappleDietBot`
  (the token was already issued — see step 2)
- No Anthropic API key needed. No Google Calendar access is required for the current bot.

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

## 4. AI queue / Google Calendar support

PDF upload and recipe Scan queue a request under `data/ai_queue/requests/` and reply
right away instead of blocking — the bot checks `data/ai_queue/responses/` every 5
minutes and messages you when the result is in (see step 7 for scheduling the
consumer that fulfills these). URL import and Google Calendar sync remain disabled —
use the manual recipe commands instead:

- `/addrecipe`
- `/replace_recipe`
- `/recipes`
- `/recipe_details <id>`
- `/today`
- `/tomorrow`
- `/week`

## 5. Run

```bash
python bot.py
```

The bot polls Telegram for updates; keep this process running while you want to use it.

## 6. Using the bot

- Send a PDF (weekly plan or single recipe) — the bot queues it for extraction and
  messages you a summary of the parsed plan once the AI queue consumer (step 7) has
  processed it.
- `/today` — today's breakfast/lunch/dinner, with buttons for recipe details,
  substitution, and nutrition info.
- `/week` — the full week's plan with recipe links.
- Just type what you ate (e.g. "ho mangiato una pizza invece della pasta") — the bot
  matches it against today's plan and logs whether you stayed on plan.
- `/report` — adherence summary for the current week.
- `/scan <id>`, `/scan_week`, `/scan_all` — queue recipe(s) for Scan (missing links,
  translations, nutrition); the bot messages you as each one finishes.

## 7. Deploying on a Raspberry Pi 5 (always-on)

The bot is lightweight (Telegram polling + SQLite, no network calls of its own) — a Pi 5
with 8GB RAM is comfortably more than enough. Moving to the Pi just makes it always-on
instead of only running while your PC does. The Pi also runs a second, independent
scheduled job — the AI queue consumer — which is what actually calls Claude (via the
Claude Code CLI under a Claude Pro subscription, not a metered API key).

1. **Raspberry Pi OS**: use the 64-bit version. Confirm Python 3.11+ is available
   (`python3 --version`); if needed: `sudo apt update && sudo apt install python3-venv python3-pip`.
   Also install the Claude Code CLI and log it in (`claude login`) under the account
   holding the Claude Pro subscription — the AI queue consumer runs as that CLI.

2. **Set the timezone** (separate from the `TIMEZONE` env var, which only affects how
   Calendar events display their time) — the bot uses the Pi's system clock for "today"
   in day-off/next-Monday/week logic:
   ```bash
   sudo raspi-config   # Localisation Options > Timezone
   ```

3. **Get the code onto the Pi**:
   ```bash
   git clone https://github.com/ShotaArveladze24/pieapple-diet-bot.git /home/ciccunitt/pieapple-diet-bot
   ```
   Then copy over your **secrets**, which are gitignored and never in the repo — from
   your PC: `.env`, `client_secret.json`, `token.json`, and `data/pieapple.db` (your
   existing plan data) if you want to keep it:
   ```powershell
   # from Windows PowerShell, run in this project folder
   scp .env client_secret.json token.json ciccunitt@<pi-ip-address>:/home/ciccunitt/pieapple-diet-bot/
   scp data/pieapple.db ciccunitt@<pi-ip-address>:/home/ciccunitt/pieapple-diet-bot/data/
   ```
   To update the bot later, `git pull` on the Pi instead of re-copying everything.

4. **Install dependencies on the Pi**:
   ```bash
   cd /home/ciccunitt/pieapple-diet-bot
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   chmod +x deploy/run_ai_consumer.sh
   ```

5. **Test it manually first**:
   ```bash
   .venv/bin/python bot.py
   ```
   Confirm it starts without errors, then Ctrl+C. Also do a manual dry run of the
   consumer once `claude` is logged in: `./deploy/run_ai_consumer.sh` (with nothing
   queued yet, it should just report 0 requests processed).

6. **Install the bot as a systemd service** so it starts on boot and restarts if it
   crashes. A template is in `deploy/pieappledietbot.service` — edit `User=`/
   `WorkingDirectory=`/`ExecStart=` if your username or path differs from `ciccunitt` /
   `/home/ciccunitt/pieapple-diet-bot`:
   ```bash
   sudo cp deploy/pieappledietbot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now pieappledietbot
   sudo systemctl status pieappledietbot   # confirm it's running
   journalctl -u pieappledietbot -f        # follow logs
   ```

7. **Install the AI queue consumer timer**, which runs `deploy/run_ai_consumer.sh`
   every 5 minutes — this is the process that actually does the Claude work (PDF
   extraction, recipe Scan), reading `ai_queue/CONSUMER_PROMPT.md` and
   `ai_queue/SPEC.md`. Edit `User=`/`WorkingDirectory=`/`ExecStart=` in
   `deploy/pieapple-ai-consumer.service` the same way as above if needed:
   ```bash
   sudo cp deploy/pieapple-ai-consumer.service deploy/pieapple-ai-consumer.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now pieapple-ai-consumer.timer
   systemctl list-timers pieapple-ai-consumer.timer   # confirm it's scheduled
   journalctl -u pieapple-ai-consumer -f              # follow consumer runs
   ```

## Notes

- `.env`, `client_secret.json`, `token.json` and the SQLite database are all gitignored
  — never commit them, and transfer them to the Pi over a secure channel (`scp`, not
  email/chat).
- `data/ai_queue/` (requests/responses/log) is also gitignored — it's runtime state,
  not something to version.
