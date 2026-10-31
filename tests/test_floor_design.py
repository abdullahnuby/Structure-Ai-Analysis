"""Whole-floor design: statics of the load take-down and consistency of the element results."""

import copy
import json
from pathlib import Path

import pytest

from structural_engine.design import run_design
from structural_engine.design.params import P

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/design/floor_2x2.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


@pytest.fixture(scope="module")
def result():
    return run_design(copy.deepcopy(EXAMPLE))


def spec(**patch):
    s = copy.deepcopy(EXAMPLE)
    s.update(patch)
    return s


def col_self_weight(c):
    return 1.4 * 25.0 * c["section_mm"][0] * c["section_mm"][1] / 1e6 * 3.2


def test_example_designs_every_element(result):
    assert result["status"] == "OK", result["failures"]
    assert len(result["columns"]) == 9 and len(result["beams"]) == 6 and len(result["slabs"]) == 4
    assert all(
        e["design"]["status"] == "OK"
        for k in ("columns", "beams", "slabs")
        for e in result[k].values()
    )
    assert result["layout"]["grid_x_m"] == [0.0, 5.0, 10.0]


def test_dead_load_take_down_balances_exactly(result):
    eq = result["equilibrium"]
    area, t = 10.0 * 9.0, 150.0
    slab = (25.0 * t / 1000 + 1.5) * area
    beams = 25.0 * 0.25 * 0.5 * (3 * 10.0 + 3 * 9.0)  # 6 beams, 500 mm deep, 250 wide
    walls = 38.0 * (3.2 - 0.5) * 0.25 * 18.0
    assert eq["applied_dead_kN"] == pytest.approx(slab + beams + walls, rel=1e-9)  # hand total
    assert eq["delivered_to_columns_dead_kN"] == pytest.approx(eq["applied_dead_kN"], rel=1e-9)
    assert abs(eq["difference_pct"]) < 1e-9


def test_ultimate_column_loads_bracket_the_applied_ultimate_load(result):
    area = 90.0
    dead = result["equilibrium"]["applied_dead_kN"]
    live = 2.0 * area
    fully_loaded = 1.4 * dead + 1.6 * live
    got = sum(c["Pu_per_floor_kN"] - col_self_weight(c) for c in result["columns"].values())
    assert got >= fully_loaded - 1e-6  # pattern live load can only add reaction
    assert got <= 1.12 * fully_loaded  # ...but not by much on a 2x2 grid


def test_symmetric_layout_gives_symmetric_columns(result):
    c = result["columns"]
    for group in (("C1", "C3", "C7", "C9"), ("C2", "C8"), ("C4", "C6")):
        vals = [c[k]["Pu_kN"] for k in group]
        assert vals == pytest.approx([vals[0]] * len(vals), rel=1e-9)
    assert c["C5"]["Pu_kN"] > c["C2"]["Pu_kN"] > c["C1"]["Pu_kN"]  # interior > edge > corner


def test_only_exterior_beam_ends_transfer_moment_to_columns(result):
    c = result["columns"]
    assert c["C5"]["Mux_kNm"] == 0 and c["C5"]["Muy_kNm"] == 0
    assert c["C1"]["Mux_kNm"] > 0 and c["C1"]["Muy_kNm"] > 0  # corner: both beams end here
    # C2 is the end of a y-beam only -> Mux; interior of an x-beam -> no Muy
    assert c["C2"]["Mux_kNm"] > 0 and c["C2"]["Muy_kNm"] == 0
    assert c["C4"]["Muy_kNm"] > 0 and c["C4"]["Mux_kNm"] == 0


def test_floor_count_scales_the_column_axial_load(result):
    more = run_design(spec(floors=8))
    for k, c in result["columns"].items():
        assert more["columns"][k]["Pu_kN"] == pytest.approx(2 * c["Pu_kN"], rel=1e-9)
        assert more["columns"][k]["Pu_per_floor_kN"] == pytest.approx(c["Pu_per_floor_kN"])


def test_walls_add_exactly_their_weight(result):
    no_walls = run_design(spec(walls=[]))
    added = result["equilibrium"]["applied_dead_kN"] - no_walls["equilibrium"]["applied_dead_kN"]
    assert added == pytest.approx(38.0 * 2.7 * 0.25 * 18.0, rel=1e-9)
    assert abs(no_walls["equilibrium"]["difference_pct"]) < 1e-9


def test_overloaded_small_columns_fail_and_name_the_column():
    cols = [dict(c, b_mm=200, h_mm=200) for c in EXAMPLE["columns"]]
    r = run_design(spec(columns=cols, floors=12))
    assert r["status"] == "FAIL"
    assert any(f.startswith("C5") for f in r["failures"])


def test_missing_column_is_reported_and_the_rest_is_still_designed():
    cols = [c for c in EXAMPLE["columns"] if c["id"] != "C9"]
    r = run_design(spec(columns=cols, walls=[]))
    assert any("not enclosed" in w for w in r["warnings"])
    assert len(r["slabs"]) == 3 and len(r["columns"]) == 8
    assert abs(r["equilibrium"]["difference_pct"]) < 1e-9


def test_explicit_slab_thickness_flows_into_the_load():
    thin, thick = run_design(spec(slab_thickness_mm=130)), run_design(spec(slab_thickness_mm=200))
    assert thick["equilibrium"]["applied_dead_kN"] - thin["equilibrium"][
        "applied_dead_kN"
    ] == pytest.approx(25.0 * 0.07 * 90.0)
    assert all(s["thickness_mm"] == 200 for s in thick["slabs"].values())


def test_result_is_serialisable_and_carries_limits(result):
    json.dumps(result)
    assert "UNVERIFIED" in result["banner"]
    assert any("lateral" in a for a in result["assumptions"])


@pytest.mark.parametrize(
    "patch",
    [
        {"columns": []},
        {"storey_height_m": 0},
        {"floors": 0},
        {"live_kN_m2": -1},
        {"finishes_kN_m2": None},
    ],
)
def test_invalid_input_is_rejected(patch):
    bad = spec(**patch)
    if patch.get("finishes_kN_m2", 0) is None:
        del bad["finishes_kN_m2"]
    with pytest.raises((ValueError, KeyError, TypeError)):
        run_design(bad)
