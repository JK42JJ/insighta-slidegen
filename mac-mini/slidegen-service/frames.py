"""
Wide-net candidate frame extraction using Katna.

Primary extractor: Katna VideoFrameSelector — pulls ~80 candidate frames
per video by sampling at regular intervals and retaining frames with high
information content.  The goal is a *wide net*: cast broadly, accept some
junk.  Downstream selection (select.py / pgvector dedup) will narrow to ~12.

PySceneDetect is an optional reinforcement pass only: it may flag additional
scene-boundary timestamps but is NOT the primary selector.

Entry function: extract_candidates(video_path, target_count) → list[FrameCandidate]
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2

# Target candidate count — wide net before embedding-based selection.
KATNA_TARGET_COUNT = 80
TOPIC_ALIGN_WINDOW_SEC = 3.0


@dataclass
class FrameCandidate:
    """A single candidate frame with quality metadata."""
    path: Path
    timestamp_sec: float
    section_index: int
    quality_score: float  # 0.0 – 1.0; Katna information-content score
    is_scene_boundary: bool  # True if PySceneDetect reinforcement flagged this frame


def extract_candidates(
    video_path: Path,
    target_count: int = KATNA_TARGET_COUNT,
) -> list[FrameCandidate]:
    """
    Extract ~target_count candidate frames from video_path using Katna.

    Algorithm:
        1. Run Katna VideoFrameSelector.extract_frames_from_video() with
           no_of_frames=target_count to produce a wide candidate set (~80).
        2. Assign section_index from timestamp proportion over video duration.
        3. Compute quality_score from Katna's internal brightness/sharpness
           signals (exposed via frame_metadata if available, else Laplacian var).
        4. Optional reinforcement: run scenedetect ContentDetector; set
           is_scene_boundary=True for frames within ±0.5 s of a boundary.
        5. Return list sorted by timestamp_sec ascending.

    Note: is_scene_boundary is advisory only — final selection is done
    by CLIP embedding distance + BGE-M3 caption topic-change alignment (select.py).
    """
    # Get video duration
    duration = _get_video_duration(video_path)

    # Step 1: Run Katna to extract ~target_count candidates
    katna_frames = _run_katna(video_path, target_count)

    # Step 2: Detect scene boundaries (optional reinforcement)
    scene_boundaries = _scene_boundaries(video_path)

    # Step 3: Build FrameCandidate list with quality scores
    candidates = []
    for frame_path in katna_frames:
        timestamp_sec = _extract_timestamp(frame_path.name)
        if timestamp_sec is None:
            continue

        # Compute quality score (Laplacian variance)
        quality_score = _laplacian_score(frame_path)

        # Check if this frame is near a scene boundary
        is_boundary = any(
            abs(timestamp_sec - boundary) <= TOPIC_ALIGN_WINDOW_SEC
            for boundary in scene_boundaries
        )

        # Assign section_index from timestamp proportion
        section_index = int(timestamp_sec / duration * 10) if duration > 0 else 0

        candidate = FrameCandidate(
            path=frame_path,
            timestamp_sec=timestamp_sec,
            section_index=section_index,
            quality_score=quality_score,
            is_scene_boundary=is_boundary,
        )
        candidates.append(candidate)

    # Step 4: Sort by timestamp
    candidates.sort(key=lambda c: c.timestamp_sec)

    return candidates


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    if fps <= 0:
        return 0.0
    return frame_count / fps


def _run_katna(video_path: Path, target_count: int) -> list[Path]:
    """Run Katna to extract keyframes. Returns list of frame paths."""
    try:
        from katna.video import Video
        from katna.writer import KeyFrameDiskWriter
    except ImportError as e:
        raise ImportError(
            "katna not installed. Install with: pip install katna"
        ) from e

    with tempfile.TemporaryDirectory() as tmpdir:
        writer = KeyFrameDiskWriter(location=tmpdir)
        vd = Video()

        try:
            vd.extract_video_keyframes(
                no_of_frames=target_count,
                file_path=str(video_path),
                writer=writer,
            )
        except Exception as e:
            raise RuntimeError(f"Katna extraction failed: {e}") from e

        # Collect extracted frames
        frames = sorted(Path(tmpdir).glob("*.jpg"))
        return frames


def _scene_boundaries(video_path: Path) -> list[float]:
    """Detect scene boundaries using PySceneDetect. Returns list of timestamps (sec)."""
    try:
        # PySceneDetect 0.6+ high-level API. The legacy VideoManager/SceneManager
        # boilerplate was removed; detect() wraps open_video + SceneManager.
        from scenedetect import ContentDetector, detect
    except ImportError:
        # If scenedetect not available, return empty list (no reinforcement)
        return []

    try:
        scene_list = detect(str(video_path), ContentDetector())
        # Each scene is a (start, end) timecode pair; take each scene's start.
        return [scene[0].get_seconds() for scene in scene_list]
    except Exception:
        # On any error, return empty list (no reinforcement, but don't fail)
        return []


def _laplacian_score(img_path: Path) -> float:
    """Compute Laplacian variance (sharpness score) for an image."""
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0

    var = cv2.Laplacian(img, cv2.CV_64F).var()
    # Normalize: 0-500 range → 0.0-1.0 (empirical upper bound)
    return min(var / 500.0, 1.0)


def _extract_timestamp(filename: str) -> float | None:
    """Extract timestamp_sec from a filename like 'keyframe_000000123.jpg'."""
    # Katna typically names files like 'keyframe_000000000.jpg'
    # Try to extract the numeric part
    import re
    match = re.search(r"(\d+)", filename)
    if match:
        return float(match.group(1))
    return None
