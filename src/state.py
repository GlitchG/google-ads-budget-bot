"""SQLite store for pending budget actions across accounts + applied audit."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "agency.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_actions (
    token        TEXT PRIMARY KEY,     -- "<cid>:<budget_id>"
    cid          TEXT,
    campaign     TEXT,
    budget_id    INTEGER,
    current_micros  INTEGER,
    proposed_micros INTEGER,
    direction    TEXT,
    reason       TEXT,
    message_id   INTEGER,
    status       TEXT,                 -- pending | applied | skipped | error
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS applied_budget_changes (
    cid          TEXT,
    budget_id    INTEGER,
    campaign     TEXT,
    from_micros  INTEGER,
    to_micros    INTEGER,
    applied_at   TEXT
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_action(conn, a, message_id) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pending_actions(token, cid, campaign, budget_id, "
        "current_micros, proposed_micros, direction, reason, message_id, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?, 'pending', ?)",
        (a.token, a.cid, a.campaign, a.budget_id, a.current_micros, a.proposed_micros,
         a.direction, a.reason, message_id, _now()),
    )
    conn.commit()


def get_action(conn, token) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM pending_actions WHERE token=?", (token,)).fetchone()


def set_status(conn, token, status) -> None:
    conn.execute("UPDATE pending_actions SET status=? WHERE token=?", (status, token))
    conn.commit()


def record_applied(conn, cid, budget_id, campaign, from_micros, to_micros) -> None:
    conn.execute(
        "INSERT INTO applied_budget_changes(cid, budget_id, campaign, from_micros, to_micros, applied_at) "
        "VALUES (?,?,?,?,?,?)",
        (cid, budget_id, campaign, from_micros, to_micros, _now()),
    )
    conn.commit()
