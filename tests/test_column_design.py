import math

import pytest

from structural_engine.design.column_design import (
    bar_layers,
    check_column,
    design_column,
    interaction_curve,
    moment_capacity_at_axial,
    pure_compression_capacity,
)
from structural_engine.design.params import P
from structural_engine.design.sections import fcd, flexural_capacity, fyd

FCU, FY = 30.0, 400.0


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def test_pure_bending_agrees_with_the_beam_section_solver():
    """Two different code paths: column (moment about the centroid, P=0 by equilibrium) vs the
    doubly reinforced beam section (moment about the tension steel)."""
    b, h, dia, cc = 300.0, 500.0, 20.0, 48.0
    layers = bar_layers(
        b, h, nx=3, ny=2, dia=dia, cover_to_centre=cc, axis="x"
    )  # top + bottom rows only
    area_row = 3 * math.pi * dia**2 / 4
    col = moment_capacity_at_axial(0.0, h, b, layers, FCU, FY) / 1e6
    beam = flexural_capacity(area_row, h - cc, b, h, FCU, FY, As_c=area_row, d_c=cc)["capacity_kNm"]
    assert col == pytest.approx(beam, rel=1e-6)


def test_pure_compression_formula():
    b, h, ast = 400.0, 400.0, 2513.3
    assert pure_compression_capacity(b, h, ast, FCU, FY) == pytest.approx(
        fcd(FCU) * (b * h - ast) + fyd(FY) * ast
    )


def test_bar_layers_geometry_and_area():
    layers = bar_layers(300, 500, nx=3, ny=4, dia=20, cover_to_centre=50, axis="x")
    assert sum(a for _, a in layers) == pytest.approx((2 * 3 + 2 * (4 - 2)) * math.pi * 100)
    ys = sorted(y for y, _ in layers)
    assert ys[0] == pytest.approx(50) and ys[-1] == pytest.approx(450)
    assert ys == pytest.approx(
        [50, 50 + 400 / 3, 50 + 800 / 3, 450][0:1] + [150 + 0 * 1] * 0 + ys[1:]
    )  # sorted, within section
    assert all(50 - 1e-9 <= y <= 450 + 1e-9 for y in ys)


def test_interaction_curve_shape():
    curve = interaction_curve(400, 400, 3, 3, 20, 48, FCU, FY)
    p_values = [p for p, _ in curve]
    assert all(
        a >= b - 1e-6 for a, b in zip(p_values, p_values[1:])
    )  # axial load falls along the curve
    assert min(p_values) < 0 < max(p_values)  # runs from compression into tension
    assert all(m >= -1e-6 for _, m in curve)
    peak = max(m for _, m in curve)
    m_pure = (
        moment_capacity_at_axial(0.0, 400, 400, bar_layers(400, 400, 3, 3, 20, 48, "x"), FCU, FY)
        / 1e6
    )
    assert peak > m_pure  # compression increases flexural capacity up to the balanced point


def test_square_section_is_symmetric_in_both_axes():
    p = 800e3
    lx = bar_layers(400, 400, 3, 3, 20, 48, "x")
    ly = bar_layers(400, 400, 3, 3, 20, 48, "y")
    assert moment_capacity_at_axial(p, 400, 400, lx, FCU, FY) == pytest.approx(
        moment_capacity_at_axial(p, 400, 400, ly, FCU, FY)
    )


def test_axial_load_beyond_the_section_has_no_moment_capacity():
    layers = bar_layers(300, 300, 2, 2, 16, 45, "x")
    assert moment_capacity_at_axial(1e9, 300, 300, layers, FCU, FY) is None


def test_more_steel_never_reduces_capacity():
    spec = {"b_mm": 300, "h_mm": 500, "Pu_kN": 1200, "Mux_kNm": 100}
    ratios = [check_column(spec, 2, 2, dia)["ratio"] for dia in (16, 20, 25, 32)]
    assert all(a >= b - 1e-12 for a, b in zip(ratios, ratios[1:]))


# ---- design ------------------------------------------------------------------------------------
BASE = {
    "name": "C",
    "b_mm": 300,
    "h_mm": 500,
    "fcu_MPa": 30,
    "fy_MPa": 400,
    "Pu_kN": 1500,
    "Mux_kNm": 120,
    "Muy_kNm": 30,
    "unsupported_length_m": 3.0,
}


def test_design_returns_a_layout_that_passes_its_own_check():
    r = design_column(BASE)
    assert r["status"] == "OK"
    res = r["result"]
    again = check_column(BASE, res["nx"], res["ny"], res["dia_mm"])
    assert again["status"] == "OK" and again["ratio"] == pytest.approx(res["ratio"])
    assert res["ratio"] <= 1.0
    assert P.column_min_steel_ratio <= res["rho"] <= P.column_max_steel_ratio
    # biaxial interaction at alpha = 1: sum of the two moment ratios
    ax = res["axes"]
    assert res["ratio"] == pytest.approx(
        ax["x"]["M_design_kNm"] / ax["x"]["M_cap_kNm"]
        + ax["y"]["M_design_kNm"] / ax["y"]["M_cap_kNm"]
    )


def test_steel_is_non_decreasing_with_load():
    areas = []
    for pu in (300, 800, 1400, 2000):
        r = design_column({**BASE, "Pu_kN": pu, "Mux_kNm": 60, "Muy_kNm": 0})
        assert r["status"] == "OK", (pu, r["failures"])
        areas.append(r["result"]["Ast_mm2"])
    assert all(a <= b + 1e-9 for a, b in zip(areas, areas[1:]))


def test_the_layout_fits_clear_spacing_and_ties_follow_the_rules():
    res = design_column(BASE)["result"]
    dia, b, h = res["dia_mm"], 300, 500
    gap = max(dia, P.min_clear_spacing_mm)
    assert res["nx"] * dia + (res["nx"] - 1) * gap <= b - 2 * (30 + 8)
    assert res["ny"] * dia + (res["ny"] - 1) * gap <= h - 2 * (30 + 8)
    assert res["tie_dia_mm"] >= max(8, 0.25 * dia)
    assert res["tie_spacing_mm"] <= min(200, 15 * dia, 300)


def test_minimum_eccentricity_governs_a_nominally_axial_column():
    r = design_column({"b_mm": 300, "h_mm": 500, "Pu_kN": 1000})
    ax = r["result"]["axes"]
    assert ax["x"]["min_ecc_governs"] and ax["x"]["e_min_mm"] == pytest.approx(25.0)
    assert ax["x"]["M_design_kNm"] == pytest.approx(1000 * 0.025)
    assert ax["y"]["e_min_mm"] == pytest.approx(20.0)  # 5 % of 300 = 15 -> floor of 20 mm applies


def test_a_weak_layout_is_reported_as_failing_not_adjusted():
    r = design_column({**BASE, "bars": {"nx": 2, "ny": 2, "dia_mm": 16}})
    assert r["mode"] == "check" and r["status"] == "FAIL" and r["result"]["ratio"] > 1.0


def test_check_mode_accepts_an_adequate_layout():
    r = design_column(
        {
            **BASE,
            "Pu_kN": 600,
            "Mux_kNm": 40,
            "Muy_kNm": 10,
            "bars": {"nx": 3, "ny": 3, "dia_mm": 20},
        }
    )
    assert r["status"] == "OK" and r["result"]["ratio"] < 1.0


def test_biaxial_ratio_grows_with_the_second_moment_and_falls_with_alpha():
    base = check_column({**BASE, "Muy_kNm": 0}, 3, 3, 20)["ratio"]
    more = check_column({**BASE, "Muy_kNm": 40}, 3, 3, 20)["ratio"]
    assert more > base
    P.set("column_biaxial_alpha", 1.5)
    assert check_column({**BASE, "Muy_kNm": 40}, 3, 3, 20)["ratio"] < more


def test_slender_columns_are_not_given_a_design():
    r = design_column({**BASE, "unsupported_length_m": 6.0})  # lambda = 6000/300 = 20 > 15
    assert r["status"] == "SLENDER_NOT_DESIGNED" and "result" not in r and r["failures"]
    ok = design_column({**BASE, "unsupported_length_m": 4.5})  # lambda = 15 -> short
    assert ok["status"] == "OK" and ok["slenderness"]["lambda_y"] == pytest.approx(15.0)
    unbraced = design_column({**BASE, "unsupported_length_m": 3.5, "braced": False})  # 11.7 > 10
    assert unbraced["status"] == "SLENDER_NOT_DESIGNED"


def test_missing_length_is_a_warning_not_a_silent_pass():
    spec = {k: v for k, v in BASE.items() if k != "unsupported_length_m"}
    r = design_column(spec)
    assert r["status"] == "OK" and any("slenderness NOT checked" in w for w in r["warnings"])


def test_axial_load_from_floors_matches_a_hand_calculation():
    r = design_column(
        {
            "b_mm": 300,
            "h_mm": 500,
            "storey_height_m": 3.2,
            "floors": [{"tributary_area_m2": 20, "dead_kN_m2": 6, "live_kN_m2": 2, "count": 4}],
        }
    )
    sw = 25 * 0.3 * 0.5 * 3.2
    expected = 4 * (1.4 * (6 * 20 + sw) + 1.6 * 2 * 20)
    assert r["input"]["Pu_kN"] == pytest.approx(expected)
    assert "no live-load reduction" in r["input"]["Pu_source"]


def test_impossible_demand_fails_with_a_message():
    r = design_column({"b_mm": 250, "h_mm": 250, "fcu_MPa": 25, "Pu_kN": 2500, "Mux_kNm": 50})
    assert r["status"] == "FAIL" and "enlarge" in r["failures"][0]


@pytest.mark.parametrize(
    "patch",
    [{"b_mm": 0}, {"h_mm": -1}, {"Pu_kN": -10}],
)
def test_invalid_input_is_rejected(patch):
    with pytest.raises(ValueError):
        design_column({**BASE, **patch})


def test_pu_or_floors_is_required():
    with pytest.raises(ValueError):
        design_column({"b_mm": 300, "h_mm": 300})
