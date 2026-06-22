"""
Wide-net candidate frame extraction — PySceneDetect PRIMARY (ADR 0002 D1).

Stage-1 extractor for the CV pipeline. PySceneDetect `ContentDetector` cuts the
video into scenes with **exact decimal timecodes** in a single decode pass and
full timeline coverage (no front bias, no static-video crash). Katna — the
previous primary — is retired (ADR 0002 D1), which also removes the entire
fingerprint timestamp-recovery machinery (it existed only because Katna encoded
an extraction *index*, not a time, into filenames).

Pipeline shape (ADR 0002 D3, ADR 0003 D5 — recall-first):

    1. WIDE NET  — the scene start plus duration-proportional mid-scene samples
       per detected scene, plus gap-fill grabs so every timeline decile is
       covered (~target 200; over-extraction is fine — a *missed* slide
       transition is the only unrecoverable failure).
    2. CPU DOWNSAMPLE — pHash near-duplicate merge + time-even cut to ~60,
       implemented as a separate pure function (`downsample_candidates`) so the
       wide net and the cut are independently testable.

Time provenance (ADR 0002 D6): every candidate carries an interval
[`t_start`, `t_end`] (seconds). The pHash merge expands the kept frame's
interval to span the whole merged group [min start, max end]. Persisted
filenames encode the interval as `keyframe_{idx}_[MMmSSs-MMmSSs].jpeg`
(no ':' — illegal on Windows; '-' instead of '~').

A post-download duration-validation gate (`validate_video_duration`) fails
loud on gross mismatch between the file's actual duration and the expected
duration (partial / truncated download).

Entry function: extract_candidates(video_path, ...) → list[FrameCandidate]
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# --- wide net / downsample targets (ADR 0002 D3: ~200 → ~60) ---------------
WIDE_NET_TARGET_COUNT = 200
DOWNSAMPLE_TARGET_COUNT = 60

# Timeline buckets (deciles) for section_index / coverage gap-fill.
NUM_SECTIONS = 10

# PySceneDetect ContentDetector sensitivity (ADR 0002 D1). ContentDetector
# measures the FRAME-AVERAGED HSV delta between frames, so the right threshold is
# CONTENT-TYPE dependent (troubleshooting #24):
#   - lecture-hall CAMERA footage has lots of motion → a high threshold (≈27)
#     still finds the slide cuts;
#   - a WHITE-BACKGROUND SCREENCAST changes only a small text region between
#     slides, so a real slide swap's averaged delta is SMALL — at threshold 15
#     (let alone 27) those transitions go undetected and many minutes of distinct
#     slides COLLAPSE into a single scene (measured: a ~23-minute span of dozens of
#     real slides detected as ONE scene), silently dropping the slides between.
# A single global default must therefore err LOW and let the downstream pHash
# merge + time-even cut DEDUP the resulting over-segmentation (recall-first: a
# missed transition is unrecoverable, an extra near-dup is cheaply deduped).
# Measured on a 53-minute screencast: th=8 → 82 scenes / full 10/10-decile
# coverage, vs the whole first third collapsing into one scene at th=15.
SCENE_DETECT_THRESHOLD = 8.0  # was 15 (under-segments white-bg screencast); see #24

# Within a scene we sample MULTIPLE candidate instants, not just the scene start.
# On lecture-hall recordings scene cuts track CAMERA motion, so the start frame
# can be the speaker while a figure/equation appears MID-scene; a start-only grab
# would MISS it (the only unrecoverable failure, ADR 0003 D5). Over-sampling is
# free on the recall axis here — the pHash merge collapses the near-dups and the
# downsample cuts the global set, so the extra frames never reach the VLM.
SCENE_SAMPLE_STEP_SEC = 2.5      # cadence of candidate samples within a scene
MAX_SAMPLES_PER_SCENE = 10       # baseline cap for normal-length scenes
# A flat per-scene cap STARVES an under-segmented long scene (e.g. a white-bg
# screencast whose swaps slipped under the detector → 23 min in one scene):
# capping at 10 keeps ~1 frame per 2.3 min and drops the slides between. So the
# cap scales with scene DURATION — never let the sampling gap exceed this — as a
# defense-in-depth net even when the threshold mis-segments (troubleshooting #24).
LONG_SCENE_MAX_GAP_SEC = 20.0    # in a long scene, sample at least once per ~20s

# --- pHash (CPU downsample stage, ADR 0002 D3) ------------------------------
# 32×32 DCT → top-left 8×8 low-frequency block → 64-bit hash. Implemented with
# cv2.dct + numpy (opencv-python does not ship cv2.img_hash — that lives in
# opencv-contrib — and a self-contained DCT keeps the hash identical across
# environments).
PHASH_DCT_SIZE = 32
PHASH_HASH_SIZE = 8
# Hamming distance (out of 64 bits) at or below which two frames are merged as
# near-duplicates. 10/64 is the common pHash near-dup band; recall-first says
# err low (merge less) rather than high.
PHASH_NEAR_DUP_MAX_DISTANCE = 10

# --- duration-validation gate -----------------------------------------------
# Relative mismatch above which the downloaded file is considered truncated /
# partial. 10%: yt-dlp metadata durations and container durations differ by
# seconds, not minutes; a partial download is typically off by far more.
DURATION_MISMATCH_TOLERANCE = 0.10

# Sharpness normalisation for quality_score (empirical upper bound, carried
# over from the previous implementation).
LAPLACIAN_NORM = 500.0

JPEG_SUFFIX = ".jpeg"


class VideoDurationMismatchError(RuntimeError):
    """Downloaded video duration grossly differs from the expected duration."""


@dataclass
class FrameCandidate:
    """A single candidate frame with quality metadata and time provenance.

    `t_start` / `t_end` (ADR 0002 D6) are the interval of video time this frame
    represents — initially its enclosing scene; widened by the pHash merge to
    span the whole merged group. They default to `timestamp_sec` so existing
    positional construction (5 args) keeps working for consumers.
    """
    path: Path
    timestamp_sec: float
    section_index: int
    quality_score: float          # 0.0 – 1.0; Laplacian sharpness
    is_scene_boundary: bool       # True if this frame sits on a PySceneDetect cut
    t_start: float = field(default=-1.0)
    t_end: float = field(default=-1.0)
    # figure-bearing YOLO box count, set by preselect_candidates; numerize ranks
    # in-window frames by this (figure frames over text/title). Default 0.
    fig_box_count: int = field(default=0)

    def __post_init__(self) -> None:
        if self.t_start < 0:
            self.t_start = self.timestamp_sec
        if self.t_end < 0:
            self.t_end = self.timestamp_sec


def extract_candidates(
    video_path: Path,
    target_count: int = WIDE_NET_TARGET_COUNT,
    downsample_to: int = DOWNSAMPLE_TARGET_COUNT,
    expected_duration_sec: float | None = None,
) -> list[FrameCandidate]:
    """
    Extract candidate frames: PySceneDetect wide net → CPU downsample.

    Algorithm:
        1. Duration gate — if expected_duration_sec is given, fail loud when the
           file's actual duration grossly mismatches it (partial download).
        2. PySceneDetect ContentDetector (SCENE_DETECT_THRESHOLD) → scene list
           with exact timecodes; the scene start plus duration-proportional
           mid-scene samples, each carrying the scene's [t_start, t_end]
           interval (recall-first — a mid-scene figure is not missed).
        3. Recall-first gap-fill (ADR 0003 D5): every timeline decile with no
           candidate gets a grab at its midpoint so the VLM sees the full talk
           even on sparse-cut / static video.
        4. Decode all candidate frames in ONE forward pass (no seeking — seeks
           are non-deterministic on corrupt/partial files).
        5. CPU downsample (ADR 0002 D3): pHash near-dup merge (interval
           expansion) + time-even cut to ~downsample_to. Never drops the last
           representative of a merged group.
        6. Persist survivors as keyframe_{idx}_[MMmSSs-MMmSSs].jpeg, sorted by
           timestamp_sec ascending.

    `target_count` is a soft wide-net target: the wide net is never truncated
    below the detected scene count (recall-first — dropping a scene start could
    lose a transition); the downsample stage is the only cut.
    """
    duration = _get_video_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"Video has no readable duration: {video_path}")

    if expected_duration_sec is not None:
        validate_video_duration(video_path, expected_duration_sec, duration=duration)

    # Step 2: scenes (exact decimal timecodes; full-timeline coverage).
    scenes = _detect_scenes(video_path)
    if not scenes:
        scenes = [(0.0, duration)]

    # Multiple specs per scene (timestamp, t_start, t_end, is_scene_boundary):
    # the scene start (the transition) plus duration-proportional mid-scene
    # samples so a figure that appears mid-scene survives (recall-first).
    specs: list[tuple[float, float, float, bool]] = []
    for start, end in scenes:
        specs.extend(_scene_sample_specs(start, end))

    # Step 3: recall-first decile gap-fill.
    specs.extend(_gap_fill_specs(specs, duration))
    specs.sort(key=lambda s: s[0])

    # Step 4: single forward-pass decode of all requested timestamps.
    out_dir = Path(tempfile.mkdtemp(prefix="slidegen_frames_"))
    grabbed = _grab_frames(video_path, [s[0] for s in specs], out_dir)

    candidates: list[FrameCandidate] = []
    for (t, t_start, t_end, is_boundary), frame_path in zip(specs, grabbed):
        if frame_path is None:
            continue
        candidates.append(
            FrameCandidate(
                path=frame_path,
                timestamp_sec=round(t, 2),
                section_index=_section_index(t, duration),
                quality_score=_laplacian_score(frame_path),
                is_scene_boundary=is_boundary,
                t_start=round(t_start, 2),
                t_end=round(t_end, 2),
            )
        )

    # Step 5: CPU downsample (pure function — independently tested).
    kept = downsample_candidates(candidates, target=downsample_to)

    # Step 6: persist survivors under the interval filename format (D6) and
    # remove merged-away frames from disk.
    kept_paths = {c.path for c in kept}
    for c in candidates:
        if c.path not in kept_paths:
            c.path.unlink(missing_ok=True)
    kept.sort(key=lambda c: c.timestamp_sec)
    for idx, c in enumerate(kept):
        c.path = _rename_with_interval(c.path, idx, c.t_start, c.t_end)
    return kept


# ----------------------------------------------------------------
# Duration-validation gate
# ----------------------------------------------------------------

def validate_video_duration(
    video_path: Path,
    expected_duration_sec: float,
    tolerance: float = DURATION_MISMATCH_TOLERANCE,
    duration: float | None = None,
) -> float:
    """Fail loud when the file's actual duration grossly mismatches expected.

    Guards against partial/truncated downloads reaching extraction (where they
    would silently produce a deck missing the tail of the talk). Returns the
    actual duration on success; raises VideoDurationMismatchError on gross
    mismatch.
    """
    actual = _get_video_duration(video_path) if duration is None else duration
    if expected_duration_sec <= 0:
        raise ValueError("expected_duration_sec must be > 0")
    if abs(actual - expected_duration_sec) / expected_duration_sec > tolerance:
        raise VideoDurationMismatchError(
            f"Video duration mismatch for {video_path.name}: actual {actual:.1f}s "
            f"vs expected {expected_duration_sec:.1f}s (tolerance "
            f"{tolerance:.0%}) — likely a partial/truncated download"
        )
    return actual


# ----------------------------------------------------------------
# Wide net — PySceneDetect + decile gap-fill
# ----------------------------------------------------------------

def _detect_scenes(video_path: Path) -> list[tuple[float, float]]:
    """Detect scenes via PySceneDetect ContentDetector (PRIMARY — ADR 0002 D1).

    Returns [(start_sec, end_sec), ...] with exact decimal timecodes.
    `start_in_scene=True` makes a cut-free (static) video return one scene
    spanning the whole timeline instead of an empty list.
    """
    # PySceneDetect 0.6+ high-level API (detect() wraps open_video+SceneManager).
    from scenedetect import ContentDetector, detect

    scene_list = detect(
        str(video_path),
        ContentDetector(threshold=SCENE_DETECT_THRESHOLD),
        start_in_scene=True,
    )
    return [(_timecode_seconds(s), _timecode_seconds(e)) for s, e in scene_list]


def _timecode_seconds(tc) -> float:
    """FrameTimecode → seconds across scenedetect versions.

    0.7 deprecates get_seconds() in favor of the `seconds` property; 0.6 only
    has get_seconds().
    """
    seconds = getattr(tc, "seconds", None)
    return float(seconds) if seconds is not None else float(tc.get_seconds())


def _scene_sample_specs(
    start: float, end: float
) -> list[tuple[float, float, float, bool]]:
    """Candidate (timestamp, t_start, t_end, is_scene_boundary) specs for one scene.

    Always emits the scene START (the transition frame, is_scene_boundary=True),
    then evenly-spaced mid-scene samples. The per-scene sample count is
    duration-proportional: the spacing never exceeds LONG_SCENE_MAX_GAP_SEC, so an
    under-segmented long scene is densely sampled instead of starved at a flat cap
    (troubleshooting #24). Every sample carries the WHOLE scene interval
    [start, end] as its provenance (ADR 0002 D6); the pHash merge collapses the
    near-dups and widens the survivor's interval. Short scenes (<= one step)
    collapse to just the start, so there is no regression vs start-only behaviour.
    """
    specs = [(start, start, end, True)]
    span = max(end - start, 0.0)
    if span <= SCENE_SAMPLE_STEP_SEC:
        return specs
    # Cap scales with duration so the gap stays <= LONG_SCENE_MAX_GAP_SEC; for a
    # normal scene MAX_SAMPLES_PER_SCENE dominates. `-1` accounts for the start.
    cap = max(MAX_SAMPLES_PER_SCENE, int(span // LONG_SCENE_MAX_GAP_SEC) + 1)
    n_mid = min(int(span // SCENE_SAMPLE_STEP_SEC), cap - 1)
    if n_mid <= 0:
        return specs
    step = span / (n_mid + 1)
    for k in range(1, n_mid + 1):
        t = start + step * k
        if t < end - 0.5:  # guard so a mid sample never coincides with the next cut
            specs.append((t, start, end, False))
    return specs


def _section_index(timestamp_sec: float, duration: float) -> int:
    """Map a timestamp to its [0, NUM_SECTIONS) timeline bucket."""
    if duration <= 0:
        return 0
    return min(int(timestamp_sec / duration * NUM_SECTIONS), NUM_SECTIONS - 1)


def _gap_fill_specs(
    specs: list[tuple[float, float, float, bool]],
    duration: float,
) -> list[tuple[float, float, float, bool]]:
    """Specs for one midpoint grab per empty timeline decile (recall-first).

    Sparse-cut / static video leaves whole deciles without a scene start; the
    VLM would never see those parts of the talk. Each fill carries the decile's
    own bounds as its interval (it represents that stretch of timeline, not an
    instant). ADR 0003 D5: full-timeline coverage is the acceptance bar.
    """
    if duration <= 0:
        return []
    covered = {_section_index(t, duration) for t, _, _, _ in specs}
    fills: list[tuple[float, float, float, bool]] = []
    for section in range(NUM_SECTIONS):
        if section in covered:
            continue
        lo = section / NUM_SECTIONS * duration
        hi = (section + 1) / NUM_SECTIONS * duration
        fills.append(((lo + hi) / 2, lo, hi, False))
    return fills


def _grab_frames(
    video_path: Path,
    timestamps: list[float],
    out_dir: Path,
) -> list[Path | None]:
    """Decode the frames nearest each timestamp in ONE forward pass.

    Forward-only decode (no cap.set seeking) is deterministic and survives
    corrupt/partial files where POS_MSEC seeks return wrong frames. Input
    timestamps must be sorted ascending; returns one path (or None) per input,
    in input order. Files are written with provisional names; the caller
    renames survivors to the interval format after the downsample.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    results: list[Path | None] = [None] * len(timestamps)
    next_i = 0
    frame_i = 0
    while next_i < len(timestamps):
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        t = frame_i / fps if fps > 0 else float(frame_i)
        # Save this frame for every pending timestamp it has reached.
        while next_i < len(timestamps) and t >= timestamps[next_i]:
            dst = out_dir / f"wide_{next_i:04d}{JPEG_SUFFIX}"
            if cv2.imwrite(str(dst), frame):
                results[next_i] = dst
            next_i += 1
        frame_i += 1
    cap.release()
    return results


# ----------------------------------------------------------------
# CPU downsample — pHash near-dup merge + time-even cut (ADR 0002 D3)
# ----------------------------------------------------------------

def compute_phash(image: np.ndarray) -> int:
    """64-bit perceptual hash: 32×32 grayscale DCT, top-left 8×8 vs median.

    Self-contained cv2.dct implementation (opencv-python has no cv2.img_hash;
    see PHASH_DCT_SIZE comment). Deterministic across platforms.
    """
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(image, (PHASH_DCT_SIZE, PHASH_DCT_SIZE)).astype(np.float32)
    dct = cv2.dct(small)
    low = dct[:PHASH_HASH_SIZE, :PHASH_HASH_SIZE].flatten()
    median = np.median(low)
    bits = low > median
    h = 0
    for bit in bits:
        h = (h << 1) | int(bit)
    return h


def phash_distance(a: int, b: int) -> int:
    """Hamming distance between two 64-bit pHashes."""
    return int(bin(a ^ b).count("1"))


def merge_near_duplicates(
    candidates: list[FrameCandidate],
    hashes: list[int],
    max_distance: int = PHASH_NEAR_DUP_MAX_DISTANCE,
) -> list[FrameCandidate]:
    """Merge runs of perceptually near-identical frames; expand intervals.

    Walks the candidates in timestamp order and merges each frame into the
    current group while its pHash is within max_distance of the group
    representative's hash. The kept frame is the group's sharpest
    (quality_score); its interval expands to span the whole merged group
    [min t_start, max t_end] (ADR 0002 D6) so the represented range is never
    lost. Only adjacent-in-time frames merge — two visually similar slides far
    apart in the talk stay distinct.
    """
    if not candidates:
        return []
    if len(candidates) != len(hashes):
        raise ValueError("candidates and hashes must be the same length")

    order = sorted(range(len(candidates)), key=lambda i: candidates[i].timestamp_sec)
    merged: list[FrameCandidate] = []
    group_rep_hash = hashes[order[0]]
    group = [candidates[order[0]]]
    for i in order[1:]:
        if phash_distance(group_rep_hash, hashes[i]) <= max_distance:
            group.append(candidates[i])
        else:
            merged.append(_collapse_group(group))
            group_rep_hash = hashes[i]
            group = [candidates[i]]
    merged.append(_collapse_group(group))
    return merged


def _collapse_group(group: list[FrameCandidate]) -> FrameCandidate:
    """Collapse a near-dup group to its sharpest member with the spanned interval."""
    rep = max(group, key=lambda c: c.quality_score)
    rep.t_start = min(c.t_start for c in group)
    rep.t_end = max(c.t_end for c in group)
    # A group containing a scene boundary keeps that provenance on the survivor.
    rep.is_scene_boundary = any(c.is_scene_boundary for c in group)
    return rep


def time_even_cut(
    candidates: list[FrameCandidate], target: int
) -> list[FrameCandidate]:
    """Deterministic time-even cut to ~target frames.

    Splits the candidate list (timestamp order) into `target` even buckets and
    keeps the sharpest frame of each non-empty bucket. Pure + deterministic:
    same input → same output. Every bucket that had a frame keeps one, so the
    cut thins dense stretches instead of erasing sparse ones (coverage is
    preserved — recall-first, ADR 0003 D5).
    """
    if target <= 0:
        raise ValueError("target must be > 0")
    if len(candidates) <= target:
        return list(candidates)

    ordered = sorted(candidates, key=lambda c: c.timestamp_sec)
    kept: list[FrameCandidate] = []
    n = len(ordered)
    for b in range(target):
        lo = b * n // target
        hi = (b + 1) * n // target
        bucket = ordered[lo:hi]
        if bucket:
            kept.append(max(bucket, key=lambda c: c.quality_score))
    return kept


def downsample_candidates(
    candidates: list[FrameCandidate],
    target: int = DOWNSAMPLE_TARGET_COUNT,
) -> list[FrameCandidate]:
    """CPU downsample stage (ADR 0002 D3): pHash merge then time-even cut.

    Reads each candidate's pixels once to hash it; otherwise pure (no mutation
    of dropped candidates, no other I/O). Frames whose image cannot be read are
    dropped (they cannot feed the VLM anyway). Returns the kept candidates
    sorted by timestamp_sec.

    Coverage guarantee (recall-first, ADR 0003 D5): any timeline section that
    was represented after the merge is still represented after the cut — the
    repair pass re-adds the sharpest merged frame of a lost section, slightly
    overshooting `target` rather than ever blanking a decile.
    """
    hashable: list[FrameCandidate] = []
    hashes: list[int] = []
    for c in candidates:
        img = cv2.imread(str(c.path))
        if img is None:
            continue
        hashable.append(c)
        hashes.append(compute_phash(img))

    merged = merge_near_duplicates(hashable, hashes)
    kept = time_even_cut(merged, target)

    # Coverage repair: never let the cut blank a section the merge still covered.
    kept_sections = {c.section_index for c in kept}
    for c in sorted(merged, key=lambda c: -c.quality_score):
        if c.section_index not in kept_sections:
            kept.append(c)
            kept_sections.add(c.section_index)

    return sorted(kept, key=lambda c: c.timestamp_sec)


# ----------------------------------------------------------------
# Persistence helpers
# ----------------------------------------------------------------

def format_interval_filename(
    idx: int, t_start: float, t_end: float, suffix: str = JPEG_SUFFIX
) -> str:
    """Interval filename per ADR 0002 D6: keyframe_{idx}_[MMmSSs-MMmSSs].jpeg.

    ':' is illegal on Windows → MMmSSs; '-' separates the bounds (not '~').
    """
    return f"keyframe_{idx:04d}_[{_mmss(t_start)}-{_mmss(t_end)}]{suffix}"


def _mmss(t_sec: float) -> str:
    """Format seconds as zero-padded MMmSSs (minutes may exceed 99)."""
    total = int(round(t_sec))
    minutes, seconds = divmod(total, 60)
    return f"{minutes:02d}m{seconds:02d}s"


def _rename_with_interval(
    frame_path: Path, idx: int, t_start: float, t_end: float
) -> Path:
    """Rename a kept frame to the D6 interval format; never hard-fails."""
    new_path = frame_path.with_name(
        format_interval_filename(idx, t_start, t_end, frame_path.suffix)
    )
    if new_path == frame_path:
        return frame_path
    try:
        frame_path.rename(new_path)
        return new_path
    except OSError:
        return frame_path


# ----------------------------------------------------------------
# Shared helpers (carried over)
# ----------------------------------------------------------------

def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds (frame count / fps)."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    if fps <= 0:
        return 0.0
    return frame_count / fps


def _laplacian_score(img_path: Path) -> float:
    """Compute Laplacian variance (sharpness score) for an image, 0.0–1.0."""
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0

    var = cv2.Laplacian(img, cv2.CV_64F).var()
    # Normalize: 0-LAPLACIAN_NORM range → 0.0-1.0 (empirical upper bound)
    return min(var / LAPLACIAN_NORM, 1.0)
