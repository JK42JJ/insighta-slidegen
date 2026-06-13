"""Stage-artifact sink — per-stage JSON dump for pipeline review.

Privacy: the real youtube_video_id must NEVER appear in the tree (only the
anonymous index). No-op when artifacts_dir is None (existing behavior).
"""

import json

from frames import FrameCandidate
from observability import StageArtifactSink
from typing_select import SelectedFrame


def _selected(ts: float, kind: str = "chart") -> SelectedFrame:
    return SelectedFrame(
        candidate=FrameCandidate(f"/tmp/f_{int(ts)}.jpg", ts, 0, 0.9, True),
        contains_graph=True,
        contains_equation=False,
        frame_type=kind,
        summary_hint="synthetic hint",
        is_topic_aligned=True,
        nearest_topic_point=None,
        selection_score=0.88,
    )


class _Fig:
    def __init__(self, fid, kind, bbox=None, struct=None, latex=None):
        self.cv_figure_id = fid
        self.kind = kind
        self.bbox = bbox
        self.struct = struct
        self.extracted_latex = latex
        self.extraction_conf = 0.9
        self.verification_status = "pending"
        self.timestamp_sec = 12
        self.png_path = f"/tmp/{fid}.png"


def test_sink_writes_stage_tree_with_counts(tmp_path):
    sink = StageArtifactSink(tmp_path, "V02")
    sink.keyframes(578, [_selected(10), _selected(44, "diagram")])
    sink.detect_and_numerize(
        [
            _Fig("f1", "chart", bbox={"x": 0, "y": 0, "w": 5, "h": 5},
                 struct={"chart_type": "line", "series": []}),
            _Fig("f2", "equation", bbox={"x": 1, "y": 1, "w": 4, "h": 4}, latex="E=mc^2"),
        ]
    )
    sink.write_manifest()

    kf = json.loads((tmp_path / "01-keyframes" / "selection.json").read_text())
    assert kf["candidate_count"] == 578
    assert kf["selected_count"] == 2
    assert kf["selected"][0]["frame_type"] == "chart"

    boxes = json.loads((tmp_path / "02-detect" / "boxes.json").read_text())
    assert len(boxes) == 2

    data = json.loads((tmp_path / "04-numerize" / "data.json").read_text())
    assert len(data["charts"]) == 1
    assert len(data["formulas"]) == 1

    manifest = (tmp_path / "MANIFEST.md").read_text()
    assert "578 candidates" in manifest
    assert "2 selected" in manifest


def test_sink_is_noop_without_dir(tmp_path):
    sink = StageArtifactSink(None, "V02")
    sink.keyframes(10, [_selected(1)])
    sink.detect_and_numerize([])
    sink.write_manifest()
    # Nothing written, no crash.
    assert list(tmp_path.iterdir()) == []


def test_sink_persists_source_crops_for_fidelity_3panel(tmp_path):
    """The crop|struct|render fidelity review needs the SOURCE crops, which were
    ephemeral before (frames working dir). detect_and_numerize must copy each
    figure's crop PNG into 02-detect/crops/ (leaf name only). Regression: the
    V02 after-run could not be 3-panel-reviewed because crops weren't persisted."""
    src_dir = tmp_path / "work" / "crops"
    src_dir.mkdir(parents=True)
    figs = []
    for i in range(3):
        p = src_dir / f"keyframe_{i:04d}_crop0.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 16)  # stand-in crop bytes
        f = _Fig(f"f{i}", "diagram", bbox={"x": 0, "y": 0, "w": 5, "h": 5},
                 struct={"diagram_type": "flow", "nodes": [], "edges": []})
        f.png_path = str(p)
        figs.append(f)

    sink = StageArtifactSink(tmp_path / "tree", "V02")
    sink.detect_and_numerize(figs)
    sink.write_manifest()

    crops = sorted((tmp_path / "tree" / "02-detect" / "crops").glob("*.png"))
    assert len(crops) == 3
    assert {c.name for c in crops} == {f"keyframe_{i:04d}_crop0.png" for i in range(3)}
    assert crops[0].read_bytes().startswith(b"\x89PNG")  # bytes copied intact
    assert "3 source crops" in (tmp_path / "tree" / "MANIFEST.md").read_text()


def test_sink_crop_persist_skips_missing_files(tmp_path):
    """A figure whose crop file is gone must not abort the dump (best-effort)."""
    fig = _Fig("f1", "chart", bbox={"x": 0, "y": 0, "w": 1, "h": 1},
               struct={"chart_type": "line", "series": []})
    fig.png_path = "/tmp/does-not-exist-crop.png"
    sink = StageArtifactSink(tmp_path, "V02")
    sink.detect_and_numerize([fig])  # no crash
    crops_dir = tmp_path / "02-detect" / "crops"
    assert not crops_dir.exists() or list(crops_dir.iterdir()) == []


def test_sink_strips_video_id_from_frame_and_crop_paths(tmp_path):
    """PUBLIC-repo rule: frame/crop paths live under
    /tmp/slidegen-frames/<youtube_id>/… — only the leaf filename may be
    written, never the id-bearing directory (regression: the V02 sample run
    surfaced the full path leaking into the stage JSON)."""
    yt_id = "sSjeDITAyYx"  # synthetic 11-char id (fixture only)

    class _Frame:
        def __init__(self, p):
            self.path = p
            self.timestamp_sec = 10.0

    class _Sel:
        candidate = _Frame(f"/tmp/slidegen-frames/{yt_id}/0_0.jpg")
        frame_type = "chart"
        selection_score = 0.9
        is_topic_aligned = True
        summary_hint = "h"
        contains_graph = True
        contains_equation = False

    fig = _Fig("f1", "chart", bbox={"x": 0, "y": 0, "w": 5, "h": 5},
               struct={"chart_type": "line", "series": []})
    fig.png_path = f"/tmp/slidegen-frames/{yt_id}/crops/c0.png"

    sink = StageArtifactSink(tmp_path, "V02")
    sink.keyframes(5, [_Sel()])
    sink.detect_and_numerize([fig])
    sink.write_manifest()

    blob = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    assert yt_id not in blob  # the id-bearing dir must never appear
    assert "0_0.jpg" in blob and "c0.png" in blob  # leaf names are fine
    assert "V02" in blob
