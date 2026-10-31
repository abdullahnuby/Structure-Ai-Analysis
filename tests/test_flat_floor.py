"""Flat plate / flat slab: direct-design moments, punching and column loads checked by hand."""

import copy
import json
import math
from pathlib import Path

import pytest

from structural_engine.design import run_design
from structural_engine.design.flat_floor import (
    panel_direction_moments,
    propose_flat_layout,
    punching_check,
)
from structural_engine.design.params import P
from structural_engine.design.report import to_markdown

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/design/floor_2x2.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def spec(system="flat_plate", **patch):
    s = copy.deepcopy(EXAMPLE)
    s.update({"system": system, "walls": [], **patch})
    return s


# ---- direct design moments ------------------------------------------------------------------------
def test_interior_span_moments_against_hand_values():
    m = panel_direction_moments(5.0, 4.5, 0.3, 11.6, True, True)
    Ln = 5.0 - 0.3
    M0 = 11.6 * 4.5 * Ln**2 / 8
    assert m["Ln"] == pytest.approx(Ln) and m["M0"] == pytest.approx(M0)
    assert m["neg_start"] == pytest.approx(0.65 * M0) and m["pos"] == pytest.approx(0.35 * M0)
    cs_w = 0.5 * min(5.0, 4.5)
    assert m["cs_width_m"] == pytest.approx(cs_w)
    assert m["strip_neg_start"]["cs_per_m"] == pytest.approx(0.75 * 0.65 * M0 / cs_w)
    assert m["strip_pos"]["ms_per_m"] == pytest.approx(0.40 * 0.35 * M0 / (4.5 - cs_w))


@pytest.mark.parametrize("left,right", [(True, True), (True, False), (False, True), (False, False)])
def test_static_equilibrium_of_the_panel_moments(left, right):
    """Positive moment + mean negative moment must equal M0 for every end condition."""
    m = panel_direction_moments(6.0, 5.0, 0.4, 12.0, left, right)
    assert m["pos"] + (m["neg_start"] + m["neg_end"]) / 2 == pytest.approx(m["M0"], rel=1e-12)


def test_end_span_puts_the_large_negative_moment_at_the_continuous_side():
    m = panel_direction_moments(6.0, 5.0, 0.4, 12.0, True, False)  # neighbour on the start side
    assert m["neg_start"] == pytest.approx(P.ddm_ext_int_neg * m["M0"])
    assert m["neg_end"] == pytest.approx(P.ddm_ext_neg * m["M0"])


def test_clear_span_never_drops_below_65_percent_of_the_span():
    assert panel_direction_moments(4.0, 4.0, 3.5, 10.0, True, True)["Ln"] == pytest.approx(
        0.65 * 4.0
    )


# ---- punching ----------------------------------------------------------------------------------
def test_interior_punching_matches_a_hand_calculation():
    wu = 11.6
    vu = wu * 22.5
    r = punching_check(vu, 300, 500, 144, "interior", None, wu, 30)
    bo = 2 * (300 + 144) + 2 * (500 + 144)
    vnet = vu - wu * (0.444 * 0.644)
    qu = 1.15 * vnet * 1000 / (bo * 144)
    qcup = 0.316 * math.sqrt(30 / 1.5) * min(1.0, 0.5 + 300 / 500)
    assert r["bo_mm"] == pytest.approx(bo) and r["qu_MPa"] == pytest.approx(qu, rel=1e-9)
    assert r["qcup_MPa"] == pytest.approx(qcup) and r["ratio"] == pytest.approx(qu / qcup)


def test_edge_and_corner_perimeters_are_shorter_and_more_heavily_factored():
    kw = dict(Vu_kN=200.0, b_mm=300, h_mm=500, d_mm=150, wu_kN_m2=10.0, fcu=30)
    i = punching_check(position="interior", free_edge=None, **kw)
    e = punching_check(position="edge", free_edge="x", **kw)
    c = punching_check(position="corner", free_edge="both", **kw)
    assert i["bo_mm"] > e["bo_mm"] > c["bo_mm"]
    assert (i["beta"], e["beta"], c["beta"]) == (1.15, 1.30, 1.50)
    assert e["bo_mm"] == pytest.approx(2 * (300 + 75) + (500 + 150))  # free edge perpendicular to x
    assert punching_check(position="edge", free_edge="y", **kw)["bo_mm"] == pytest.approx(
        2 * (500 + 75) + (300 + 150)
    )
    assert c["bo_mm"] == pytest.approx((300 + 75) + (500 + 75))


def test_slender_column_section_lowers_the_allowable_punching_stress():
    sq = punching_check(300.0, 400, 400, 150, "interior", None, 10.0, 30)
    slender = punching_check(300.0, 200, 800, 150, "interior", None, 10.0, 30)
    assert slender["qcup_MPa"] < sq["qcup_MPa"]


# ---- layout ----------------------------------------------------------------------------------------
def test_column_positions_on_a_3x3_grid():
    lay = propose_flat_layout(EXAMPLE["columns"])
    kinds = sorted(c["position"] for c in lay["columns"])
    assert kinds == ["corner"] * 4 + ["edge"] * 4 + ["interior"]
    assert len(lay["panels"]) == 4


def test_cell_with_a_missing_corner_is_reported_not_slabbed():
    cols = [c for c in EXAMPLE["columns"] if c["id"] != "C9"]
    lay = propose_flat_layout(cols)
    assert len(lay["panels"]) == 3 and any("lacks" in w for w in lay["warnings"])
    with pytest.raises(ValueError):
        propose_flat_layout(EXAMPLE["columns"][:3])


# ---- whole floor -----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plate():
    return run_design(spec())


def test_flat_plate_designs_and_balances(plate):
    assert plate["status"] == "OK", plate["failures"]
    assert plate["input"]["slab_thickness_mm"] == 180.0
    assert abs(plate["equilibrium"]["difference_pct"]) < 1e-9
    area = 90.0
    assert plate["equilibrium"]["applied_dead_kN"] == pytest.approx((25 * 0.18 + 1.5) * area)


def test_column_loads_are_tributary_areas(plate):
    wu = 1.4 * (25 * 0.18 + 1.5) + 1.6 * 2.0
    sw = 1.4 * 25 * 0.3 * 0.5 * 3.2
    c = plate["columns"]
    assert c["C5"]["Pu_per_floor_kN"] == pytest.approx(
        wu * 22.5 + sw
    )  # interior: four quarter panels
    assert c["C2"]["Pu_per_floor_kN"] == pytest.approx(wu * 22.5 / 2 + sw)
    assert c["C1"]["Pu_per_floor_kN"] == pytest.approx(wu * 22.5 / 4 + sw)
    assert c["C5"]["Pu_kN"] == pytest.approx(4 * c["C5"]["Pu_per_floor_kN"])


def test_unbalanced_moment_rules(plate):
    wu_l = 1.6 * 2.0
    Ln = 5.0 - 0.3
    interior_x = (
        0.07 * (0.5 * wu_l) * 4.5 * Ln**2 / 2
    )  # equal spans: 0.07*0.5*wLu*L2*Ln^2, half to this column
    assert plate["columns"]["C5"]["Muy_kNm"] == pytest.approx(interior_x, rel=1e-9)
    wu = 1.4 * (25 * 0.18 + 1.5) + 1.6 * 2.0
    Ln_y = 4.5 - 0.5
    ext = (
        P.ddm_ext_neg * wu * 5.0 * Ln_y**2 / 8 / 2
    )  # exterior in y: Mux from the y-direction panels
    assert plate["columns"]["C2"]["Mux_kNm"] == pytest.approx(ext, rel=1e-9)


def test_every_steel_zone_covers_its_moment(plate):
    for s in plate["slabs"].values():
        for e in s["design"].values():
            for k in (
                "bottom_cs",
                "bottom_ms",
                "top_start_cs",
                "top_end_cs",
                "top_start_ms",
                "top_end_ms",
            ):
                z = e[k]
                assert z["status"] == "OK" and z["capacity_kNm"] >= z["Mu_kNm"] - 1e-9


def test_shared_support_takes_the_larger_of_the_two_panel_moments():
    s = spec(columns=[dict(c) for c in EXAMPLE["columns"]])
    for c in s["columns"]:
        if c["x"] == 10.0:
            c["x"] = 8.0  # right bay becomes 3 m, left stays 5 m
    r = run_design(s)
    top_left = r["slabs"]["P1"]["design"]["x"]["top_end_cs"]
    top_right = r["slabs"]["P3"]["design"]["x"]["top_start_cs"]
    assert (
        top_left is top_right or top_left == top_right
    )  # same record: one governing value per support
    longer_panel = max(r["slabs"]["P1"]["design"]["x"]["M0"], r["slabs"]["P3"]["design"]["x"]["M0"])
    assert top_left["Mu_kNm"] > 0.5 * longer_panel / 5.0  # sanity: driven by the 5 m panel


def test_drop_panels_relieve_punching(plate):
    slab = run_design(spec("flat_slab"))
    assert slab["status"] == "OK", slab["failures"]
    a = plate["columns"]["C5"]["punching"]["at_column"]["ratio"]
    b = slab["columns"]["C5"]["punching"]["at_column"]["ratio"]
    assert b < a
    assert slab["columns"]["C5"]["drop_mm"] == pytest.approx(4500 / 3)  # shortest span / 3
    assert slab["columns"]["C5"]["punching"]["at_drop_edge"]["d_mm"] == pytest.approx(180 - 20 - 16)
    assert abs(slab["equilibrium"]["difference_pct"]) < 1e-9


def test_thin_slab_and_small_columns_fail_with_reasons():
    thin = run_design(spec(slab_thickness_mm=120))
    assert thin["status"] == "FAIL" and any("deflection rule" in f for f in thin["failures"])
    cols = [dict(c, b_mm=200, h_mm=200) for c in EXAMPLE["columns"]]
    heavy = run_design(spec(columns=cols, live_kN_m2=8.0, finishes_kN_m2=4.0))
    assert heavy["status"] == "FAIL" and any("punching FAIL" in f for f in heavy["failures"])


def test_walls_are_smeared_and_their_weight_is_conserved(plate):
    walls = [{"x0": 0, "y0": 0, "x1": 5, "y1": 0.0, "thickness_mm": 250}]
    r = run_design(spec(walls=walls))
    added = r["equilibrium"]["applied_dead_kN"] - plate["equilibrium"]["applied_dead_kN"]
    assert added == pytest.approx(5 * 0.25 * (3.2 - 0.18) * 18.0, rel=1e-9)
    far = run_design(spec(walls=[{"x0": 50, "y0": 50, "x1": 55, "y1": 50, "thickness_mm": 250}]))
    assert any("far from any slab panel" in w for w in far["warnings"])


def test_report_and_serialisation(plate):
    json.dumps(plate)
    md = to_markdown(plate)
    assert "Punching shear" in md and "column strip" in md.lower()
    assert any("lateral" in a for a in plate["assumptions"])


@pytest.mark.parametrize("patch", [{"floors": 0}, {"storey_height_m": 0}, {"live_kN_m2": -1}])
def test_invalid_input_is_rejected(patch):
    with pytest.raises(ValueError):
        run_design(spec(**patch))


def test_flat_slab_needs_a_positive_drop_thickness():
    with pytest.raises(ValueError):
        run_design(spec("flat_slab", drop_thickness_mm=0))
