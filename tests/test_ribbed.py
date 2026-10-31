"""Ribbed (hollow-block) slab system, checked against hand statics of a single rib."""

import copy
import json
import math
from pathlib import Path

import pytest

from structural_engine.design import run_design
from structural_engine.design.params import P
from structural_engine.design.ribbed_design import rib_geometry, self_weight_kN_m2

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/design/floor_2x2.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


@pytest.fixture(scope="module")
def result():
    s = copy.deepcopy(EXAMPLE)
    s["system"] = "ribbed"
    return run_design(s)


def test_weight_per_m2_is_topping_plus_webs_plus_blocks():
    g = rib_geometry({}, 4.5)
    assert g["depth_mm"] == 230.0  # 4500/20 = 225 -> 230
    expected = 25 * 0.070 + 25 * (150 / 500) * (0.230 - 0.070) + 1.0
    assert self_weight_kN_m2(g) == pytest.approx(expected)


def test_rib_midspan_moment_and_capacity_match_hand_calculation(result):
    p = result["slabs"]["P1"]
    assert p["kind"] == "rib" and p["short_span_m"] == pytest.approx(4.5)
    sag = p["design"]["spans"][0]["sagging"]
    s = 0.5
    web = 25 * 0.150 * 0.230  # kN/m per rib, counted over the full depth by the beam engine
    dead = 25 * 0.070 * s + (1.5 + 1.0) * s + web
    wu = 1.4 * dead + 1.6 * 2.0 * s
    assert sag["Mu_kNm"] == pytest.approx(wu * 4.5**2 / 8, rel=1e-6)
    # independent capacity of the chosen bars (flange assumed to contain the stress block)
    n, dia = (int(x) for x in sag["bars"].split("Φ"))
    as_prov = n * math.pi * dia**2 / 4
    d = 230 - 20 - 6 - dia / 2
    fc, fs = 0.67 * 30 / 1.5, 400 / 1.15
    a = as_prov * fs / (fc * 500)
    assert a < 70  # block inside the 70 mm topping
    assert sag["capacity_kNm"] == pytest.approx(as_prov * fs * (d - a / 2) / 1e6, rel=1e-3)
    assert sag["capacity_kNm"] >= sag["Mu_kNm"]


def test_ribs_load_only_the_long_side_beams_and_the_load_still_balances(result):
    assert abs(result["equilibrium"]["difference_pct"]) < 1e-9
    area = 90.0
    own = self_weight_kN_m2(rib_geometry({}, 4.5))
    slab = (own + 1.5) * area
    beams = 25 * 0.25 * 0.5 * (3 * 10 + 3 * 9)
    walls = 38 * 2.7 * 0.25 * 18
    assert result["equilibrium"]["applied_dead_kN"] == pytest.approx(slab + beams + walls, rel=1e-9)
    # the 5 m beams (along x) carry the slabs; the 4.5 m beams (along y) only the walls and themselves
    bx = result["beams"]["BX2"]["loads"][0]["statics_dead_kN_m"]
    by = result["beams"]["BY5"]["loads"][0]["statics_dead_kN_m"]
    assert bx > 4 * by


def test_bar_diameters_are_restored_after_the_rib_design(result):
    assert P.bar_diameters_mm == [12, 16, 18, 20, 22, 25, 28, 32]


def test_report_lists_rib_schedule(result):
    from structural_engine.design.report import to_markdown

    md = to_markdown(result)
    assert "rib 230" in md and "per rib" in md


@pytest.mark.parametrize("rib", [{"width_mm": 600}, {"topping_mm": 300}, {"spacing_mm": -5}])
def test_invalid_rib_geometry_is_rejected(rib):
    s = copy.deepcopy(EXAMPLE)
    s.update(system="ribbed", rib=rib)
    with pytest.raises(ValueError):
        run_design(s)


def test_unknown_system_is_rejected():
    s = copy.deepcopy(EXAMPLE)
    s["system"] = "teapot"
    with pytest.raises(ValueError, match="unknown system"):
        run_design(s)
