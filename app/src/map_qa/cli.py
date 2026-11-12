"""CLI `map-qa`: `check` i `compare-counts` (ADR-000 §6)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from map_qa import compare, config, ingest, matching, report, sources_remote, store
from map_qa.config import ArgumentValidationError, Limits, resolve_repo_path, validate_limits

CATEGORIES = ("zgodne", "rozbieżne", "do sprawdzenia")


class _PolishParser(argparse.ArgumentParser):
    def error(self, message):  # komunikat po polsku i kod 2 (ADR-000 §6)
        raise ArgumentValidationError(message)


def _parser() -> argparse.ArgumentParser:
    p = _PolishParser(prog="map-qa", description="Kontrola mapy: drogi OSM i Overture a zdjęcia ulic Krakowa")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_PolishParser)
    c = sub.add_parser("check", help="Uruchom kontrolę etapu")
    c.add_argument("--stage", type=int, choices=(1, 2), required=True, help="etap: 1 (prędkość, nawierzchnia) lub 2 (także oświetlenie, skrzyżowanie)")
    c.add_argument("--decision-limit", type=int, default=0, help="limit żądań modelu głównego (0–25)")
    c.add_argument("--comparison-limit", type=int, default=0, help="limit żądań modelu porównawczego (0–5)")
    c.add_argument("--fallback-limit", type=int, default=0, help="limit żądań modelu drugiego stopnia (0–10)")
    c.add_argument("--max-cost-usd", type=float, default=0.0, help="łączny limit kosztu w USD")
    c.add_argument("--out", default=str(config.DEFAULT_OUT_DIR), help="katalog wyników")
    c.add_argument("--data-dir", default=str(config.DEFAULT_DATA_DIR), help="katalog danych wejściowych")
    c.add_argument("--db", default=str(config.DEFAULT_DB), help="plik SQLite (decyzje, cache, budżet)")
    sub.add_parser("compare-counts", help="Porównaj liczności plików z tabelami Databricks")
    return p


def _log(msg: str) -> None:
    print(msg, flush=True)


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        args = _parser().parse_args(argv)
        if args.command == "compare-counts":
            return compare_counts()
        limits = Limits(args.decision_limit, args.comparison_limit, args.fallback_limit, args.max_cost_usd)
        validate_limits(limits)
    except ArgumentValidationError as exc:
        print(f"Błędne argumenty: {exc}", file=sys.stderr)
        return 2
    except SystemExit as exc:  # --help
        return int(exc.code or 0)
    return check(args.stage, limits, resolve_repo_path(args.out), resolve_repo_path(args.data_dir), resolve_repo_path(args.db))


# --- check -------------------------------------------------------------------------------
def _thresholds_commit() -> str:
    try:
        rel = config.THRESHOLDS_PATH.relative_to(config.REPO_ROOT).as_posix()
        h = subprocess.run(["git", "log", "-1", "--format=%h", "--", rel], cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", rel], cwd=config.REPO_ROOT, timeout=10).returncode != 0
        return (h or "brak commitu") + (" (+niezatwierdzone zmiany)" if dirty else "")
    except Exception:  # brak gita nie blokuje kontroli
        return "nieznany"


def _photo_paths(data_dir: Path, photos: pd.DataFrame) -> dict[str, str | None]:
    out = {}
    for pid, fn in zip(photos["photo_id"], photos["filename"]):
        path = None
        for cand in (data_dir / "offline" / fn, data_dir / "data" / "photos" / fn):
            if cand.exists():
                path = str(cand)
                break
        out[pid] = path
    return out


def _sources_meta(src: dict) -> list[dict]:
    return [
        {"name": "OpenStreetMap (Geofabrik małopolskie)", "version": src["osm"]["source"], "date": src["osm"]["extract_date"], "license": src["osm"]["license"]},
        {"name": "Overture Maps transportation/segment", "version": src["overture"]["release"], "date": src["overture"]["release"][:10], "license": src["overture"]["license"]},
        {"name": "Zdjęcia Panoramax i Mapillary (photos.csv)", "version": f"{src['photos']['rows']} zdjęć", "date": src["created_at"], "license": src["photos"]["license"]},
        {"name": "Znaki Mapillary (traffic_signs.geojson)", "version": f"{src['mapillary']['signs']} znaków", "date": src["created_at"], "license": src["mapillary"]["sign_license"]},
        {"name": "Etykiety referencyjne (reference_labels.csv)", "version": f"{src['reference']['images']} zdjęć", "date": src["created_at"], "license": "—"},
    ]


def _run_id(stage: int, limits: Limits) -> str:
    now = datetime.now(timezone.utc)
    h = hashlib.sha256(f"{now.isoformat()}|{stage}|{limits}|{os.getpid()}".encode()).hexdigest()[:6]
    return f"{now:%Y%m%dT%H%M%SZ}-{h}"


def check(stage: int, limits: Limits, out_dir: Path, data_dir: Path, db_path: Path) -> int:
    t0 = time.monotonic()
    partial: Path | None = None
    try:
        _log(f"Kontrola etapu {stage}: weryfikacja plików wejściowych ({data_dir})")
        ingest.verify_inputs(data_dir)
        layers = ingest.load_layers(data_dir)
        counts = {"osm_roads": len(layers.osm), "overture_segments": len(layers.overture),
                  "photos": len(layers.photos), "traffic_signs": layers.traffic_signs_count}
        _log(f"Wczytano: drogi OSM {_fmt(counts['osm_roads'])}, segmenty Overture {_fmt(counts['overture_segments'])}, "
             f"zdjęcia {_fmt(counts['photos'])}, znaki ograniczeń {_fmt(counts['traffic_signs'])}")

        th = config.load_thresholds()
        run_id = _run_id(stage, limits)
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        out_dir.mkdir(parents=True, exist_ok=True)
        partial = out_dir / f".{run_id}.partial"
        partial.mkdir()

        _log("Przeliczanie warstw do EPSG:2180 i ocena połączeń zdjęcie–droga")
        osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
        assessment = matching.assess_links(layers.links, layers.photos, osm2180, th["links"])
        lc = matching.link_counts(assessment)
        _log(f"Połączenia: pewne {lc['certain']}, niepewne {lc['uncertain']}, bez kandydata {lc['no_candidate']} (zdjęcia bez kierunku: {lc['missing_heading']})")

        conn = store.connect(db_path)
        vision_result = _run_vision(conn, run_id, stage, limits, th, layers, assessment, data_dir, partial)
        readings = vision_result["readings"]

        _log("Porównanie atrybutów i nadawanie kategorii")
        points = matching.photo_points_2180(layers.photos)
        cand, excl = compare.build_candidates(layers, assessment, readings, stage, th, run_id,
                                              osm_2180=osm2180, photo_points=points)

        photo_paths = _photo_paths(data_dir, layers.photos)
        photo_paths.update(vision_result.get("photo_paths", {}))
        listed = cand[cand["category"] != "zgodne"] if len(cand) else cand
        referenced = {p for ids in listed["photo_ids"] for p in ids} if len(listed) else set()
        referenced |= set(readings["photo_id"])
        attrib_src = layers.photos.set_index("photo_id")
        attribution = {}
        for pid in sorted(referenced):
            if pid in attrib_src.index:
                r = attrib_src.loc[pid]
                attribution[pid] = {"author": r["author"], "license": r["license"], "source_url": r["source_url"], "local_path": photo_paths.get(pid)}
            elif pid in vision_result.get("attribution", {}):
                attribution[pid] = vision_result["attribution"][pid]

        limitations = [{"source": "Databricks", "reason": "nie odpytywany w kontroli (D-02); liczności: `map-qa compare-counts`"}]
        limitations.append({"source": "OpenRouter", "reason": vision_result["openrouter_state"]})

        summary = {a: {c: int(((cand["attribute"] == a) & (cand["category"] == c)).sum()) for c in CATEGORIES}
                   for a in (sorted(set(cand["attribute"])) if len(cand) else [])}
        run_meta = {
            "run_id": run_id, "stage": stage, "created_at": created_at, "crs": "EPSG:2180",
            "questions_version": th["vision"]["questions_version"], "thresholds_commit": _thresholds_commit(),
            "sources": _sources_meta(layers.sources), "input_counts": counts, "link_counts": lc,
            "exclusions": dict(sorted(excl.items())), "limitations": limitations,
            "limits": {"decision": limits.decision, "comparison": limits.comparison, "fallback": limits.fallback, "max_cost_usd": limits.max_cost_usd},
            "usage": vision_result["usage"], "cost_total_usd": vision_result["cost_total_usd"], "requests_total": vision_result["requests_total"],
            "vision_summary": vision_result["vision_summary"], "evaluation": vision_result["evaluation"],
            "comparison": vision_result.get("comparison", []),
            "evaluation_thresholds": {"min_coverage": th["evaluation"]["min_coverage"], "min_accuracy": th["evaluation"]["min_accuracy"],
                                      "met": vision_result.get("evaluation_thresholds_met", {})},
            "photo_attribution": attribution, "summary": summary,
        }
        cand.to_parquet(partial / "candidates.parquet")
        assessment.to_parquet(partial / "links.parquet")  # LinkAssessment (ADR-000 §5.2)
        readings.to_parquet(partial / "readings.parquet")
        (partial / "run.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=1), encoding="utf-8")

        _log("Zapis raportu Markdown, HTML i CSV; końcowa kontrola hashy wejść")
        report.write_report(partial, verify=lambda: ingest.verify_inputs(data_dir))
        final = out_dir / run_id
        # zapis runu przed publikacją: błąd SQLite → kod 3 i brak opublikowanego raportu (R-A, ADR-000 §6)
        store.record_run(conn, run_id, stage, created_at, th["vision"]["questions_version"], "ok", {"run_dir": str(final), "summary": summary})
        try:
            partial.rename(final)
        except OSError:
            store.record_run(conn, run_id, stage, created_at, th["vision"]["questions_version"], "failed", {"run_dir": None})
            raise
        partial = None
        conn.close()

        _log("")
        _log(f"Wynik kontroli {run_id} (etap {stage}):")
        for a, c in summary.items():
            _log(f"  {compare.ATTRIBUTE_LABEL[a]}: zgodne {_fmt(c['zgodne'])}, rozbieżne {_fmt(c['rozbieżne'])}, do sprawdzenia {_fmt(c['do sprawdzenia'])}")
        _log(f"  wykluczenia: {_fmt(sum(excl.values()))} (szczegóły w raporcie)")
        _log(f"  żądania do modeli: {vision_result['requests_total']}, koszt: {vision_result['cost_total_usd']:.4f} USD")
        _log(f"  raport: {final / 'report.md'}")
        _log(f"  raport HTML: {final / 'report.html'}")
        _log(f"  CSV: {final / 'candidates.csv'}")
        _log(f"  czas: {time.monotonic() - t0:.0f} s")
        return 0
    except ingest.InputIntegrityError as exc:
        print(f"Błąd integralności danych: {exc} Kontrola przerwana, raport nie powstał.", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — kod 3 dla nieoczekiwanego błędu
        print(f"Nieoczekiwany błąd: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    finally:
        if partial is not None and partial.exists():
            shutil.rmtree(partial, ignore_errors=True)


def _run_vision(conn, run_id, stage, limits, th, layers, assessment, data_dir, run_dir) -> dict:
    """Bez budżetu: zero żądań, brak manifestu (AC-19b, AC-21). Z limitem: próbka, kaskada, ewaluacja (ADR-002)."""
    from map_qa import evaluation, vision

    if not limits.any_positive():
        result = vision.run_vision(conn, run_id=run_id, stage=stage, limits=limits, th=th, layers=layers,
                                   assessment=assessment, data_dir=data_dir, run_dir=run_dir, labels=None)
        result["openrouter_state"] = ("brak budżetu (limity 0) — nie wysłano żadnego żądania; "
                                      "pary ze zdjęciem jako jedynym dowodem: model_unavailable")
        result["evaluation"] = {}
        return result
    labels = evaluation.load_labels(data_dir)
    signs = pd.read_csv(data_dir / "signs" / "signs.csv", encoding="utf-8")
    nearest = pd.read_csv(data_dir / "signs" / "nearest_osm.csv", dtype=str, keep_default_na=False, encoding="utf-8")
    osm2180 = layers.osm[["osm_id", "highway", "access", "motor_vehicle", "geometry"]].to_crs(2180)
    sign_links = matching.assess_sign_links(nearest, signs, osm2180, th["links"])
    _log(f"Odczyt zdjęć modelami: limity {limits.decision}/{limits.comparison}/{limits.fallback}, maks. koszt {limits.max_cost_usd} USD")
    result = vision.run_vision(conn, run_id=run_id, stage=stage, limits=limits, th=th, layers=layers,
                               assessment=assessment, data_dir=data_dir, run_dir=run_dir, labels=labels,
                               sign_links=sign_links)
    comparison = pd.DataFrame(result.get("comparison") or [])
    ev = evaluation.evaluate(result["readings"], labels, comparison if len(comparison) else None)
    result["evaluation"] = ev
    result["evaluation_thresholds_met"] = evaluation.thresholds_met(ev, th)
    _log(f"Żądania do modeli: {result['requests_total']}, koszt {result['cost_total_usd']:.6f} USD")
    return result


# --- compare-counts ------------------------------------------------------------------------
def compare_counts() -> int:
    data_dir = config.DEFAULT_DATA_DIR
    ingest.verify_inputs(data_dir)
    layers = ingest.load_layers(data_dir)
    local = {"osm_roads": len(layers.osm), "overture_segments": len(layers.overture), "photos": len(layers.photos),
             "photo_road_links": len(layers.links), "traffic_signs": layers.traffic_signs_count}
    remote = sources_remote.fetch_counts()
    rows = sources_remote.compare(local, remote)
    _log("Liczności: pliki lokalne a Databricks workspace.map_qa")
    _log(f"{'tabela':<20} {'plik':>10} {'Databricks':>12}  zgodność")
    for r in rows:
        rem = "—" if r["remote"] is None else _fmt(r["remote"])
        ok = "—" if r["match"] is None else ("✓" if r["match"] else "✗")
        _log(f"{r['table']:<20} {_fmt(r['local']):>10} {rem:>12}  {ok}")
    if remote.status != "ok":
        _log(f"Ograniczenia: Databricks — {remote.reason}")
    return 0


def entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
