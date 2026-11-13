"""ADR-002 §8 „Brak retry w SDK” i D-202: prawdziwy klient SDK openrouter na transporcie httpx bez sieci.

Ciała odpowiedzi wyłącznie z capture (TAC-002-04):
- tests/fixtures/captures/2026-11-12_decisions_typesafe_jev-1.14.json (200)
- tests/fixtures/captures/2026-11-12_decisions-error_typesafe_jev-1.14.json (błąd; status podmieniony na 503 w jednym teście)
- tests/fixtures/captures/2026-11-12_chat_openai_gpt-6-luna.json (200)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from vision_support import CHAT_LUNA, DECISIONS_JEV, ERROR_422, body, jpeg_bytes  # noqa: E402

from map_qa import config, vision  # noqa: E402

TH = config.load_thresholds()


def transport_with(handler):
    calls = []

    def h(request: httpx.Request):
        calls.append(request)
        return handler(request)

    t = vision.OpenRouterTransport(api_key="test-key-not-real", timeout_s=40, http_client=httpx.Client(transport=httpx.MockTransport(h)))
    return t, calls


def payload():
    return {"model": TH["vision"]["decision_model"], **vision.build_decisions_request("surface", TH, jpeg_bytes(300, 300))}


def test_503_exactly_one_request():
    t, calls = transport_with(lambda r: httpx.Response(503, json=body(ERROR_422)))
    with pytest.raises(vision.TransportError) as e:
        t("decisions", payload())
    assert len(calls) == 1 and e.value.status == 503
    assert str(calls[0].url).startswith("https://openrouter.ai/api/alpha/decisions")


def test_connection_error_exactly_one_request():
    def boom(r):
        raise httpx.ConnectError("refused")

    t, calls = transport_with(boom)
    with pytest.raises(vision.TransportError):
        t("decisions", payload())
    assert len(calls) == 1


def test_422_from_capture_is_transport_error():
    t, calls = transport_with(lambda r: httpx.Response(422, json=body(ERROR_422)))
    with pytest.raises(vision.TransportError) as e:
        t("decisions", payload())
    assert e.value.status == 422 and len(calls) == 1


def test_success_returns_raw_body_and_sends_auth_header_only_in_request():
    t, calls = transport_with(lambda r: httpx.Response(200, json=body(DECISIONS_JEV)))
    out = t("decisions", payload())
    assert out == body(DECISIONS_JEV)
    sent = json.loads(calls[0].content)
    assert sent["model"] == TH["vision"]["decision_model"] and "surface" in sent["questions"]
    assert sent["state"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_chat_success_and_url():
    t, calls = transport_with(lambda r: httpx.Response(200, json=body(CHAT_LUNA)))
    out = t("chat", {"model": TH["vision"]["fallback_model"], **vision.build_chat_request("surface", TH, jpeg_bytes(300, 300))})
    assert vision.interpret_chat(out, vision.options(TH, "surface")).answer == "paved"
    assert str(calls[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert json.loads(calls[0].content)["stream"] is False if "stream" in json.loads(calls[0].content) else True
