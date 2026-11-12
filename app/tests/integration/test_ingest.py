"""AC-01..AC-03, ADR-001 §3.1, §8 (hash wejścia), AC-08 (heading)."""

from __future__ import annotations

import json
import math

import pytest

from map_qa import ingest


def test_verify_inputs_accepts_snapshot(data_dir):
    files = ingest.verify_inputs(data_dir)
    names = {f["name"] for f in files}
    assert len(files) == 8
    assert {"osm_roads.parquet", "photos.csv", "traffic_signs.geojson"} <= names
    assert all(len(f["sha256"]) == 64 for f in files)


def test_changed_byte_raises_with_filename(data_copy):
    p = data_copy / "photos.csv"
    raw = bytearray(p.read_bytes())
    raw[100] = (raw[100] + 1) % 256
    p.write_bytes(bytes(raw))
    with pytest.raises(ingest.InputIntegrityError) as exc:
        ingest.verify_inputs(data_copy)
    assert exc.value.filename == "photos.csv"
    assert "photos.csv" in str(exc.value)


def test_missing_file_raises_with_filename(data_copy):
    (data_copy / "photo_road_links.csv").unlink()
    with pytest.raises(ingest.InputIntegrityError) as exc:
        ingest.verify_inputs(data_copy)
    assert exc.value.filename == "photo_road_links.csv"


@pytest.fixture(scope="module")
def layers(data_dir):
    return ingest.load_layers(data_dir)


def test_counts_match_snapshot(layers):
    assert len(layers.osm) == 99_768
    assert len(layers.overture) == 85_405
    assert len(layers.photos) == 561
    assert len(layers.links) == 561
    assert layers.traffic_signs_count == 1_730


def test_crs_set_from_sources(layers):
    assert layers.osm.crs.to_epsg() == 4326
    assert layers.overture.crs.to_string() in {"OGC:CRS84", "EPSG:4326"} or layers.overture.crs.equals("OGC:CRS84")


def test_tags_parsed_and_raw_preserved(layers):
    row = layers.osm.iloc[0]
    assert isinstance(row["tags_dict"], dict)
    assert json.loads(row["tags_raw"]) == row["tags_dict"]


def test_heading_missing_is_nan_and_zero_is_north(layers):
    ph = layers.photos.set_index("photo_id")
    assert math.isnan(ph.loc["panoramax_646ecfdd-ab57-4a28-b411-fb112ced3c97", "heading"]) is False
    assert ph.loc["panoramax_646ecfdd-ab57-4a28-b411-fb112ced3c97", "heading"] == 0.0
    assert ph["heading"].isna().sum() == 15


def test_source_versions(layers):
    assert layers.sources["osm"]["extract_date"] == "2026-11-01T21:21:36Z"
    assert layers.sources["overture"]["release"] == "2026-10-21.0"
