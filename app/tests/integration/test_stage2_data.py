"""Etap 2 na pełnych danych bez modelu: AC-32, P4 (run etapu 2 = nadzbiór etapu 1), AC-10, AC-16; ADR-001 §3.5 „Zakres par”."""

from __future__ import annotations

import pytest

from map_qa import compare, config, ingest, matching


@pytest.fixture(scope="module")
def runs(data_dir):
    layers = ingest.load_layers(data_dir)
    th = config.load_thresholds()
    osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
    a = matching.assess_links(layers.links, layers.photos, osm2180, th["links"])
    pts = matching.photo_points_2180(layers.photos)
    c1, e1 = compare.build_candidates(layers, a, None, 1, th, "r1", osm_2180=osm2180, photo_points=pts)
    c2, e2 = compare.build_candidates(layers, a, None, 2, th, "r2", osm_2180=osm2180, photo_points=pts)
    return layers, a, c1, e1, c2, e2


def test_stage2_is_superset_of_stage1(runs):  # P4
    _, _, c1, _, c2, _ = runs
    s1 = c2[c2["attribute"].isin(["speed", "surface"])]
    assert len(s1) == len(c1)
    assert sorted(s1["candidate_key"]) == sorted(c1["candidate_key"])
    assert set(c2["attribute"]) == {"speed", "surface", "lit", "junction"}


def test_lit_and_junction_only_for_photo_linked_ways(runs):
    _, a, _, _, c2, e2 = runs
    linked = set(a.loc[a["status"].isin(["certain", "uncertain"]), "osm_way_id"].astype(int))
    s2 = c2[c2["attribute"].isin(["lit", "junction"])]
    assert set(s2["osm_id"]) <= linked
    excl = sum(v for k, v in e2.items() if k.startswith(("oświetlenie", "skrzyżowanie")))
    assert len(s2) + excl == 2 * len(linked)  # AC-16: każda para kandydatem albo wykluczeniem


def test_stage2_without_model_never_decides_from_photo(runs):  # AC-10a, PRD §4.4
    _, _, _, _, c2, _ = runs
    s2 = c2[c2["attribute"].isin(["lit", "junction"])]
    assert set(s2["category"]) == {"do sprawdzenia"}
    assert set(r for rs in s2["reasons"] for r in rs) <= {"model_unavailable", "ambiguous_link", "not_comparable", "missing"}


def test_junction_bridge_or_tunnel_not_comparable_present(runs):  # ADR-001 §4.4
    layers, _, _, _, c2, _ = runs
    j = c2[(c2["attribute"] == "junction") & c2["reasons"].map(lambda r: "not_comparable" in r)]
    tags = dict(zip(layers.osm["osm_id"], layers.osm["tags_dict"]))
    for oid in j["osm_id"]:
        t = tags[oid]
        assert t.get("bridge") not in (None, "no") or t.get("tunnel") not in (None, "no") or t.get("layer", "0") != "0" \
            or layers.osm.loc[layers.osm["osm_id"] == oid, "boundary_crossing"].iloc[0], oid
