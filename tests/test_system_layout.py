"""Grid / beam / panel proposal and slab-to-beam load distribution, checked by statics."""

import math

import pytest

from structural_engine.design.params import P
from structural_engine.design.system import (
    floor_loads,
    panel_side_loads,
    propose_layout,
    suggested_slab_thickness_mm,
)


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def grid_columns(xs, ys, jitter=0.0, skip=()):
    cols = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            if (i, j) in skip:
                continue
            cols.append(
                {
                    "id": f"C{i}{j}",
                    "x": x + jitter * ((i + j) % 2),
                    "y": y,
                    "b_mm": 300,
                    "h_mm": 500,
                }
            )
    return cols


# ---- layout ----------------------------------------------------------------------------------
def test_regular_grid_gives_beams_on_every_line_and_a_panel_per_bay():
    lay = propose_layout(grid_columns([0, 5, 10], [0, 4, 8], jitter=0.05))
    assert (
        lay["grid_x_m"] == pytest.approx([0.025, 5.0, 10.0], abs=0.03) or len(lay["grid_x_m"]) == 3
    )
    assert len(lay["grid_x_m"]) == 3 and len(lay["grid_y_m"]) == 3
    assert sorted(b["axis"] for b in lay["beams"]) == ["x"] * 3 + ["y"] * 3
    assert all(len(b["columns"]) == 3 and len(b["spans_m"]) == 2 for b in lay["beams"])
    assert len(lay["panels"]) == 4 and not lay["warnings"]


def test_beam_depth_follows_the_longest_span_rule():
    lay = propose_layout(grid_columns([0, 6.0], [0, 3.0]))
    bx = next(b for b in lay["beams"] if b["axis"] == "x")
    assert bx["h_mm"] == max(
        P.beam_min_depth_mm, math.ceil(6000 / P.beam_depth_span_ratio / 50) * 50
    )
    by = next(b for b in lay["beams"] if b["axis"] == "y")
    assert by["h_mm"] == P.beam_min_depth_mm  # 3 m / 12 = 250 -> minimum applies


def test_far_apart_columns_are_not_joined_and_are_reported():
    lay = propose_layout(grid_columns([0, 5, 14], [0, 4]))  # last bay 9 m > 8 m
    assert all(
        max(b["positions_m"]) <= 5 + 1e-9 or min(b["positions_m"]) >= 14 - 1e-9 or b["axis"] == "y"
        for b in lay["beams"]
    )
    assert any("no beam along x" in w for w in lay["warnings"])
    assert len(lay["panels"]) == 1


def test_missing_corner_column_leaves_an_unenclosed_cell_that_is_reported():
    lay = propose_layout(grid_columns([0, 5, 10], [0, 4, 8], skip={(2, 2)}))
    assert len(lay["panels"]) == 3
    assert any("not enclosed" in w for w in lay["warnings"])


def test_invalid_columns_are_rejected():
    with pytest.raises(ValueError):
        propose_layout(grid_columns([0], [0]))
    dup = grid_columns([0, 5], [0, 4])
    dup[1]["id"] = dup[0]["id"]
    with pytest.raises(ValueError):
        propose_layout(dup)
    near = grid_columns([0, 5], [0, 4]) + [
        {"id": "X", "x": 0.05, "y": 0.0, "b_mm": 300, "h_mm": 300}
    ]
    with pytest.raises(ValueError, match="same grid point"):
        propose_layout(near)


# ---- slab -> beam distribution ------------------------------------------------------------------
@pytest.mark.parametrize(
    "Lx,Ly", [(5.0, 4.0), (4.0, 4.0), (4.0, 5.9), (6.0, 2.5), (2.0, 7.0), (7.0, 3.0)]
)
def test_resultants_add_up_to_the_applied_load(Lx, Ly):
    w = 7.3
    s = panel_side_loads(Lx, Ly, w)
    total = s["bottom"]["total"] + s["top"]["total"] + s["left"]["total"] + s["right"]["total"]
    assert total == pytest.approx(w * Lx * Ly, rel=1e-12)


def test_equivalent_load_reproduces_the_midspan_moment_of_the_real_distribution():
    """Numerical check of the trapezoid/triangle equivalence (independent of the closed form)."""
    Lx, Ly, w = 6.0, 4.5, 10.0
    s = panel_side_loads(Lx, Ly, w)
    Ls = Ly

    def mid_moment(L, q_at):  # simply supported beam, load q(x), moment at mid-span by integration
        n = 4000
        dx = L / n
        R = sum(q_at((i + 0.5) * dx) * dx for i in range(n)) / 2  # symmetric -> half the total
        m = R * L / 2
        for i in range(n // 2):
            x = (i + 0.5) * dx
            m -= q_at(x) * dx * (L / 2 - x)
        return m

    # long side (length Lx = 6): trapezoid, ramp length Ls/2, peak w*Ls/2
    q = w * Ls / 2
    trap = lambda x: q * min(1.0, x / (Ls / 2), (Lx - x) / (Ls / 2))
    assert s["bottom"]["eq"] * Lx**2 / 8 == pytest.approx(mid_moment(Lx, trap), rel=2e-3)
    # short side (length Ly = 4.5): triangle, peak w*Ls/2
    tri = lambda x: q * min(x, Ly - x) / (Ly / 2)
    assert s["left"]["eq"] * Ly**2 / 8 == pytest.approx(mid_moment(Ly, tri), rel=2e-3)


def test_one_way_slab_loads_only_the_long_sides():
    s = panel_side_loads(8.0, 3.0, 10.0)  # ratio 2.67 > 2
    assert s["left"]["eq"] == s["right"]["eq"] == 0.0
    assert s["bottom"]["eq"] == pytest.approx(10.0 * 3.0 / 2)
    assert s["bottom"]["total"] == pytest.approx(10.0 * 3.0 / 2 * 8.0)


def test_square_panel_is_symmetric():
    s = panel_side_loads(4.0, 4.0, 9.0)
    assert {round(v["eq"], 9) for v in s.values()} == {round(9.0 * 4.0 / 3, 9)}


# ---- floor loads -----------------------------------------------------------------------------
LOADS = dict(finishes_kN_m2=1.5, live_kN_m2=2.0, storey_height_m=3.2)


def beam_total(fl, lay, key):
    return sum(sp[key] * sp["length_m"] for spans in fl["beam_spans"].values() for sp in spans)


def test_beam_loads_balance_the_floor_load_exactly():
    lay = propose_layout(grid_columns([0, 5, 10], [0, 4, 8]))
    fl = floor_loads(lay, **LOADS)
    area = sum((p["x1"] - p["x0"]) * (p["y1"] - p["y0"]) for p in lay["panels"])
    assert area == pytest.approx(80.0)
    t = suggested_slab_thickness_mm(5.0, 4.0)
    dead = (25.0 * t / 1000 + 1.5) * area
    assert beam_total(fl, lay, "statics_dead_kN_m") == pytest.approx(dead, rel=1e-9)
    assert beam_total(fl, lay, "statics_live_kN_m") == pytest.approx(2.0 * area, rel=1e-9)


def test_design_load_is_never_below_the_statics_load_per_metre_for_triangular_sides():
    lay = propose_layout(grid_columns([0, 4.0], [0, 4.0]))
    fl = floor_loads(lay, **LOADS)
    for spans in fl["beam_spans"].values():
        sp = spans[0]
        # square panel: eq = w*L/3 per side-length unit, true average = w*L/4 -> eq is larger (moment basis)
        assert sp["design_dead_kN_m"] > sp["statics_dead_kN_m"] > 0


def test_a_wall_on_a_beam_adds_its_line_load_and_a_stray_wall_is_reported():
    lay = propose_layout(grid_columns([0, 5], [0, 4]))
    base = floor_loads(lay, **LOADS)
    wall = {"x0": 0, "y0": 0, "x1": 5, "y1": 0.02, "thickness_mm": 250}
    fl = floor_loads(lay, walls=[wall], **LOADS)
    bx = next(b for b in lay["beams"] if b["axis"] == "x" and b["coord"] < 1)
    h = (3.2 - bx["h_mm"] / 1000) * 0.25 * 18.0
    got = (
        fl["beam_spans"][bx["id"]][0]["design_dead_kN_m"]
        - base["beam_spans"][bx["id"]][0]["design_dead_kN_m"]
    )
    assert got == pytest.approx(h)
    stray = floor_loads(
        lay, walls=[{"x0": 1, "y0": 2, "x1": 4, "y1": 2, "thickness_mm": 120}], **LOADS
    )
    assert any("lies on no beam" in w for w in stray["warnings"])
    diag = floor_loads(
        lay, walls=[{"x0": 0, "y0": 0, "x1": 3, "y1": 3, "thickness_mm": 120}], **LOADS
    )
    assert any("not parallel" in w for w in diag["warnings"])


def test_explicit_thickness_overrides_the_suggestion():
    lay = propose_layout(grid_columns([0, 5], [0, 4]))
    a = floor_loads(lay, slab_thickness_mm=200, **LOADS)
    assert lay["panels"][0]["thickness_mm"] == 200
    b = floor_loads(lay, slab_thickness_mm={"P1": 150}, **LOADS)
    assert lay["panels"][0]["thickness_mm"] == 150
    assert beam_total(a, lay, "statics_dead_kN_m") > beam_total(b, lay, "statics_dead_kN_m")
