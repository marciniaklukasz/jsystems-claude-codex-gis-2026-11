"""Pure normalization helpers for OSM and Overture map attributes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Normalized:
    status: str
    value: int | str | None
    detail: str
    raw: str

    @property
    def comparable(self) -> bool:
        return self.status == "value"


@dataclass(frozen=True)
class SpeedRule:
    max_kmh: int | None
    unit: str | None
    has_when: bool
    between: list | None
    is_variable: bool


def _normalized(status: str, value: int | str | None, detail: str, raw: str) -> Normalized:
    return Normalized(status, value, detail, raw)


def parse_maxspeed_value(s: str | None) -> Normalized:
    raw = "" if s is None else s
    value = raw.strip()
    if not value:
        return _normalized("missing", None, "missing", raw)
    if ";" in value:
        return _normalized("not_comparable", None, "multiple", raw)
    if re.match(r"^[A-Z]{2}:", value):
        return _normalized("not_comparable", None, "implicit", raw)
    match = re.fullmatch(r"(\d+)\s*(km/h)?", value, flags=re.IGNORECASE)
    if match:
        return _normalized("value", int(match.group(1)), "numeric", raw)
    if re.fullmatch(r"\d+\s*(?:mph|knots)", value, flags=re.IGNORECASE):
        return _normalized("not_comparable", None, "other_unit", raw)
    return _normalized("not_comparable", None, "special", raw)


def parse_osm_speed(tags: dict) -> Normalized:
    selected = {k: v for k, v in tags.items() if isinstance(k, str) and k.startswith("maxspeed")}
    raw = to_json(selected)
    if "maxspeed:conditional" in selected:
        return _normalized("not_comparable", None, "conditional", raw)
    if "maxspeed:forward" in selected or "maxspeed:backward" in selected:
        general = tags.get("maxspeed")
        forward = parse_maxspeed_value(selected.get("maxspeed:forward", general))
        backward = parse_maxspeed_value(selected.get("maxspeed:backward", general))
        if forward.comparable and backward.comparable and forward.value == backward.value:
            return _normalized("value", forward.value, "numeric", raw)
        return _normalized("not_comparable", None, "directional", raw)
    parsed = parse_maxspeed_value(tags.get("maxspeed"))
    return _normalized(parsed.status, parsed.value, parsed.detail, raw)


def _plain(obj: Any) -> Any:
    """Konwersja wartości z Parquet (numpy) na typy Pythona; ta sama co w to_json."""
    return json.loads(to_json(obj))


def speed_rules(rules) -> list[SpeedRule]:
    rules = _plain(rules)
    result: list[SpeedRule] = []
    if not isinstance(rules, list):
        return result
    for rule in rules:
        rule = rule if isinstance(rule, dict) else {}
        speed = rule.get("max_speed")
        speed = speed if isinstance(speed, dict) else {}
        val = speed.get("value")
        unit = speed.get("unit")
        result.append(SpeedRule(
            max_kmh=val if isinstance(val, int) and not isinstance(val, bool) and unit == "km/h" else None,
            unit=unit if isinstance(unit, str) else None,
            has_when=bool(rule.get("when")),
            between=rule.get("between") if rule.get("between") else None,
            is_variable=rule.get("is_max_speed_variable") is True,
        ))
    return result


def parse_overture_speed(rules: list | None) -> Normalized:
    raw = to_json(rules)
    rules = _plain(rules)
    if not rules:
        return _normalized("missing", None, "missing", raw)
    if len(rules) != 1:
        return _normalized("not_comparable", None, "multiple", raw)
    rule = rules[0] if isinstance(rules[0], dict) else {}
    speed = rule.get("max_speed")
    speed = speed if isinstance(speed, dict) else {}
    unit = speed.get("unit")
    if unit is not None and unit != "km/h":
        return _normalized("not_comparable", None, "other_unit", raw)
    if rule.get("when"):
        return _normalized("not_comparable", None, "conditional", raw)
    if rule.get("between") or rule.get("is_max_speed_variable") is True:
        return _normalized("not_comparable", None, "partial", raw)
    value = speed.get("value")
    if unit == "km/h" and isinstance(value, int) and not isinstance(value, bool):
        return _normalized("value", value, "numeric", raw)
    return _normalized("not_comparable", None, "partial", raw)


def parse_osm_surface(value, paved, unpaved) -> Normalized:
    raw = "" if value is None else value
    stripped = raw.strip()
    if not stripped:
        return _normalized("missing", None, "missing", raw)
    if stripped in paved:
        return _normalized("value", "paved", "paved_unpaved", raw)
    if stripped in unpaved:
        return _normalized("value", "unpaved", "paved_unpaved", raw)
    return _normalized("not_comparable", None, "unknown_value", raw)


def parse_overture_surface(rules, paved, unpaved) -> Normalized:
    raw = to_json(rules)
    rules = _plain(rules)
    if not rules:
        return _normalized("missing", None, "missing", raw)
    if len(rules) != 1 or not isinstance(rules[0], dict) or rules[0].get("between"):
        return _normalized("not_comparable", None, "partial", raw)
    value = rules[0].get("value")
    if value in paved:
        return _normalized("value", "paved", "paved_unpaved", raw)
    if value in unpaved:
        return _normalized("value", "unpaved", "paved_unpaved", raw)
    return _normalized("not_comparable", None, "unknown_value", raw)


def parse_lit(value) -> Normalized:
    raw = "" if value is None else value
    stripped = raw.strip()
    if not stripped:
        return _normalized("missing", None, "missing", raw)
    if stripped in {"yes", "automatic", "24/7"}:
        return _normalized("value", "yes", "lit", raw)
    if stripped == "no":
        return _normalized("value", "no", "lit", raw)
    return _normalized("not_comparable", None, "unknown_value", raw)


def to_json(obj: Any) -> str:
    def convert(value):
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None:
            if isinstance(value, np.ndarray):
                return convert(value.tolist())
            if isinstance(value, np.integer):
                return int(value)
            if isinstance(value, np.floating):
                number = float(value)
                return None if number != number else number
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, float) and value != value:
            return None
        return value

    return json.dumps(convert(obj), ensure_ascii=False)
