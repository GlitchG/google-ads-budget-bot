"""Configuration — loads .env and the list of accounts to manage.

Nothing secret lives here. Real values go in .env (gitignored). See README.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _req(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing env var {name} (set it in .env)")
    return v


# ── Google Ads (one MCC/manager account can serve all child accounts) ───────
DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()

# ── Telegram ────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CURRENCY = os.getenv("CURRENCY", "$").strip()

# ── Schedule (weekly). Per-account hour can override SCHEDULE_HOUR below. ────
SCHEDULE_TZ = os.getenv("SCHEDULE_TZ", "Europe/Lisbon").strip()
SCHEDULE_DAYS = os.getenv("SCHEDULE_DAYS", "wed").strip()       # cron day_of_week
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "9"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))

# ── Analysis & write behaviour ──────────────────────────────────────────────
# ~90% of conversion value often lands a couple of days after the click, so the
# analysis window ends this many days ago to use settled data.
CONVERSION_LAG_DAYS = int(os.getenv("CONVERSION_LAG_DAYS", "2"))
WOW_DELTA = float(os.getenv("WOW_DELTA", "0.30"))              # week-over-week anomaly threshold
NO_CONV_CLICKS = int(os.getenv("NO_CONV_CLICKS", "25"))        # clicks w/ 0 conv -> flag
SCALE_BUFFER = float(os.getenv("SCALE_BUFFER", "0.20"))        # scale floor = break-even * (1+buffer)
MAX_BUDGET_STEP = float(os.getenv("MAX_BUDGET_STEP", "0.20"))  # max budget change per approval
# When false the bot is advisory-only (no buttons that mutate the account).
WRITE_ENABLED = os.getenv("WRITE_ENABLED", "false").strip().lower() in ("1", "true", "yes")

# Best-practices knowledge base (optional). Blank -> kb.py tries ./knowledge-base.
KB_PATH = os.getenv("KB_PATH", "").strip()

# ── Accounts to manage ──────────────────────────────────────────────────────
# One entry per Google Ads account under your MCC. EDIT THESE.
#   cid    : 10-digit customer ID, no dashes
#   name   : label shown in reports
#   margin : gross margin (1 - COGS). break-even ROAS = 1 / margin
#   tz     : the account's reporting timezone (for date ranges)
#   hour   : weekly send hour in SCHEDULE_TZ (optional; defaults to SCHEDULE_HOUR)
ACCOUNTS = [
    {"cid": "1112223333", "name": "shop-a.example", "margin": 0.60, "tz": "Europe/Kyiv", "hour": 9},
    {"cid": "4445556666", "name": "shop-b.example", "margin": 0.45, "tz": "Europe/Kyiv", "hour": 10},
]


def google_ads_config() -> dict:
    """Config dict for GoogleAdsClient.load_from_dict()."""
    return {
        "developer_token": _req("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": _req("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": _req("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": _req("GOOGLE_ADS_REFRESH_TOKEN"),
        "login_customer_id": _req("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
        "use_proto_plus": True,
    }
