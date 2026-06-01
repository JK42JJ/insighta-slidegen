"""Unit tests for typing_select.py (keyframe selection via a local VLM router)."""

from pathlib import Path
from unittest.mock import patch


def _routing(
    *,
    is_slide=True,
    contains_graph=False,
    contains_equation=False,
    frame_type="diagram",
    summary_hint="hint",
    confidence=0.9,
):
    """Build a RoutingMetadata with sensible defaults (kept import-local)."""
    from typing_select import RoutingMetadata

    return RoutingMetadata(
        is_slide=is_slide,
        contains_graph=contains_graph,
        contains_equation=contains_equation,
        frame_type=frame_type,
        summary_hint=summary_hint,
        confidence=confidence,
    )


def _candidates(n):
    from frames import FrameCandidate

    return [FrameCandidate(Path(f"/tmp/frame_{i}.jpg"), float(i), 0, 0.8, False) for i in range(n)]


def test_routing_metadata_dataclass():
    """RoutingMetadata carries the ADR 0001 routing fields."""
    r = _routing(contains_graph=True, frame_type="chart")
    assert r.is_slide is True
    assert r.contains_graph is True
    assert r.frame_type == "chart"


def test_selected_frame_dataclass():
    """SelectedFrame carries routing metadata (no clip_embedding — ADR 0001)."""
    from frames import FrameCandidate
    from typing_select import SelectedFrame

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    sf = SelectedFrame(
        candidate=candidate,
        contains_graph=True,
        contains_equation=False,
        frame_type="chart",
        summary_hint="revenue chart",
        is_topic_aligned=False,
        nearest_topic_point=None,
        selection_score=0.88,
    )
    assert sf.candidate.timestamp_sec == 10.0
    assert sf.contains_graph is True
    assert sf.selection_score == 0.88
    assert not hasattr(sf, "clip_embedding")


def test_select_keyframes_returns_list():
    """select_keyframes returns a list."""
    from typing_select import select_keyframes

    with patch("typing_select._route_with_vlm", return_value=[]):
        result = select_keyframes([], [])
        assert isinstance(result, list)


def test_select_keyframes_empty_candidates():
    """Empty candidates short-circuit to an empty list (no VLM call)."""
    from typing_select import select_keyframes

    with patch("typing_select._route_with_vlm") as mock_route:
        result = select_keyframes([], [])
        assert result == []
        mock_route.assert_not_called()


def test_select_keyframes_filters_non_slides():
    """Frames the router marks is_slide=False are excluded."""
    from typing_select import select_keyframes

    candidates = _candidates(4)
    routings = [
        _routing(is_slide=True),
        _routing(is_slide=False),
        _routing(is_slide=True),
        _routing(is_slide=False),
    ]
    with patch("typing_select._route_with_vlm", return_value=routings):
        result = select_keyframes(candidates, [])
        assert len(result) == 2


def test_select_keyframes_stops_at_target_max():
    """Selection caps at TARGET_SELECTED_MAX even with more is_slide frames."""
    from typing_select import TARGET_SELECTED_MAX, select_keyframes

    candidates = _candidates(TARGET_SELECTED_MAX + 10)
    routings = [_routing(is_slide=True) for _ in candidates]
    with patch("typing_select._route_with_vlm", return_value=routings):
        result = select_keyframes(candidates, [])
        assert len(result) == TARGET_SELECTED_MAX


def test_select_keyframes_carries_routing_metadata():
    """Routing flags (graph/equation/type/hint/score) propagate onto SelectedFrame."""
    from typing_select import select_keyframes

    candidates = _candidates(1)
    routings = [
        _routing(
            contains_graph=True,
            contains_equation=True,
            frame_type="chart",
            summary_hint="GraphDB layout",
            confidence=0.77,
        )
    ]
    with patch("typing_select._route_with_vlm", return_value=routings):
        result = select_keyframes(candidates, [])
        assert len(result) == 1
        sf = result[0]
        assert sf.contains_graph is True
        assert sf.contains_equation is True
        assert sf.frame_type == "chart"
        assert sf.summary_hint == "GraphDB layout"
        assert sf.selection_score == 0.77


def test_select_keyframes_sorted_by_timestamp():
    """Selected frames are returned sorted by timestamp_sec ascending."""
    from frames import FrameCandidate
    from typing_select import select_keyframes

    candidates = [FrameCandidate(Path(f"/tmp/f_{i}.jpg"), float(100 - i), 0, 0.8, False) for i in range(5)]
    routings = [_routing(is_slide=True) for _ in candidates]
    with patch("typing_select._route_with_vlm", return_value=routings):
        result = select_keyframes(candidates, [])
        for i in range(len(result) - 1):
            assert result[i].candidate.timestamp_sec <= result[i + 1].candidate.timestamp_sec


def test_find_topic_alignment_within_window():
    """A topic point within TOPIC_ALIGN_WINDOW_SEC aligns the frame."""
    from frames import FrameCandidate
    from typing_select import CaptionTopicPoint, _find_topic_alignment

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    topic = CaptionTopicPoint(10.5, "Topic", [0.1] * 1024)
    nearest, is_aligned = _find_topic_alignment(candidate, [topic])
    assert is_aligned is True
    assert nearest == topic


def test_find_topic_alignment_outside_window():
    """A topic point outside the window does not align the frame."""
    from frames import FrameCandidate
    from typing_select import CaptionTopicPoint, _find_topic_alignment

    candidate = FrameCandidate(Path("/tmp/frame.jpg"), 10.0, 0, 0.8, False)
    topic = CaptionTopicPoint(20.0, "Topic", [0.1] * 1024)
    nearest, is_aligned = _find_topic_alignment(candidate, [topic])
    assert is_aligned is False
    assert nearest is None


def test_select_keyframes_aligns_topic_points():
    """A nearby topic point marks the selected frame topic-aligned."""
    from frames import FrameCandidate
    from typing_select import CaptionTopicPoint, select_keyframes

    candidates = [FrameCandidate(Path("/tmp/f.jpg"), 10.0, 0, 0.8, False)]
    topic = CaptionTopicPoint(11.0, "Topic", [0.1] * 1024)
    with patch("typing_select._route_with_vlm", return_value=[_routing(is_slide=True)]):
        result = select_keyframes(candidates, [topic])
        assert result[0].is_topic_aligned is True
        assert result[0].nearest_topic_point == topic
