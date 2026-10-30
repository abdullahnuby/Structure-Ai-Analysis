"""Reinforced-concrete section mechanics: flexure, shear and bar selection.

Units in this module: mm, N, MPa, N*mm; moments in/out of the public functions are kN*m and
forces kN. Flexural capacity is found from strain compatibility and equilibrium (not from a
closed-form shortcut), so any stress-block parameter changed in ``params`` is honoured and the
design result is always re-verified against the capacity function.
"""

from __future__ import annotations

import math
from typing import Any

from .params import P

KNM_TO_NMM = 1.0e6


def fcd(fcu: float) -> float:
    return P.concrete_stress_factor * fcu / P.gamma_c


def fyd(fy: float) -> float:
    return fy / P.gamma_s


def steel_stress(eps: float, fy: float) -> float:
    """Elastic - perfectly plastic steel, strain and stress positive in the same sense."""
    lim = fyd(fy)
    return max(-lim, min(lim, eps * P.Es_MPa))


def Ec_MPa(fcu: float) -> float:
    return P.Ec_factor * math.sqrt(fcu)


def _compression_zone(a: float, bw: float, bf: float | None, tf: float | None):
    """Area and centroid depth (from the compression face) of the stress block of depth a."""
    a = max(a, 0.0)
    if a == 0.0:
        return 0.0, 0.0
    if bf is None or tf is None or bf <= bw:
        return bw * a, a / 2.0
    t = min(a, tf)
    a1 = bf * t
    m1 = a1 * t / 2.0
    a2 = bw * max(a - tf, 0.0)
    m2 = a2 * (tf + max(a - tf, 0.0) / 2.0)
    return a1 + a2, (m1 + m2) / (a1 + a2)


def flexural_capacity(
    As: float,
    d: float,
    bw: float,
    h: float,
    fcu: float,
    fy: float,
    As_c: float = 0.0,
    d_c: float = 0.0,
    bf: float | None = None,
    tf: float | None = None,
) -> dict[str, Any]:
    """Moment capacity (kN*m) of a section with tension steel As at depth d and compression
    steel As_c at depth d_c, by strain compatibility. ``bf``/``tf``: flange of a T section whose
    flange is in compression."""
    if As <= 0 or d <= 0 or bw <= 0:
        return {"capacity_kNm": 0.0, "c_mm": 0.0, "c_over_d": 0.0}
    beta, ecu = P.stress_block_ratio, P.eps_cu
    f_cd = fcd(fcu)

    def parts(c: float):
        a = min(beta * c, h)
        area, yc = _compression_zone(a, bw, bf, tf)
        cc = f_cd * area
        t_force = As * steel_stress(ecu * (d - c) / c, fy)
        cs = As_c * steel_stress(ecu * (c - d_c) / c, fy) if As_c > 0 else 0.0
        return cc, yc, cs, t_force

    lo, hi = 1e-6, 10.0 * h
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        cc, _, cs, t_force = parts(mid)
        if cc + cs - t_force > 0:
            hi = mid
        else:
            lo = mid
    c = 0.5 * (lo + hi)
    cc, yc, cs, _ = parts(c)
    moment = cc * (d - yc) + cs * (d - d_c)
    return {"capacity_kNm": moment / KNM_TO_NMM, "c_mm": c, "c_over_d": c / d}


def minimum_flexural_steel(bw: float, d: float, fcu: float, fy: float) -> float:
    return max(
        P.beam_min_steel_a * math.sqrt(fcu) / fy * bw * d,
        P.beam_min_steel_b / fy * bw * d,
    )


def design_flexure(
    Mu_kNm: float,
    bw: float,
    h: float,
    d: float,
    fcu: float,
    fy: float,
    d_c: float = 0.0,
    bf: float | None = None,
    tf: float | None = None,
) -> dict[str, Any]:
    """Required tension (and, if the ductility limit c/d is exceeded, compression) steel for Mu."""
    mu = abs(Mu_kNm) * KNM_TO_NMM
    if mu == 0.0:
        return {"status": "OK", "As_mm2": 0.0, "As_c_mm2": 0.0, "doubly": False, "c_over_d": 0.0}
    beta, ecu, f_cd = P.stress_block_ratio, P.eps_cu, fcd(fcu)
    cmax = P.c_over_d_max * d
    area, yc = _compression_zone(min(beta * cmax, h), bw, bf, tf)
    cc_max = f_cd * area
    sig_t = steel_stress(ecu * (d - cmax) / cmax, fy)
    m1 = cc_max * (d - yc)
    out: dict[str, Any] = {"doubly": False}
    if mu <= m1:
        lo, hi = 0.0, cc_max / sig_t
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            cap = flexural_capacity(mid, d, bw, h, fcu, fy, bf=bf, tf=tf)["capacity_kNm"]
            if cap * KNM_TO_NMM < mu:
                lo = mid
            else:
                hi = mid
        as_t, as_c = hi, 0.0
    else:
        if d_c <= 0 or d_c >= cmax:
            return {"status": "FAIL", "reason": "COMPRESSION_STEEL_NOT_EFFECTIVE", "As_mm2": None}
        sig_sc = steel_stress(ecu * (cmax - d_c) / cmax, fy)
        if sig_sc <= 0 or d - d_c <= 0:
            return {"status": "FAIL", "reason": "COMPRESSION_STEEL_NOT_EFFECTIVE", "As_mm2": None}
        m2 = mu - m1
        as_c = m2 / ((d - d_c) * sig_sc)
        as_t = cc_max / sig_t + as_c * sig_sc / sig_t
        out["doubly"] = True
    check = flexural_capacity(as_t, d, bw, h, fcu, fy, as_c, d_c, bf, tf)
    ok = check["capacity_kNm"] * KNM_TO_NMM >= mu * (1 - 1e-6)
    out.update(
        status="OK" if ok else "FAIL",
        As_mm2=as_t,
        As_c_mm2=as_c,
        c_over_d=check["c_over_d"],
        capacity_check_kNm=check["capacity_kNm"],
    )
    if not ok:
        out["reason"] = "CAPACITY_CHECK_FAILED"
    return out


def apply_minimum_steel(As_req: float, bw: float, d: float, fcu: float, fy: float) -> float:
    """Required steel raised to the minimum, which need not exceed a multiple of the requirement."""
    a_min = minimum_flexural_steel(bw, d, fcu, fy)
    return max(As_req, min(a_min, P.min_steel_cap_factor * As_req)) if As_req > 0 else 0.0


def design_shear(
    Vu_kN: float, bw: float, d: float, fcu: float, fyst: float, stirrup_dia: float, legs: int = 2
) -> dict[str, Any]:
    qu = abs(Vu_kN) * 1000.0 / (bw * d)
    root = math.sqrt(fcu / P.gamma_c)
    qcu, qumax = P.shear_qcu_factor * root, P.shear_qu_max_factor * root
    out = {"qu_MPa": qu, "qcu_MPa": qcu, "qu_max_MPa": qumax, "stirrup_dia_mm": stirrup_dia}
    if qu > qumax:
        return {**out, "status": "FAIL", "reason": "SECTION_TOO_SMALL_FOR_SHEAR"}
    av = legs * math.pi * stirrup_dia**2 / 4.0
    min_per_mm = P.stirrup_min_ratio * bw / fyst
    if qu <= qcu:
        per_mm, basis = min_per_mm, "minimum"
    else:
        qsu = qu - P.stirrup_qcu_share * qcu
        per_mm, basis = max(qsu * bw / (fyst / P.gamma_s), min_per_mm), "calculated"
    s = min(av / per_mm, P.stirrup_max_spacing_mm, 0.75 * d)
    s = math.floor(s / 5.0) * 5.0
    if s < P.stirrup_min_spacing_mm:
        return {**out, "status": "FAIL", "reason": "STIRRUPS_TOO_CLOSE_USE_LARGER_BAR_OR_SECTION"}
    return {**out, "status": "OK", "spacing_mm": s, "legs": legs, "basis": basis}


def select_bars(
    As_req: float,
    width: float,
    cover: float,
    stirrup_dia: float,
    layers: int = 1,
    min_bars: int = 2,
) -> dict[str, Any] | None:
    """Smallest-area bar group meeting As_req within ``layers`` layers of the given width."""
    avail = width - 2.0 * (cover + stirrup_dia)
    best = None
    for dia in P.bar_diameters_mm:
        area = math.pi * dia**2 / 4.0
        n = max(min_bars, math.ceil(As_req / area - 1e-9))
        per_layer = math.ceil(n / layers)
        gap = max(dia, P.min_clear_spacing_mm)
        if per_layer * dia + (per_layer - 1) * gap > avail:
            continue
        cand = {
            "n": n,
            "dia": dia,
            "layers": layers,
            "As_prov_mm2": n * area,
            "label": f"{n}Φ{dia}" + (f" ({layers} layers)" if layers > 1 else ""),
        }
        if best is None or (cand["As_prov_mm2"], n) < (best["As_prov_mm2"], best["n"]):
            best = cand
    return best
