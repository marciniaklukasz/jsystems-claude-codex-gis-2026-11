"""E2E etapu 2 na prawdziwych plikach (bez mocków): AC-32, P4 (nadzbiór etapu 1), ADR-000 §6."""

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
    mp.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sieć")))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(["check", "--stage", "2", "--out", str(out), "--db", str(db)])
    mp.undo()
    return code, [p for p in out.iterdir() if p.is_dir()][0], buf.getvalue()


def test_exit_0(run):
    assert run[0] == 0


def test_all_four_attributes_and_summary(run):
    _, d, stdout = run
    c = pd.read_parquet(d / "candidates.parquet")
    assert set(c["attribute"]) == {"speed", "surface", "lit", "junction"}
    meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    assert meta["stage"] == 2 and set(meta["summary"]) == {"speed", "surface", "lit", "junction"}
    md = (d / "report.md").read_text(encoding="utf-8")
    assert "| oświetlenie |" in md and "| skrzyżowanie |" in md
    assert "oświetlenie" in stdout and "skrzyżowanie" in stdout


def test_stage1_pairs_included(run):  # P4
    _, d, _ = run
    c = pd.read_parquet(d / "candidates.parquet")
    s1 = c[c["attribute"].isin(["speed", "surface"])]
    assert (s1["category"] == "rozbieżne").sum() == 26  # jak w runie etapu 1 (24 + 2)
