"""Structural layout and load take-down for a regular rectangular-grid floor.

Pipeline (all NOT FOR CONSTRUCTION, every rule here is a proposal for the engineer to accept
or change):

    columns (from the reviewed plan)
      -> propose_layout():     grid lines, beams between aligned columns, slab panels
      -> panel_loads():        slab dead/live load delivered to each supporting beam side
      -> floor_loads():        beam-span loads (slab + masonry on the beam + self weight)

The load distribution uses the usual triangular / trapezoidal tributary areas. Two numbers are
kept for every beam side: an *equivalent uniform* load (same mid-span moment, used to design the
beam) and the *true total* (used for reactions, so the column load take-down balances the applied
load exactly).
"""

from __future__ import annotations

import math
from typing import Any

from .params import P


# ------------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------------
def _cluster(values: list[float], tol: float) -> list[float]:
    """Chain-cluster values closer than tol; return the mean of each cluster, ascending."""
    vs = sorted(values)
    groups = [[vs[0]]]
    for v in vs[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _nearest(grid: list[float], v: float) -> int:
    return min(range(len(grid)), key=lambda i: abs(grid[i] - v))


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step - 1e-9) * step


# ------------------------------------------------------------------------------------------------
# layout
# ------------------------------------------------------------------------------------------------
def propose_layout(
    columns: list[dict[str, Any]], *, beam_b_mm: float | None = None, beam_h_mm: float | None = None
) -> dict[str, Any]:
    """Grid, beams and slab panels from column centres.

    columns: [{"id","x","y","b_mm","h_mm"}] with x, y in metres; b_mm is the column size along x and
    h_mm along y. Beams join consecutive columns on a common grid line (nearer than
    max_beam_span_m). A panel is every grid cell whose four sides are all covered by beams;
    anything else is reported, never silently dropped.
    """
    if len(columns) < 2:
        raise ValueError("at least two columns are needed to propose a layout")
    ids = [str(c["id"]) for c in columns]
    if len(set(ids)) != len(ids):
        raise ValueError("column ids must be unique")
    tol, max_span = P.grid_snap_tolerance_m, P.max_beam_span_m
    gx = _cluster([float(c["x"]) for c in columns], tol)
    gy = _cluster([float(c["y"]) for c in columns], tol)
    cols = {}
    for c in columns:
        ix, iy = _nearest(gx, float(c["x"])), _nearest(gy, float(c["y"]))
        key = (ix, iy)
        if any(v["key"] == key for v in cols.values()):
            raise ValueError(f"two columns snap to the same grid point {key}; check the plan")
        cols[str(c["id"])] = {
            "id": str(c["id"]),
            "key": key,
            "x": gx[ix],
            "y": gy[iy],
            "b_mm": float(c["b_mm"]),
            "h_mm": float(c["h_mm"]),
        }
    warnings: list[str] = []
    beams: list[dict[str, Any]] = []

    def add_beams(axis: str) -> None:
        # axis 'x': beam runs along x on the grid line y = const (columns sharing iy)
        line_idx = 1 if axis == "x" else 0
        for li in sorted({c["key"][line_idx] for c in cols.values()}):
            line = sorted(
                (c for c in cols.values() if c["key"][line_idx] == li),
                key=lambda c: c["x"] if axis == "x" else c["y"],
            )
            group = [line[0]]
            for c in line[1:]:
                prev = group[-1]
                gap = (c["x"] - prev["x"]) if axis == "x" else (c["y"] - prev["y"])
                if gap <= max_span + 1e-9:
                    group.append(c)
                else:
                    if len(group) > 1:
                        beams.append(_make_beam(axis, group))
                    else:
                        warnings.append(
                            f"column {prev['id']} has no beam along {axis}: next column is {gap:.2f} m away"
                        )
                    group = [c]
            if len(group) > 1:
                beams.append(_make_beam(axis, group))
            elif len(line) == 1:
                warnings.append(
                    f"column {line[0]['id']} is alone on its {axis}-direction grid line"
                )
            else:
                warnings.append(
                    f"column {group[0]['id']} has no beam along {axis}: previous column is more than {max_span:g} m away"
                )

    def _make_beam(axis: str, group: list[dict[str, Any]]) -> dict[str, Any]:
        coord = group[0]["y"] if axis == "x" else group[0]["x"]
        pos = [c["x"] if axis == "x" else c["y"] for c in group]
        spans = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
        h = beam_h_mm or max(
            P.beam_min_depth_mm, _round_up(max(spans) * 1000 / P.beam_depth_span_ratio, 50.0)
        )
        # support width = column dimension measured along the beam
        sup = [c["b_mm"] if axis == "x" else c["h_mm"] for c in group]
        return {
            "id": "",
            "axis": axis,
            "coord": coord,
            "columns": [c["id"] for c in group],
            "positions_m": pos,
            "spans_m": spans,
            "support_width_mm": sup,
            "b_mm": beam_b_mm or P.beam_default_width_mm,
            "h_mm": h,
        }

    add_beams("x")
    add_beams("y")
    for k, b in enumerate(
        sorted(beams, key=lambda b: (b["axis"], b["coord"], b["positions_m"][0])), 1
    ):
        b["id"] = f"B{b['axis'].upper()}{k}"
    beams.sort(key=lambda b: b["id"])

    def covered(axis: str, coord: float, a0: float, a1: float) -> dict[str, Any] | None:
        for b in beams:
            if (
                b["axis"] == axis
                and abs(b["coord"] - coord) <= tol
                and b["positions_m"][0] <= a0 + 1e-9
                and b["positions_m"][-1] >= a1 - 1e-9
            ):
                return b
        return None

    panels: list[dict[str, Any]] = []
    for i in range(len(gx) - 1):
        for j in range(len(gy) - 1):
            x0, x1, y0, y1 = gx[i], gx[i + 1], gy[j], gy[j + 1]
            sides = {
                "bottom": covered("x", y0, x0, x1),
                "top": covered("x", y1, x0, x1),
                "left": covered("y", x0, y0, y1),
                "right": covered("y", x1, y0, y1),
            }
            if all(sides.values()):
                panels.append(
                    {
                        "id": f"P{len(panels) + 1}",
                        "x0": x0,
                        "x1": x1,
                        "y0": y0,
                        "y1": y1,
                        "sides": {k: v["id"] for k, v in sides.items()},
                    }
                )
            elif sum(1 for v in sides.values() if v) >= 2:
                warnings.append(
                    f"cell x {x0:.2f}-{x1:.2f}, y {y0:.2f}-{y1:.2f} is not enclosed by beams "
                    f"(missing: {', '.join(k for k, v in sides.items() if not v)}); no slab panel created"
                )
    return {
        "grid_x_m": gx,
        "grid_y_m": gy,
        "columns": list(cols.values()),
        "beams": beams,
        "panels": panels,
        "warnings": warnings,
    }


# ------------------------------------------------------------------------------------------------
# slab -> beam load distribution
# ------------------------------------------------------------------------------------------------
def panel_side_loads(
    Lx: float, Ly: float, w: float, *, force_one_way: bool = False
) -> dict[str, dict[str, float]]:
    """Load delivered by a slab panel (area load w, kN/m2) to each of its four sides.

    Returns for every side: eq (kN/m, equivalent uniform load over the whole side for mid-span
    moment) and total (kN, true resultant). Sides: bottom/top run along x (length Lx),
    left/right run along y (length Ly).
    """
    if Lx <= 0 or Ly <= 0 or w < 0:
        raise ValueError("panel dimensions must be positive and the load non-negative")
    Ls, Ll = min(Lx, Ly), max(Lx, Ly)
    m = Ls / Ll
    one_way = force_one_way or Ll / Ls > P.slab_one_way_ratio

    def long_side() -> dict[str, float]:
        if one_way:
            return {"eq": w * Ls / 2, "total": w * Ls / 2 * Ll}
        q = w * Ls / 2
        return {"eq": q * (1 - m * m / 3), "total": q * (Ll - Ls / 2)}

    def short_side() -> dict[str, float]:
        if one_way:
            return {"eq": 0.0, "total": 0.0}
        return {"eq": w * Ls / 3, "total": w * Ls * Ls / 4}

    along_x_is_long = Lx >= Ly
    x_side = long_side() if along_x_is_long else short_side()
    y_side = short_side() if along_x_is_long else long_side()
    return {
        "bottom": dict(x_side),
        "top": dict(x_side),
        "left": dict(y_side),
        "right": dict(y_side),
    }


def suggested_slab_thickness_mm(Lx: float, Ly: float) -> float:
    return max(
        P.slab_min_thickness_mm, _round_up(min(Lx, Ly) * 1000 / P.slab_thickness_span_ratio, 10.0)
    )


def floor_loads(
    layout: dict[str, Any],
    *,
    finishes_kN_m2: float,
    live_kN_m2: float,
    storey_height_m: float,
    slab_thickness_mm: float | dict[str, float] | None = None,
    walls: list[dict[str, Any]] | None = None,
    slab_self_weight_kN_m2: float | None = None,
    force_one_way: bool = False,
) -> dict[str, Any]:
    """Per beam span: equivalent and true uniform loads (kN/m) from slabs and walls.

    Beam self weight is NOT included here (the beam design adds it). walls: [{"x0","y0","x1","y1",
    "thickness_mm","height_m"?}] in metres; a wall is carried by the beam it lies on (same grid line
    within the snap tolerance, overlapping its extent). Walls that lie on no beam are reported.
    """
    gamma = P.unit_weight_concrete_kN_m3
    beams = {b["id"]: b for b in layout["beams"]}
    # contributions per beam: list of (a0, a1, w_eq_dead, w_eq_live, total_dead_kN, total_live_kN)
    contrib: dict[str, list[tuple[float, float, float, float, float, float]]] = {
        k: [] for k in beams
    }
    panel_report = []
    for p in layout["panels"]:
        Lx, Ly = p["x1"] - p["x0"], p["y1"] - p["y0"]
        if isinstance(slab_thickness_mm, dict):
            t = float(slab_thickness_mm.get(p["id"], suggested_slab_thickness_mm(Lx, Ly)))
        elif slab_thickness_mm:
            t = float(slab_thickness_mm)
        else:
            t = suggested_slab_thickness_mm(Lx, Ly)
        own = gamma * t / 1000.0 if slab_self_weight_kN_m2 is None else slab_self_weight_kN_m2
        wd = own + finishes_kN_m2
        d = panel_side_loads(Lx, Ly, wd, force_one_way=force_one_way)
        l = panel_side_loads(Lx, Ly, live_kN_m2, force_one_way=force_one_way)
        p["thickness_mm"] = t
        p["dead_kN_m2"] = wd
        p["live_kN_m2"] = live_kN_m2
        p["one_way"] = force_one_way or max(Lx, Ly) / min(Lx, Ly) > P.slab_one_way_ratio
        panel_report.append(p["id"])
        for side, bid in p["sides"].items():
            a0, a1 = (p["x0"], p["x1"]) if side in ("bottom", "top") else (p["y0"], p["y1"])
            contrib[bid].append(
                (a0, a1, d[side]["eq"], l[side]["eq"], d[side]["total"], l[side]["total"])
            )

    warnings: list[str] = []
    wall_loads: dict[str, list[tuple[float, float, float]]] = {k: [] for k in beams}
    tol = P.grid_snap_tolerance_m
    for w in walls or []:
        x0, y0, x1, y1 = (float(w[k]) for k in ("x0", "y0", "x1", "y1"))
        horizontal = abs(y1 - y0) <= tol and abs(x1 - x0) > tol
        vertical = abs(x1 - x0) <= tol and abs(y1 - y0) > tol
        if not (horizontal or vertical):
            warnings.append(
                f"wall ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}) is not parallel to the grid; not assigned to a beam"
            )
            continue
        axis, coord = ("x", (y0 + y1) / 2) if horizontal else ("y", (x0 + x1) / 2)
        a0, a1 = sorted((x0, x1) if horizontal else (y0, y1))
        host = next(
            (
                b
                for b in beams.values()
                if b["axis"] == axis
                and abs(b["coord"] - coord) <= tol
                and min(a1, b["positions_m"][-1]) - max(a0, b["positions_m"][0]) > 1e-6
            ),
            None,
        )
        if host is None:
            warnings.append(
                f"wall at {axis}-line {coord:.2f} m, {a0:.2f}-{a1:.2f} m lies on no beam; its load is NOT applied"
            )
            continue
        height = float(w.get("height_m") or (storey_height_m - host["h_mm"] / 1000.0))
        kn_m = float(w["thickness_mm"]) / 1000.0 * height * P.masonry_unit_weight_kN_m3
        wall_loads[host["id"]].append(
            (max(a0, host["positions_m"][0]), min(a1, host["positions_m"][-1]), kn_m)
        )

    result = {}
    for bid, b in beams.items():
        spans = []
        for k, L in enumerate(b["spans_m"]):
            s0, s1 = b["positions_m"][k], b["positions_m"][k + 1]
            eq_d = eq_l = tr_d = tr_l = wall = 0.0
            for a0, a1, ed, el, td, tl in contrib[bid]:
                ov = min(a1, s1) - max(a0, s0)
                if ov <= 1e-9:
                    continue
                frac = ov / (a1 - a0)
                eq_d += ed * ov
                eq_l += el * ov
                tr_d += td * frac
                tr_l += tl * frac
            for a0, a1, kn_m in wall_loads[bid]:
                ov = min(a1, s1) - max(a0, s0)
                if ov > 1e-9:
                    wall += kn_m * ov
            spans.append(
                {
                    "length_m": L,
                    "design_dead_kN_m": (eq_d + wall) / L,
                    "design_live_kN_m": eq_l / L,
                    "statics_dead_kN_m": (tr_d + wall) / L,
                    "statics_live_kN_m": tr_l / L,
                    "wall_kN_m": wall / L,
                }
            )
        result[bid] = spans
    return {"beam_spans": result, "panels": panel_report, "warnings": warnings}
