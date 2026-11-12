from __future__ import annotations

import argparse
import sys

from map_qa import ingest
from map_qa.config import DEFAULT_DATA_DIR, DEFAULT_DB, DEFAULT_OUT_DIR, ArgumentValidationError, Limits, resolve_repo_path, validate_limits

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="map-qa", description="Kontrola jakości mapy")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Sprawdź dane mapy")
    check.add_argument("--stage", choices=("1", "2"), required=True)
    check.add_argument("--decision-limit", type=int, default=0)
    check.add_argument("--comparison-limit", type=int, default=0)
    check.add_argument("--fallback-limit", type=int, default=0)
    check.add_argument("--max-cost-usd", type=float, default=0.0)
    check.add_argument("--out", default=DEFAULT_OUT_DIR)
    check.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    check.add_argument("--db", default=DEFAULT_DB)
    sub.add_parser("compare-counts", help="Porównaj liczności")
    return parser

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        print("Błędne argumenty.", file=sys.stderr)
        return 2 if exc.code else 0
    if args.command == "compare-counts":
        print("Ograniczenia: Databricks — nie zaimplementowane w T1.3")
        return 0
    limits = Limits(args.decision_limit, args.comparison_limit, args.fallback_limit, args.max_cost_usd)
    try:
        validate_limits(limits)
    except ArgumentValidationError as exc:
        print(f"Błędne argumenty: {exc}", file=sys.stderr)
        return 2
    data_dir = resolve_repo_path(args.data_dir)
    resolve_repo_path(args.out)
    resolve_repo_path(args.db)
    try:
        ingest.verify_inputs(data_dir)
        layers = ingest.load_layers(data_dir)
        ingest.verify_inputs(data_dir)
    except ingest.InputIntegrityError as exc:
        print(f"Błąd integralności danych: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Nieoczekiwany błąd: {exc}", file=sys.stderr)
        return 3
    print(f"Drogi OSM: {len(layers.osm)}")
    print(f"Segmenty Overture: {len(layers.overture)}")
    print(f"Zdjęcia: {len(layers.photos)}")
    print(f"Znaki ograniczeń (traffic_signs): {layers.traffic_signs_count}")
    return 0
