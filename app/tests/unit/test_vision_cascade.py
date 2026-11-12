"""ADR-002 §4.3–4.9, §8; PRD AC-19, AC-19b, AC-20, AC-20a–AC-20f, AC-21, AC-22; TAC-002-01.

Transport testowy zwraca wyłącznie ciała z capture (vision_support.py, TAC-002-04).
"""

from __future__ import annotations

import pandas as pd
import pytest

from map_qa import config, store, vision
from map_qa.config import Limits

from vision_support import DECISIONS_JEV, DECISIONS_LUNA, FakeTransport, NoNetwork, body, chat_body, decision_body, jpeg_bytes

TH = config.load_thresholds()
JEV, LUNA_D, LUNA = TH["vision"]["decision_model"], TH["vision"]["comparison_model"], TH["vision"]["fallback_model"]
SURE = {"paved": 1, "unpaved": 0, "unknown": 0}
UNSURE = {"paved": 0.5, "unpaved": 0.5, "unknown": 0}


def manifest(n: int, qid: str = "surface") -> pd.DataFrame:
    return pd.DataFrame([{"photo_id": f"p{i}", "question_id": qid, "split": "validation", "sequence": f"s{i}",
                          "image_sha256": f"sha{i}", "order": i} for i in range(n)])


def images(n: int) -> dict:
    return {f"sha{i}": jpeg_bytes(300, 300) for i in range(n)}


@pytest.fixture()
def conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def run(conn, m, transport, limits, links=None, run_id="R1"):
    return vision.run_cascade(conn, run_id=run_id, manifest=m, images=images(len(m)), links=links or {},
                              limits=limits, th=TH, transport=transport)


def by_photo(res):
    return res.readings.set_index("photo_id")


def test_limit_zero_no_requests_model_unavailable(conn):  # AC-19b, AC-21, §8 „Limit 0”
    t = NoNetwork()
    res = run(conn, manifest(3), t, Limits())
    assert t.calls == []
    assert set(res.readings["final_stage"]) == {"manual"} and set(res.readings["status"]) == {"model_unavailable"}


def test_confident_decision_final(conn):  # AC-20e/f
    t = FakeTransport([body(DECISIONS_JEV)])
    res = run(conn, manifest(1), t, Limits(decision=1, max_cost_usd=1))
    r = by_photo(res).loc["p0"]
    assert (r["final_stage"], r["status"], r["answer"], r["model"]) == ("decision", "certain", "paved", JEV)
    assert [c[0] for c in t.calls] == ["decisions"]


def test_limit_with_failures_counts_all(conn):  # AC-19, §8 „Limit z błędami”, TAC-002-01
    t = FakeTransport([vision.TransportError(503, "ServiceUnavailable")])
    res = run(conn, manifest(4), t, Limits(decision=3, max_cost_usd=1))
    # pierwszy błąd wyłącza model (AC-20) — kolejne pary bez żądań
    assert len(t.calls) == 1
    u = store.budget_usage(conn, "R1")[JEV]
    assert u["sent"] == len([c for c in t.calls if c[0] == "decisions"]) == 1 and u["errors"] == 1 and u["disabled"]
    assert set(res.readings["status"]) == {"model_unavailable"}


def test_limit_counts_successes(conn):
    t = FakeTransport([decision_body("paved", SURE) for _ in range(3)])
    res = run(conn, manifest(4), t, Limits(decision=3, max_cost_usd=1))
    assert len(t.calls) == 3
    assert store.budget_usage(conn, "R1")[JEV]["sent"] == 3
    assert by_photo(res).loc["p3", "status"] == "model_unavailable"


def test_error_escalates_to_fallback(conn):  # AC-20, §8 „Wyłączenie po błędzie”
    t = FakeTransport([vision.TransportError(503, "ServiceUnavailable"), chat_body('{"answer":"unpaved"}')])
    res = run(conn, manifest(1), t, Limits(decision=1, fallback=1, max_cost_usd=1))
    r = by_photo(res).loc["p0"]
    assert (r["final_stage"], r["answer"], r["model"]) == ("fallback", "unpaved", LUNA)
    assert [c[0] for c in t.calls] == ["decisions", "chat"]


def test_unsure_escalates_once_then_abstain(conn):  # AC-20b, AC-20d
    t = FakeTransport([decision_body("paved", UNSURE), chat_body('{"answer":"unknown"}')])
    res = run(conn, manifest(1), t, Limits(decision=1, fallback=5, max_cost_usd=1))
    r = by_photo(res).loc["p0"]
    assert (r["final_stage"], r["status"]) == ("manual", "abstain")
    assert len(t.calls) == 2


@pytest.mark.parametrize("content", ["", "not json", '{"answer":"gravel"}'])
def test_fallback_bad_output_model_unavailable(conn, content):
    t = FakeTransport([decision_body("paved", UNSURE), chat_body(content)])
    r = by_photo(run(conn, manifest(1), t, Limits(decision=1, fallback=1, max_cost_usd=1))).loc["p0"]
    assert (r["final_stage"], r["status"]) == ("manual", "model_unavailable")


def test_fallback_limit_zero_goes_manual(conn):  # AC-20c
    t = FakeTransport([decision_body("paved", UNSURE)])
    r = by_photo(run(conn, manifest(1), t, Limits(decision=1, max_cost_usd=1))).loc["p0"]
    assert (r["final_stage"], r["status"]) == ("manual", "model_unavailable")
    assert len(t.calls) == 1


def test_uncertain_link_escalates_even_if_confident(conn):  # AC-20a, §8 „Połączenie niepewne”
    t = FakeTransport([decision_body("paved", SURE), chat_body('{"answer":"paved"}')])
    res = run(conn, manifest(1), t, Limits(decision=1, fallback=1, max_cost_usd=1), links={"p0": "uncertain"})
    r = by_photo(res).loc["p0"]
    assert [c[0] for c in t.calls] == ["decisions", "chat"]
    assert r["final_stage"] == "fallback" and r["link_status"] == "uncertain"


def test_cache_second_run_no_requests(conn):  # AC-22, §8 „Cache”
    run(conn, manifest(2), FakeTransport([decision_body("paved", SURE), decision_body("unpaved", SURE)]), Limits(decision=2, max_cost_usd=1))
    t2 = NoNetwork()
    res = run(conn, manifest(2), t2, Limits(decision=2, max_cost_usd=1), run_id="R2")
    assert t2.calls == []
    assert res.readings["cache_hit"].all()
    assert by_photo(res).loc["p1", "answer"] == "unpaved"
    assert store.budget_usage(conn, "R2").get(JEV, {"sent": 0})["sent"] == 0


def test_cache_invalidated_by_questions_version(conn, monkeypatch):
    run(conn, manifest(1), FakeTransport([decision_body("paved", SURE)]), Limits(decision=1, max_cost_usd=1))
    th2 = {**TH, "vision": {**TH["vision"], "questions_version": 2}}
    t = FakeTransport([decision_body("paved", SURE)])
    vision.run_cascade(conn, run_id="R2", manifest=manifest(1), images=images(1), links={}, limits=Limits(decision=1, max_cost_usd=1), th=th2, transport=t)
    assert len(t.calls) == 1


def test_errors_not_cached(conn):
    run(conn, manifest(1), FakeTransport([vision.TransportError(500, "x")]), Limits(decision=1, max_cost_usd=1))
    assert store.cache_get(conn, "sha0", JEV, "surface", TH["vision"]["questions_version"]) is None


def test_cost_budget_blocks_requests(conn):  # ADR-002 §4.8: przed żądaniem koszt_zaksięgowany + rezerwa(0,01) ≤ max
    # koszt z capture 0.000104538/żądanie: 0+0.01 ≤ 0.0102 ✓, 0.0001045+0.01 ≤ 0.0102 ✓, 0.000209+0.01 > 0.0102 ✗
    t = FakeTransport([decision_body("paved", SURE) for _ in range(5)])
    run(conn, manifest(5), t, Limits(decision=5, max_cost_usd=0.0102))
    assert len(t.calls) == 2


def test_cost_recorded_from_capture_byok(conn):  # TAC-002-03
    res = run(conn, manifest(1), FakeTransport([decision_body("paved", SURE)]), Limits(decision=1, max_cost_usd=1))
    assert store.budget_usage(conn, "R1")[JEV]["cost_usd"] == pytest.approx(0.000104538)
    assert res.cost_total_usd == pytest.approx(0.000104538) and res.requests_total == 1


def test_comparison_model_only_pairs_sent_to_primary(conn):  # AC-19, §4.7
    t = FakeTransport([decision_body("paved", SURE), decision_body("paved", SURE, path=DECISIONS_LUNA),
                       decision_body("paved", SURE), decision_body("paved", SURE, path=DECISIONS_LUNA)])
    res = run(conn, manifest(3), t, Limits(decision=2, comparison=5, max_cost_usd=1))
    eps = [(c[0], c[1].get("model")) for c in t.calls]
    assert eps == [("decisions", JEV), ("decisions", LUNA_D), ("decisions", JEV), ("decisions", LUNA_D)]
    assert len(res.comparison) == 2
    # porównawczy nie wpływa na kategorię ani eskalację
    assert set(res.readings["model"].dropna()) <= {JEV, ""}


def test_comparison_stops_after_primary_disabled(conn):
    t = FakeTransport([vision.TransportError(429, "x")])
    res = run(conn, manifest(2), t, Limits(decision=2, comparison=2, max_cost_usd=1))
    assert len(t.calls) == 1 and len(res.comparison) == 0


def test_no_exception_escapes(conn):  # ADR-002 §5 read(): nigdy nie przepuszcza wyjątku API
    t = FakeTransport([RuntimeError("SDK internal"), TimeoutError()])
    res = run(conn, manifest(1), t, Limits(decision=1, fallback=1, max_cost_usd=1))
    assert by_photo(res).loc["p0", "status"] == "model_unavailable"


def test_summary_sums_to_total():  # AC-20e
    df = pd.DataFrame({"question_id": ["surface"] * 4, "final_stage": ["decision", "fallback", "manual", "decision"]})
    s = vision.vision_summary(df)
    assert s == {"surface": {"decision": 2, "fallback": 1, "manual": 1, "total": 4}}


def test_bad_fallback_content_does_not_disable_model(conn):  # ADR-002 §4.4 vs AC-20 (wyłączenie tylko po błędzie żądania)
    t = FakeTransport([decision_body("paved", UNSURE), chat_body("not json"), decision_body("paved", UNSURE), chat_body('{"answer":"paved"}')])
    res = run(conn, manifest(2), t, Limits(decision=2, fallback=2, max_cost_usd=1))
    assert by_photo(res).loc["p0", "status"] == "model_unavailable"
    assert by_photo(res).loc["p1", "final_stage"] == "fallback"
    assert store.budget_usage(conn, "R1")[LUNA]["disabled"] is False


def test_rerun_replays_comparison_from_cache_without_request(conn):  # AC-22 + ADR-002 §4.10
    t = FakeTransport([decision_body("paved", SURE), decision_body("paved", SURE, path=DECISIONS_LUNA)])
    run(conn, manifest(1), t, Limits(decision=1, comparison=1, max_cost_usd=1))
    t2 = NoNetwork()
    res = run(conn, manifest(1), t2, Limits(decision=1, comparison=1, max_cost_usd=1), run_id="R2")
    assert t2.calls == [] and len(res.comparison) == 1
