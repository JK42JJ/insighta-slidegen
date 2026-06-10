#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_deck.py v2 — '잘 만들었는지'를 사람 눈이 아니라 코드가 판정한다.
약한 모델(Sonnet 등)도 이 판정을 통과할 때까지 고치면 동일 품질에 수렴한다.

사용: python validate_deck.py deck.pptx [--min-slides 12] [--lenient]
하드 검사(FAIL): 1)오버플로 2)분량(기본 12장) 3)메타 표현(영상/출처/별첨/타임스탬프)
  4)간지/저밀도(표지 제외, 본문 글자수 미만) 5)세로 빈 공간(위만 차고 아래 빔)
정보성: 장표별 글자수 범위, 네이티브 표/차트, 이미지 수.  --lenient면 4·5는 경고만.
"""
import sys, re, zipfile

EMU = 914400.0
PAGE_W, PAGE_H = 13.333, 7.5
TOL = 30000
SP = re.compile(r'<p:sp>.*?</p:sp>', re.S)
OFF = re.compile(r'<a:off x="(-?\d+)" y="(-?\d+)"\s*/>')
EXT = re.compile(r'<a:ext cx="(\d+)" cy="(\d+)"\s*/>')
AT = re.compile(r'<a:t>(.*?)</a:t>', re.S)
META = re.compile(r'영상|출처\s*영상|동반\s*별첨|별첨|VIDEO\s*DIGEST|채널명|유튜브|youtube', re.I)
TIMESTAMP = re.compile(r'\b\d{1,2}:\d{2}\b')
DARK_BG = ("0B1220", "16213E")

def slides(z):
    names = [n for n in z.namelist() if re.match(r'ppt/slides/slide\d+\.xml$', n)]
    return sorted(names, key=lambda n: int(re.search(r'(\d+)', n.split('/')[-1]).group()))

def analyze(xml):
    dark = any(c in xml for c in DARK_BG)
    tops, bottoms, overflow = [], [], []
    shape_count = len(SP.findall(xml)); body_shapes = 0
    for sp in SP.findall(xml):
        txt = re.sub(r'<[^>]+>', '', "".join(AT.findall(sp))).strip()
        mo, me = OFF.search(sp), EXT.search(sp)
        if mo and me:
            x, y, cx, cy = int(mo.group(1)), int(mo.group(2)), int(me.group(1)), int(me.group(2))
            if y / EMU > 1.45:
                body_shapes += 1
            if txt:
                tops.append(y/EMU); bottoms.append((y+cy)/EMU)
                if x+cx > PAGE_W*EMU+TOL or y+cy > PAGE_H*EMU+TOL or x < -TOL or y < -TOL:
                    overflow.append((round(x/EMU,2), round(y/EMU,2), round((x+cx)/EMU,2), round((y+cy)/EMU,2)))
    body = " ".join(re.sub(r'<[^>]+>', '', t) for t in AT.findall(xml))  # 표 셀 텍스트 포함
    return {"dark": dark, "chars": len(body.strip()), "shapes": shape_count, "bodyShapes": body_shapes,
            "hasImg": ("<a:blip" in xml or "<p:pic>" in xml), "hasTbl": ("<a:tbl>" in xml),
            "minTop": min(tops) if tops else None, "maxBot": max(bottoms) if bottoms else None,
            "overflow": overflow, "body": body}

def main():
    args = sys.argv
    if len(args) < 2:
        print("usage: validate_deck.py deck.pptx [--min-slides 12] [--lenient]"); sys.exit(2)
    path = args[1]
    min_slides = int(args[args.index("--min-slides")+1]) if "--min-slides" in args else 12
    lenient = "--lenient" in args
    z = zipfile.ZipFile(path); sl = slides(z)
    problems, soft, notes, charlist = [], [], [], []

    for idx, n in enumerate(sl):
        a = analyze(z.read(n).decode("utf-8", "ignore")); tag = n.split("/")[-1]; first = (idx == 0); last = (idx == len(sl) - 1)
        charlist.append(a["chars"])
        if a["overflow"]:
            problems.append(f"[오버플로] {tag}: {len(a['overflow'])}개 텍스트 도형 슬라이드 밖 예{a['overflow'][0]}")
        if META.search(a["body"]) or TIMESTAMP.search(a["body"]):
            hit = (META.search(a["body"]) or TIMESTAMP.search(a["body"])).group(0)
            problems.append(f"[메타] {tag}: 본문에 제작/출처 표현 '{hit}' — 주제 자체만 설명")
        if first or last or ("\u201c" in a["body"]):
            continue
        # 4) 간지/저밀도 — 글자도 적고 + 이미지·표·도형도 없는 '빈' 장표만 잡는다(시각적으로 찬 장표는 면제)
        min_chars = 110 if a["dark"] else 160
        visual = a["hasImg"] or a["hasTbl"] or a["bodyShapes"] >= 8
        if a["chars"] < min_chars and not visual:
            (soft if lenient else problems).append(
                f"[저밀도/간지] {tag}: 글자수 {a['chars']}, 도형 {a['shapes']}개, 이미지/표 없음 — 빈 섹션 구분(간지)이거나 내용 부족. 리서치로 채울 것")
        # 5) 세로 빈 공간 — 위만 차고 아래가 비며 시각요소도 없는 경우만
        elif (not a["dark"]) and not (a["hasImg"] or a["hasTbl"]) and a["maxBot"] is not None and a["minTop"] is not None:
            if a["maxBot"] < 5.0 and a["minTop"] < 2.0:
                (soft if lenient else problems).append(
                    f"[세로빈공간] {tag}: 콘텐츠 하단 {a['maxBot']:.1f}\" (<5.0) — 위만 차고 아래 빔, 영역 채울 것")

    if len(sl) < min_slides:
        problems.append(f"[분량] {len(sl)} < 최소 {min_slides} — 간지 없이 실질 내용으로 채울 것")

    body_all = "".join(z.read(n).decode("utf-8", "ignore") for n in sl)
    media = [n for n in z.namelist() if n.startswith("ppt/media/")]
    has_chart = any(re.match(r'ppt/charts/chart\d+\.xml$', n) for n in z.namelist())
    cc = charlist[1:] if len(charlist) > 1 else charlist
    if cc: notes.append(f"본문 글자수/장표: 최소 {min(cc)} ~ 최대 {max(cc)} (균일할수록 좋음)")
    notes.append(f"슬라이드 {len(sl)}장 · 네이티브표 {'✓' if '<a:tbl>' in body_all else '—'} · 차트 {'✓' if has_chart else '—'} · 이미지 {len(media)}개")

    print("=== validate_deck v2:", path, "===")
    for x in notes: print("  ·", x)
    if soft:
        print("\n--- 경고(참고) ---")
        for w in soft: print("  !", w)
    if problems:
        print("\n--- 점검 필요(수정 후 재검증) ---")
        for p in problems: print("  ✗", p)
        print("\nRESULT: FAIL"); sys.exit(1)
    print("\nRESULT: PASS ✓"); sys.exit(0)

if __name__ == "__main__":
    main()
