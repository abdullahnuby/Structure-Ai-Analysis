"""One-way ribbed (hollow-block) slab: every rib is designed as a T-section continuous beam.

The ribs span the short direction of each panel and rest on the beams along the long sides. Dead load
per m2 = topping + rib web + block fill (+ finishes, added by the caller). NOT FOR CONSTRUCTION.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Any

from .beam_design import design_continuous_beam
from .params import P


@contextmanager
def _bars(diameters):
    saved = P.bar_diameters_mm
    P.set("bar_diameters_mm", list(diameters))
    try:
        yield
    finally:
        P.set("bar_diameters_mm", saved)


def rib_geometry(spec: dict[str, Any], shortest_span_m: float) -> dict[str, float]:
    """Rib section from the spec (spec['rib'] may override any of the suggestions)."""
    r = spec.get("rib") or {}
    width = float(r.get("width_mm", P.rib_width_mm))
    spacing = float(r.get("spacing_mm", P.rib_spacing_mm))
    topping = float(r.get("topping_mm", P.rib_topping_mm))
    depth = r.get("depth_mm")
    if depth is None:
        depth = max(
            P.rib_min_depth_mm, math.ceil(shortest_span_m * 1000 / P.rib_depth_span_ratio / 10) * 10
        )
    depth = float(depth)
    block = float(r.get("block_dead_kN_m2", P.rib_block_dead_kN_m2))
    if min(width, spacing, topping, depth) <= 0 or block < 0:
        raise ValueError("rib dimensions must be positive")
    if width >= spacing:
        raise ValueError("rib width must be smaller than the rib spacing")
    if topping >= depth:
        raise ValueError("topping must be thinner than the total rib depth")
    return {
        "width_mm": width,
        "spacing_mm": spacing,
        "topping_mm": topping,
        "depth_mm": depth,
        "block_dead_kN_m2": block,
    }


def self_weight_kN_m2(g: dict[str, float]) -> float:
    """Topping + rib webs + block fill, per m2 of slab."""
    gamma = P.unit_weight_concrete_kN_m3
    web = gamma * (g["width_mm"] / g["spacing_mm"]) * (g["depth_mm"] - g["topping_mm"]) / 1000.0
    return gamma * g["topping_mm"] / 1000.0 + web + g["block_dead_kN_m2"]


def design_rib(
    name: str,
    span_m: float,
    g: dict[str, float],
    *,
    finishes_kN_m2: float,
    live_kN_m2: float,
    fcu: float,
    fy: float,
    fyst: float,
    support_width_mm: float,
    cover_mm: float = 20.0,
) -> dict[str, Any]:
    """Design one rib (a T-section beam of width = rib width, flange = rib spacing)."""
    s = g["spacing_mm"] / 1000.0
    topping_kN_m = P.unit_weight_concrete_kN_m3 * g["topping_mm"] / 1000.0 * s
    dead = topping_kN_m + (finishes_kN_m2 + g["block_dead_kN_m2"]) * s
    spec = {
        "type": "continuous_beam",
        "name": name,
        "spans_m": [span_m],
        "b_mm": g["width_mm"],
        "h_mm": g["depth_mm"],
        "fcu_MPa": fcu,
        "fy_MPa": fy,
        "fyst_MPa": fyst,
        "cover_mm": cover_mm,
        "stirrup_dia_mm": P.rib_stirrup_dia_mm,
        "dead_kN_m": dead,  # web weight is added by the beam engine (b x h x 25)
        "live_kN_m": live_kN_m2 * s,
        "self_weight": True,
        "support_width_mm": support_width_mm,
        "flange_width_mm": g["spacing_mm"],
        "flange_thickness_mm": g["topping_mm"],
        "end_fixity": True,
    }
    with _bars(P.rib_bar_diameters_mm):
        return design_continuous_beam(spec)
