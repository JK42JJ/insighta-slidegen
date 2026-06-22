/* insighta_deck.js — Insighta 브랜드 슬라이드 컴포넌트 라이브러리 (pptxgenjs)
 * 재사용 단위: createDeck() → 헬퍼들. 모든 컴포넌트는 LAYOUT_WIDE(13.33x7.5") 기준.
 * 디자인 규칙(중요): 제목 밑줄 금지 · 전면 장식 컬러바 금지 · 모든 슬라이드에 시각요소 ·
 *                   카드형 고밀도 모티프 · 레이아웃 다양화 · 본문 좌측정렬.
 */
const pptxgen = require("pptxgenjs");

const BRAND = {
  font:  { display: "Pretendard", body: "Pretendard", mono: "JetBrains Mono" },
  text: "0F172A", muted: "475569", faint: "94A3B8",
  line: "E2E8F0", surface: "FFFFFF", surfaceAlt: "F8FAFC",
  bgDark: "0B1220", bgDarkAlt: "16213E",
  primary: "2563EB", purple: "7C3AED", purpleLite: "A855F7", white: "FFFFFF",
  cats: {
    blue:    { c: "2563EB", t: "EFF4FF", d: "1D4ED8" },
    emerald: { c: "059669", t: "ECFDF5", d: "047857" },
    violet:  { c: "7C3AED", t: "F5F0FF", d: "6D28D9" },
    amber:   { c: "D97706", t: "FFF7ED", d: "B45309" },
    rose:    { c: "E11D48", t: "FFF1F4", d: "BE123C" },
    slate:   { c: "475569", t: "F1F5F9", d: "334155" },
  },
};
const PAGE_W = 13.333, PAGE_H = 7.5, MX = 0.62;
const CW = PAGE_W - 2 * MX;

function createDeck(meta = {}) {
  const pres = new pptxgen();
  pres.defineLayout({ name: "IW", width: PAGE_W, height: PAGE_H });
  pres.layout = "IW";
  pres.author = "Insighta";
  pres.title = meta.title || "Insighta Deck";

  // ---- 공통 헬퍼 ----
  const T = (s, o) => s.length ? s : s;

  function footer(slide, n, total) {
    slide.addText([
      { text: "Insighta", options: { bold: true, color: BRAND.primary } },
      ...(meta.footer ? [{ text: "   " + meta.footer, options: { color: BRAND.faint } }] : []),
    ], { x: MX, y: 7.04, w: 7, h: 0.3, fontFace: BRAND.font.body, fontSize: 9, align: "left", valign: "middle", margin: 0 });
    slide.addText(`${n} / ${total}`, {
      x: PAGE_W - MX - 2, y: 7.04, w: 2, h: 0.3, fontFace: BRAND.font.mono,
      fontSize: 9, color: BRAND.faint, align: "right", valign: "middle", margin: 0,
    });
  }

  // 콘텐츠 슬라이드 헤더 (번호 태그 + 카테고리 키커 + 큰 제목). 밑줄 없음.
  function header(slide, { num, kicker, title, cat = "blue" }) {
    const C = BRAND.cats[cat];
    let tx = MX;
    if (num != null) {
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: MX, y: 0.52, w: 0.62, h: 0.62, rectRadius: 0.1,
        fill: { color: C.c }, line: { type: "none" },
      });
      slide.addText(String(num), {
        x: MX, y: 0.52, w: 0.62, h: 0.62, align: "center", valign: "middle",
        fontFace: BRAND.font.display, fontSize: 24, bold: true, color: BRAND.white, margin: 0,
      });
      tx = MX + 0.84;
    }
    if (kicker) {
      slide.addText(kicker.toUpperCase(), {
        x: tx, y: 0.5, w: CW - (tx - MX), h: 0.26, align: "left", valign: "middle",
        fontFace: BRAND.font.mono, fontSize: 10.5, bold: true, color: C.c, charSpacing: 2, margin: 0,
      });
    }
    slide.addText(title, {
      x: tx, y: kicker ? 0.74 : 0.6, w: CW - (tx - MX), h: 0.5, align: "left", valign: "middle",
      fontFace: BRAND.font.display, fontSize: 28, bold: true, color: BRAND.text, margin: 0,
    });
  }

  // 개념 카드 그리드. items: [{term, desc, ts}]
  function conceptGrid(slide, items, opt = {}) {
    const { x = MX, y = 1.62, w = CW, h = 5.18, cols = 2, cat = "blue",
            colGap = 0.28, rowGap = 0.22 } = opt;
    const C = BRAND.cats[cat];
    const rows = Math.ceil(items.length / cols);
    const cardW = (w - colGap * (cols - 1)) / cols;
    const cardH = (h - rowGap * (rows - 1)) / rows;
    items.forEach((it, i) => {
      const r = Math.floor(i / cols), cidx = i % cols;
      const cx = x + cidx * (cardW + colGap);
      const cy = y + r * (cardH + rowGap);
      // 카드 본체
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: cx, y: cy, w: cardW, h: cardH, rectRadius: 0.06,
        fill: { color: BRAND.surface }, line: { color: BRAND.line, width: 1 },
        shadow: { type: "outer", color: "0F172A", blur: 5, offset: 1.5, angle: 90, opacity: 0.06 },
      });
      // 좌측 카테고리 액센트 바
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: cx, y: cy, w: 0.09, h: cardH, rectRadius: 0.04, fill: { color: C.c }, line: { type: "none" },
      });
      const padL = cx + 0.26, innerW = cardW - 0.42;
      // 용어 + 타임스탬프(모노)
      slide.addText(it.term, {
        x: padL, y: cy + 0.13, w: innerW - 1.05, h: 0.32, align: "left", valign: "middle",
        fontFace: BRAND.font.display, fontSize: 13.5, bold: true, color: BRAND.text, margin: 0,
      });
      if (it.ts) {
        slide.addText(it.ts, {
          x: cx + cardW - 1.18, y: cy + 0.14, w: 0.96, h: 0.28, align: "right", valign: "middle",
          fontFace: BRAND.font.mono, fontSize: 9.5, color: C.d, margin: 0,
        });
      }
      slide.addText(it.desc, {
        x: padL, y: cy + 0.46, w: innerW, h: cardH - 0.56, align: "left", valign: "top",
        fontFace: BRAND.font.body, fontSize: 10.8, color: BRAND.muted, lineSpacingMultiple: 1.04, margin: 0,
      });
    });
  }

  // 카테고리 카드 (개념 지도용). concepts: [짧은 라벨...]
  function categoryCard(slide, { x, y, w, h, name, count, concepts, cat }) {
    const C = BRAND.cats[cat];
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.07, fill: { color: C.t }, line: { color: C.c, width: 1 },
    });
    slide.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.2, w: 0.16, h: 0.16, fill: { color: C.c }, line: { type: "none" } });
    slide.addText(name, {
      x: x + 0.48, y: y + 0.12, w: w - 1.1, h: 0.32, align: "left", valign: "middle",
      fontFace: BRAND.font.display, fontSize: 13, bold: true, color: C.d, margin: 0,
    });
    slide.addText(String(count), {
      x: x + w - 0.7, y: y + 0.12, w: 0.5, h: 0.32, align: "right", valign: "middle",
      fontFace: BRAND.font.mono, fontSize: 12, bold: true, color: C.c, margin: 0,
    });
    slide.addText(concepts.map((t, i) => ({
      text: t, options: { breakLine: true, bullet: { code: "2022", indent: 10 }, color: BRAND.text },
    })), {
      x: x + 0.26, y: y + 0.52, w: w - 0.5, h: h - 0.66, align: "left", valign: "top",
      fontFace: BRAND.font.body, fontSize: 9.6, color: BRAND.text, lineSpacingMultiple: 1.02, margin: 0,
    });
  }

  // 가로 플로우 (라운드 박스 + 화살표). stages:[{title, sub}]
  function flow(slide, stages, opt = {}) {
    const { x = MX, y = 2.2, w = CW, h = 1.5, cat = "violet", onDark = false } = opt;
    const C = BRAND.cats[cat];
    const n = stages.length, gap = 0.5;
    const boxW = (w - gap * (n - 1)) / n;
    stages.forEach((s, i) => {
      const bx = x + i * (boxW + gap);
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: bx, y, w: boxW, h, rectRadius: 0.08,
        fill: { color: onDark ? BRAND.bgDarkAlt : C.t }, line: { color: C.c, width: 1.25 },
      });
      slide.addText(s.title, {
        x: bx + 0.1, y: y + 0.18, w: boxW - 0.2, h: 0.5, align: "center", valign: "middle",
        fontFace: BRAND.font.display, fontSize: 12.5, bold: true, color: onDark ? BRAND.white : C.d, margin: 0,
      });
      if (s.sub) slide.addText(s.sub, {
        x: bx + 0.1, y: y + h - 0.62, w: boxW - 0.2, h: 0.52, align: "center", valign: "middle",
        fontFace: BRAND.font.body, fontSize: 9.5, color: onDark ? BRAND.faint : BRAND.muted, margin: 0,
      });
      if (i < n - 1) slide.addShape(pres.shapes.LINE, {
        x: bx + boxW + 0.06, y: y + h / 2, w: gap - 0.12, h: 0,
        line: { color: C.c, width: 2, endArrowType: "triangle" },
      });
    });
  }

  // 큰 수치 콜아웃. {value, label, cat, onDark}
  function statCallout(slide, { x, y, w, h = 1.7, value, unit, label, cat = "blue", onDark = false }) {
    const C = BRAND.cats[cat];
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.08,
      fill: { color: onDark ? BRAND.bgDarkAlt : C.t }, line: { color: onDark ? C.c : C.c, width: 1 },
    });
    slide.addText([
      { text: value, options: { fontSize: 34, bold: true, color: onDark ? BRAND.white : C.d, fontFace: BRAND.font.display } },
      ...(unit ? [{ text: " " + unit, options: { fontSize: 14, bold: true, color: onDark ? C.c : C.c, fontFace: BRAND.font.mono } }] : []),
    ], { x: x + 0.24, y: y + 0.22, w: w - 0.48, h: 0.7, align: "left", valign: "middle", margin: 0 });
    slide.addText(label, {
      x: x + 0.24, y: y + h - 0.78, w: w - 0.48, h: 0.66, align: "left", valign: "top",
      fontFace: BRAND.font.body, fontSize: 10.5, color: onDark ? BRAND.faint : BRAND.muted, lineSpacingMultiple: 1.02, margin: 0,
    });
  }

  // 모노 칩 행
  function chips(slide, labels, { x = MX, y, w = CW, cat = "amber", title } = {}) {
    const C = BRAND.cats[cat];
    let cx = x;
    if (title) {
      slide.addText(title, { x, y: y - 0.34, w, h: 0.3, fontFace: BRAND.font.body, fontSize: 11, bold: true, color: BRAND.text, margin: 0 });
    }
    labels.forEach((lb) => {
      const cw = 0.28 + lb.length * 0.105;
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y, w: cw, h: 0.4, rectRadius: 0.2, fill: { color: C.t }, line: { color: C.c, width: 1 } });
      slide.addText(lb, { x: cx, y, w: cw, h: 0.4, align: "center", valign: "middle", fontFace: BRAND.font.mono, fontSize: 10.5, bold: true, color: C.d, margin: 0 });
      cx += cw + 0.18;
    });
  }

  // 2x2 혼동행렬 미니 비주얼
  function matrix2x2(slide, { x, y, w, h, cells, cat = "rose" }) {
    const C = BRAND.cats[cat];
    const g = 0.12, cw = (w - g) / 2, ch = (h - g) / 2;
    const pos = [[x, y], [x + cw + g, y], [x, y + ch + g], [x + cw + g, y + ch + g]];
    cells.forEach((cell, i) => {
      const [px, py] = pos[i];
      const good = cell.good;
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: px, y: py, w: cw, h: ch, rectRadius: 0.06,
        fill: { color: good ? C.t : BRAND.surfaceAlt }, line: { color: good ? C.c : BRAND.line, width: 1 },
      });
      slide.addText(cell.k, { x: px + 0.14, y: py + 0.1, w: cw - 0.28, h: 0.3, align: "left", valign: "middle", fontFace: BRAND.font.mono, fontSize: 11, bold: true, color: good ? C.d : BRAND.muted, margin: 0 });
      slide.addText(cell.v, { x: px + 0.14, y: py + ch - 0.44, w: cw - 0.28, h: 0.36, align: "left", valign: "middle", fontFace: BRAND.font.body, fontSize: 9.5, color: BRAND.muted, margin: 0 });
    });
  }

  // 브랜드 표 (네이티브, 편집 가능). headers:[..], rows:[[..]], colW 합 = w
  function table(slide, { x = MX, y, w = CW, headers, rows, cat = "slate", colW, fontSize = 11.5, rowH }) {
    const C = BRAND.cats[cat];
    const head = headers.map((h) => ({ text: h, options: { bold: true, color: "FFFFFF", fill: { color: C.c }, align: "left", valign: "middle", fontFace: BRAND.font.display } }));
    const body = rows.map((r, ri) => r.map((cell, ci) => ({
      text: String(cell),
      options: { color: ci === 0 ? BRAND.text : BRAND.muted, bold: ci === 0,
                 fill: { color: ri % 2 ? C.t : "FFFFFF" }, align: "left", valign: "middle",
                 fontFace: ci === 0 ? BRAND.font.display : BRAND.font.body },
    })));
    const opt = {
      x, y, w, colW, fontFace: BRAND.font.body, fontSize,
      border: { type: "solid", color: BRAND.line, pt: 0.75 },
      align: "left", valign: "middle", margin: [4, 7, 4, 7], autoPage: false,
    };
    if (rowH) opt.rowH = rowH; // 행 높이로 세로 공간 채움
    slide.addTable([head, ...body], opt);
  }

  // 이미지(도형/차트)를 라운드 패널 안에 contain 으로 배치. 다크 위에 흰 패널.
  function imagePanel(slide, { x, y, w, h, img, dark = false, pad = 0.2, border = true, fill = "FFFFFF", caption }) {
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w, h, rectRadius: 0.08, fill: { color: fill },
      line: border ? { color: dark ? "26324F" : BRAND.line, width: 1 } : { type: "none" },
      shadow: dark ? undefined : { type: "outer", color: "0F172A", blur: 6, offset: 1.5, angle: 90, opacity: 0.07 },
    });
    slide.addImage({ path: img, x: x + pad, y: y + pad, w: w - 2 * pad, h: h - 2 * pad - (caption ? 0.3 : 0), sizing: { type: "contain", w: w - 2 * pad, h: h - 2 * pad - (caption ? 0.3 : 0) } });
    if (caption) slide.addText(caption, { x: x + pad, y: y + h - 0.34, w: w - 2 * pad, h: 0.26, align: "center", valign: "middle", fontFace: BRAND.font.body, fontSize: 9.5, color: dark ? BRAND.faint : BRAND.muted, margin: 0 });
  }

  // 도형/차트를 패널 없이 슬라이드에 contain 배치
  function figure(slide, { x, y, w, h, img }) {
    slide.addImage({ path: img, x, y, w, h, sizing: { type: "contain", w, h } });
  }

  // 편집 가능한 수식 행 목록 (유니코드 텍스트 — 복사/편집 가능, 이미지 아님)
  // items: [{name, desc, expr, ts, cat}]
  function equationList(slide, items, opt = {}) {
    const { x = MX, y = 1.66, w = CW, rowH = 1.0, gap = 0.02 } = opt;
    const exprX = x + 5.3, exprW = w - (exprX - x) - 0.25;
    items.forEach((e, i) => {
      const cy = y + i * (rowH + gap);
      const C = BRAND.cats[e.cat || "blue"];
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: cy, w, h: rowH, rectRadius: 0.06,
        fill: { color: i % 2 ? BRAND.surfaceAlt : BRAND.surface }, line: { color: BRAND.line, width: 1 } });
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: cy, w: 0.09, h: rowH, rectRadius: 0.04, fill: { color: C.c }, line: { type: "none" } });
      slide.addText(e.name, { x: x + 0.28, y: cy + 0.13, w: 3.9, h: 0.34, fontFace: BRAND.font.display, fontSize: 13.5, bold: true, color: C.d, margin: 0 });
      if (e.ts) slide.addText(e.ts, { x: x + 3.9, y: cy + 0.14, w: 1.1, h: 0.3, fontFace: BRAND.font.mono, fontSize: 9.5, color: BRAND.faint, align: "right", margin: 0 });
      if (e.desc) slide.addText(e.desc, { x: x + 0.28, y: cy + 0.5, w: 4.7, h: 0.42, fontFace: BRAND.font.body, fontSize: 10.3, color: BRAND.muted, valign: "middle", margin: 0 });
      // 수식 (JetBrains Mono, 실제 텍스트)
      slide.addText(e.expr, { x: exprX, y: cy, w: exprW, h: rowH, fontFace: BRAND.font.mono, fontSize: 17, bold: true, color: BRAND.text, align: "left", valign: "middle", margin: 0 });
    });
  }

  // 네이티브(편집 가능) 막대 차트 — PNG 아님
  function nativeBarChart(slide, { x, y, w, h, labels, values, color = BRAND.primary, title }) {
    if (title) slide.addText(title, { x, y: y - 0.38, w, h: 0.3, fontFace: BRAND.font.display, fontSize: 14, bold: true, color: BRAND.text, margin: 0 });
    slide.addChart(pres.charts.BAR, [{ name: "개념 수", labels, values }], {
      x, y, w, h, barDir: "col", chartColors: [color],
      showValue: true, dataLabelColor: BRAND.text, dataLabelFontFace: BRAND.font.mono, dataLabelFontSize: 12, dataLabelFontBold: true, dataLabelPosition: "outEnd",
      showLegend: false, showTitle: false,
      catAxisLabelColor: BRAND.text, catAxisLabelFontFace: BRAND.font.body, catAxisLabelFontSize: 10, catAxisLineShow: false, catAxisMajorTickMark: "none",
      valAxisHidden: true, valGridLine: { style: "none" }, valAxisLineShow: false, valAxisMajorTickMark: "none",
      barGapWidthPct: 45,
    });
  }

  // 직선 커넥터 (네이티브 LINE, 방향 자동)
  function connect(slide, x1, y1, x2, y2, color = BRAND.faint, width = 1.5, arrow = false) {
    const o = { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
      line: { color, width, endArrowType: arrow ? "triangle" : "none" }, flipH: x2 < x1, flipV: y2 < y1 };
    slide.addShape(pres.shapes.LINE, o);
  }

  function newSlide(dark = false) {
    const s = pres.addSlide();
    s.background = { color: dark ? BRAND.bgDark : BRAND.surface };
    return s;
  }

  return { pres, BRAND, shapes: pres.shapes, newSlide, footer, header,
           conceptGrid, categoryCard, flow, statCallout, chips, matrix2x2,
           table, imagePanel, figure, equationList, nativeBarChart, connect,
           PAGE_W, PAGE_H, MX, CW };
}

module.exports = { createDeck, BRAND };
