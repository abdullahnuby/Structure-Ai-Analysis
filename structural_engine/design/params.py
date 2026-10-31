"""Single source of every design-code number used by the design engine.

IMPORTANT - STATUS: UNVERIFIED.
None of the values below has been checked against the official ECP 203 text (this
project's documents mention ECP 203-2025; the values here are the commonly quoted
limit-state-design values of the ECP 203 family). A responsible engineer must compare
every entry with the code edition in force and edit it here (or through an override
file) before any result is relied on. Every report prints how many parameters are still
unverified, so an unchecked run can never look like a checked one.

Override: set STRUCTURAL_STUDIO_PARAMS to a JSON file {"name": value, ...}. Names set
that way are still listed as "overridden, verify" until the entry is listed in
{"_verified": ["name", ...]} inside the same file.
"""

from __future__ import annotations

import json
import os
from typing import Any

# name -> (value, meaning)
_DEFAULTS: dict[str, tuple[Any, str]] = {
    # ---- materials / limit state ----
    "gamma_c": (1.5, "concrete material factor"),
    "gamma_s": (1.15, "steel material factor"),
    "concrete_stress_factor": (0.67, "design concrete stress = factor * fcu / gamma_c"),
    "stress_block_ratio": (0.8, "rectangular stress block depth a = ratio * c"),
    "eps_cu": (0.003, "ultimate concrete strain"),
    "Es_MPa": (200000.0, "steel elastic modulus"),
    "Ec_factor": (4400.0, "Ec = factor * sqrt(fcu) [MPa]"),
    "unit_weight_concrete_kN_m3": (25.0, "reinforced concrete unit weight"),
    # ---- load factors ----
    "load_factor_dead": (1.4, "ultimate factor on dead load"),
    "load_factor_live": (1.6, "ultimate factor on live load"),
    # ---- flexure ----
    "c_over_d_max": (0.45, "max neutral-axis depth ratio c/d (ductility limit)"),
    "beam_min_steel_a": (0.225, "As,min >= a * sqrt(fcu)/fy * b*d"),
    "beam_min_steel_b": (1.1, "As,min >= b / fy * b*d"),
    "min_steel_cap_factor": (1.3, "As,min need not exceed factor * As,required"),
    # ---- shear (beams) ----
    "shear_qcu_factor": (0.24, "qcu = factor * sqrt(fcu/gamma_c)  [MPa]"),
    "shear_qu_max_factor": (0.7, "qu <= factor * sqrt(fcu/gamma_c)  [MPa]"),
    "stirrup_qcu_share": (0.5, "stirrups carry qsu = qu - share * qcu"),
    "stirrup_min_ratio": (0.4, "Ast,min/(b*s) >= ratio / fyst"),
    "stirrup_max_spacing_mm": (200.0, "maximum stirrup spacing"),
    "stirrup_min_spacing_mm": (75.0, "practical minimum stirrup spacing"),
    # ---- slabs ----
    "slab_qcu_factor": (0.16, "slab concrete shear qcu = factor * sqrt(fcu/gamma_c)  [MPa]"),
    "slab_min_steel_ratio": (0.0015, "minimum slab steel as ratio of b*h (high-grade steel)"),
    "slab_max_bar_spacing_mm": (200.0, "maximum slab bar spacing"),
    # ---- detailing ----
    "bar_diameters_mm": ([12, 16, 18, 20, 22, 25, 28, 32], "available bar diameters"),
    "min_clear_spacing_mm": (25.0, "minimum clear spacing between bars (also >= bar diameter)"),
    # ---- columns ----
    "column_axial_cap_ratio": (0.8, "Pu <= ratio * pure axial capacity (accidental eccentricity)"),
    "column_min_ecc_ratio": (0.05, "minimum eccentricity = ratio * section dimension"),
    "column_min_ecc_mm": (20.0, "minimum eccentricity floor in mm"),
    "column_min_steel_ratio": (0.008, "minimum total steel / gross area"),
    "column_max_steel_ratio": (0.04, "maximum total steel / gross area"),
    "column_biaxial_alpha": (1.0, "contour exponent; 1.0 = linear (most conservative)"),
    "column_slenderness_limit_braced": (
        15.0,
        "short-column limit on lambda = k*L/(least dimension), braced",
    ),
    "column_slenderness_limit_unbraced": (
        10.0,
        "short-column limit on lambda = k*L/(least dimension), unbraced",
    ),
    "column_tie_min_dia_mm": (8.0, "minimum tie diameter"),
    "column_tie_dia_bar_ratio": (0.25, "tie diameter >= ratio * largest longitudinal bar"),
    "column_tie_max_spacing_mm": (200.0, "maximum tie spacing"),
    "column_tie_spacing_bar_multiple": (
        15.0,
        "tie spacing <= multiple * smallest longitudinal bar",
    ),
    # ---- structural layout (proposal rules; engineer decisions, not code values) ----
    "grid_snap_tolerance_m": (0.15, "column centres closer than this share one grid line"),
    "max_beam_span_m": (8.0, "columns further apart than this are not joined by a proposed beam"),
    "slab_one_way_ratio": (2.0, "panel long/short ratio above which the slab is one-way"),
    "slab_thickness_span_ratio": (
        32.0,
        "suggested slab thickness = short span / ratio (rule of thumb)",
    ),
    "slab_min_thickness_mm": (120.0, "minimum suggested slab thickness"),
    "beam_depth_span_ratio": (12.0, "suggested beam depth = longest span / ratio (rule of thumb)"),
    "beam_min_depth_mm": (500.0, "minimum suggested beam depth"),
    "beam_default_width_mm": (250.0, "suggested beam width"),
    "masonry_unit_weight_kN_m3": (18.0, "wall masonry unit weight (plastered)"),
}

_VERIFIED: set[str] = set()


def _load() -> dict[str, Any]:
    values = {k: v for k, (v, _) in _DEFAULTS.items()}
    _VERIFIED.clear()
    path = os.environ.get("STRUCTURAL_STUDIO_PARAMS")
    if path:
        data = json.loads(open(path, encoding="utf-8").read())
        for key, value in data.items():
            if key == "_verified":
                _VERIFIED.update(value)
            elif key in values:
                values[key] = value
            else:
                raise KeyError(f"Unknown design parameter in override file: {key}")
    return values


class _Params:
    def __init__(self) -> None:
        object.__setattr__(self, "_v", _load())

    def __getattr__(self, name: str) -> Any:
        try:
            return object.__getattribute__(self, "_v")[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def set(self, name: str, value: Any) -> None:
        """Change one value (tests, scripts). The entry stays unverified."""
        if name not in _DEFAULTS:
            raise KeyError(name)
        self._v[name] = value

    def reset(self) -> None:
        object.__setattr__(self, "_v", _load())

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": k,
                "value": self._v[k],
                "meaning": _DEFAULTS[k][1],
                "verified": k in _VERIFIED,
            }
            for k in _DEFAULTS
        ]

    def unverified(self) -> list[str]:
        return [k for k in _DEFAULTS if k not in _VERIFIED]


P = _Params()

STATUS_BANNER = (
    "UNVERIFIED DESIGN PARAMETERS - values not checked against the official ECP 203 text; "
    "NOT FOR CONSTRUCTION"
)
