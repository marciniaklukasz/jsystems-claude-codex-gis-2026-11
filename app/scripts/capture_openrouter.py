"""T5.2b: capture prawdziwych żądań i odpowiedzi OpenRouter (ADR-002 §4.5; przydział prowadzącego ≤ 1 USD).

Uruchomienie z app/: uv run python scripts/capture_openrouter.py
Po jednym żądaniu na parę (endpoint, model) + jeden capture błędu (puste `criteria`).
Bez retry (strategia "none"), timeout 40 s. Klucz tylko z os.environ["OPENROUTER_API_KEY"]; nigdy nie jest zapisywany.
Obraz w zapisanym żądaniu zastąpiony przez sha256 i rozmiar (bez base64).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import httpx
from openrouter import OpenRouter
from openrouter.utils import BackoffStrategy, RetryConfig

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "src"))
from map_qa import config  # noqa: E402

OUT = APP / "tests" / "fixtures" / "captures"
PHOTO_ID = "panoramax_334a574d-18cb-4c2e-be3f-f99307e080d9"  # offline/, etykieta surface=paved (certain)
HEADER_ALLOW = re.compile(r"^(content-type|date|x-request-id|x-generation-id|.*request-id)$", re.I)
NO_RETRY = RetryConfig("none", BackoffStrategy(500, 60000, 1.5, 3600000), False)


def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("data:image"):
        raw = base64.b64decode(obj.split(",", 1)[1])
        return f"<image sha256={hashlib.sha256(raw).hexdigest()} bytes={len(raw)}>"
    return obj


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("Brak OPENROUTER_API_KEY — capture niemożliwy (zgłoś brak prerekwizytu).")
        return 1
    th = config.load_thresholds()
    v = th["vision"]
    q = th["questions"]["surface"]
    img = (config.DEFAULT_DATA_DIR / "offline" / f"{PHOTO_ID}.jpg").read_bytes()
    data_url = "data:image/jpeg;base64," + base64.b64encode(img).decode()
    state = [{"type": "text", "text": v["state_text"]}, {"type": "image_url", "image_url": {"url": data_url}}]
    question = {"surface": {"type": "choice", "instructions": q["instructions"], "criteria": dict(q["criteria"])}}

    log: list[dict] = []

    def on_request(request: httpx.Request):
        log.append({"request": {"method": request.method, "url": str(request.url), "body": sanitize(json.loads(request.content or b"null"))}})

    def on_response(response: httpx.Response):
        response.read()
        try:
            body = response.json()
        except ValueError:
            body = {"_non_json_text": response.text}
        log[-1]["response"] = {"status": response.status_code,
                               "headers": {k.lower(): val for k, val in response.headers.items() if HEADER_ALLOW.match(k)},
                               "body": body}

    client = OpenRouter(api_key=key, client=httpx.Client(event_hooks={"request": [on_request], "response": [on_response]}),
                        retry_config=NO_RETRY, timeout_ms=v["timeout_s"] * 1000)

    options = list(q["criteria"])
    chat_text = (f"{v['state_text']}\n\n{q['instructions']}\nAnswer with exactly one option: "
                 + "; ".join(f"{k} = {d}" for k, d in q["criteria"].items()))
    calls = [
        ("decisions", v["decision_model"], lambda: client.alpha.decisions.create(
            model=v["decision_model"], state=state, questions=question, provider={"allow_fallbacks": False},
            retries=NO_RETRY, timeout_ms=v["timeout_s"] * 1000)),
        ("decisions", v["comparison_model"], lambda: client.alpha.decisions.create(
            model=v["comparison_model"], state=state, questions=question, provider={"allow_fallbacks": False},
            retries=NO_RETRY, timeout_ms=v["timeout_s"] * 1000)),
        ("chat", v["fallback_model"], lambda: client.chat.send(
            model=v["fallback_model"],
            messages=[{"role": "user", "content": [{"type": "text", "text": chat_text}, {"type": "image_url", "image_url": {"url": data_url}}]}],
            reasoning={"effort": v["fallback_reasoning_effort"]}, max_tokens=v["fallback_max_tokens"],
            response_format={"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {
                "type": "object", "properties": {"answer": {"type": "string", "enum": options}}, "required": ["answer"], "additionalProperties": False}}},
            provider={"require_parameters": True, "allow_fallbacks": False}, retries=NO_RETRY, timeout_ms=v["timeout_s"] * 1000)),
        ("decisions-error", v["decision_model"], lambda: client.alpha.decisions.create(
            model=v["decision_model"], state=state, questions={"surface": {"type": "choice", "instructions": q["instructions"], "criteria": {}}},
            provider={"allow_fallbacks": False}, retries=NO_RETRY, timeout_ms=v["timeout_s"] * 1000)),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for kind, model, call in calls:
        n_before = len(log)
        sdk_result, sdk_error = None, None
        try:
            res = call()
            sdk_result = type(res).__name__
        except Exception as e:  # noqa: BLE001 — capture zapisuje także błędy
            sdk_error = f"{type(e).__module__}.{type(e).__name__}"
        entries = log[n_before:]
        assert len(entries) == 1, f"oczekiwano 1 żądania HTTP (bez retry), jest {len(entries)}"
        e = entries[0]
        cap = {
            "captured_at": datetime.now(timezone.utc).isoformat(), "endpoint": e["request"]["url"], "kind": kind,
            "model": model, "sdk": f"openrouter=={version('openrouter')}", "httpx": version("httpx"),
            "photo": {"photo_id_not_sent": PHOTO_ID, "sha256": hashlib.sha256(img).hexdigest(), "bytes": len(img)},
            "request": e["request"], "status": e.get("response", {}).get("status"),
            "headers": e.get("response", {}).get("headers", "niedostępne"),
            "body": e.get("response", {}).get("body"), "sdk_result": sdk_result, "sdk_error": sdk_error,
        }
        text = json.dumps(cap, ensure_ascii=False, indent=1)
        for bad in ("authorization", "sk-or-", key, "base64,"):
            assert bad.lower() not in text.lower(), f"capture zawiera zakazany ciąg ({'klucz' if bad == key else bad})"
        cost = ((cap["body"] or {}).get("usage") or {}).get("cost") if isinstance(cap["body"], dict) else None
        total += float(cost or 0)
        name = f"{today}_{kind}_{model.replace('/', '_')}.json"
        (OUT / name).write_text(text, encoding="utf-8")
        print(f"{name}: HTTP {cap['status']}, sdk={sdk_result or sdk_error}, cost={cost}")
    print(f"łączny koszt capture (usage.cost): {total:.6f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
