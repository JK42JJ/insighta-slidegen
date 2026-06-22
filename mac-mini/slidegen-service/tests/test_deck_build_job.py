"""Deck build job (/slides/build) — job flow + result-bytes + error paths.

book_json → .pptx via build_deck_service.js (deterministic rule mapper). The
node subprocess is monkeypatched out here (run_build replaced), so these tests
pin only the FastAPI job contract — no node, no pptxgenjs, no network.
TestClient runs BackgroundTasks synchronously, so one poll after POST is final.
"""

from fastapi.testclient import TestClient

import deck_build_job
from app import app


def test_build_job_completes_and_returns_bytes(monkeypatch, tmp_path):
    out = tmp_path / "deck.pptx"
    out.write_bytes(b"PK\x03\x04 fake pptx bytes")  # FileResponse needs a real file

    def fake_run(job_id, book_json, figures):
        deck_build_job._build_jobs[job_id].update(
            status="done", progress_pct=100.0, stage="done",
            out=str(out), slides=12, figures={"tables": 0, "diagrams": 0},
        )

    monkeypatch.setattr(deck_build_job, "run_build", fake_run)  # late-bound by route
    client = TestClient(app)

    resp = client.post("/slides/build", json={"book_json": {"chapters": []}})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = client.get(f"/slides/build/status?job_id={job_id}").json()
    assert status["status"] == "done"
    assert status["progress_pct"] == 100.0

    result = client.get(f"/slides/build/result?job_id={job_id}")
    assert result.status_code == 200
    assert result.content.startswith(b"PK")  # .pptx (zip) bytes returned


def test_build_result_409_until_done(monkeypatch):
    monkeypatch.setattr(deck_build_job, "run_build", lambda *a, **k: None)  # never finishes
    client = TestClient(app)
    job_id = client.post("/slides/build", json={"book_json": {"chapters": []}}).json()["job_id"]
    assert client.get(f"/slides/build/result?job_id={job_id}").status_code == 409


def test_build_unknown_job_id_404():
    client = TestClient(app)
    assert client.get("/slides/build/status?job_id=nope").status_code == 404
    assert client.get("/slides/build/result?job_id=nope").status_code == 404
