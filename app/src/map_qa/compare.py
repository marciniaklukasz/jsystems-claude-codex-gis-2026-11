"""Pary (droga OSM, atrybut), kategorie i przyczyny (ADR-001 §3.3, §3.5, §4.4, §4.5)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from map_qa import normalize as nz
from map_qa.normalize import Normalized

STAGE_OF = {"speed": 1, "surface": 1, "lit": 2, "junction": 2}
QUESTION_OF = {"speed": "speed_limit_value", "surface": "surface", "lit": "street_lighting_visible", "junction": "junction_visible"}
ATTRIBUTE_LABEL = {"speed": "ograniczenie prędkości", "surface": "nawierzchnia", "lit": "oświetlenie", "junction": "skrzyżowanie"}
REASONS = ("missing", "not_comparable", "ambiguous_link", "abstain", "model_unavailable")
EXCL_NO_EVIDENCE = "brak porównywalnego dowodu"
EXCL_MISSING_LOW = "brak wartości poniżej tertiary"
EXCL_NO_CANDIDATE = "zdjęcie: brak kandydata w promieniu"
EXCL_EVAL_ONLY = "zdjęcie znaku: tylko ewaluacja odczytu"

REASON_TEXT = {
    "missing": "brak atrybutu w OSM",
    "not_comparable": "wartość nieporównywalna",
    "ambiguous_link": "niepewne połączenie zdjęcia z drogą",
    "abstain": "model nie rozstrzygnął odczytu (abstencja)",
    "model_unavailable": "brak odczytu modelu",
}


@dataclass(frozen=True)
class PhotoEvidence:
    photo_id: str
    link_status: str  # certain | uncertain
    reading_status: str  # certain | abstain | model_unavailable
    value: str | int | None
    stage: str | None = None  # decision | fallback | manual


@dataclass
class PairResult:
    category: str | None
    reasons: list[str] = field(default_factory=list)
    exclusion: str | None = None
    reason_text: str = ""


# --- dowód ze zdjęcia ---------------------------------------------------------------------
def _photo_value(attribute: str, value):
    """Odczyt → (status, wartość znormalizowana). status: value | none | abstain."""
    if value is None:
        return "abstain", None
    v = str(value)
    if v == "unknown":
        return "abstain", None
    if attribute == "speed":
        if v == "none":
            return "none", None  # brak znaku B-33 nie jest dowodem wartości
        if v == "unreadable":
            return "abstain", None
        try:
            return "value", int(v)
        except ValueError:
            return "abstain", None
    if attribute == "lit" and v == "no":
        return "none", None  # brak lampy w kadrze nie jest dowodem lit=no
    return "value", v


def categorize(attribute: str, highway: str, osm: Normalized, overture: Normalized | None,
               photos: list[PhotoEvidence], missing_classes) -> PairResult:
    major = highway in set(missing_classes)
    reasons: list[str] = []
    comparable: list[tuple[str, object]] = []  # (źródło, wartość)
    notes: list[str] = []

    # dowód (b): zdjęcia
    photo_values: list[tuple[str, object]] = []
    for ph in photos:
        if ph.link_status != "certain":
            reasons.append("ambiguous_link")
            continue
        if ph.reading_status == "model_unavailable":
            reasons.append("model_unavailable")
            continue
        if ph.reading_status != "certain":
            reasons.append("abstain")
            continue
        st, val = _photo_value(attribute, ph.value)
        if st == "abstain":
            reasons.append("abstain")
        elif st == "value":
            photo_values.append((f"zdjęcie {ph.photo_id}", val))

    # oświetlenie: widoczna lampa przy lit=no lub braku lit → kolejka (PRD §8)
    if attribute == "lit":
        lamp = any(v == "yes" for _, v in photo_values)
        if osm.status == "missing":
            if lamp:
                return _queue(["missing"], attribute, highway, osm, "widoczna lampa, brak tagu lit")
            return _from_reasons(reasons, attribute, highway, osm, major=True)
        if osm.status == "not_comparable":
            return _queue(["not_comparable"], attribute, highway, osm, f"lit={osm.raw}")
        if lamp and osm.value == "no":
            return _queue(["not_comparable"], attribute, highway, osm,
                          "widoczna lampa przy lit=no (lampa nie dowodzi działania instalacji)")
        comparable = [(s, v) for s, v in photo_values if v == "yes"]
        return _decide(comparable, reasons, attribute, highway, osm, major=True)

    # krok 1: brak wartości OSM
    if osm.status == "missing":
        if attribute in ("speed", "surface"):
            if major:
                return _queue(["missing"], attribute, highway, osm, f"brak atrybutu (droga {highway})")
            return PairResult(None, [], EXCL_MISSING_LOW, "")
        return _from_reasons(reasons, attribute, highway, osm, major=True)

    # wartość OSM nieporównywalna (AC-12)
    if osm.status == "not_comparable":
        if attribute in ("speed", "surface") and not major:
            return PairResult(None, [], EXCL_NO_EVIDENCE, "")
        return _queue(["not_comparable"], attribute, highway, osm, f"OSM: {osm.detail}")

    # dowód (a): OSM vs Overture
    if overture is not None and attribute in ("speed", "surface"):
        if overture.status == "value":
            comparable.append(("Overture", overture.value))
        elif overture.status == "not_comparable":
            reasons.insert(0, "not_comparable")
            notes.append(f"Overture: {overture.detail}")
    comparable.extend(photo_values)
    major_pairs = major or attribute in ("lit", "junction")
    return _decide(comparable, reasons, attribute, highway, osm, major=major_pairs, notes=notes)


def _decide(comparable, reasons, attribute, highway, osm, major, notes=()):
    if comparable:
        diffs = [(s, v) for s, v in comparable if v != osm.value]
        if diffs:
            txt = "; ".join(f"OSM {osm.value} ≠ {s} {v}" for s, v in diffs)
            return PairResult("rozbieżne", [], None, txt)
        txt = "OSM zgodne z: " + ", ".join(s for s, _ in comparable) + f" ({osm.value})"
        return PairResult("zgodne", [], None, txt)
    return _from_reasons(reasons, attribute, highway, osm, major=major, notes=notes)


def _from_reasons(reasons, attribute, highway, osm, major, notes=()):
    uniq = list(dict.fromkeys(reasons))
    if not uniq:
        return PairResult(None, [], EXCL_NO_EVIDENCE, "")
    if not major:  # poniżej tertiary para tylko przy porównywalnym dowodzie (ADR-001 §3.5, P1)
        return PairResult(None, [], EXCL_NO_EVIDENCE, "")
    return _queue(uniq, attribute, highway, osm, "; ".join(notes))


def _queue(reasons, attribute, highway, osm, extra=""):
    parts = [REASON_TEXT[r] for r in reasons]
    if extra:
        parts.append(extra)
    return PairResult("do sprawdzenia", list(reasons), None, "; ".join(parts))


def link_detail(a: dict) -> str:
    """Opis LinkAssessment dla analityka (dystans i kąt przeliczone w EPSG:2180, przyczyny, flagi informacyjne)."""
    status = {"certain": "pewne", "uncertain": "niepewne"}.get(a["status"], a["status"])
    bd = a.get("bearing_diff")
    bd_txt = "brak" if bd is None or (isinstance(bd, float) and math.isnan(bd)) else f"{bd:.1f}°"
    txt = f"{a['photo_id']}: {status}, {a['distance_m']:.1f} m, różnica kierunku {bd_txt}"
    if len(a.get("reasons") or []):
        txt += ", przyczyny: " + ", ".join(a["reasons"])
    if len(a.get("info_flags") or []):
        txt += "; informacje: " + ", ".join(a["info_flags"])
    return txt


def combine_results(results: list[PairResult]) -> PairResult:
    """Łączy wyniki dowodów częściowych tej samej pary wg kolejności ADR-001 §3.5 (rozbieżne > zgodne > kolejka > wykluczenie)."""
    for cat in ("rozbieżne", "zgodne"):
        hit = [r for r in results if r.category == cat]
        if hit:
            return PairResult(cat, [], None, "; ".join(dict.fromkeys(r.reason_text for r in hit)))
    queue = [r for r in results if r.category == "do sprawdzenia"]
    if queue:
        reasons = list(dict.fromkeys(x for r in queue for x in r.reasons))
        return PairResult("do sprawdzenia", reasons, None, "; ".join(dict.fromkeys(r.reason_text for r in queue)))
    return PairResult(None, [], results[0].exclusion if results else EXCL_NO_EVIDENCE, "")


# --- Overture → OSM -----------------------------------------------------------------------
_RECORD = re.compile(r"^w(\d+)(?:@.*)?$")


def osm_id_from_record(record_id: str | None) -> int | None:
    m = _RECORD.match(record_id or "")
    return int(m.group(1)) if m else None


def aggregate_overture(values: list[Normalized]) -> Normalized | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    raw = json.dumps([json.loads(v.raw) for v in values], ensure_ascii=False)
    if all(v.status == "missing" for v in values):
        return Normalized("missing", None, "missing", raw)
    if all(v.status == "value" for v in values) and len({v.value for v in values}) == 1:
        return Normalized("value", values[0].value, values[0].detail, raw)
    return Normalized("not_comparable", None, "partial", raw)


# --- skrzyżowanie na mapie (§4.4) ---------------------------------------------------------
def node_degrees(ways: pd.DataFrame) -> Counter:
    c: Counter = Counter()
    for nodes in ways["node_ids"]:
        c.update(set(int(n) for n in nodes))
    return c


def _present(v) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return str(v) not in ("", "no", "nan")


def map_junction(way, degrees: Counter, camera_2180: Point, radius_m: float) -> Normalized:
    raw = nz.to_json({k: (None if not _present(way.get(k)) else str(way.get(k))) for k in ("bridge", "tunnel", "layer")})
    layer = way.get("layer")
    if _present(way.get("bridge")) or _present(way.get("tunnel")) or (_present(layer) and str(layer) != "0"):
        return Normalized("not_comparable", None, "level", raw)
    line = way["geometry"]
    proj = line.interpolate(line.project(camera_2180))
    coords = list(line.coords)
    nodes = [int(n) for n in way["node_ids"]]
    if bool(way.get("boundary_crossing")):
        for idx in (0, len(coords) - 1):
            if Point(coords[idx]).distance(proj) <= radius_m:
                return Normalized("not_comparable", None, "boundary", raw)
    for nid, xy in zip(nodes, coords):
        if degrees.get(nid, 0) >= 2 and Point(xy).distance(proj) <= radius_m:
            return Normalized("value", "yes", "junction", raw)
    return Normalized("value", "no", "junction", raw)


def candidate_key(osm_id: int, overture_ids, attribute: str) -> str:
    return f"{int(osm_id)}|{','.join(sorted(overture_ids))}|{attribute}"


def candidate_id(run_id: str, key: str) -> str:
    return hashlib.sha256(f"{run_id}|{key}".encode()).hexdigest()[:16]


# --- budowa kandydatów na pełnych danych ---------------------------------------------------
def _overture_index(overture: gpd.GeoDataFrame, th: dict) -> dict[int, list[tuple[str, Normalized, Normalized]]]:
    paved, unpaved = th["surface"]["overture_paved"], th["surface"]["overture_unpaved"]
    idx: dict[int, list] = {}
    for seg_id, sources, sl, rs in zip(overture["id"], overture["sources"], overture["speed_limits"], overture["road_surface"]):
        if sources is None:
            continue
        ids = {osm_id_from_record(s.get("record_id")) for s in sources}
        ids.discard(None)
        if not ids:
            continue
        sp = nz.parse_overture_speed(sl)
        su = nz.parse_overture_surface(rs, paved, unpaved)
        for oid in ids:
            idx.setdefault(oid, []).append((seg_id, sp, su))
    return idx


def readings_index(readings: pd.DataFrame | None) -> dict[tuple[str, str], dict]:
    if readings is None or readings.empty:
        return {}
    return {(r["photo_id"], r["question_id"]): r for r in readings.to_dict("records")}


def build_candidates(layers, assessment: pd.DataFrame, readings: pd.DataFrame | None, stage: int,
                     th: dict, run_id: str, osm_2180: gpd.GeoDataFrame | None = None,
                     photo_points: gpd.GeoDataFrame | None = None) -> tuple[pd.DataFrame, Counter]:
    """Zwraca (kandydaci, liczniki wykluczeń). Każda para (droga, atrybut) jest kandydatem albo wykluczeniem (AC-16)."""
    osm = layers.osm
    missing_classes = th["compare"]["missing_classes"]
    s = th["surface"]
    ov_idx = _overture_index(layers.overture, th)
    rd = readings_index(readings)
    excl: Counter = Counter()

    # zdjęcia połączone z drogą (bez kandydata → wykluczone z licznikiem, PRD §4.4)
    excl[EXCL_NO_CANDIDATE] = int((assessment["status"] == "no_candidate").sum())
    linked = assessment[assessment["status"].isin(["certain", "uncertain"])]
    photos_by_way: dict[int, list[dict]] = {}
    for r in linked.to_dict("records"):
        photos_by_way.setdefault(int(r["osm_way_id"]), []).append(r)

    attrs = ["speed", "surface"] + (["lit", "junction"] if stage == 2 else [])
    extract = layers.sources["osm"]["extract_date"]
    release = layers.sources["overture"]["release"]

    deg = None
    geo2180 = None
    if stage == 2:
        deg = node_degrees(osm)
        geo2180 = osm_2180 if osm_2180 is not None else osm[["osm_id", "geometry"]].to_crs(2180)
        geo2180 = dict(zip(geo2180["osm_id"], geo2180.geometry))
        pts = photo_points.set_index("photo_id").geometry if photo_points is not None else None

    rows = []
    cols = ["osm_id", "highway", "name", "osm_timestamp", "tags_dict", "node_ids", "boundary_crossing", "bridge", "tunnel", "layer"]
    for way in osm[cols].to_dict("records"):
        oid = int(way["osm_id"])
        tags = way["tags_dict"]
        hw = way["highway"]
        segs = ov_idx.get(oid, [])
        ov_ids = [sid for sid, _, _ in segs]
        wphotos = photos_by_way.get(oid, [])
        for attr in attrs:
            if attr in ("lit", "junction") and not wphotos:
                continue  # etap 2: tylko drogi połączone ze zdjęciem
            q = QUESTION_OF[attr]
            evid = []
            for p in wphotos:
                r = rd.get((p["photo_id"], q))
                if r is None:
                    evid.append(PhotoEvidence(p["photo_id"], p["status"], "model_unavailable", None, None))
                else:
                    evid.append(PhotoEvidence(p["photo_id"], p["status"], r["status"], r.get("answer"), r.get("final_stage")))
            if attr == "speed":
                o = nz.parse_osm_speed(tags)
                ov = aggregate_overture([sp for _, sp, _ in segs])
            elif attr == "surface":
                o = nz.parse_osm_surface(tags.get("surface"), s["osm_paved"], s["osm_unpaved"])
                ov = aggregate_overture([su for _, _, su in segs])
            elif attr == "lit":
                o = nz.parse_lit(tags.get("lit"))
                ov = None
            else:
                # skrzyżowanie: każde zdjęcie porównywane z mapą w swoim punkcie rzutu (ADR-001 §4.4)
                w = dict(way)
                w["geometry"] = geo2180[oid]
                vals = [map_junction(w, deg, pts.loc[p["photo_id"]], th["links"]["junction_radius_m"]) for p in wphotos]
                per_photo = [categorize(attr, hw, v, None, [e], missing_classes) for v, e in zip(vals, evid)]
                res = combine_results(per_photo)
                o = Normalized(vals[0].status if len({v.status for v in vals}) == 1 else "not_comparable",
                               ",".join(sorted({str(v.value) for v in vals if v.value is not None})) or None,
                               "junction", nz.to_json({e.photo_id: {"status": v.status, "value": v.value, "detail": v.detail}
                                                        for v, e in zip(vals, evid)}))
                ov = None
            if attr != "junction":
                res = categorize(attr, hw, o, ov, evid, missing_classes)
            if res.category is None:
                excl[f"{ATTRIBUTE_LABEL[attr]}: {res.exclusion}"] += 1
                continue
            key = candidate_key(oid, ov_ids, attr)
            readings_txt = [f"{e.photo_id}: {e.value} ({e.stage})" for e in evid if e.stage]
            rows.append({
                "candidate_id": candidate_id(run_id, key),
                "candidate_key": key,
                "run_id": run_id,
                "stage": STAGE_OF[attr],
                "osm_id": oid,
                "osm_url": f"https://www.openstreetmap.org/way/{oid}",
                "highway": hw,
                "name": way["name"] if isinstance(way["name"], str) else "",
                "overture_ids": ov_ids,
                "attribute": attr,
                "osm_raw": o.raw,
                "overture_raw": nz.to_json({sid: json.loads((sp if attr == "speed" else su).raw) for sid, sp, su in segs}) if attr in ("speed", "surface") else "",
                "osm_norm": "" if o.value is None else str(o.value),
                "overture_norm": "" if ov is None or ov.value is None else str(ov.value),
                "osm_status": o.status,
                "overture_status": "" if ov is None else ov.status,
                "photo_ids": [p["photo_id"] for p in wphotos],
                "link_status": [p["status"] for p in wphotos],
                "link_details": [link_detail(p) for p in wphotos],
                "photo_reading": "; ".join(readings_txt) if readings_txt else "brak odczytu modelu",
                "osm_timestamp": str(way["osm_timestamp"]),
                "osm_extract_date": extract,
                "overture_release": release,
                "category": res.category,
                "reasons": res.reasons,
                "reason_text": res.reason_text,
            })
    cand = pd.DataFrame(rows)
    return cand, excl
