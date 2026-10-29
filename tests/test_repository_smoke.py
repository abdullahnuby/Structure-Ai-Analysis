from pathlib import Path
import json
from structural_engine.dxf_structural_inference import parse_architectural_layer
from structural_engine.building_stack import validate_building_stack_config


def test_parse_layer_dimensions():
    assert parse_architectural_layer("column 60x30")["dimensions_cm"] == {
        "width": 60.0,
        "depth": 30.0,
    }
    assert parse_architectural_layer("wall 25 cm")["parsed_role"] == "wall"


def test_missing_inputs_block_stack():
    r = validate_building_stack_config(
        {"above_ground_story_count": 4, "ground_story_height_m": 4.2},
        has_ground_plan=True,
        has_typical_plan=False,
        has_basement_plan=False,
        has_roof_plan=False,
    )
    assert not r["valid"]
    assert any("مسقط" in x for x in r["errors"])
