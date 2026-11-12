"""Optional Databricks row counts for ``map-qa compare-counts``."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping

TABLES = ["osm_roads", "overture_segments", "photos", "photo_road_links", "traffic_signs"]
REQUIRED_VARS = ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_SQL_WAREHOUSE_ID")


@dataclass
class RemoteCounts:
    status: str
    reason: str
    remote: dict[str, int]


def build_statement() -> str:
    return " UNION ALL ".join(
        f"SELECT '{table}' AS source, count(*) AS rows FROM workspace.map_qa.{table}"
        for table in TABLES
    )


def build_request(env: Mapping[str, str]) -> urllib.request.Request:
    host = env["DATABRICKS_HOST"].removeprefix("https://").removeprefix("http://").rstrip("/")
    payload = {
        "warehouse_id": env["DATABRICKS_SQL_WAREHOUSE_ID"],
        "statement": build_statement(),
        "wait_timeout": "30s",
        "disposition": "INLINE",
        "format": "JSON_ARRAY",
    }
    return urllib.request.Request(
        f"https://{host}/api/2.0/sql/statements/",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {env['DATABRICKS_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def parse_response(body: bytes) -> dict[str, int]:
    response = json.loads(body)
    if response["status"]["state"] != "SUCCEEDED":
        raise ValueError("statement did not succeed")
    rows = response["result"]["data_array"]
    counts = {str(row[0]): int(row[1]) for row in rows}
    if set(counts) != set(TABLES):
        raise ValueError("unexpected table rows")
    return counts


def fetch_counts(
    env: Mapping[str, str] = os.environ,
    transport: Callable[[urllib.request.Request], bytes] | None = None,
    parser: Callable[[bytes], dict[str, int]] | None = None,
) -> RemoteCounts:
    missing = [name for name in REQUIRED_VARS if not env.get(name)]
    if missing:
        return RemoteCounts("unavailable", f"brak zmiennych środowiskowych: {', '.join(missing)}", {})

    request = build_request(env)
    if transport is None:
        transport = lambda req: urllib.request.urlopen(req, timeout=40).read()
    try:
        body = transport(request)
    except urllib.error.HTTPError as exc:
        return RemoteCounts("unavailable", f"błąd HTTP {exc.code}", {})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return RemoteCounts("unavailable", f"błąd połączenia: {type(exc).__name__}", {})

    try:
        remote = (parser or parse_response)(body)
    except Exception:
        return RemoteCounts("unavailable", "nieoczekiwany kształt odpowiedzi", {})
    return RemoteCounts("ok", "", remote)


def compare(local: dict[str, int], remote: RemoteCounts) -> list[dict]:
    return [
        {
            "table": table,
            "local": local.get(table),
            "remote": remote.remote.get(table) if remote.status == "ok" else None,
            "match": (local.get(table) == remote.remote.get(table)) if remote.status == "ok" else None,
        }
        for table in TABLES if table in local
    ]
