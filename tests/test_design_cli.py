"""CLI, parameter overrides and the /api/design endpoint."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import desktop_server as ds
import run_design
from structural_engine.design import run_design as engine_run
from structural_engine.design.params import P

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((REPO / "examples" / "design").glob("*.json"))
ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def _reset_params():
    yield
    P.reset()


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_runs_and_writes_json_and_markdown(path, tmp_path, capsys):
    code = run_design.main([str(path), "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0 and "UNVERIFIED" in out
    stems = {p.stem for p in tmp_path.iterdir()}
    assert len(stems) == 1
    md = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert "UNVERIFIED" in md and "NOT FOR CONSTRUCTION" in md.upper()
    assert json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))["status"] == "OK"


def test_cli_exit_codes(tmp_path):
    assert len(EXAMPLES) == 3
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_design.main([str(bad), "--out", str(tmp_path)]) == 2
    assert run_design.main([str(tmp_path / "missing.json"), "--out", str(tmp_path)]) == 2
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"type": "teapot"}), encoding="utf-8")
    assert run_design.main([str(wrong), "--out", str(tmp_path)]) == 2
    failing = tmp_path / "fail.json"
    failing.write_text(
        json.dumps(
            {
                "type": "column",
                "name": "X",
                "b_mm": 250,
                "h_mm": 250,
                "fcu_MPa": 25,
                "Pu_kN": 2500,
                "Mux_kNm": 50,
            }
        ),
        encoding="utf-8",
    )
    assert run_design.main([str(failing), "--out", str(tmp_path)]) == 1


def test_cli_runs_as_a_script(tmp_path):
    r = subprocess.run(
        [sys.executable, "run_design.py", str(EXAMPLES[0]), "--out", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr


# ---- parameters ---------------------------------------------------------------------------------
def test_defaults_are_all_unverified_and_counted():
    assert set(P.unverified()) == {d["name"] for d in P.describe()}
    assert engine_run(json.loads(EXAMPLES[0].read_text(encoding="utf-8")))[
        "unverified_parameters"
    ] == len(P.unverified())


def test_set_and_reset_and_unknown_key():
    base = P.gamma_c
    P.set("gamma_c", 1.6)
    assert P.gamma_c == 1.6
    P.reset()
    assert P.gamma_c == base
    with pytest.raises(KeyError):
        P.set("not_a_parameter", 1)
    with pytest.raises(AttributeError):
        P.not_a_parameter


def test_override_file_and_verified_marking(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"gamma_c": 1.55, "_verified": ["gamma_c"]}), encoding="utf-8")
    monkeypatch.setenv("STRUCTURAL_STUDIO_PARAMS", str(f))
    P.reset()
    assert P.gamma_c == 1.55 and "gamma_c" not in P.unverified()
    assert next(d for d in P.describe() if d["name"] == "gamma_c")["verified"] is True
    f.write_text(json.dumps({"gamma_x": 1}), encoding="utf-8")
    with pytest.raises(KeyError):
        P.reset()
    monkeypatch.delenv("STRUCTURAL_STUDIO_PARAMS")
    P.reset()
    assert P.gamma_c == 1.5


# ---- endpoint -----------------------------------------------------------------------------------
@pytest.fixture
def client():
    return TestClient(ds.app, base_url=ORIGIN)


def test_endpoint_designs_and_can_include_the_report(client):
    spec = json.loads(EXAMPLES[0].read_text(encoding="utf-8"))
    r = client.post("/api/design", json=spec, headers={"origin": ORIGIN})
    assert r.status_code == 200 and r.json()["status"] == "OK" and "report_markdown" not in r.json()
    r2 = client.post("/api/design?report=true", json=spec, headers={"origin": ORIGIN})
    assert "UNVERIFIED" in r2.json()["report_markdown"]


def test_endpoint_rejects_bad_input_and_cross_origin(client):
    assert client.post("/api/design", json={"type": "teapot"}).status_code == 422
    assert (
        client.post(
            "/api/design", json={"type": "column", "b_mm": -1, "h_mm": 300, "Pu_kN": 100}
        ).status_code
        == 422
    )
    spec = json.loads(EXAMPLES[0].read_text(encoding="utf-8"))
    assert (
        client.post(
            "/api/design", json=spec, headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
