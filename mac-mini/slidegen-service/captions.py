"""
Caption loading and BGE-M3 topic-change detection.

Reads caption segments from the video_captions read-mirror (insighta DB),
embeds each segment with BGE-M3 (1024-dim text embeddings), and detects
topic-change boundaries via cosine distance between adjacent segment embeddings.

Topic-change points are the "this is the important part" moments: topic shifts
are detectable in captions (text) rather than screen content, so this module
complements CLIP (image) embeddings in the selection step.

Entry: detect_topic_changes(youtube_video_id, mode) → list[CaptionTopicPoint]
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# BGE-M3 embedding endpoint (env: BGE_M3_EMBED_URL).
# Expected: POST {"texts": [...]} → {"embeddings": [[float, ...], ...]}
# Model: BAAI/bge-m3 (1024-dim dense text embeddings).
BGE_M3_EMBED_URL = os.environ.get("BGE_M3_EMBED_URL", "http://localhost:8078/embed")
BGE_M3_MODEL_VERSION = os.environ.get("BGE_M3_MODEL_VERSION", "bge-m3")

# Cosine distance between adjacent caption segments above this → topic changed.
TOPIC_CHANGE_DISTANCE_THRESHOLD = 0.30

# Minimum segment duration to consider (short fragments skipped).
MIN_SEGMENT_SEC = 5.0


@dataclass
class CaptionSegment:
    """A single caption segment with timing and BGE-M3 embedding."""
    from_sec: float
    to_sec: float
    text: str
    bge_embedding: list[float]  # 1024-dim BGE-M3 vector


@dataclass
class CaptionTopicPoint:
    """
    A topic-change boundary detected between two adjacent caption segments.
    Exported to typing_select.select_keyframes() for frame alignment.
    """
    timestamp_sec: float         # start of the new topic segment
    topic_label: str | None      # first ~60 chars of the new-topic segment text
    bge_embedding: list[float]   # 1024-dim embedding of the new-topic segment


def detect_topic_changes(
    youtube_video_id: str,
    mode: str = "dev",
) -> list[CaptionTopicPoint]:
    """
    Load captions for youtube_video_id and detect topic-change points.

    Algorithm:
        1. Query video_captions (read-mirror) for the video; parse segments JSON.
        2. Filter segments shorter than MIN_SEGMENT_SEC.
        3. Batch-embed all segment texts via POST BGE_M3_EMBED_URL → 1024-dim vectors.
        4. Slide over adjacent pairs; compute cosine distance.
        5. Where distance > TOPIC_CHANGE_DISTANCE_THRESHOLD → topic changed.
           Record CaptionTopicPoint at the boundary (from_sec of the new segment).
        6. Persist each segment + embedding to slide_caption_segments
           (is_topic_change=True at boundaries) — skipped in dev if no DB URL.
        7. Return list of CaptionTopicPoint sorted by timestamp_sec.

    In dev mode: DB write skipped; BGE_M3_EMBED_URL may be a local stub.

    TODO: implement using httpx (async POST to BGE_M3_EMBED_URL) + Prisma/psycopg2
          for video_captions read + slide_caption_segments write.
    """
    raise NotImplementedError(
        f"TODO: detect_topic_changes youtube_video_id={youtube_video_id}"
    )
