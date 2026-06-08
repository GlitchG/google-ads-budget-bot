"""Load best-practice tips from a Markdown knowledge base.

Reads knowledge-base/best-practices.md (or KB_PATH), parses the practice bullets,
and selects the ones relevant to an account's situation. Returns [] if no file is
found, so tips.py falls back to its built-in list.

This lets a separate process (cron, another agent) grow the KB over time, and the
bot automatically surfaces the new practices — no code change needed.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import config

CANDIDATES = [
    config.KB_PATH,
    str(Path(__file__).resolve().parent.parent / "knowledge-base" / "best-practices.md"),
    str(Path.home() / "wiki" / "references" / "google-ads-best-practices.md"),
]

# bullet keyword -> the account-context flag it requires to be shown
REQS = {
    "demandgen": ("demand gen", "display", "video", "upper-funnel"),
    "brand": ("brand",),
    "pmax": ("pmax", "performance max"),
    "rank": ("rank", "ad rank"),
}
# section titles whose bullets are NOT budget tips
EXCLUDE_SECTIONS = ("sources", "changelog", "search-terms")


def _load() -> str:
    for p in CANDIDATES:
        if p and Path(p).is_file():
            try:
                return Path(p).read_text(encoding="utf-8")
            except OSError:
                continue
    return ""


def _md_to_tg(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def _practice_bullets(text: str) -> list[str]:
    out, excluded = [], False
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("## "):
            title = st[3:].strip().lower()
            excluded = any(x in title for x in EXCLUDE_SECTIONS)
            continue
        if excluded:
            continue
        if st.startswith("- ") and len(st) > 32:
            b = st[2:].strip()
            if "http" not in b and not re.match(r"^\d{4}-\d{2}-\d{2}", b):
                out.append(b)
    return out


def _required_flag(bullet: str):
    bl = bullet.lower()
    for flag, kws in REQS.items():
        if any(kw in bl for kw in kws):
            return flag
    return None


def select_tips(context: set[str], k: int = 4) -> list[str]:
    bullets = _practice_bullets(_load())
    if not bullets:
        return []
    specific, general = [], []
    for b in bullets:
        flag = _required_flag(b)
        if flag is None:
            general.append(b)
        elif flag in context:
            specific.append(b)

    wk = dt.date.today().isocalendar()[1]  # rotate weekly for variety

    def rot(lst):
        return (lst[wk % len(lst):] + lst[: wk % len(lst)]) if lst else lst

    picked, seen = [], set()
    for b in rot(specific) + rot(general):
        if b in seen:
            continue
        seen.add(b)
        picked.append(_md_to_tg(b))
        if len(picked) >= k:
            break
    return picked


def available() -> bool:
    return bool(_load())
