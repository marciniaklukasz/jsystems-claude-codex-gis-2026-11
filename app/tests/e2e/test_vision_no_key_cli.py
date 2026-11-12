"""E2E bez mocków: limit > 0 bez OPENROUTER_API_KEY → kod 0, manifest przed żądaniami, 0 żądań, model_unavailable.

ADR-002 §8 (wiersz „Rzeczywista próba”, przypadek brzegowy „brak klucza”), AC-19c, AC-20d, AC-20e, AC-21, AC-23, AC-26.
"""

from __future__ import annotations

import contextlib
import io
import json
import socket

import pandas as pd
import pytest

from map_qa import cli


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    db = tmp_path_factory.mktemp("db") / "map_qa.db"
    mp = pytest.MonkeyPatch()
    mp.delenv("OPENROUTER_API_KEY", raising=False)

    def no_network(*a, **k):
        raise AssertionError("połączenie sieciowe bez klucza")

    mp.setattr(socket.socket, "connect", no_network)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(["check", "--stage", "1", "--decision-limit", "25", "--comparison-limit", "5", "--fallback-limit", "10",
                         "--max-cost-usd", "1", "--out", str(out), "--db", str(db)])
    mp.undo()
    d = [p for p in out.iterdir() if p.is_dir()][0]
    return code, d, buf.getvalue()


def test_exit_0_and_manifest(run):
    code, d, _ = run
    assert code == 0
    m = pd.read_csv(d / "sample_manifest.csv", dtype=str)
    assert len(m) == 25 and (m["question_id"] == "speed_limit_value").sum() == 13 and (m["question_id"] == "surface").sum() == 12
    assert m.groupby("sequence")["split"].nunique().max() == 1


def test_readings_manual_model_unavailable_and_summary(run):
    _, d, _ = run
    r = pd.read_parquet(d / "readings.parquet")
    assert len(r) == 25 and set(r["final_stage"]) == {"manual"} and set(r["status"]) == {"model_unavailable"}
    meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    assert meta["requests_total"] == 0
    assert any(x["source"] == "OpenRouter" and "OPENROUTER_API_KEY" in x["reason"] for x in meta["limitations"])
    vs = meta["vision_summary"]
    assert vs["surface"]["manual"] == vs["surface"]["total"] == 12  # AC-20e: suma = liczba odczytów
    ev = meta["evaluation"]["speed_limit_value"]
    assert ev["pairs"] == 13 and "uncertain_labels_excluded" in ev  # AC-23
    row = next(x for x in ev["rows"] if x["who"] == "after_escalation" and x["split"] == "all")
    assert row["coverage"] == 0 and row["accuracy"] is None  # 0 pewnych → „brak danych”, nie 0


def test_report_shows_stage_and_attribution_of_sample_photos(run):
    _, d, _ = run
    md = (d / "report.md").read_text(encoding="utf-8")
    assert "kolejka ręczna" in md and "Trafność" in md
    meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    m = pd.read_csv(d / "sample_manifest.csv", dtype=str)
    for pid in m["photo_id"]:
        a = meta["photo_attribution"][pid]
        assert a["author"] and a["license"] and a["source_url"]  # AC-25
