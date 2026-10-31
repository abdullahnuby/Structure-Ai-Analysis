"""Flat plate and flat slab (drop panels) floors: no beams, slab on columns.

Method (all coefficients are recalled from the direct design method and are UNVERIFIED, see params.py):
  * total static moment per panel and direction  M0 = wu * L2 * Ln^2 / 8,
  * split into negative/positive moments by end condition, then into column / middle strips,
  * punching shear at every column with a moment-transfer factor, plus a second check at the drop edge,
  * unbalanced moments transferred to the columns, columns designed with the column engine.
Deflection is NOT calculated; a span/thickness rule is applied instead. NOT FOR CONSTRUCTION.
"""

from __future__ import annotations

import math
from typing import Any

from .column_design import design_column
from .params import P, STATUS_BANNER
from .slab_design import _slab_steel
from .system import _cluster, _nearest, _round_up

FLAT_SYSTEMS = ("flat_plate", "flat_slab")

ASSUMPTIONS = [
    "Layout: a slab panel is every grid cell with a column at all four corners; there are no beams and no edge beams.",
    "Moments by the direct design method (coefficients recalled, unverified); the method's limits (>= 3 spans, regular grid, live <= 2x dead) are NOT checked.",
    "Strips: column strip = 0.25 * min(L1, L2) each side of a column line; middle strip = the rest. Larger of the two moments at a shared support governs.",
    "Punching: critical section at d/2 from the column face, moment-transfer factor by position (interior/edge/corner); no shear reinforcement is designed - a failing column must be enlarged, or the slab thickened or dropped.",
    "Unbalanced moments transferred to columns: exterior = exterior negative moment, interior = 0.07*(...) formula; half goes to the column below.",
    "Column loads are tributary areas (a quarter of every adjacent panel); no continuity increase for first interior columns.",
    "Walls are smeared over the nearest panel (no beams to carry them): verify edge strips and wall panels separately.",
    "Slab thickness for the deflection rule uses the longest centre-to-centre span; deflection itself is NOT computed.",
    "NOT CHECKED: lateral loads (wind/seismic) and the frame action they need, slab shear at d, deflection, crack width, development/lap lengths, curtailment, openings, foundations.",
]


# ------------------------------------------------------------------------------------------------
# layout
# ------------------------------------------------------------------------------------------------
def propose_flat_layout(columns: list[dict[str, Any]]) -> dict[str, Any]:
    if len(columns) < 4:
        raise ValueError("a flat floor needs at least four columns (one panel)")
    ids = [str(c["id"]) for c in columns]
    if len(set(ids)) != len(ids):
        raise ValueError("column ids must be unique")
    tol = P.grid_snap_tolerance_m
    gx = _cluster([float(c["x"]) for c in columns], tol)
    gy = _cluster([float(c["y"]) for c in columns], tol)
    at: dict[tuple[int, int], dict[str, Any]] = {}
    for c in columns:
        key = (_nearest(gx, float(c["x"])), _nearest(gy, float(c["y"])))
        if key in at:
            raise ValueError(f"two columns snap to the same grid point {key}; check the plan")
        at[key] = {
            "id": str(c["id"]),
            "ix": key[0],
            "iy": key[1],
            "x": gx[key[0]],
            "y": gy[key[1]],
            "b_mm": float(c["b_mm"]),
            "h_mm": float(c["h_mm"]),
        }
    warnings: list[str] = []
    panels: dict[tuple[int, int], dict[str, Any]] = {}
    for i in range(len(gx) - 1):
        for j in range(len(gy) - 1):
            corners = [(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)]
            have = sum(1 for k in corners if k in at)
            if have == 4:
                panels[(i, j)] = {
                    "id": f"P{len(panels) + 1}",
                    "i": i,
                    "j": j,
                    "x0": gx[i],
                    "x1": gx[i + 1],
                    "y0": gy[j],
                    "y1": gy[j + 1],
                }
            elif have >= 2:
                warnings.append(
                    f"cell x {gx[i]:.2f}-{gx[i + 1]:.2f}, y {gy[j]:.2f}-{gy[j + 1]:.2f} lacks "
                    f"{4 - have} corner column(s); no slab panel created"
                )
    if not panels:
        raise ValueError("no grid cell has columns at all four corners")
    for (ix, iy), c in at.items():
        left = (ix - 1, iy) in panels or (ix - 1, iy - 1) in panels
        right = (ix, iy) in panels or (ix, iy - 1) in panels
        down = (ix, iy - 1) in panels or (ix - 1, iy - 1) in panels
        up = (ix, iy) in panels or (ix - 1, iy) in panels
        c["has_x"], c["has_y"] = (left, right), (down, up)
        n_adj = sum(
            1 for k in ((ix - 1, iy - 1), (ix, iy - 1), (ix - 1, iy), (ix, iy)) if k in panels
        )
        c["n_panels"] = n_adj
        if n_adj == 0:
            c["position"] = "none"
        else:
            ext_x, ext_y = left != right, down != up
            c["position"] = (
                "corner" if ext_x and ext_y else "edge" if (ext_x or ext_y) else "interior"
            )
            c["free_edge"] = (
                "x"
                if ext_x and not ext_y
                else "y" if ext_y and not ext_x else "both" if ext_x else None
            )
    return {
        "grid_x_m": gx,
        "grid_y_m": gy,
        "columns": list(at.values()),
        "panels": sorted(panels.values(), key=lambda p: p["id"]),
        "panel_at": panels,
        "warnings": warnings,
    }


# ------------------------------------------------------------------------------------------------
# punching
# ------------------------------------------------------------------------------------------------
def punching_check(
    Vu_kN: float,
    b_mm: float,
    h_mm: float,
    d_mm: float,
    position: str,
    free_edge: str | None,
    wu_kN_m2: float,
    fcu: float,
) -> dict[str, Any]:
    """Punching at d/2 from the loaded area (b x h). free_edge: 'x' = slab edge perpendicular to x."""
    d = d_mm
    if position == "interior":
        sx, sy, bo, beta = (
            b_mm + d,
            h_mm + d,
            2 * (b_mm + d) + 2 * (h_mm + d),
            P.punching_beta_interior,
        )
    elif position == "edge":
        if free_edge == "x":
            sx, sy = b_mm + d / 2, h_mm + d
            bo = 2 * sx + sy
        else:
            sx, sy = b_mm + d, h_mm + d / 2
            bo = 2 * sy + sx
        beta = P.punching_beta_edge
    else:
        sx, sy = b_mm + d / 2, h_mm + d / 2
        bo, beta = sx + sy, P.punching_beta_corner
    inside = sx * sy / 1e6 * wu_kN_m2
    vnet = max(Vu_kN - inside, 0.0)
    qu = beta * vnet * 1000.0 / (bo * d)
    ratio_dims = min(b_mm, h_mm) / max(b_mm, h_mm)
    qcup = P.punching_qcup_factor * math.sqrt(fcu / P.gamma_c) * min(1.0, 0.5 + ratio_dims)
    return {
        "position": position,
        "Vu_kN": Vu_kN,
        "Vu_net_kN": vnet,
        "bo_mm": bo,
        "d_mm": d,
        "beta": beta,
        "qu_MPa": qu,
        "qcup_MPa": qcup,
        "ratio": qu / qcup,
        "status": "OK" if qu <= qcup else "FAIL",
    }


# ------------------------------------------------------------------------------------------------
# moments of one panel in one direction
# ------------------------------------------------------------------------------------------------
def panel_direction_moments(
    L1: float, L2: float, colsize_m: float, wu: float, left: bool, right: bool
) -> dict[str, Any]:
    """Moments (kN.m) of a panel spanning L1 with width L2 under factored area load wu (kN/m2)."""
    Ln = max(L1 - colsize_m, 0.65 * L1)
    M0 = wu * L2 * Ln**2 / 8.0
    if left and right:
        case, neg_l, neg_r, pos = "interior", P.ddm_int_neg, P.ddm_int_neg, P.ddm_int_pos
    elif left or right:
        case, pos = "end", P.ddm_ext_pos
        neg_l, neg_r = (
            (P.ddm_ext_int_neg, P.ddm_ext_neg) if left else (P.ddm_ext_neg, P.ddm_ext_int_neg)
        )
    else:
        case, neg_l, neg_r, pos = "single", P.ddm_ext_neg, P.ddm_ext_neg, 1.0 - P.ddm_ext_neg
    cs_w = min(0.5 * min(L1, L2), L2)
    ms_w = L2 - cs_w

    def split(total: float, share: float) -> dict[str, float]:
        return {
            "cs_per_m": share * total / cs_w if cs_w > 0 else 0.0,
            "ms_per_m": (1 - share) * total / ms_w if ms_w > 1e-9 else 0.0,
        }

    def neg_share(is_exterior: bool) -> float:
        return P.ddm_cs_ext_neg if is_exterior else P.ddm_cs_int_neg

    left_ext, right_ext = not left, not right
    return {
        "case": case,
        "L1": L1,
        "L2": L2,
        "Ln": Ln,
        "M0": M0,
        "cs_width_m": cs_w,
        "ms_width_m": ms_w,
        "neg_start": neg_l * M0,
        "neg_end": neg_r * M0,
        "pos": pos * M0,
        "strip_neg_start": split(neg_l * M0, neg_share(left_ext)),
        "strip_neg_end": split(neg_r * M0, neg_share(right_ext)),
        "strip_pos": split(pos * M0, P.ddm_cs_pos),
    }


# ------------------------------------------------------------------------------------------------
# whole floor
# ------------------------------------------------------------------------------------------------
def design_flat_floor(spec: dict[str, Any]) -> dict[str, Any]:
    system = str(spec.get("system", "flat_plate"))
    if system not in FLAT_SYSTEMS:
        raise ValueError(f"unknown system {system!r}")
    cols = spec.get("columns")
    if not isinstance(cols, list):
        raise ValueError("columns must be a list")
    for key in ("finishes_kN_m2", "live_kN_m2", "storey_height_m"):
        if key not in spec:
            raise ValueError(f"missing input: {key}")
    finishes, live, H = (
        float(spec["finishes_kN_m2"]),
        float(spec["live_kN_m2"]),
        float(spec["storey_height_m"]),
    )
    if finishes < 0 or live < 0 or H <= 0:
        raise ValueError("loads must be non-negative and storey_height_m positive")
    floors = int(spec.get("floors", 1))
    if floors < 1:
        raise ValueError("floors must be at least 1")
    fcu, fy = float(spec.get("fcu_MPa", 30.0)), float(spec.get("fy_MPa", 400.0))
    cover = float(spec.get("slab_cover_mm", 20.0))
    gamma = P.unit_weight_concrete_kN_m3
    lay = propose_flat_layout(cols)
    panels, panel_at = lay["panels"], lay["panel_at"]
    warnings = list(spec.get("plan_notes") or []) + list(lay["warnings"])
    failures: list[str] = []

    # thickness
    spans = [max(p["x1"] - p["x0"], p["y1"] - p["y0"]) for p in panels]
    ratio = P.flat_slab_thickness_ratio if system == "flat_slab" else P.flat_plate_thickness_ratio
    suggested = max(P.flat_plate_min_thickness_mm, _round_up(max(spans) * 1000.0 / ratio, 10.0))
    h = float(spec.get("slab_thickness_mm") or suggested)
    if h < max(spans) * 1000.0 / ratio - 1e-6:
        failures.append(
            f"slab thickness {h:.0f} mm is below span/{ratio:g} = {max(spans) * 1000.0 / ratio:.0f} mm (deflection rule; deflection not calculated)"
        )
    drop_t = float(spec.get("drop_thickness_mm", 100.0)) if system == "flat_slab" else 0.0
    if system == "flat_slab" and drop_t <= 0:
        raise ValueError("drop_thickness_mm must be positive for a flat slab")
    d_slab = h - cover - 16.0
    if d_slab <= 50:
        raise ValueError("slab too thin for the cover")

    # walls smeared on the nearest panel
    extra_dead = {p["id"]: 0.0 for p in panels}
    for w in spec.get("walls") or []:
        mx, my = (float(w["x0"]) + float(w["x1"])) / 2, (float(w["y0"]) + float(w["y1"])) / 2
        length = math.hypot(float(w["x1"]) - float(w["x0"]), float(w["y1"]) - float(w["y0"]))
        host = min(
            panels,
            key=lambda p: max(p["x0"] - mx, 0, mx - p["x1"]) ** 2
            + max(p["y0"] - my, 0, my - p["y1"]) ** 2,
        )
        dist = math.hypot(
            max(host["x0"] - mx, 0, mx - host["x1"]), max(host["y0"] - my, 0, my - host["y1"])
        )
        if dist > 1.0:
            warnings.append(
                f"wall at ({mx:.1f},{my:.1f}) is far from any slab panel; its load is NOT applied"
            )
            continue
        height = float(w.get("height_m") or (H - h / 1000.0))
        extra_dead[host["id"]] += (
            float(w["thickness_mm"]) / 1000.0 * height * P.masonry_unit_weight_kN_m3 * length
        )
    for p in panels:
        area = (p["x1"] - p["x0"]) * (p["y1"] - p["y0"])
        p["area"] = area
        p["dead_kN_m2"] = gamma * h / 1000.0 + finishes + extra_dead[p["id"]] / area
        p["live_kN_m2"] = live
        p["wu"] = P.load_factor_dead * p["dead_kN_m2"] + P.load_factor_live * live

    # ---- strip moments per panel and direction --------------------------------------------------
    colmap = {(c["ix"], c["iy"]): c for c in lay["columns"]}
    support_demand: dict[tuple, float] = {}  # (dir, line, row, strip) -> per-m negative moment
    panel_moments: dict[str, dict[str, Any]] = {}
    for p in panels:
        i, j = p["i"], p["j"]
        Lx, Ly = p["x1"] - p["x0"], p["y1"] - p["y0"]
        sizes_x = [colmap[k]["b_mm"] for k in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))]
        sizes_y = [colmap[k]["h_mm"] for k in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))]
        mx = panel_direction_moments(
            Lx, Ly, sum(sizes_x) / 4000.0, p["wu"], (i - 1, j) in panel_at, (i + 1, j) in panel_at
        )
        my = panel_direction_moments(
            Ly, Lx, sum(sizes_y) / 4000.0, p["wu"], (i, j - 1) in panel_at, (i, j + 1) in panel_at
        )
        panel_moments[p["id"]] = {"x": mx, "y": my}
        for dr, m, line0, line1, row in (("x", mx, i, i + 1, j), ("y", my, j, j + 1, i)):
            for line, key in ((line0, "strip_neg_start"), (line1, "strip_neg_end")):
                for strip in ("cs", "ms"):
                    k = (dr, line, row, strip)
                    support_demand[k] = max(support_demand.get(k, 0.0), m[key][f"{strip}_per_m"])

    def steel(mu_per_m: float, label: str) -> dict[str, Any]:
        r = _slab_steel(mu_per_m, h, cover, fcu, fy, label)
        if r["status"] != "OK":
            failures.append(f"{label}: {r['reason']} (Mu {mu_per_m:.1f} kN.m/m, h {h:.0f} mm)")
        return r

    support_steel = {
        k: steel(v, f"{k[0]}-support line {k[1]} row {k[2]} {k[3]} top")
        for k, v in sorted(support_demand.items())
    }
    slabs: dict[str, Any] = {}
    for p in panels:
        entry: dict[str, Any] = {}
        for dr in ("x", "y"):
            m = panel_moments[p["id"]][dr]
            i, j = p["i"], p["j"]
            line0, line1, row = (i, i + 1, j) if dr == "x" else (j, j + 1, i)
            entry[dr] = {
                "case": m["case"],
                "L1": m["L1"],
                "L2": m["L2"],
                "Ln": m["Ln"],
                "M0": m["M0"],
                "cs_width_m": m["cs_width_m"],
                "ms_width_m": m["ms_width_m"],
                "bottom_cs": steel(
                    m["strip_pos"]["cs_per_m"], f"{p['id']} {dr} column-strip bottom"
                ),
                "bottom_ms": steel(
                    m["strip_pos"]["ms_per_m"], f"{p['id']} {dr} middle-strip bottom"
                ),
                "top_start_cs": support_steel[(dr, line0, row, "cs")],
                "top_start_ms": support_steel[(dr, line0, row, "ms")],
                "top_end_cs": support_steel[(dr, line1, row, "cs")],
                "top_end_ms": support_steel[(dr, line1, row, "ms")],
            }
        slabs[p["id"]] = {
            "kind": "flat_strips",
            "x0": p["x0"],
            "x1": p["x1"],
            "y0": p["y0"],
            "y1": p["y1"],
            "thickness_mm": h,
            "dead_kN_m2": p["dead_kN_m2"],
            "wu_kN_m2": p["wu"],
            "design": entry,
        }

    # ---- columns: loads, punching, moments ---------------------------------------------------------
    columns: dict[str, Any] = {}
    delivered_dead = 0.0
    applied_dead = sum(p["dead_kN_m2"] * p["area"] for p in panels)
    for c in lay["columns"]:
        ix, iy = c["ix"], c["iy"]
        adj = [
            panel_at[k]
            for k in ((ix - 1, iy - 1), (ix, iy - 1), (ix - 1, iy), (ix, iy))
            if k in panel_at
        ]
        if not adj:
            warnings.append(f"column {c['id']} touches no slab panel; not designed")
            continue
        trib_d = sum(p["dead_kN_m2"] * p["area"] / 4.0 for p in adj)
        trib_l = sum(live * p["area"] / 4.0 for p in adj)
        delivered_dead += trib_d
        vu = P.load_factor_dead * trib_d + P.load_factor_live * trib_l
        wu_loc = sum(p["wu"] for p in adj) / len(adj)
        drop_a = drop_w = 0.0
        pun = {}
        if system == "flat_slab":
            shortest = min(min(p["x1"] - p["x0"], p["y1"] - p["y0"]) for p in adj)
            drop_a = shortest / P.drop_panel_span_ratio * 1000.0  # mm, square drop
            drop_w = P.load_factor_dead * gamma * (drop_a / 1000.0) ** 2 * drop_t / 1000.0
            d_col = h + drop_t - cover - 16.0
            pun["at_column"] = punching_check(
                vu, c["b_mm"], c["h_mm"], d_col, c["position"], c.get("free_edge"), wu_loc, fcu
            )
            pun["at_drop_edge"] = punching_check(
                vu, drop_a, drop_a, d_slab, c["position"], c.get("free_edge"), wu_loc, fcu
            )
        else:
            pun["at_column"] = punching_check(
                vu, c["b_mm"], c["h_mm"], d_slab, c["position"], c.get("free_edge"), wu_loc, fcu
            )
        for where, r in pun.items():
            if r["status"] != "OK":
                failures.append(
                    f"{c['id']}: punching FAIL {where} (qu {r['qu_MPa']:.2f} > qcup {r['qcup_MPa']:.2f} MPa); "
                    + (
                        "increase column size, slab thickness or drop panel"
                        if system == "flat_slab"
                        else "increase column size or slab thickness, or use drop panels"
                    )
                )
        # unbalanced moments (kN.m), shared by the columns above and below
        m_cols = {
            "x": 0.0,
            "y": 0.0,
        }  # slab span direction x -> moment about the column's y axis (Muy)
        for dr, (lo, hi) in (("x", c["has_x"]), ("y", c["has_y"])):
            if (
                lo != hi
            ):  # slab edge in this direction: the exterior negative moment goes into the column
                m_cols[dr] = max(
                    panel_moments[p["id"]][dr]["neg_start" if hi else "neg_end"] for p in adj
                )
                continue
            sides: dict[bool, list[tuple[float, float]]] = {False: [], True: []}
            for p in adj:
                m = panel_moments[p["id"]][dr]
                high_side = (p["i"] == ix) if dr == "x" else (p["j"] == iy)
                base = m["L2"] * m["Ln"] ** 2
                wd = P.load_factor_dead * p["dead_kN_m2"]
                sides[high_side].append((base * (wd + 0.5 * P.load_factor_live * live), base * wd))
            if sides[False] and sides[True]:
                a_lo, b_lo = max(sides[False]), max(x[1] for x in sides[False])
                a_hi, b_hi = max(sides[True]), max(x[1] for x in sides[True])
                a_lo = a_lo[0]
                a_hi = a_hi[0]
                big, small_b = (a_lo, b_hi) if a_lo >= a_hi else (a_hi, b_lo)
                m_cols[dr] = P.ddm_unbalanced_coeff * abs(big - small_b)
        pu_floor = vu + drop_w + P.load_factor_dead * gamma * c["b_mm"] * c["h_mm"] / 1e6 * H
        res = design_column(
            {
                "type": "column",
                "name": c["id"],
                "b_mm": c["b_mm"],
                "h_mm": c["h_mm"],
                "fcu_MPa": fcu,
                "fy_MPa": fy,
                "cover_mm": float(spec.get("column_cover_mm", 30.0)),
                "tie_dia_mm": float(spec.get("tie_dia_mm", 8.0)),
                "Pu_kN": floors * pu_floor,
                "Mux_kNm": m_cols["y"] / 2.0,
                "Muy_kNm": m_cols["x"] / 2.0,
                "unsupported_length_m": max(H - h / 1000.0, 0.5),
                "k": 1.0,
                "braced": True,
            }
        )
        if res["status"] != "OK":
            failures.append(
                f"{c['id']}: {res['status']} {'; '.join(res.get('failures') or [])}".strip()
            )
        columns[c["id"]] = {
            "x": c["x"],
            "y": c["y"],
            "section_mm": [c["b_mm"], c["h_mm"]],
            "position": c["position"],
            "drop_mm": drop_a or None,
            "Pu_per_floor_kN": pu_floor,
            "Pu_kN": floors * pu_floor,
            "Mux_kNm": m_cols["y"] / 2.0,
            "Muy_kNm": m_cols["x"] / 2.0,
            "punching": pun,
            "design": res,
        }
    equilibrium = {
        "applied_dead_kN": applied_dead,
        "delivered_to_columns_dead_kN": delivered_dead,
        "difference_pct": (
            0.0 if applied_dead == 0 else 100.0 * (delivered_dead - applied_dead) / applied_dead
        ),
    }
    if abs(equilibrium["difference_pct"]) > 0.5:
        failures.append(f"load take-down does not balance ({equilibrium['difference_pct']:.2f} %)")
    return {
        "type": "floor",
        "name": str(spec.get("name", "floor")),
        "system": system,
        "rib": None,
        "banner": STATUS_BANNER,
        "unverified_parameters": len(P.unverified()),
        "status": "OK" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "assumptions": ASSUMPTIONS,
        "input": {
            "finishes_kN_m2": finishes,
            "live_kN_m2": live,
            "storey_height_m": H,
            "floors": floors,
            "fcu_MPa": fcu,
            "fy_MPa": fy,
            "fyst_MPa": float(spec.get("fyst_MPa", 280.0)),
            "slab_thickness_mm": h,
            "suggested_thickness_mm": suggested,
            "drop_thickness_mm": drop_t or None,
        },
        "layout": {
            "grid_x_m": lay["grid_x_m"],
            "grid_y_m": lay["grid_y_m"],
            "columns": lay["columns"],
            "panels": [{k: v for k, v in p.items()} for p in panels],
            "beams": [],
        },
        "equilibrium": equilibrium,
        "applied_live_kN": sum(live * p["area"] for p in panels),
        "beams": {},
        "slabs": slabs,
        "columns": columns,
        "support_steel": {f"{k[0]}-{k[1]}-{k[2]}-{k[3]}": v for k, v in support_steel.items()},
    }
