"""One-way continuous RC slab, designed as a 1 m strip over rigid line supports (beams/walls).

Loads are given per m2 and become kN/m on the 1 m strip. Reinforcement is returned as bar
diameter @ spacing; distribution (secondary) steel is the minimum ratio. Deflection and cracking
are NOT checked.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .beam_design import BeamInput, analyze_continuous_beam
from .params import P, STATUS_BANNER
from .sections import design_flexure, flexural_capacity

SLAB_BAR_DIAMETERS = (8, 10, 12, 14, 16)
MIN_PRACTICAL_SPACING_MM = 100.0


def _slab_steel(
    Mu: float, h: float, cover: float, fcu: float, fy: float, label: str
) -> dict[str, Any]:
    out: dict[str, Any] = {"location": label, "Mu_kNm": Mu}
    a_min = P.slab_min_steel_ratio * 1000.0 * h
    reason = "NO_BAR_ARRANGEMENT"
    for dia in SLAB_BAR_DIAMETERS:
        d = h - cover - dia / 2.0
        req = (
            design_flexure(Mu, 1000.0, h, d, fcu, fy)
            if Mu > 1e-9
            else {"status": "OK", "As_mm2": 0.0, "doubly": False}
        )
        if req["status"] != "OK" or req.get("doubly"):
            reason = "SLAB_TOO_THIN_FOR_MOMENT"
            break
        as_req = max(req["As_mm2"], a_min)
        area = math.pi * dia**2 / 4.0
        spacing = min(math.floor(1000.0 * area / as_req / 25.0) * 25.0, P.slab_max_bar_spacing_mm)
        if spacing < MIN_PRACTICAL_SPACING_MM:
            continue
        as_prov = 1000.0 * area / spacing
        cap = flexural_capacity(as_prov, d, 1000.0, h, fcu, fy)["capacity_kNm"]
        if cap + 1e-6 < Mu:
            continue
        return {
            **out,
            "status": "OK",
            "bars": f"Φ{dia}@{int(spacing)}",
            "dia_mm": dia,
            "spacing_mm": spacing,
            "As_req_mm2_per_m": as_req,
            "As_prov_mm2_per_m": as_prov,
            "d_mm": d,
            "capacity_kNm": cap,
            "utilisation": Mu / cap if cap > 0 else 0.0,
        }
    return {**out, "status": "FAIL", "reason": reason}


def design_slab_strip(spec: dict[str, Any]) -> dict[str, Any]:
    h = float(spec["thickness_mm"])
    if h <= 0:
        raise ValueError("thickness_mm must be positive")
    fcu, fy = float(spec.get("fcu_MPa", 30.0)), float(spec.get("fy_MPa", 400.0))
    cover = float(spec.get("cover_mm", 20.0))
    inp = BeamInput.from_dict(
        {
            "name": spec.get("name", "slab"),
            "spans_m": spec["spans_m"],
            "b_mm": 1000.0,
            "h_mm": h,
            "fcu_MPa": fcu,
            "fy_MPa": fy,
            "cover_mm": cover,
            "stirrup_dia_mm": 0.0,
            "dead_kN_m": spec.get("dead_kN_m2", 0.0),
            "live_kN_m": spec.get("live_kN_m2", 0.0),
            "self_weight": spec.get("self_weight", True),
            "support_width_mm": spec.get("support_width_mm", 250.0),
            "end_fixity": spec.get("end_fixity", True),
        }
    )
    n = len(inp.spans_m)
    an = analyze_continuous_beam(inp)
    fd, fl = P.load_factor_dead, P.load_factor_live
    sw = an["self_weight_kN_m"]
    failures: list[str] = []

    spans = []
    for k in range(n):
        env = an["spans"][k]
        mu = float(max(env["M_max"].max(), 0.0))
        steel = _slab_steel(mu, h, cover, fcu, fy, f"mid-span {k + 1}")
        spans.append({"index": k + 1, "length_m": inp.spans_m[k], "sagging": steel})
        if steel["status"] != "OK":
            failures.append(f"span {k + 1} sagging: {steel['reason']}")

    supports = []
    for k in range(n + 1):
        if k == 0:
            m_an, sp = float(an["spans"][0]["M_min"][0]), 0
        elif k == n:
            m_an, sp = float(an["spans"][-1]["M_min"][-1]), n - 1
        else:
            m_an, sp = float(an["spans"][k - 1]["M_min"][-1]), None
        mu = max(-m_an, 0.0)
        basis = "analysis"
        if sp is not None and inp.end_fixity:
            wu = fd * (inp.dead_kN_m[sp] + sw) + fl * inp.live_kN_m[sp]
            fix = wu * inp.spans_m[sp] ** 2 / 24.0
            if fix > mu:
                mu, basis = fix, "ASSUMED end fixity wu*L^2/24"
        steel = _slab_steel(mu, h, cover, fcu, fy, f"support {k}")
        steel["basis"] = basis
        supports.append({"index": k, "hogging": steel})
        if steel["status"] != "OK":
            failures.append(f"support {k} hogging: {steel['reason']}")

    # shear (no stirrups in slabs): concrete only, at d + half support width from the centre-line
    d_shear = h - cover - 6.0
    root = math.sqrt(fcu / P.gamma_c)
    qcu = P.slab_qcu_factor * root
    shear = []
    for k in range(n):
        env, length = an["spans"][k], inp.spans_m[k]
        v_abs = np.maximum(np.abs(env["V_max"]), np.abs(env["V_min"]))
        xl = inp.support_width_mm[k] / 2000.0 + d_shear / 1000.0
        xr = length - inp.support_width_mm[k + 1] / 2000.0 - d_shear / 1000.0
        vu = float(max(np.interp(xl, env["x_m"], v_abs), np.interp(xr, env["x_m"], v_abs)))
        qu = vu * 1000.0 / (1000.0 * d_shear)
        ok = qu <= qcu
        shear.append(
            {
                "span": k + 1,
                "Vu_kN_per_m": vu,
                "qu_MPa": qu,
                "qcu_MPa": qcu,
                "status": "OK" if ok else "FAIL",
            }
        )
        if not ok:
            failures.append(
                f"span {k + 1} shear: INCREASE_THICKNESS (qu {qu:.2f} > qcu {qcu:.2f} MPa)"
            )

    a_dist = P.slab_min_steel_ratio * 1000.0 * h
    dia_d = 8
    area_d = math.pi * dia_d**2 / 4.0
    s_d = min(math.floor(1000.0 * area_d / a_dist / 25.0) * 25.0, P.slab_max_bar_spacing_mm)
    return {
        "type": "slab_strip",
        "banner": STATUS_BANNER,
        "name": inp.name,
        "status": "OK" if not failures else "FAIL",
        "failures": failures,
        "input": {
            "spans_m": inp.spans_m,
            "thickness_mm": h,
            "fcu_MPa": fcu,
            "fy_MPa": fy,
            "dead_kN_m2": inp.dead_kN_m,
            "live_kN_m2": inp.live_kN_m,
            "self_weight_kN_m2": sw,
        },
        "spans": spans,
        "supports": supports,
        "shear": shear,
        "distribution_steel": {"bars": f"Φ{dia_d}@{int(s_d)}", "As_mm2_per_m": a_dist},
        "reactions_ultimate_max_kN_per_m": an["reaction_ultimate_max_kN"],
        "assumptions": [
            "One-way strip on rigid line supports; two-way action ignored.",
            "End supports: top steel for wu*L^2/24 when analysis gives less.",
            "NOT CHECKED: deflection, crack width, development lengths, curtailment, openings.",
        ],
        "unverified_parameters": len(P.unverified()),
    }
