import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import desktop_server as ds

ORIGIN = "http://127.0.0.1:8765"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a loopback URL, with disk state redirected into tmp_path and STATE restored."""
    monkeypatch.setattr(ds, "STATE_PATH", tmp_path / "workspace.json")
    monkeypatch.setattr(ds, "UPLOAD_DIR", tmp_path)
    saved = {k: copy.copy(v) for k, v in ds.STATE.items()}
    try:
        yield TestClient(ds.app, base_url=ORIGIN)
    finally:
        ds.STATE.clear()
        ds.STATE.update(saved)


PROJECT = {"name": "demo", "location": "Luxor"}


def test_same_origin_write_is_allowed(client):
    r = client.put("/api/project", json=PROJECT, headers={"origin": ORIGIN})
    assert r.status_code == 200 and ds.STATE["project"]["name"] == "demo"


def test_write_without_origin_is_allowed_for_non_browser_clients(client):
    assert client.put("/api/project", json=PROJECT).status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "http://127.0.0.1:9999", "null"])
def test_cross_origin_writes_are_rejected(client, origin):
    r = client.put("/api/project", json=PROJECT, headers={"origin": origin})
    assert r.status_code == 403
    assert not ds.STATE["project"].get("name") == "demo"


def test_cross_site_fetch_metadata_is_rejected(client):
    r = client.put("/api/project", json=PROJECT, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403


def test_dns_rebinding_host_is_rejected_even_for_reads(client):
    assert client.get("/api/health", headers={"host": "evil.example:8765"}).status_code == 403
    assert client.get("/api/health").status_code == 200


def test_cross_origin_cannot_delete_an_uploaded_plan(client, sample_dxf_bytes):
    up = client.post(
        "/api/plans/ground",
        files={"file": ("ground.dxf", sample_dxf_bytes, "application/dxf")},
        data={"units": "mm", "confirm_layer_standard": "true"},
        headers={"origin": ORIGIN},
    )
    assert up.status_code == 200, up.text
    assert "ground" in ds.STATE["plan_candidates"]
    assert (Path(ds.STATE["plan_uploads"]["ground"]["path"])).is_file()

    evil = client.delete("/api/plans/ground", headers={"origin": "https://evil.example"})
    assert evil.status_code == 403 and "ground" in ds.STATE["plan_candidates"]

    ok = client.delete("/api/plans/ground", headers={"origin": ORIGIN})
    assert ok.status_code == 200 and "ground" not in ds.STATE["plan_candidates"]


def test_upload_validation(client, sample_dxf_bytes):
    files = {"file": ("ground.dxf", sample_dxf_bytes, "application/dxf")}
    assert (
        client.post("/api/plans/ground", files=files, data={"units": "mm"}).status_code == 400
    )  # not confirmed
    bad_ext = {"file": ("ground.txt", sample_dxf_bytes, "text/plain")}
    assert (
        client.post(
            "/api/plans/ground",
            files=bad_ext,
            data={"units": "mm", "confirm_layer_standard": "true"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/plans/attic", files=files, data={"units": "mm", "confirm_layer_standard": "true"}
        ).status_code
        == 404
    )


def test_state_survives_concurrent_writes(client):
    from concurrent.futures import ThreadPoolExecutor

    def save(i):
        return client.put("/api/project", json={"name": f"p{i}", "location": "L"}).status_code

    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(save, range(24)))
    assert set(codes) == {200}
    import json

    saved = json.loads(ds.STATE_PATH.read_text(encoding="utf-8"))  # never a half-written file
    assert saved["project"]["name"].startswith("p")


def test_local_workspace_is_gitignored():
    """Uploaded drawings, project data and chat history live here and must never be committed."""
    lines = {l.strip() for l in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert ".structural_studio_local/" in lines
