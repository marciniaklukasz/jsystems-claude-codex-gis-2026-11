"""ADR-001 §3.3, §3.5, §4.4, §8 (Kategoria, Most/tunel); AC-07, AC-10, AC-10a, AC-11, AC-12, AC-13, AC-16; P1, P2."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from map_qa import compare as cp
from map_qa.normalize import Normalized

MISSING_CLASSES = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
                   "secondary", "secondary_link", "tertiary", "tertiary_link"]
REASONS = {"missing", "not_comparable", "ambiguous_link", "abstain", "model_unavailable"}


def V(v):
    return Normalized("value", v, "numeric", json.dumps(v))


MISSING = Normalized("missing", None, "missing", "{}")
NC = Normalized("not_comparable", None, "conditional", '{"maxspeed:conditional": "x"}')


def photo(value=None, link="certain", reading="certain", pid="p1"):
    return cp.PhotoEvidence(photo_id=pid, link_status=link, reading_status=reading, value=value, stage="decision" if reading == "certain" else None)


def cat(attribute="speed", highway="primary", osm=V(50), overture=None, photos=()):
    return cp.categorize(attribute, highway, osm, overture, list(photos), MISSING_CLASSES)


# Tabela §8 „Kategoria”
def test_osm_equals_overture_zgodne():
    r = cat(overture=V(50))
    assert (r.category, r.reasons, r.exclusion) == ("zgodne", [], None)


def test_osm_differs_from_overture_rozbiezne():
    r = cat(overture=V(70))
    assert r.category == "rozbieżne"


def test_no_comparable_evidence_is_exclusion_not_zgodne():  # P1, AC-16
    r = cat(overture=None)
    assert r.category is None and r.exclusion == "brak porównywalnego dowodu"


def test_ambiguous_photo_sole_evidence_do_sprawdzenia_even_if_reading_certain():  # AC-07
    r = cat(overture=None, photos=[photo(70, link="uncertain")])
    assert r.category == "do sprawdzenia" and r.reasons == ["ambiguous_link"]


def test_osm_overture_differ_with_ambiguous_photo_stays_rozbiezne():  # P2
    r = cat(overture=V(70), photos=[photo(50, link="uncertain")])
    assert r.category == "rozbieżne"


def test_photo_never_makes_rozbiezne_when_link_uncertain():  # AC-07
    r = cat(overture=V(50), photos=[photo(70, link="uncertain")])
    assert r.category == "zgodne"


def test_certain_photo_reading_differs_rozbiezne():
    r = cat(overture=None, photos=[photo(70)])
    assert r.category == "rozbieżne"


def test_certain_photo_equal_zgodne():
    assert cat(overture=None, photos=[photo(50)]).category == "zgodne"


def test_no_budget_photo_sole_evidence_model_unavailable():  # PRD §4.4
    r = cat(overture=None, photos=[photo(None, reading="model_unavailable")])
    assert r.category == "do sprawdzenia" and r.reasons == ["model_unavailable"]


def test_abstain_reason():
    r = cat(overture=None, photos=[photo(None, reading="abstain")])
    assert r.reasons == ["abstain"]


def test_speed_reading_none_is_not_evidence():
    r = cat(overture=None, photos=[photo("none")])
    assert r.exclusion == "brak porównywalnego dowodu"


def test_speed_reading_unreadable_is_abstain():
    assert cat(overture=None, photos=[photo("unreadable")]).reasons == ["abstain"]


def test_missing_osm_tertiary_plus_missing():  # AC-13
    r = cat(osm=MISSING, highway="tertiary_link", overture=V(50))
    assert r.category == "do sprawdzenia" and r.reasons == ["missing"]
    assert "brak atrybutu" in r.reason_text


def test_missing_osm_below_tertiary_exclusion():  # P1
    r = cat(osm=MISSING, highway="residential", overture=V(50))
    assert r.category is None and r.exclusion == "brak wartości poniżej tertiary"


def test_osm_not_comparable_do_sprawdzenia():  # AC-12
    r = cat(osm=NC, overture=V(50))
    assert r.category == "do sprawdzenia" and r.reasons == ["not_comparable"]


def test_overture_not_comparable_sole_evidence_do_sprawdzenia():
    r = cat(overture=NC)
    assert r.category == "do sprawdzenia" and r.reasons == ["not_comparable"]


def test_overture_not_comparable_but_photo_comparable():
    assert cat(overture=NC, photos=[photo(50)]).category == "zgodne"


def test_below_tertiary_pair_only_with_comparable_evidence():  # P1, ADR-001 §3.5 „Zakres par”
    r = cat(highway="residential", overture=NC)
    assert r.category is None and r.exclusion == "brak porównywalnego dowodu"
    r = cat(highway="residential", osm=NC, overture=V(50))
    assert r.category is None and r.exclusion == "brak porównywalnego dowodu"
    r = cat(highway="residential", overture=None, photos=[photo(70, link="uncertain")])
    assert r.category is None and r.exclusion == "brak porównywalnego dowodu"
    assert cat(highway="residential", overture=V(70)).category == "rozbieżne"


def test_multiple_reasons_all_listed():
    r = cat(overture=NC, photos=[photo(None, link="uncertain", reading="model_unavailable"), photo(None, reading="abstain", pid="p2")])
    assert r.category == "do sprawdzenia"
    assert set(r.reasons) == {"not_comparable", "ambiguous_link", "abstain"}


def test_queue_items_never_automatic_category():  # AC-10, AC-10a
    for r in [cat(osm=NC), cat(overture=NC), cat(osm=MISSING, overture=V(50)), cat(photos=[photo(None, reading="abstain")])]:
        assert r.category == "do sprawdzenia"
        assert r.reasons and set(r.reasons) <= REASONS


def test_surface():
    assert cp.categorize("surface", "primary", V("paved"), V("unpaved"), [], MISSING_CLASSES).category == "rozbieżne"
    assert cp.categorize("surface", "primary", V("paved"), None, [photo("paved")], MISSING_CLASSES).category == "zgodne"
    assert cp.categorize("surface", "primary", V("paved"), None, [photo("unknown")], MISSING_CLASSES).reasons == ["abstain"]


# Etap 2: oświetlenie (PRD §8, ADR-001 §4.4)
def test_lit_lamp_visible_with_lit_no_is_queue():
    r = cp.categorize("lit", "residential", V("no"), None, [photo("yes")], MISSING_CLASSES)
    assert r.category == "do sprawdzenia" and r.reasons == ["not_comparable"]


def test_lit_lamp_visible_with_missing_lit_is_missing():
    r = cp.categorize("lit", "residential", MISSING, None, [photo("yes")], MISSING_CLASSES)
    assert r.category == "do sprawdzenia" and r.reasons == ["missing"]


def test_lit_no_lamp_is_not_evidence():
    r = cp.categorize("lit", "residential", V("no"), None, [photo("no")], MISSING_CLASSES)
    assert r.exclusion == "brak porównywalnego dowodu"
    r = cp.categorize("lit", "residential", MISSING, None, [photo("no")], MISSING_CLASSES)
    assert r.exclusion == "brak porównywalnego dowodu"


def test_lit_yes_and_lamp_zgodne():
    assert cp.categorize("lit", "residential", V("yes"), None, [photo("yes")], MISSING_CLASSES).category == "zgodne"


def test_lit_photo_sole_evidence_model_unavailable():
    r = cp.categorize("lit", "service", MISSING, None, [photo(None, reading="model_unavailable")], MISSING_CLASSES)
    assert r.category == "do sprawdzenia" and r.reasons == ["model_unavailable"]


# Etap 2: skrzyżowanie
def test_junction_compare():
    assert cp.categorize("junction", "residential", V("yes"), None, [photo("no")], MISSING_CLASSES).category == "rozbieżne"
    assert cp.categorize("junction", "residential", V("yes"), None, [photo("yes")], MISSING_CLASSES).category == "zgodne"
    r = cp.categorize("junction", "residential", Normalized("not_comparable", None, "bridge", "{}"), None, [photo("yes")], MISSING_CLASSES)
    assert r.category == "do sprawdzenia" and r.reasons == ["not_comparable"]


# Crosswalk Overture → OSM (§3.3)
def test_record_id_parser_tolerates_missing_version():
    assert cp.osm_id_from_record("w75390950@17") == 75390950
    assert cp.osm_id_from_record("w75390950") == 75390950
    assert cp.osm_id_from_record("n123@4") is None
    assert cp.osm_id_from_record("") is None


def test_overture_aggregate_multiple_segments():
    assert cp.aggregate_overture([V(50), V(50)]).value == 50
    assert cp.aggregate_overture([V(50), V(70)]).status == "not_comparable"
    assert cp.aggregate_overture([V(50), MISSING]).status == "not_comparable"
    assert cp.aggregate_overture([MISSING, MISSING]).status == "missing"
    assert cp.aggregate_overture([]) is None


# Skrzyżowanie na mapie (§4.4)
def _ways():
    # droga A przez węzły 1-2-3, droga B dochodzi do węzła 2 (skrzyżowanie), droga C daleko
    a = {"osm_id": 1, "node_ids": [1, 2, 3], "geometry": LineString([(0, 0), (100, 0), (200, 0)]), "bridge": None, "tunnel": None, "layer": None, "boundary_crossing": False}
    b = {"osm_id": 2, "node_ids": [2, 4], "geometry": LineString([(100, 0), (100, 100)]), "bridge": None, "tunnel": None, "layer": None, "boundary_crossing": False}
    c = {"osm_id": 3, "node_ids": [5, 6], "geometry": LineString([(1000, 0), (1100, 0)]), "bridge": "yes", "tunnel": None, "layer": "1", "boundary_crossing": False}
    return gpd.GeoDataFrame([a, b, c], geometry="geometry", crs=2180)


def test_map_junction_near_camera():
    ways = _ways()
    deg = cp.node_degrees(ways)
    a = ways.iloc[0]
    assert cp.map_junction(a, deg, Point(110, 5), 25.0).value == "yes"
    assert cp.map_junction(a, deg, Point(160, 5), 25.0).value == "no"


def test_map_junction_bridge_or_layer_not_comparable():
    ways = _ways()
    deg = cp.node_degrees(ways)
    assert cp.map_junction(ways.iloc[2], deg, Point(1050, 0), 25.0).status == "not_comparable"


def test_map_junction_boundary_end_node_not_comparable():
    ways = _ways()
    a = ways.iloc[0].copy()
    a["boundary_crossing"] = True
    deg = cp.node_degrees(ways)
    assert cp.map_junction(a, deg, Point(195, 0), 25.0).status == "not_comparable"


def test_candidate_key_stable_and_sorted():
    k1 = cp.candidate_key(5, ["b", "a"], "speed")
    k2 = cp.candidate_key(5, ["a", "b"], "speed")
    assert k1 == k2 == "5|a,b|speed"


def test_stage_of_attribute():
    assert cp.STAGE_OF == {"speed": 1, "surface": 1, "lit": 2, "junction": 2}


def test_combine_per_photo_results():  # skrzyżowanie: każde zdjęcie względem mapy w swoim punkcie
    z = cp.PairResult("zgodne", [], None, "a")
    r = cp.PairResult("rozbieżne", [], None, "b")
    q = cp.PairResult("do sprawdzenia", ["ambiguous_link"], None, "c")
    q2 = cp.PairResult("do sprawdzenia", ["model_unavailable"], None, "d")
    x = cp.PairResult(None, [], "brak porównywalnego dowodu", "")
    assert cp.combine_results([z, r, q]).category == "rozbieżne"
    assert cp.combine_results([q, z]).category == "zgodne"
    assert cp.combine_results([q, q2, x]).reasons == ["ambiguous_link", "model_unavailable"]
    assert cp.combine_results([x]).exclusion == "brak porównywalnego dowodu"


def test_link_details_text():  # R-A: szczegóły LinkAssessment przy kandydacie (ADR-000 §5.2, ADR-001 §3.4)
    row = {"photo_id": "p1", "status": "uncertain", "distance_m": 5.2128, "bearing_diff": 87.898,
           "reasons": ["bearing_gt_threshold"], "info_flags": ["camera_against_way_direction"]}
    t = cp.link_detail(row)
    assert t == "p1: niepewne, 5.2 m, różnica kierunku 87.9°, przyczyny: bearing_gt_threshold; informacje: camera_against_way_direction"
    row2 = {**row, "status": "certain", "bearing_diff": float("nan"), "reasons": [], "info_flags": []}
    assert cp.link_detail(row2) == "p1: pewne, 5.2 m, różnica kierunku brak"
