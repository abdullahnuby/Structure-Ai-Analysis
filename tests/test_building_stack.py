import os
import subprocess
import sys
from pathlib import Path

import pytest

from structural_engine.building_stack import (
    _max_column_matching,
    _offset,
    build_multistorey_building_candidate,
    validate_building_stack_config,
)

REPO = Path(__file__).resolve().parents[1]

GOOD = {
    "above_ground_story_count": 3,
    "ground_story_height_m": 4.0,
    "upper_story_height_mode": "uniform",
    "typical_story_height_m": 3.2,
    "ground_finished_floor_offset_from_street_m": 0.3,
    "street_datum_elevation_m": 0.0,
    "typical_plan_mode": "same_as_ground",
    "roof_plan_mode": "typical_proxy",
}


def _validate(config, **plans):
    flags = dict(
        has_ground_plan=True, has_typical_plan=False, has_basement_plan=False, has_roof_plan=False
    )
    flags.update(plans)
    return validate_building_stack_config(config, **flags)


# ---- validation ---------------------------------------------------------------------------------


def test_valid_config_normalises():
    r = _validate(GOOD)
    assert r["valid"], r["errors"]
    assert r["normalized"]["upper_story_heights_m"] == [3.2, 3.2]
    assert r["normalized"]["ground_finished_floor_elevation_m"] == pytest.approx(0.3)


@pytest.mark.parametrize(
    "patch",
    [
        {"above_ground_story_count": 0},
        {"above_ground_story_count": 101},
        {"above_ground_story_count": "abc"},
        {"ground_story_height_m": -1},
        {"ground_story_height_m": float("nan")},
        {"ground_finished_floor_offset_from_street_m": float("inf")},
    ],
)
def test_invalid_values_are_errors(patch):
    r = _validate({**GOOD, **patch})
    assert not r["valid"] and r["errors"]


def test_basement_inputs_are_validated():
    bad = {
        **GOOD,
        "basement_enabled": True,
        "basement_count": "x",
        "basement_plan_mode": "ground_footprint_proxy",
    }
    assert not _validate(bad)["valid"]
    bad = {
        **GOOD,
        "basement_enabled": True,
        "basement_count": 1,
        "basement_story_height_m": -3,
        "basement_plan_mode": "ground_footprint_proxy",
    }
    assert not _validate(bad)["valid"]


def test_validation_does_not_depend_on_assert_statements():
    """`python -O` strips asserts; the validator must reject bad input all the same."""
    code = (
        "from structural_engine.building_stack import validate_building_stack_config as v;"
        "r=v({'above_ground_story_count':0,'ground_story_height_m':-5,'ground_finished_floor_offset_from_street_m':0.3,'street_datum_elevation_m':0,'roof_plan_mode':'typical_proxy'},has_ground_plan=True,"
        "has_typical_plan=False,has_basement_plan=False,has_roof_plan=False);"
        "raise SystemExit(0 if (not r['valid'] and r['errors']) else 1)"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    out = subprocess.run([sys.executable, "-O", "-c", code], env=env, cwd=REPO, capture_output=True)
    assert out.returncode == 0, out.stderr.decode()


# ---- floor alignment and column continuity --------------------------------------------------------


def _comp(role, cid, x0, y0, x1, y1):
    return {
        "candidate_id": cid,
        "source_entity_id": cid,
        "role": role,
        "source_layer": role,
        "geometry_m": {
            "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]],
            "bbox": {"min_x": x0, "max_x": x1, "min_y": y0, "max_y": y1},
            "closed": True,
        },
        "declared_dimensions_cm": {"width": 40, "depth": 40},
    }


def _col(cid, x, y, s=0.4):
    return _comp("column", cid, x - s / 2, y - s / 2, x + s / 2, y + s / 2)


def _plan(components, name="plan.dxf"):
    return {"components": components, "source_dxf": {"filename": name}}


GRID = [(0, 0), (5, 0), (0, 5), (5, 5)]


def test_alignment_uses_columns_not_every_element():
    # A stair wall far to the left exists only on the ground floor. Aligning on all elements
    # would shift the typical floor by metres; aligning on columns gives the true 1 m shift.
    ground = _plan(
        [_col(f"G{i}", x, y) for i, (x, y) in enumerate(GRID)] + [_comp("wall", "W", -3, 0, -2, 4)]
    )
    typical = _plan([_col(f"T{i}", x + 1, y + 1) for i, (x, y) in enumerate(GRID)])
    dx, dy, warnings = _offset(ground, typical)
    assert dx == pytest.approx(-1.0) and dy == pytest.approx(-1.0)
    assert not any("كل العناصر" in w for w in warnings)


def test_alignment_falls_back_with_a_warning_when_no_columns():
    ground = _plan([_comp("wall", "W1", 0, 0, 5, 0.2)])
    other = _plan([_comp("wall", "W2", 1, 1, 6, 1.2)])
    dx, dy, warnings = _offset(ground, other)
    assert (dx, dy) == (pytest.approx(-1.0), pytest.approx(-1.0))
    assert any("كل العناصر" in w for w in warnings)


def test_matching_finds_a_full_assignment_when_greedy_would_not():
    # left0 can only use right0; left1 prefers right0 but can also use right1.
    assert _max_column_matching([[0], [0, 1]], 2) == {0: 0, 1: 1}
    assert _max_column_matching([[], [0]], 1) == {1: 0}
    assert _max_column_matching([[0], [0]], 1) in ({0: 0}, {1: 0})  # only one can win


def test_stacked_model_matches_columns_floor_to_floor():
    ground = _plan([_col(f"G{i}", x, y) for i, (x, y) in enumerate(GRID)], "ground.dxf")
    typical = _plan(
        [_col(f"T{i}", x, y) for i, (x, y) in enumerate(GRID[:3])], "typical.dxf"
    )  # one missing
    model = build_multistorey_building_candidate(
        {**GOOD, "typical_plan_mode": "separate"}, ground_plan=ground, typical_plan=typical
    )
    first = model["vertical_continuity_checks"][0]
    assert first["lower_column_count"] == 4 and first["upper_column_count"] == 3
    assert first["matched_column_count"] == 3
    assert first["status"] == "MATCHED_WITH_UNMATCHED_REVIEW"
    assert len(first["lower_unmatched_column_ids"]) == 1
    assert model["review_gate"]["analysis_ready"] is False
    assert all(
        s["analysis_status"] == "GEOMETRIC_ONLY_NOT_DESIGNED" for s in model["column_segments"]
    )


def test_identical_floors_all_match():
    plan = _plan([_col(f"G{i}", x, y) for i, (x, y) in enumerate(GRID)])
    model = build_multistorey_building_candidate(GOOD, ground_plan=plan)
    checks = model["vertical_continuity_checks"]
    assert checks and all(
        c["status"] == "ALL_COLUMN_CENTRES_MATCH_WITHIN_TOLERANCE" for c in checks
    )
