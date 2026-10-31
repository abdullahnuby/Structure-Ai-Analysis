"""DXF candidate -> floor design input, and the plan-to-design endpoint."""

import copy

import pytest
from fastapi.testclient import TestClient

import desktop_server as ds
from conftest import _rect
from structural_engine.design import run_design
from structural_engine.design.from_plan import columns_and_walls, floor_spec_from_candidate
from structural_engine.design.params import P

ORIGIN = "http://127.0.0.1:8765"
LOADS = dict(finishes_kN_m2=1.5, live_kN_m2=2.0, storey_height_m=3.2, floors=3)


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


def plan_dxf(make_dxf, double_wall=False):
    def fill(doc, msp):
        for n in ("column 30x50", "wall 25 cm"):
            doc.layers.add(n)
        for x in (0, 5000, 10000):
            for y in (0, 4500):
                msp.add_lwpolyline(
                    _rect(x - 150, y - 250, 300, 500),
                    close=True,
                    dxfattribs={"layer": "column 30x50"},
                )
        msp.add_line((0, 0), (10000, 0), dxfattribs={"layer": "wall 25 cm"})
        if double_wall:
            msp.add_line((0, 250), (10000, 250), dxfattribs={"layer": "wall 25 cm"})
        msp.add_lwpolyline(
            _rect(-100, 2000, 200, 200), close=True, dxfattribs={"layer": "wall 25 cm"}
        )

    return make_dxf(fill)


def candidate(raw):
    return ds._floor_candidate("ground", raw, "g.dxf", "mm", contract_confirmed=True)[2]


def test_columns_come_from_the_geometry_in_metres_and_mm(make_dxf):
    got = columns_and_walls(candidate(plan_dxf(make_dxf)))
    assert len(got["columns"]) == 6
    c = got["columns"][0]
    assert (c["x"], c["y"], c["b_mm"], c["h_mm"]) == (
        pytest.approx(0.0),
        pytest.approx(0.0),
        300.0,
        500.0,
    )
    assert [round(c["x"]) for c in got["columns"][:3]] == [0, 5, 10]


def test_wall_line_becomes_a_loaded_wall_and_stubby_entity_is_reported(make_dxf):
    got = columns_and_walls(candidate(plan_dxf(make_dxf)))
    assert len(got["walls"]) == 1
    w = got["walls"][0]
    assert (w["x0"], w["x1"], w["thickness_mm"]) == (pytest.approx(0.0), pytest.approx(10.0), 250.0)
    assert any("not elongated" in n for n in got["notes"])


def test_double_line_wall_is_not_loaded_twice(make_dxf):
    got = columns_and_walls(candidate(plan_dxf(make_dxf, double_wall=True)))
    assert len(got["walls"]) == 1
    assert any("not loaded twice" in n for n in got["notes"])


def test_candidate_runs_through_the_whole_floor_design(make_dxf):
    spec = floor_spec_from_candidate(candidate(plan_dxf(make_dxf)), **LOADS)
    r = run_design(copy.deepcopy(spec))
    assert r["status"] == "OK", r["failures"]
    assert len(r["columns"]) == 6 and len(r["slabs"]) == 2
    assert abs(r["equilibrium"]["difference_pct"]) < 1e-9
    assert any("not elongated" in w for w in r["warnings"])  # plan notes reach the report


def test_a_plan_without_columns_is_refused(make_dxf):
    raw = make_dxf(
        lambda doc, msp: (
            doc.layers.add("wall 25 cm"),
            msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "wall 25 cm"}),
        )
    )
    with pytest.raises(ValueError, match="fewer than two"):
        floor_spec_from_candidate(candidate(raw), **LOADS)


# ---- endpoint -----------------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "STATE_PATH", tmp_path / "workspace.json")
    monkeypatch.setattr(ds, "UPLOAD_DIR", tmp_path)
    saved = {k: copy.copy(v) for k, v in ds.STATE.items()}
    try:
        yield TestClient(ds.app, base_url=ORIGIN)
    finally:
        ds.STATE.clear()
        ds.STATE.update(saved)


def test_endpoint_designs_the_uploaded_plan(client, make_dxf):
    body = dict(floor="ground", **LOADS, report=True)
    assert (
        client.post(
            "/api/design/floor-from-plan", json=body, headers={"origin": ORIGIN}
        ).status_code
        == 400
    )  # nothing uploaded
    up = client.post(
        "/api/plans/ground",
        files={"file": ("g.dxf", plan_dxf(make_dxf), "application/dxf")},
        data={"units": "mm", "confirm_layer_standard": "true"},
        headers={"origin": ORIGIN},
    )
    assert up.status_code == 200, up.text
    r = client.post("/api/design/floor-from-plan", json=body, headers={"origin": ORIGIN})
    assert r.status_code == 200, r.text
    data = r.json()
    assert (
        data["status"] == "OK"
        and len(data["columns"]) == 6
        and "UNVERIFIED" in data["report_markdown"]
    )
    assert (
        client.post(
            "/api/design/floor-from-plan",
            json={**body, "live_kN_m2": -1},
            headers={"origin": ORIGIN},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/design/floor-from-plan", json=body, headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
