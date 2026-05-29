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

from dataclasses import dataclass
from pathlib import Path

# Target candidate count — wide net before embedding-based selection.
KATNA_TARGET_COUNT = 80


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

    TODO: implement using katna + opencv; scenedetect import is optional.
    """
    raise NotImplementedError(
        f"TODO: extract_candidates video_path={video_path} target_count={target_count}"
    )
