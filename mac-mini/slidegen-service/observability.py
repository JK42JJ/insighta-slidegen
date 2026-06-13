"""Stage-artifact sink (PR — observability).

Pipeline evaluation needs the INTERMEDIATE products, not just the final deck.
This module dumps each CV stage's output to a per-video artifact tree so a
reviewer can inspect what each stage saw and produced:

    <artifacts_dir>/
    ├── 01-keyframes/   candidate count + selected frames (with WHY chosen)
    ├── 02-detect/      YOLO bbox per selected frame
    ├── 03-select/      Qwen routing decision per selected frame
    ├── 04-numerize/    struct-JSON (charts) / LaTeX (formulas) per figure
    └── MANIFEST.md     per-stage counts + what flowed to the next stage

The DECISIONS and DATA around each stage are recorded as JSON. In addition,
the 02-detect SOURCE crops (the exact frame regions Qwen numerized) are copied
into `02-detect/crops/` — without them the crops are ephemeral (frames working
dir) and the review cannot run the crop|struct|render 3-panel that decides CV
fidelity ("does Qwen's table/diagram match the actual frame?"). Crops persist
only when an artifacts_dir is set (measurement runs), never in a normal prod run.

Privacy (PUBLIC-repo rules): the real youtube_video_id is NEVER written —
the caller passes the anonymous index label (e.g. "V02"). Caption/transcript
text is NOT persisted here (review-only, no permanent subtitle store).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


class StageArtifactSink:
    """Writes per-stage JSON under <artifacts_dir>. No-op when dir is None."""

    def __init__(self, artifacts_dir: str | os.PathLike | None, index_label: str) -> None:
        self.root = Path(artifacts_dir) if artifacts_dir else None
        # Anonymous index only — never the real video id (PUBLIC-repo rule).
        self.index = index_label
        self._counts: dict[str, int] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_path(p: Any) -> str:
        """Frame/crop paths live under /tmp/slidegen-frames/<youtube_id>/… —
        the id segment is a PUBLIC-repo leak. Keep only the leaf filename."""
        return os.path.basename(str(p)) if p else ""

    def _write(self, stage_dir: str, name: str, payload: Any) -> None:
        if self.root is None:
            return
        d = self.root / stage_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2))

    def keyframes(self, candidate_count: int, selected: list) -> None:
        self._counts["candidates"] = candidate_count
        self._counts["selected"] = len(selected)
        self._write(
            "01-keyframes",
            "selection.json",
            {
                "candidate_count": candidate_count,
                "selected_count": len(selected),
                "selected": [
                    {
                        "timestamp_sec": s.candidate.timestamp_sec,
                        "frame_type": s.frame_type,
                        "selection_score": s.selection_score,
                        "is_topic_aligned": s.is_topic_aligned,
                        "summary_hint": s.summary_hint,
                        "contains_graph": s.contains_graph,
                        "contains_equation": s.contains_equation,
                        "frame_path": self._safe_path(s.candidate.path),
                    }
                    for s in selected
                ],
            },
        )

    def detect_and_numerize(self, figures: list) -> None:
        """figures carry both YOLO bbox (WHERE) and Qwen numerization (WHAT)."""
        boxed = [f for f in figures if getattr(f, "bbox", None)]
        charts = [f for f in figures if getattr(f, "struct", None)]
        formulas = [f for f in figures if getattr(f, "extracted_latex", None)]
        self._counts["bbox"] = len(boxed)
        self._counts["charts"] = len(charts)
        self._counts["formulas"] = len(formulas)
        self._write(
            "02-detect",
            "boxes.json",
            [
                {"figure_id": f.cv_figure_id, "kind": f.kind, "bbox": f.bbox,
                 "timestamp_sec": f.timestamp_sec, "crop_path": self._safe_path(f.png_path)}
                for f in figures
            ],
        )
        # Persist the SOURCE crops next to boxes.json so the review's
        # crop|struct|render 3-panel can verify CV fidelity. crop_path in
        # boxes.json already records each leaf filename — copy the file itself.
        self._persist_crops(figures)
        self._write(
            "04-numerize",
            "data.json",
            {
                "charts": [
                    {"figure_id": f.cv_figure_id, "kind": f.kind, "struct": f.struct,
                     "conf": f.extraction_conf, "verification_status": f.verification_status}
                    for f in charts
                ],
                "formulas": [
                    {"figure_id": f.cv_figure_id, "latex": f.extracted_latex,
                     "conf": f.extraction_conf, "verification_status": f.verification_status}
                    for f in formulas
                ],
            },
        )

    def _persist_crops(self, figures: list) -> None:
        """Copy each figure's source crop PNG into 02-detect/crops/ (leaf name
        only — the /tmp/<youtube_id>/ dir segment is a PUBLIC-repo leak and is
        stripped). No-op when no artifacts dir or a crop file is missing."""
        if self.root is None:
            return
        crops_dir = self.root / "02-detect" / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for f in figures:
            src = getattr(f, "png_path", None)
            if not src or not os.path.exists(src):
                continue
            try:
                shutil.copy(src, crops_dir / os.path.basename(str(src)))
                copied += 1
            except OSError:
                pass  # a single bad crop must not abort the dump
        self._counts["crops_persisted"] = copied

    def write_manifest(self) -> None:
        if self.root is None:
            return
        c = self._counts
        lines = [
            f"# CV pipeline artifacts — {self.index}",
            "",
            "Per-stage decisions+data as JSON; 02-detect also keeps the source crops.",
            "",
            f"- 01-keyframes: {c.get('candidates', '?')} candidates → "
            f"**{c.get('selected', '?')} selected** (selection.json — frame_type, score, why)",
            f"- 02-detect: **{c.get('bbox', '?')} YOLO boxes** across selected frames "
            f"(boxes.json) + **{c.get('crops_persisted', 0)} source crops** (crops/ — "
            f"for the crop|struct|render fidelity 3-panel)",
            f"- 04-numerize: **{c.get('charts', '?')} chart structs + {c.get('formulas', '?')} "
            f"formulas** (data.json) → flows to the bundle, then deck render",
            "",
            "Note: 03-select decisions are folded into 01-keyframes/selection.json "
            "(routing metadata per frame). 05-render PNGs + 06-deck are written "
            "by the orchestrator (TS side).",
        ]
        (self.root / "MANIFEST.md").write_text("\n".join(lines))
