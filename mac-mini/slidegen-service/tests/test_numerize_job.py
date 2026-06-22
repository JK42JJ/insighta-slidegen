"""Async ⑤ numerize job (/numerize/job) — job flow, result shape, failure attribution.

The sync /numerize can't fit the insighta 60s client timeout (single ts ≈ 148s;
cv_extract Qwen VLM dominates), so the async job lets the client poll instead.
These tests pin the job contract WITHOUT network:
  ① empty pipeline → job completes (done, 100%), result figures=[] (fail-closed)
  ② an exception in a stage → status=error with failure_stage attributed
  ③ unknown job_id → 404 on status and result

TestClient runs BackgroundTasks synchronously, so one status poll after the POST
sees the final job state. Synthetic ids only (PUBLIC repo rule); the pipeline
funcs are monkeypatched and dev-mode uses the in-service mock clients (no network).
"""

from fastapi.testclient import TestClient

import numerize_job
from app import app

SYNTH_VIDEO_ID = "synthvid001"


def test_job_completes_empty_pipeline(monkeypatch, tmp_path):
    # No real download/scan: empty candidates → selected=[] → cv_extract([]) → [].
    monkeypatch.setattr(numerize_job, "download_frames", lambda *a, **k: tmp_path)
    monkeypatch.setattr(numerize_job, "extract_candidates", lambda *a, **k: [])
    monkeypatch.setattr(numerize_job, "preselect_candidates", lambda c, **k: c)
    client = TestClient(app)

    resp = client.post(
        "/numerize/job", json={"video_id": SYNTH_VIDEO_ID, "ts": [1], "mode": "dev"}
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = client.get(f"/numerize/job/status?job_id={job_id}").json()
    assert status["status"] == "done"
    assert status["progress_pct"] == 100.0

    result = client.get(f"/numerize/job/result?job_id={job_id}")
    assert result.status_code == 200
    assert result.json()["figures"] == []  # fail-closed: no candidates, job still done


def test_job_failure_stage_attributed(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(numerize_job, "download_frames", _boom)
    client = TestClient(app)

    job_id = client.post(
        "/numerize/job", json={"video_id": SYNTH_VIDEO_ID, "ts": [1], "mode": "dev"}
    ).json()["job_id"]

    status = client.get(f"/numerize/job/status?job_id={job_id}").json()
    assert status["status"] == "error"
    assert status["failure_stage"] == "acquire"  # died before leaving the acquire stage

    # result is 409 until done (never, here)
    assert client.get(f"/numerize/job/result?job_id={job_id}").status_code == 409


def test_unknown_job_id_404():
    client = TestClient(app)
    assert client.get("/numerize/job/status?job_id=nope").status_code == 404
    assert client.get("/numerize/job/result?job_id=nope").status_code == 404
