"""
Wide-net candidate frame extraction using Katna.

Primary extractor: Katna VideoFrameSelector — pulls ~80 candidate frames
per video by sampling at regular intervals and retaining frames with high
information content.  The goal is a *wide net*: cast broadly, accept some
junk.  Downstream selection (select.py / pgvector dedup) will narrow to ~12.

PySceneDetect is an optional reinforcement pass only: it may flag additional
scene-boundary timestamps but is NOT the primary selector.

IMPORTANT — timestamps are recovered, not parsed from filenames:
Katna's KeyFrameDiskWriter names files "<stem>_<seq>.jpeg" where <seq> is a
0,1,2,... extraction index, NOT a wall-clock time. Treating that index as a
timestamp (the previous behaviour) put every frame at the wrong moment in the
video, breaking section_index, scene-boundary alignment and downstream VLM
routing. We instead recover each keyframe's true timestamp by fingerprint-
matching it back against the source video, then encode that time into the
persisted filename so it is visible to the VLM router.

Entry function: extract_candidates(video_path, target_count) → list[FrameCandidate]
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Target candidate count — wide net before embedding-based selection.
KATNA_TARGET_COUNT = 80
TOPIC_ALIGN_WINDOW_SEC = 3.0

# --- timestamp recovery tuning -------------------------------------------
# The index is built by a single SEQUENTIAL decode pass (no seeking). Seeking
# via cap.set(POS_MSEC) is non-deterministic on corrupt / B-frame-heavy files
# (returns wrong or garbage frames), which made an earlier seek-based recovery
# unstable. A forward-only read is deterministic and robust on partial files.
INDEX_STEP_SEC = 0.5     # sample the source video every N seconds for the index
DESC_SIZE = 32           # fingerprint resolution (grayscale DESC_SIZE×DESC_SIZE)
LAPLACIAN_NORM = 500.0   # empirical upper bound for sharpness normalisation
NUM_SECTIONS = 10        # timeline buckets for section_index / coverage

# Katna's keyframe writer emits .jpeg by default, but the extension can vary by
# version/codec — glob both rather than silently matching zero files.
_KATNA_GLOBS = ("*.jpeg", "*.jpg", "*.png")


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
        1. Run Katna to produce a wide candidate set (~target_count), copied to a
           persistent dir (extensions vary, so several globs are tried).
        2. Recover each keyframe's TRUE timestamp by matching it back against the
           source video, and rename the persisted file to encode that time.
        3. Compute quality_score (Laplacian variance) and section_index.
        4. Optional reinforcement: run scenedetect ContentDetector and flag
           frames within ±TOPIC_ALIGN_WINDOW_SEC of a scene boundary.
        5. Return the list sorted by timestamp_sec ascending.

    Note: is_scene_boundary is advisory only — final selection is done by the VLM
    router (typing_select.py) + BGE-M3 caption topic-change alignment.
    """
    # Get video duration
    duration = _get_video_duration(video_path)

    # Step 1: Run Katna to extract ~target_count candidates
    katna_frames = _run_katna(video_path, target_count)

    # Step 2: Recover the true timestamp of each keyframe (Katna only gives an
    # extraction index in the filename) and rename to encode it.
    timestamps = _recover_timestamps(video_path, katna_frames, duration)

    # Step 3: Detect scene boundaries (optional reinforcement)
    scene_boundaries = _scene_boundaries(video_path)

    # Step 4: Build FrameCandidate list with quality scores
    candidates = []
    for frame_path in katna_frames:
        timestamp_sec = timestamps.get(frame_path)
        if timestamp_sec is None:
            continue

        # Encode the recovered time into the filename so it is visible to the VLM
        # router (e.g. keyframe_000000046_00m46s.jpg).
        frame_path = _rename_with_timestamp(frame_path, timestamp_sec)

        # Compute quality score (Laplacian variance)
        quality_score = _laplacian_score(frame_path)

        # Check if this frame is near a scene boundary
        is_boundary = any(
            abs(timestamp_sec - boundary) <= TOPIC_ALIGN_WINDOW_SEC
            for boundary in scene_boundaries
        )

        # Assign section_index from timestamp proportion
        section_index = (
            min(int(timestamp_sec / duration * NUM_SECTIONS), NUM_SECTIONS - 1)
            if duration > 0
            else 0
        )

        candidate = FrameCandidate(
            path=frame_path,
            timestamp_sec=timestamp_sec,
            section_index=section_index,
            quality_score=quality_score,
            is_scene_boundary=is_boundary,
        )
        candidates.append(candidate)

    # Step 5: Sort by timestamp
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


def _patch_katna_empty_cluster() -> None:
    """Guard Katna against the empty-cluster crash on low-variety video.

    Katna selects keyframes by KMeans(n_clusters=N) over per-frame grayscale
    histograms. On a static/low-variety video (e.g. a lecture slide deck) many
    histograms are near-identical, so KMeans produces fewer than N distinct
    clusters; the empty cluster's index array is empty and Katna's
    __get_best_images_index_from_each_cluster__ calls np.argmax([]) → ValueError
    ("attempt to get argmax of an empty sequence"). We monkeypatch that method to
    skip empty clusters (returning fewer frames than requested — the honest
    outcome). Behaviour for non-empty clusters is byte-for-byte identical.

    The target name ends in "__" → it is a dunder-style name and is NOT
    name-mangled, so we assign to the literal attribute.
    """
    try:
        from katna.image_selector import ImageSelector
    except ImportError:
        return

    if getattr(ImageSelector, "_slidegen_empty_cluster_patched", False):
        return

    def _patched_best_index(self, files, files_clusters_index_array):
        filtered = []
        for cluster_i in np.arange(len(files_clusters_index_array)):
            curr_row = files_clusters_index_array[cluster_i][0]
            if len(curr_row) == 0:  # the guard upstream lacks
                continue
            n_images = np.arange(len(curr_row))
            variance_laplacians = self._ImageSelector__get_laplacian_scores(
                files, n_images
            )
            filtered.append(curr_row[np.argmax(variance_laplacians)])
        return filtered

    ImageSelector.__get_best_images_index_from_each_cluster__ = _patched_best_index
    ImageSelector._slidegen_empty_cluster_patched = True


def _run_katna(video_path: Path, target_count: int) -> list[Path]:
    """Run Katna to extract keyframes. Returns list of persistent frame paths.

    Katna writes into a scratch directory; we copy the frames into a persistent
    temp dir BEFORE that scratch dir is cleaned up. Returning paths from inside
    the `with tempfile.TemporaryDirectory()` block yields dangling paths once the
    directory is deleted on function return (the caller would read missing files
    → cv2.imread None → quality_score 0.0, silently). The caller owns cleanup of
    the returned directory.
    """
    try:
        from katna.video import Video
        from katna.writer import KeyFrameDiskWriter
    except ImportError as e:
        raise ImportError(
            "katna not installed. Install with: pip install katna"
        ) from e

    _patch_katna_empty_cluster()

    out_dir = Path(tempfile.mkdtemp(prefix="slidegen_katna_"))
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

        # Copy extracted frames out of the scratch dir before it is deleted.
        # Katna's output extension varies by version, so glob several.
        persisted: list[Path] = []
        srcs: list[Path] = []
        for pattern in _KATNA_GLOBS:
            srcs.extend(Path(tmpdir).glob(pattern))
        for src in sorted(srcs):
            dst = out_dir / src.name
            shutil.copyfile(src, dst)
            persisted.append(dst)
        return persisted


def _descriptor(bgr: np.ndarray) -> np.ndarray:
    """Small grayscale fingerprint used for frame-to-frame MSE matching."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (DESC_SIZE, DESC_SIZE)).astype(np.float32)


def _mse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean((a - b) ** 2))


def _build_video_index(video_path: Path) -> list[tuple[float, np.ndarray]]:
    """Build a (timestamp_sec, descriptor) index via ONE sequential decode pass.

    Reads the video forward only — no seeking — sampling roughly every
    INDEX_STEP_SEC. Forward decode is deterministic and survives corrupt/partial
    files where cap.set(POS_MSEC) returns wrong frames. Timestamps come from the
    decoded frame's own position (POS_MSEC), falling back to frame_index / fps.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    stride = max(1, int(round(fps * INDEX_STEP_SEC))) if fps > 0 else 1

    index: list[tuple[float, np.ndarray]] = []
    frame_i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_i % stride == 0:
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            t = pos_ms / 1000.0 if pos_ms > 0 else (frame_i / fps if fps > 0 else 0.0)
            index.append((round(t, 2), _descriptor(frame)))
        frame_i += 1
    cap.release()
    return index


def _recover_timestamps(
    video_path: Path,
    frame_paths: list[Path],
    duration: float,
) -> dict[Path, float]:
    """Recover the true timestamp (seconds) of each Katna keyframe.

    Katna filenames carry only an extraction index, so we build a fingerprint
    index of the source video by a single forward decode pass and match each
    keyframe to its nearest-MSE sample. Returns {frame_path: timestamp_sec};
    frames that cannot be read are omitted. Note: on visually repetitive video
    (e.g. near-identical slides) the match resolves to the correct slide's time
    range, which is the intended granularity.
    """
    if not frame_paths or duration <= 0:
        return {}

    index = _build_video_index(video_path)
    result: dict[Path, float] = {}
    if not index:
        return result

    for fp in frame_paths:
        img = cv2.imread(str(fp))
        if img is None:
            continue
        d = _descriptor(img)
        best_t, _ = min(index, key=lambda c: _mse(d, c[1]))
        result[fp] = best_t
    return result


def _rename_with_timestamp(frame_path: Path, timestamp_sec: float) -> Path:
    """Rename a keyframe so its filename encodes the recovered timestamp.

    Format: keyframe_<sec:09d>_<MM>m<SS>s<suffix>. The zero-padded integer
    seconds keeps filenames timestamp-sortable AND lets _extract_timestamp read
    the time back; the MMmSSs part is human/VLM readable. Returns the new path
    (or the original if the rename fails — recovery must never hard-fail).
    """
    total = int(round(timestamp_sec))
    minutes, seconds = divmod(total, 60)
    new_name = f"keyframe_{total:09d}_{minutes:02d}m{seconds:02d}s{frame_path.suffix}"
    new_path = frame_path.with_name(new_name)
    if new_path == frame_path:
        return frame_path
    try:
        frame_path.rename(new_path)
        return new_path
    except OSError:
        return frame_path


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
    # Normalize: 0-LAPLACIAN_NORM range → 0.0-1.0 (empirical upper bound)
    return min(var / LAPLACIAN_NORM, 1.0)


def _extract_timestamp(filename: str) -> float | None:
    """Read the timestamp (seconds) back from a timestamp-encoded filename.

    Filenames are encoded by _rename_with_timestamp as
    'keyframe_<sec>_<MM>m<SS>s.jpg'; the leading numeric group is the seconds.
    Returns None if the name carries no number.
    """
    match = re.search(r"(\d+)", filename)
    if match:
        return float(match.group(1))
    return None
