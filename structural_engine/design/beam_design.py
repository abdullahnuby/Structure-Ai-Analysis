"""Continuous RC beam: analysis with live-load patterns, then flexure and shear design.

Analysis: each span is one Euler-Bernoulli member (gross rectangular section, Ec from fcu),
supports are rigid simple supports under the beam. The ultimate envelope is built by exact
superposition of one dead-load case and one live-load case per span, so every pattern
(checkerboard, adjacent spans, all spans) is covered without enumerating combinations.

Units: spans in m, loads in kN/m, section dimensions in mm, moments in kN*m, forces in kN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..frame2d import Frame2D, FrameResult
from .params import P, STATUS_BANNER
from .sections import (
    Ec_MPa,
    KNM_TO_NMM,
    apply_minimum_steel,
    design_flexure,
    design_shear,
    flexural_capacity,
    select_bars,
)

N_STATIONS = 41  # points per span for the envelope (span/40 spacing)


def _per_span(value, n: int, name: str) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)] * n
    value = [float(v) for v in value]
    if len(value) != n:
        raise ValueError(f"{name}: expected {n} values (one per span), got {len(value)}")
    return value


@dataclass
class BeamInput:
    name: str
    spans_m: list[float]
    b_mm: float
    h_mm: float
    fcu: float
    fy: float
    fyst: float
    cover_mm: float
    stirrup_dia_mm: float
    dead_kN_m: list[float]
    live_kN_m: list[float]
    self_weight: bool
    support_width_mm: list[float]
    flange_width_mm: float | None
    flange_thickness_mm: float | None
    end_fixity: bool

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BeamInput":
        spans = [float(x) for x in data["spans_m"]]
        if not spans or min(spans) <= 0:
            raise ValueError("spans_m must be a non-empty list of positive lengths")
        n = len(spans)
        b, h = float(data["b_mm"]), float(data["h_mm"])
        if b <= 0 or h <= 0:
            raise ValueError("b_mm and h_mm must be positive")
        fcu, fy = float(data.get("fcu_MPa", 30.0)), float(data.get("fy_MPa", 400.0))
        if fcu <= 0 or fy <= 0:
            raise ValueError("fcu_MPa and fy_MPa must be positive")
        dead = _per_span(data.get("dead_kN_m", 0.0), n, "dead_kN_m")
        live = _per_span(data.get("live_kN_m", 0.0), n, "live_kN_m")
        if min(dead) < 0 or min(live) < 0:
            raise ValueError("loads are entered as positive downward values")
        bf, tf = data.get("flange_width_mm"), data.get("flange_thickness_mm")
        if (bf is None) != (tf is None):
            raise ValueError("give both flange_width_mm and flange_thickness_mm, or neither")
        return BeamInput(
            name=str(data.get("name", "beam")),
            spans_m=spans,
            b_mm=b,
            h_mm=h,
            fcu=fcu,
            fy=fy,
            fyst=float(data.get("fyst_MPa", 280.0)),
            cover_mm=float(data.get("cover_mm", 25.0)),
            stirrup_dia_mm=float(data.get("stirrup_dia_mm", 8.0)),
            dead_kN_m=dead,
            live_kN_m=live,
            self_weight=bool(data.get("self_weight", True)),
            support_width_mm=_per_span(
                data.get("support_width_mm", 300.0), n + 1, "support_width_mm"
            ),
            flange_width_mm=None if bf is None else float(bf),
            flange_thickness_mm=None if tf is None else float(tf),
            end_fixity=bool(data.get("end_fixity", True)),
        )


# ------------------------------------------------------------------------------------------------
# analysis
# ------------------------------------------------------------------------------------------------
def _build_frame(inp: BeamInput) -> Frame2D:
    E = Ec_MPa(inp.fcu) * 1000.0  # kN/m2
    A = inp.b_mm * inp.h_mm / 1e6
    I = inp.b_mm * inp.h_mm**3 / 12.0 / 1e12
    f = Frame2D()
    x = 0.0
    f.add_node(0, 0.0, 0.0)
    for k, length in enumerate(inp.spans_m, 1):
        x += length
        f.add_node(k, x, 0.0)
        f.add_member(k, k - 1, k, E, A, I)
    f.add_support(0, True, True, False)
    for k in range(1, len(inp.spans_m) + 1):
        f.add_support(k, False, True, False)
    return f


def self_weight_kN_m(inp: BeamInput) -> float:
    return P.unit_weight_concrete_kN_m3 * inp.b_mm * inp.h_mm / 1e6 if inp.self_weight else 0.0


def analyze_continuous_beam(inp: BeamInput) -> dict[str, Any]:
    n = len(inp.spans_m)
    sw = self_weight_kN_m(inp)

    def solve(dead: list[float], live: list[float]) -> FrameResult:
        f = _build_frame(inp)
        for k in range(1, n + 1):
            f.add_member_udl(k, qy=-(dead[k - 1] + live[k - 1]))
        return f.solve()

    dead_case = solve([d + sw for d in inp.dead_kN_m], [0.0] * n)
    live_cases = [
        solve([0.0] * n, [inp.live_kN_m[i] if i == j else 0.0 for i in range(n)]) for j in range(n)
    ]
    fd, fl = P.load_factor_dead, P.load_factor_live

    spans = []
    for k, length in enumerate(inp.spans_m, 1):
        xs = np.linspace(0.0, length, N_STATIONS)
        md = np.array([dead_case.moment(k, x) for x in xs])
        vd = np.array([dead_case.shear(k, x) for x in xs])
        ml = np.array([[c.moment(k, x) for x in xs] for c in live_cases])
        vl = np.array([[c.shear(k, x) for x in xs] for c in live_cases])
        spans.append(
            {
                "x_m": xs,
                "M_max": fd * md + fl * np.maximum(ml, 0).sum(axis=0),
                "M_min": fd * md + fl * np.minimum(ml, 0).sum(axis=0),
                "V_max": fd * vd + fl * np.maximum(vl, 0).sum(axis=0),
                "V_min": fd * vd + fl * np.minimum(vl, 0).sum(axis=0),
            }
        )
    react_d = [float(dead_case.reactions[k][1]) for k in range(n + 1)]
    react_l = [[float(c.reactions[k][1]) for k in range(n + 1)] for c in live_cases]
    react_l_max = [sum(max(r[k], 0.0) for r in react_l) for k in range(n + 1)]
    return {
        "self_weight_kN_m": sw,
        "spans": spans,
        "reaction_dead_kN": react_d,
        "reaction_live_max_kN": react_l_max,
        "reaction_ultimate_max_kN": [fd * react_d[k] + fl * react_l_max[k] for k in range(n + 1)],
    }


# ------------------------------------------------------------------------------------------------
# section design with real bar selection
# ------------------------------------------------------------------------------------------------
def _design_tension_steel(
    Mu: float, inp: BeamInput, bf: float | None, tf: float | None, label: str
) -> dict[str, Any]:
    """Choose bars for |Mu| and verify the provided section against Mu (strain compatibility)."""
    b, h = inp.b_mm, inp.h_mm
    out: dict[str, Any] = {"location": label, "Mu_kNm": Mu}
    if Mu <= 1e-9:
        return {**out, "status": "OK", "bars": None, "As_prov_mm2": 0.0, "note": "no moment demand"}
    cs = inp.cover_mm + inp.stirrup_dia_mm
    last_reason = "NO_BAR_ARRANGEMENT_FITS"
    for layers in (1, 2):
        dia_guess = 20.0
        for _ in range(6):
            offset = (
                0.0 if layers == 1 else (dia_guess + max(dia_guess, P.min_clear_spacing_mm)) / 2.0
            )
            d = h - cs - dia_guess / 2.0 - offset
            d_c = cs + 8.0
            req = design_flexure(Mu, b, h, d, inp.fcu, inp.fy, d_c, bf, tf)
            if req["status"] != "OK":
                last_reason = req.get("reason", "FLEXURE_FAILED")
                break
            as_target = apply_minimum_steel(req["As_mm2"], b, d, inp.fcu, inp.fy)
            sel = select_bars(as_target, b, inp.cover_mm, inp.stirrup_dia_mm, layers)
            if sel is None:
                last_reason = "NO_BAR_ARRANGEMENT_FITS"
                break
            if sel["dia"] == dia_guess:
                comp = None
                if req["As_c_mm2"] > 0:
                    comp = select_bars(req["As_c_mm2"], b, inp.cover_mm, inp.stirrup_dia_mm, 1)
                    if comp is None:
                        last_reason = "COMPRESSION_BARS_DO_NOT_FIT"
                        break
                cap = flexural_capacity(
                    sel["As_prov_mm2"],
                    d,
                    b,
                    h,
                    inp.fcu,
                    inp.fy,
                    comp["As_prov_mm2"] if comp else 0.0,
                    d_c,
                    bf,
                    tf,
                )
                if cap["capacity_kNm"] + 1e-6 >= Mu:
                    return {
                        **out,
                        "status": "OK",
                        "bars": sel["label"],
                        "layers": layers,
                        "dia_mm": sel["dia"],
                        "As_req_mm2": req["As_mm2"],
                        "As_min_applied_mm2": as_target,
                        "As_prov_mm2": sel["As_prov_mm2"],
                        "compression_bars": comp["label"] if comp else None,
                        "As_c_prov_mm2": comp["As_prov_mm2"] if comp else 0.0,
                        "d_mm": d,
                        "c_over_d": cap["c_over_d"],
                        "capacity_kNm": cap["capacity_kNm"],
                        "utilisation": Mu / cap["capacity_kNm"],
                        "T_section": bf is not None,
                    }
                last_reason = "PROVIDED_STEEL_BELOW_DEMAND"
                break
            dia_guess = float(sel["dia"])
    return {**out, "status": "FAIL", "reason": last_reason}


def _shear_zones(
    inp: BeamInput, span_idx: int, span: dict[str, np.ndarray], d_mm: float
) -> list[dict[str, Any]]:
    length = inp.spans_m[span_idx]
    xs = span["x_m"]
    v_abs = np.maximum(np.abs(span["V_max"]), np.abs(span["V_min"]))
    xc_left = inp.support_width_mm[span_idx] / 2000.0 + d_mm / 1000.0
    xc_right = inp.support_width_mm[span_idx + 1] / 2000.0 + d_mm / 1000.0
    clamped = np.empty_like(v_abs)
    for k, x in enumerate(xs):  # shear inside the critical distance equals the value at it
        xe = min(max(x, xc_left), length - xc_right) if xc_left + xc_right < length else x
        clamped[k] = np.interp(xe, xs, v_abs)
    zones = []
    for name, lo, hi in (
        ("left", 0.0, length / 4),
        ("middle", length / 4, 3 * length / 4),
        ("right", 3 * length / 4, length),
    ):
        mask = (xs >= lo - 1e-9) & (xs <= hi + 1e-9)
        vu = float(clamped[mask].max())
        res = design_shear(vu, inp.b_mm, d_mm, inp.fcu, inp.fyst, inp.stirrup_dia_mm)
        zones.append({"zone": name, "from_m": lo, "to_m": hi, "Vu_kN": vu, **res})
    return zones


def design_continuous_beam(spec: dict[str, Any]) -> dict[str, Any]:
    inp = BeamInput.from_dict(spec)
    n = len(inp.spans_m)
    an = analyze_continuous_beam(inp)
    bf, tf = inp.flange_width_mm, inp.flange_thickness_mm
    fd, fl = P.load_factor_dead, P.load_factor_live
    sw = an["self_weight_kN_m"]

    span_results, failures = [], []
    d_by_span = []
    for k in range(n):
        env = an["spans"][k]
        mu_pos = float(max(env["M_max"].max(), 0.0))
        x_pos = float(env["x_m"][int(np.argmax(env["M_max"]))])
        sag = _design_tension_steel(mu_pos, inp, bf, tf, f"mid-span {k + 1}")
        sag["at_x_m"] = x_pos
        d_here = [r["d_mm"] for r in (sag,) if r.get("d_mm")] or [
            inp.h_mm - inp.cover_mm - inp.stirrup_dia_mm - 10.0
        ]
        span_results.append({"index": k + 1, "length_m": inp.spans_m[k], "sagging": sag})
        d_by_span.append(d_here)
        if sag["status"] != "OK":
            failures.append(f"span {k + 1} sagging: {sag.get('reason')}")

    supports = []
    for k in range(n + 1):
        if k == 0:
            m_an = float(an["spans"][0]["M_min"][0])
            span_for_fixity = 0
        elif k == n:
            m_an = float(an["spans"][-1]["M_min"][-1])
            span_for_fixity = n - 1
        else:
            m_an = float(an["spans"][k - 1]["M_min"][-1])
            span_for_fixity = None
        mu_h = max(-m_an, 0.0)
        basis = "analysis"
        if span_for_fixity is not None and inp.end_fixity:
            sp = span_for_fixity
            wu = fd * (inp.dead_kN_m[sp] + sw) + fl * inp.live_kN_m[sp]
            fixity = wu * inp.spans_m[sp] ** 2 / 24.0
            if fixity > mu_h:
                mu_h, basis = fixity, "ASSUMED end fixity wu*L^2/24 (monolithic with the support)"
        hog = _design_tension_steel(mu_h, inp, None, None, f"support {k}")
        hog["basis"] = basis
        supports.append({"index": k, "hogging": hog})
        if hog["status"] != "OK":
            failures.append(f"support {k} hogging: {hog.get('reason')}")

    for k in range(n):
        ds = [
            supports[k]["hogging"].get("d_mm"),
            supports[k + 1]["hogging"].get("d_mm"),
            *d_by_span[k],
        ]
        d_shear = (
            min(x for x in ds if x)
            if any(ds)
            else inp.h_mm - inp.cover_mm - inp.stirrup_dia_mm - 10.0
        )
        zones = _shear_zones(inp, k, an["spans"][k], d_shear)
        span_results[k]["shear"] = {"d_mm": d_shear, "zones": zones}
        for z in zones:
            if z["status"] != "OK":
                failures.append(f"span {k + 1} shear {z['zone']}: {z.get('reason')}")

    return {
        "type": "continuous_beam",
        "banner": STATUS_BANNER,
        "name": inp.name,
        "status": "OK" if not failures else "FAIL",
        "failures": failures,
        "input": {
            "spans_m": inp.spans_m,
            "b_mm": inp.b_mm,
            "h_mm": inp.h_mm,
            "fcu_MPa": inp.fcu,
            "fy_MPa": inp.fy,
            "fyst_MPa": inp.fyst,
            "dead_kN_m": inp.dead_kN_m,
            "live_kN_m": inp.live_kN_m,
            "self_weight_kN_m": sw,
            "flange": None if bf is None else {"bf_mm": bf, "tf_mm": tf},
        },
        "spans": span_results,
        "supports": supports,
        "reactions": {
            "dead_kN": an["reaction_dead_kN"],
            "live_max_kN": an["reaction_live_max_kN"],
            "ultimate_max_kN": an["reaction_ultimate_max_kN"],
        },
        "envelope": {
            "x_m": [[float(v) for v in s["x_m"]] for s in an["spans"]],
            "M_max_kNm": [[float(v) for v in s["M_max"]] for s in an["spans"]],
            "M_min_kNm": [[float(v) for v in s["M_min"]] for s in an["spans"]],
            "V_max_kN": [[float(v) for v in s["V_max"]] for s in an["spans"]],
            "V_min_kN": [[float(v) for v in s["V_min"]] for s in an["spans"]],
        },
        "assumptions": [
            "Rigid simple supports under the beam; no column/beam frame interaction.",
            "Gross rectangular section for stiffness (T flange ignored in analysis).",
            "Moments taken at support centre-lines (no reduction to the face of support).",
            f"Shear designed at d + half support width from the support centre-line.",
            "End hogging steel uses wu*L^2/24 when the analysis gives less (monolithic frame action).",
            "Stirrup zones: quarter / half / quarter of each span.",
            "NOT CHECKED: deflection, crack width, development/lap lengths, torsion, curtailment.",
        ],
        "unverified_parameters": len(P.unverified()),
    }
