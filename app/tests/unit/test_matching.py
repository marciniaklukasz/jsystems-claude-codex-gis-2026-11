"""ADR-001 §3.2–3.4, §8; AC-04, AC-06, AC-08; TAC-001-02. Plan.md §3 (6 przypadków)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import LineString, Point

from map_qa import matching as mt

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "rows"
TH = {
    "max_distance_m": 15.0,
    "max_bearing_diff_deg": 30.0,
    "distance_tolerance_m": 1.0,
    "bearing_tolerance_deg": 1.0,
    "tangent_half_length_m": 5.0,
}
TO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)


def osm_gdf(rows: list[dict], crs=4326) -> gpd.GeoDataFrame:
    recs = []
    for r in rows:
        t = json.loads(r["tags"]) if isinstance(r.get("tags"), str) else r.get("tags", {})
        recs.append({
            "osm_id": r["osm_id"], "highway": r.get("highway"), "access": t.get("access"),
            "motor_vehicle": t.get("motor_vehicle"), "geometry": r["geometry"] if "geometry" in r else wkt.loads(r["geometry_wkt"]),
        })
    g = gpd.GeoDataFrame(recs, geometry="geometry", crs=crs)
    return g


def link_row(photo_id, osm_way_id, distance_m, bearing_diff, flags="", method="osm_source_reference"):
    return {"photo_id": photo_id, "osm_way_id": osm_way_id, "overture_id": "ov", "distance_m": distance_m,
            "bearing_diff": bearing_diff, "match_method": method, "candidate_flags": flags}


def photo_row(photo_id, x2180, y2180, heading):
    lon, lat = TO_4326.transform(x2180, y2180)
    return {"photo_id": photo_id, "longitude": lon, "latitude": lat, "heading": heading}


# Prosta droga w EPSG:2180 o kierunku siatki ~północ, w okolicy Krakowa.
X0, Y0 = 566000.0, 244000.0


def north_road(osm_id=1, reverse=False, **attrs):
    line = LineString([(X0, Y0 - 100), (X0, Y0 + 100)])
    if reverse:
        line = LineString(list(line.coords)[::-1])
    g = gpd.GeoDataFrame([{"osm_id": osm_id, "highway": "residential", "access": None, "motor_vehicle": None, **attrs, "geometry": line}],
                         geometry="geometry", crs=2180)
    return g


def assess_one(osm2180, photo, link, th=TH):
    res = mt.assess_links(pd.DataFrame([link]), pd.DataFrame([photo]), osm2180, th)
    assert len(res) == 1
    return res.iloc[0]


# 1. CRS i znany dystans 10 m -----------------------------------------------------------
def test_distance_10m_after_roundtrip_from_4326():
    road = north_road()
    road4326 = road.to_crs(4326)
    photo = photo_row("p", X0 + 10.0, Y0, 0.0)
    pts = mt.photo_points_2180(pd.DataFrame([photo]))
    assert pts.crs.to_epsg() == 2180
    d = mt.distance_m(pts.geometry.iloc[0], road4326.to_crs(2180).geometry.iloc[0])
    assert d == pytest.approx(10.0, abs=0.01)


def test_overture_crs84_converts_to_2180():
    road = north_road().to_crs("OGC:CRS84")
    back = road.to_crs(2180)
    assert back.geometry.iloc[0].length == pytest.approx(200.0, abs=0.01)


def test_functions_reject_non_metric_crs():  # TAC-001-02
    with pytest.raises(mt.CRSError):
        mt.assess_links(pd.DataFrame([link_row("p", 1, 1.0, 0.0)]), pd.DataFrame([photo_row("p", X0, Y0, 0.0)]), north_road().to_crs(4326), TH)
    with pytest.raises(mt.CRSError):
        mt.require_metric(north_road().to_crs(4326))


# 2. Kąt z zawijaniem ---------------------------------------------------------------------
@pytest.mark.parametrize("heading, bearing, expected", [(359, 1, 2), (1, 359, 2), (10, 190, 0), (90, 0, 90), (100, 0, 80), (0, 0, 0), (180, 0, 0)])
def test_angle_diff_wraps_and_is_undirected(heading, bearing, expected):
    assert mt.angle_diff(heading, bearing) == pytest.approx(expected)


def test_angle_diff_nan_heading():
    assert math.isnan(mt.angle_diff(float("nan"), 10.0))


# 3. Odwrócona geometria i oneway=-1 → ta sama różnica ---------------------------------
def test_reversed_geometry_same_bearing_diff():
    photo = photo_row("p", X0 + 2.0, Y0, 3.0)
    a = assess_one(north_road(), photo, link_row("p", 1, 2.0, 3.0))
    b = assess_one(north_road(reverse=True, oneway="-1"), photo, link_row("p", 1, 2.0, 3.0))
    assert a["bearing_diff"] == pytest.approx(b["bearing_diff"], abs=1e-6)


def test_local_bearing_is_geodesic_true_north():
    # Oś Y układu 2180 nie jest północą rzeczywistą poza południkiem 19°E (zbieżność południków).
    line = LineString([(X0, Y0 - 100), (X0, Y0 + 100)])
    b = mt.local_bearing(line, Point(X0, Y0), 5.0)
    lon, _ = TO_4326.transform(X0, Y0)
    assert lon > 19.0
    assert 0.1 < (b % 360) < 2.0 or 180.1 < (b % 360) < 182.0 or 358.0 < (b % 360) < 359.9 or 178.0 < (b % 360) < 179.9


# 4. Brak kierunku / heading 0 -----------------------------------------------------------
def test_missing_heading_is_uncertain():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, float("nan")), link_row("p", 1, 1.0, float("nan"), "missing_heading"))
    assert r["status"] == "uncertain"
    assert "missing_heading" in r["reasons"]
    assert math.isnan(r["bearing_diff"])


def test_heading_zero_is_north_not_missing():
    road = north_road()
    b = mt.local_bearing(road.geometry.iloc[0], Point(X0, Y0), 5.0)
    expected = mt.angle_diff(0.0, b)
    r = assess_one(road, photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, expected))
    assert r["status"] == "certain"
    assert r["bearing_diff"] == pytest.approx(expected, abs=0.01)


# 5. Dwa bliskie odcinki / remis -----------------------------------------------------------
def test_ambiguous_candidates_flag():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, 0.0, "ambiguous_candidates"))
    assert r["status"] == "uncertain" and "ambiguous_candidates" in r["reasons"]


def test_rank_tie_break_distance_then_osm_id():
    cands = pd.DataFrame([
        {"osm_id": 7, "distance_m": 3.0, "bearing_diff": 9.0},   # rank 4.0
        {"osm_id": 5, "distance_m": 4.0, "bearing_diff": 0.0},   # rank 4.0, większy dystans
        {"osm_id": 3, "distance_m": 3.0, "bearing_diff": 9.0},   # rank 4.0, ten sam dystans, mniejsze id
        {"osm_id": 9, "distance_m": 1.0, "bearing_diff": float("nan")},  # brak kierunku = +5 m → 6.0
    ])
    assert list(mt.rank_candidates(cands)["osm_id"]) == [3, 7, 5, 9]


# 6. Droga serwisowa / dostęp --------------------------------------------------------------
@pytest.mark.parametrize("attrs", [{"access": "private"}, {"access": "no"}, {"motor_vehicle": "no"}, {"motor_vehicle": "private"}])
def test_restricted_access_is_uncertain(attrs):
    r = assess_one(north_road(**attrs), photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, 0.0))
    assert r["status"] == "uncertain" and "restricted_access" in r["reasons"]


def test_service_way_flag_uncertain():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, 0.0, "service_way"))
    assert r["status"] == "uncertain" and "service_way" in r["reasons"]


# Progi, mismatch, flagi informacyjne, brak kandydata --------------------------------------
def test_distance_threshold_and_mismatch():
    r = assess_one(north_road(), photo_row("p", X0 + 16, Y0, 0.0), link_row("p", 1, 16.0, 0.5))
    assert r["status"] == "uncertain" and "distance_gt_threshold" in r["reasons"]
    r = assess_one(north_road(), photo_row("p", X0 + 5, Y0, 0.0), link_row("p", 1, 2.0, 0.5))
    assert "link_distance_mismatch" in r["reasons"]


def test_bearing_threshold():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, 45.0), link_row("p", 1, 1.0, float("nan")))
    assert "bearing_gt_threshold" in r["reasons"]


def test_info_flags_do_not_make_uncertain():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, 0.5, "camera_against_way_direction;boundary_crossing"))
    assert r["status"] == "certain"
    assert set(r["info_flags"]) == {"camera_against_way_direction", "boundary_crossing"}


def test_spatial_fallback_and_overture_spatial_only():
    r = assess_one(north_road(), photo_row("p", X0 + 1, Y0, 0.0), link_row("p", 1, 1.0, 0.5, "overture_spatial_only", "spatial_fallback"))
    assert r["status"] == "uncertain"
    assert {"spatial_fallback", "overture_spatial_only"} <= set(r["reasons"])


def test_no_candidate():
    link = {"photo_id": "p", "osm_way_id": pd.NA, "overture_id": "", "distance_m": float("nan"), "bearing_diff": float("nan"),
            "match_method": "none", "candidate_flags": "no_osm_within_25m"}
    r = assess_one(north_road(), photo_row("p", X0, Y0, 0.0), link)
    assert r["status"] == "no_candidate"


def test_link_counts_three_disjoint_groups():
    df = pd.DataFrame({"status": ["certain", "uncertain", "uncertain", "no_candidate"], "heading_missing": [False, True, False, False]})
    c = mt.link_counts(df)
    assert c == {"certain": 1, "uncertain": 2, "no_candidate": 1, "total": 4, "missing_heading": 1}


# Prawdziwe wiersze ------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real():
    osm = osm_gdf(json.loads((ROWS / "osm_link_rows.json").read_text(encoding="utf-8"))).to_crs(2180)
    links = pd.read_csv(ROWS / "photo_road_links.csv", comment="#", dtype={"photo_id": str, "candidate_flags": str, "overture_id": str, "match_method": str}, keep_default_na=False, na_values={"distance_m": [""], "bearing_diff": [""], "osm_way_id": [""]})
    links["osm_way_id"] = pd.array(pd.to_numeric(links["osm_way_id"], errors="coerce"), dtype="Int64")
    photos = pd.read_csv(ROWS / "photos.csv", comment="#")
    return mt.assess_links(links, photos, osm, TH).set_index("photo_id")


def test_real_certain_link(real):
    r = real.loc["panoramax_334a574d-18cb-4c2e-be3f-f99307e080d9"]
    assert r["status"] == "certain", r["reasons"]
    assert r["distance_m"] == pytest.approx(0.392, abs=1.0)
    assert r["bearing_diff"] == pytest.approx(0.154, abs=1.0)


def test_real_poor_heading_uncertain(real):
    r = real.loc["panoramax_646ecfdd-ab57-4a28-b411-fb112ced3c97"]
    assert r["status"] == "uncertain" and "bearing_gt_threshold" in r["reasons"]


def test_real_no_candidate(real):
    assert real.loc["panoramax_df4d3a9c-5fb6-427f-8c54-293ed6ea354b", "status"] == "no_candidate"


def test_real_spatial_fallback(real):
    assert real.loc["mapillary_1127617272466620", "status"] == "uncertain"


# signs/nearest_osm.csv (ADR-001 §3.4, uzupełnienie 2026-11-12) ----------------------------
def test_sign_links_schema_mapping_and_evaluation_only():
    osm = osm_gdf(json.loads((ROWS / "osm_link_rows.json").read_text(encoding="utf-8"))).to_crs(2180)
    near = pd.read_csv(ROWS / "nearest_osm.csv", comment="#", dtype=str, keep_default_na=False)
    signs = pd.read_csv(ROWS / "signs.csv", comment="#")
    res = mt.assess_sign_links(near, signs, osm, TH).set_index("photo_id")
    assert res.loc["mapillary_940500342204329", "status"] == "evaluation_only"  # source = osm_api
    assert res.loc["mapillary_1602686671072776", "status"] == "evaluation_only"  # outside_standard_25m
    assert res.loc["mapillary_1428012997566511", "status"] == "uncertain"  # ambiguous_candidates
    assert res.loc["mapillary_1931009810597411", "status"] == "certain", res.loc["mapillary_1931009810597411", "reasons"]
