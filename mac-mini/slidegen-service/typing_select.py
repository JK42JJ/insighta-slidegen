"""
Keyframe selection by a local vision-language model (Qwen2.5-VL) — ADR 0001.

Replaces the former CLIP-embedding + cosine-dedup selector. A local VLM reads
the candidate frames (PySceneDetect wide net → CPU downsample, frames.py — ADR
0002 D1/D3) in timestamp order and decides, per frame, whether it is a
knowledge-bearing slide and what it contains (graph / equation / type),
emitting routing metadata that drives the downstream conditional extraction
(DocLayout-YOLO region crop / UniMERNet equation OCR).

Inputs:
    candidates   — ~60 downsampled FrameCandidate objects (each carrying its
                   t_start/t_end interval, ADR 0002 D6) from
                   frames.extract_candidates()
    topic_points — list[CaptionTopicPoint] from captions.detect_topic_changes()
                   (BGE-M3 caption topic-change signal; auxiliary)

Selection algorithm:
    1. Batch the candidate frames to the local VLM router (Qwen2.5-VL) via the
       pluggable `vlm_router` backend (mock / transformers / mlx, selected by
       SLIDEGEN_VLM_BACKEND — so this runs off Apple Silicon too). The prompt
       forces the routing JSON schema: is_slide / contains_graph /
       contains_equation / frame_type / summary_hint / confidence.
    2. Keep the frames the VLM marks is_slide=True, in timestamp order, up to
       TARGET_SELECTED_MAX (~20). Target floor is TARGET_SELECTED_MIN (~12).
    3. Mark caption topic-change alignment (auxiliary BGE-M3 signal).
    4. In prod mode, persist selected rows to slidegen.slide_keyframes with the
       routing metadata columns — NO clip_embedding (ADR 0001). Dev: no DB write.

No CLIP. No vision API. The router VLM runs locally (ADR 0001 — LLM API ban
upheld; this is an open-weights local model, not an API call).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from frames import FrameCandidate
from vlm_router import route_frames

# A caption topic-change point within this window of a candidate "locks it in".
TOPIC_ALIGN_WINDOW_SEC = 3.0

# Final selected-frame target band (ADR 0001: 12-20 knowledge-bearing slides).
TARGET_SELECTED_MIN = 12
TARGET_SELECTED_MAX = 20


@dataclass
class SectionContext:
    """A v2 rich-summary section: a time window plus its title/summary text.

    Mirrors app.py's `Section` pydantic model (the TS client sends title +
    summary from `video_rich_summaries.segments.sections`). The text is the
    Qwen select call's grounding input — ADR 0002 D5: a HINT for selection,
    NEVER a keep/drop gate (no code path may drop a frame because of it).
    """
    index: int
    from_sec: float
    to_sec: float
    title: str = ""
    summary: str | None = None


@dataclass
class CaptionTopicPoint:
    """A topic-change boundary detected in the caption stream (from captions.py)."""
    timestamp_sec: float
    topic_label: str | None      # brief description of new topic; may be None
    bge_embedding: list[float]   # 1024-dim BGE-M3 embedding of the topic-change segment


@dataclass
class RoutingMetadata:
    """Per-frame routing decision emitted by the VLM router (ADR 0001 JSON schema)."""
    is_slide: bool               # knowledge-bearing slide vs transition/b-roll
    contains_graph: bool         # chart / diagram / table region present
    contains_equation: bool      # mathematical equation present
    frame_type: str              # "title_card"|"diagram"|"chart"|"table"|"face"|"b_roll"
    summary_hint: str | None     # brief description of the slide content
    confidence: float            # VLM confidence for this routing decision (0.0-1.0)


@dataclass
class SelectedFrame:
    """A candidate the VLM router kept as a final keyframe, carrying routing metadata."""
    candidate: FrameCandidate
    contains_graph: bool
    contains_equation: bool
    frame_type: str
    summary_hint: str | None
    is_topic_aligned: bool                          # locked in by a caption topic-change point
    nearest_topic_point: CaptionTopicPoint | None   # the aligning topic-change point, if any
    selection_score: float                          # VLM confidence for this frame


def select_keyframes(
    candidates: list[FrameCandidate],
    topic_points: list[CaptionTopicPoint],
    mode: str = "dev",
    sections: Sequence[SectionContext | Mapping[str, Any]] | None = None,
    youtube_video_id: str | None = None,
) -> list[SelectedFrame]:
    """
    Select 12-20 keyframes from the candidates via the local VLM router.

    `sections` (optional, default None = previous behavior) carries the v2
    rich-summary section windows with their title/summary text. When present,
    candidates are grouped into one routing window per overlapping section
    (ADR 0002 D4) and each window's section text rides along as the backend's
    `captions_text` companion input (CONTRACT §2.2 mode A). Per ADR 0002 D5
    the text GROUNDS the VLM's selection — it is a hint, never a keep/drop
    gate: no frame is kept or dropped here based on section text.

    Returns SelectedFrame list sorted by timestamp_sec ascending. In dev mode no
    DB write happens; in prod mode the selected rows are persisted to
    slidegen.slide_keyframes (routing metadata; no CLIP embedding — ADR 0001).
    """
    if not candidates:
        return []

    # Step 1: VLM routing decision per candidate (same order as candidates).
    routings = _route_with_vlm(candidates, sections)
    if not routings:
        return []

    # Step 2: keep is_slide frames in timestamp order, capped at the target max.
    selected: list[SelectedFrame] = []
    for candidate, routing in zip(candidates, routings):
        if not routing.is_slide:
            continue

        # Step 3: caption topic-change alignment (auxiliary signal).
        nearest_topic, is_aligned = _find_topic_alignment(candidate, topic_points)

        selected.append(
            SelectedFrame(
                candidate=candidate,
                contains_graph=routing.contains_graph,
                contains_equation=routing.contains_equation,
                frame_type=routing.frame_type,
                summary_hint=routing.summary_hint,
                is_topic_aligned=is_aligned,
                nearest_topic_point=nearest_topic,
                selection_score=routing.confidence,
            )
        )

        if len(selected) >= TARGET_SELECTED_MAX:
            break

    # Step 4: persist (prod only).
    if mode != "dev":
        _persist_keyframes(selected, youtube_video_id, sections)

    return sorted(selected, key=lambda s: s.candidate.timestamp_sec)


def _route_with_vlm(
    candidates: list[FrameCandidate],
    sections: Sequence[SectionContext | Mapping[str, Any]] | None = None,
) -> list[RoutingMetadata]:
    """
    Run the local VLM router (Qwen2.5-VL) over the candidate frames.

    Delegates inference to the configured `vlm_router` backend (mock by default;
    transformers on CUDA/Kaggle; mlx on Apple Silicon — selected by
    SLIDEGEN_VLM_BACKEND). The backend returns one routing dict per candidate in
    input order, which is mapped 1:1 onto RoutingMetadata.

    With `sections` present, candidates are routed in one backend call per
    window (a window = the candidates whose [t_start, t_end] interval best
    overlaps that section — ADR 0002 D4/D6) and the window's section text is
    passed as `captions_text`. Without sections (None/empty): a single call
    with no companion text — exactly the previous behavior.

    Returns one RoutingMetadata per input candidate, in the same order.
    """
    if not candidates:
        return []

    raw_routings: list[dict | None] = [None] * len(candidates)
    for captions_text, indices in _window_candidates(candidates, sections):
        window_raw = route_frames([candidates[i] for i in indices], captions_text)
        if len(window_raw) != len(indices):
            # Fail loud: a silent truncation would misalign frame ↔ routing.
            raise ValueError(
                f"VLM backend returned {len(window_raw)} routings for "
                f"{len(indices)} window candidates"
            )
        for i, raw in zip(indices, window_raw):
            raw_routings[i] = raw

    return [
        RoutingMetadata(
            is_slide=routing["is_slide"],
            contains_graph=routing["contains_graph"],
            contains_equation=routing["contains_equation"],
            frame_type=routing["frame_type"],
            summary_hint=routing["summary_hint"],
            confidence=routing["confidence"],
        )
        for routing in raw_routings
        if routing is not None
    ]


def _coerce_section(raw: SectionContext | Mapping[str, Any]) -> SectionContext:
    """Accept either a SectionContext or app.py's Section.model_dump() dict."""
    if isinstance(raw, SectionContext):
        return raw
    return SectionContext(
        index=int(raw.get("index", 0)),
        from_sec=float(raw["from_sec"]),
        to_sec=float(raw["to_sec"]),
        title=str(raw.get("title") or ""),
        summary=raw.get("summary"),
    )


def format_section_hint(section: SectionContext) -> str:
    """One grounding line per section: "[{from}-{to}s] {title}: {summary}"."""
    line = f"[{section.from_sec:g}-{section.to_sec:g}s] {section.title}"
    if section.summary:
        line += f": {section.summary}"
    return line


def _window_candidates(
    candidates: list[FrameCandidate],
    sections: Sequence[SectionContext | Mapping[str, Any]] | None,
) -> list[tuple[str | None, list[int]]]:
    """Group candidate indices into routing windows by section overlap.

    Each candidate is assigned to the section whose [from_sec, to_sec] window
    has the largest overlap with the candidate's [t_start, t_end] interval
    (ADR 0002 D6 time provenance; ties → earlier section). Candidates that
    overlap no section — and the whole list when `sections` is None/empty —
    fall into a no-context window (captions_text=None), so every candidate is
    ALWAYS routed: section text can never gate a frame out (ADR 0002 D5).

    Returns [(captions_text | None, [original candidate indices]), ...] with
    indices in input order within each window.
    """
    if not sections:
        return [(None, list(range(len(candidates))))]

    contexts = [_coerce_section(s) for s in sections]
    grouped: dict[int | None, list[int]] = {}
    for i, candidate in enumerate(candidates):
        grouped.setdefault(_best_section(candidate, contexts), []).append(i)

    windows: list[tuple[str | None, list[int]]] = []
    for section_pos, indices in grouped.items():
        text = None if section_pos is None else format_section_hint(contexts[section_pos])
        windows.append((text, indices))
    return windows


def _best_section(
    candidate: FrameCandidate, contexts: list[SectionContext]
) -> int | None:
    """Index (into contexts) of the section overlapping the candidate most.

    Overlap is measured between the candidate's [t_start, t_end] interval and
    the section's [from_sec, to_sec]; a touching boundary (overlap == 0)
    counts so instant candidates sitting exactly on a section edge still get
    context. Returns None when no section overlaps at all.
    """
    best: int | None = None
    best_overlap = -1.0
    for pos, section in enumerate(contexts):
        overlap = min(candidate.t_end, section.to_sec) - max(
            candidate.t_start, section.from_sec
        )
        if overlap < 0:
            continue
        if overlap > best_overlap:
            best, best_overlap = pos, overlap
    return best


def _find_topic_alignment(
    candidate: FrameCandidate, topic_points: list[CaptionTopicPoint]
) -> tuple[CaptionTopicPoint | None, bool]:
    """Find a caption topic-change point within TOPIC_ALIGN_WINDOW_SEC of candidate."""
    for topic_point in topic_points:
        if abs(candidate.timestamp_sec - topic_point.timestamp_sec) <= TOPIC_ALIGN_WINDOW_SEC:
            return topic_point, True

    return None, False


def _section_index_for(
    timestamp_sec: float,
    sections: Sequence[SectionContext | Mapping[str, Any]] | None,
) -> int:
    """Section whose [from_sec, to_sec) window contains the timestamp (else 0)."""
    for section in sections or []:
        get = section.get if isinstance(section, Mapping) else lambda k, _s=section: getattr(_s, k, None)
        from_sec, to_sec = get("from_sec"), get("to_sec")
        if from_sec is None or to_sec is None:
            continue
        if float(from_sec) <= timestamp_sec < float(to_sec):
            index = get("index")
            return int(index) if index is not None else 0
    return 0


def _persist_keyframes(
    selected: list[SelectedFrame],
    youtube_video_id: str | None,
    sections: Sequence[SectionContext | Mapping[str, Any]] | None = None,
) -> None:
    """
    Persist selected frames to slidegen.slide_keyframes (prod only).

    Writes the routing-metadata columns that EXIST in the prod DDL
    (slidegen-init/001): youtube_video_id, section_index, timestamp_sec,
    frame_type, selection_score, is_selected — NO clip_embedding (deprecated,
    ADR 0001). NOTE: the Prisma mirror also lists contains_graph /
    contains_equation / summary_hint, but those columns are NOT in the prod
    DB (verified 2026-06-11) — adding them is a raw-DDL follow-up.

    Best-effort like captions._persist_segments: a persistence hiccup is
    logged, never fails the select stage. slide_* writes only.
    """
    import sys

    if not selected or not youtube_video_id:
        if selected and not youtube_video_id:
            sys.stderr.write("persist_keyframes: no youtube_video_id — skipped\n")
        return

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return

    try:
        import psycopg2
    except ImportError:
        sys.stderr.write("persist_keyframes: psycopg2 not installed — skipped\n")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        for frame in selected:
            cur.execute(
                """INSERT INTO slidegen.slide_keyframes
                   (youtube_video_id, section_index, timestamp_sec, frame_type,
                    selection_score, is_selected)
                   VALUES (%s, %s, %s, %s, %s, TRUE)
                   ON CONFLICT DO NOTHING""",
                (
                    youtube_video_id,
                    _section_index_for(frame.candidate.timestamp_sec, sections),
                    frame.candidate.timestamp_sec,
                    frame.frame_type,
                    frame.selection_score,
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001 — best-effort persistence boundary
        sys.stderr.write(f"persist_keyframes: failed ({exc}) — select stage continues\n")
