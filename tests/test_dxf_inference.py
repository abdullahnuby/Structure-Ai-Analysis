import pytest

from structural_engine.dxf_structural_inference import (
    analyze_dxf_structure,
    parse_architectural_layer,
    validate_architectural_layer_geometry,
)

# ---- layer-name parsing: every dimension is converted with its own unit -------------------------


@pytest.mark.parametrize(
    "layer, width, depth, assumed",
    [
        ("column 600x300mm", 60.0, 30.0, False),  # trailing unit applies to both sides
        ("column 60x30cm", 60.0, 30.0, False),
        ("column 60cm x 300mm", 60.0, 30.0, False),  # mixed units: each side on its own
        ("column 600mm x 30cm", 60.0, 30.0, False),
        ("beam 25x60 cm", 25.0, 60.0, False),
        ("column 60x30", 60.0, 30.0, True),  # no unit: cm assumed AND flagged
    ],
)
def test_pair_dimensions_and_units(layer, width, depth, assumed):
    spec = parse_architectural_layer(layer)
    assert spec["dimensions_cm"] == {"width": width, "depth": depth}
    assert spec["unit_assumed"] is assumed
    if assumed:
        assert "UNIT_ASSUMED" in spec["dimension_parse_status"]
    else:
        assert spec["dimension_parse_status"] == "PARSED_NEEDS_CONFIRMATION"


def test_single_dimension_and_roles():
    assert parse_architectural_layer("wall 250 mm")["dimensions_cm"] == {"thickness": 25.0}
    assert parse_architectural_layer("slab 12 cm")["dimensions_cm"] == {"thickness": 12.0}
    assert parse_architectural_layer("محور A")["parsed_role"] == "grid_axis"
    assert parse_architectural_layer("random")["parsed_role"] == "unknown"
    assert parse_architectural_layer("column")["dimension_parse_status"] == "MISSING_SECTION_PAIR"


# ---- geometry: blocks, circles and polylines give a footprint; loose lines are flagged ----------


def _by_layer(analysis, layer):
    return [e for e in analysis["entities"] if e["layer"] == layer]


def test_footprints_from_polyline_block_and_circle(sample_dxf_bytes):
    a = analyze_dxf_structure(sample_dxf_bytes, "sample.dxf")

    poly = _by_layer(a, "column 60x30cm")[0]
    assert poly["geometry_raw"]["source"] == "vertices" and poly["geometry_raw"]["closed"]
    assert poly["bbox_raw"]["max_x"] - poly["bbox_raw"]["min_x"] == pytest.approx(600)

    block = _by_layer(a, "column 40x40")[0]
    assert block["entity_type"] == "INSERT"
    assert block["geometry_raw"]["source"] == "entity_bbox"
    assert block["bbox_raw"]["min_x"] == pytest.approx(2000)
    assert block["bbox_raw"]["max_x"] - block["bbox_raw"]["min_x"] == pytest.approx(400)

    circle = _by_layer(a, "column 50x50")[0]
    assert circle["bbox_raw"]["max_x"] - circle["bbox_raw"]["min_x"] == pytest.approx(500)


def test_loose_lines_are_reported_not_silently_trusted(sample_dxf_bytes):
    a = analyze_dxf_structure(sample_dxf_bytes, "sample.dxf")
    assert any("LINE" in w and "2" in w for w in a["warnings"])
    line = _by_layer(a, "column 30x30")[0]
    poly = _by_layer(a, "column 60x30cm")[0]
    assert "open_line_fragment_not_grouped" in line["evidence"]
    assert line["confidence"] < poly["confidence"]


def test_confidence_reflects_evidence_not_a_constant(sample_dxf_bytes):
    a = analyze_dxf_structure(sample_dxf_bytes, "sample.dxf")
    conf = {e["layer"]: e["confidence"] for e in a["entities"]}
    assert conf["misc"] == pytest.approx(0.15)
    assert conf["column 60x30cm"] > conf["column 40x40"] > conf["column 30x30"] > conf["misc"]
    assert max(conf.values()) <= 0.9  # a layer name alone never reaches certainty


def test_layer_size_check_matches_real_footprints(sample_dxf_bytes):
    a = analyze_dxf_structure(sample_dxf_bytes, "sample.dxf")
    res = validate_architectural_layer_geometry(
        a, metres_per_drawing_unit=0.001, units_confirmed=True, layer_dimensions_confirmed=True
    )
    status = {r["layer"]: r["status"] for r in res["records"]}
    assert status["column 60x30cm"] == "MATCH"
    assert status["column 40x40"] == "MATCH"
    assert status["column 50x50"] == "MATCH"
    # the two loose lines have no footprint, so they cannot match 30x30
    assert res["mismatches"] == 2 and res["status"] == "MISMATCH_REVIEW"


def test_wrong_unit_scale_is_caught(sample_dxf_bytes):
    a = analyze_dxf_structure(sample_dxf_bytes, "sample.dxf")
    res = validate_architectural_layer_geometry(
        a, metres_per_drawing_unit=0.01, units_confirmed=True, layer_dimensions_confirmed=True
    )
    assert res["mismatches"] >= 3


def test_empty_and_invalid_dxf_rejected():
    with pytest.raises(ValueError):
        analyze_dxf_structure(b"")
    with pytest.raises(ValueError):
        analyze_dxf_structure(b"this is not a dxf file")
