"""ADR-000 §5.2, D-05; ADR-003 §3.2, §8 (trwałość, walidacja), D-303; ADR-002 §4.8–4.9; TAC-002-01."""

from __future__ import annotations

import sqlite3
import threading

import pytest

from map_qa import store


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "data" / "map_qa.db"


def test_migration_idempotent_and_wal(db):
    c1 = store.connect(db)
    c1.close()
    c2 = store.connect(db)
    assert c2.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    tables = {r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "decisions", "decisions_history", "model_cache", "budget_ledger"} <= tables


def test_decision_persists_across_connections(db):  # AC-28, ADR-003 §8
    c = store.connect(db)
    store.save_decision(c, "1|a|speed", "confirmed_error", "50", "znak 50 na zdjęciu", "anna", "R1")
    c.close()
    c = store.connect(db)
    d = store.get_decisions(c)["1|a|speed"]
    assert (d["decision"], d["proposed_value"], d["author"], d["run_id"]) == ("confirmed_error", "50", "anna", "R1")
    assert d["decided_at"].endswith("Z") or "+00:00" in d["decided_at"]


def test_overwrite_moves_previous_to_history(db):
    c = store.connect(db)
    store.save_decision(c, "k", "uncertain", None, "a", "anna", "R1")
    store.save_decision(c, "k", "no_error", None, "b", "jan", "R2")
    assert store.get_decisions(c)["k"]["decision"] == "no_error"
    hist = store.decision_history(c, "k")
    assert len(hist) == 1 and hist[0]["decision"] == "uncertain" and hist[0]["replaced_at"]


@pytest.mark.parametrize(
    "decision, proposed, author",
    [("confirmed_error", None, "anna"), ("confirmed_error", "  ", "anna"), ("no_error", None, ""), ("błąd", None, "anna")],
)
def test_validation_saves_nothing(db, decision, proposed, author):  # ADR-003 §3.2
    c = store.connect(db)
    with pytest.raises(store.DecisionValidationError):
        store.save_decision(c, "k", decision, proposed, "x", author, "R1")
    assert store.get_decisions(c) == {}


def test_list_confirmed_only_confirmed(db):  # AC-29
    c = store.connect(db)
    store.save_decision(c, "a", "confirmed_error", "30", "", "anna", "R1")
    store.save_decision(c, "b", "no_error", None, "", "anna", "R1")
    assert [d["candidate_key"] for d in store.list_confirmed(c)] == ["a"]


def test_cache_key_includes_questions_version(db):  # AC-22, ADR-002 §4.9
    c = store.connect(db)
    assert store.cache_get(c, "sha", "m", "surface", 1) is None
    store.cache_put(c, "sha", "m", "surface", 1, {"answers": {}}, {"answer": "paved"})
    hit = store.cache_get(c, "sha", "m", "surface", 1)
    assert hit["reading"] == {"answer": "paved"} and hit["response"] == {"answers": {}}
    assert store.cache_get(c, "sha", "m", "surface", 2) is None
    assert store.cache_get(c, "sha", "m2", "surface", 1) is None


def test_budget_limit_counts_failures_and_survives_reconnect(db):  # ADR-002 §8 „Limit z błędami”
    c = store.connect(db)
    assert store.budget_reserve(c, "R1", "m", limit=3, max_cost=1.0, reserve=0.01)
    store.budget_record(c, "R1", "m", cost_usd=None, reserve=0.01, error=True, disable=False)
    assert store.budget_reserve(c, "R1", "m", limit=3, max_cost=1.0, reserve=0.01)
    store.budget_record(c, "R1", "m", cost_usd=0.002, reserve=0.01, error=False)
    c.close()
    c = store.connect(db)  # przerwany run i wznowienie — licznik z SQLite
    assert store.budget_reserve(c, "R1", "m", limit=3, max_cost=1.0, reserve=0.01)
    assert not store.budget_reserve(c, "R1", "m", limit=3, max_cost=1.0, reserve=0.01)
    u = store.budget_usage(c, "R1")["m"]
    assert u["sent"] == 3 and u["errors"] == 1
    assert u["cost_usd"] == pytest.approx(0.012)


def test_budget_limit_zero_refuses(db):
    c = store.connect(db)
    assert not store.budget_reserve(c, "R1", "m", limit=0, max_cost=0.0, reserve=0.01)
    assert store.budget_usage(c, "R1").get("m", {"sent": 0})["sent"] == 0


def test_budget_cost_is_shared_across_models(db):  # --max-cost-usd wspólne
    c = store.connect(db)
    assert store.budget_reserve(c, "R1", "a", limit=5, max_cost=0.02, reserve=0.01)
    store.budget_record(c, "R1", "a", cost_usd=0.015, reserve=0.01, error=False)
    assert not store.budget_reserve(c, "R1", "b", limit=5, max_cost=0.02, reserve=0.01)


def test_disable_model_after_error(db):  # AC-20
    c = store.connect(db)
    assert store.budget_reserve(c, "R1", "m", limit=5, max_cost=1.0, reserve=0.01)
    store.budget_record(c, "R1", "m", cost_usd=None, reserve=0.01, error=True, disable=True)
    assert store.budget_usage(c, "R1")["m"]["disabled"] is True
    assert not store.budget_reserve(c, "R1", "m", limit=5, max_cost=1.0, reserve=0.01)


def test_record_run(db):
    c = store.connect(db)
    store.record_run(c, "R1", 1, "2026-11-12T10:00:00Z", 1, "ok", {"x": 1})
    store.record_run(c, "R1", 1, "2026-11-12T10:00:00Z", 1, "ok", {"x": 2})
    assert store.get_run(c, "R1")["payload"] == {"x": 2}


def test_write_is_transactional_on_error(db, monkeypatch):
    c = store.connect(db)
    store.save_decision(c, "k", "uncertain", None, "a", "anna", "R1")

    real = store._insert_decision

    def broken(*a, **k):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "_insert_decision", broken)
    with pytest.raises(sqlite3.OperationalError):
        store.save_decision(c, "k", "no_error", None, "b", "jan", "R2")
    monkeypatch.setattr(store, "_insert_decision", real)
    assert store.get_decisions(c)["k"]["decision"] == "uncertain"
    assert store.decision_history(c, "k") == []
