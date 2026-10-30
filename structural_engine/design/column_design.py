"""Rectangular tied RC column: axial + uniaxial/biaxial bending by strain compatibility.

The interaction curve is generated from first principles (strain profile -> stresses -> forces)
for any bar layout; the design routine searches real bar layouts (n x diameter) and returns the
lightest one that passes. Short columns only: a slender column is reported as
``SLENDER_NOT_DESIGNED`` instead of being given a number that ignores second-order effects.

Units: mm, N, MPa; demands in kN and kN*m. Bending "about x" acts in the plane of the depth h,
bending "about y" in the plane of the width b.
"""

from __future__ import annotations

import math
from typing import Any

from .params import P, STATUS_BANNER
from .sections import fcd, fyd, steel_stress


def bar_layers(b: float, h: float, nx: int, ny: int, dia: float, cover_to_centre: float, axis: str):
    """[(distance from the compression face, steel area)] for a perimeter layout.

    nx = bars on each b-face (corners included), ny = bars on each h-face (corners included).
    axis 'x': depth = h, rows of nx bars at top/bottom, ny-2 interior layers of 2 bars.
    axis 'y': depth = b, rows of ny bars at top/bottom, nx-2 interior layers of 2 bars.
    """
    area = math.pi * dia**2 / 4.0
    depth, rows, inner = (h, nx, ny) if axis == "x" else (b, ny, nx)
    layers = [(cover_to_centre, rows * area), (depth - cover_to_centre, rows * area)]
    for k in range(1, inner - 1):
        y = cover_to_centre + k * (depth - 2 * cover_to_centre) / (inner - 1)
        layers.append((y, 2 * area))
    return layers


def _forces(c: float, depth: float, width: float, layers, fcu: float, fy: float):
    """(axial force N, moment N*mm about the section centroid), compression positive."""
    a = min(P.stress_block_ratio * c, depth)
    cc = fcd(fcu) * width * a
    n = cc
    m = cc * (depth / 2.0 - a / 2.0)
    for y, area in layers:
        sig = steel_stress(P.eps_cu * (c - y) / c, fy)
        n += sig * area
        m += sig * area * (depth / 2.0 - y)
    return n, m


def pure_compression_capacity(
    width: float, depth: float, ast: float, fcu: float, fy: float
) -> float:
    return fcd(fcu) * (width * depth - ast) + fyd(fy) * ast


def moment_capacity_at_axial(
    Pu_N: float, depth: float, width: float, layers, fcu: float, fy: float
) -> float | None:
    """Moment capacity (N*mm) at axial load Pu_N; None when Pu_N is beyond the section."""
    lo, hi = 1e-3 * depth, 100.0 * depth
    if (
        Pu_N > _forces(hi, depth, width, layers, fcu, fy)[0]
        or Pu_N < _forces(lo, depth, width, layers, fcu, fy)[0]
    ):
        return None
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if _forces(mid, depth, width, layers, fcu, fy)[0] < Pu_N:
            lo = mid
        else:
            hi = mid
    return max(_forces(0.5 * (lo + hi), depth, width, layers, fcu, fy)[1], 0.0)


def interaction_curve(b, h, nx, ny, dia, cover_to_centre, fcu, fy, axis="x", points=60):
    """[(P kN, M kN*m)] from pure compression down to pure tension."""
    depth, width = (h, b) if axis == "x" else (b, h)
    layers = bar_layers(b, h, nx, ny, dia, cover_to_centre, axis)
    out = []
    for k in range(points + 1):
        c = depth * (0.01 + 99.99 * (1 - k / points) ** 3)  # dense near the balanced region
        n, m = _forces(c, depth, width, layers, fcu, fy)
        out.append((n / 1000.0, m / 1e6))
    return out


def _min_eccentricity_mm(dimension: float) -> float:
    return max(P.column_min_ecc_ratio * dimension, P.column_min_ecc_mm)


def check_column(spec: dict[str, Any], nx: int, ny: int, dia: float) -> dict[str, Any]:
    """Check one bar layout against the demands in ``spec``."""
    b, h = float(spec["b_mm"]), float(spec["h_mm"])
    fcu, fy = float(spec.get("fcu_MPa", 30.0)), float(spec.get("fy_MPa", 400.0))
    cover = float(spec.get("cover_mm", 30.0))
    tie = float(spec.get("tie_dia_mm", 8.0))
    cc = cover + tie + dia / 2.0
    pu = float(spec["Pu_kN"]) * 1000.0
    ast = (2 * nx + 2 * (ny - 2)) * math.pi * dia**2 / 4.0
    p0 = pure_compression_capacity(b, h, ast, fcu, fy)
    p_cap = P.column_axial_cap_ratio * p0
    res: dict[str, Any] = {
        "nx": nx,
        "ny": ny,
        "dia_mm": dia,
        "Ast_mm2": ast,
        "rho": ast / (b * h),
        "P_cap_kN": p_cap / 1000.0,
    }
    if pu > p_cap:
        return {
            **res,
            "status": "FAIL",
            "reason": "AXIAL_LOAD_EXCEEDS_CAPACITY",
            "ratio": pu / p_cap,
        }
    demands, ratios = {}, []
    for axis, depth, width, m_key in (("x", h, b, "Mux_kNm"), ("y", b, h, "Muy_kNm")):
        m_user = abs(float(spec.get(m_key, 0.0))) * 1e6
        m_min = pu * _min_eccentricity_mm(depth) / 1.0
        m_des = max(m_user, m_min)
        layers = bar_layers(b, h, nx, ny, dia, cc, axis)
        m_cap = moment_capacity_at_axial(pu, depth, width, layers, fcu, fy)
        if m_cap is None:
            return {**res, "status": "FAIL", "reason": "NO_MOMENT_CAPACITY_AT_THIS_AXIAL_LOAD"}
        demands[axis] = {
            "M_design_kNm": m_des / 1e6,
            "M_cap_kNm": m_cap / 1e6,
            "min_ecc_governs": m_min > m_user,
            "e_min_mm": _min_eccentricity_mm(depth),
        }
        ratios.append((m_des / m_cap) if m_cap > 0 else math.inf)
    alpha = P.column_biaxial_alpha
    biaxial = sum(r**alpha for r in ratios) if len(ratios) == 2 else ratios[0]
    # Min eccentricity acts in ONE direction at a time (not both simultaneously)
    if float(spec.get("Mux_kNm", 0.0)) == 0.0 and float(spec.get("Muy_kNm", 0.0)) == 0.0:
        biaxial = max(ratios)
    res.update(axes=demands, ratio=biaxial, status="OK" if biaxial <= 1.0 + 1e-9 else "FAIL")
    if res["status"] == "FAIL":
        res["reason"] = "INTERACTION_RATIO_EXCEEDS_1"
    return res


def _ties(dia_max: float, dia_min: float, b: float, h: float) -> dict[str, Any]:
    d = max(P.column_tie_min_dia_mm, math.ceil(P.column_tie_dia_bar_ratio * dia_max / 2.0) * 2.0)
    s = min(P.column_tie_max_spacing_mm, P.column_tie_spacing_bar_multiple * dia_min, min(b, h))
    return {"tie_dia_mm": d, "tie_spacing_mm": math.floor(s / 5.0) * 5.0}


def _loads_from_floors(spec: dict[str, Any]) -> float | None:
    """Ultimate axial load (kN) from a list of tributary floor loads, else None."""
    floors = spec.get("floors")
    if not floors:
        return None
    fd, fl = P.load_factor_dead, P.load_factor_live
    total = 0.0
    sw_per_m = P.unit_weight_concrete_kN_m3 * float(spec["b_mm"]) * float(spec["h_mm"]) / 1e6
    height = float(spec.get("storey_height_m", 3.0))
    for fl_ in floors:
        count = int(fl_.get("count", 1))
        area = float(fl_["tributary_area_m2"])
        total += count * (
            fd * (float(fl_.get("dead_kN_m2", 0.0)) * area + sw_per_m * height)
            + fl * float(fl_.get("live_kN_m2", 0.0)) * area
        )
    return total


def design_column(spec: dict[str, Any]) -> dict[str, Any]:
    spec = dict(spec)
    for key in ("b_mm", "h_mm"):
        if float(spec.get(key, 0)) <= 0:
            raise ValueError(f"{key} must be positive")
    if "Pu_kN" not in spec:
        derived = _loads_from_floors(spec)
        if derived is None:
            raise ValueError("give Pu_kN, or floors[] to derive it")
        spec["Pu_kN"] = derived
        spec["Pu_source"] = "derived from floors[] (no live-load reduction, no continuity factor)"
    if float(spec["Pu_kN"]) < 0:
        raise ValueError("Pu_kN is compression positive; tension columns are not designed")
    b, h = float(spec["b_mm"]), float(spec["h_mm"])
    out: dict[str, Any] = {
        "type": "column",
        "banner": STATUS_BANNER,
        "name": spec.get("name", "column"),
        "input": {
            k: spec.get(k)
            for k in (
                "b_mm",
                "h_mm",
                "fcu_MPa",
                "fy_MPa",
                "Pu_kN",
                "Mux_kNm",
                "Muy_kNm",
                "Pu_source",
            )
        },
        "unverified_parameters": len(P.unverified()),
    }
    # slenderness: lambda = k * L / (dimension in the bending plane), ECP-style (not k*L/r)
    k_eff, length = float(spec.get("k", 1.0)), spec.get("unsupported_length_m")
    braced = bool(spec.get("braced", True))
    limit = P.column_slenderness_limit_braced if braced else P.column_slenderness_limit_unbraced
    if length is not None:
        lam = {ax: k_eff * float(length) * 1000.0 / dim for ax, dim in (("x", h), ("y", b))}
        out["slenderness"] = {
            "lambda_x": lam["x"],
            "lambda_y": lam["y"],
            "limit": limit,
            "braced": braced,
            "k": k_eff,
        }
        if max(lam.values()) > limit:
            return {
                **out,
                "status": "SLENDER_NOT_DESIGNED",
                "failures": [
                    "Slenderness exceeds the short-column limit; second-order (moment magnification) "
                    "design is not implemented. Enlarge the section or design it by another method."
                ],
            }
    else:
        out["slenderness"] = None
        out["warnings"] = ["unsupported_length_m not given: slenderness NOT checked."]

    def layout_ok(nx, ny, dia):
        cc = float(spec.get("cover_mm", 30.0)) + float(spec.get("tie_dia_mm", 8.0)) + dia / 2.0
        gap = max(dia, P.min_clear_spacing_mm)
        fits_b = nx * dia + (nx - 1) * gap <= b - 2 * (cc - dia / 2.0)
        fits_h = ny * dia + (ny - 1) * gap <= h - 2 * (cc - dia / 2.0)
        return fits_b and fits_h

    if "bars" in spec:  # check-only mode
        bars = spec["bars"]
        chk = check_column(spec, int(bars["nx"]), int(bars["ny"]), float(bars["dia_mm"]))
        status = chk["status"]
        return {
            **out,
            "mode": "check",
            "status": status,
            "result": chk,
            "failures": [] if status == "OK" else [chk.get("reason")],
        }

    candidates = []
    for dia in P.bar_diameters_mm:
        if dia < 16:
            continue
        for nx in range(2, 13):
            for ny in range(2, 13):
                ast = (2 * nx + 2 * (ny - 2)) * math.pi * dia**2 / 4.0
                rho = ast / (b * h)
                if not (P.column_min_steel_ratio <= rho <= P.column_max_steel_ratio):
                    continue
                if layout_ok(nx, ny, dia):
                    candidates.append((ast, 2 * nx + 2 * (ny - 2), dia, nx, ny))
    candidates.sort()
    last = None
    for ast, count, dia, nx, ny in candidates:
        chk = check_column(spec, nx, ny, float(dia))
        last = chk
        if chk["status"] == "OK":
            out.update(
                mode="design",
                status="OK",
                failures=[],
                result={**chk, "bars": f"{count}Φ{dia}", **_ties(dia, dia, b, h)},
            )
            return out
    reason = (last or {}).get("reason", "NO_LAYOUT_FITS_THE_SECTION")
    return {
        **out,
        "mode": "design",
        "status": "FAIL",
        "failures": [
            f"No bar layout within {P.column_min_steel_ratio:.1%}-{P.column_max_steel_ratio:.1%} passes "
            f"({reason}); enlarge the section or raise fcu."
        ],
        "result": last,
    }
