"""Pełne dane, etap 1 bez modelu: AC-10, AC-16, TAC-001-01, TAC-001-04, PRD §4.4 (model_unavailable)."""

from __future__ import annotations

import json

import pytest

from map_qa import compare, config, ingest, matching, normalize


@pytest.fixture(scope="module")
def result(data_dir):
    layers = ingest.load_layers(data_dir)
    th = config.load_thresholds()
    osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
    a = matching.assess_links(layers.links, layers.photos, osm2180, th["links"])
    cand, excl = compare.build_candidates(layers, a, None, 1, th, "test-run")
    return layers, cand, excl


def test_every_pair_is_candidate_or_counted_exclusion(result):  # AC-16
    layers, cand, excl = result
    pair_excl = sum(v for k, v in excl.items() if not k.startswith("zdjęcie"))
    assert len(cand) + pair_excl == len(layers.osm) * 2
    assert excl[compare.EXCL_NO_CANDIDATE] == 3


def test_categories_and_reasons_closed(result):  # AC-10, AC-10a
    _, cand, _ = result
    assert set(cand["category"]) <= {"zgodne", "rozbieżne", "do sprawdzenia"}
    q = cand[cand["category"] == "do sprawdzenia"]
    assert q["reasons"].map(len).min() >= 1
    assert set(r for rs in q["reasons"] for r in rs) <= set(compare.REASONS)
    assert cand[cand["category"] != "do sprawdzenia"]["reasons"].map(len).max() == 0


def test_raw_values_identical_to_input(result):  # TAC-001-01
    layers, cand, _ = result
    tags = dict(zip(layers.osm["osm_id"], layers.osm["tags_dict"]))
    ov = layers.overture.set_index("id")
    sample = cand[cand["attribute"] == "speed"].head(300)
    for r in sample.itertuples():
        expected = {k: v for k, v in tags[r.osm_id].items() if k.startswith("maxspeed")}
        assert json.loads(r.osm_raw) == expected
        for sid, rules in json.loads(r.overture_raw).items():
            assert rules == json.loads(normalize.to_json(ov.loc[sid, "speed_limits"]))


def test_multi_rule_overture_never_decides_without_model(result):  # TAC-001-04
    _, cand, _ = result
    nc = cand[(cand["attribute"] == "speed") & (cand["overture_status"] == "not_comparable") & (cand["osm_status"] == "value")]
    assert len(nc) > 0
    # bez odczytu modelu jedynym możliwym dowodem byłoby Overture, a ono jest nieporównywalne
    assert set(nc["category"]) == {"do sprawdzenia"}


def test_no_budget_photo_sole_evidence_model_unavailable(result):  # PRD §4.4, ADR-000 §9.3
    _, cand, _ = result
    assert cand["reasons"].map(lambda r: "model_unavailable" in r).sum() > 0
    assert (cand["photo_reading"] == "brak odczytu modelu").all()


def test_missing_attribute_only_for_major_roads(result):  # AC-13
    _, cand, _ = result
    m = cand[cand["reasons"].map(lambda r: "missing" in r)]
    assert set(m["highway"]) <= set(config.load_thresholds()["compare"]["missing_classes"])
    assert m["reason_text"].str.contains("brak atrybutu").all()
