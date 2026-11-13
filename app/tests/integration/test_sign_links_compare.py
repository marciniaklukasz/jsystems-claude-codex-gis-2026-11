"""R-F (Codex P1): zdjęcia `signs/` z połączeniem do drogi są dowodem prędkości (ADR-001 §3.4), ale nie wchodzą do AC-09."""

from __future__ import annotations

import pandas as pd
import pytest

from map_qa import compare, config, ingest, matching


@pytest.fixture(scope="module")
def built(data_dir):
    layers = ingest.load_layers(data_dir)
    th = config.load_thresholds()
    osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
    a = matching.assess_links(layers.links, layers.photos, osm2180, th["links"])
    signs = pd.read_csv(data_dir / "signs" / "signs.csv", encoding="utf-8")
    near = pd.read_csv(data_dir / "signs" / "nearest_osm.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    sl = matching.assess_sign_links(near, signs, osm2180, th["links"])
    sign_ids = set(sl.loc[sl["status"].isin(["certain", "uncertain"]), "photo_id"]) - set(layers.photos["photo_id"])
    # odczyt pewny 999 km/h dla każdego zdjęcia znaku — musi pojawić się jako dowód (rozbieżne) przy połączeniu pewnym
    readings = pd.DataFrame([{"photo_id": p, "question_id": "speed_limit_value", "status": "certain", "answer": "130",
                              "final_stage": "decision"} for p in sign_ids])
    cand, excl = compare.build_candidates(layers, a, readings, 1, th, "r", sign_links=sl)
    return sl, sign_ids, cand, excl


def test_sign_photos_attached_to_speed_pairs_only(built):
    sl, sign_ids, cand, _ = built
    with_sign = cand[cand["photo_ids"].map(lambda ids: bool(set(ids) & sign_ids))]
    assert len(with_sign) > 0
    assert set(with_sign["attribute"]) == {"speed"}


def test_certain_sign_reading_is_evidence(built):
    sl, sign_ids, cand, _ = built
    certain_ways = set(sl.loc[(sl["status"] == "certain") & sl["photo_id"].isin(sign_ids), "osm_way_id"].astype(int))
    hit = cand[(cand["attribute"] == "speed") & cand["osm_id"].isin(certain_ways) & (cand["osm_status"] == "value")]
    assert (hit["category"] == "rozbieżne").any()
    assert hit["reason_text"].str.contains("zdjęcie mapillary_").any()


def test_evaluation_only_signs_never_in_candidates(built):
    sl, _, cand, _ = built
    ev = set(sl.loc[sl["status"] == "evaluation_only", "photo_id"])
    assert not any(set(ids) & ev for ids in cand["photo_ids"])


def test_ac09_counts_unchanged(built):
    _, _, _, excl = built
    assert excl[compare.EXCL_NO_CANDIDATE] == 3
