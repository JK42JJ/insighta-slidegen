"""Unit tests for typing_select.py (keyframe selection via CLIP + topic alignment)."""

from pathlib import Path
from unittest.mock import patch


def test_selected_frame_dataclass():
    """SelectedFrame dataclass should have required fields."""
    from frames import FrameCandidate
    from typing_select import SelectedFrame

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    selected = SelectedFrame(
        candidate=candidate,
        clip_embedding=[0.1] * 512,
        is_topic_aligned=False,
        nearest_topic_point=None,
        cosine_distance_to_prev=0.3,
    )

    assert selected.candidate.timestamp_sec == 10.0
    assert len(selected.clip_embedding) == 512
    assert selected.is_topic_aligned is False


def test_select_keyframes_returns_list():
    """select_keyframes should return list[SelectedFrame]."""
    from typing_select import select_keyframes

    with patch("typing_select._encode_candidates") as mock_encode:
        with patch("typing_select._persist_keyframes"):
            mock_encode.return_value = []
            result = select_keyframes([], [])
            assert isinstance(result, list)


def test_select_keyframes_empty_candidates():
    """Empty candidates should return empty list."""
    from typing_select import select_keyframes

    result = select_keyframes([], [])
    assert result == []


def test_select_keyframes_stops_at_target():
    """Selection should stop at TARGET_SELECTED (12) keyframes."""
    from frames import FrameCandidate
    from typing_select import select_keyframes, TARGET_SELECTED

    # Create many candidates (more than TARGET_SELECTED)
    candidates = [
        FrameCandidate(Path(f"/tmp/frame_{i}.jpg"), float(i), 0, 0.8, False)
        for i in range(TARGET_SELECTED + 10)
    ]

    with patch("typing_select._encode_candidates") as mock_encode:
        with patch("typing_select._persist_keyframes"):
            # Distinct one-hot embeddings → mutually orthogonal (cosine distance
            # 1.0 between any pair) so none are deduped and selection reaches the
            # TARGET_SELECTED cap. A constant-valued vector would be collinear and
            # get correctly deduped, leaving far fewer than TARGET_SELECTED.
            mock_encode.return_value = [
                [1.0 if j == i else 0.0 for j in range(512)]
                for i in range(len(candidates))
            ]

            result = select_keyframes(candidates, [])

            assert len(result) == TARGET_SELECTED


def test_cosine_distance_orthogonal():
    """Orthogonal vectors should have distance ~1.0."""
    from typing_select import _cosine_distance

    a = [1.0, 0.0]
    b = [0.0, 1.0]
    dist = _cosine_distance(a, b)
    assert 0.99 < dist <= 1.0


def test_cosine_distance_identical():
    """Identical vectors should have distance near 0.0."""
    from typing_select import _cosine_distance

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    dist = _cosine_distance(a, b)
    assert dist < 1e-10


def test_min_cosine_distance_to_selected_empty():
    """Empty selected list should return 1.0."""
    from typing_select import _min_cosine_distance_to_selected

    vec = [0.1] * 512
    dist = _min_cosine_distance_to_selected(vec, [])
    assert dist == 1.0


def test_find_topic_alignment_within_window():
    """Topic point within TOPIC_ALIGN_WINDOW_SEC should align."""
    from frames import FrameCandidate
    from typing_select import CaptionTopicPoint, _find_topic_alignment

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    topic = CaptionTopicPoint(10.5, "Topic", [0.1] * 1024)  # Within window

    nearest, is_aligned = _find_topic_alignment(candidate, [topic])

    assert is_aligned is True
    assert nearest == topic


def test_find_topic_alignment_outside_window():
    """Topic point outside TOPIC_ALIGN_WINDOW_SEC should not align."""
    from frames import FrameCandidate
    from typing_select import CaptionTopicPoint, _find_topic_alignment

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    topic = CaptionTopicPoint(20.0, "Topic", [0.1] * 1024)  # Outside window (>3s away)

    nearest, is_aligned = _find_topic_alignment(candidate, [topic])

    assert is_aligned is False
    assert nearest is None


def test_select_keyframes_sorted_by_timestamp():
    """Selected frames should be sorted by timestamp_sec ascending."""
    from frames import FrameCandidate
    from typing_select import select_keyframes

    # Create candidates in reverse order
    candidates = [
        FrameCandidate(Path(f"/tmp/frame_{i}.jpg"), float(100 - i), 0, 0.8, False)
        for i in range(5)
    ]

    with patch("typing_select._encode_candidates") as mock_encode:
        with patch("typing_select._persist_keyframes"):
            # Different embeddings
            mock_encode.return_value = [
                [float(i % 512) / 512] * 512 for i in range(len(candidates))
            ]

            result = select_keyframes(candidates, [])

            # Check sorted
            for i in range(len(result) - 1):
                assert result[i].candidate.timestamp_sec <= result[i + 1].candidate.timestamp_sec
