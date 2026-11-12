from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

class InputIntegrityError(Exception):
    def __init__(self, filename: str):
        self.filename = Path(filename).name
        super().__init__(f"Plik wejściowy {self.filename} nie istnieje lub nie zgadza się z manifestem.")

def load_sources(data_dir: str | Path) -> dict:
    with (Path(data_dir) / "sources.json").open(encoding="utf-8") as f:
        return json.load(f)

def verify_inputs(data_dir: str | Path) -> list[dict]:
    root = Path(data_dir)
    results = []
    files = load_sources(root)["files"]
    entries = files.items() if isinstance(files, dict) else ((s["name"], s) for s in files)
    for name, spec in entries:
        expected_bytes = spec.get("bytes", spec.get("size_bytes"))
        expected_hash = spec.get("sha256")
        if expected_bytes is None or expected_hash is None:
            raise ValueError("sources.json files musi zawierać name, bytes i sha256.")
        path = root / name
        try:
            size = path.stat().st_size
            digest = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise InputIntegrityError(name) from exc
        sha256 = digest.hexdigest()
        if size != expected_bytes or sha256 != expected_hash:
            raise InputIntegrityError(name)
        results.append({"name": name, "bytes": size, "sha256": sha256})
    return results

@dataclass
class Layers:
    osm: gpd.GeoDataFrame
    overture: gpd.GeoDataFrame
    photos: pd.DataFrame
    links: pd.DataFrame
    traffic_signs_count: int
    sources: dict

def _require(df: pd.DataFrame, columns: set[str]) -> None:
    missing = columns - set(df.columns)
    if missing:
        raise ValueError(f"Brak wymaganej kolumny: {sorted(missing)[0]}")

def load_layers(data_dir: str | Path) -> Layers:
    root = Path(data_dir)
    sources = load_sources(root)
    osm = gpd.read_parquet(root / "osm_roads.parquet")
    _require(osm, {"tags"})
    osm = osm.set_crs(sources["osm"]["crs"], allow_override=True)
    osm["tags_raw"] = osm["tags"]
    osm["tags_dict"] = osm["tags"].map(json.loads)
    overture = gpd.read_parquet(root / "overture_segments.parquet")
    overture = overture.set_crs(sources["overture"]["crs"], allow_override=True)
    photos = pd.read_csv(root / "photos.csv", encoding="utf-8")
    _require(photos, {"heading", "photo_id"})
    photos["heading"] = pd.to_numeric(photos["heading"], errors="coerce").astype(float)
    photos["photo_id"] = photos["photo_id"].astype(str)
    links = pd.read_csv(root / "photo_road_links.csv", encoding="utf-8")
    _require(links, {"osm_way_id", "overture_id", "candidate_flags", "match_method"})
    links["osm_way_id"] = pd.to_numeric(links["osm_way_id"], errors="coerce").astype("Int64")
    for col in ("overture_id", "candidate_flags", "match_method"):
        links[col] = links[col].fillna("").astype(str)
    with (root / "traffic_signs.geojson").open(encoding="utf-8") as f:
        traffic_signs_count = len(json.load(f)["features"])
    return Layers(osm, overture, photos, links, traffic_signs_count, sources)
