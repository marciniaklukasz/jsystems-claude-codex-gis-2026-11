"""Walidacja dostarczonych połączeń zdjęcie–droga (ADR-001)."""

from __future__ import annotations

import math

import geopandas as gpd
import pandas as pd
from pyproj import Geod, Transformer


TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
TO_4326 = Transformer.from_crs(2180, 4326, always_xy=True)
GEOD = Geod(ellps="WGS84")
UNCERTAIN_FLAGS = (
    "ambiguous_candidates", "overture_spatial_only", "service_way",
    "panorama_heading_ambiguous", "missing_heading",
)
INFO_FLAGS = ("camera_against_way_direction", "boundary_crossing")
RESULT_COLUMNS = (
    "photo_id", "osm_way_id", "overture_id", "match_method", "input_flags",
    "distance_m_input", "distance_m", "bearing_diff_input", "bearing_diff",
    "heading_missing", "status", "reasons", "info_flags", "is_uncertain",
)


class CRSError(ValueError):
    """Geometria nie jest w wymaganym układzie EPSG:2180."""


def require_metric(gdf):
    if gdf.crs is None or gdf.crs.to_epsg() != 2180:
        raise CRSError("Obliczenia odległości wymagają CRS EPSG:2180.")


def angle_diff(heading, bearing) -> float:
    if pd.isna(heading) or pd.isna(bearing):
        return math.nan
    difference = abs((heading - bearing + 180) % 360 - 180)
    return float(min(difference, 180 - difference))


def photo_points_2180(photos: pd.DataFrame) -> gpd.GeoDataFrame:
    x, y = TO_2180.transform(
        photos["longitude"].to_numpy(), photos["latitude"].to_numpy(),
    )
    return gpd.GeoDataFrame(
        photos.copy(), geometry=gpd.points_from_xy(x, y), crs=2180,
    )


def distance_m(point, line) -> float:
    return float(point.distance(line))


def local_bearing(line_2180, point_2180, half_length_m) -> float:
    position = line_2180.project(point_2180)
    start = line_2180.interpolate(max(0, position - half_length_m))
    end = line_2180.interpolate(min(line_2180.length, position + half_length_m))
    lon1, lat1 = TO_4326.transform(start.x, start.y)
    lon2, lat2 = TO_4326.transform(end.x, end.y)
    azimuth, _, _ = GEOD.inv(lon1, lat1, lon2, lat2)
    return float(azimuth % 360)


def rank_candidates(df: pd.DataFrame) -> pd.DataFrame:
    score = df["distance_m"] + (df["bearing_diff"] / 9).fillna(5)
    # Osobny klucz sortowania nie nadpisuje żadnej kolumny wejścia.
    order = pd.DataFrame({
        "score": score.to_numpy(),
        "distance_m": df["distance_m"].to_numpy(),
        "osm_id": df["osm_id"].to_numpy(),
    }).sort_values(["score", "distance_m", "osm_id"], kind="stable").index
    return df.iloc[order].copy()


def _flags(value) -> list[str]:
    if pd.isna(value) or value == "":
        return []
    return list(dict.fromkeys(flag.strip() for flag in value.split(";") if flag.strip()))


def _result_row(link, heading) -> dict:
    flags = _flags(link.candidate_flags)
    return {
        "photo_id": link.photo_id,
        "osm_way_id": link.osm_way_id,
        "overture_id": link.overture_id,
        "match_method": link.match_method,
        "input_flags": flags,
        "distance_m_input": link.distance_m,
        "distance_m": math.nan,
        "bearing_diff_input": link.bearing_diff,
        "bearing_diff": math.nan,
        "heading_missing": bool(pd.isna(heading)),
        "status": "no_candidate",
        "reasons": ["no_candidate"],
        "info_flags": [flag for flag in INFO_FLAGS if flag in flags],
        "is_uncertain": False,
    }


def assess_links(links, photos, osm_2180, th) -> pd.DataFrame:
    require_metric(osm_2180)
    points = photo_points_2180(photos).set_index("photo_id")
    roads = osm_2180.set_index("osm_id")
    results = []
    for link in links.itertuples(index=False):
        photo = points.loc[link.photo_id]
        row = _result_row(link, photo.heading)
        flags = row["input_flags"]
        if (link.match_method == "none" or "no_osm_within_25m" in flags
                or pd.isna(link.osm_way_id)):
            results.append(row)
            continue

        road = roads.loc[link.osm_way_id]
        distance = distance_m(photo.geometry, road.geometry)
        # Azymuty na przeciwnych końcach geodezyjnej nie różnią się dokładnie o 180°.
        direction_line = road.geometry.normalize()
        bearing = angle_diff(
            photo.heading,
            local_bearing(direction_line, photo.geometry, th["tangent_half_length_m"]),
        )
        reasons = []
        if distance > th["max_distance_m"]:
            reasons.append("distance_gt_threshold")
        if bearing > th["max_bearing_diff_deg"]:
            reasons.append("bearing_gt_threshold")
        for flag in UNCERTAIN_FLAGS:
            if flag in flags or (flag == "missing_heading" and row["heading_missing"]):
                reasons.append(flag)
        if link.match_method == "spatial_fallback":
            reasons.append("spatial_fallback")
        if pd.notna(link.distance_m) and abs(distance - link.distance_m) > th["distance_tolerance_m"]:
            reasons.append("link_distance_mismatch")
        if (pd.notna(link.bearing_diff) and pd.notna(bearing)
                and abs(bearing - link.bearing_diff) > th["bearing_tolerance_deg"]):
            reasons.append("link_bearing_mismatch")
        if any(pd.notna(value) and value in {"private", "no"}
               for value in (road.access, road.motor_vehicle)):
            reasons.append("restricted_access")
        row.update(
            distance_m=distance, bearing_diff=bearing, reasons=reasons,
            status="uncertain" if reasons else "certain", is_uncertain=bool(reasons),
        )
        results.append(row)
    return pd.DataFrame(results, columns=RESULT_COLUMNS)


def link_counts(df: pd.DataFrame) -> dict:
    return {
        **{status: int(df["status"].eq(status).sum())
           for status in ("certain", "uncertain", "no_candidate")},
        "total": len(df),
        "missing_heading": int(df["heading_missing"].sum()),
    }


def assess_sign_links(nearest, signs, osm_2180, th) -> pd.DataFrame:
    require_metric(osm_2180)
    links = nearest.rename(columns={
        "heading_diff_deg": "bearing_diff", "match_flags": "candidate_flags",
    }).copy().reset_index(drop=True)
    links["match_method"] = "osm_source_reference"
    links["overture_id"] = ""
    links["osm_way_id"] = pd.to_numeric(links["osm_way_id"], errors="raise").astype("Int64")
    for column in ("distance_m", "bearing_diff"):
        links[column] = pd.to_numeric(links[column].replace("", math.nan), errors="raise")
    photos = signs.rename(columns={"compass_angle": "heading"}).copy()
    photos["heading"] = pd.to_numeric(photos["heading"].replace("", math.nan), errors="raise")
    evaluation = links["source"].eq("osm_api") | links["candidate_flags"].map(
        lambda value: "outside_standard_25m" in _flags(value),
    )
    normal = links.loc[~evaluation]
    assessed = assess_links(normal, photos[photos["photo_id"].isin(normal["photo_id"])], osm_2180, th)
    assessed.index = normal.index
    headings = photos.set_index("photo_id")["heading"]
    evaluation_rows = []
    for link in links.loc[evaluation].itertuples(index=False):
        row = _result_row(link, headings.loc[link.photo_id])
        row.update(status="evaluation_only", reasons=["evaluation_only"])
        evaluation_rows.append(row)
    evaluated = pd.DataFrame(evaluation_rows, columns=RESULT_COLUMNS, index=links.index[evaluation])
    return pd.concat([assessed, evaluated]).sort_index().reset_index(drop=True)
