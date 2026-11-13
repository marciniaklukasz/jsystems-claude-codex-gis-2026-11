"""Dane i prezentacyjne przekształcenia dashboardu (bez zależności od Streamlit)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from map_qa import config, store
from map_qa.compare import ATTRIBUTE_LABEL, QUESTION_OF, STAGE_OF


@dataclass
class RunData:
    run: dict
    candidates: pd.DataFrame
    readings: pd.DataFrame
    run_dir: Path


def latest_run(runs_dir: str | Path) -> Path | None:
    root = Path(runs_dir)
    if not root.is_dir():
        return None
    runs = sorted((p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".") and (p / "run.json").is_file()), key=lambda p: p.name)
    return runs[-1] if runs else None


def _lists(df: pd.DataFrame) -> pd.DataFrame:
    for col in ("overture_ids", "photo_ids", "link_status", "reasons"):
        if col in df:
            df[col] = df[col].map(lambda v: v if isinstance(v, list) else ([] if v is None else v.tolist() if hasattr(v, "tolist") else list(v) if isinstance(v, tuple) else []))
    return df


def load_run(run_dir: str | Path) -> RunData:
    path = Path(run_dir)
    return RunData(json.loads((path / "run.json").read_text(encoding="utf-8")),
                   _lists(pd.read_parquet(path / "candidates.parquet")), pd.read_parquet(path / "readings.parquet"), path)


def filter_candidates(df, attributes=None, categories=None, stages=None, reasons=None):
    result = df
    if attributes:
        result = result[result.attribute.isin(attributes)]
    if categories:
        result = result[result.category.isin(categories)]
    if stages:
        wanted = {int(s) for s in stages}
        result = result[result.attribute.map(STAGE_OF).isin(wanted)]
    if reasons:
        wanted = set(reasons)
        result = result[result.reasons.map(lambda rs: bool(wanted.intersection(rs or [])))]
    return result.copy()


def review_table(df, decisions: dict) -> pd.DataFrame:
    rows = []
    for r in df.to_dict("records"):
        d = decisions.get(r["candidate_key"], {})
        rows.append({"kategoria": r["category"], "atrybut": ATTRIBUTE_LABEL.get(r["attribute"], r["attribute"]),
                     "etap": STAGE_OF[r["attribute"]], "OSM id": r["osm_id"], "nazwa": r.get("name", ""),
                     "OSM": r.get("osm_norm", ""), "Overture": r.get("overture_norm", ""),
                     "przyczyny": ", ".join(r.get("reasons") or []),
                     "decyzja": store.DECISION_LABEL.get(d.get("decision"), ""), "autor": d.get("author", ""),
                     "czas": d.get("decided_at", ""), "candidate_id": r["candidate_id"]})
    return pd.DataFrame(rows, columns=["kategoria", "atrybut", "etap", "OSM id", "nazwa", "OSM", "Overture", "przyczyny", "decyzja", "autor", "czas", "candidate_id"])


def photo_bytes(path) -> bytes | None:
    if not path or str(path).lower().startswith(("http://", "https://")):
        return None
    p = Path(path)
    return p.read_bytes() if p.is_file() else None


def candidate_detail(row, data: RunData) -> dict:
    r = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    attribute = r["attribute"]
    readings = data.readings[data.readings.photo_id.isin(r.get("photo_ids") or [])]
    readings = readings[readings.question_id == QUESTION_OF[attribute]]
    by_photo = {x["photo_id"]: x for x in readings.to_dict("records")}
    attrs = data.run.get("photo_attribution", {})
    photos = []
    for i, pid in enumerate(r.get("photo_ids") or []):
        a = attrs.get(pid, {})
        caption = " · ".join(str(a.get(k) or "") for k in ("author", "license", "source_url"))
        reading = by_photo.get(pid)
        if reading:
            stage = reading.get("final_stage")
            stage_label = {"decision": "model decyzyjny", "comparison": "drugi stopień", "fallback": "drugi stopień", "manual": "kolejka ręczna"}.get(stage, stage or "kolejka ręczna")
            text = f'{reading.get("answer")} (stopień: {stage_label}, {reading.get("model") or ""})'
        else:
            text = "brak odczytu modelu"
        b = photo_bytes(a.get("local_path"))
        photos.append({"photo_id": pid, "caption": caption, "image_bytes": b,
                       "unavailable_text": "" if b is not None else "Zdjęcie niedostępne",
                       "link_text": "połączenie pewne" if (r.get("link_status") or [])[i] == "certain" else "połączenie niepewne", "reading": text})
    return {"osm": {"raw": r.get("osm_raw", ""), "value": r.get("osm_norm", ""), "date": r.get("osm_timestamp", "")},
            "overture": {"raw": r.get("overture_raw", ""), "value": r.get("overture_norm", ""), "release": r.get("overture_release", "")},
            "reasons": r.get("reasons") or [], "reason_text": r.get("reason_text", ""), "category": r.get("category", ""),
            "osm_url": r.get("osm_url") or f'https://www.openstreetmap.org/way/{r["osm_id"]}', "photos": photos}


def to_fix(data: RunData, confirmed: list[dict]) -> pd.DataFrame:
    indexed = {r["candidate_key"]: r for r in data.candidates.to_dict("records")}
    rows = []
    for d in confirmed:
        key = d["candidate_key"]
        r = indexed.get(key)
        parts = key.split("|")
        oid = r.get("osm_id") if r else parts[0]
        attr = r.get("attribute") if r else parts[-1]
        photos = (r.get("photo_ids") or []) if r else []
        a = data.run.get("photo_attribution", {}).get(photos[0], {}) if photos else {}
        caption = " · ".join(str(a.get(k) or "") for k in ("author", "license", "source_url")) if a else ""
        rows.append({"OSM": f"https://www.openstreetmap.org/way/{oid}", "atrybut": ATTRIBUTE_LABEL.get(attr, attr),
                     "obecna wartość": (r.get("osm_norm") or r.get("osm_raw", "")) if r else "", "wartość proponowana": d.get("proposed_value") or "",
                     "zdjęcie": caption, "komentarz": d.get("comment", ""), "autor": d.get("author", ""), "czas": d.get("decided_at", ""),
                     "uwagi": "" if r else "brak w bieżącym runie"})
    return pd.DataFrame(rows, columns=["OSM", "atrybut", "obecna wartość", "wartość proponowana", "zdjęcie", "komentarz", "autor", "czas", "uwagi"])


def to_fix_photos(data: RunData, confirmed: list[dict]) -> list[dict]:
    """Zdjęcia potwierdzonych przypadków: bajty tylko z plików lokalnych (AC-30) i podpis atrybucji (AC-25)."""
    indexed = {r["candidate_key"]: r for r in data.candidates.to_dict("records")}
    out = []
    for d in confirmed:
        r = indexed.get(d["candidate_key"])
        if not r:
            continue
        for pid in list(r.get("photo_ids") or []):
            a = data.run.get("photo_attribution", {}).get(pid, {})
            out.append({
                "photo_id": pid,
                "label": f'droga {r["osm_id"]} · {ATTRIBUTE_LABEL.get(r["attribute"], r["attribute"])}',
                "caption": " · ".join(str(a.get(k) or "") for k in ("author", "license", "source_url")),
                "image_bytes": photo_bytes(a.get("local_path")),
            })
    return out
