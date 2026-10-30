import math

import pytest

from structural_engine.design.params import P
from structural_engine.design.slab_design import design_slab_strip

SPEC = {
    "type": "slab_strip",
    "name": "S",
    "spans_m": [4.0, 4.0],
    "thickness_mm": 140,
    "fcu_MPa": 30,
    "fy_MPa": 400,
    "cover_mm": 20,
    "dead_kN_m2": 1.5,
    "live_kN_m2": 2.0,
}


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def wu_parts(spec=SPEC):
    sw = 25 * spec["thickness_mm"] / 1000
    return 1.4 * (spec["dead_kN_m2"] + sw), 1.6 * spec["live_kN_m2"]


def test_two_span_moments_match_textbook_coefficients():
    r = design_slab_strip(SPEC)
    wd, wl = wu_parts()
    L = 4.0
    # both spans loaded -> interior support wL^2/8 (the governing hogging case)
    assert r["supports"][1]["hogging"]["Mu_kNm"] == pytest.approx((wd + wl) * L * L / 8, rel=1e-6)
    # sagging in span 1, dead on both spans + live on span 1 only (hand statics):
    # R_A = 3/8*wd*L + (wl*L/2 - wl*L/16) ; M(x) = R_A*x - (wd+wl)*x^2/2 -> max = R_A^2/(2*(wd+wl))
    ra = 3 / 8 * wd * L + (wl * L / 2 - wl * L / 16)
    hand = ra**2 / (2 * (wd + wl))
    assert r["spans"][0]["sagging"]["Mu_kNm"] == pytest.approx(hand, rel=2e-3)
    # and it stays below the (non-simultaneous) sum of the textbook peaks
    assert hand <= (9 / 128 * wd + 49 / 512 * wl) * L * L


def test_every_zone_is_covered_by_its_bars_and_respects_the_detailing_limits():
    r = design_slab_strip(SPEC)
    assert r["status"] == "OK", r["failures"]
    h = SPEC["thickness_mm"]
    parts = [s["sagging"] for s in r["spans"]] + [s["hogging"] for s in r["supports"]]
    for p in parts:
        assert p["capacity_kNm"] >= p["Mu_kNm"] - 1e-9
        assert p["As_prov_mm2_per_m"] >= P.slab_min_steel_ratio * 1000 * h - 1e-9
        assert 100 <= p["spacing_mm"] <= P.slab_max_bar_spacing_mm
        area = math.pi * p["dia_mm"] ** 2 / 4
        assert p["As_prov_mm2_per_m"] == pytest.approx(1000 * area / p["spacing_mm"])


def test_distribution_steel_is_the_minimum_ratio():
    r = design_slab_strip(SPEC)
    assert r["distribution_steel"]["As_mm2_per_m"] == pytest.approx(0.0015 * 1000 * 140)


def test_heavier_load_never_gives_less_steel():
    light = design_slab_strip(SPEC)
    heavy = design_slab_strip({**SPEC, "live_kN_m2": 5.0, "dead_kN_m2": 3.0})
    assert (
        heavy["supports"][1]["hogging"]["As_prov_mm2_per_m"]
        >= light["supports"][1]["hogging"]["As_prov_mm2_per_m"]
    )


def test_thin_overloaded_slab_fails_with_a_reason():
    r = design_slab_strip(
        {**SPEC, "spans_m": [6.0], "thickness_mm": 100, "live_kN_m2": 10.0, "dead_kN_m2": 5.0}
    )
    assert r["status"] == "FAIL" and r["failures"]


def test_shear_check_is_concrete_only_and_flags_a_thin_slab():
    ok = design_slab_strip(SPEC)
    assert all(s["status"] == "OK" for s in ok["shear"])
    bad = design_slab_strip(
        {**SPEC, "spans_m": [2.0], "thickness_mm": 80, "live_kN_m2": 60.0, "dead_kN_m2": 30.0}
    )
    assert any("shear" in f and "INCREASE_THICKNESS" in f for f in bad["failures"])


@pytest.mark.parametrize("patch", [{"thickness_mm": 0}, {"spans_m": []}, {"live_kN_m2": -1.0}])
def test_invalid_input_is_rejected(patch):
    with pytest.raises(ValueError):
        design_slab_strip({**SPEC, **patch})
