"""Design of a whole regular-grid floor: beams, slab panels and the columns that carry them.

Input is the reviewed column layout (plus optional walls and the project loads). Everything else is
proposed (see system.py) and designed with the element engines. The column loads come from the beam
reactions, repeated for ``floors`` identical storeys. NOT FOR CONSTRUCTION; every proposal rule and
code value is UNVERIFIED and listed in the report.
"""

from __future__ import annotations

from typing import Any

from .beam_design import BeamInput, analyze_continuous_beam, design_continuous_beam
from .column_design import design_column
from .params import P, STATUS_BANNER
from .ribbed_design import design_rib, rib_geometry, self_weight_kN_m2
from .slab_design import design_slab_strip
from .system import floor_loads, propose_layout

BEAM_SYSTEMS = ("beam_slab", "ribbed")

ASSUMPTIONS = [
    "Grid, beams and slab panels are PROPOSED from the column positions; the engineer must accept or change them.",
    "All storeys carry the same loads and have the same layout (no roof/typical difference, no setbacks).",
    "Slab-to-beam load: triangular/trapezoidal tributary areas (equivalent uniform load for beam design; true resultants for reactions).",
    "Each beam line is designed as a continuous beam on rigid column supports (no frame action); end-support hogging uses the monolithic-frame minimum.",
    "Slab panels are designed as one-way strips in the short direction; two-way action and continuity between panels are ignored (conservative for bending, long-direction steel not designed).",
    "Column moments come only from beam end moments at exterior supports (half to the column below); interior-column unbalanced moments from pattern loading are NOT included, minimum eccentricity applies.",
    "Columns are assumed braced; unsupported length = storey height - deepest framing beam.",
    "NOT CHECKED: lateral loads (wind/seismic), punching, deflection, crack width, development/lap lengths, curtailment, foundations, stairs, cantilevers.",
]


def _assumptions(system: str) -> list[str]:
    out = list(ASSUMPTIONS)
    if system == "ribbed":
        out[4] = (
            "Ribs span the short direction of each panel as single-span T-section beams (end fixity assumed); "
            "solid zones next to beams, cross ribs and two-way action are ignored; web weight is counted over the full depth."
        )
    return out


def _need(spec: dict[str, Any], key: str) -> float:
    if key not in spec:
        raise ValueError(f"missing input: {key}")
    v = float(spec[key])
    if v < 0:
        raise ValueError(f"{key} must not be negative")
    return v


def design_floor(spec: dict[str, Any]) -> dict[str, Any]:
    columns = spec.get("columns")
    if spec.get("system") in ("flat_plate", "flat_slab"):
        from .flat_floor import design_flat_floor

        return design_flat_floor(spec)
    if not isinstance(columns, list) or len(columns) < 2:
        raise ValueError("columns must be a list of at least two columns")
    finishes, live = _need(spec, "finishes_kN_m2"), _need(spec, "live_kN_m2")
    H = _need(spec, "storey_height_m")
    if H <= 0:
        raise ValueError("storey_height_m must be positive")
    floors = int(spec.get("floors", 1))
    if floors < 1:
        raise ValueError("floors must be at least 1")
    fcu, fy = float(spec.get("fcu_MPa", 30.0)), float(spec.get("fy_MPa", 400.0))
    fyst = float(spec.get("fyst_MPa", 280.0))
    cover = float(spec.get("cover_mm", 25.0))
    name = str(spec.get("name", "floor"))
    system = str(spec.get("system", "beam_slab"))
    if system in ("flat_plate", "flat_slab"):
        from .flat_floor import design_flat_floor

        return design_flat_floor(spec)
    if system not in BEAM_SYSTEMS:
        raise ValueError(f"unknown system {system!r}; expected one of {BEAM_SYSTEMS}")

    layout = propose_layout(
        columns, beam_b_mm=spec.get("beam_b_mm"), beam_h_mm=spec.get("beam_h_mm")
    )
    rib_g = None
    own_weight = None
    if system == "ribbed":
        if not layout["panels"]:
            raise ValueError("ribbed system needs at least one slab panel enclosed by beams")
        longest_short = max(min(p["x1"] - p["x0"], p["y1"] - p["y0"]) for p in layout["panels"])
        rib_g = rib_geometry(spec, longest_short)
        own_weight = self_weight_kN_m2(rib_g)
    loads = floor_loads(
        layout,
        finishes_kN_m2=finishes,
        live_kN_m2=live,
        storey_height_m=H,
        slab_thickness_mm=rib_g["depth_mm"] if rib_g else spec.get("slab_thickness_mm"),
        walls=spec.get("walls"),
        slab_self_weight_kN_m2=own_weight,
        force_one_way=system == "ribbed",
    )
    warnings = (
        list(spec.get("plan_notes") or []) + list(layout["warnings"]) + list(loads["warnings"])
    )
    failures: list[str] = []
    if not layout["beams"]:
        raise ValueError("no beams could be proposed from these columns")
    if not layout["panels"]:
        warnings.append("no slab panel is enclosed by beams; slabs were not designed")

    # ---- beams ---------------------------------------------------------------------------------
    gamma = P.unit_weight_concrete_kN_m3
    beam_results: dict[str, Any] = {}
    col_reaction: dict[str, dict[str, float]] = {
        c["id"]: {"dead": 0.0, "ult": 0.0, "Mux": 0.0, "Muy": 0.0, "beams": []}
        for c in layout["columns"]
    }
    applied_beam_self = 0.0
    delivered_dead = 0.0
    for b in layout["beams"]:
        sp = loads["beam_spans"][b["id"]]
        common = {
            "name": b["id"],
            "spans_m": b["spans_m"],
            "b_mm": b["b_mm"],
            "h_mm": b["h_mm"],
            "fcu_MPa": fcu,
            "fy_MPa": fy,
            "fyst_MPa": fyst,
            "cover_mm": cover,
            "support_width_mm": b["support_width_mm"],
            "self_weight": True,
        }
        design = design_continuous_beam(
            {
                **common,
                "type": "continuous_beam",
                "dead_kN_m": [s["design_dead_kN_m"] for s in sp],
                "live_kN_m": [s["design_live_kN_m"] for s in sp],
            }
        )
        statics = analyze_continuous_beam(
            BeamInput.from_dict(
                {
                    **common,
                    "dead_kN_m": [s["statics_dead_kN_m"] for s in sp],
                    "live_kN_m": [s["statics_live_kN_m"] for s in sp],
                }
            )
        )
        applied_beam_self += gamma * b["b_mm"] * b["h_mm"] / 1e6 * sum(b["spans_m"])
        delivered_dead += sum(statics["reaction_dead_kN"])
        last = len(b["columns"]) - 1
        for idx, cid in enumerate(b["columns"]):
            rec = col_reaction[cid]
            rec["dead"] += statics["reaction_dead_kN"][idx]
            rec["ult"] += statics["reaction_ultimate_max_kN"][idx]
            rec["beams"].append(b["id"])
            if idx in (0, last) and design.get("supports"):
                m_end = design["supports"][idx]["hogging"].get("Mu_kNm") or 0.0
                # a beam running along y bends the column over its y-dimension (Mux)
                rec["Mux" if b["axis"] == "y" else "Muy"] += m_end / 2.0
        if design["status"] != "OK":
            failures += [f"{b['id']}: {f}" for f in design["failures"]]
        beam_results[b["id"]] = {
            "axis": b["axis"],
            "coord_m": b["coord"],
            "columns": b["columns"],
            "section_mm": [b["b_mm"], b["h_mm"]],
            "loads": sp,
            "design": design,
            "reaction_dead_kN": statics["reaction_dead_kN"],
            "reaction_ultimate_max_kN": statics["reaction_ultimate_max_kN"],
        }

    # ---- slabs -----------------------------------------------------------------------------------
    slab_results: dict[str, Any] = {}
    applied_slab_dead = applied_slab_live = 0.0
    for p in layout["panels"]:
        Lx, Ly = p["x1"] - p["x0"], p["y1"] - p["y0"]
        Ls = min(Lx, Ly)
        applied_slab_dead += p["dead_kN_m2"] * Lx * Ly
        applied_slab_live += p["live_kN_m2"] * Lx * Ly
        bw = min(beam_results[bid]["section_mm"][0] for bid in p["sides"].values())
        if rib_g:
            r = design_rib(
                p["id"],
                Ls,
                rib_g,
                finishes_kN_m2=finishes,
                live_kN_m2=live,
                fcu=fcu,
                fy=fy,
                fyst=fyst,
                support_width_mm=bw,
            )
        else:
            r = design_slab_strip(
                {
                    "type": "slab_strip",
                    "name": p["id"],
                    "spans_m": [Ls],
                    "thickness_mm": p["thickness_mm"],
                    "fcu_MPa": fcu,
                    "fy_MPa": fy,
                    "cover_mm": float(spec.get("slab_cover_mm", 20.0)),
                    "dead_kN_m2": finishes,
                    "live_kN_m2": live,
                    "support_width_mm": bw,
                }
            )
        if r["status"] != "OK":
            failures += [f"{p['id']}: {f}" for f in r["failures"]]
        slab_results[p["id"]] = {
            "x0": p["x0"],
            "x1": p["x1"],
            "y0": p["y0"],
            "y1": p["y1"],
            "short_span_m": Ls,
            "direction": "x" if Lx < Ly else "y",
            "one_way": p["one_way"],
            "thickness_mm": p["thickness_mm"],
            "kind": "rib" if rib_g else "solid_strip",
            "design": r,
        }

    # ---- columns -------------------------------------------------------------------------------------
    deepest = max(b["h_mm"] for b in layout["beams"]) / 1000.0
    column_results: dict[str, Any] = {}
    for c in layout["columns"]:
        rec = col_reaction[c["id"]]
        if not rec["beams"]:
            warnings.append(f"column {c['id']} carries no beam; not designed")
            continue
        self_w = P.load_factor_dead * gamma * c["b_mm"] * c["h_mm"] / 1e6 * H
        pu = floors * (rec["ult"] + self_w)
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
                "Pu_kN": pu,
                "Mux_kNm": rec["Mux"],
                "Muy_kNm": rec["Muy"],
                "unsupported_length_m": max(H - deepest, 0.5),
                "k": 1.0,
                "braced": True,
            }
        )
        if res["status"] != "OK":
            failures.append(
                f"{c['id']}: {res['status']} {'; '.join(res.get('failures') or [])}".strip()
            )
        column_results[c["id"]] = {
            "x": c["x"],
            "y": c["y"],
            "section_mm": [c["b_mm"], c["h_mm"]],
            "beams": rec["beams"],
            "Pu_per_floor_kN": rec["ult"] + self_w,
            "Pu_kN": pu,
            "Mux_kNm": rec["Mux"],
            "Muy_kNm": rec["Muy"],
            "design": res,
        }

    applied = (
        applied_slab_dead
        + applied_beam_self
        + sum(
            w
            for w in [
                sum(
                    s["wall_kN_m"] * s["length_m"]
                    for sp in loads["beam_spans"].values()
                    for s in sp
                )
            ]
        )
    )
    equilibrium = {
        "applied_dead_kN": applied,
        "delivered_to_columns_dead_kN": delivered_dead,
        "difference_pct": 0.0 if applied == 0 else 100.0 * (delivered_dead - applied) / applied,
    }
    if abs(equilibrium["difference_pct"]) > 0.5:
        failures.append(
            f"load take-down does not balance ({equilibrium['difference_pct']:.2f} %): check beam/slab coverage"
        )
    status = "OK" if not failures else "FAIL"
    return {
        "type": "floor",
        "name": name,
        "system": system,
        "rib": rib_g,
        "banner": STATUS_BANNER,
        "unverified_parameters": len(P.unverified()),
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "assumptions": _assumptions(system),
        "input": {
            "finishes_kN_m2": finishes,
            "live_kN_m2": live,
            "storey_height_m": H,
            "floors": floors,
            "fcu_MPa": fcu,
            "fy_MPa": fy,
            "fyst_MPa": fyst,
        },
        "layout": {
            "grid_x_m": layout["grid_x_m"],
            "grid_y_m": layout["grid_y_m"],
            "columns": layout["columns"],
            "panels": layout["panels"],
            "beams": [{k: v for k, v in b.items()} for b in layout["beams"]],
        },
        "equilibrium": equilibrium,
        "applied_live_kN": applied_slab_live,
        "beams": beam_results,
        "slabs": slab_results,
        "columns": column_results,
    }
