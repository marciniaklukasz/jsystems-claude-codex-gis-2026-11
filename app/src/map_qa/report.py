from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import pandas as pd
from jinja2 import Environment, FileSystemLoader


_TEMPLATES = Path(__file__).with_name("templates")
_MD = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=False)
_HTML = Environment(loader=FileSystemLoader(_TEMPLATES), autoescape=True)


def _mdcell(value) -> str:
    """Komórka tabeli Markdown: escapowanie `|` i zamiana nowych linii (wartości surowe zostają w Parquet i CSV)."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


_MD.filters["mdcell"] = _mdcell
_LABELS = {"speed": "ograniczenie prędkości", "surface": "nawierzchnia", "lit": "oświetlenie", "junction": "skrzyżowanie"}


def _photo_href(local: str, run_dir: Path) -> str:
    """Ścieżka względna od katalogu runu; inny dysk (Windows) → absolutny URI file:///."""
    try:
        return os.path.relpath(local, run_dir).replace("\\", "/")
    except ValueError:
        return Path(local).resolve().as_uri()


def _thousands(value):
    return f"{int(value):,}".replace(",", " ")


def _safe(value):
    if isinstance(value, (list, dict, tuple)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    return None if value is None or pd.isna(value) else value


def _render_md(ctx) -> str:
    return _MD.get_template("report.md.j2").render(ctx)


def _render_html(ctx) -> str:
    return _HTML.get_template("report.html.j2").render(ctx)


def write_report(run_dir: Path, verify: Callable[[], None] | None = None) -> dict[str, Path]:
    run_dir = Path(run_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    candidates = pd.read_parquet(run_dir / "candidates.parquet")
    readings = pd.read_parquet(run_dir / "readings.parquet")
    records = [{k: _safe(v) for k, v in row.items()} for row in candidates.to_dict("records")]
    detailed = sorted((r for r in records if r.get("category") in ("rozbieżne", "do sprawdzenia")),
                      key=lambda r: (0 if r["category"] == "rozbieżne" else 1, r.get("attribute") or "", r.get("osm_id") or 0))
    for row in records:
        for key in ("overture_ids", "photo_ids", "link_status", "reasons", "link_details"):
            if not isinstance(row.get(key), list):
                row[key] = []
    for row in detailed:
        for key in ("overture_ids", "photo_ids", "link_status", "reasons", "link_details"):
            if not isinstance(row.get(key), list):
                row[key] = []
        row["photos"] = []
        for photo_id in row["photo_ids"]:
            attr = (run.get("photo_attribution") or {}).get(photo_id, {})
            local = attr.get("local_path")
            path = _photo_href(local, run_dir) if local and Path(local).exists() else None
            row["photos"].append({"id": photo_id, "path": path, **attr})
    summary = []
    for attr in sorted({r.get("attribute") for r in records if r.get("attribute")}):
        summary.append({"label": _LABELS.get(attr, attr), **{cat: sum(r.get("attribute") == attr and r.get("category") == cat for r in records) for cat in ("zgodne", "rozbieżne", "do sprawdzenia")}})
    ctx = {"run": run, "input_counts": run.get("input_counts", {}), "link_counts": run.get("link_counts", {}),
           "exclusions": run.get("exclusions", {}), "limitations": run.get("limitations", []), "summary": summary,
           "candidates": detailed, "readings": readings.to_dict("records"),
           "empty": not detailed, "thousands": _thousands}
    targets = {"md": run_dir / "report.md", "html": run_dir / "report.html", "csv": run_dir / "candidates.csv"}
    temps = {key: run_dir / (path.name + ".tmp") for key, path in targets.items()}
    created = []
    try:
        temps["md"].write_text(_render_md(ctx), encoding="utf-8")
        temps["html"].write_text(_render_html(ctx), encoding="utf-8")
        csv_rows = []
        for row in detailed:
            csv_rows.append({k: json.dumps(v, ensure_ascii=False) if k in ("overture_ids", "photo_ids", "link_status", "reasons") else v for k, v in row.items() if k != "photos"})
        columns = list(candidates.columns)
        pd.DataFrame(csv_rows, columns=columns).to_csv(temps["csv"], index=False, encoding="utf-8-sig")
        if verify:
            verify()
        for key in targets:
            temps[key].replace(targets[key])
            created.append(targets[key])
        return targets
    except Exception:
        for path in [*temps.values(), *created]:
            path.unlink(missing_ok=True)
        raise
