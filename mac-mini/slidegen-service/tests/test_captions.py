"""Unit tests for captions.py (caption loading and topic-change detection)."""

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
        with patch("captions._embed_texts"):
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

                detect_topic_changes("test_video_id")

                # short_seg should be filtered, so embed_texts should receive 1 text
                mock_embed.assert_called_once_with(["Long"])


# ── PR-G regressions: persisted shape ↔ raw SQL DDL ──────────────────────────


class _FakeCursor:
    def __init__(self, executed):
        self._executed = executed

    def execute(self, sql, params=None):
        self._executed.append((sql, params))

    def close(self):
        pass


class _FakeConn:
    def __init__(self, executed):
        self._executed = executed

    def cursor(self):
        return _FakeCursor(self._executed)

    def commit(self):
        pass

    def close(self):
        pass


def _run_persist_with_fake_db(monkeypatch):
    """Run _persist_segments against a fake psycopg2; return executed SQL."""
    import sys
    import types

    from captions import CaptionSegment, _persist_segments

    executed = []
    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.connect = lambda dsn: _FakeConn(executed)
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub/stub")

    segment = CaptionSegment(from_sec=0.0, to_sec=5.0, text="VERBATIM", bge_embedding=[0.1] * 4)
    _persist_segments("synthvid001", [segment], [])
    return executed


def test_persist_segments_insert_matches_ddl_columns(monkeypatch):
    """Regression (PR-G): the INSERT column list must be a subset of the live
    DDL columns (init DDL minus the 002 text drop).

    Blocks the silent-fail class: the pre-PR-G INSERT wrote to a nonexistent
    bge_embedding column (DDL says embedding) and was swallowed by the blanket
    except — every persist failed silently.
    """
    import re
    from pathlib import Path

    executed = _run_persist_with_fake_db(monkeypatch)
    assert executed, "_persist_segments executed no SQL"
    sql, _params = executed[0]

    insert_cols = {
        col.strip() for col in re.search(r"\(([^)]+)\)\s*VALUES", sql).group(1).split(",")
    }

    # DDL source of truth: init CREATE TABLE minus the 002 text drop.
    repo_root = Path(__file__).resolve().parents[3]
    init_ddl = (
        repo_root / "prisma/migrations/slidegen-init/001_create_slide_tables.sql"
    ).read_text()
    block = re.search(
        r"CREATE TABLE IF NOT EXISTS slide_caption_segments \((.*?)\n\);", init_ddl, re.S
    ).group(1)
    ddl_cols = {m.group(1) for m in re.finditer(r"^\s{2}(\w+)", block, re.M)}
    drop_ddl = (
        repo_root / "prisma/migrations/slidegen-jobs-v2/002_caption_segments_drop_text.sql"
    ).read_text()
    assert "DROP COLUMN IF EXISTS text" in drop_ddl
    ddl_cols.discard("text")

    assert insert_cols <= ddl_cols, f"INSERT columns {insert_cols} not all in DDL {ddl_cols}"
    assert "bge_embedding" not in sql  # the silent-fail bug, pinned


def test_persist_segments_never_stores_verbatim_text(monkeypatch):
    """ADR 0003 D6: no verbatim caption text in slidegen — neither as an INSERT
    column nor riding along in the bound parameters."""
    import re

    executed = _run_persist_with_fake_db(monkeypatch)
    sql, params = executed[0]

    insert_cols = {
        col.strip() for col in re.search(r"\(([^)]+)\)\s*VALUES", sql).group(1).split(",")
    }
    assert "text" not in insert_cols
    assert "VERBATIM" not in [p for p in params if isinstance(p, str)]


def test_persist_segments_writes_only_slidegen_schema(monkeypatch):
    """Write-path rule: this module may write ONLY to slidegen-owned slide_*
    tables (insighta tables are read-only sources)."""
    executed = _run_persist_with_fake_db(monkeypatch)

    for sql, _params in executed:
        if "INSERT" in sql.upper() or "UPDATE" in sql.upper() or "DELETE" in sql.upper():
            assert "slidegen.slide_caption_segments" in sql
