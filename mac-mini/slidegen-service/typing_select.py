"""
Keyframe selection by CLIP embedding distance + BGE-M3 caption topic alignment.

Inputs:
    candidates  — ~80 FrameCandidate objects from frames.extract_candidates()
    topic_points — list[CaptionTopicPoint] from captions.detect_topic_changes()

Selection algorithm (greedy dedup, same logic as Insighta iks-scorer dedup):
    1. Batch-encode all candidate frames with open_clip (CLIP ViT-B/32) → 512-dim vectors.
    2. For each candidate in timestamp order:
         a. Compute cosine distance vs every already-selected frame's CLIP vector.
         b. If min_distance < CLIP_DISTANCE_THRESHOLD → semantically similar → skip.
         c. If a caption topic-change point falls within ±TOPIC_ALIGN_WINDOW_SEC of
            this frame AND the CLIP distance check passes → "definite keep".
         d. Otherwise keep if CLIP distance check passes (visually new content).
    3. Stop when selected count reaches TARGET_SELECTED or candidates exhausted.
    4. Write each selected frame's clip_embedding to slide_keyframes via pgvector
       (pgvector computes cosine distances; embeddings stored for later querying).

Result: ~12 SelectedFrame objects, each carrying timestamp_sec + clip_embedding.

YOLO / layout detection / OCR are NOT here.  They run downstream in
figure_extract.py on the already-selected ~12 frames.

Constants:
    CLIP_DISTANCE_THRESHOLD  — cosine distance below which frames are "too similar".
    TOPIC_ALIGN_WINDOW_SEC   — seconds within which a topic change "locks in" a frame.
    TARGET_SELECTED          — target number of final keyframes (~12).
"""

from __future__ import annotations

from dataclasses import dataclass

from frames import FrameCandidate

# Cosine distance threshold: frames closer than this are considered duplicates.
# Mirrors the similarity threshold used in Insighta's iks-scorer card dedup.
CLIP_DISTANCE_THRESHOLD = 0.25

# A caption topic-change point within this window of a candidate frame locks it in.
TOPIC_ALIGN_WINDOW_SEC = 3.0

# Final selected frame target — one keyframe per distinct topic.
TARGET_SELECTED = 12


@dataclass
class CaptionTopicPoint:
    """A topic-change boundary detected in the caption stream (from captions.py)."""
    timestamp_sec: float
    topic_label: str | None  # brief description of new topic; may be None
    bge_embedding: list[float]  # 1024-dim BGE-M3 embedding of the topic-change segment


@dataclass
class SelectedFrame:
    """A candidate that survived embedding-distance dedup and is a final keyframe."""
    candidate: FrameCandidate
    clip_embedding: list[float]          # 512-dim CLIP vector
    is_topic_aligned: bool               # True if locked in by a caption topic-change point
    nearest_topic_point: CaptionTopicPoint | None  # topic-change point that aligned this frame
    cosine_distance_to_prev: float | None  # distance to the nearest already-selected frame
    # frame_type / quality are available as tie-break notes only (no longer the selector)
    frame_type: str = "unknown"          # "title_card" | "diagram" | "chart" | "face" | "b_roll"
    type_confidence: float = 0.0


def select_keyframes(
    candidates: list[FrameCandidate],
    topic_points: list[CaptionTopicPoint],
    mode: str = "dev",
) -> list[SelectedFrame]:
    """
    Select ~TARGET_SELECTED keyframes from ~80 candidates via CLIP + topic alignment.

    Algorithm:
        1. Batch-encode candidates with open_clip.encode_image() → 512-dim vectors.
        2. Iterate candidates in timestamp order:
             a. Query pgvector for cosine distance to all already-selected embeddings.
                  (pgvector: SELECT 1 - (embedding <=> query) FROM slide_keyframes ...)
             b. If min cosine distance < CLIP_DISTANCE_THRESHOLD → skip (duplicate).
             c. Else: check caption topic_points within TOPIC_ALIGN_WINDOW_SEC.
                  topic-aligned AND visually new → definite keep (is_topic_aligned=True).
                  visually new only → keep.
             d. Persist is_selected=True row to slide_keyframes with clip_embedding.
        3. Stop at TARGET_SELECTED or end of candidates.
        4. Return SelectedFrame list (timestamp_sec ascending).

    In dev mode: no DB write; skip pgvector queries; use in-memory cosine calc.
    In prod mode: write to slide_keyframes + use pgvector for distance computation.

    TODO: implement using open_clip + psycopg2/asyncpg for pgvector queries.
    """
    raise NotImplementedError("TODO: select_keyframes")
