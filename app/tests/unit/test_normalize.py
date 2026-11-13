"""ADR-001 §4.1–4.4, §8; AC-12; TAC-001-01, TAC-001-04.

Prawdziwe wiersze: tests/fixtures/rows/{osm_rows,overture_rows}.json (pole _source).
Formaty nieobecne w snapshocie (mph, `50;70`, `PL:urban` w `maxspeed`, `none`) są jawnie syntetyczne.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from map_qa import normalize as nz

ROWS = Path(__file__).resolve().parents[1] / "fixtures" / "rows"
OSM = {r["case"]: r for r in json.loads((ROWS / "osm_rows.json").read_text(encoding="utf-8"))}
OV = {r["case"]: r for r in json.loads((ROWS / "overture_rows.json").read_text(encoding="utf-8"))}

PAVED = ["asphalt", "concrete", "concrete:plates", "paving_stones", "sett", "paved"]
UNPAVED = ["unpaved", "gravel", "dirt", "grass"]
OV_PAVED = ["paved", "paving_stones", "metal"]
OV_UNPAVED = ["unpaved", "gravel", "dirt"]


def tags(case: str) -> dict:
    return json.loads(OSM[case]["tags"])


# --- §4.1 pojedyncza wartość maxspeed (syntetyczne formaty) ---------------------------
@pytest.mark.parametrize(
    "raw, status, value, detail",
    [
        ("50", "value", 50, "numeric"),
        (" 50 ", "value", 50, "numeric"),
        ("50 km/h", "value", 50, "numeric"),
        ("50 KM/H", "value", 50, "numeric"),
        ("30 mph", "not_comparable", None, "other_unit"),
        ("10 knots", "not_comparable", None, "other_unit"),
        ("50;70", "not_comparable", None, "multiple"),
        ("PL:urban", "not_comparable", None, "implicit"),
        ("PL:zone30", "not_comparable", None, "implicit"),
        ("none", "not_comparable", None, "special"),
        ("signals", "not_comparable", None, "special"),
        ("walk", "not_comparable", None, "special"),
        ("", "missing", None, "missing"),
        (None, "missing", None, "missing"),
    ],
)
def test_parse_maxspeed_value(raw, status, value, detail):
    r = nz.parse_maxspeed_value(raw)
    assert (r.status, r.value, r.detail) == (status, value, detail)


def test_parse_osm_speed_never_raises_on_garbage():
    r = nz.parse_osm_speed({"maxspeed": " ???"})
    assert r.status == "not_comparable" and r.detail == "special"


# --- §4.1 prawdziwe wiersze OSM --------------------------------------------------------
def test_simple_numeric_real_row():
    r = nz.parse_osm_speed(tags("simple_maxspeed_40"))
    assert (r.status, r.value) == ("value", 40)
    assert json.loads(r.raw) == {"maxspeed": "40"}


def test_conditional_makes_pair_not_comparable_and_keeps_raw():
    t = tags("conditional")
    r = nz.parse_osm_speed(t)
    assert r.status == "not_comparable" and r.detail == "conditional"
    assert json.loads(r.raw) == {k: v for k, v in t.items() if k.startswith("maxspeed")}
    assert "110 @ (Mo-Fr 06:00-18:00)" in r.raw


def test_forward_backward_different_not_comparable():
    r = nz.parse_osm_speed(tags("forward_backward_diff"))
    assert r.status == "not_comparable" and r.detail == "directional"


def test_forward_backward_equal_comparable():
    r = nz.parse_osm_speed(tags("forward_backward_equal"))
    assert (r.status, r.value) == ("value", 50)


def test_forward_only_without_maxspeed_not_comparable():
    r = nz.parse_osm_speed(tags("forward_only"))
    assert r.status == "not_comparable" and r.detail == "directional"


def test_oneway_minus1_does_not_make_equal_directions_comparable_differently():
    t = {"maxspeed:forward": "50", "maxspeed:backward": "70", "oneway": "-1"}
    assert nz.parse_osm_speed(t).status == "not_comparable"


def test_forward_with_general_maxspeed_for_other_direction():
    assert nz.parse_osm_speed({"maxspeed": "50", "maxspeed:forward": "50"}).value == 50
    assert nz.parse_osm_speed({"maxspeed": "50", "maxspeed:forward": "30"}).status == "not_comparable"


def test_maxspeed_type_and_hgv_informational_only():
    r = nz.parse_osm_speed(tags("maxspeed_type_pl"))
    assert (r.status, r.value) == ("value", 30)
    assert json.loads(r.raw)["maxspeed:type"] == "PL:zone30"
    h = nz.parse_osm_speed(tags("hgv"))
    assert (h.status, h.value) == ("value", 120)
    assert json.loads(h.raw)["maxspeed:hgv"] == "80"


def test_missing_maxspeed():
    r = nz.parse_osm_speed(tags("tertiary_no_maxspeed"))
    assert r.status == "missing"
    assert json.loads(r.raw) == {}


# --- §4.2 Overture speed_limits -------------------------------------------------------
def test_overture_single_whole_rule_comparable():
    r = nz.parse_overture_speed(OV["one_rule_whole"]["speed_limits"])
    assert (r.status, r.value) == ("value", 50)


@pytest.mark.parametrize("case", ["two_rules", "rule_with_when", "rule_with_between", "variable", "surface_between"])
def test_overture_other_rules_not_comparable(case):
    rules = OV[case]["speed_limits"]
    r = nz.parse_overture_speed(rules)
    assert r.status == "not_comparable"
    # wszystkie reguły zachowane (TAC-001-01)
    assert json.loads(r.raw) == rules


def test_overture_two_or_more_rules_never_comparable_even_if_equal():  # TAC-001-04
    rule = {"min_speed": None, "max_speed": {"value": 50, "unit": "km/h"}, "is_max_speed_variable": None, "when": None, "between": None}
    assert nz.parse_overture_speed([rule, dict(rule)]).status == "not_comparable"


def test_overture_mph_not_comparable_synthetic():
    rule = {"min_speed": None, "max_speed": {"value": 30, "unit": "mph"}, "is_max_speed_variable": None, "when": None, "between": None}
    r = nz.parse_overture_speed([rule])
    assert r.status == "not_comparable" and r.detail == "other_unit"


def test_overture_missing():
    assert nz.parse_overture_speed(None).status == "missing"
    assert nz.parse_overture_speed([]).status == "missing"


def test_overture_rules_structured():
    rules = nz.speed_rules(OV["rule_with_when"]["speed_limits"])
    assert rules[0].max_kmh == 40 and rules[0].has_when is True and rules[0].unit == "km/h"


# --- §4.3 nawierzchnia ----------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, status, value",
    [
        ("asphalt", "value", "paved"),
        (" asphalt ", "value", "paved"),
        ("paving_stones", "value", "paved"),
        ("gravel", "value", "unpaved"),
        ("paving_Stones", "not_comparable", None),
        ("contrete:plates", "not_comparable", None),
        ("utwardzona", "not_comparable", None),
        ("", "missing", None),
        (None, "missing", None),
    ],
)
def test_osm_surface(raw, status, value):
    r = nz.parse_osm_surface(raw, PAVED, UNPAVED)
    assert (r.status, r.value) == (status, value)


def test_osm_surface_real_typo_row():
    r = nz.parse_osm_surface(tags("surface_typo").get("surface"), PAVED, UNPAVED)
    assert r.status == "not_comparable" and r.raw == "paving_Stones"


def test_overture_surface():
    assert nz.parse_overture_surface(OV["one_rule_whole"]["road_surface"], OV_PAVED, OV_UNPAVED).value == "paved"
    assert nz.parse_overture_surface(OV["surface_unknown"]["road_surface"], OV_PAVED, OV_UNPAVED).status == "not_comparable"
    r = nz.parse_overture_surface(OV["surface_between"]["road_surface"], OV_PAVED, OV_UNPAVED)
    assert r.status == "not_comparable"
    assert json.loads(r.raw) == OV["surface_between"]["road_surface"]
    assert nz.parse_overture_surface(None, OV_PAVED, OV_UNPAVED).status == "missing"


# --- §4.4 lit ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, status, value",
    [("yes", "value", "yes"), ("automatic", "value", "yes"), ("24/7", "value", "yes"), ("no", "value", "no"),
     ("disused", "not_comparable", None), (None, "missing", None), ("", "missing", None)],
)
def test_lit(raw, status, value):
    r = nz.parse_lit(raw)
    assert (r.status, r.value) == (status, value)


def test_to_json_handles_numpy_and_is_deterministic():
    np = pytest.importorskip("numpy")
    v = [{"between": np.array([0.0, 0.5]), "x": np.int64(3)}]
    assert nz.to_json(v) == '[{"between": [0.0, 0.5], "x": 3}]'
    assert nz.to_json({"name": "Mościckiego"}) == '{"name": "Mościckiego"}'


def test_overture_rules_as_numpy_from_parquet():
    np = pytest.importorskip("numpy")
    rules = np.array([{"min_speed": None, "max_speed": {"value": 50, "unit": "km/h"}, "is_max_speed_variable": None, "when": None, "between": np.array([0.0, 0.3])}], dtype=object)
    r = nz.parse_overture_speed(rules)
    assert r.status == "not_comparable" and r.detail == "partial"
    whole = np.array([{"min_speed": None, "max_speed": {"value": 50, "unit": "km/h"}, "is_max_speed_variable": None, "when": None, "between": None}], dtype=object)
    assert nz.parse_overture_speed(whole).value == 50
    surf = np.array([{"value": "paved", "between": np.array([0.0, 0.5])}], dtype=object)
    assert nz.parse_overture_surface(surf, ["paved"], []).status == "not_comparable"
