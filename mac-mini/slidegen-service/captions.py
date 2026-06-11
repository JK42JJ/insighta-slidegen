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
    """
    segments = _load_caption_segments(youtube_video_id)
    if not segments:
        return []

    # Filter by minimum duration
    segments = [s for s in segments if (s.to_sec - s.from_sec) >= MIN_SEGMENT_SEC]
    if not segments:
        return []

    # Embed all segment texts
    texts = [s.text for s in segments]
    embeddings = _embed_texts(texts)

    # Assign embeddings to segments
    for seg, emb in zip(segments, embeddings):
        seg.bge_embedding = emb

    # Detect topic changes
    topic_points = _detect_changes(segments)

    # Persist to slide_caption_segments (prod only)
    if mode != "dev":
        _persist_segments(youtube_video_id, segments, topic_points)

    return sorted(topic_points, key=lambda p: p.timestamp_sec)


def _load_caption_segments(youtube_video_id: str) -> list[CaptionSegment]:
    """Load caption segments from video_captions table."""
    import json
    import os

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return []

    try:
        import psycopg2
    except ImportError:
        return []

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # video_captions.video_id is a UUID FK → youtube_videos.id (insighta
        # schema) — NOT the 11-char YouTube id; join to look up by YouTube id.
        cur.execute(
            """SELECT vc.segments
               FROM video_captions vc
               JOIN youtube_videos yv ON yv.id = vc.video_id
               WHERE yv.youtube_video_id = %s
               LIMIT 1""",
            (youtube_video_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return []

        raw = row[0]
        if isinstance(raw, str):
            parsed = json.loads(raw)
        else:
            parsed = raw

        return [
            CaptionSegment(
                from_sec=s["from_sec"],
                to_sec=s["to_sec"],
                text=s["text"],
                bge_embedding=[],
            )
            for s in parsed
        ]
    except Exception:
        return []


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed texts via BGE_M3_EMBED_URL HTTP endpoint."""
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx not installed. Install with: pip install httpx")

    if not texts:
        return []

    try:
        response = httpx.post(
            BGE_M3_EMBED_URL,
            json={"texts": texts},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])
    except Exception as e:
        raise RuntimeError(f"BGE-M3 embedding failed: {e}") from e


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Compute cosine distance (1 - cosine similarity) between two vectors."""
    import math

    if not a or not b or len(a) != len(b):
        return 1.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 1.0

    cosine_sim = dot / (norm_a * norm_b)
    return 1.0 - cosine_sim


def _detect_changes(segments: list[CaptionSegment]) -> list[CaptionTopicPoint]:
    """Detect topic-change boundaries via cosine distance."""
    points = []
    for i in range(1, len(segments)):
        prev = segments[i - 1]
        curr = segments[i]
        dist = _cosine_distance(prev.bge_embedding, curr.bge_embedding)
        if dist > TOPIC_CHANGE_DISTANCE_THRESHOLD:
            points.append(
                CaptionTopicPoint(
                    timestamp_sec=curr.from_sec,
                    topic_label=curr.text[:60] if curr.text else None,
                    bge_embedding=curr.bge_embedding,
                )
            )
    return points


def _persist_segments(
    youtube_video_id: str, segments: list[CaptionSegment], topic_points: list[CaptionTopicPoint]
) -> None:
    """Persist segments and topic changes to slide_caption_segments."""
    import json
    import os

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return

    try:
        import psycopg2
    except ImportError:
        return

    try:
        topic_timestamps = {p.timestamp_sec for p in topic_points}
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        for seg in segments:
            is_boundary = seg.from_sec in topic_timestamps
            embedding_json = json.dumps(seg.bge_embedding)
            # ADR 0003 D6: no verbatim caption text — embedding + boundary flag
            # only. Schema-qualified: slide_* tables live in `slidegen`.
            cur.execute(
                """INSERT INTO slidegen.slide_caption_segments
                   (youtube_video_id, from_sec, to_sec, embedding, is_topic_change)
                   VALUES (%s, %s, %s, %s::vector, %s)
                   ON CONFLICT DO NOTHING""",
                (youtube_video_id, seg.from_sec, seg.to_sec, embedding_json, is_boundary),
            )

        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
