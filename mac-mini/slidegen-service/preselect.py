"""
preselect.py — cheap content-box prefilter BEFORE the VLM router (select-before-extract).

Repo port of the v3 `[S]` figure front-end (docs/design/pipeline.md §5/§6),
scoped to the CONTENT-BOX gate only. It runs the EXISTING DocLayout-YOLO detect
client over the ~60 `frames.extract_candidates()` candidates and drops the ones
with NO real slide content, so the (expensive) VLM router (typing_select) runs
on fewer frames. This sits between frames (stage `keyframe`) and typing_select.

A frame is KEPT iff it carries a real slide region — ANY of:
  * a SUBSTANTIAL text/eq/table box (>= MIN_TEXT_AREA_FRAC of the frame), OR
  * a HIGH-confidence figure (diagram >= FIGURE_CONF_KEEP) [chart/diagram/portrait], OR
  * a bounded frame-dominating diagram with >= 2 content boxes [a genuine
    low-confidence diagram slide].
Otherwise (empty / transition card / a lecturer the detector labels a low-conf
"figure" with no other content) → DROP.

DocLayout-YOLO has NO person class, so a lecturer is just a low-confidence
"figure" box; the content-box gate therefore drops a lecturer-ONLY frame (no
real content) while KEEPING a composited lecture frame (lecturer + on-screen
text passes the substantial-text test). The COCO person sub-gate of the v3 [S]
is intentionally OMITTED here — this service has no person detector, and the
person-vs-slide fine call is the downstream VLM router's job (typing_select
`is_slide`). Keeping the composited-lecture content is the safe default (it
matches the v3 'lecture' mode; the person-gate escape was the only thing
'mode'/content_type toggled, so without a person detector there is no mode).

The box `cls` is ADVISORY (CONTRACT §3.4) — used ONLY to bucket a box as
text/eq/table/diagram for the cheap content signal, never to decide WHAT a
figure is (that stays Qwen's mode-B authority in figure_extract). Section /
caption text never reaches here (ADR 0002 D5 — selection text is a hint, never
a keep/drop gate). Recall-first: a detect failure KEEPS the frame (the VLM
router still vets it); a gate that emptied the whole set is ignored by the
caller (app.py) so the pipeline is never starved.

Entry: preselect_candidates(candidates, *, yolo) -> list[FrameCandidate]
"""

from __future__ import annotations

import sys

from frames import FrameCandidate
from vlm_router import _image_data_url as image_data_url

# DocStructBench class -> content kind (CP#18; identical to the v1/v3 [S] map so
# the repo gate sees the same kinds). "abandon" = chrome/noise -> not content.
KIND_MAP = {
    "figure": "diagram",
    "table": "table",
    "isolate_formula": "equation",
    "title": "text",
    "plain text": "text",
    "figure_caption": "text",
    "table_caption": "text",
    "formula_caption": "text",
}
DROP_CLASSES = frozenset({"abandon"})
TEXTUAL_KINDS = frozenset({"equation", "table", "text"})
# figure-bearing kinds for frame RANKING (numerize select): YOLO advisory boxes
# whose _kind() is a figure (table/diagram/equation), NOT plain text/title. Used to
# rank in-window frames by figure content so numerize picks figure frames, not the
# chronological first-N (which were section-intro text/title slides → kind=text → 0).
FIGURE_KINDS = frozenset({"diagram", "table", "equation"})

# A figure at/above this confidence is a trusted real slide region (chart /
# diagram / portrait) — distinguishes a real figure slide from a low-confidence
# lecturer "figure".
FIGURE_CONF_KEEP = 0.80
# A text/eq/table box must cover at least this fraction of the frame to count as
# real content (rejects the tiny edge-caption sliver a lecturer-dominant frame
# shows; a single genuine slide line typically spans > 2%).
MIN_TEXT_AREA_FRAC = 0.02
# Large-figure rescue: a bounded, frame-dominating diagram (ANY confidence) plus
# >= 2 content boxes is a genuine low-confidence diagram slide, not a lecturer.
# Bounded to [MIN, MAX] so a near-full-frame box (the lecturer/scene) is NOT
# rescued (keeps the lecturer defence intact).
LARGE_FIGURE_MIN_FRAC = 0.20
LARGE_FIGURE_MAX_FRAC = 0.85
MIN_CONTENT_BOXES_FOR_RESCUE = 2


def _kind(cls: str) -> str:
    """Map an advisory DocLayout-YOLO class to a content kind ('drop' = chrome)."""
    if cls in DROP_CLASSES:
        return "drop"
    return KIND_MAP.get(cls, "other")


def _content_boxes(boxes) -> list[tuple[str, float, float]]:
    """(kind, pixel area, score) for each non-'drop' box."""
    out: list[tuple[str, float, float]] = []
    for b in boxes:
        kind = _kind(b.cls)
        if kind == "drop":
            continue
        out.append((kind, float(b.bbox.w) * float(b.bbox.h), float(b.score)))
    return out


def _has_substantial_text(content: list[tuple[str, float, float]], frame_area: float) -> bool:
    min_area = MIN_TEXT_AREA_FRAC * frame_area
    return any(kind in TEXTUAL_KINDS and area >= min_area for kind, area, _ in content)


def _has_strong_figure(content: list[tuple[str, float, float]]) -> bool:
    return any(kind == "diagram" and score >= FIGURE_CONF_KEEP for kind, _, score in content)


def _has_large_diagram(content: list[tuple[str, float, float]], frame_area: float) -> bool:
    lo, hi = LARGE_FIGURE_MIN_FRAC * frame_area, LARGE_FIGURE_MAX_FRAC * frame_area
    return any(kind == "diagram" and lo <= area <= hi for kind, area, _ in content)


def has_real_content(boxes, frame_area: float) -> bool:
    """True iff the frame carries a real slide region (see module docstring)."""
    content = _content_boxes(boxes)
    if not content:
        return False
    if _has_substantial_text(content, frame_area):
        return True
    if _has_strong_figure(content):
        return True
    if len(content) >= MIN_CONTENT_BOXES_FOR_RESCUE and _has_large_diagram(content, frame_area):
        return True
    return False


def preselect_candidates(
    candidates: list[FrameCandidate], *, yolo
) -> list[FrameCandidate]:
    """Drop candidates with no real slide content via a cheap DocLayout-YOLO pass.

    Args:
        candidates: output of frames.extract_candidates().
        yolo: the injected DocLayout-YOLO client (`.detect(image_url) ->
              DetectResponse`) — the SAME client figure_extract uses, so no new
              dependency is introduced.

    Returns the surviving FrameCandidate list in input order. Recall-first: a
    detect error on a frame KEEPS it (the VLM router still vets it). The caller
    is responsible for not starving the pipeline if the gate empties the set.
    """
    if not candidates:
        return []

    kept: list[FrameCandidate] = []
    for cand in candidates:
        try:
            detection = yolo.detect(image_data_url(cand.path))
        except Exception as exc:  # noqa: BLE001 — recall-first: keep on detect error
            sys.stderr.write(
                f"preselect: detect failed for {cand.path} ({exc}) — frame kept\n"
            )
            kept.append(cand)
            continue
        frame_area = float(detection.image.w) * float(detection.image.h)
        if frame_area <= 0 or has_real_content(detection.boxes, frame_area):
            # Attach figure-box count (reuses this frame's YOLO result — no extra
            # detect) so numerize can rank figure frames over text frames.
            cand.fig_box_count = sum(
                1 for kind, _, _ in _content_boxes(detection.boxes) if kind in FIGURE_KINDS
            )
            kept.append(cand)
    return kept
