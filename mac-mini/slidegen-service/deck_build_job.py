"""덱 빌드 ASYNC JOB (/slides/build) — book_json → .pptx (결정성, fail-closed).

insighta D build-call의 타깃. build_deck_service.js(규칙 매퍼, LLM auto-route 0)를
subprocess로 돌리고 진행률을 PROGRESS 라인으로 받아 job store에 반영. 결과는
.pptx 바이트(EC2↔MacMini 디스크 비공유 → path 반환 금지). /numerize/job·/slides/*
job 패턴 미러.

배포(app.py 2줄):
    import deck_build_job
    deck_build_job.register(app, StatusResponse)
env: SLIDEGEN_SKILL_DIR(deck/scripts) · SLIDEGEN_PY_DIR(py) · SLIDEGEN_DECK_OUT.
"""
import json
import os
import subprocess
import tempfile
import uuid

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

SKILL_DIR = os.environ.get("SLIDEGEN_SKILL_DIR", "/opt/slidegen/deck/scripts")
PY_DIR = os.environ.get("SLIDEGEN_PY_DIR", "/opt/slidegen/py")
OUT_DIR = os.environ.get("SLIDEGEN_DECK_OUT", "/opt/slidegen/decks")

_build_jobs: dict[str, dict] = {}


class DeckBuildRequest(BaseModel):
    book_json: dict
    figures: list | None = None


class DeckBuildResponse(BaseModel):
    job_id: str


def run_build(job_id: str, book_json: dict, figures) -> None:
    job = _build_jobs[job_id]
    try:
        job.update(status="running", stage="map", progress_pct=2.0)
        os.makedirs(OUT_DIR, exist_ok=True)
        out_path = os.path.join(OUT_DIR, f"{job_id}.pptx")
        with tempfile.TemporaryDirectory() as td:
            bp = os.path.join(td, "book.json")
            with open(bp, "w") as fh:
                json.dump(book_json, fh)
            argv = ["node", os.path.join(SKILL_DIR, "build_deck_service.js"), bp, out_path]
            if figures:
                fp = os.path.join(td, "figures.json")
                with open(fp, "w") as fh:
                    json.dump(figures, fh)
                argv.append(fp)
            env = {**os.environ, "SLIDEGEN_PY_DIR": PY_DIR}
            proc = subprocess.Popen(
                argv, cwd=SKILL_DIR, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for line in proc.stderr:                       # build_deck_service가 PROGRESS 방출
                if line.startswith("PROGRESS "):
                    _, pct, stage = line.strip().split(" ", 2)
                    job.update(status="running", progress_pct=float(pct), stage=stage)
            proc.wait(timeout=300)
            last = (proc.stdout.read().strip().splitlines() or [""])[-1]
            res = json.loads(last)
            if not res.get("ok"):
                raise RuntimeError(res.get("error", "build failed"))
        job.update(status="done", progress_pct=100.0, stage="done",
                   out=out_path, slides=res["slides"], figures=res["figures"])
    except Exception as e:  # fail-closed: 단계 귀속 + 메시지
        job.update(status="error", failure_stage=job.get("stage"), error=str(e)[:300])


def register(app, StatusResponse):
    @app.post("/slides/build", response_model=DeckBuildResponse)
    def slides_build(req: DeckBuildRequest, background_tasks: BackgroundTasks):
        job_id = uuid.uuid4().hex[:12]
        _build_jobs[job_id] = {"status": "queued", "progress_pct": 0.0,
                               "stage": "queued"}
        background_tasks.add_task(run_build, job_id, req.book_json, req.figures)
        return DeckBuildResponse(job_id=job_id)

    @app.get("/slides/build/status", response_model=StatusResponse)
    def slides_build_status(job_id: str):
        job = _build_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
        return StatusResponse(job_id=job_id, status=job["status"],
                              progress_pct=job["progress_pct"], error=job.get("error"),
                              stage=job.get("stage"), failure_stage=job.get("failure_stage"))

    @app.get("/slides/build/result")
    def slides_build_result(job_id: str):
        job = _build_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"job_id {job_id} not found")
        if job["status"] != "done":
            raise HTTPException(status_code=409, detail=f"job not done (status={job['status']})")
        return FileResponse(
            job["out"],
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=f"{job_id}.pptx",
        )
