"""Unit + acceptance tests for frames.py (PySceneDetect-primary extraction).

Covers the ADR 0002 §7 port:
    D1 — PySceneDetect ContentDetector PRIMARY (Katna retired)
    D3 — CPU downsample (pHash near-dup merge + time-even cut) as a pure stage
    D6 — interval time-provenance (t_start/t_end + [MMmSSs-MMmSSs] filenames)
plus the recall-first invariant (ADR 0003 D5) measured as the G4 acceptance
criterion (ADR 0004): full timeline coverage + zero missed transitions.

Synthetic videos are generated with cv2.VideoWriter (MJPG/.avi — the most
portable codec in headless OpenCV builds; tests skip if the build cannot
write video). Each scene is a distinct seeded-noise pattern, so scene cuts are
unambiguous for ContentDetector and scenes are far apart in pHash space.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("scenedetect")

from frames import (  # noqa: E402
    DOWNSAMPLE_TARGET_COUNT,
    NUM_SECTIONS,
    FrameCandidate,
    VideoDurationMismatchError,
    _gap_fill_specs,
    _get_video_duration,
    _laplacian_score,
    _section_index,
    compute_phash,
    downsample_candidates,
    extract_candidates,
    format_interval_filename,
    merge_near_duplicates,
    phash_distance,
    time_even_cut,
    validate_video_duration,
)

FPS = 10
FRAME_SIZE = (320, 240)  # (w, h)
# Filename format per ADR 0002 D6: keyframe_{idx}_[MMmSSs-MMmSSs].jpeg
INTERVAL_NAME_RE = re.compile(
    r"^keyframe_\d{4}_\[\d{2,}m\d{2}s-\d{2,}m\d{2}s\]\.jpeg$"
)


def _scene_pattern(seed: int) -> np.ndarray:
    """A deterministic per-scene noise frame (distinct in pHash space)."""
    w, h = FRAME_SIZE
    return np.random.RandomState(42 + seed).randint(
        0, 256, (h, w, 3), dtype=np.uint8
    )


def _write_video(path: Path, n_scenes: int, scene_sec: float, fps: int = FPS) -> None:
    """Write a synthetic video of n_scenes equal-length noise scenes."""
    w, h = FRAME_SIZE
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV build cannot write MJPG video")
    for i in range(n_scenes):
        frame = _scene_pattern(i)
        for _ in range(int(round(scene_sec * fps))):
            writer.write(frame)
    writer.release()


@pytest.fixture(scope="module")
def scene_video(tmp_path_factory) -> tuple[Path, list[float], float]:
    """10 scenes × 3s = 30s — a cut at every decile boundary."""
    path = tmp_path_factory.mktemp("vid") / "scenes.avi"
    _write_video(path, n_scenes=10, scene_sec=3.0)
    boundaries = [i * 3.0 for i in range(1, 10)]  # internal cuts
    return path, boundaries, 30.0


@pytest.fixture(scope="module")
def sparse_video(tmp_path_factory) -> tuple[Path, list[float], float]:
    """2 scenes × 10s = 20s — a single cut; most deciles have no scene start."""
    path = tmp_path_factory.mktemp("vid") / "sparse.avi"
    _write_video(path, n_scenes=2, scene_sec=10.0)
    return path, [10.0], 20.0


@pytest.fixture(scope="module")
def static_video(tmp_path_factory) -> tuple[Path, float]:
    """1 scene × 20s — zero cuts (the case that crashed Katna)."""
    path = tmp_path_factory.mktemp("vid") / "static.avi"
    _write_video(path, n_scenes=1, scene_sec=20.0)
    return path, 20.0


def _decile_covered_by_intervals(
    candidates: list[FrameCandidate], duration: float, section: int
) -> bool:
    """A decile counts as covered if any candidate interval overlaps it."""
    lo = section / NUM_SECTIONS * duration
    hi = (section + 1) / NUM_SECTIONS * duration
    return any(c.t_start < hi and c.t_end > lo for c in candidates)


# ----------------------------------------------------------------
# FrameCandidate dataclass (backward compatibility + D6 interval fields)
# ----------------------------------------------------------------

def test_frame_candidate_dataclass_backward_compatible():
    """Positional 5-arg construction (used by other test suites and consumers)
    must keep working; interval fields default to the capture instant."""
    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.5, 1, 0.75, False)

    assert candidate.timestamp_sec == 10.5
    assert candidate.section_index == 1
    assert 0.0 <= candidate.quality_score <= 1.0
    assert candidate.t_start == 10.5  # defaults to timestamp_sec (ADR 0002 D6)
    assert candidate.t_end == 10.5


def test_frame_candidate_explicit_interval_preserved():
    """Explicit t_start/t_end are kept as given (including a 0.0 t_start)."""
    c = FrameCandidate(Path("/x.jpg"), 5.0, 0, 1.0, True, t_start=0.0, t_end=12.5)
    assert c.t_start == 0.0
    assert c.t_end == 12.5


# ----------------------------------------------------------------
# G4 acceptance — recall-first (ADR 0003 D5, ADR 0004 G4)
# ----------------------------------------------------------------

def test_g4_full_timeline_coverage(scene_video):
    """G4(a): every decile of the timeline is represented in the candidates."""
    path, _, duration = scene_video
    result = extract_candidates(path)

    assert len(result) > 0
    for section in range(NUM_SECTIONS):
        assert _decile_covered_by_intervals(result, duration, section), (
            f"decile {section} has no covering candidate interval"
        )


def test_g4_zero_missed_transitions(scene_video):
    """G4(b): every synthetic scene boundary has a candidate within tolerance.
    A missed slide transition is the only unrecoverable failure (ADR 0003 D5)."""
    path, boundaries, _ = scene_video
    result = extract_candidates(path)

    tolerance = 0.5
    for boundary in boundaries:
        assert any(
            abs(c.timestamp_sec - boundary) <= tolerance for c in result
        ), f"scene transition at {boundary}s has no candidate within ±{tolerance}s"


def test_g4_downsample_never_drops_last_scene_group_representative():
    """G4(c): the downsample keeps >=1 representative per pHash scene group,
    and the kept frame's interval spans the whole merged group."""
    # 3 visual groups: hash 0 (x3 near-dups), hash with 1 bit (still group A),
    # then two far-apart hashes (distinct groups B, C).
    cands = [
        FrameCandidate(Path("/a0.jpg"), 0.0, 0, 0.5, True, t_start=0.0, t_end=2.0),
        FrameCandidate(Path("/a1.jpg"), 2.0, 0, 0.9, False, t_start=2.0, t_end=4.0),
        FrameCandidate(Path("/a2.jpg"), 4.0, 0, 0.4, False, t_start=4.0, t_end=6.0),
        FrameCandidate(Path("/b.jpg"), 6.0, 1, 0.8, True, t_start=6.0, t_end=8.0),
        FrameCandidate(Path("/c.jpg"), 8.0, 1, 0.7, True, t_start=8.0, t_end=10.0),
    ]
    hashes = [0b0, 0b1, 0b10, (1 << 64) - 1, 0xAAAAAAAAAAAAAAAA]

    merged = merge_near_duplicates(cands, hashes)

    assert len(merged) == 3  # one representative per visual group — never zero
    group_a = merged[0]
    assert group_a.path == Path("/a1.jpg")  # sharpest member kept
    assert group_a.t_start == 0.0 and group_a.t_end == 6.0  # spans the group
    assert group_a.is_scene_boundary is True  # boundary provenance survives

    # The time-even cut never removes the only representative of a group when
    # the merged count is within target.
    kept = time_even_cut(merged, target=DOWNSAMPLE_TARGET_COUNT)
    assert kept == merged


def test_g4_sparse_cuts_gap_fill_covers_every_decile(sparse_video):
    """G4(a) on sparse-cut video: deciles without a scene start are covered by
    gap-fill grabs (wide net) / expanded intervals (after merge)."""
    path, boundaries, duration = sparse_video
    result = extract_candidates(path)

    for section in range(NUM_SECTIONS):
        assert _decile_covered_by_intervals(result, duration, section)
    # And the single transition is still captured.
    assert any(abs(c.timestamp_sec - boundaries[0]) <= 0.5 for c in result)


def test_static_video_full_coverage_no_crash(static_video):
    """Zero-cut video (the Katna empty-cluster crash case) must extract cleanly
    with full interval coverage of the timeline."""
    path, duration = static_video
    result = extract_candidates(path)

    assert len(result) >= 1
    for section in range(NUM_SECTIONS):
        assert _decile_covered_by_intervals(result, duration, section)


def test_gap_fill_specs_cover_all_empty_deciles():
    """Wide-net gap-fill (pure): every decile without a scene start gets one
    midpoint grab carrying the decile's bounds as its interval."""
    duration = 100.0
    # Scene starts only in deciles 0 and 5.
    specs = [(0.0, 0.0, 50.0, True), (50.0, 50.0, 100.0, True)]

    fills = _gap_fill_specs(specs, duration)

    filled = {_section_index(t, duration) for t, _, _, _ in fills}
    assert filled == set(range(NUM_SECTIONS)) - {0, 5}
    for t, lo, hi, is_boundary in fills:
        assert lo <= t <= hi
        assert is_boundary is False
        assert hi - lo == pytest.approx(duration / NUM_SECTIONS)


def test_downsample_coverage_repair_restores_lost_section():
    """The cut may not blank a section the merge still covered: the repair pass
    re-adds the sharpest merged frame of any lost section (recall-first)."""
    # 30 distinct-hash frames in section 0 (sharp) + 1 frame in section 9 (dull).
    cands = [
        FrameCandidate(Path(f"/s0_{i}.jpg"), float(i), 0, 0.9, True)
        for i in range(30)
    ]
    lone = FrameCandidate(Path("/s9.jpg"), 95.0, 9, 0.1, True)

    # Alternating all-zero / all-one hashes: adjacent distance 64 → no merging,
    # so the cut (target=4) is forced to drop frames.
    alternating = [0 if i % 2 == 0 else (1 << 64) - 1 for i in range(31)]
    with patch("frames.cv2.imread", return_value=np.zeros((8, 8), dtype=np.uint8)):
        with patch("frames.compute_phash", side_effect=alternating):
            kept = downsample_candidates([*cands, lone], target=4)

    assert any(c.path == Path("/s9.jpg") for c in kept), (
        "cut dropped the last representative of section 9 and repair did not restore it"
    )


# ----------------------------------------------------------------
# pHash unit tests (D3)
# ----------------------------------------------------------------

def test_compute_phash_identical_images_zero_distance():
    img = _scene_pattern(0)
    assert phash_distance(compute_phash(img), compute_phash(img.copy())) == 0


def test_compute_phash_near_duplicate_small_distance():
    """A brightness shift + mild noise is a near-duplicate (small distance)."""
    img = _scene_pattern(1)
    shifted = cv2.convertScaleAbs(img, alpha=1.0, beta=12)
    d = phash_distance(compute_phash(img), compute_phash(shifted))
    assert d <= 6


def test_compute_phash_distinct_images_large_distance():
    a = compute_phash(_scene_pattern(2))
    b = compute_phash(_scene_pattern(3))
    assert phash_distance(a, b) > 16


def test_compute_phash_accepts_grayscale():
    gray = cv2.cvtColor(_scene_pattern(4), cv2.COLOR_BGR2GRAY)
    h = compute_phash(gray)
    assert 0 <= h < (1 << 64)


def test_merge_near_duplicates_does_not_merge_across_dissimilar_frame():
    """Two similar frames separated in time by a different frame stay distinct
    (merge is adjacency-based — similar slides far apart are different events)."""
    cands = [
        FrameCandidate(Path("/a.jpg"), 0.0, 0, 0.5, True),
        FrameCandidate(Path("/x.jpg"), 5.0, 0, 0.5, True),
        FrameCandidate(Path("/a2.jpg"), 10.0, 1, 0.5, True),
    ]
    hashes = [0b0, (1 << 64) - 1, 0b1]
    merged = merge_near_duplicates(cands, hashes)
    assert len(merged) == 3


def test_merge_near_duplicates_length_mismatch_raises():
    with pytest.raises(ValueError):
        merge_near_duplicates(
            [FrameCandidate(Path("/a.jpg"), 0.0, 0, 0.5, True)], []
        )


def test_time_even_cut_deterministic_and_count():
    """Same input → same output (pure); 200 frames cut to exactly 60."""
    cands = [
        FrameCandidate(Path(f"/f{i}.jpg"), float(i), i % NUM_SECTIONS, (i % 7) / 7, False)
        for i in range(200)
    ]
    a = time_even_cut(cands, DOWNSAMPLE_TARGET_COUNT)
    b = time_even_cut(list(cands), DOWNSAMPLE_TARGET_COUNT)
    assert a == b
    assert len(a) == DOWNSAMPLE_TARGET_COUNT
    # Under target → identity.
    assert time_even_cut(cands[:10], DOWNSAMPLE_TARGET_COUNT) == cands[:10]


def test_time_even_cut_invalid_target_raises():
    with pytest.raises(ValueError):
        time_even_cut([], 0)


# ----------------------------------------------------------------
# Interval filenames (D6)
# ----------------------------------------------------------------

def test_format_interval_filename():
    name = format_interval_filename(3, 65.0, 125.0)
    assert name == "keyframe_0003_[01m05s-02m05s].jpeg"
    assert ":" not in name  # illegal on Windows
    assert "~" not in name  # '-' separates the bounds


def test_format_interval_filename_minutes_over_99():
    name = format_interval_filename(0, 6000.0, 6010.0)
    assert name == "keyframe_0000_[100m00s-100m10s].jpeg"


def test_extracted_files_use_interval_filename_format(scene_video):
    """Every persisted candidate file follows keyframe_{idx}_[MMmSSs-MMmSSs].jpeg
    and its interval is consistent (t_start <= timestamp <= t_end ordering)."""
    path, _, _ = scene_video
    result = extract_candidates(path)

    for c in result:
        assert INTERVAL_NAME_RE.match(c.path.name), c.path.name
        assert c.path.exists()
        assert c.t_start <= c.t_end


def test_extract_candidates_sorted_by_timestamp(scene_video):
    path, _, _ = scene_video
    result = extract_candidates(path)
    for i in range(len(result) - 1):
        assert result[i].timestamp_sec <= result[i + 1].timestamp_sec


# ----------------------------------------------------------------
# Duration-validation gate (post-download, pre-extraction)
# ----------------------------------------------------------------

def test_duration_gate_truncated_video_fails_loud(static_video):
    """A 20s file presented as a 60s video (partial download) must fail loud
    BEFORE extraction."""
    path, _ = static_video
    with pytest.raises(VideoDurationMismatchError, match="duration mismatch"):
        extract_candidates(path, expected_duration_sec=60.0)


def test_duration_gate_passes_within_tolerance(static_video):
    path, duration = static_video
    actual = validate_video_duration(path, expected_duration_sec=duration)
    assert actual == pytest.approx(duration, abs=0.5)


def test_duration_gate_rejects_nonpositive_expected(static_video):
    path, _ = static_video
    with pytest.raises(ValueError):
        validate_video_duration(path, expected_duration_sec=0.0)


# ----------------------------------------------------------------
# Carried-over helpers
# ----------------------------------------------------------------

def test_get_video_duration():
    """_get_video_duration should return frame_count / fps."""
    with patch("frames.cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap_class.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [300, 30.0]  # frame_count, fps

        assert _get_video_duration(Path("dummy.mp4")) == 10.0


def test_section_index_buckets():
    assert _section_index(0.0, 100.0) == 0
    assert _section_index(55.0, 100.0) == 5
    assert _section_index(100.0, 100.0) == NUM_SECTIONS - 1  # clamped
    assert _section_index(10.0, 0.0) == 0  # degenerate duration


def test_laplacian_score_bounds():
    """Quality score should be in [0.0, 1.0] even for very sharp images."""
    with patch("frames.cv2.imread") as mock_imread:
        mock_imread.return_value = np.ones((100, 100), dtype=np.uint8) * 128
        with patch("frames.cv2.Laplacian") as mock_laplacian:
            mock_laplacian.return_value = MagicMock(var=MagicMock(return_value=1000))
            score = _laplacian_score(Path("/tmp/frame.jpg"))
            assert 0.0 <= score <= 1.0


def test_laplacian_score_handles_none():
    """If image read fails, quality_score should be 0.0."""
    with patch("frames.cv2.imread", return_value=None):
        assert _laplacian_score(Path("/nonexistent.jpg")) == 0.0
