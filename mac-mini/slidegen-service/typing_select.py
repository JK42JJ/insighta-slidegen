"""
Keyframe selection by a local vision-language model (Qwen2.5-VL) — ADR 0001.

Replaces the former CLIP-embedding + cosine-dedup selector. A local VLM reads
the Katna candidate frames in timestamp order and decides, per frame, whether it
is a knowledge-bearing slide and what it contains (graph / equation / type),
emitting routing metadata that drives the downstream conditional extraction
(DocLayout-YOLO region crop / UniMERNet equation OCR).

Inputs:
    candidates   — ~50-100 FrameCandidate objects from frames.extract_candidates()
    topic_points — list[CaptionTopicPoint] from captions.detect_topic_changes()
                   (BGE-M3 caption topic-change signal; auxiliary)

Selection algorithm:
    1. Batch the candidate frames to the local VLM (Qwen2.5-VL, MLX on Apple
       Silicon; 3B fallback per ADR 0001 D9) with a prompt that forces the
       routing JSON schema: is_slide / contains_graph / contains_equation /
       frame_type / summary_hint / confidence.
    2. Keep the frames the VLM marks is_slide=True, in timestamp order, up to
       TARGET_SELECTED_MAX (~20). Target floor is TARGET_SELECTED_MIN (~12).
    3. Mark caption topic-change alignment (auxiliary BGE-M3 signal).
    4. In prod mode, persist selected rows to slidegen.slide_keyframes with the
       routing metadata columns — NO clip_embedding (ADR 0001). Dev: no DB write.

No CLIP. No vision API. The router VLM runs locally (ADR 0001 — LLM API ban
upheld; this is an open-weights local model, not an API call).
"""

from __future__ import annotations

from dataclasses import dataclass

from frames import FrameCandidate

# Local VLM router model (Apple Silicon / MLX). 3B is the memory fallback (ADR D9).
ROUTER_MODEL = "qwen2.5-vl-7b-instruct"

# A caption topic-change point within this window of a candidate "locks it in".
TOPIC_ALIGN_WINDOW_SEC = 3.0

# Final selected-frame target band (ADR 0001: 12-20 knowledge-bearing slides).
TARGET_SELECTED_MIN = 12
TARGET_SELECTED_MAX = 20


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
) -> list[SelectedFrame]:
    """
    Select 12-20 keyframes from the candidates via the local VLM router.

    Returns SelectedFrame list sorted by timestamp_sec ascending. In dev mode no
    DB write happens; in prod mode the selected rows are persisted to
    slidegen.slide_keyframes (routing metadata; no CLIP embedding — ADR 0001).
    """
    if not candidates:
        return []

    # Step 1: VLM routing decision per candidate (same order as candidates).
    routings = _route_with_vlm(candidates)
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
        _persist_keyframes(selected)

    return sorted(selected, key=lambda s: s.candidate.timestamp_sec)


def _route_with_vlm(candidates: list[FrameCandidate]) -> list[RoutingMetadata]:
    """
    Run the local VLM router (Qwen2.5-VL) over the candidate frames.

    Phase 2 inference stub (ADR 0001). Implementation plan:
        1. Lazy-import the MLX VLM runtime (mlx_vlm on Apple Silicon; 3B fallback
           per ADR D9 when the 7B-4bit footprint is unsafe alongside the
           extractors).
        2. Load ROUTER_MODEL once (module-level cache).
        3. Prompt the model (batched, timestamp-ordered) with the routing JSON
           schema and parse exactly one RoutingMetadata per input candidate.

    Returns one RoutingMetadata per input candidate, in the same order.
    """
    raise NotImplementedError(
        "TODO (Phase 2 inference): load Qwen2.5-VL via mlx_vlm and emit routing metadata"
    )


def _find_topic_alignment(
    candidate: FrameCandidate, topic_points: list[CaptionTopicPoint]
) -> tuple[CaptionTopicPoint | None, bool]:
    """Find a caption topic-change point within TOPIC_ALIGN_WINDOW_SEC of candidate."""
    for topic_point in topic_points:
        if abs(candidate.timestamp_sec - topic_point.timestamp_sec) <= TOPIC_ALIGN_WINDOW_SEC:
            return topic_point, True

    return None, False


def _persist_keyframes(selected: list[SelectedFrame]) -> None:
    """
    Persist selected frames to slidegen.slide_keyframes (prod only).

    Writes the routing-metadata columns (frame_type, selection_score,
    contains_graph, contains_equation, summary_hint, is_selected) — NO
    clip_embedding (deprecated, ADR 0001).

    Phase 2 prod stub: wire the psycopg2 INSERT (with youtube_video_id +
    section_index) when the prod write path is implemented.
    """
    raise NotImplementedError(
        "TODO (Phase 2 prod): INSERT routing metadata into slidegen.slide_keyframes"
    )
