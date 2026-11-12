"""AC-09, TAC-001-03, D-101 i D-103 (wyzwalacze) na pełnych danych map-qa."""

from __future__ import annotations

import pytest

from map_qa import config, ingest, matching


@pytest.fixture(scope="module")
def assessment(data_dir):
    layers = ingest.load_layers(data_dir)
    th = config.load_thresholds()["links"]
    osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
    return matching.assess_links(layers.links, layers.photos, osm2180, th)


def test_three_disjoint_groups_sum_to_561(assessment):
    c = matching.link_counts(assessment)
    assert c["certain"] + c["uncertain"] + c["no_candidate"] == 561 == c["total"]
    assert c["no_candidate"] == 3
    assert c["uncertain"] >= 65
    assert c["missing_heading"] == 15


def test_recomputed_values_agree_with_input_d101(assessment):
    has = assessment[assessment["status"] != "no_candidate"]
    mismatch = has["reasons"].map(lambda r: "link_distance_mismatch" in r or "link_bearing_mismatch" in r)
    assert mismatch.mean() <= 0.05, has.loc[mismatch, ["photo_id", "distance_m_input", "distance_m", "bearing_diff_input", "bearing_diff"]].head(10)


def test_restricted_access_share_below_d103_trigger(assessment):
    has = assessment[assessment["status"] != "no_candidate"]
    assert has["reasons"].map(lambda r: "restricted_access" in r).mean() <= 0.5
