"""Section mechanics against hand calculations written in the test (independent of the solver)."""

import math

import pytest

from structural_engine.design.params import P
from structural_engine.design.sections import (
    apply_minimum_steel,
    design_flexure,
    design_shear,
    flexural_capacity,
    minimum_flexural_steel,
    select_bars,
)

FCU, FY, B, H, D = 30.0, 400.0, 250.0, 600.0, 550.0


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def hand_as(mu_knm, b=B, d=D, fcu=FCU, fy=FY):
    """Closed form for a singly reinforced rectangle: Mu = As*fyd*(d - As*fyd/(2*fcd*b))."""
    fc, fs = 0.67 * fcu / 1.5, fy / 1.15
    qa, qb, qc = fs * fs / (2 * fc * b), -fs * d, mu_knm * 1e6
    return (-qb - math.sqrt(qb * qb - 4 * qa * qc)) / (2 * qa)


@pytest.mark.parametrize("mu", [20, 80, 150, 250])
def test_singly_reinforced_matches_closed_form(mu):
    r = design_flexure(mu, B, H, D, FCU, FY, d_c=50)
    assert r["status"] == "OK" and not r["doubly"]
    assert r["As_mm2"] == pytest.approx(hand_as(mu), rel=1e-6)
    assert r["capacity_check_kNm"] == pytest.approx(mu, rel=1e-6)


def test_ductility_limit_forces_compression_steel():
    fc = 0.67 * FCU / 1.5
    a = 0.8 * P.c_over_d_max * D
    m_lim = fc * B * a * (D - a / 2) / 1e6  # hand-calculated limiting moment
    below = design_flexure(m_lim * 0.99, B, H, D, FCU, FY, d_c=50)
    above = design_flexure(m_lim * 1.25, B, H, D, FCU, FY, d_c=50)
    assert not below["doubly"] and above["doubly"]
    assert above["As_c_mm2"] > 0 and above["c_over_d"] == pytest.approx(P.c_over_d_max, abs=1e-6)
    assert above["capacity_check_kNm"] == pytest.approx(m_lim * 1.25, rel=1e-6)


def test_compression_steel_that_cannot_work_is_refused():
    r = design_flexure(900, B, H, D, FCU, FY, d_c=0.0)
    assert r["status"] == "FAIL" and r["reason"] == "COMPRESSION_STEEL_NOT_EFFECTIVE"


def test_zero_moment_needs_no_steel():
    assert design_flexure(0.0, B, H, D, FCU, FY)["As_mm2"] == 0.0


def test_t_section_equals_wide_rectangle_when_block_is_in_flange():
    t = design_flexure(150, B, H, D, FCU, FY, bf=1000, tf=120)
    rect = design_flexure(150, 1000, H, D, FCU, FY)
    assert t["As_mm2"] == pytest.approx(rect["As_mm2"], rel=1e-9)


def test_t_section_with_deep_block_matches_hand_equilibrium():
    bf, tf, bw, mu = (
        800.0,
        100.0,
        250.0,
        600.0,
    )  # flange alone gives 536 kN.m, so the web is engaged
    r = design_flexure(mu, bw, H, D, FCU, FY, bf=bf, tf=tf)
    assert r["status"] == "OK"
    fc, fs = 0.67 * FCU / 1.5, FY / 1.15

    # solve a by hand from moment equilibrium of the T block (a > tf), then As from force equilibrium
    def moment(a):
        c1, y1 = fc * bf * tf, tf / 2
        c2, y2 = fc * bw * (a - tf), tf + (a - tf) / 2
        return (c1 * (D - y1) + c2 * (D - y2)) / 1e6

    assert moment(tf) < mu < moment(0.8 * 0.45 * D)  # the block really is deeper than the flange
    lo, hi = tf, 0.8 * 0.45 * D
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if moment(mid) < mu else (lo, mid)
    a = (lo + hi) / 2
    as_hand = (fc * bf * tf + fc * bw * (a - tf)) / fs
    assert r["As_mm2"] == pytest.approx(as_hand, rel=1e-5)


def test_stress_block_parameters_are_honoured():
    base = flexural_capacity(1000, D, B, H, FCU, FY)["capacity_kNm"]
    P.set("concrete_stress_factor", 0.5)
    weaker = flexural_capacity(1000, D, B, H, FCU, FY)["capacity_kNm"]
    assert weaker < base
    P.reset()
    P.set("gamma_s", 1.0)
    assert flexural_capacity(1000, D, B, H, FCU, FY)["capacity_kNm"] > base


def test_minimum_steel_rules():
    a_min = minimum_flexural_steel(B, D, FCU, FY)
    assert a_min == pytest.approx(max(0.225 * math.sqrt(FCU) / FY, 1.1 / FY) * B * D)
    assert apply_minimum_steel(10.0, B, D, FCU, FY) == pytest.approx(
        13.0
    )  # capped at 1.3 x required
    assert apply_minimum_steel(a_min * 2, B, D, FCU, FY) == pytest.approx(a_min * 2)
    assert apply_minimum_steel(0.0, B, D, FCU, FY) == 0.0


def test_shear_hand_values():
    root = math.sqrt(FCU / 1.5)
    r = design_shear(200, B, D, FCU, 280, 8)
    qu = 200e3 / (B * D)
    assert r["qu_MPa"] == pytest.approx(qu) and r["qcu_MPa"] == pytest.approx(0.24 * root)
    qsu = qu - 0.5 * 0.24 * root
    s_hand = 2 * math.pi * 8**2 / 4 / (qsu * B / (280 / 1.15))
    assert r["status"] == "OK" and r["basis"] == "calculated"
    assert r["spacing_mm"] == pytest.approx(math.floor(min(s_hand, 200, 0.75 * D) / 5) * 5)


def test_shear_that_needs_stirrups_closer_than_practical_is_refused():
    r = design_shear(300, B, D, FCU, 280, 8)  # needs ~60 mm spacing
    assert r["status"] == "FAIL" and "CLOSE" in r["reason"]


def test_shear_limits():
    assert design_shear(20, B, D, FCU, 280, 8)["basis"] == "minimum"
    too_big = design_shear(600, B, D, FCU, 280, 8)
    assert too_big["status"] == "FAIL" and too_big["reason"] == "SECTION_TOO_SMALL_FOR_SHEAR"
    tight = design_shear(0.9 * 0.7 * math.sqrt(FCU / 1.5) * B * D / 1000, B, D, FCU, 280, 6)
    assert tight["status"] == "FAIL" and "CLOSE" in tight["reason"]


def test_bar_selection_fits_and_covers():
    sel = select_bars(1200, B, 25, 8)
    assert sel and sel["As_prov_mm2"] >= 1200
    n, dia = sel["n"], sel["dia"]
    avail = B - 2 * (25 + 8)
    assert n * dia + (n - 1) * max(dia, 25) <= avail
    assert select_bars(4000, B, 25, 8) is None  # nothing fits in one layer
    two = select_bars(4000, B, 25, 8, layers=2)
    assert two and two["As_prov_mm2"] >= 4000 and two["layers"] == 2
    assert select_bars(10, B, 25, 8)["n"] == 2  # never fewer than two bars
