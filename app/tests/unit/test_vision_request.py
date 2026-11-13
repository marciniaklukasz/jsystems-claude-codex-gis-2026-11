"""ADR-002 §2 (kontrakt połączenia), §4.1–4.6; PRD AC-17, AC-18, AC-19a, AC-20a, AC-20d; D-201, D-203."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re

import pytest
from PIL import Image

from map_qa import config, vision

from vision_support import CHAT_LUNA, DECISIONS_JEV, DECISIONS_LUNA, body, chat_body, decision_body, jpeg_bytes

TH = config.load_thresholds()


# --- pytania (ADR-002 §4.1) ---------------------------------------------------------------
def test_questions_per_stage():
    assert list(vision.questions_for_stage(TH, 1)) == ["speed_limit_value", "surface"]
    assert list(vision.questions_for_stage(TH, 2)) == ["speed_limit_value", "surface", "street_lighting_visible", "junction_visible"]
    assert vision.options(TH, "surface") == ["paved", "unpaved", "unknown"]
    assert "unknown" in vision.options(TH, "speed_limit_value") and "unreadable" in vision.options(TH, "speed_limit_value")


# --- obraz (ADR-002 §4.6) ------------------------------------------------------------------
def test_prepare_image_resizes_long_side_to_1568(tmp_path):
    p = tmp_path / "x.jpg"
    p.write_bytes(jpeg_bytes(1600, 900))
    img = vision.prepare_image(p, TH)
    assert (img.width, img.height) == (1568, 882)
    assert img.sha256 == hashlib.sha256(img.data).hexdigest() != hashlib.sha256(p.read_bytes()).hexdigest()
    assert Image.open(io.BytesIO(img.data)).format == "JPEG"


def test_prepare_image_small_unchanged(tmp_path):
    p = tmp_path / "x.jpg"
    raw = jpeg_bytes(1024, 768)
    p.write_bytes(raw)
    img = vision.prepare_image(p, TH)
    assert img.data == raw and (img.width, img.height) == (1024, 768)


@pytest.mark.parametrize("w,h,fmt", [(1024, 200, "JPEG"), (300, 300, "GIF")])
def test_prepare_image_rejects_too_small_or_wrong_format(tmp_path, w, h, fmt):
    p = tmp_path / "x.img"
    p.write_bytes(jpeg_bytes(w, h, fmt))
    with pytest.raises(vision.ImageRejected):
        vision.prepare_image(p, TH)


# --- treść żądania (AC-17, §4.2, §4.4) ------------------------------------------------------
def test_decisions_request_only_neutral_text_and_image():
    data = jpeg_bytes(400, 300)
    req = vision.build_decisions_request("surface", TH, data)
    assert set(req) == {"state", "questions", "provider"}
    assert req["provider"] == {"allow_fallbacks": False}
    assert req["state"][0] == {"type": "text", "text": TH["vision"]["state_text"]}
    assert req["state"][1]["type"] == "image_url"
    assert req["state"][1]["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(data).decode()
    assert len(req["state"]) == 2
    q = req["questions"]
    assert list(q) == ["surface"] and q["surface"]["type"] == "choice"
    assert list(q["surface"]["criteria"]) == ["paved", "unpaved", "unknown"]


def test_request_has_no_ids_labels_or_map_data():
    data = jpeg_bytes(400, 300)
    for req in (vision.build_decisions_request("speed_limit_value", TH, data), vision.build_chat_request("speed_limit_value", TH, data)):
        s = re.sub(r"data:image/jpeg;base64,[A-Za-z0-9+/=]+", "IMG", json.dumps(req))
        for forbidden in ("mapillary_", "panoramax_", ".jpg", "photo_id", "osm", "maxspeed", "label", "latitude", "longitude", "session_id", "trace"):
            assert forbidden not in s, forbidden
    assert "user" not in vision.build_decisions_request("surface", TH, data)


def test_chat_request_contract():
    data = jpeg_bytes(400, 300)
    req = vision.build_chat_request("surface", TH, data)
    assert req["reasoning"] == {"effort": "medium"}
    assert req["max_tokens"] == TH["vision"]["fallback_max_tokens"]
    assert req["provider"]["require_parameters"] is True
    schema = req["response_format"]["json_schema"]
    assert req["response_format"]["type"] == "json_schema" and schema["strict"] is True
    assert schema["schema"]["properties"]["answer"]["enum"] == ["paved", "unpaved", "unknown"]
    msg = req["messages"]
    assert len(msg) == 1 and msg[0]["role"] == "user"  # bez promptu systemowego
    parts = msg[0]["content"]
    assert parts[0]["type"] == "text" and TH["vision"]["state_text"] in parts[0]["text"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# --- interpretacja (§4.3, §4.4, AC-18, AC-20a, AC-20d) ---------------------------------------
OPTS = ["paved", "unpaved", "unknown"]


def test_decision_confident_from_capture():  # DECISIONS_JEV
    r = vision.interpret_decision(body(DECISIONS_JEV), "surface", OPTS, 0.7)
    assert (r.answer, r.confident, r.probability) == ("paved", True, 1)


@pytest.mark.parametrize("probs, confident", [({"paved": 0.69, "unpaved": 0.31, "unknown": 0}, False), ({"paved": 0.70, "unpaved": 0.30, "unknown": 0}, True)])
def test_abstain_threshold(probs, confident):  # §8 „Próg abstencji”; mock: DECISIONS_JEV z podmienionym probabilities
    r = vision.interpret_decision(decision_body("paved", probs), "surface", OPTS, 0.7)
    assert r.confident is confident


@pytest.mark.parametrize("choice", ["unknown", "gravel"])
def test_unknown_or_out_of_list_not_confident(choice):  # AC-18; mock: DECISIONS_LUNA z podmienionym choice
    r = vision.interpret_decision(decision_body(choice, path=DECISIONS_LUNA), "surface", OPTS, 0.7)
    assert r.confident is False


def test_missing_question_in_answers_not_confident():
    r = vision.interpret_decision(body(DECISIONS_JEV), "street_lighting_visible", ["yes", "no", "unknown"], 0.7)
    assert r.confident is False


@pytest.mark.parametrize(
    "content, status, answer",
    [('{"answer":"paved"}', "certain", "paved"), ('{"answer":"unknown"}', "abstain", None),
     ('{"answer":"gravel"}', "model_unavailable", None), ("not json", "model_unavailable", None),
     ("", "model_unavailable", None), ('{"answer":"pav', "model_unavailable", None)],
)
def test_interpret_chat(content, status, answer):  # D-203; mock: CHAT_LUNA z podmienionym message.content
    r = vision.interpret_chat(chat_body(content), OPTS)
    assert (r.status, r.answer) == (status, answer)


def test_interpret_chat_from_capture_unchanged():  # CHAT_LUNA
    assert vision.interpret_chat(body(CHAT_LUNA), OPTS).answer == "paved"


def test_cost_byok_uses_upstream_cost():  # capture: usage.cost = 0, is_byok = true
    assert vision.cost_of(body(DECISIONS_JEV)) == pytest.approx(0.000104538)
    u = body(CHAT_LUNA)["usage"]  # chat: is_byok=false, cost 0.000141372, upstream 0.0001428 → max
    assert vision.cost_of(body(CHAT_LUNA)) == pytest.approx(max(u["cost"], u["cost_details"]["upstream_inference_cost"]))
    assert vision.cost_of({}) is None


def test_real_transport_points_to_openrouter_without_retry():  # ADR-002 §2, D-202
    t = vision.OpenRouterTransport(api_key="test-key-not-real", timeout_s=40)
    assert t.client.sdk_configuration.get_server_details()[0].startswith("https://openrouter.ai/")
    assert t.retry.strategy == "none"
    assert t.timeout_ms == 40_000
