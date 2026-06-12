"""PR-H2: prod keyframe persistence (the former Phase-2 TODO stub).

Pins:
  ① the INSERT targets slidegen.slide_keyframes ONLY (slide_* write rule) and
    writes only columns that exist in the prod DDL
  ② section_index derives from the v2 section windows (fallback 0)
  ③ dev mode never touches the DB; persistence failures never fail the
    select stage (best-effort, captions._persist_segments pattern)

All fixtures synthetic (PUBLIC repo rule).
"""

import sys
import types
from unittest.mock import MagicMock

from frames import FrameCandidate
from typing_select import SelectedFrame, _persist_keyframes, _section_index_for

SYNTH_VIDEO_ID = "synthvid001"
SECTIONS = [
    {"index": 0, "from_sec": 0.0, "to_sec": 30.0},
    {"index": 1, "from_sec": 30.0, "to_sec": 60.0},
]


def _frame(t: float) -> SelectedFrame:
    return SelectedFrame(
        candidate=FrameCandidate(
            path="/tmp/synth.jpg",
            timestamp_sec=t,
            section_index=0,
            quality_score=1.0,
            is_scene_boundary=False,
        ),
        contains_graph=True,
        contains_equation=False,
        frame_type="chart",
        summary_hint="synthetic chart",
        is_topic_aligned=False,
        nearest_topic_point=None,
        selection_score=0.91,
    )


def _fake_psycopg2(cursor: MagicMock) -> types.ModuleType:
    mod = types.ModuleType("psycopg2")
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mod.connect = MagicMock(return_value=conn)
    return mod


def test_persist_inserts_into_slide_keyframes_only(monkeypatch):
    cursor = MagicMock()
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(cursor))
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub:stub@localhost:5432/stub")

    _persist_keyframes([_frame(12.0), _frame(45.0)], SYNTH_VIDEO_ID, SECTIONS)

    assert cursor.execute.call_count == 2
    for call, expected_section in zip(cursor.execute.call_args_list, (0, 1)):
        sql, params = call.args
        assert "INSERT INTO slidegen.slide_keyframes" in sql
        # slide_* only — no non-slide table may appear in the statement
        # ("youtube_video_id" the COLUMN is fine; the youtube_videos TABLE is not).
        assert "youtube_videos" not in sql
        assert "video_captions" not in sql and "video_rich_summaries" not in sql
        assert params[0] == SYNTH_VIDEO_ID
        assert params[1] == expected_section
        assert params[3] == "chart"


def test_persist_skips_without_video_id_or_db(monkeypatch):
    cursor = MagicMock()
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(cursor))
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub:stub@localhost:5432/stub")
    _persist_keyframes([_frame(1.0)], None, SECTIONS)
    assert cursor.execute.call_count == 0

    monkeypatch.delenv("DATABASE_URL")
    _persist_keyframes([_frame(1.0)], SYNTH_VIDEO_ID, SECTIONS)
    assert cursor.execute.call_count == 0


def test_persist_failure_never_raises(monkeypatch):
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError("connection reset")
    monkeypatch.setitem(sys.modules, "psycopg2", _fake_psycopg2(cursor))
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub:stub@localhost:5432/stub")
    _persist_keyframes([_frame(1.0)], SYNTH_VIDEO_ID, SECTIONS)  # must not raise


def test_section_index_fallback_zero():
    assert _section_index_for(12.0, SECTIONS) == 0
    assert _section_index_for(45.0, SECTIONS) == 1
    assert _section_index_for(999.0, SECTIONS) == 0
    assert _section_index_for(5.0, None) == 0
