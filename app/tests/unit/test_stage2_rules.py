"""Etap 2 na prawdziwych wierszach: ADR-001 §4.4 (most/tunel/warstwa → not_comparable), PRD §8 (oświetlenie), AC-32."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely import wkt
from shapely.geometry import Point

from map_qa import compare, normalize

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "rows"
OSM = {r["case"]: r for r in json.loads((ROWS / "osm_rows.json").read_text(encoding="utf-8"))}


def way(case: str):
    r = OSM[case]
    t = json.loads(r["tags"])
    g = gpd.GeoDataFrame([{"osm_id": r["osm_id"], "node_ids": r["node_ids"], "boundary_crossing": r["boundary_crossing"],
                           "bridge": t.get("bridge"), "tunnel": t.get("tunnel"), "layer": t.get("layer"),
                           "geometry": wkt.loads(r["geometry_wkt"])}], geometry="geometry", crs=4326).to_crs(2180)
    return g.iloc[0], g


def test_real_bridge_way_junction_not_comparable():
    w, g = way("bridge")
    mid = w.geometry.interpolate(0.5, normalized=True)
    assert compare.map_junction(w, compare.node_degrees(g), Point(mid.x, mid.y), 25.0).status == "not_comparable"


def test_real_layer_minus1_way_junction_not_comparable():
    w, g = way("layer_minus1")
    mid = w.geometry.interpolate(0.5, normalized=True)
    assert compare.map_junction(w, compare.node_degrees(g), Point(mid.x, mid.y), 25.0).status == "not_comparable"


def test_real_lit_no_row_with_lamp_goes_to_queue():
    lit = normalize.parse_lit(json.loads(OSM["lit_no"]["tags"]).get("lit"))
    ph = compare.PhotoEvidence("p", "certain", "certain", "yes", "decision")
    r = compare.categorize("lit", "motorway", lit, None, [ph], [])
    assert r.category == "do sprawdzenia" and "lampa nie dowodzi działania instalacji" in r.reason_text


def test_real_lit_yes_row_without_reading_model_unavailable():
    lit = normalize.parse_lit(json.loads(OSM["simple_maxspeed_40"]["tags"]).get("lit"))
    ph = compare.PhotoEvidence("p", "certain", "model_unavailable", None, None)
    r = compare.categorize("lit", "residential", lit, None, [ph], [])
    assert r.reasons == ["model_unavailable"]
