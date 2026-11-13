"""ADR-003 §3.2–3.3, §5; PRD AC-14, AC-25, AC-27–AC-30; P4 (etap = etap atrybutu)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from map_qa import dashboard_data as dd
from map_qa import store


def _cand(i, attribute, category, reasons=(), photo_ids=(), link_status=()):
    stage = {"speed": 1, "surface": 1, "lit": 2, "junction": 2}[attribute]
    return {"candidate_id": f"c{i}", "candidate_key": f"{100 + i}||{attribute}", "run_id": "20261112T100000Z-aaaaaa", "stage": stage,
            "osm_id": 100 + i, "osm_url": f"https://www.openstreetmap.org/way/{100 + i}", "highway": "primary", "name": f"Ulica {i}",
            "overture_ids": [], "attribute": attribute, "osm_raw": '{"maxspeed": "50"}', "overture_raw": "{}", "osm_norm": "50",
            "overture_norm": "70", "osm_status": "value", "overture_status": "value", "photo_ids": list(photo_ids),
            "link_status": list(link_status), "photo_reading": "brak odczytu modelu", "osm_timestamp": "2026-02-21",
            "osm_extract_date": "2026-11-01T21:21:36Z", "overture_release": "2026-10-21.0", "category": category,
            "reasons": list(reasons), "reason_text": "powód"}


CANDS = [
    _cand(1, "speed", "rozbieżne"), _cand(2, "speed", "do sprawdzenia", ["missing"]), _cand(3, "surface", "zgodne"),
    _cand(4, "lit", "do sprawdzenia", ["model_unavailable"], ["p1"], ["certain"]), _cand(5, "junction", "rozbieżne", [], ["p2"], ["uncertain"]),
]
RUN = {"run_id": "20261112T100000Z-aaaaaa", "stage": 2, "created_at": "2026-11-12T10:00:00Z",
       "photo_attribution": {"p1": {"author": "czecko", "license": "CC-BY-SA-4.0", "source_url": "https://panoramax.example/p1", "local_path": None}}}


def make_run(root: Path, run_id=RUN["run_id"], cands=CANDS) -> Path:
    d = root / run_id
    d.mkdir(parents=True)
    pd.DataFrame(cands).to_parquet(d / "candidates.parquet")
    pd.DataFrame([{"photo_id": "p1", "question_id": "street_lighting_visible", "final_stage": "fallback", "model": "openai/gpt-6-luna",
                   "answer": "yes", "status": "certain", "reason": ""}]).to_parquet(d / "readings.parquet")
    (d / "run.json").write_text(json.dumps({**RUN, "run_id": run_id}, ensure_ascii=False), encoding="utf-8")
    return d


def test_latest_run_by_run_id_ignores_partial(tmp_path):
    make_run(tmp_path, "20261112T100000Z-aaaaaa")
    make_run(tmp_path, "20261112T120000Z-bbbbbb")
    (tmp_path / ".20261112T130000Z-cccccc.partial").mkdir()
    assert dd.latest_run(tmp_path).name == "20261112T120000Z-bbbbbb"
    assert dd.latest_run(tmp_path / "missing") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert dd.latest_run(empty) is None


def test_load_run(tmp_path):
    data = dd.load_run(make_run(tmp_path))
    assert data.run["run_id"] == RUN["run_id"] and len(data.candidates) == 5 and len(data.readings) == 1
    assert isinstance(data.candidates.iloc[0]["reasons"], list)


@pytest.mark.parametrize(
    "kwargs, expected",
    [({}, 5), ({"categories": ["rozbieżne"]}, 2), ({"attributes": ["speed"]}, 2), ({"stages": [2]}, 2),
     ({"stages": [1], "categories": ["do sprawdzenia"]}, 1), ({"reasons": ["missing"]}, 1)],
)
def test_filters(kwargs, expected):  # AC-27, P4
    df = pd.DataFrame(CANDS)
    assert len(dd.filter_candidates(df, **kwargs)) == expected


def test_review_table_polish_labels_and_no_map_error_without_decision():  # AC-14
    t = dd.review_table(pd.DataFrame(CANDS), {})
    assert list(t.columns)[:4] == ["kategoria", "atrybut", "etap", "OSM id"]
    assert set(t["atrybut"]) == {"ograniczenie prędkości", "nawierzchnia", "oświetlenie", "skrzyżowanie"}
    assert "błąd mapy" not in t.to_string()
    t2 = dd.review_table(pd.DataFrame(CANDS), {"101||speed": {"decision": "confirmed_error", "author": "anna", "decided_at": "2026-11-12T11:00:00Z", "proposed_value": "70", "comment": ""}})
    assert t2.iloc[0]["decyzja"] == "potwierdzony błąd mapy" and t2.iloc[0]["autor"] == "anna"


def test_detail_shows_sources_dates_photo_attribution_link_and_reading(tmp_path):  # PRD §9.3, AC-20f, AC-25
    data = dd.load_run(make_run(tmp_path))
    row = data.candidates[data.candidates["candidate_id"] == "c4"].iloc[0]
    det = dd.candidate_detail(row, data)
    assert det["osm"]["date"] == "2026-02-21" and det["overture"]["release"] == "2026-10-21.0"
    ph = det["photos"][0]
    assert ph["caption"] == "czecko · CC-BY-SA-4.0 · https://panoramax.example/p1"
    assert ph["image_bytes"] is None and ph["unavailable_text"] == "Zdjęcie niedostępne"
    assert ph["link_text"] == "połączenie pewne"
    assert ph["reading"] == "yes (stopień: drugi stopień, openai/gpt-6-luna)"
    row5 = data.candidates[data.candidates["candidate_id"] == "c5"].iloc[0]
    d5 = dd.candidate_detail(row5, data)
    assert d5["photos"][0]["link_text"] == "połączenie niepewne"
    assert d5["photos"][0]["reading"] == "brak odczytu modelu"


def test_photo_bytes_only_from_local_file(tmp_path):  # AC-30
    p = tmp_path / "x.jpg"
    p.write_bytes(b"\xff\xd8\xffdata")
    assert dd.photo_bytes(str(p)) == b"\xff\xd8\xffdata"
    assert dd.photo_bytes("https://example.com/x.jpg") is None
    assert dd.photo_bytes(None) is None


def test_to_fix_only_confirmed_with_osm_link_and_proposed(tmp_path):  # AC-29, ADR-003 §5 list_confirmed
    conn = store.connect(tmp_path / "t.db")
    store.save_decision(conn, "101||speed", "confirmed_error", "70", "znak 70", "anna", "R1")
    store.save_decision(conn, "102||speed", "no_error", None, "", "anna", "R1")
    store.save_decision(conn, "999||speed", "confirmed_error", "30", "", "jan", "R0")
    data = dd.load_run(make_run(tmp_path / "runs"))
    t = dd.to_fix(data, store.list_confirmed(conn))
    assert len(t) == 2
    first = t[t["OSM"] == "https://www.openstreetmap.org/way/101"].iloc[0]
    assert first["wartość proponowana"] == "70" and first["obecna wartość"] == "50" and first["komentarz"] == "znak 70"
    gone = t[t["OSM"] == "https://www.openstreetmap.org/way/999"].iloc[0]
    assert gone["uwagi"] == "brak w bieżącym runie"


def test_to_fix_photos_local_only(tmp_path):  # R-F (Codex P2): zdjęcie w zakładce „Do poprawy”
    conn = store.connect(tmp_path / "t.db")
    store.save_decision(conn, "104||lit", "confirmed_error", "yes", "lampa", "anna", "R1")
    data = dd.load_run(make_run(tmp_path / "runs"))
    items = dd.to_fix_photos(data, store.list_confirmed(conn))
    assert len(items) == 1 and items[0]["photo_id"] == "p1"
    assert items[0]["image_bytes"] is None and items[0]["caption"] == "czecko · CC-BY-SA-4.0 · https://panoramax.example/p1"
    assert "104" in items[0]["label"]


def test_streamlit_config_hides_deploy_toolbar():  # AC-30: brak akcji wysyłających do usług zewnętrznych
    import tomllib
    cfg = tomllib.loads((Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["client"]["toolbarMode"] == "viewer" and cfg["browser"]["gatherUsageStats"] is False
