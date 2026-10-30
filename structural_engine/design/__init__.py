"""Design engine (analysis + RC section design). All results are NOT FOR CONSTRUCTION."""

from __future__ import annotations

from typing import Any

KINDS = ("continuous_beam", "slab_strip", "column")


def run_design(spec: dict[str, Any]) -> dict[str, Any]:
    """Dispatch on spec['type']; raises ValueError for unknown types or invalid input."""
    kind = spec.get("type")
    if kind == "continuous_beam":
        from .beam_design import design_continuous_beam

        return design_continuous_beam(spec)
    if kind == "slab_strip":
        from .slab_design import design_slab_strip

        return design_slab_strip(spec)
    if kind == "column":
        from .column_design import design_column

        return design_column(spec)
    raise ValueError(f"Unknown design type {kind!r}; expected one of {KINDS}")
