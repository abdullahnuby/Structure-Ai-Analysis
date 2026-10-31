"""Turn a reviewed plan candidate (DXF -> components) into the input of the floor design.

Only what the drawing actually says is used: column centres and sizes from the column geometry,
walls from the wall layers. Everything else (loads, storey height, number of floors, materials) must be
given by the engineer. Every skipped or doubtful entity is returned in ``notes`` - nothing is dropped
silently.
"""

from __future__ import annotations

from typing import Any

from .params import P


def _mm5(v_m: float) -> float:
    return round(v_m * 1000.0 / 5.0) * 5.0


def columns_and_walls(candidate: dict[str, Any]) -> dict[str, Any]:
    notes: list[str] = []
    raw_cols: list[tuple[float, float, float, float, str]] = []
    walls: list[dict[str, Any]] = []
    tol = P.grid_snap_tolerance_m
    for comp in candidate.get("components", []):
        role = comp.get("role")
        geom = comp.get("geometry_m") or {}
        box = geom.get("bbox")
        cid = comp.get("candidate_id", "?")
        declared = comp.get("declared_dimensions_cm") or {}
        if role == "column":
            if box and (box["max_x"] - box["min_x"]) > 0 and (box["max_y"] - box["min_y"]) > 0:
                bx, by = box["max_x"] - box["min_x"], box["max_y"] - box["min_y"]
                cx, cy = (box["min_x"] + box["max_x"]) / 2, (box["min_y"] + box["max_y"]) / 2
            elif comp.get("center_3d_m") and declared.get("width") and declared.get("depth"):
                cx, cy = comp["center_3d_m"][0], comp["center_3d_m"][1]
                bx, by = declared["width"] / 100.0, declared["depth"] / 100.0
                notes.append(f"{cid}: column size taken from the layer name (no usable geometry)")
            else:
                notes.append(f"{cid}: column skipped - no usable geometry or size")
                continue
            raw_cols.append((cx, cy, _mm5(bx), _mm5(by), cid))
        elif role == "wall":
            if not box:
                notes.append(f"{cid}: wall skipped - no geometry")
                continue
            dx, dy = box["max_x"] - box["min_x"], box["max_y"] - box["min_y"]
            thick_decl = declared.get("thickness")
            if (
                dx >= dy
                and dx > tol
                and dy <= tol * 2 + 1e-9
                or dy > dx
                and dy > tol
                and dx <= tol * 2 + 1e-9
            ):
                horizontal = dx >= dy
                length, cross = (dx, dy) if horizontal else (dy, dx)
                if length < 3 * max(cross, 1e-9) and cross > tol:
                    notes.append(f"{cid}: wall entity not elongated - ignored")
                    continue
                t_mm = float(thick_decl) * 10.0 if thick_decl else _mm5(cross)
                if not t_mm:
                    notes.append(f"{cid}: wall skipped - thickness unknown")
                    continue
                if horizontal:
                    y = (box["min_y"] + box["max_y"]) / 2
                    walls.append(
                        {
                            "x0": box["min_x"],
                            "y0": y,
                            "x1": box["max_x"],
                            "y1": y,
                            "thickness_mm": t_mm,
                            "source": cid,
                        }
                    )
                else:
                    x = (box["min_x"] + box["max_x"]) / 2
                    walls.append(
                        {
                            "x0": x,
                            "y0": box["min_y"],
                            "x1": x,
                            "y1": box["max_y"],
                            "thickness_mm": t_mm,
                            "source": cid,
                        }
                    )
            else:
                notes.append(f"{cid}: wall is not parallel to the axes - not loaded onto a beam")
        # beams, slabs and openings in the drawing are not used yet; counted below
    # a wall drawn as two parallel lines would otherwise be loaded twice
    kept: list[dict[str, Any]] = []
    for w in walls:
        horiz = abs(w["y1"] - w["y0"]) <= abs(w["x1"] - w["x0"])
        dup = False
        for k in kept:
            khoriz = abs(k["y1"] - k["y0"]) <= abs(k["x1"] - k["x0"])
            if horiz != khoriz:
                continue
            if horiz:
                close = abs(w["y0"] - k["y0"]) <= 0.4
                overlap = min(max(w["x0"], w["x1"]), max(k["x0"], k["x1"])) - max(
                    min(w["x0"], w["x1"]), min(k["x0"], k["x1"])
                )
                shorter = min(abs(w["x1"] - w["x0"]), abs(k["x1"] - k["x0"]))
            else:
                close = abs(w["x0"] - k["x0"]) <= 0.4
                overlap = min(max(w["y0"], w["y1"]), max(k["y0"], k["y1"])) - max(
                    min(w["y0"], w["y1"]), min(k["y0"], k["y1"])
                )
                shorter = min(abs(w["y1"] - w["y0"]), abs(k["y1"] - k["y0"]))
            if close and overlap > 0.5 * shorter:
                dup = True
                notes.append(
                    f"{w['source']}: parallel to {k['source']} within 0.4 m - treated as the other face of the same wall, not loaded twice"
                )
                break
        if not dup:
            kept.append(w)
    ordered = sorted(raw_cols, key=lambda c: (round(c[1], 1), c[0]))
    columns = [
        {"id": f"C{i}", "x": c[0], "y": c[1], "b_mm": c[2], "h_mm": c[3], "source": c[4]}
        for i, c in enumerate(ordered, 1)
    ]
    counts = candidate.get("component_counts", {})
    for role in ("beam", "slab", "opening"):
        if counts.get(role):
            notes.append(
                f"{counts[role]} {role} entities in the drawing are not used yet (layout is proposed from the columns)"
            )
    return {"columns": columns, "walls": kept, "notes": notes}


def floor_spec_from_candidate(candidate: dict[str, Any], **loads: Any) -> dict[str, Any]:
    """loads must contain finishes_kN_m2, live_kN_m2, storey_height_m (+ optional floors, fcu_MPa ...)."""
    got = columns_and_walls(candidate)
    if len(got["columns"]) < 2:
        raise ValueError("the plan has fewer than two usable columns; check the column layers")
    spec = {
        "type": "floor",
        "name": loads.pop("name", None) or candidate.get("floor_identity") or "floor",
    }
    spec.update(columns=got["columns"], walls=got["walls"], **loads)
    spec["plan_notes"] = got["notes"]
    return spec
