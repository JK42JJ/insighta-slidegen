"""
insighta-slidegen CV microservice — FastAPI :8077

Endpoints:
    GET  /health              → {"status": "ok", "mode": "dev"|"prod"}
    POST /slides/generate     → {"job_id": "..."}
    GET  /slides/status       → {"job_id": ..., "status": ..., "progress_pct": ...}
    GET  /slides/result       → {"job_id": ..., "figures": [...], "keyframe_count": ...}

Mode gate (SLIDEGEN_MODE env var):
    dev  — vision API (Gemini etc.) hard-disabled. Only local CV runs.
           Returns placeholder figures so the TS pipeline can be tested end-to-end.
    prod — full pipeline including optional vision API fallback enabled.

Pipeline (per job) — canonical order:
    1. acquire.py        → download video + extract raw frames for requested sections
    2. frames.py         → Katna wide-net candidate extraction (~80 frames)
    3. captions.py       → load captions, BGE-M3 embed segments, detect topic-change points
    4. typing_select.py  → CLIP embed candidates + pgvector greedy dedup → ~12 selected frames
                           (aligned with caption topic-change points; definite keep = new image + new topic)
    5. figure_extract.py → YOLO layout detection + OCR (PaddleOCR / pix2tex) on selected ~12 only
    6. redraw.py         → vector redraw (300 DPI SVG/PDF) for chart/diagram/equation figures

Jobs run in a background thread pool; /slides/status polls the in-memory
job store until done or error.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

from acquire import download_frames
from frames import extract_candidates
from captions import detect_topic_changes
from typing_select import select_keyframes
from figure_extract import extract_figures as cv_extract_figures  # noqa: F401
from redraw import vector_redraw  # noqa: F401

app = FastAPI(title="insighta-slidegen-cv", version="0.1.0")

SLIDEGEN_MODE = os.environ.get("SLIDEGEN_MODE", "dev")

# In-memory job store — replace with Redis or Supabase for multi-worker prod.
_jobs: dict[str, dict[str, Any]] = {}


# ----------------------------------------------------------------
# Request / Response models
# ----------------------------------------------------------------

class Section(BaseModel):
    index: int
    from_sec: float
    to_sec: float


class GenerateRequest(BaseModel):
    youtube_video_id: str
    sections: list[Section]
    mode: str = "dev"


class GenerateResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: float
    error: str | None = None


class FigureResult(BaseModel):
    cv_figure_id: str
    kind: str
    png_url: str
    vector_pdf_url: str | None = None
    vector_svg_url: str | None = None
    caption: str | None = None
    timestamp_sec: int | None = None
    extraction_conf: float | None = None


class ResultResponse(BaseModel):
    job_id: str
    figures: list[FigureResult]
    keyframe_count: int


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Returns service health and active mode. Always 200 when server is up."""
    return {"status": "ok", "mode": SLIDEGEN_MODE}


@app.post("/slides/generate", response_model=GenerateResponse)
def slides_generate(req: GenerateRequest, background_tasks: BackgroundTasks) -> GenerateResponse:
    """
    Submit a CV extraction job.

    Rejects vision API usage when mode='dev' (hard gate — see module docstring).

    TODO: validate youtube_video_id (11 chars), enforce dev mode gate,
    enqueue _run_pipeline as a background task.
    """
    if req.mode == "prod" and SLIDEGEN_MODE == "dev":
        raise HTTPException(
            status_code=400,
            detail="Vision API disabled in dev mode (SLIDEGEN_MODE=dev)"
        )
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "progress_pct": 0.0, "figures": [], "keyframe_count": 0}
    background_tasks.add_task(_run_pipeline, job_id, req)
    return GenerateResponse(job_id=job_id)


@app.get("/slides/status", response_model=StatusResponse)
def slides_status(job_id: str) -> StatusResponse:
    """Return current job status. 404 if job_id unknown."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
    return StatusResponse(
        job_id=job_id,
        status=job["status"],
        progress_pct=job["progress_pct"],
        error=job.get("error"),
    )


@app.get("/slides/result", response_model=ResultResponse)
def slides_result(job_id: str) -> ResultResponse:
    """Return figures once job status='done'. 404 / 409 otherwise."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"job not done (status={job['status']})")
    return ResultResponse(
        job_id=job_id,
        figures=[FigureResult(**f) for f in job["figures"]],
        keyframe_count=job["keyframe_count"],
    )


# ----------------------------------------------------------------
# Background pipeline
# ----------------------------------------------------------------

def _run_pipeline(job_id: str, req: GenerateRequest) -> None:
    """
    Execute the full CV pipeline for a job.

    Steps (each updates _jobs[job_id]["progress_pct"]):
        15%  acquire.download_frames(youtube_video_id, sections)
        30%  frames.extract_candidates(video_path)          → ~80 FrameCandidate
        45%  captions.detect_topic_changes(youtube_video_id) → topic-change points (BGE-M3)
        65%  typing_select.select_keyframes(candidates, topic_points) → ~12 SelectedFrame
        80%  figure_extract.extract_figures(selected_frames, mode)   → layout + OCR
        95%  redraw.vector_redraw(figures)                  → 300 DPI vector output
        100% Done — write figures to _jobs[job_id]["figures"]

    On exception: set status='error', error=str(e).
    """
    try:
        _jobs[job_id]["status"] = "running"

        # Step 1: acquire (15%) — download video + extract JPEG frames
        sections = [s.model_dump() for s in req.sections]
        frames_dir = download_frames(req.youtube_video_id, sections)
        _jobs[job_id]["progress_pct"] = 15.0

        # Step 2: frames (30%) — Katna ~80 candidate frames
        video_path = frames_dir / "video.mp4"
        candidates = extract_candidates(video_path)
        _jobs[job_id]["progress_pct"] = 30.0

        # Step 3: captions (45%) — BGE-M3 topic-change detection
        topic_points = detect_topic_changes(req.youtube_video_id, req.mode)
        _jobs[job_id]["progress_pct"] = 45.0

        # Step 4: typing_select (65%) — CLIP + topic alignment → ~12 keyframes
        selected_frames = select_keyframes(candidates, topic_points, req.mode)
        _jobs[job_id]["progress_pct"] = 65.0

        # Step 5-6: TODO (remaining stages)
        # step 5 — figure_extract (yolo/ocr on selected)
        # step 6 — redraw (vector 300dpi)

        # Placeholder output
        _jobs[job_id].update({
            "status": "done",
            "progress_pct": 100.0,
            "figures": [],
            "keyframe_count": len(candidates),
        })

    except Exception as exc:
        _jobs[job_id].update({
            "status": "error",
            "error": str(exc),
            "progress_pct": 0.0,
        })
