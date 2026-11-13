"""ADR-003 §3.1, §4, §5, §8; PRD AC-05, AC-14, AC-15, AC-16, AC-20e/f, AC-23–AC-26; TAC-003-01, TAC-002-03."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pandas as pd
import pytest

from map_qa import report


def _cand(i, category, attribute="speed", reasons=(), name="Ulica", photo_ids=(), stage=1):
    return {
        "candidate_id": f"c{i:04d}", "candidate_key": f"{100 + i}||{attribute}", "run_id": "R1", "stage": stage,
        "osm_id": 100 + i, "osm_url": f"https://www.openstreetmap.org/way/{100 + i}", "highway": "primary", "name": name,
        "overture_ids": ["ov-a"] if i % 2 else [], "attribute": attribute,
        "osm_raw": '{"maxspeed": "50"}', "overture_raw": '{"ov-a": [{"max_speed": {"value": 70, "unit": "km/h"}}]}',
        "osm_norm": "50", "overture_norm": "70", "osm_status": "value", "overture_status": "value",
        "photo_ids": list(photo_ids), "link_status": ["certain"] * len(photo_ids),
        "photo_reading": "brak odczytu modelu", "osm_timestamp": "2026-02-21 10:25:53+00:00",
        "osm_extract_date": "2026-11-01T21:21:36Z", "overture_release": "2026-10-21.0",
        "category": category, "reasons": list(reasons), "reason_text": "powód " + category,
    }


RUN = {
    "run_id": "R1", "stage": 1, "created_at": "2026-11-12T10:00:00Z", "crs": "EPSG:2180",
    "questions_version": 1, "thresholds_commit": "abc1234",
    "sources": [
        {"name": "OpenStreetMap (Geofabrik małopolskie)", "version": "extract", "date": "2026-11-01T21:21:36Z", "license": "ODbL-1.0"},
        {"name": "Overture Maps transportation", "version": "2026-10-21.0", "date": "2026-10-21", "license": "ODbL-1.0"},
        {"name": "Zdjęcia Panoramax/Mapillary", "version": "sources.json", "date": "2026-11-02T23:52:58Z", "license": "CC-BY-SA-4.0"},
    ],
    "input_counts": {"osm_roads": 99768, "overture_segments": 85405, "photos": 561, "traffic_signs": 1730},
    "link_counts": {"certain": 434, "uncertain": 124, "no_candidate": 3, "total": 561, "missing_heading": 15},
    "exclusions": {"ograniczenie prędkości: brak porównywalnego dowodu": 7, "zdjęcie: brak kandydata w promieniu": 3},
    "limitations": [
        {"source": "Databricks", "reason": "nie odpytywany w kontroli (D-02)"},
        {"source": "OpenRouter", "reason": "brak budżetu (limity 0)"},
    ],
    "limits": {"decision": 0, "comparison": 0, "fallback": 0, "max_cost_usd": 0.0},
    "usage": {}, "cost_total_usd": 0.0, "requests_total": 0,
    "vision_summary": {}, "evaluation": {},
    "photo_attribution": {
        "p1": {"author": "czecko", "license": "CC-BY-SA-4.0", "source_url": "https://panoramax.example/p1", "local_path": None},
    },
}


def make_run(tmp_path: Path, cands: list[dict], run: dict | None = None, readings: pd.DataFrame | None = None) -> Path:
    run_dir = tmp_path / "R1"
    run_dir.mkdir()
    pd.DataFrame(cands).to_parquet(run_dir / "candidates.parquet")
    (readings if readings is not None else pd.DataFrame(columns=["photo_id", "question_id", "final_stage", "model", "answer", "status", "reason"])).to_parquet(run_dir / "readings.parquet")
    (run_dir / "run.json").write_text(json.dumps(run or RUN, ensure_ascii=False), encoding="utf-8")
    return run_dir


def seven(tmp_path):
    cands = [_cand(i, c, reasons=r) for i, (c, r) in enumerate([
        ("zgodne", ()), ("zgodne", ()), ("zgodne", ()),
        ("rozbieżne", ()), ("do sprawdzenia", ("missing",)), ("do sprawdzenia", ("not_comparable",)),
        ("do sprawdzenia", ("model_unavailable",)),
    ])]
    return make_run(tmp_path, cands), cands


def test_three_formats_same_number_of_rows(tmp_path):  # AC-24, TAC-003-01
    run_dir, cands = seven(tmp_path)
    paths = report.write_report(run_dir)
    md = paths["md"].read_text(encoding="utf-8")
    html = paths["html"].read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(paths["csv"].read_text(encoding="utf-8-sig"))))
    listed = [c["candidate_id"] for c in cands if c["category"] != "zgodne"]
    assert len(rows) == 4 == len(listed)
    assert html.count('<tr class="candidate"') == 4
    assert sum(1 for line in md.splitlines() if line.startswith("| ") and any(cid in line for cid in listed)) == 4
    for cid in listed:
        assert cid in md and cid in html
    assert {r["candidate_id"] for r in rows} == set(listed)


def test_csv_utf8_bom_and_lists_as_json(tmp_path):
    run_dir, _ = seven(tmp_path)
    p = report.write_report(run_dir)["csv"]
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig"))))
    assert json.loads(rows[0]["reasons"]) is not None
    assert isinstance(json.loads(rows[0]["overture_ids"]), list)


def test_order_rozbiezne_first_then_attribute_then_osm_id(tmp_path):
    run_dir, _ = seven(tmp_path)
    rows = list(csv.DictReader(io.StringIO(report.write_report(run_dir)["csv"].read_text(encoding="utf-8-sig"))))
    assert rows[0]["category"] == "rozbieżne"
    assert [int(r["osm_id"]) for r in rows[1:]] == sorted(int(r["osm_id"]) for r in rows[1:])


def test_html_escapes_untrusted_tags(tmp_path):  # ADR-003 §8 Escapowanie
    c = _cand(1, "rozbieżne", name='<script>alert(1)</script> & "x"')
    c["osm_raw"] = '{"name": "<script>alert(1)</script>"}'
    run_dir = make_run(tmp_path, [c])
    html = report.write_report(run_dir)["html"].read_text(encoding="utf-8")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_html_self_contained(tmp_path):
    run_dir, _ = seven(tmp_path)
    html = report.write_report(run_dir)["html"].read_text(encoding="utf-8")
    assert "<script src" not in html and "fonts.googleapis" not in html and "<link " not in html


def test_attribution_and_missing_photo(tmp_path):  # AC-25
    c = _cand(1, "do sprawdzenia", reasons=("model_unavailable",), photo_ids=["p1"])
    run_dir = make_run(tmp_path, [c])
    paths = report.write_report(run_dir)
    for fmt in ("md", "html"):
        t = paths[fmt].read_text(encoding="utf-8")
        assert "czecko" in t and "CC-BY-SA-4.0" in t and "https://panoramax.example/p1" in t
        assert "Zdjęcie niedostępne" in t


def test_thumbnail_relative_path_when_local_file_exists(tmp_path):
    img = tmp_path / "photos" / "p1.jpg"
    img.parent.mkdir()
    img.write_bytes(b"\xff\xd8\xff")
    run = json.loads(json.dumps(RUN))
    run["photo_attribution"]["p1"]["local_path"] = str(img)
    run_dir = make_run(tmp_path, [_cand(1, "rozbieżne", photo_ids=["p1"])], run)
    html = report.write_report(run_dir)["html"].read_text(encoding="utf-8")
    assert 'src="../photos/p1.jpg"' in html


def test_header_sources_versions_questions_crs(tmp_path):  # AC-04, AC-26
    run_dir, _ = seven(tmp_path)
    for p in report.write_report(run_dir).values():
        if p.suffix == ".csv":
            continue
        t = p.read_text(encoding="utf-8")
        assert "EPSG:2180" in t and "2026-10-21.0" in t and "2026-11-01T21:21:36Z" in t
        assert "Wersja pytań" in t and "abc1234" in t


def test_counts_limitations_exclusions(tmp_path):  # AC-03, AC-05, AC-08, AC-09, AC-16
    run_dir, _ = seven(tmp_path)
    for p in report.write_report(run_dir).values():
        if p.suffix == ".csv":
            continue
        t = p.read_text(encoding="utf-8").replace(" ", " ")
        assert "Ograniczenia" in t and "Databricks" in t and "nie odpytywany w kontroli (D-02)" in t and "OpenRouter" in t
        assert "99 768" in t and "85 405" in t and "561" in t and "1 730" in t
        assert "brak porównywalnego dowodu" in t and "brak kandydata w promieniu" in t
        assert "434" in t and "124" in t and "bez kierunku" in t


def test_summary_table_includes_zgodne_counts(tmp_path):
    run_dir, _ = seven(tmp_path)
    md = report.write_report(run_dir)["md"].read_text(encoding="utf-8")
    assert "zgodne" in md and "| ograniczenie prędkości | 3 | 1 | 3 |" in md


def test_never_labels_map_error(tmp_path):  # AC-14
    run_dir, _ = seven(tmp_path)
    for p in report.write_report(run_dir).values():
        assert "błąd mapy" not in p.read_text(encoding="utf-8-sig").lower()


def test_empty_state(tmp_path):
    run_dir = make_run(tmp_path, [_cand(1, "zgodne")])
    paths = report.write_report(run_dir)
    assert "Brak kandydatów dla wybranego etapu" in paths["md"].read_text(encoding="utf-8")
    assert "Brak kandydatów dla wybranego etapu" in paths["html"].read_text(encoding="utf-8")


def test_vision_sections_when_readings(tmp_path):  # AC-20e, AC-20f, AC-23, TAC-002-03
    run = json.loads(json.dumps(RUN))
    run["usage"] = {"typesafe/jev-1.14": {"sent": 3, "errors": 0, "cost_usd": 0.0012}, "openai/gpt-6-luna": {"sent": 1, "errors": 1, "cost_usd": 0.0}}
    run["cost_total_usd"] = 0.0012
    run["requests_total"] = 4
    run["vision_summary"] = {"surface": {"decision": 2, "fallback": 0, "manual": 1, "total": 3}}
    run["evaluation"] = {"surface": {"pairs": 3, "uncertain_labels_excluded": 4, "rows": [
        {"split": "validation", "who": "decision", "pairs": 3, "certain": 2, "correct": 2, "coverage": 0.667, "accuracy": 1.0}]}}
    readings = pd.DataFrame([{"photo_id": "p1", "question_id": "surface", "final_stage": "decision", "model": "typesafe/jev-1.14",
                              "answer": "paved", "status": "certain", "reason": ""}])
    run_dir = make_run(tmp_path, [_cand(1, "rozbieżne")], run, readings)
    for p in report.write_report(run_dir).values():
        if p.suffix == ".csv":
            continue
        t = p.read_text(encoding="utf-8")
        assert "typesafe/jev-1.14" in t and "0.0012" in t
        assert "model decyzyjny" in t and "kolejka ręczna" in t
        assert "Trafność" in t and "pokrycie" in t.lower()
        assert "decision" in t  # stopień przy odczycie (AC-20f)


def test_no_partial_report_on_render_error(tmp_path, monkeypatch):  # ADR-003 §8
    run_dir, _ = seven(tmp_path)
    monkeypatch.setattr(report, "_render_html", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        report.write_report(run_dir)
    assert not any((run_dir / n).exists() for n in ("report.md", "report.html", "candidates.csv"))
    assert not list(run_dir.glob("*.tmp"))


def test_verify_callback_failure_leaves_no_report(tmp_path):  # AC-01, ADR-000 §6
    run_dir, _ = seven(tmp_path)

    class Integrity(Exception):
        pass

    def verify():
        raise Integrity("photos.csv")

    with pytest.raises(Integrity):
        report.write_report(run_dir, verify=verify)
    assert not any((run_dir / n).exists() for n in ("report.md", "report.html", "candidates.csv"))
    assert not list(run_dir.glob("*.tmp"))


def test_missing_run_file_raises(tmp_path):
    run_dir, _ = seven(tmp_path)
    (run_dir / "run.json").unlink()
    with pytest.raises(FileNotFoundError):
        report.write_report(run_dir)


def test_photo_href_other_drive_falls_back_to_file_uri(monkeypatch, tmp_path):
    import os as _os

    def boom(*a, **k):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    img = tmp_path / "p.jpg"
    img.write_bytes(b"x")
    monkeypatch.setattr(_os.path, "relpath", boom)
    assert report._photo_href(str(img), tmp_path / "run").startswith("file:///")


def test_md_table_cells_escape_pipes_and_newlines(tmp_path):  # R-A: prawdziwa wartość z drogi 140855412
    c = _cand(1, "rozbieżne")
    c["osm_raw"] = '{"maxspeed": "120", "maxspeed:lanes": "120|120|120|80"}'
    c["reason_text"] = "linia1\nlinia2"
    md = report.write_report(make_run(tmp_path, [c]))["md"].read_text(encoding="utf-8")
    row = next(line for line in md.splitlines() if "c0001" in line)
    header = next(line for line in md.splitlines() if line.startswith("| kategoria"))
    unescaped = row.replace("\|", "")
    assert unescaped.count("|") == header.count("|")
    assert "120\|120\|120\|80" in row


def test_link_details_shown(tmp_path):  # R-A: LinkAssessment przy kandydacie
    c = _cand(1, "do sprawdzenia", reasons=("ambiguous_link",), photo_ids=["p1"])
    c["link_details"] = ["p1: niepewne, 5.2 m, różnica kierunku 87.9°, przyczyny: bearing_gt_threshold"]
    paths = report.write_report(make_run(tmp_path, [c]))
    for fmt in ("md", "html"):
        assert "różnica kierunku 87.9°" in paths[fmt].read_text(encoding="utf-8")


def test_vision_summary_shown_even_without_requests(tmp_path):  # AC-20e: brak klucza → wszystkie w kolejce ręcznej
    run = json.loads(json.dumps(RUN))
    run["vision_summary"] = {"surface": {"decision": 0, "fallback": 0, "manual": 12, "total": 12}}
    for p in report.write_report(make_run(tmp_path, [_cand(1, "rozbieżne")], run)).values():
        if p.suffix != ".csv":
            t = p.read_text(encoding="utf-8")
            assert "kolejka ręczna" in t and "Brak wywołań modelu w tej kontroli." in t


def test_md_candidate_table_header_and_separator_same_width(tmp_path):  # R-F: tabela GFM
    md = report.write_report(make_run(tmp_path, [_cand(1, "rozbieżne")]))["md"].read_text(encoding="utf-8").splitlines()
    i = next(n for n, line in enumerate(md) if line.startswith("| kategoria"))
    assert md[i].count("|") == md[i + 1].count("|")
