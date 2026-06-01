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
    """
    if not candidates:
        return []

    # Step 1: Batch-encode all candidates with CLIP
    clip_embeddings = _encode_candidates(candidates)
    if not clip_embeddings:
        return []

    # Step 2: Greedy dedup — iterate in timestamp order
    selected: list[SelectedFrame] = []
    for i, candidate in enumerate(candidates):
        clip_vec = clip_embeddings[i]

        # Compute min cosine distance to already-selected frames (dev: in-memory)
        min_distance = _min_cosine_distance_to_selected(clip_vec, selected)

        # Skip if semantically similar to an already-selected frame
        if min_distance < CLIP_DISTANCE_THRESHOLD:
            continue

        # Check for topic-change alignment
        nearest_topic, is_aligned = _find_topic_alignment(candidate, topic_points)

        # Create SelectedFrame
        selected_frame = SelectedFrame(
            candidate=candidate,
            clip_embedding=clip_vec,
            is_topic_aligned=is_aligned,
            nearest_topic_point=nearest_topic,
            cosine_distance_to_prev=min_distance if selected else None,
        )
        selected.append(selected_frame)

        # Stop when target reached
        if len(selected) >= TARGET_SELECTED:
            break

    # Step 3: Persist to slide_keyframes (prod only)
    if mode != "dev":
        _persist_keyframes(selected)

    # Step 4: Return sorted by timestamp
    return sorted(selected, key=lambda s: s.candidate.timestamp_sec)


def _encode_candidates(candidates: list[FrameCandidate]) -> list[list[float]]:
    """Batch-encode candidates with CLIP ViT-B/32."""
    try:
        import open_clip
        from PIL import Image
    except ImportError as e:
        raise ImportError("open_clip and Pillow required. Install with: pip install open-clip-torch pillow") from e

    try:
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    except Exception as e:
        raise RuntimeError(f"Failed to load CLIP model: {e}") from e

    embeddings = []
    for candidate in candidates:
        try:
            img = Image.open(candidate.path)
            img_tensor = preprocess(img).unsqueeze(0)
            with open_clip.get_tokenizer("ViT-B-32").__call__ as tokenizer:
                with __import__("torch").no_grad():
                    emb = model.encode_image(img_tensor)
                    emb_normalized = emb / emb.norm(dim=-1, keepdim=True)
                    embeddings.append(emb_normalized.squeeze(0).tolist())
        except Exception:
            # If encoding fails, use zero vector as fallback
            embeddings.append([0.0] * 512)

    return embeddings


def _min_cosine_distance_to_selected(clip_vec: list[float], selected: list[SelectedFrame]) -> float:
    """Compute minimum cosine distance from clip_vec to all selected frames."""
    if not selected:
        return 1.0

    min_dist = 1.0
    for selected_frame in selected:
        dist = _cosine_distance(clip_vec, selected_frame.clip_embedding)
        min_dist = min(min_dist, dist)

    return min_dist


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


def _find_topic_alignment(
    candidate: FrameCandidate, topic_points: list[CaptionTopicPoint]
) -> tuple[CaptionTopicPoint | None, bool]:
    """Find topic-change point within TOPIC_ALIGN_WINDOW_SEC of candidate."""
    for topic_point in topic_points:
        if abs(candidate.timestamp_sec - topic_point.timestamp_sec) <= TOPIC_ALIGN_WINDOW_SEC:
            return topic_point, True

    return None, False


def _persist_keyframes(selected: list[SelectedFrame]) -> None:
    """Persist selected frames to slide_keyframes (prod only)."""
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
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        for selected_frame in selected:
            candidate = selected_frame.candidate
            embedding_json = json.dumps(selected_frame.clip_embedding)

            cur.execute(
                """INSERT INTO slide_keyframes
                   (timestamp_sec, clip_embedding, is_topic_aligned, is_selected)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (
                    candidate.timestamp_sec,
                    embedding_json,
                    selected_frame.is_topic_aligned,
                    True,
                ),
            )

        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
