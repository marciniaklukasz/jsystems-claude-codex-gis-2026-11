"""ADR-000 §6: walidacja flag, kody wyjścia 0/1/2, brak częściowego raportu (AC-02, AC-01)."""

from __future__ import annotations

import re

import pytest

from map_qa import cli, ingest


def _digits(text: str) -> str:
    return re.sub(r"[\s ]", "", text)


@pytest.mark.parametrize(
    "args",
    [
        ["check", "--stage", "3"],
        ["check"],
        ["check", "--stage", "1", "--decision-limit", "26", "--max-cost-usd", "1"],
        ["check", "--stage", "1", "--comparison-limit", "6", "--max-cost-usd", "1"],
        ["check", "--stage", "1", "--fallback-limit", "11", "--max-cost-usd", "1"],
        ["check", "--stage", "1", "--decision-limit", "2", "--max-cost-usd", "0"],
        ["check", "--stage", "1", "--decision-limit", "-1"],
    ],
)
def test_invalid_arguments_exit_2_before_loading(args, tmp_path, capsys, monkeypatch):
    def boom(*a, **k):  # dane nie mogą być wczytane przed walidacją
        raise AssertionError("verify_inputs called before validation")

    monkeypatch.setattr(ingest, "verify_inputs", boom)
    code = cli.main(args + ["--data-dir", str(tmp_path / "nope"), "--out", str(tmp_path / "out")])
    assert code == 2
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("report.md"))


def test_changed_byte_exit_1_no_report(data_copy, tmp_path, capsys):
    p = data_copy / "photos.csv"
    raw = bytearray(p.read_bytes())
    raw[50] ^= 0x01
    p.write_bytes(bytes(raw))
    out = tmp_path / "out"
    code = cli.main(["check", "--stage", "1", "--data-dir", str(data_copy), "--out", str(out), "--db", str(tmp_path / "t.db")])
    captured = capsys.readouterr()
    assert code == 1
    assert "photos.csv" in captured.err + captured.out
    assert not list(out.rglob("report.md")) if out.exists() else True


def test_post_run_hash_check_exit_1_no_report(data_copy, tmp_path, capsys, monkeypatch):
    original = ingest.load_layers

    def load_and_corrupt(data_dir, *a, **k):
        layers = original(data_dir, *a, **k)
        p = data_copy / "reference_labels.csv"
        raw = bytearray(p.read_bytes())
        raw[10] ^= 0x01
        p.write_bytes(bytes(raw))
        return layers

    monkeypatch.setattr(ingest, "load_layers", load_and_corrupt)
    out = tmp_path / "out"
    code = cli.main(["check", "--stage", "1", "--data-dir", str(data_copy), "--out", str(out), "--db", str(tmp_path / "t.db")])
    captured = capsys.readouterr()
    assert code == 1
    assert "reference_labels.csv" in captured.err + captured.out
    assert not out.exists() or not list(out.rglob("report.*"))


def test_check_stage1_counts_exit_0(data_dir, tmp_path, capsys):
    code = cli.main(["check", "--stage", "1", "--out", str(tmp_path / "out"), "--db", str(tmp_path / "t.db")])
    out = _digits(capsys.readouterr().out)
    assert code == 0
    assert "99768" in out and "85405" in out and "561" in out and "1730" in out
