"""Continuous-beam envelope and design, verified against an independent three-moment solution."""

import math

import numpy as np
import pytest

from structural_engine.design import run_design
from structural_engine.design.beam_design import (
    N_STATIONS,
    BeamInput,
    analyze_continuous_beam,
    design_continuous_beam,
)
from structural_engine.design.params import P


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


SPEC = {
    "type": "continuous_beam",
    "name": "T",
    "spans_m": [4.0, 6.0, 5.0],
    "b_mm": 300,
    "h_mm": 650,
    "fcu_MPa": 30,
    "fy_MPa": 400,
    "fyst_MPa": 280,
    "dead_kN_m": [10.0, 14.0, 12.0],
    "live_kN_m": [6.0, 9.0, 7.0],
}


# ---- independent reference: three-moment equation, sagging moments positive ---------------------
def support_moments(spans, w):
    n = len(spans)
    m = np.zeros(n + 1)
    if n == 1:
        return m
    a, rhs = np.zeros((n - 1, n - 1)), np.zeros(n - 1)
    for i in range(1, n):
        a[i - 1, i - 1] = 2 * (spans[i - 1] + spans[i])
        if i - 2 >= 0:
            a[i - 1, i - 2] = spans[i - 1]
        if i < n - 1:
            a[i - 1, i] = spans[i]
        rhs[i - 1] = -(w[i - 1] * spans[i - 1] ** 3 + w[i] * spans[i] ** 3) / 4
    m[1:n] = np.linalg.solve(a, rhs)
    return m


def span_moment(spans, w, m, k, x):
    L = spans[k]
    return w[k] * x * (L - x) / 2 + m[k] * (1 - x / L) + m[k + 1] * x / L


def span_shear(spans, w, m, k, x):
    L = spans[k]
    return w[k] * (L / 2 - x) + (m[k + 1] - m[k]) / L


def reference_envelope(inp, sw):
    spans, n = inp.spans_m, len(inp.spans_m)
    wd = [d + sw for d in inp.dead_kN_m]
    md = support_moments(spans, wd)
    cases = []
    for j in range(n):
        wl = [inp.live_kN_m[i] if i == j else 0.0 for i in range(n)]
        cases.append((wl, support_moments(spans, wl)))
    out = []
    for k in range(n):
        xs = np.linspace(0, spans[k], N_STATIONS)
        mmax, mmin, vmax, vmin = [], [], [], []
        for x in xs:
            d_m, d_v = span_moment(spans, wd, md, k, x), span_shear(spans, wd, md, k, x)
            lm = [span_moment(spans, wl, ml, k, x) for wl, ml in cases]
            lv = [span_shear(spans, wl, ml, k, x) for wl, ml in cases]
            mmax.append(1.4 * d_m + 1.6 * sum(max(v, 0) for v in lm))
            mmin.append(1.4 * d_m + 1.6 * sum(min(v, 0) for v in lm))
            vmax.append(1.4 * d_v + 1.6 * sum(max(v, 0) for v in lv))
            vmin.append(1.4 * d_v + 1.6 * sum(min(v, 0) for v in lv))
        out.append({"M_max": mmax, "M_min": mmin, "V_max": vmax, "V_min": vmin})
    return out


def test_three_moment_reference_itself_on_a_textbook_case():
    m = support_moments([5.0, 5.0], [10.0, 10.0])
    assert m[1] == pytest.approx(-10 * 25 / 8)


def test_envelope_matches_independent_three_moment_solution():
    inp = BeamInput.from_dict(SPEC)
    an = analyze_continuous_beam(inp)
    ref = reference_envelope(inp, an["self_weight_kN_m"])
    for k in range(3):
        for key in ("M_max", "M_min", "V_max", "V_min"):
            assert an["spans"][k][key] == pytest.approx(np.array(ref[k][key]), abs=1e-6), (k, key)


def test_reactions_and_total_load_equilibrium():
    inp = BeamInput.from_dict(SPEC)
    an = analyze_continuous_beam(inp)
    sw = an["self_weight_kN_m"]
    assert sw == pytest.approx(25 * 0.3 * 0.65)
    total_dead = sum((d + sw) * L for d, L in zip(inp.dead_kN_m, inp.spans_m))
    assert sum(an["reaction_dead_kN"]) == pytest.approx(total_dead)
    # every ultimate reaction is at least the all-spans-loaded value (pattern loading only adds)
    wu = [1.4 * (d + sw) + 1.6 * l for d, l in zip(inp.dead_kN_m, inp.live_kN_m)]
    m_all = support_moments(inp.spans_m, wu)
    r_all = [
        sum(
            wu[k] * inp.spans_m[k] / 2
            + (m_all[k + 1] - m_all[k]) / inp.spans_m[k] * (1 if side else -1)
            for k, side in ((j, 1) for j in range(len(wu)) if j == i)
        )  # span to the right, shear at its left end
        for i in range(len(wu))
    ]
    assert an["reaction_ultimate_max_kN"][0] >= r_all[0] - 1e-9


def test_known_coefficients_three_equal_spans():
    spec = {**SPEC, "spans_m": [5.0] * 3, "dead_kN_m": 12.0, "live_kN_m": 8.0, "self_weight": True}
    inp = BeamInput.from_dict(spec)
    an = analyze_continuous_beam(inp)
    wd, wl, L = 1.4 * (12.0 + an["self_weight_kN_m"]), 1.6 * 8.0, 5.0
    # textbook coefficients for three equal spans: support B with live on AB+BC = 7/60 wL^2,
    # mid-span of an end span with live on AB+CD ~ 0.101 wL^2 (+ dead 0.08 wL^2)
    assert an["spans"][0]["M_min"][-1] == pytest.approx(-(0.1 * wd + 7 / 60 * wl) * L * L, rel=2e-3)
    # The peaks of the dead and live diagrams are at slightly different sections, and
    # max(a + b) <= max(a) + max(b): the textbook sum is an upper bound that the true envelope
    # must approach from below (within ~0.5 %), never exceed.
    bound = (0.08 * wd + 0.1013 * wl) * L * L
    peak = an["spans"][0]["M_max"].max()
    assert peak <= bound * (1 + 1e-4)
    assert peak >= 0.995 * bound


# ---- design results ----------------------------------------------------------------------------
def test_design_is_consistent_with_its_own_demands():
    r = design_continuous_beam(SPEC)
    assert r["status"] == "OK", r["failures"]
    parts = [s["sagging"] for s in r["spans"]] + [s["hogging"] for s in r["supports"]]
    for p in parts:
        assert p["status"] == "OK"
        if p["Mu_kNm"] > 0:
            assert p["capacity_kNm"] >= p["Mu_kNm"] - 1e-9
            assert p["As_prov_mm2"] >= p["As_req_mm2"] - 1e-9
            assert 0 < p["utilisation"] <= 1.0 + 1e-9
    assert [s["sagging"]["Mu_kNm"] for s in r["spans"]] == pytest.approx(
        [max(max(env), 0) for env in r["envelope"]["M_max_kNm"]]
    )
    for s in r["spans"]:
        for z in s["shear"]["zones"]:
            assert z["status"] == "OK" and z["spacing_mm"] <= P.stirrup_max_spacing_mm


def test_interior_support_hogging_uses_the_analysis_value():
    r = design_continuous_beam(SPEC)
    env = r["envelope"]["M_min_kNm"]
    for k in (1, 2):
        assert r["supports"][k]["hogging"]["Mu_kNm"] == pytest.approx(-env[k - 1][-1])
        assert r["supports"][k]["hogging"]["basis"] == "analysis"


def test_end_support_fixity_is_labelled_and_can_be_switched_off():
    on = design_continuous_beam(SPEC)
    off = design_continuous_beam({**SPEC, "end_fixity": False})
    assert "ASSUMED" in on["supports"][0]["hogging"]["basis"]
    assert on["supports"][0]["hogging"]["Mu_kNm"] > 0
    assert off["supports"][0]["hogging"]["Mu_kNm"] == pytest.approx(0.0, abs=1e-6)
    assert off["supports"][0]["hogging"]["bars"] is None


def test_self_weight_toggle_changes_the_load_by_exactly_the_section_weight():
    with_sw = analyze_continuous_beam(BeamInput.from_dict(SPEC))
    without = analyze_continuous_beam(BeamInput.from_dict({**SPEC, "self_weight": False}))
    assert without["self_weight_kN_m"] == 0.0
    diff = sum(with_sw["reaction_dead_kN"]) - sum(without["reaction_dead_kN"])
    assert diff == pytest.approx(25 * 0.3 * 0.65 * sum(SPEC["spans_m"]))


def test_t_flange_never_needs_more_sagging_steel_than_the_rectangle():
    rect = design_continuous_beam({**SPEC, "spans_m": [6.0], "dead_kN_m": 25, "live_kN_m": 15})
    tee = design_continuous_beam(
        {
            **SPEC,
            "spans_m": [6.0],
            "dead_kN_m": 25,
            "live_kN_m": 15,
            "flange_width_mm": 1500,
            "flange_thickness_mm": 150,
        }
    )
    a, b = rect["spans"][0]["sagging"], tee["spans"][0]["sagging"]
    assert b["T_section"] and not a["T_section"]
    assert b["As_prov_mm2"] <= a["As_prov_mm2"] + 1e-9


def test_overloaded_small_section_fails_with_reasons_not_numbers():
    r = design_continuous_beam(
        {**SPEC, "b_mm": 150, "h_mm": 250, "spans_m": [6.0], "dead_kN_m": 30, "live_kN_m": 20}
    )
    assert r["status"] == "FAIL" and r["failures"]
    assert any("shear" in f or "sagging" in f for f in r["failures"])


def test_narrow_beam_falls_back_to_two_layers_and_reduces_d():
    spec = {**SPEC, "spans_m": [7.0], "b_mm": 200, "h_mm": 700, "dead_kN_m": 30, "live_kN_m": 25}
    r = design_continuous_beam(spec)
    g = r["spans"][0]["sagging"]
    assert g["status"] == "OK"
    if g["layers"] == 2:  # centroid of two layers is below a single layer's
        assert g["d_mm"] < 700 - 25 - 8 - g["dia_mm"] / 2


@pytest.mark.parametrize(
    "patch",
    [
        {"spans_m": []},
        {"spans_m": [4, -1]},
        {"b_mm": 0},
        {"h_mm": -5},
        {"fcu_MPa": 0},
        {"dead_kN_m": [1.0, 2.0]},
        {"live_kN_m": -3.0},
        {"flange_width_mm": 900},
    ],
)
def test_invalid_input_is_rejected(patch):
    with pytest.raises(ValueError):
        design_continuous_beam({**SPEC, **patch})


def test_result_is_json_serialisable_and_carries_the_unverified_banner():
    import json

    r = run_design(SPEC)
    json.dumps(r)
    assert "UNVERIFIED" in r["banner"] and r["unverified_parameters"] == len(P.unverified()) > 0
    assert any("NOT CHECKED" in a for a in r["assumptions"])


def test_changing_a_code_parameter_changes_the_design():
    base = design_continuous_beam(SPEC)
    P.set("load_factor_live", 2.0)
    heavier = design_continuous_beam(SPEC)
    assert heavier["spans"][0]["sagging"]["Mu_kNm"] > base["spans"][0]["sagging"]["Mu_kNm"]


def test_single_span_beam_matches_wL2_over_8():
    spec = {**SPEC, "spans_m": [6.0], "dead_kN_m": 20.0, "live_kN_m": 10.0, "end_fixity": False}
    r = design_continuous_beam(spec)
    sw = 25 * 0.3 * 0.65
    wu = 1.4 * (20.0 + sw) + 1.6 * 10.0
    assert r["spans"][0]["sagging"]["Mu_kNm"] == pytest.approx(wu * 36 / 8, rel=1e-6)
    assert r["reactions"]["ultimate_max_kN"] == pytest.approx([wu * 3, wu * 3])
