"""Jednorazowy capture odpowiedzi Databricks SQL Statement Execution API (T4.5, AGENTS.md: mock tylko z capture).

Uruchomienie z app/: uv run python scripts/capture_databricks.py
Jedno żądanie SELECT count(*) (tylko odczyt). Zapisuje status, dozwolone nagłówki i pełne ciało odpowiedzi;
nie zapisuje nagłówków żądania, hosta, tokenu ani identyfikatora warehouse.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "src"))
from map_qa import sources_remote  # noqa: E402

ALLOWED_HEADERS = {"content-type", "date", "x-request-id"}
OUT = APP / "tests" / "fixtures" / "captures"


def main() -> int:
    missing = [v for v in sources_remote.REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        print("Brak zmiennych:", ", ".join(missing))
        return 1
    req = sources_remote.build_request(os.environ)
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            status, headers, body = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, dict(e.headers), e.read()
    secrets = [os.environ["DATABRICKS_TOKEN"], os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/"),
               os.environ["DATABRICKS_SQL_WAREHOUSE_ID"]]
    text = body.decode("utf-8")
    for s in secrets:
        if s and s in text:
            text = text.replace(s, "<redacted>")
    capture = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target": "Databricks SQL Statement Execution API 2.0 POST /api/2.0/sql/statements/ (host redacted)",
        "request": {"statement": sources_remote.build_statement(), "wait_timeout": "30s", "disposition": "INLINE", "format": "JSON_ARRAY"},
        "status": status,
        "headers": {k.lower(): v for k, v in headers.items() if k.lower() in ALLOWED_HEADERS},
        "body": json.loads(text),
    }
    serialized = json.dumps(capture, ensure_ascii=False, indent=1)
    assert not any(s and s in serialized for s in secrets), "sekret w capture"
    assert "authorization" not in serialized.lower()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{datetime.now(timezone.utc):%Y-%m-%d}_databricks_statement_counts.json"
    path.write_text(serialized, encoding="utf-8")
    print("status", status, "->", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
