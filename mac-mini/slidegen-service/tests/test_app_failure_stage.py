"""PR-H2: ADR 0004 failure-stage attribution on the CV service job store.

The polling client (src/cv/cv-client.ts) reads `failure_stage` off
GET /slides/status to attribute a failed run; these tests pin:
  ① a plain exception inherits the pipeline-step fallback stage
  ② an exception carrying its own .stage (ModelEndpointError) WINS over the
    fallback, with the "recognize" → "numerize" DDL alias applied
  ③ off-domain stage values degrade to None (manual attribution)

TestClient runs BackgroundTasks synchronously, so one status poll after the
POST sees the final job state. Only the acquire boundary is faked — synthetic
ids only (PUBLIC repo rule).
"""

from fastapi.testclient import TestClient

import app as app_module
from app import _normalize_failure_stage, app
from model_clients import ModelEndpointError

SYNTH_VIDEO_ID = "synthvid001"


def _submit_and_poll(client: TestClient) -> dict:
    response = client.post(
        "/slides/generate",
        json={"youtube_video_id": SYNTH_VIDEO_ID, "sections": [], "mode": "dev"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    status = client.get(f"/slides/status?job_id={job_id}")
    assert status.status_code == 200
    return status.json()


def test_plain_exception_gets_step_fallback_stage(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(app_module, "download_frames", _boom)
    body = _submit_and_poll(TestClient(app))
    assert body["status"] == "error"
    assert body["failure_stage"] == "acquire"


def test_model_endpoint_error_stage_wins_with_ddl_alias(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise ModelEndpointError("qwen contract violation", stage="recognize")

    # Raised from the acquire step on purpose: the exception's own stage
    # ("recognize" → "numerize") must beat the step fallback ("acquire").
    monkeypatch.setattr(app_module, "download_frames", _boom)
    body = _submit_and_poll(TestClient(app))
    assert body["status"] == "error"
    assert body["failure_stage"] == "numerize"


def test_normalize_degrades_off_domain_stage_to_none():
    exc = ModelEndpointError("weird", stage="not-a-stage")
    assert _normalize_failure_stage(exc, None) is None
    assert _normalize_failure_stage(RuntimeError("x"), "keyframe") == "keyframe"
    assert _normalize_failure_stage(RuntimeError("x"), None) is None
