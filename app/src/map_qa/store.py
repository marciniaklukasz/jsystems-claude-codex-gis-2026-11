"""Trwały stan w SQLite: runy, decyzje (z historią), cache odczytów, budżet (ADR-000 D-05, ADR-003 §3.2, ADR-002 §4.8–4.9)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DECISIONS = ("confirmed_error", "no_error", "uncertain")
DECISION_LABEL = {"confirmed_error": "potwierdzony błąd mapy", "no_error": "brak błędu", "uncertain": "niepewne"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, stage INTEGER NOT NULL, created_at TEXT NOT NULL,
    questions_version INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    candidate_key TEXT PRIMARY KEY,
    decision TEXT NOT NULL CHECK (decision IN ('confirmed_error', 'no_error', 'uncertain')),
    proposed_value TEXT, comment TEXT NOT NULL DEFAULT '', author TEXT NOT NULL,
    decided_at TEXT NOT NULL, run_id TEXT
);
CREATE TABLE IF NOT EXISTS decisions_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_key TEXT NOT NULL, decision TEXT NOT NULL,
    proposed_value TEXT, comment TEXT, author TEXT, decided_at TEXT, run_id TEXT, replaced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_cache (
    image_sha256 TEXT NOT NULL, model TEXT NOT NULL, question_id TEXT NOT NULL,
    questions_version INTEGER NOT NULL, response_json TEXT NOT NULL, reading_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (image_sha256, model, question_id, questions_version)
);
CREATE TABLE IF NOT EXISTS budget_ledger (
    run_id TEXT NOT NULL, model TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, model)
);
"""


class DecisionValidationError(ValueError):
    """Niepoprawna decyzja analityka; komunikat po polsku."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # transakcje jawnie przez BEGIN
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


class _tx:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, *_):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


# --- decyzje -------------------------------------------------------------------------------
def validate_decision(decision: str, proposed_value: str | None, author: str) -> None:
    if decision not in DECISIONS:
        raise DecisionValidationError("Nieznana decyzja.")
    if not (author or "").strip():
        raise DecisionValidationError("Podaj autora decyzji.")
    if decision == "confirmed_error" and not (proposed_value or "").strip():
        raise DecisionValidationError("Decyzja „potwierdzony błąd mapy” wymaga wartości proponowanej.")


def _insert_decision(conn, key, decision, proposed_value, comment, author, decided_at, run_id):
    conn.execute(
        "INSERT INTO decisions (candidate_key, decision, proposed_value, comment, author, decided_at, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(candidate_key) DO UPDATE SET decision=excluded.decision, "
        "proposed_value=excluded.proposed_value, comment=excluded.comment, author=excluded.author, "
        "decided_at=excluded.decided_at, run_id=excluded.run_id",
        (key, decision, proposed_value, comment, author, decided_at, run_id),
    )


def save_decision(conn, key: str, decision: str, proposed_value: str | None, comment: str, author: str,
                  run_id: str | None, now: str | None = None) -> dict:
    validate_decision(decision, proposed_value, author)
    proposed_value = (proposed_value or "").strip() or None
    decided_at = now or utc_now()
    with _tx(conn):
        prev = conn.execute("SELECT * FROM decisions WHERE candidate_key = ?", (key,)).fetchone()
        if prev is not None:
            conn.execute(
                "INSERT INTO decisions_history (candidate_key, decision, proposed_value, comment, author, decided_at, run_id, replaced_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (prev["candidate_key"], prev["decision"], prev["proposed_value"], prev["comment"], prev["author"],
                 prev["decided_at"], prev["run_id"], decided_at),
            )
        _insert_decision(conn, key, decision, proposed_value, comment or "", author.strip(), decided_at, run_id)
    return get_decisions(conn)[key]


def get_decisions(conn) -> dict[str, dict]:
    return {r["candidate_key"]: dict(r) for r in conn.execute("SELECT * FROM decisions")}


def decision_history(conn, key: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM decisions_history WHERE candidate_key = ? ORDER BY id", (key,))]


def list_confirmed(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM decisions WHERE decision = 'confirmed_error' ORDER BY decided_at, candidate_key")]


# --- runy ----------------------------------------------------------------------------------
def record_run(conn, run_id: str, stage: int, created_at: str, questions_version: int, status: str, payload: dict) -> None:
    with _tx(conn):
        conn.execute(
            "INSERT INTO runs (run_id, stage, created_at, questions_version, status, payload) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, payload=excluded.payload",
            (run_id, stage, created_at, questions_version, status, json.dumps(payload, ensure_ascii=False)),
        )


def get_run(conn, run_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


# --- cache ---------------------------------------------------------------------------------
def cache_get(conn, image_sha256: str, model: str, question_id: str, questions_version: int) -> dict | None:
    r = conn.execute(
        "SELECT response_json, reading_json, created_at FROM model_cache WHERE image_sha256=? AND model=? AND question_id=? AND questions_version=?",
        (image_sha256, model, question_id, questions_version),
    ).fetchone()
    if r is None:
        return None
    return {"response": json.loads(r["response_json"]), "reading": json.loads(r["reading_json"]), "created_at": r["created_at"]}


def cache_put(conn, image_sha256: str, model: str, question_id: str, questions_version: int, response: dict, reading: dict) -> None:
    with _tx(conn):
        conn.execute(
            "INSERT OR REPLACE INTO model_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            (image_sha256, model, question_id, questions_version, json.dumps(response, ensure_ascii=False),
             json.dumps(reading, ensure_ascii=False), utc_now()),
        )


# --- budżet --------------------------------------------------------------------------------
def budget_reserve(conn, run_id: str, model: str, *, limit: int, max_cost: float, reserve: float) -> bool:
    """Jedna transakcja: sprawdź limit, wyłączenie i koszt; zwiększ `sent` (żądanie nieudane zostaje policzone)."""
    if limit <= 0:
        return False
    with _tx(conn):
        conn.execute("INSERT OR IGNORE INTO budget_ledger (run_id, model) VALUES (?, ?)", (run_id, model))
        row = conn.execute("SELECT sent, disabled FROM budget_ledger WHERE run_id=? AND model=?", (run_id, model)).fetchone()
        total = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM budget_ledger WHERE run_id=?", (run_id,)).fetchone()[0]
        if row["disabled"] or row["sent"] >= limit or total + reserve > max_cost + 1e-12:
            return False
        conn.execute("UPDATE budget_ledger SET sent = sent + 1 WHERE run_id=? AND model=?", (run_id, model))
    return True


def budget_record(conn, run_id: str, model: str, *, cost_usd: float | None, reserve: float, error: bool, disable: bool = False) -> None:
    """Po żądaniu: dolicz koszt z `usage.cost` albo rezerwę; błąd zwiększa licznik, `disable` wyłącza model (AC-20)."""
    add = reserve if cost_usd is None else float(cost_usd)
    with _tx(conn):
        conn.execute("INSERT OR IGNORE INTO budget_ledger (run_id, model) VALUES (?, ?)", (run_id, model))
        conn.execute(
            "UPDATE budget_ledger SET cost_usd = cost_usd + ?, errors = errors + ?, disabled = MAX(disabled, ?) WHERE run_id=? AND model=?",
            (add, 1 if error else 0, 1 if disable else 0, run_id, model),
        )


def budget_disable(conn, run_id: str, model: str) -> None:
    with _tx(conn):
        conn.execute("INSERT OR IGNORE INTO budget_ledger (run_id, model) VALUES (?, ?)", (run_id, model))
        conn.execute("UPDATE budget_ledger SET disabled = 1 WHERE run_id=? AND model=?", (run_id, model))


def budget_usage(conn, run_id: str) -> dict[str, dict]:
    return {
        r["model"]: {"sent": r["sent"], "errors": r["errors"], "cost_usd": r["cost_usd"], "disabled": bool(r["disabled"])}
        for r in conn.execute("SELECT * FROM budget_ledger WHERE run_id=? ORDER BY model", (run_id,))
    }
