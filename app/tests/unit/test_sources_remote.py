import json
import urllib.error

import pytest

from map_qa import sources_remote as sr


def test_statement_counts_five_tables_in_contract_order():
    sql = sr.build_statement()
    assert sql == " UNION ALL ".join(
        f"SELECT '{table}' AS source, count(*) AS rows FROM workspace.map_qa.{table}"
        for table in sr.TABLES
    )


def test_build_request_sets_api_contract():
    req = sr.build_request({
        "DATABRICKS_HOST": "https://example.cloud.databricks.com/",
        "DATABRICKS_TOKEN": "test-token-xyz",
        "DATABRICKS_SQL_WAREHOUSE_ID": "warehouse-1",
    })
    assert req.full_url == "https://example.cloud.databricks.com/api/2.0/sql/statements/"
    assert req.method == "POST"
    assert req.get_header("Authorization") == "Bearer test-token-xyz"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data) == {
        "warehouse_id": "warehouse-1", "statement": sr.build_statement(),
        "wait_timeout": "30s", "disposition": "INLINE", "format": "JSON_ARRAY",
    }


def test_build_request_accepts_host_without_scheme():
    req = sr.build_request({
        "DATABRICKS_HOST": "example.cloud.databricks.com",
        "DATABRICKS_TOKEN": "token", "DATABRICKS_SQL_WAREHOUSE_ID": "wh",
    })
    assert req.full_url.startswith("https://example.cloud.databricks.com/")


def test_missing_variables_reports_names_only():
    result = sr.fetch_counts(env={"DATABRICKS_TOKEN": "test-token-xyz"})
    assert result.status == "unavailable"
    assert result.reason == "brak zmiennych środowiskowych: DATABRICKS_HOST, DATABRICKS_SQL_WAREHOUSE_ID"
    assert "test-token-xyz" not in result.reason + repr(result)


def test_http_error_is_unavailable_without_leaking_token():
    def transport(_request):
        raise urllib.error.HTTPError("https://host", 403, "denied", {}, None)

    result = sr.fetch_counts(_env(), transport=transport)
    assert result.status == "unavailable" and result.reason == "błąd HTTP 403"
    assert "test-token-xyz" not in result.reason + repr(result)


@pytest.mark.parametrize("exc", [urllib.error.URLError("offline"), TimeoutError(), OSError()])
def test_connection_errors_are_unavailable(exc):
    result = sr.fetch_counts(_env(), transport=lambda _request: (_ for _ in ()).throw(exc))
    assert result.status == "unavailable"
    assert result.reason == f"błąd połączenia: {type(exc).__name__}"


def test_success_uses_injected_parser():
    result = sr.fetch_counts(_env(), transport=lambda _request: b"body", parser=lambda body: {"osm_roads": len(body)})
    assert result.status == "ok" and result.remote == {"osm_roads": 4}


def test_parser_error_is_unavailable():
    result = sr.fetch_counts(_env(), transport=lambda _request: b"body", parser=lambda _body: 1 / 0)
    assert result.status == "unavailable" and result.reason == "nieoczekiwany kształt odpowiedzi"


@pytest.mark.skip(reason="brak capture")
def test_parse_response_capture():
    assert sr.parse_response(b"captured response")


def test_compare_available_and_unavailable():
    available = sr.RemoteCounts("ok", "", {"osm_roads": 2, "photos": 3})
    rows = sr.compare({"osm_roads": 2, "photos": 4}, available)
    assert rows == [
        {"table": "osm_roads", "local": 2, "remote": 2, "match": True},
        {"table": "photos", "local": 4, "remote": 3, "match": False},
    ]
    rows = sr.compare({"osm_roads": 2}, sr.RemoteCounts("unavailable", "offline", {}))
    assert rows[0] == {"table": "osm_roads", "local": 2, "remote": None, "match": None}


def _env():
    return {
        "DATABRICKS_HOST": "example.cloud.databricks.com",
        "DATABRICKS_TOKEN": "test-token-xyz",
        "DATABRICKS_SQL_WAREHOUSE_ID": "warehouse-1",
    }
