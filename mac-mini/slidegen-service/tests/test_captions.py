"""Unit tests for captions.py (caption loading and topic-change detection)."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_caption_segment_dataclass():
    """CaptionSegment dataclass should have required fields."""
    from captions import CaptionSegment

    segment = CaptionSegment(
        from_sec=10.0,
        to_sec=20.0,
        text="This is a caption segment",
        bge_embedding=[0.1] * 1024,
    )

    assert segment.from_sec == 10.0
    assert segment.to_sec == 20.0
    assert segment.text == "This is a caption segment"
    assert len(segment.bge_embedding) == 1024


def test_caption_topic_point_dataclass():
    """CaptionTopicPoint dataclass should have required fields."""
    from captions import CaptionTopicPoint

    point = CaptionTopicPoint(
        timestamp_sec=30.0,
        topic_label="New topic",
        bge_embedding=[0.2] * 1024,
    )

    assert point.timestamp_sec == 30.0
    assert point.topic_label == "New topic"
    assert len(point.bge_embedding) == 1024


def test_detect_topic_changes_returns_list():
    """detect_topic_changes should return list[CaptionTopicPoint]."""
    from captions import detect_topic_changes

    with patch("captions._load_caption_segments") as mock_load:
        with patch("captions._embed_texts") as mock_embed:
            with patch("captions._persist_segments"):
                mock_load.return_value = []
                result = detect_topic_changes("test_video_id")
                assert isinstance(result, list)


def test_detect_topic_changes_sorted_by_timestamp():
    """Topic points should be sorted by timestamp_sec ascending."""
    from captions import CaptionSegment, detect_topic_changes

    with patch("captions._load_caption_segments") as mock_load:
        with patch("captions._embed_texts") as mock_embed:
            with patch("captions._persist_segments"):
                # Return segments that will trigger topic changes
                seg1 = CaptionSegment(0.0, 5.0, "Topic A", [])
                seg2 = CaptionSegment(5.0, 10.0, "Topic B", [])
                seg3 = CaptionSegment(10.0, 15.0, "Topic C", [])

                mock_load.return_value = [seg1, seg2, seg3]
                # Embeddings: very different between all segments (>0.30 threshold)
                mock_embed.return_value = [
                    [1.0] + [0.0] * 1023,  # Topic A
                    [0.0, 1.0] + [0.0] * 1022,  # Topic B
                    [0.0, 0.0, 1.0] + [0.0] * 1021,  # Topic C
                ]

                result = detect_topic_changes("test_video_id")

                # Check sorted
                for i in range(len(result) - 1):
                    assert result[i].timestamp_sec <= result[i + 1].timestamp_sec


def test_cosine_distance_orthogonal():
    """Orthogonal vectors should have distance ~1.0."""
    from captions import _cosine_distance

    a = [1.0, 0.0]
    b = [0.0, 1.0]
    dist = _cosine_distance(a, b)
    assert 0.99 < dist <= 1.0


def test_cosine_distance_identical():
    """Identical vectors should have distance near 0.0."""
    from captions import _cosine_distance

    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    dist = _cosine_distance(a, b)
    assert dist < 1e-10


def test_cosine_distance_zero_vector():
    """Zero vectors should return 1.0."""
    from captions import _cosine_distance

    a = [0.0, 0.0]
    b = [1.0, 1.0]
    dist = _cosine_distance(a, b)
    assert dist == 1.0


def test_embed_texts_calls_http():
    """_embed_texts should POST to BGE_M3_EMBED_URL and return embeddings."""
    from captions import _embed_texts

    # captions imports httpx lazily inside _embed_texts, so patch the real
    # httpx module (captions has no module-level httpx attribute to patch).
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        mock_post.return_value = mock_response

        result = _embed_texts(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]
        mock_post.assert_called_once()


def test_short_segments_filtered():
    """Segments shorter than MIN_SEGMENT_SEC should be filtered."""
    from captions import CaptionSegment, MIN_SEGMENT_SEC, detect_topic_changes

    with patch("captions._load_caption_segments") as mock_load:
        with patch("captions._embed_texts") as mock_embed:
            with patch("captions._persist_segments"):
                # Long segment + short segment
                long_seg = CaptionSegment(0.0, MIN_SEGMENT_SEC + 1, "Long", [])
                short_seg = CaptionSegment(MIN_SEGMENT_SEC + 1, MIN_SEGMENT_SEC + 2, "Short", [])

                mock_load.return_value = [long_seg, short_seg]
                mock_embed.return_value = [[1.0] * 1024, [0.5] * 1024]

                result = detect_topic_changes("test_video_id")

                # short_seg should be filtered, so embed_texts should receive 1 text
                mock_embed.assert_called_once_with(["Long"])
