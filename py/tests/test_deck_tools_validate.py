"""Smoke tests for the vendored deck validator (py/deck_tools/validate_deck.py).

Exercises the analyze()/slides() logic on minimal synthetic slide XML — no
node, no pptxgenjs, no real deck needed. Goal: prove the vendored validator's
overflow and meta-text detection actually fire (ADR 0003 D7 smoke contract).
"""

import io
import zipfile

from deck_tools.validate_deck import EMU, META, PAGE_W, TIMESTAMP, analyze, slides

# Page width in EMU ≈ 12,193,714 (13.333" × 914,400). TOL is 30,000 EMU.
PAGE_W_EMU = int(PAGE_W * EMU)

# A shape comfortably inside the page: 1" × 1" at (1", 2").
IN_X = int(1.0 * EMU)
IN_Y = int(2.0 * EMU)
IN_CX = int(1.0 * EMU)
IN_CY = int(1.0 * EMU)

# A shape whose right edge lands ~2" past the page edge (well beyond TOL).
OUT_X = PAGE_W_EMU - int(0.5 * EMU)
OUT_CX = int(2.5 * EMU)


def _sp(x: int, y: int, cx: int, cy: int, text: str) -> str:
    """Minimal <p:sp> matching validate_deck's OFF/EXT/AT regexes."""
    return (
        "<p:sp>"
        f'<a:off x="{x}" y="{y}" />'
        f'<a:ext cx="{cx}" cy="{cy}" />'
        f"<a:t>{text}</a:t>"
        "</p:sp>"
    )


def _slide_xml(*shapes: str) -> str:
    return "<p:cSld>" + "".join(shapes) + "</p:cSld>"


def test_analyze_flags_horizontal_overflow():
    xml = _slide_xml(_sp(OUT_X, IN_Y, OUT_CX, IN_CY, "본문이 슬라이드 밖으로 넘친다"))
    result = analyze(xml)
    assert result["overflow"], "shape past the right page edge must be reported as overflow"


def test_analyze_clean_shape_has_no_overflow():
    xml = _slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, "페이지 안에 들어가는 본문"))
    result = analyze(xml)
    assert result["overflow"] == []
    assert result["chars"] > 0


def test_meta_text_and_timestamp_detection():
    meta_xml = _slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, "유튜브 영상에서 발췌한 내용"))
    ts_xml = _slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, "자세한 내용은 3:07 참조"))
    clean_xml = _slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, "컨테이너는 환경을 코드로 고정한다"))

    assert META.search(analyze(meta_xml)["body"]) is not None
    assert TIMESTAMP.search(analyze(ts_xml)["body"]) is not None

    clean_body = analyze(clean_xml)["body"]
    assert META.search(clean_body) is None
    assert TIMESTAMP.search(clean_body) is None


def test_meta_is_provenance_only_not_domain_subject():
    """Provenance-only META: domain subject words ('영상 제작', '유튜브 콘텐츠') must
    NOT trip the gate (over-flag fix), while real provenance phrasing still does."""
    for subject in ("영상 제작 워크플로우", "유튜브 콘텐츠 전략", "영상 편집 도구"):
        body = analyze(_slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, subject)))["body"]
        assert META.search(body) is None, f"domain subject over-flagged: {subject}"
    for provenance in ("이 영상에서는 다룬다", "본 강의 자료입니다", "채널 구독 부탁드립니다"):
        body = analyze(_slide_xml(_sp(IN_X, IN_Y, IN_CX, IN_CY, provenance)))["body"]
        assert META.search(body) is not None, f"provenance not caught: {provenance}"


def test_slides_sorted_numerically_not_lexically():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in (10, 2, 1):
            z.writestr(f"ppt/slides/slide{n}.xml", _slide_xml())
        z.writestr("ppt/slides/_rels/slide1.xml.rels", "<rels/>")  # must be ignored
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        assert slides(z) == [
            "ppt/slides/slide1.xml",
            "ppt/slides/slide2.xml",
            "ppt/slides/slide10.xml",
        ]
