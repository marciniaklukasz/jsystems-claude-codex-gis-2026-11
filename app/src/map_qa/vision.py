"""Odczyt zdjęć: próbka, OpenRouter, kaskada i trwały budżet (ADR-002)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import pandas as pd
from openrouter import OpenRouter
from openrouter.utils import BackoffStrategy, RetryConfig
from PIL import Image, UnidentifiedImageError

from map_qa import store

MANIFEST_COLUMNS = ["photo_id", "question_id", "split", "sequence", "image_sha256", "order"]
READING_COLUMNS = [
    "photo_id", "question_id", "split", "final_stage", "model", "answer", "probability",
    "status", "reason", "decision_answer", "decision_probability", "decision_confident",
    "fallback_answer", "cache_hit", "link_status", "image_sha256", "cost_usd",
]
COMPARISON_COLUMNS = ["photo_id", "question_id", "split", "model", "answer", "probability", "confident"]


def questions_for_stage(th, stage) -> dict:
    return {qid: q for qid, q in th["questions"].items() if q["stage"] <= stage}


def options(th, qid) -> list[str]:
    return list(th["questions"][qid]["criteria"])


class ImageRejected(Exception):
    """Zdjęcie nie spełnia wymagań wejścia modelu."""


@dataclass
class PreparedImage:
    data: bytes
    sha256: str
    width: int
    height: int


def prepare_image(path, th) -> PreparedImage:
    try:
        raw = Path(path).read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise ImageRejected("niedozwolony format zdjęcia")
            width, height = image.size
            if min(width, height) < th["vision"]["min_side_px"]:
                raise ImageRejected("zbyt małe zdjęcie")
            image.load()  # Sprawdź także uszkodzone pliki, których nagłówek jest poprawny.
            maximum = th["vision"]["max_side_px"]
            if max(width, height) > maximum:
                scale = maximum / max(width, height)
                width, height = round(width * scale), round(height * scale)
                resized = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                resized.save(output, format="JPEG", quality=90)
                raw = output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ImageRejected("nieczytelne lub uszkodzone zdjęcie") from exc
    return PreparedImage(raw, hashlib.sha256(raw).hexdigest(), width, height)


def _image_part(image_bytes) -> dict:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": url}}


def build_decisions_request(qid, th, image_bytes) -> dict:
    question = th["questions"][qid]
    return {
        "state": [{"type": "text", "text": th["vision"]["state_text"]}, _image_part(image_bytes)],
        "questions": {qid: {"type": "choice", "instructions": question["instructions"],
                            "criteria": dict(question["criteria"])}},
        "provider": {"allow_fallbacks": False},
    }


def build_chat_request(qid, th, image_bytes) -> dict:
    v, question = th["vision"], th["questions"][qid]
    text = (f"{v['state_text']}\n\n{question['instructions']}\nAnswer with exactly one option: "
            + "; ".join(f"{key} = {description}" for key, description in question["criteria"].items()))
    return {
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}, _image_part(image_bytes)]}],
        "reasoning": {"effort": v["fallback_reasoning_effort"]},
        "max_tokens": v["fallback_max_tokens"],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "answer", "strict": True, "schema": {
                "type": "object", "properties": {"answer": {"type": "string", "enum": options(th, qid)}},
                "required": ["answer"], "additionalProperties": False,
            },
        }},
        "provider": {"require_parameters": True, "allow_fallbacks": False},
    }


@dataclass
class DecisionReading:
    answer: str | None
    probability: float | None
    confident: bool


def interpret_decision(body, qid, options, threshold) -> DecisionReading:
    try:
        answer = body["answers"][qid]["choice"]
        if not isinstance(answer, str) or answer not in options:
            return DecisionReading(None, None, False)
        probabilities = body["answers"][qid].get("probabilities")
        if not isinstance(probabilities, dict) or not probabilities:
            return DecisionReading(answer, None, False)
        values = list(probabilities.values())
        if not all(isinstance(p, (int, float)) and not isinstance(p, bool)
                   and math.isfinite(p) and 0 <= p <= 1 for p in values):
            return DecisionReading(answer, None, False)
        probability = max(values)
        return DecisionReading(answer, probability, answer != "unknown" and probability >= threshold)
    except (KeyError, TypeError, AttributeError):
        return DecisionReading(None, None, False)


@dataclass
class ChatReading:
    answer: str | None
    status: str


def interpret_chat(body, options) -> ChatReading:
    try:
        answer = json.loads(body["choices"][0]["message"]["content"])["answer"]
        if isinstance(answer, str) and answer in options:
            return ChatReading(None, "abstain") if answer == "unknown" else ChatReading(answer, "certain")
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return ChatReading(None, "model_unavailable")


def cost_of(body) -> float | None:
    usage = body.get("usage") or {}
    details = usage.get("cost_details") or {}
    values = [usage.get("cost"), details.get("upstream_inference_cost")]
    costs = [float(value) for value in values if isinstance(value, (int, float))
             and not isinstance(value, bool) and math.isfinite(value) and value >= 0]
    return max(costs) if costs else None


class TransportError(Exception):
    def __init__(self, status: int | None, kind: str):
        self.status, self.kind = status, kind
        super().__init__(f"{kind} (HTTP {status})")


class OpenRouterTransport:
    def __init__(self, api_key, timeout_s=40, http_client=None):
        self.retry = RetryConfig("none", BackoffStrategy(500, 60000, 1.5, 3600000), False)
        self.timeout_ms = round(timeout_s * 1000)
        self._status = None
        self._body = None
        http_client = http_client if http_client is not None else httpx.Client()
        http_client.event_hooks.setdefault("response", []).append(self._capture_response)
        self.client = OpenRouter(api_key=api_key, client=http_client,
                                 retry_config=self.retry, timeout_ms=self.timeout_ms)

    def _capture_response(self, response):
        self._status = response.status_code
        response.read()
        self._body = response.json()

    def __call__(self, endpoint, payload):
        self._status, self._body = None, None
        try:
            if endpoint == "decisions":
                self.client.alpha.decisions.create(**payload, retries=self.retry, timeout_ms=self.timeout_ms)
            elif endpoint == "chat":
                self.client.chat.send(**payload, retries=self.retry, timeout_ms=self.timeout_ms)
            else:
                raise ValueError("Nieznany endpoint")
            if self._status is None or self._status >= 400 or not isinstance(self._body, dict):
                raise ValueError("Niepoprawna odpowiedź HTTP")
            return self._body
        except Exception as exc:
            # Wyjątki SDK mogą zawierać żądanie; przekazujemy wyłącznie nazwę klasy i status.
            raise TransportError(self._status, type(exc).__name__) from None


def split_of(sequence) -> str:
    return "validation" if hashlib.sha256(sequence.encode()).digest()[0] % 2 == 0 else "test"


def select_pairs(labels_df, qids, limit) -> pd.DataFrame:
    columns = ["photo_id", "question_id", "split", "sequence", "order"]
    if "image_path" in labels_df.columns:
        columns.append("image_path")
    queues = []
    for qid in qids:
        rows = labels_df.loc[labels_df["status"].eq("certain") & labels_df["question_id"].eq(qid)]
        rows = sorted(rows.to_dict("records"),
                      key=lambda row: hashlib.sha256((row["photo_id"] + qid).encode()).hexdigest())
        queues.append(iter(rows))
    selected = []
    while queues and len(selected) < limit:
        remaining = []
        for queue in queues:
            row = next(queue, None)
            if row is None:
                continue
            remaining.append(queue)
            selected.append({**row, "split": split_of(row["sequence"]), "order": len(selected)})
            if len(selected) >= limit:
                break
        queues = remaining
    return pd.DataFrame(selected, columns=columns)


@dataclass
class Sample:
    manifest: pd.DataFrame
    images: dict[str, bytes]
    excluded: dict[str, int]
    attribution: dict
    photo_paths: dict


def build_sample(stage, limit, th, data_dir, labels) -> Sample:
    qids = list(questions_for_stage(th, stage))
    candidates = select_pairs(labels, qids, len(labels))
    queues = [iter(candidates.loc[candidates["question_id"].eq(qid)].to_dict("records")) for qid in qids]
    metadata = {(row["photo_id"], row["question_id"]): row for row in labels.to_dict("records")}
    selected, images, excluded, attribution, photo_paths = [], {}, {}, {}, {}
    prepared = {}
    while queues and len(selected) < limit:
        remaining = []
        for queue in queues:
            for row in queue:
                pid, qid = row["photo_id"], row["question_id"]
                meta = metadata[pid, qid]
                path = meta.get("image_path")
                if path is None or pd.isna(path) or str(path) == "":
                    excluded["brak lokalnego pliku zdjęcia"] = excluded.get("brak lokalnego pliku zdjęcia", 0) + 1
                    continue
                path = Path(path)
                if not path.is_absolute():
                    path = Path(data_dir) / path
                try:
                    if not path.is_file():
                        raise ImageRejected("brak lokalnego pliku zdjęcia")
                    expected = str(meta.get("expected_sha256") or "")
                    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                        raise ImageRejected("niezgodny hash zdjęcia")  # plik inny niż w manifeście (ADR-002 §4.6)
                    if path not in prepared:
                        prepared[path] = prepare_image(path, th)
                    image = prepared[path]
                except ImageRejected as exc:
                    reason = str(exc)
                    excluded[reason] = excluded.get(reason, 0) + 1
                    continue
                selected.append({**row, "image_sha256": image.sha256, "order": len(selected)})
                images[image.sha256] = image.data
                photo_paths[pid] = str(path)
                attribution[pid] = {key: meta.get(key) for key in ("author", "license", "source_url")}
                attribution[pid]["local_path"] = str(path)
                remaining.append(queue)
                break
            if len(selected) >= limit:
                break
        queues = remaining
    return Sample(pd.DataFrame(selected, columns=MANIFEST_COLUMNS), images, excluded, attribution, photo_paths)


def write_manifest(manifest, run_dir) -> Path:
    path = Path(run_dir) / "sample_manifest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        manifest.to_csv(output, columns=MANIFEST_COLUMNS, index=False)
        output.flush()
        os.fsync(output.fileno())
    return path


@dataclass
class CascadeResult:
    readings: pd.DataFrame
    comparison: pd.DataFrame
    usage: dict
    cost_total_usd: float
    requests_total: int


def _manual_row(pair, links) -> dict:
    return {
        "photo_id": pair["photo_id"], "question_id": pair["question_id"], "split": pair["split"],
        "final_stage": "manual", "model": "", "answer": None, "probability": None,
        "status": "model_unavailable", "reason": "model_unavailable", "decision_answer": None,
        "decision_probability": None, "decision_confident": False, "fallback_answer": None,
        "cache_hit": False, "link_status": links.get(pair["photo_id"]),
        "image_sha256": pair["image_sha256"], "cost_usd": 0.0,
    }


def run_cascade(conn, *, run_id, manifest, images, links, limits, th, transport) -> CascadeResult:
    v = th["vision"]
    readings, comparison = [], []

    def read(pair, model, endpoint, limit):
        """Odczyt, trafienie cache, wysłanie żądania, koszt tej próby."""
        sent = False
        cost = 0.0
        try:
            qid, sha = pair["question_id"], pair["image_sha256"]
            opts = options(th, qid)

            def interpret(body):
                return (interpret_decision(body, qid, opts, v["abstain_threshold"]) if endpoint == "decisions"
                        else interpret_chat(body, opts))

            cached = store.cache_get(conn, sha, model, qid, v["questions_version"])
            if cached is not None:
                return interpret(cached["response"]), True, False, 0.0
            builder = build_decisions_request if endpoint == "decisions" else build_chat_request
            payload = {"model": model, **builder(qid, th, images[sha])}
            if not store.budget_reserve(conn, run_id, model, limit=limit,
                                        max_cost=limits.max_cost_usd, reserve=v["reserve_usd"]):
                return None, False, False, 0.0
            sent = True
            body = transport(endpoint, payload)
            reading = interpret(body)
            reported_cost = cost_of(body)
            cost = v["reserve_usd"] if reported_cost is None else reported_cost
        except Exception:
            if sent:
                store.budget_record(conn, run_id, model, cost_usd=None, reserve=v["reserve_usd"],
                                    error=True, disable=True)
                cost = v["reserve_usd"]
            return None, False, sent, cost

        # niepoprawna treść (zły JSON, spoza listy) → model_unavailable dla tej pary, bez wyłączania modelu (ADR-002 §4.4)
        invalid_chat = endpoint == "chat" and reading.status == "model_unavailable"
        store.budget_record(conn, run_id, model, cost_usd=reported_cost, reserve=v["reserve_usd"], error=False)
        valid = reading.answer is not None if endpoint == "decisions" else not invalid_chat
        if valid:
            store.cache_put(conn, sha, model, qid, v["questions_version"], response=body, reading=asdict(reading))
        return reading, False, sent, cost

    for pair in manifest.sort_values("order").to_dict("records"):
        row = _manual_row(pair, links)
        decision, hit, sent, cost = read(pair, v["decision_model"], "decisions", limits.decision)
        row.update(cache_hit=hit, cost_usd=cost)
        if decision is not None:
            row.update(decision_answer=decision.answer, decision_probability=decision.probability,
                       decision_confident=decision.confident)
        if decision is not None and decision.confident and row["link_status"] != "uncertain":
            row.update(final_stage="decision", model=v["decision_model"], answer=decision.answer,
                       probability=decision.probability, status="certain", reason="")
        else:
            fallback, fallback_hit, _, fallback_cost = read(pair, v["fallback_model"], "chat", limits.fallback)
            row["cache_hit"] = hit or fallback_hit
            row["cost_usd"] += fallback_cost
            if fallback is not None:
                row["fallback_answer"] = fallback.answer
                row["status"] = fallback.status
                row["reason"] = fallback.status
                if fallback.status == "certain":
                    row.update(final_stage="fallback", model=v["fallback_model"], answer=fallback.answer, reason="")

        usage = store.budget_usage(conn, run_id)
        primary_usage = usage.get(v["decision_model"], {})
        comparison_usage = usage.get(v["comparison_model"], {})
        replay = (hit and not sent and limits.comparison > 0 and
                  store.cache_get(conn, pair["image_sha256"], v["comparison_model"], pair["question_id"], v["questions_version"]) is not None)
        if replay or (sent and not primary_usage.get("disabled", False)
                      and comparison_usage.get("sent", 0) < limits.comparison):
            other, _, other_sent, other_cost = read(pair, v["comparison_model"], "decisions", limits.comparison)
            row["cost_usd"] += other_cost
            if other is not None or other_sent:
                comparison.append({
                    "photo_id": pair["photo_id"], "question_id": pair["question_id"], "split": pair["split"],
                    "model": v["comparison_model"], "answer": other.answer if other else None,
                    "probability": other.probability if other else None, "confident": other.confident if other else False,
                })
        readings.append(row)

    usage = store.budget_usage(conn, run_id)
    return CascadeResult(pd.DataFrame(readings, columns=READING_COLUMNS),
                         pd.DataFrame(comparison, columns=COMPARISON_COLUMNS), usage,
                         sum((u["cost_usd"] for u in usage.values()), 0.0), sum(u["sent"] for u in usage.values()))


def vision_summary(readings) -> dict:
    return {qid: {**{stage: int(group["final_stage"].eq(stage).sum())
                     for stage in ("decision", "fallback", "manual")}, "total": len(group)}
            for qid, group in readings.groupby("question_id", sort=False)}


def run_vision(conn, *, run_id, stage, limits, th, layers, assessment, data_dir, run_dir,
               labels, sign_links=None, transport=None) -> dict:
    result = {"readings": pd.DataFrame(columns=READING_COLUMNS), "comparison": [], "usage": {},
              "cost_total_usd": 0.0, "requests_total": 0, "vision_summary": {},
              "openrouter_state": "brak budżetu (limity 0) — nie wysłano żadnego żądania",
              "photo_paths": {}, "attribution": {}}
    if not limits.any_positive():
        return result
    sample = build_sample(stage, limits.decision, th, data_dir, labels)
    write_manifest(sample.manifest, run_dir)
    links = {}
    for frame in (assessment, sign_links):
        if frame is not None:
            for row in frame.to_dict("records"):
                if row["status"] in {"certain", "uncertain"}:
                    links[row["photo_id"]] = row["status"]
                elif row["status"] == "evaluation_only":
                    links.pop(row["photo_id"], None)
    result.update(photo_paths=sample.photo_paths, attribution=sample.attribution, sample_excluded=dict(sample.excluded))
    if transport is None and "OPENROUTER_API_KEY" not in os.environ:
        result["readings"] = pd.DataFrame([_manual_row(pair, links) for pair in sample.manifest.to_dict("records")],
                                          columns=READING_COLUMNS)
        result["openrouter_state"] = "brak klucza OPENROUTER_API_KEY"
    else:
        if transport is None:
            transport = OpenRouterTransport(os.environ["OPENROUTER_API_KEY"], th["vision"]["timeout_s"])
        cascade = run_cascade(conn, run_id=run_id, manifest=sample.manifest, images=sample.images, links=links,
                              limits=limits, th=th, transport=transport)
        result.update(readings=cascade.readings, comparison=cascade.comparison.to_dict("records"),
                      usage=cascade.usage, cost_total_usd=cascade.cost_total_usd, requests_total=cascade.requests_total)
        errors = "; ".join(f"{model}: {usage['errors']}" for model, usage in cascade.usage.items() if usage["errors"])
        result["openrouter_state"] = (f"żądania: {cascade.requests_total}; błędy: {errors or '0'}; "
                                      f"koszt: {cascade.cost_total_usd:.6f} USD")
    result["vision_summary"] = vision_summary(result["readings"])
    return result
