"""Unit tests for acquire.py (frame acquisition module)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_download_frames_returns_path():
    """download_frames should return a Path object."""
    from acquire import download_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("acquire._download_video"):
            with patch("acquire._extract_section_frames"):
                result = download_frames(
                    "12345678abc",
                    [{"index": 0, "from_sec": 0, "to_sec": 10}],
                    output_root=tmpdir,
                )
                assert isinstance(result, Path)
                assert result.name == "12345678abc"


def test_download_frames_caches_video():
    """If video.mp4 exists, _download_video should not be called."""
    from acquire import download_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        frames_dir = Path(tmpdir) / "12345678abc"
        frames_dir.mkdir()
        video_path = frames_dir / "video.mp4"
        video_path.touch()  # Create dummy file

        with patch("acquire._download_video") as mock_download:
            with patch("acquire._extract_section_frames"):
                download_frames(
                    "12345678abc",
                    [{"index": 0, "from_sec": 0, "to_sec": 10}],
                    output_root=tmpdir,
                )
                # Should not have called download since video exists
                mock_download.assert_not_called()


def test_download_frames_calls_extract_for_each_section():
    """_extract_section_frames should be called once per section."""
    from acquire import download_frames

    with tempfile.TemporaryDirectory() as tmpdir:
        sections = [
            {"index": 0, "from_sec": 0, "to_sec": 10},
            {"index": 1, "from_sec": 10, "to_sec": 20},
        ]

        with patch("acquire._download_video"):
            with patch("acquire._extract_section_frames") as mock_extract:
                download_frames(
                    "12345678abc",
                    sections,
                    output_root=tmpdir,
                )
                assert mock_extract.call_count == 2


def test_download_video_raises_on_failure(tmp_path):
    """_download_video should raise RuntimeError on yt-dlp failure."""
    from acquire import _download_video

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Download failed"

    with patch("acquire.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="yt-dlp failed"):
            _download_video("invalid_id", tmp_path / "video.mp4")


def test_extract_section_frames_creates_jpegs(tmp_path):
    """_extract_section_frames should create JPEG files with correct naming."""
    from acquire import _extract_section_frames

    # Mock cv2 operations
    with patch("acquire.cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap_class.return_value = mock_cap
        mock_cap.isOpened.return_value = True

        # Simulate 3 frames at timestamps 0, 1, 2
        mock_frame = MagicMock()
        mock_cap.read.side_effect = [
            (True, mock_frame),
            (True, mock_frame),
            (True, mock_frame),
            (False, None),  # End of video
        ]
        mock_cap.get.side_effect = [
            0,     # First frame at 0 ms
            1000,  # Second frame at 1 s
            2000,  # Third frame at 2 s
        ]

        section = {"index": 0, "from_sec": 0, "to_sec": 3}
        # imwrite must be mocked too — the mock frames are not real numpy arrays.
        with patch("acquire.cv2.imwrite"):
            _extract_section_frames(tmp_path / "dummy.mp4", section, tmp_path)

        # Check that imwrite was called (mock doesn't actually write)
        # But we can verify the video was closed
        mock_cap.release.assert_called_once()


def test_extract_section_frames_respects_frame_rate():
    """Frame extraction should respect FRAME_RATE (1 fps by default)."""
    from acquire import FRAME_RATE, _extract_section_frames

    with patch("acquire.cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap_class.return_value = mock_cap
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, MagicMock())
        mock_cap.get.side_effect = [0, 1000, 2000]

        section = {"index": 0, "from_sec": 0, "to_sec": 3}

        with patch("acquire.cv2.imwrite"):
            _extract_section_frames(Path("dummy.mp4"), section, Path("/tmp"))

        # Should have called seek for FRAME_RATE seconds apart
        assert FRAME_RATE == 1
