"""Kopiuje wybrane prawdziwe wiersze danych map-qa do app/tests/fixtures/rows/ (T1.4, ADR-001 §8).

Uruchomienie z app/: uv run python scripts/extract_fixture_rows.py
Wejścia tylko czytane. Każdy wiersz ma pole _source (plik, ID, data ekstrakcji).
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parents[1]
DATA = APP.parent / "course-materials" / "exercise-data" / "map-qa"
OUT = APP / "tests" / "fixtures" / "rows"
TODAY = date.today().isoformat()


def plain(v):
    if isinstance(v, np.ndarray):
        return [plain(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def pick_osm(osm: gpd.GeoDataFrame) -> list[dict]:
    tags = osm["tags"].map(json.loads)
    sel: dict[str, int] = {}

    def first(name, mask):
        idx = osm.index[mask]
        if len(idx):
            sel[name] = idx[0]

    first("simple_maxspeed_40", osm["osm_id"] == 2954554)
    first("conditional", tags.map(lambda t: "maxspeed:conditional" in t))
    first("forward_backward_diff", tags.map(lambda t: "maxspeed:forward" in t and "maxspeed:backward" in t and t["maxspeed:forward"] != t["maxspeed:backward"]))
    first("forward_backward_equal", tags.map(lambda t: "maxspeed:forward" in t and "maxspeed:backward" in t and t["maxspeed:forward"] == t["maxspeed:backward"]))
    first("forward_only", tags.map(lambda t: "maxspeed:forward" in t and "maxspeed:backward" not in t and "maxspeed" not in t))
    first("maxspeed_type_pl", tags.map(lambda t: str(t.get("maxspeed:type", "")).startswith("PL:") and "maxspeed" in t))
    first("hgv", tags.map(lambda t: "maxspeed:hgv" in t))
    first("surface_typo", osm["surface"] == "paving_Stones")
    first("tertiary_no_maxspeed", (osm["highway"] == "tertiary") & osm["maxspeed"].isna() & tags.map(lambda t: not any(k.startswith("maxspeed") for k in t)))
    first("residential_no_maxspeed", (osm["highway"] == "residential") & osm["maxspeed"].isna() & tags.map(lambda t: not any(k.startswith("maxspeed") for k in t)))
    first("access_private", (osm["access"] == "private") & (osm["highway"] == "service"))
    first("motor_vehicle_no", osm["motor_vehicle"] == "no")
    first("bridge", osm["bridge"] == "yes")
    first("layer_minus1", osm["layer"] == "-1")
    first("lit_no", osm["lit"] == "no")
    rows = []
    for name, i in sel.items():
        r = osm.loc[i]
        rows.append({
            "_source": f"osm_roads.parquet osm_id={int(r.osm_id)} ({TODAY})",
            "case": name,
            "osm_id": int(r.osm_id),
            "osm_timestamp": r.osm_timestamp,
            "highway": r.highway,
            "tags": r.tags,
            "node_ids": plain(r.node_ids),
            "boundary_crossing": bool(r.boundary_crossing),
            "geometry_wkt": r.geometry.wkt,
        })
    return rows


def pick_overture(ov: gpd.GeoDataFrame) -> list[dict]:
    sl = ov["speed_limits"]
    n = sl.map(lambda x: 0 if x is None else len(x))

    def has(rule, key):
        return rule.get(key) is not None

    sel = {}
    def first(name, mask):
        idx = ov.index[mask]
        if len(idx):
            sel[name] = idx[0]

    first("one_rule_whole", (n == 1) & sl.map(lambda x: x is not None and not has(x[0], "when") and not has(x[0], "between")))
    first("two_rules", n >= 2)
    first("rule_with_when", (n == 1) & sl.map(lambda x: x is not None and has(x[0], "when")))
    first("rule_with_between", (n == 1) & sl.map(lambda x: x is not None and has(x[0], "between") and not has(x[0], "when")))
    first("variable", sl.map(lambda x: x is not None and any(r.get("is_max_speed_variable") for r in x)))
    first("surface_unknown", ov["road_surface"].map(lambda x: x is not None and len(x) == 1 and x[0]["value"] == "unknown"))
    first("surface_between", ov["road_surface"].map(lambda x: x is not None and any(r.get("between") is not None for r in x)))
    first("record_without_version", ov["sources"].map(lambda x: x is not None and any(str(s.get("record_id", "")).startswith("w") and "@" not in str(s.get("record_id")) for s in x)))
    rows = []
    for name, i in sel.items():
        r = ov.loc[i]
        rows.append({
            "_source": f"overture_segments.parquet id={r.id} ({TODAY})",
            "case": name,
            "id": r.id,
            "class": r["class"],
            "sources": plain(r.sources),
            "speed_limits": plain(r.speed_limits),
            "road_surface": plain(r.road_surface),
            "geometry_wkt": r.geometry.wkt,
        })
    return rows


def copy_csv_rows(src: Path, dst: Path, key: str, ids: list[str]) -> None:
    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r[key] in ids]
        fields = reader.fieldnames
    with dst.open("w", encoding="utf-8", newline="") as f:
        f.write(f"# source: {src.name}, {key} in selection, extracted {TODAY}\n")
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    osm = gpd.read_parquet(DATA / "osm_roads.parquet")
    ov = gpd.read_parquet(DATA / "overture_segments.parquet")
    (OUT / "osm_rows.json").write_text(json.dumps(pick_osm(osm), ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "overture_rows.json").write_text(json.dumps(pick_overture(ov), ensure_ascii=False, indent=1), encoding="utf-8")

    links = pd.read_csv(DATA / "photo_road_links.csv", dtype=str, keep_default_na=False)
    want = []
    for flag in ["", "poor_heading_alignment", "missing_heading", "ambiguous_candidates", "service_way", "no_osm_within_25m", "overture_spatial_only", "panorama_heading_ambiguous", "camera_against_way_direction"]:
        m = links[links.candidate_flags == flag] if flag == "" else links[links.candidate_flags.str.contains(flag)]
        if len(m):
            want.append(m.iloc[0].photo_id)
    want.append(links[links.match_method == "spatial_fallback"].iloc[0].photo_id)
    want = list(dict.fromkeys(want))
    copy_csv_rows(DATA / "photo_road_links.csv", OUT / "photo_road_links.csv", "photo_id", want)
    way_ids = {int(x) for x in links[links.photo_id.isin(want)].osm_way_id if x}
    near_all = pd.read_csv(DATA / "signs" / "nearest_osm.csv", dtype=str, keep_default_na=False)
    way_ids |= {int(x) for x in near_all[near_all.photo_id.isin(["mapillary_1931009810597411", "mapillary_1428012997566511"])].osm_way_id if x}
    linked = osm[osm.osm_id.isin(way_ids)]
    (OUT / "osm_link_rows.json").write_text(json.dumps([
        {
            "_source": f"osm_roads.parquet osm_id={int(r.osm_id)} ({TODAY})",
            "osm_id": int(r.osm_id), "osm_timestamp": r.osm_timestamp, "highway": r.highway, "tags": r.tags,
            "node_ids": plain(r.node_ids), "boundary_crossing": bool(r.boundary_crossing), "geometry_wkt": r.geometry.wkt,
        }
        for r in linked.itertuples()
    ], ensure_ascii=False, indent=1), encoding="utf-8")
    copy_csv_rows(DATA / "photos.csv", OUT / "photos.csv", "photo_id", want)

    signs_ids = ["mapillary_1931009810597411", "mapillary_1428012997566511"]
    near = pd.read_csv(DATA / "signs" / "nearest_osm.csv", dtype=str, keep_default_na=False)
    for cond in [near.source == "osm_api", near.match_flags.str.contains("outside_standard_25m")]:
        if cond.any():
            signs_ids.append(near[cond].iloc[0].photo_id)
    copy_csv_rows(DATA / "signs" / "signs.csv", OUT / "signs.csv", "photo_id", signs_ids)
    copy_csv_rows(DATA / "signs" / "nearest_osm.csv", OUT / "nearest_osm.csv", "photo_id", signs_ids)
    print("photos:", want)
    print("signs:", signs_ids)


if __name__ == "__main__":
    main()
