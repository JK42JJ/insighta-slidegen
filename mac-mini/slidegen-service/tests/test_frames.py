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
                mock_katna.return_value = [Path("/tmp/frame1.jpg")]
                mock_duration.return_value = 100.0
                mock_boundaries.return_value = []

                result = extract_candidates(Path("dummy.mp4"))

                assert isinstance(result, list)
                if len(result) > 0:
                    from frames import FrameCandidate
                    assert isinstance(result[0], FrameCandidate)


def test_extract_candidates_sorted_by_timestamp():
    """Candidates should be sorted by timestamp_sec ascending."""
    from frames import extract_candidates

    with patch("frames._run_katna") as mock_katna:
        with patch("frames._get_video_duration") as mock_duration:
            with patch("frames._scene_boundaries") as mock_boundaries:
                # Return frames in reverse order
                mock_katna.return_value = [
                    Path("/tmp/keyframe_000000030.jpg"),
                    Path("/tmp/keyframe_000000010.jpg"),
                    Path("/tmp/keyframe_000000020.jpg"),
                ]
                mock_duration.return_value = 100.0
                mock_boundaries.return_value = []

                result = extract_candidates(Path("dummy.mp4"))

                # Check sorted by timestamp
                for i in range(len(result) - 1):
                    assert result[i].timestamp_sec <= result[i + 1].timestamp_sec


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


def test_extract_timestamp_from_filename():
    """_extract_timestamp should parse numeric timestamp from filename."""
    from frames import _extract_timestamp

    assert _extract_timestamp("keyframe_000000010.jpg") == 10.0
    assert _extract_timestamp("keyframe_000000123.jpg") == 123.0
    assert _extract_timestamp("invalid_name.jpg") is None
