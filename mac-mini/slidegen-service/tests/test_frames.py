"""Unit tests for frames.py (candidate frame extraction module)."""

from pathlib import Path
from unittest.mock import MagicMock, patch



def test_frame_candidate_dataclass():
    """FrameCandidate dataclass should have required fields."""
    from frames import FrameCandidate

    candidate = FrameCandidate(
        path=Path("/tmp/frame.jpg"),
        timestamp_sec=10.5,
        section_index=1,
        quality_score=0.75,
        is_scene_boundary=False,
    )

    assert candidate.timestamp_sec == 10.5
    assert candidate.section_index == 1
    assert 0.0 <= candidate.quality_score <= 1.0


def test_extract_candidates_returns_list():
    """extract_candidates should return list[FrameCandidate]."""
    from frames import extract_candidates

    with patch("frames._run_katna") as mock_katna:
        with patch("frames._get_video_duration") as mock_duration:
            with patch("frames._scene_boundaries") as mock_boundaries:
                with patch("frames._recover_timestamps") as mock_recover:
                    frame = Path("/tmp/frame1.jpg")
                    mock_katna.return_value = [frame]
                    mock_duration.return_value = 100.0
                    mock_boundaries.return_value = []
                    mock_recover.return_value = {frame: 12.0}

                    result = extract_candidates(Path("dummy.mp4"))

                    assert isinstance(result, list)
                    if len(result) > 0:
                        from frames import FrameCandidate
                        assert isinstance(result[0], FrameCandidate)


def test_extract_candidates_sorted_by_timestamp():
    """Candidates should be sorted by timestamp_sec ascending."""
    from frames import extract_candidates

    f30 = Path("/tmp/k30.jpg")
    f10 = Path("/tmp/k10.jpg")
    f20 = Path("/tmp/k20.jpg")
    with patch("frames._run_katna") as mock_katna:
        with patch("frames._get_video_duration") as mock_duration:
            with patch("frames._scene_boundaries") as mock_boundaries:
                with patch("frames._recover_timestamps") as mock_recover:
                    # Frames returned in reverse time order; recovery assigns the
                    # true timestamps (NOT parsed from the filename index).
                    mock_katna.return_value = [f30, f10, f20]
                    mock_duration.return_value = 100.0
                    mock_boundaries.return_value = []
                    mock_recover.return_value = {f30: 30.0, f10: 10.0, f20: 20.0}

                    result = extract_candidates(Path("dummy.mp4"))

                    # Check sorted by recovered timestamp
                    for i in range(len(result) - 1):
                        assert result[i].timestamp_sec <= result[i + 1].timestamp_sec


def test_extract_candidates_uses_recovered_not_filename_timestamp():
    """Regression (Bug A): the candidate timestamp must come from video matching,
    NOT from the Katna filename index. A frame named '..._5.jpeg' (extraction
    index 5) that really occurs at 600s must end up at 600s, not 5s."""
    from frames import extract_candidates

    frame = Path("/tmp/lecture_5.jpeg")  # index-5 filename, real time 600s
    with patch("frames._run_katna", return_value=[frame]):
        with patch("frames._get_video_duration", return_value=1200.0):
            with patch("frames._scene_boundaries", return_value=[]):
                with patch("frames._recover_timestamps", return_value={frame: 600.0}):
                    result = extract_candidates(Path("dummy.mp4"))

    assert len(result) == 1
    assert result[0].timestamp_sec == 600.0  # recovered, not the filename's 5
    assert result[0].section_index == 5  # 600/1200*10


def test_rename_with_timestamp_encodes_time():
    """Bug A: the persisted filename must encode the recovered timestamp so it is
    visible to the VLM router, and be readable back by _extract_timestamp."""
    import tempfile

    from frames import _extract_timestamp, _rename_with_timestamp

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "lecture_5.jpeg"
        src.write_bytes(b"x")
        out = _rename_with_timestamp(src, 46.7)

        assert out.exists()
        assert out.name == "keyframe_000000047_00m47s.jpeg"  # round(46.7)=47
        assert _extract_timestamp(out.name) == 47.0


def test_run_katna_globs_jpeg_extension():
    """Regression (Bug B): Katna writes .jpeg by default; globbing only *.jpg
    would silently return zero frames."""
    import sys
    from types import SimpleNamespace

    class FakeWriter:
        def __init__(self, location):
            self.location = location

    class FakeVideo:
        def extract_video_keyframes(self, no_of_frames, file_path, writer):
            # Katna's default extension is .jpeg, not .jpg.
            (Path(writer.location) / "video_0.jpeg").write_bytes(b"x")

    fake_video_mod = SimpleNamespace(Video=FakeVideo)
    fake_writer_mod = SimpleNamespace(KeyFrameDiskWriter=FakeWriter)

    with patch.dict(
        sys.modules,
        {"Katna.video": fake_video_mod, "Katna.writer": fake_writer_mod},
    ):
        from frames import _run_katna

        paths = _run_katna(Path("dummy.mp4"), 1)

    assert len(paths) == 1
    assert paths[0].suffix == ".jpeg"

    import shutil

    shutil.rmtree(paths[0].parent, ignore_errors=True)


def test_fill_coverage_gaps_fills_empty_sections():
    """Timeline-bias mitigation: empty timeline sections get a gap-fill frame
    (Katna clusters frames in early sections, leaving later ones empty)."""
    from frames import FrameCandidate, _fill_coverage_gaps

    duration = 1000.0
    # Only sections 0 and 1 covered; 2..9 are empty.
    existing = [
        FrameCandidate(Path("/tmp/a.jpg"), 50.0, 0, 1.0, False),
        FrameCandidate(Path("/tmp/b.jpg"), 150.0, 1, 1.0, False),
    ]

    def fake_extract(video_path, t, out_dir):
        return Path(f"/tmp/gap_{int(t)}.jpg")

    with patch("frames._extract_frame_at", side_effect=fake_extract):
        with patch("frames._laplacian_score", return_value=0.5):
            added = _fill_coverage_gaps(
                Path("dummy.mp4"), existing, [], duration, Path("/tmp")
            )

    filled_sections = {c.section_index for c in added}
    assert filled_sections == set(range(2, 10))  # all empty sections filled
    # No duplicates of already-covered sections.
    assert 0 not in filled_sections and 1 not in filled_sections


def test_fill_coverage_gaps_prefers_scene_boundary():
    """A gap-fill frame should land on a scene boundary inside the empty section
    when one exists, rather than the section midpoint."""
    from frames import FrameCandidate, _fill_coverage_gaps

    duration = 100.0  # each section spans 10s
    existing = [FrameCandidate(Path("/tmp/a.jpg"), 5.0, 0, 1.0, False)]
    # Boundary at 52s sits inside section 5 (50–60s); midpoint would be 55.
    boundaries = [52.0]

    def fake_extract(video_path, t, out_dir):
        return Path(f"/tmp/gap_{int(t)}.jpg")

    with patch("frames._extract_frame_at", side_effect=fake_extract):
        with patch("frames._laplacian_score", return_value=0.5):
            added = _fill_coverage_gaps(
                Path("dummy.mp4"), existing, boundaries, duration, Path("/tmp")
            )

    sec5 = next(c for c in added if c.section_index == 5)
    assert sec5.timestamp_sec == 52.0  # snapped to the boundary, not midpoint 55
    assert sec5.is_scene_boundary is True


def test_laplacian_score_bounds():
    """Quality score should be in [0.0, 1.0]."""
    from frames import _laplacian_score

    with patch("frames.cv2.imread") as mock_imread:
        import numpy as np

        # Mock image that returns high variance (sharp)
        mock_img = np.ones((100, 100), dtype=np.uint8) * 128
        mock_imread.return_value = mock_img

        with patch("frames.cv2.Laplacian") as mock_laplacian:
            # Return high variance
            mock_laplacian.return_value = MagicMock(var=MagicMock(return_value=1000))

            score = _laplacian_score(Path("/tmp/frame.jpg"))

            assert 0.0 <= score <= 1.0


def test_laplacian_score_handles_none():
    """If image read fails, quality_score should be 0.0."""
    from frames import _laplacian_score

    with patch("frames.cv2.imread", return_value=None):
        score = _laplacian_score(Path("/nonexistent.jpg"))
        assert score == 0.0


def test_scene_boundaries_returns_timestamps():
    """_scene_boundaries should return list of float timestamps."""
    import sys

    from frames import _scene_boundaries

    # scenedetect is imported lazily inside _scene_boundaries, so it is not a
    # module-level attribute of `frames`. Inject a fake scenedetect module so the
    # `from scenedetect import ...` resolves to mocks regardless of the installed
    # scenedetect version.
    fake_scenedetect = MagicMock()
    mock_scene_1 = (MagicMock(get_seconds=MagicMock(return_value=10.0)), MagicMock())
    mock_scene_2 = (MagicMock(get_seconds=MagicMock(return_value=20.0)), MagicMock())
    # _scene_boundaries uses the 0.6+ high-level detect() API.
    fake_scenedetect.detect.return_value = [mock_scene_1, mock_scene_2]

    with patch.dict(sys.modules, {"scenedetect": fake_scenedetect}):
        result = _scene_boundaries(Path("dummy.mp4"))

    assert isinstance(result, list)
    assert all(isinstance(t, float) for t in result)


def test_get_video_duration():
    """_get_video_duration should return duration in seconds."""
    from frames import _get_video_duration

    with patch("frames.cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap_class.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = [
            300,  # frame_count = 300
            30.0,  # fps = 30
        ]

        duration = _get_video_duration(Path("dummy.mp4"))

        assert duration == 10.0  # 300 frames / 30 fps = 10 seconds


def test_run_katna_returns_persistent_paths():
    """Regression: returned frame paths must survive _run_katna's internal
    TemporaryDirectory cleanup (previously returned dangling paths inside a
    deleted dir → cv2.imread None → silent quality_score 0.0)."""
    import sys
    from types import SimpleNamespace

    class FakeWriter:
        def __init__(self, location):
            self.location = location

    class FakeVideo:
        def extract_video_keyframes(self, no_of_frames, file_path, writer):
            # Katna writes frames into the writer's scratch location.
            (Path(writer.location) / "keyframe_000000001.jpg").write_bytes(b"x")

    fake_video_mod = SimpleNamespace(Video=FakeVideo)
    fake_writer_mod = SimpleNamespace(KeyFrameDiskWriter=FakeWriter)

    with patch.dict(
        sys.modules,
        {"Katna.video": fake_video_mod, "Katna.writer": fake_writer_mod},
    ):
        from frames import _run_katna

        paths = _run_katna(Path("dummy.mp4"), 1)

    assert len(paths) == 1
    assert paths[0].exists()  # not dangling
    assert paths[0].read_bytes() == b"x"

    # cleanup the persistent dir this test produced
    import shutil

    shutil.rmtree(paths[0].parent, ignore_errors=True)


def test_extract_timestamp_from_filename():
    """_extract_timestamp should parse numeric timestamp from filename."""
    from frames import _extract_timestamp

    assert _extract_timestamp("keyframe_000000010.jpg") == 10.0
    assert _extract_timestamp("keyframe_000000123.jpg") == 123.0
    assert _extract_timestamp("invalid_name.jpg") is None
