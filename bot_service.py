"""Multi-account Google Ads budget bot.

On schedule (per-account weekly time): for each account in config.ACCOUNTS —
pull metrics, analyze (margin-aware, conversion-lag-adjusted), post report +
best-practice tips, and (if WRITE_ENABLED) per-campaign budget-change buttons.
Budgets only; brand & shared budgets are never auto-changed. Commands: /run, /ping.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

import config
from src import ads, budget, kb, state, telegram, tips
from src.analysis import analyze
from src.report import format_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ads-bot")


def _money(micros: int) -> str:
    return f"{config.CURRENCY}{micros / 1e6:,.0f}"


def run_account(conn, acc: dict) -> None:
    cid, name, margin, tz = acc["cid"], acc["name"], acc["margin"], acc["tz"]
    log.info("Analyzing %s (%s)…", name, cid)
    cur, prev, (cs, ce), _ = ads.pull_two_periods(cid, tz, days=7)
    result = analyze(cur, prev, margin, days=7)
    period = f"{cs:%d %b} – {ce:%d %b %Y}"
    telegram.send(format_report(ads.account_name(cid), period, result))

    tip_lines = tips.generate_tips(result["serving"])
    src = "knowledge base" if kb.available() else "built-in"
    telegram.send(f"<b>💡 Tips ({src}):</b>\n\n" + "\n\n".join(tip_lines))

    if not config.WRITE_ENABLED:
        return
    actions, skipped = budget.build_actions(cid, result["serving"], margin)
    if skipped:
        lines = "\n".join(f"• <b>{n}</b> — {r}" for n, r in skipped)
        telegram.send(f"⚠️ <b>Needs manual action — {name}:</b>\n{lines}")
    if not actions:
        return
    telegram.send(f"💰 <b>Budget — {name}</b> (max ±{config.MAX_BUDGET_STEP*100:.0f}%). "
                  f"Applied only on tap:")
    for a in actions:
        arrow = "▲" if a.direction == "up" else "▼"
        text = (f"{arrow} <b>{a.campaign}</b> <i>({name})</i>\n"
                f"{_money(a.current_micros)} → <b>{_money(a.proposed_micros)}</b>/day\n"
                f"<i>{a.reason}</i>")
        keyboard = [[{"text": "✅ Apply", "callback_data": f"bgo:{a.token}"},
                     {"text": "❌ Skip", "callback_data": f"bno:{a.token}"}]]
        mid = telegram.send_buttons(text, keyboard)
        state.save_action(conn, a, mid)
    log.info("%s: posted %d budget actions", name, len(actions))


def _alert(name: str, exc: Exception) -> None:
    msg = str(exc)
    auth = any(k in msg.upper() for k in ("AUTHENTICATION", "REFRESH", "INVALID_GRANT",
                                          "PERMISSION_DENIED", "UNAUTHENTICATED"))
    hint = ("\n🔑 Looks like an access/refresh-token problem — this token is shared, "
            "so ALL accounts are affected. Check urgently." if auth else "")
    telegram.send(f"⚠️ <b>Failure: {name}</b>\n<code>{msg[:300]}</code>{hint}")


def run_all() -> None:
    conn = state.connect()
    telegram.send("📊 <b>Weekly report</b> — gathering all accounts…")
    for acc in config.ACCOUNTS:
        try:
            run_account(conn, acc)
        except Exception as e:  # noqa: BLE001
            log.exception("account %s failed", acc.get("name"))
            _alert(acc.get("name", "?"), e)


def _handle_callback(conn, cb) -> None:
    data = cb.get("data", "")
    cb_id = cb["id"]
    mid = (cb.get("message") or {}).get("message_id")
    if not (data.startswith("bgo:") or data.startswith("bno:")):
        telegram.answer_callback(cb_id)
        return
    token = data[4:]
    a = state.get_action(conn, token)
    if not a or a["status"] != "pending":
        telegram.answer_callback(cb_id, "Already handled.")
        return
    if data.startswith("bno:"):
        state.set_status(conn, token, "skipped")
        telegram.answer_callback(cb_id, "Skipped.")
        telegram.edit(mid, f"❌ <b>{a['campaign']}</b> — skipped.")
        return
    try:
        budget.apply_budget(a["cid"], a["budget_id"], a["proposed_micros"])
        state.set_status(conn, token, "applied")
        state.record_applied(conn, a["cid"], a["budget_id"], a["campaign"],
                             a["current_micros"], a["proposed_micros"])
        telegram.answer_callback(cb_id, "Applied ✅")
        telegram.edit(mid, f"✅ <b>{a['campaign']}</b> — budget: "
                           f"{_money(a['current_micros'])} → {_money(a['proposed_micros'])}/day.")
    except Exception as e:  # noqa: BLE001
        state.set_status(conn, token, "error")
        telegram.answer_callback(cb_id, "Error.")
        telegram.edit(mid, f"⚠️ <b>{a['campaign']}</b> — apply error: {e}")
        log.exception("apply failed")


def poll_loop() -> None:
    conn = state.connect()
    offset = None
    log.info("Poll loop started.")
    while True:
        try:
            for upd in telegram.get_updates(offset, timeout=30):
                offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    _handle_callback(conn, upd["callback_query"])
                    continue
                text = ((upd.get("message") or {}).get("text") or "").strip()
                if text.startswith("/run"):
                    telegram.send("⏳ Running all accounts…")
                    run_all()
                elif text.startswith("/ping"):
                    accs = ", ".join(a["name"] for a in config.ACCOUNTS)
                    telegram.send(f"🟢 Bot alive. Accounts: {accs}.")
        except Exception:  # noqa: BLE001
            log.exception("poll loop error")


def _run_one(acc: dict) -> None:
    conn = state.connect()
    try:
        run_account(conn, acc)
    except Exception as e:  # noqa: BLE001
        log.exception("scheduled run for %s failed", acc.get("name"))
        _alert(acc.get("name", "?"), e)


def main() -> None:
    state.connect()
    sched = BackgroundScheduler(timezone=config.SCHEDULE_TZ)
    # One job per account, each at its own weekly time (per-account hour).
    for acc in config.ACCOUNTS:
        sched.add_job(_run_one, "cron", day_of_week=config.SCHEDULE_DAYS,
                      hour=acc.get("hour", config.SCHEDULE_HOUR),
                      minute=config.SCHEDULE_MINUTE, args=[acc],
                      id=f"weekly_{acc['cid']}", misfire_grace_time=3600)
    sched.start()
    sked = ", ".join(f"{a['name']} {a.get('hour', config.SCHEDULE_HOUR):02d}:00" for a in config.ACCOUNTS)
    log.info("Scheduler started: %s", sked)
    mode = "write enabled" if config.WRITE_ENABLED else "advisory only"
    telegram.send(f"🟢 Bot online ({mode}). Schedule ({config.SCHEDULE_DAYS}, {config.SCHEDULE_TZ}): "
                  f"<b>{sked}</b>. /run — now, /ping — health.")
    poll_loop()


if __name__ == "__main__":
    main()
