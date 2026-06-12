"""
Figure extraction on the selected keyframes: YOLO crop → Qwen numerization.

This module operates ONLY on the keyframes produced by
typing_select.select_keyframes() — NOT on the full candidate set. It is
stage 5 of the ADR 0002/0003 pipeline:

    1. The frame's VLM routing flags (contains_graph / contains_equation,
       ADR 0001 — set upstream in typing_select) decide whether the frame
       enters the crop pipeline at all. Unflagged frames become plain
       `keyframe` entries (no detection, no model calls).
    2. DocLayout-YOLO (`YoloHttpClient.detect`, over-detect defaults —
       ADR 0002 D2, recall-first ADR 0003 D5) finds WHERE the regions are.
       The returned `class` is ADVISORY ONLY and never gates anything here
       (CONTRACT_model-endpoints §3.4).
    3. Each box is cropped with opencv (pixel bbox, clamped to the image
       bounds); the bbox is kept for provenance (slide_figures.bbox shape).
    4. Qwen3-VL decides WHAT each crop is (mode B `classify_crop`,
       CONTRACT §2.2): kind + struct-JSON for charts/diagrams/tables.
    5. Equation crops go to Qwen3-VL OCR (mode C `equation_ocr`) → LaTeX
       (ADR 0003 D3 — MVP equations are Qwen OCR; UniMERNet is deferred
       behind a measured quality gap).
    6. Low-confidence extractions are FLAGGED (`verification_status=
       'unverified'`), never silently embedded (ADR 0003 D3 / ADR 0004 G3).

Failures carry ADR 0004 §4 stage attribution via ModelEndpointError raised
by the injected clients: YOLO failures → stage `detect`, Qwen mode B/C
failures → stage `recognize`.

The crop PNG is a DATA SOURCE, never the artifact (ADR 0003 P2): downstream
the deck embeds only text, LaTeX renderings, and matplotlib-REGENERATED
charts (py/deck_tools/chart_regen.py) — raw frame pixels never reach the
deck. No DB writes happen in this module; persistence to slide_figures /
slide_keyframes is the orchestrator's job (PR-G).

Entry: extract_figures(selected_frames, yolo=..., vlm=...) → list[ExtractedFigure]
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2

from model_clients import VlmContractError
from typing_select import SelectedFrame
from vlm_router import _image_data_url as image_data_url

# Document layout detector (WHERE — region boxes) — ADR 0001/0002, served per
# CONTRACT_model-endpoints §3.
LAYOUT_MODEL = "doclayout-yolo"
# Equation OCR (region → LaTeX) — ADR 0003 D3: MVP equations = Qwen3-VL OCR
# (mode C). UniMERNet is deferred behind a measured quality gap (ADR 0004 §4
# `recognize`-stage evidence), superseding the ADR 0001 UniMERNet plan.
EQUATION_OCR_MODEL = "qwen3-vl"

# ADR 0004 G3: extraction_conf below this threshold is flagged for the
# distribution report (report-only — NOT a gate) and the figure is marked
# `unverified` so it is never silently embedded (ADR 0003 D3).
LOW_CONF_THRESHOLD = 0.7

# slide_figures.verification_status values used here ("verified" is human-set).
VERIFICATION_PENDING = "pending"
VERIFICATION_UNVERIFIED = "unverified"

# Mode-B kind that routes a crop to mode-C equation OCR. The kind authority is
# Qwen's mode-B decision — never YOLO's advisory class (ADR 0002 D2/D7).
EQUATION_KIND = "equation"
# Mode-B kinds that ARE deck figures (FigureRefSchema enum, slide-manifest.ts).
# The prompt also offers "text"/"photo" as VETO answers for detector
# over-detections (§3.4) — those crops are dropped, never shipped.
MODE_B_FIGURE_KINDS = frozenset({"chart", "diagram", "table", "equation", "screenshot"})
# Kind recorded for unflagged frames (no crop, keyframe row only).
KEYFRAME_KIND = "keyframe"

# ── Selection gate (fail-closed, PR review finding) ──────────────────────────
# ROOT CAUSE: Qwen hallucinates a chart/struct for NON-chart crops (handwriting,
# titles, logos, UI badges). The gate REJECTS a crop before it pollutes the
# bundle when ANY of: kind is a reject class, confidence below the floor, the
# chart struct contradicts its own insight, the crop is an over-large bbox, or
# two extraction calls disagree (self-consistency). Reject → label-only (never
# a garbage struct). "When unsure, reject" is the contract.
REJECT_KINDS = frozenset({"handwriting", "title", "decoration", "ui_badge", "text", "photo", "none"})
# Below this confidence a figure is rejected, not numerized (fail-closed).
GATE_CONF_FLOOR = 0.55
# A crop covering more than this fraction of the frame is likely a whole-board
# over-detection (formula[3]: the entire blackboard as one bbox) → reject.
MAX_CROP_AREA_FRAC = 0.85


def _chart_struct_consistent(struct: dict | None) -> tuple[bool, str]:
    """insight↔series sanity (PR review: 'uniform/constant' insight but a
    triangular series is a numerize hallucination). Returns (ok, reason)."""
    if not isinstance(struct, dict):
        return True, ""
    insight = str(struct.get("insight", "")).lower()
    ys: list[float] = []
    for ser in struct.get("series") or []:
        for p in ser.get("points") or []:
            v = p.get("y", p.get("value"))
            if isinstance(v, (int, float)):
                ys.append(float(v))
    flat_claim = any(k in insight for k in ("uniform", "constant", "균등", "flat", "동일"))
    if flat_claim and len(set(ys)) > 1:
        return False, f"insight='{insight[:30]}'(flat) but series varies {ys[:6]}"
    return True, ""

# ── Mode B/C prompt contents (PR-F scope per CONTRACT §7; wire shape is §2.2) ─
CROP_CLASSIFY_PROMPT = (
    "You classify ONE cropped region from a knowledge-video frame. The "
    "detector decided WHERE; you decide WHAT — and CRITICALLY, whether it is a "
    "real quantitative figure at all. Reply with ONLY JSON, no prose: "
    '{"kind": "chart"|"diagram"|"table"|"equation"  '
    '|"handwriting"|"title"|"decoration"|"ui_badge"|"text"|"photo"|"none", '
    '"struct": <for kind=chart: {"chart_type": "line"|"bar"|"scatter", '
    '"axes": {"x": "", "y": ""}, '
    '"series": [{"name": "", "points": [{"x": 0, "y": 0}]}], '
    '"insight": "one sentence"}; for kind=table: {"headers": [], "rows": [[]]}; '
    'otherwise {}>, "confidence": <float 0..1>}. '
    "REJECT RULES — return the reject kind with EMPTY struct, do NOT invent a "
    "chart: hand-drawn sketches/handwriting on a board → \"handwriting\"; a "
    "slide/section TITLE or heading text → \"title\"; a logo, icon, or "
    "ornamental graphic → \"decoration\"; a UI button/badge/chip → \"ui_badge\"; "
    "plain prose → \"text\"; a photo/screenshot of a scene → \"photo\"; nothing "
    "legible or not a figure → \"none\". A chart/table/equation kind REQUIRES "
    "actual axes/cells/symbols you can READ — if you are guessing the numbers, "
    "it is NOT a chart: choose a reject kind and low confidence. When unsure, "
    "REJECT. Never invent series or values that are not visibly present; the "
    "insight MUST match the data you read (do not say 'uniform' for a rising "
    "curve)."
)
EQUATION_OCR_PROMPT = (
    "Transcribe the mathematical content of this cropped image to LaTeX. "
    'Reply with ONLY JSON, no prose: {"latex": "<LaTeX, no surrounding $>", '
    '"confidence": <float 0..1>}. '
    "If the crop is NOT a self-contained equation (it is a title, a whole "
    "blackboard with mixed prose, or unreadable), set confidence below 0.5 and "
    "transcribe only the math you can actually read — never pad with the slide "
    "title or surrounding prose. Report low confidence instead of guessing "
    "unreadable symbols (transcribe a genuinely-handwritten '?' faithfully, but "
    "do not emit '?'/'@' as a stand-in for a letter you could not read)."
)

_CROP_ID_LEN = 16  # hex chars of the sha1 kept as cv_figure_id


@dataclass
class ExtractedFigure:
    """CV-processed figure ready for vector redraw + upload.

    Field shapes mirror slidegen.slide_figures columns (cv_figure_id, kind,
    timestamp_sec, extracted_latex, bbox, extraction_conf,
    verification_status) — persistence itself is out of scope here (PR-G).
    """
    cv_figure_id: str          # short hash of frame stem + timestamp + box index
    kind: str                  # "chart" | "diagram" | "equation" | "table" | "text" | "photo" | "keyframe"
    png_path: str              # local crop PNG path — a DATA SOURCE, never a deck asset (ADR 0003 P2)
    caption: str | None        # reserved for OCR caption text (not extracted in this stage)
    timestamp_sec: int
    extracted_latex: str | None  # mode-C Qwen OCR LaTeX for kind='equation' (ADR 0003 D3)
    bbox: dict | None            # clamped crop region {x,y,w,h} in source-frame pixels; None for whole-frame
    extraction_conf: float
    struct: dict | None = None   # mode-B struct-JSON for charts/diagrams/tables
    verification_status: str = VERIFICATION_PENDING  # 'unverified' iff conf < LOW_CONF_THRESHOLD


def extract_figures(
    selected_frames: list[SelectedFrame],
    *,
    yolo,
    vlm,
    out_dir: Path | str | None = None,
    self_consistency: bool = True,
) -> list[ExtractedFigure]:
    """
    YOLO-crop + Qwen-numerize the selected keyframes.

    Args:
        selected_frames: output of typing_select.select_keyframes().
        yolo: YoloHttpClient-like — `.detect(image_url) -> DetectResponse`.
        vlm:  VlmHttpClient-like — `.classify_crop(...)` (mode B) and
              `.equation_ocr(...)` (mode C). Both are INJECTED so tests run
              against in-process stubs (no env construction in this path —
              `from_env` gating stays the composition root's concern).
        out_dir: where crop PNGs are written (default: a fresh temp dir).

    Returns one ExtractedFigure per detected region of each flagged frame,
    plus one `keyframe` entry per unflagged frame. Raises ModelEndpointError
    (stage `detect` / `recognize`) on endpoint failure — attribution is
    preserved for ADR 0004 §4 stats. A per-crop CONTRACT failure (broken JSON
    after the re-ask) only skips that crop (logged), never the whole video.
    """
    crops_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="slidegen_crops_"))
    crops_dir.mkdir(parents=True, exist_ok=True)

    figures: list[ExtractedFigure] = []
    for frame in selected_frames:
        timestamp = int(frame.candidate.timestamp_sec)

        # Routing is the frame's VLM flags (ADR 0001) — unflagged frames skip
        # detection entirely and surface as keyframe rows only.
        if not (frame.contains_graph or frame.contains_equation):
            figures.append(
                ExtractedFigure(
                    cv_figure_id=_figure_id(frame.candidate.path, timestamp, -1),
                    kind=KEYFRAME_KIND,
                    png_path=str(frame.candidate.path),
                    caption=None,
                    timestamp_sec=timestamp,
                    extracted_latex=None,
                    bbox=None,
                    extraction_conf=frame.selection_score,
                )
            )
            continue

        image = cv2.imread(str(frame.candidate.path))
        if image is None:
            raise ValueError(f"unreadable frame image: {frame.candidate.path}")
        img_h, img_w = image.shape[:2]

        # WHERE: DocLayout-YOLO over-detect (stage `detect` on failure). Local
        # frames travel as data URLs, like the vlm_router http backend.
        detection = yolo.detect(image_data_url(frame.candidate.path))

        for box_index, box in enumerate(detection.boxes):
            # box.cls is ADVISORY ONLY (§3.4) — it is deliberately never read
            # for routing; Qwen's mode-B kind is the only WHAT authority.
            clamped = _clamp_bbox(box.bbox.x, box.bbox.y, box.bbox.w, box.bbox.h, img_w, img_h)
            if clamped is None:
                continue
            x, y, w, h = clamped
            # GATE #2 — over-large bbox (whole-board over-detection): reject
            # before numerize so a blackboard-as-one-box can't become a struct.
            if (w * h) / float(img_w * img_h) > MAX_CROP_AREA_FRAC:
                sys.stderr.write(
                    f"figure_extract: oversize crop rejected "
                    f"(t={timestamp}s box={box_index} area={(w * h) / (img_w * img_h):.2f})\n"
                )
                continue
            crop_path = crops_dir / f"{frame.candidate.path.stem}_crop{box_index}.png"
            cv2.imwrite(str(crop_path), image[y : y + h, x : x + w])
            crop_url = image_data_url(crop_path)

            # WHAT: mode B per-crop kind + struct (stage `recognize` on failure).
            # A CONTRACT failure (model emitted broken JSON even after the
            # single re-ask) is a per-CROP weakness, not a per-VIDEO failure:
            # skip the crop and keep extracting (flag-don't-kill — ADR 0003 D3
            # granularity; counts surface via the skip log). Endpoint/infra
            # errors (5xx, network) still raise — those ARE stage failures.
            def _drop(reason: str, _t: int = timestamp, _b: int = box_index) -> None:
                sys.stderr.write(f"figure_extract: gate reject (t={_t}s box={_b}): {reason}\n")

            try:
                classification = vlm.classify_crop(
                    crop_url, CROP_CLASSIFY_PROMPT, caption_slice=_caption_slice(frame)
                )
                kind = classification["kind"]

                # GATE #1 — reject class (Qwen's own veto: handwriting/title/
                # decoration/ui_badge/text/photo/none). Fail-closed root fix.
                if kind in REJECT_KINDS or kind not in MODE_B_FIGURE_KINDS:
                    _drop(f"reject kind={kind}")
                    continue

                # GATE #3 — self-consistency: a second classify must agree on
                # kind, else the crop is ambiguous → label-only (a↔@ drift).
                # Doubles the per-crop call; on by default in prod.
                if self_consistency:
                    second = vlm.classify_crop(
                        crop_url, CROP_CLASSIFY_PROMPT, caption_slice=_caption_slice(frame)
                    )
                    if second["kind"] != kind:
                        _drop(f"self-consistency: kind {kind} != {second['kind']}")
                        continue

                if kind == EQUATION_KIND:
                    # Mode C: Qwen OCR → LaTeX (ADR 0003 D3; stage `recognize`).
                    ocr = vlm.equation_ocr(crop_url, EQUATION_OCR_PROMPT)
                    latex, struct, conf = ocr["latex"], None, ocr["confidence"]
                else:
                    latex, struct, conf = (
                        None,
                        classification["struct"],
                        classification["confidence"],
                    )
            except VlmContractError as exc:
                sys.stderr.write(
                    f"figure_extract: crop contract error skipped "
                    f"(t={timestamp}s box={box_index}): {exc}\n"
                )
                continue

            # GATE #4 — confidence floor (fail-closed: low conf = reject, not
            # numerize). A genuine figure clears the floor; a hallucination on a
            # non-figure crop reports low confidence (the prompt asks for it).
            if conf is None or conf < GATE_CONF_FLOOR:
                _drop(f"low confidence {conf}")
                continue

            # GATE #5 — insight↔series consistency (chart structs only): the
            # numerize-hallucination check (triangle data under a 'uniform'
            # insight). Inconsistent → label-only, never a garbage struct.
            ok, why = _chart_struct_consistent(struct)
            if not ok:
                _drop(f"struct inconsistent: {why}")
                continue

            figures.append(
                ExtractedFigure(
                    cv_figure_id=_figure_id(frame.candidate.path, timestamp, box_index),
                    kind=kind,
                    png_path=str(crop_path),
                    caption=None,
                    timestamp_sec=timestamp,
                    extracted_latex=latex,
                    bbox={"x": x, "y": y, "w": w, "h": h},
                    extraction_conf=conf,
                    struct=struct,
                    verification_status=(
                        VERIFICATION_UNVERIFIED if conf < LOW_CONF_THRESHOLD
                        else VERIFICATION_PENDING
                    ),
                )
            )

    return figures


def _clamp_bbox(
    x: float, y: float, w: float, h: float, img_w: int, img_h: int
) -> tuple[int, int, int, int] | None:
    """Clamp a pixel bbox to the image bounds; None if nothing remains."""
    x0 = max(0, min(int(round(x)), img_w))
    y0 = max(0, min(int(round(y)), img_h))
    x1 = max(0, min(int(round(x + w)), img_w))
    y1 = max(0, min(int(round(y + h)), img_h))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1 - x0, y1 - y0


def _caption_slice(frame: SelectedFrame) -> str:
    """Mode-B companion text: the frame's [t_start, t_end] interval (ADR 0002
    D6 provenance) plus the router's summary hint. Raw caption text is not
    persisted or carried here (ADR 0003 D6) — interval + hint only."""
    interval = f"[{frame.candidate.t_start:.1f}, {frame.candidate.t_end:.1f}]"
    return f"{interval} {frame.summary_hint}".strip() if frame.summary_hint else interval


def _figure_id(frame_path: Path, timestamp_sec: int, box_index: int) -> str:
    """Stable short id from frame stem + timestamp + box index."""
    key = f"{frame_path.stem}:{timestamp_sec}:{box_index}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:_CROP_ID_LEN]
