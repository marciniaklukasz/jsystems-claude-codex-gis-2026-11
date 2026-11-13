"""E2E etapu 1 bez modeli na prawdziwych plikach map-qa (bez mocków).

AC-01, AC-03, AC-04, AC-05, AC-09, AC-16, AC-21, AC-24, AC-26; TAC-01..TAC-04; ADR-000 §6, §9.3.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import socket
import time
from pathlib import Path

import pandas as pd
import pytest

from map_qa import cli, config, ingest

SECRET_OR = "sk-or-test-SECRET-VALUE-123"
SECRET_DB = "dapi-test-SECRET-VALUE-456"


@pytest.fixture(scope="module")
def run(tmp_path_factory, data_dir):
    out = tmp_path_factory.mktemp("runs")
    db = tmp_path_factory.mktemp("db") / "map_qa.db"
    before = {f["name"]: f["sha256"] for f in ingest.verify_inputs(data_dir)}

    mp = pytest.MonkeyPatch()
    mp.setenv("OPENROUTER_API_KEY", SECRET_OR)  # TAC-04: znane wartości testowe
    mp.setenv("DATABRICKS_TOKEN", SECRET_DB)

    def no_network(*a, **k):
        raise AssertionError("połączenie sieciowe w kontroli bez budżetu")

    mp.setattr(socket.socket, "connect", no_network)
    mp.setattr(socket, "create_connection", no_network)
    t0 = time.monotonic()
    import contextlib

    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        code = cli.main(["check", "--stage", "1", "--out", str(out), "--db", str(db)])
    elapsed = time.monotonic() - t0
    mp.undo()
    after = {f["name"]: f["sha256"] for f in ingest.verify_inputs(data_dir)}
    run_dirs = [p for p in out.iterdir() if p.is_dir()]
    return {"code": code, "stdout": buf_out.getvalue(), "stderr": buf_err.getvalue(), "elapsed": elapsed,
            "out": out, "run_dirs": run_dirs, "before": before, "after": after, "db": db}


def test_exit_0_within_5_minutes(run):  # TAC-02
    assert run["code"] == 0, run["stderr"]
    assert run["elapsed"] < 300


def test_inputs_unchanged(run):  # AC-01, TAC-03
    assert run["before"] == run["after"]


def test_run_dir_contents(run):  # ADR-000 §6
    assert len(run["run_dirs"]) == 1
    d = run["run_dirs"][0]
    names = {p.name for p in d.iterdir()}
    assert {"report.md", "report.html", "candidates.csv", "candidates.parquet", "readings.parquet", "run.json"} <= names
    assert "sample_manifest.csv" not in names  # limity 0 → brak manifestu
    assert not [n for n in names if n.endswith(".tmp")]


def test_run_json_counts_and_limitations(run):  # AC-03, AC-05, AC-09
    r = json.loads((run["run_dirs"][0] / "run.json").read_text(encoding="utf-8"))
    assert r["input_counts"] == {"osm_roads": 99768, "overture_segments": 85405, "photos": 561, "traffic_signs": 1730}
    lc = r["link_counts"]
    assert lc["certain"] + lc["uncertain"] + lc["no_candidate"] == 561 and lc["no_candidate"] == 3
    srcs = {x["source"] for x in r["limitations"]}
    assert {"Databricks", "OpenRouter"} <= srcs
    assert r["crs"] == "EPSG:2180" and r["questions_version"] == config.load_thresholds()["vision"]["questions_version"]
    assert r["requests_total"] == 0 and r["cost_total_usd"] == 0
    assert r["thresholds_commit"]


def test_same_rows_in_three_formats(run):  # AC-24, TAC-003-01
    d = run["run_dirs"][0]
    cand = pd.read_parquet(d / "candidates.parquet")
    listed = cand[cand["category"] != "zgodne"]
    rows = list(csv.DictReader(io.StringIO((d / "candidates.csv").read_text(encoding="utf-8-sig"))))
    html = (d / "report.html").read_text(encoding="utf-8")
    assert len(rows) == len(listed) == html.count('<tr class="candidate"')


def test_no_budget_no_readings_model_unavailable(run):  # AC-21, ADR-000 §9.3
    d = run["run_dirs"][0]
    assert len(pd.read_parquet(d / "readings.parquet")) == 0
    cand = pd.read_parquet(d / "candidates.parquet")
    assert cand["reasons"].map(lambda r: "model_unavailable" in list(r)).any()


def test_stdout_summary(run):  # PRD §9.1
    s = re.sub(r"[\s ]", "", run["stdout"])
    assert "99768" in s and "zgodne" in s and "rozbieżne" in s and "dosprawdzenia" in s and "report.md" in s


def test_no_secrets_and_no_base64_in_run_dir(run):  # TAC-04, TAC-002-02
    for p in run["run_dirs"][0].rglob("*"):
        if p.is_file():
            b = p.read_bytes()
            assert SECRET_OR.encode() not in b and SECRET_DB.encode() not in b and b"base64," not in b
    assert SECRET_OR not in run["stdout"] + run["stderr"]


def test_run_recorded_in_store(run):
    from map_qa import store

    c = store.connect(run["db"])
    rid = run["run_dirs"][0].name
    assert store.get_run(c, rid)["status"] == "ok"


def test_every_candidate_photo_has_attribution(run):  # R-F P1, AC-25 (także pary „zgodne” i zdjęcia znaków)
    d = run["run_dirs"][0]
    meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    cand = pd.read_parquet(d / "candidates.parquet")
    ids = {p for ids in cand["photo_ids"] for p in ids}
    assert any(p.startswith("mapillary_") for p in ids)
    for pid in ids:
        a = meta["photo_attribution"][pid]
        assert a["author"] and a["license"] and a["source_url"], pid
