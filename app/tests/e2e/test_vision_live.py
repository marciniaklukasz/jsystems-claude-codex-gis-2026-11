"""E2E na prawdziwym API OpenRouter — BEZ mocków (polecenie prowadzącego 2026-11-12; ADR-002 §8 „Rzeczywista próba”).

Uruchomienie świadome (płatne, przydział ≤ 1 USD): `uv run pytest -m live tests/e2e/test_vision_live.py`
Domyślne `addopts = -m 'not live'` wyklucza ten plik z `uv run pytest`.
AC-17–AC-22, TAC-002-01..03.
"""

from __future__ import annotations

import contextlib
import io
import json
import os

import pandas as pd
import pytest

from map_qa import cli, config, store

pytestmark = [pytest.mark.live, pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="brak OPENROUTER_API_KEY")]
TH = config.load_thresholds()


def _run(out, db, *limits):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(["check", "--stage", "1", *limits, "--out", str(out), "--db", str(db)])
    dirs = sorted(p for p in out.iterdir() if p.is_dir())
    return code, dirs[-1]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    db = tmp_path_factory.mktemp("db") / "map_qa.db"
    limits = ["--decision-limit", "2", "--comparison-limit", "1", "--fallback-limit", "1", "--max-cost-usd", "0.05"]
    first = _run(out, db, *limits)
    second = _run(out, db, *limits)
    return first, second, db


def test_first_run_real_requests_within_limits(runs):  # AC-19, TAC-002-01
    (code, d), _, db = runs
    assert code == 0
    meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    usage = meta["usage"]
    assert usage[TH["vision"]["decision_model"]]["sent"] <= 2
    assert usage.get(TH["vision"]["comparison_model"], {"sent": 0})["sent"] <= 1
    assert usage.get(TH["vision"]["fallback_model"], {"sent": 0})["sent"] <= 1
    ledger = store.budget_usage(store.connect(db), meta["run_id"])
    assert {m: u["sent"] for m, u in ledger.items()} == {m: u["sent"] for m, u in usage.items()}
    assert 0 < meta["cost_total_usd"] <= 0.05  # TAC-002-03 (BYOK: koszt z upstream_inference_cost)


def test_readings_have_stage_and_closed_answers(runs):  # AC-18, AC-20f
    (_, d), _, _ = runs
    r = pd.read_parquet(d / "readings.parquet")
    assert len(r) == 2
    for row in r.to_dict("records"):
        assert row["final_stage"] in {"decision", "fallback", "manual"}
        if row["final_stage"] != "manual":
            assert row["answer"] in list(TH["questions"][row["question_id"]]["criteria"])


def test_rerun_uses_cache_no_new_requests(runs):  # AC-22
    _, (code, d2), _ = runs
    meta = json.loads((d2 / "run.json").read_text(encoding="utf-8"))
    assert code == 0 and meta["requests_total"] == 0
    assert pd.read_parquet(d2 / "readings.parquet")["cache_hit"].all()


def test_no_secrets_or_base64_in_run(runs):  # TAC-002-02, TAC-04
    (_, d), _, _ = runs
    key = os.environ["OPENROUTER_API_KEY"].encode()
    for p in d.rglob("*"):
        if p.is_file():
            b = p.read_bytes()
            assert key not in b and b"base64," not in b and b"sk-or-" not in b
