# Google Ads Budget Optimizer Bot

A self-hosted **Telegram bot** that audits your Google Ads accounts every week,
finds where budget is wasted or capped, and proposes **margin-aware budget moves**
you approve with one tap. Built for e-commerce advertisers and agencies managing
multiple accounts under one manager (MCC).

> Weekly report → prioritized findings → budget-change buttons → one-tap apply.
> **Nothing is changed in your account without an explicit approval tap.**

```
📊 shop-a.example — weekly audit
30 May – 06 Jun (conversion lag applied)

📈 Week summary (vs last week):
• Spend:  $35,206  ▲10%
• Revenue: $128,919  ▲44%
• Profit (revenue×60% − ads): $42,146  ▲95%
• ROAS: 3.7  ▲31%

Break-even ROAS 1.7 · scale floor 2.0 · 8/8 campaigns serving

🔴 [Scale: budget-capped] pm_winner — LIMITED, ROAS 3.7 ≥ 2.0 → +20% to grow revenue
🔴 [Reallocate] move budget from low-ROAS dg_video → pm_winner
🟡 [Lost IS: rank] shopping_ua — losing 52% IS to rank (bid/quality, not budget)

💡 Tips (from knowledge base): …
💰 Budget — pm_winner:  $760 → $912/day   [✅ Apply] [❌ Skip]
```

## Why it's not naive

Most "budget bots" just chase ROAS. This one optimizes for **profit**, and avoids
the classic mistakes:

- **Profit, not ROAS, drives decisions.** break-even ROAS = `1 / margin`. It scales
  any budget-limited campaign that's *profitable* (above break-even + a cushion) —
  even if below the account average — and cuts only what's actually losing money.
- **Conversion lag aware.** The analysis window ends a couple of days ago so late
  conversions don't make you cut winners on incomplete data.
- **Uses `primary_status`, not `status`.** Ended/paused campaigns (which stay
  `ENABLED` in the API) are filtered out, so you don't chase phantom "0-spend" issues.
- **Brand-safe.** Brand campaigns are never auto-scaled on their (inflated) ROAS.
- **Honest about blind spots.** Campaigns it *won't* auto-change (shared budgets,
  brand) are reported as "needs manual action" instead of silently ignored.
- **Self-monitoring.** Alerts to Telegram on API/auth failures; an optional watchdog
  pings you if the service goes down.

## Does it use AI?

**No LLM at runtime.** The bot is deterministic Python — it queries the Google Ads
API and applies fixed, auditable rules. No model decides what to change. The only
optional AI touchpoint is *maintaining* the Markdown knowledge base of tips, which
you can edit by hand or with any tool. It's fully standalone — no external agent or
service required.

## Features

- Multi-account (one entry per account under your MCC)
- Weekly summary: spend / revenue / profit / ROAS with week-over-week deltas
- Findings: budget pacing, ROAS reallocation, anomalies, lost-IS, tracking gaps
- One-tap budget changes with a configurable max step (e.g. ±20%) — or **advisory-only**
- Best-practice tips pulled from a Markdown **knowledge base** you can grow over time
- Per-account schedule times, conversion-lag handling, SQLite audit log
- Runs anywhere Python runs; systemd unit + watchdog included

## How it works

```
[weekly schedule] ─▶ pull campaign metrics (2 periods, conversion-lag adjusted)
                 ─▶ analyze per account (margin → break-even ROAS)
                 ─▶ post report + tips to Telegram
                 ─▶ (if enabled) post budget-change buttons
                          └─▶ on ✅ tap: CampaignBudgetService mutate + audit log
```

---

## Quick start

```bash
git clone https://github.com/GlitchG/google-ads-budget-bot
cd google-ads-budget-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then fill it in (see below)
python get_refresh_token.py   # one-time OAuth → writes refresh token to .env
python get_chat_id.py         # prints your Telegram chat ID → put in .env
# edit ACCOUNTS in config.py (cid / name / margin / tz / hour)

python bot_service.py         # run it; send /run or /ping in your Telegram chat
```

By default `WRITE_ENABLED=false` (advisory only). Flip it to `true` when you trust
the recommendations and want the one-tap budget buttons.

---

## Getting Google Ads API access

You need four things: a **developer token**, an **OAuth client**, a **refresh
token**, and your **account IDs**. Full step-by-step including the access
*application* (what to write so it gets approved): **[docs/GOOGLE_ADS_API_ACCESS.md](docs/GOOGLE_ADS_API_ACCESS.md)**.

1. **Developer token** — sign in to your **Manager (MCC) account** →
   *Tools & Settings → API Center* → copy the developer token. New tokens may need a
   short Basic Access application (describe it as internal reporting/optimization;
   Basic Access = 15,000 ops/day, plenty here).

2. **Google Cloud project + OAuth client**
   - [console.cloud.google.com](https://console.cloud.google.com) → create a project
   - *APIs & Services → Library* → enable **Google Ads API**
   - *OAuth consent screen* → External; add yourself under **Test users**
     (required while the screen is in "Testing")
   - *Credentials → Create credentials → OAuth client ID → Desktop app* → this gives
     you `GOOGLE_ADS_CLIENT_ID` and `GOOGLE_ADS_CLIENT_SECRET`

3. **Refresh token** — `python get_refresh_token.py` opens a browser; approve with
   the account that has access to the MCC. It writes `GOOGLE_ADS_REFRESH_TOKEN` into
   `.env`. (If you see "Google hasn't verified this app", that's expected in Testing
   mode — proceed.)

4. **Account IDs**
   - `GOOGLE_ADS_LOGIN_CUSTOMER_ID` = your MCC ID, digits only (no dashes)
   - each managed account's 10-digit customer ID goes in `ACCOUNTS` (`config.py`)

## Telegram setup

1. Message **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. Create a chat/group, add the bot, send any message, then run
   `python get_chat_id.py` and put the printed ID (negative for groups) into
   `TELEGRAM_CHAT_ID`.

---

## Configuration

All secrets live in `.env`; account list and behaviour in `config.py` / `.env`.

| Setting | What it does |
|---|---|
| `ACCOUNTS` (config.py) | one entry per account: `cid`, `name`, **`margin`** (gross margin → break-even ROAS), `tz`, optional `hour` |
| `WRITE_ENABLED` | `false` = advisory only; `true` = enable one-tap budget changes |
| `MAX_BUDGET_STEP` | max budget change per approval (e.g. `0.20` = ±20%) |
| `SCALE_BUFFER` | scale floor = break-even × (1 + buffer) |
| `CONVERSION_LAG_DAYS` | end the analysis window N days ago for settled data |
| `WOW_DELTA` | week-over-week change that flags an anomaly |
| `SCHEDULE_TZ/DAYS/HOUR` | when the weekly run fires (per-account `hour` overrides) |
| `KB_PATH` | optional path to the best-practices Markdown KB |

**Margin is the key input.** break-even ROAS = `1 / margin`. With a 60% margin,
anything above ROAS 1.67 is profitable, so the bot scales profitable-but-capped
campaigns and trims only the truly unprofitable ones.

## Telegram commands

- `/run` — build and post the report(s) now
- `/ping` — health check
- `/log` — show recent applied budget changes (audit trail)

## Deployment (24/7)

Run it as a service so the weekly schedule fires reliably:

```bash
sudo cp google-ads-budget-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now google-ads-budget-bot
journalctl -u google-ads-budget-bot -f
```

`check_ads_bots.sh` is a tiny watchdog you can schedule (cron/systemd timer) to
alert if the service goes down.

## Knowledge base

`knowledge-base/best-practices.md` holds the optimization tips. The bot parses the
bullets and shows the ones relevant to each account (Performance Max present → PMax
tips, Demand Gen present → upper-funnel tips, etc.). Grow the file over time —
manually or via a scheduled agent — and new practices appear in reports with no code
change.

## Project structure

```
config.py            settings + ACCOUNTS list
bot_service.py       scheduler + Telegram loop + approval handling
src/ads.py           Google Ads read layer (per account)
src/analysis.py      margin-aware analysis → findings + weekly summary
src/budget.py        budget change proposals + apply (idempotent, capped)
src/tips.py          context-aware best-practice tips
src/kb.py            loads the Markdown knowledge base
src/report.py        Telegram report formatting
src/state.py         SQLite audit log + pending approvals
get_refresh_token.py one-time OAuth helper
get_chat_id.py       Telegram chat-id helper
```

## Safety

- Read-only until you set `WRITE_ENABLED=true`; even then, every change needs a tap.
- Only **budgets** are changed (no bids, no status), capped at `MAX_BUDGET_STEP` per
  change and a rolling 30-day ceiling (`MONTHLY_BUDGET_CAP`) so weekly increases
  can't compound forever.
- Brand and shared-budget campaigns are never auto-changed.
- All applied changes are written to a local SQLite audit log (`/log` shows them).

## Tech

Python · [google-ads](https://pypi.org/project/google-ads/) · APScheduler ·
Telegram Bot API · SQLite. No framework, no database server.

## License

MIT — see [LICENSE](LICENSE).
