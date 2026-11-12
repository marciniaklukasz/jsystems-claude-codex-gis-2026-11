"""Wspólne narzędzia testów vision. Transport testowy zwraca WYŁĄCZNIE ciała z capture (ADR-002 §4.5, TAC-002-04).

Pliki capture (2026-11-12, prawdziwe żądania T5.2b):
- DECISIONS_JEV   = tests/fixtures/captures/2026-11-12_decisions_typesafe_jev-1.14.json
- DECISIONS_LUNA  = tests/fixtures/captures/2026-11-12_decisions_openai_gpt-6-luna-decisions.json
- CHAT_LUNA       = tests/fixtures/captures/2026-11-12_chat_openai_gpt-6-luna.json
- ERROR_422       = tests/fixtures/captures/2026-11-12_decisions-error_typesafe_jev-1.14.json
"""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path

from PIL import Image

CAPTURES = Path(__file__).resolve().parents[1] / "fixtures" / "captures"
DECISIONS_JEV = CAPTURES / "2026-11-12_decisions_typesafe_jev-1.14.json"
DECISIONS_LUNA = CAPTURES / "2026-11-12_decisions_openai_gpt-6-luna-decisions.json"
CHAT_LUNA = CAPTURES / "2026-11-12_chat_openai_gpt-6-luna.json"
ERROR_422 = CAPTURES / "2026-11-12_decisions-error_typesafe_jev-1.14.json"


def body(path: Path) -> dict:
    return copy.deepcopy(json.loads(path.read_text(encoding="utf-8"))["body"])


def decision_body(choice: str = "paved", probs: dict | None = None, path: Path = DECISIONS_JEV, qid: str = "surface") -> dict:
    """Ciało z capture z podmienioną jedną wartością: odpowiedź (choice/probabilities) i klucz pytania."""
    b = body(path)
    ans = b["answers"].pop("surface")
    ans["choice"] = choice
    if probs is not None:
        ans["probabilities"] = probs
    b["answers"][qid] = ans
    return b


def chat_body(content: str = '{"answer":"paved"}') -> dict:
    """Ciało chat z capture z podmienioną jedną wartością: message.content."""
    b = body(CHAT_LUNA)
    b["choices"][0]["message"]["content"] = content
    return b


class FakeTransport:
    """Transport testowy: kolejne odpowiedzi (dict = ciało z capture, Exception = błąd). Zapisuje wywołania."""

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, endpoint: str, payload: dict) -> dict:
        self.calls.append((endpoint, payload))
        if not self.responses:
            raise AssertionError(f"nieoczekiwane żądanie {endpoint}")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class NoNetwork:
    def __init__(self):
        self.calls = []

    def __call__(self, endpoint, payload):
        self.calls.append(endpoint)
        raise AssertionError("żądanie HTTP przy limicie 0")


def jpeg_bytes(w: int, h: int, fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 130, 140)).save(buf, fmt)
    return buf.getvalue()
