/* deck_templates.js — 검증된 슬라이드 레이아웃을 '내용만 받는' 템플릿으로 캡슐화.
 * 목적: 약한 모델도 좌표/비율/화살표를 계산하지 않고 콘텐츠만 채우면 동일 품질이 나오도록.
 *
 *   const { createDeck } = require("./insighta_deck.js");
 *   const { makeTemplates } = require("./deck_templates.js");
 *   const D = createDeck({ title: "..." });
 *   const T = makeTemplates(D, { total: 15, figDir: "/path/figs" });
 *   T.title({...}); T.roadmapLoop({...}); ... ; T.save("out.pptx");
 *
 * 모든 메서드는 슬라이드 생성·푸터·페이지 번호를 자동 처리한다. 좌표를 직접 쓰지 말 것.
 */
const fs = require("fs");
function pngSize(p) { const b = fs.readFileSync(p); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function fitBox(img, maxW, maxH, pad) { const { w: iw, h: ih } = pngSize(img), ar = iw / ih; let aw = maxW - 2 * pad, ah = maxH - 2 * pad, w = aw, h = w / ar; if (h > ah) { h = ah; w = h * ar; } return { w: w + 2 * pad, h: h + 2 * pad }; }

function makeTemplates(D, opts = {}) {
  const { pres, BRAND, shapes, newSlide, footer, header, conceptGrid, categoryCard,
          flow, chips, matrix2x2, table, equationList, imagePanel, connect, MX, CW } = D;
  const total = opts.total || 0;
  const figDir = opts.figDir || ".";
  const LINK = opts.link || "https://insighta.one";
  const F = (n) => require("path").join(figDir, n);
  let page = 0; // 자동 증가

  function card(s, x, y, w, h, cat) { const C = BRAND.cats[cat];
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.07, fill: { color: BRAND.surface }, line: { color: BRAND.line, width: 1 } });
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w: 0.09, h, rectRadius: 0.04, fill: { color: C.c }, line: { type: "none" } }); }
  function pill(s, x, y, label, value) { const w = 0.5 + (label.length + value.length) * 0.11;
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.46, rectRadius: 0.23, fill: { type: "none" }, line: { color: "3B4A6B", width: 1.25 } });
    s.addText([{ text: label + "  ", options: { color: BRAND.faint, fontFace: BRAND.font.mono, fontSize: 9.5 } }, { text: value, options: { color: BRAND.white, bold: true, fontFace: BRAND.font.display, fontSize: 11 } }], { x: x + 0.2, y, w: w - 0.3, h: 0.46, align: "left", valign: "middle", margin: 0 }); return w; }
  // 직각 루프백 화살표 (왜곡 없는 검증된 패턴). flowBottomY=플로우 박스 하단 y.
  function loopArrow(s, flowBottomY, color) {
    const lineY = flowBottomY + 0.35, lx = MX + 0.95, rx = MX + CW - 0.95;
    connect(s, lx, lineY, rx, lineY, color, 2, false);
    connect(s, rx, flowBottomY, rx, lineY, color, 2, false);
    s.addShape(shapes.LINE, { x: lx, y: flowBottomY, w: 0, h: lineY - flowBottomY, line: { color, width: 2, endArrowType: "triangle" }, flipV: true });
    return lineY;
  }

  const T = {
    F, // 피규어 경로 헬퍼 노출
    /* 표지(다크) */
    title({ kicker, title, subtitle, pills = [], brandLine = "" }) {
      const s = newSlide(true);
      s.addShape(shapes.OVAL, { x: 9.0, y: -2.0, w: 6.6, h: 6.6, fill: { color: BRAND.purple, transparency: 82 }, line: { type: "none" } });
      s.addShape(shapes.OVAL, { x: 11.0, y: 2.6, w: 4.4, h: 4.4, fill: { color: BRAND.primary, transparency: 86 }, line: { type: "none" } });
      if (kicker) s.addText(kicker, { x: 0.7, y: 1.5, w: 11, h: 0.3, fontFace: BRAND.font.mono, fontSize: 12, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
      s.addText(title, { x: 0.7, y: 1.95, w: 11.4, h: 1.4, fontFace: BRAND.font.display, fontSize: 46, bold: true, color: BRAND.white, margin: 0 });
      if (subtitle) s.addText(subtitle, { x: 0.72, y: 3.45, w: 11.6, h: 0.6, fontFace: BRAND.font.body, fontSize: 15, color: "AEB8CC", margin: 0 });
      let x = 0.72; pills.forEach((p, i) => { x += pill(s, x, 4.55, p[0], p[1]) + 0.2; });
      s.addText([{ text: "Insighta", options: { bold: true, color: BRAND.white, fontFace: BRAND.font.display, fontSize: 15 } },
                 { text: brandLine ? ("   " + brandLine + " · ") : "   ", options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 11 } },
                 { text: "insighta.one", options: { color: BRAND.purpleLite, fontFace: BRAND.font.mono, fontSize: 11, bold: true, hyperlink: { url: LINK } } }],
                { x: 0.7, y: 6.7, w: 11.6, h: 0.4, align: "left", valign: "middle", margin: 0 });
      page = 1; return s;
    },
    /* 큰 그림: 워크플로우 루프 + 호기심 훅 카드 3개 */
    roadmapLoop({ kicker = "Big Picture", title, intro, stages, hooks = [], cat = "blue" }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      if (intro) s.addText(intro, { x: MX, y: 1.62, w: CW, h: 0.5, fontFace: BRAND.font.body, fontSize: 13.5, color: BRAND.text, margin: 0 });
      flow(s, stages, { y: 2.5, h: 1.5, cat });
      const ly = loopArrow(s, 4.0, BRAND.cats[cat].c);
      s.addText("반복(epoch)마다 손실이 줄도록 모델을 조금씩 고친다", { x: MX, y: ly + 0.1, w: CW, h: 0.3, fontFace: BRAND.font.mono, fontSize: 10, color: BRAND.cats[cat].d, align: "center", margin: 0 });
      const n = Math.min(hooks.length, 3), cw = (CW - 0.6) / 3;
      hooks.slice(0, 3).forEach((q, i) => { const cx = MX + i * (cw + 0.3), cy = 5.2; card(s, cx, cy, cw, 1.4, cat);
        s.addText(q.q, { x: cx + 0.24, y: cy + 0.16, w: cw - 0.44, h: 0.6, fontFace: BRAND.font.display, fontSize: 12, bold: true, color: BRAND.cats[cat].d, valign: "top", margin: 0 });
        s.addText(q.a, { x: cx + 0.24, y: cy + 0.72, w: cw - 0.44, h: 0.6, fontFace: BRAND.font.body, fontSize: 10.5, color: BRAND.muted, valign: "top", margin: 0 }); });
      footer(s, page, total); return s;
    },
    /* 개념 지도: 6개 카테고리 카드 */
    conceptMap({ kicker = "Concept Map", title, categories, cat = "violet" }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const cols = 3, gx = 0.3, gy = 0.3, cw = (CW - gx * 2) / 3, ch = (5.18 - gy) / 2;
      categories.slice(0, 6).forEach((m, i) => { const r = Math.floor(i / cols), c = i % cols;
        categoryCard(s, { x: MX + c * (cw + gx), y: 1.62 + r * (ch + gy), w: cw, h: ch, name: m.name, count: m.count, concepts: m.concepts, cat: m.cat }); });
      footer(s, page, total); return s;
    },
    /* 분류 트리: 네이티브 박스+커넥터 (편집 가능) */
    taxonomy({ kicker = "Taxonomy", title, branches, cat = "blue", note }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const gx = 0.3, w = (CW - gx * 2) / 3, y0 = 1.72, H = note ? 4.55 : 4.8;
      branches.slice(0, 3).forEach((b, bi) => { const x = MX + bi * (w + gx); const C = BRAND.cats[b.cat]; card(s, x, y0, w, H, b.cat);
        s.addText(b.name, { x: x + 0.26, y: y0 + 0.16, w: w - 0.5, h: 0.36, fontFace: BRAND.font.display, fontSize: 15, bold: true, color: C.d, margin: 0 });
        if (b.tag) s.addText(b.tag, { x: x + 0.26, y: y0 + 0.52, w: w - 0.5, h: 0.4, fontFace: BRAND.font.body, fontSize: 10, italic: true, color: BRAND.muted, margin: 0 });
        let cy = y0 + (b.tag ? 1.0 : 0.64);
        b.groups.forEach((g) => { s.addShape(shapes.ROUNDED_RECTANGLE, { x: x + 0.26, y: cy, w: w - 0.52, h: 0.38, rectRadius: 0.06, fill: { color: C.t }, line: { color: C.c, width: 1 } });
          s.addText(g.sub, { x: x + 0.42, y: cy, w: w - 0.8, h: 0.38, fontFace: BRAND.font.display, fontSize: 11.5, bold: true, color: C.d, valign: "middle", margin: 0 }); cy += 0.5;
          g.items.forEach((it) => { connect(s, x + 0.5, cy + 0.18, x + 0.64, cy + 0.18, C.c, 1.25); s.addText(it, { x: x + 0.72, y: cy, w: w - 1.0, h: 0.32, fontFace: BRAND.font.body, fontSize: 10.5, color: BRAND.text, valign: "middle", margin: 0 }); cy += 0.36; }); cy += 0.1; }); });
      if (note) s.addText(note, { x: MX, y: 6.5, w: CW, h: 0.3, fontFace: BRAND.font.body, fontSize: 10, italic: true, color: BRAND.muted, align: "center", margin: 0 });
      footer(s, page, total); return s;
    },
    /* 교육 슬라이드: 좌 고해상 그래프 + 우 직관/왜 + '직관' 콜아웃 */
    teach({ kicker, title, cat, figure, lead, points = [], aha }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const C = BRAND.cats[cat];
      const img = F(figure), pb = fitBox(img, 6.5, 4.7, 0.2);
      imagePanel(s, { x: MX, y: 1.7 + (4.7 - pb.h) / 2, w: pb.w, h: pb.h, img, pad: 0.2 });
      const rx = 7.45, rw = CW - (rx - MX);
      s.addText(lead, { x: rx, y: 1.74, w: rw, h: 0.85, fontFace: BRAND.font.body, fontSize: 13, color: BRAND.text, valign: "top", lineSpacingMultiple: 1.12, margin: 0 });
      let y = 2.7; points.slice(0, 3).forEach((p) => { s.addShape(shapes.OVAL, { x: rx, y: y + 0.06, w: 0.13, h: 0.13, fill: { color: C.c }, line: { type: "none" } });
        s.addText(p, { x: rx + 0.28, y: y - 0.02, w: rw - 0.28, h: 0.6, fontFace: BRAND.font.body, fontSize: 11.5, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.06, margin: 0 }); y += 0.74; });
      if (aha) { card(s, rx, 5.55, rw, 0.95, cat);
        s.addText([{ text: "직관  ", options: { bold: true, color: C.d, fontFace: BRAND.font.display, fontSize: 11 } }, { text: aha, options: { color: BRAND.text, fontFace: BRAND.font.body, fontSize: 11.5 } }], { x: rx + 0.26, y: 5.62, w: rw - 0.5, h: 0.8, valign: "middle", lineSpacingMultiple: 1.08, margin: 0 }); }
      footer(s, page, total); return s;
    },
    /* 두 그래프 + 설명 카드 2개 */
    dualTeach({ kicker, title, cat, figures, notes }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      [0, 1].forEach((i) => { const img = F(figures[i]); const pb = fitBox(img, 6.0, 3.2, 0.18); imagePanel(s, { x: MX + i * 6.2, y: 1.7, w: pb.w, h: pb.h, img, pad: 0.18 }); });
      notes.slice(0, 2).forEach((c, i) => { const cw = (CW - 0.4) / 2, cx = MX + i * (cw + 0.4), cy = 5.0; card(s, cx, cy, cw, 1.55, cat);
        s.addText(c.h, { x: cx + 0.24, y: cy + 0.16, w: cw - 0.44, h: 0.34, fontFace: BRAND.font.display, fontSize: 13, bold: true, color: BRAND.cats[cat].d, margin: 0 });
        s.addText(c.t, { x: cx + 0.24, y: cy + 0.54, w: cw - 0.44, h: 0.95, fontFace: BRAND.font.body, fontSize: 11, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.06, margin: 0 }); });
      footer(s, page, total); return s;
    },
    /* 진화 플로우 + 연표 + 보강 카드 3 */
    evolution({ kicker, title, cat = "violet", stages, timeline, cards }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      flow(s, stages, { y: 1.82, h: 1.3, cat });
      if (timeline) s.addText(timeline, { x: MX, y: 3.3, w: CW, h: 0.3, fontFace: BRAND.font.mono, fontSize: 10.5, color: BRAND.cats[cat].d, align: "center", margin: 0 });
      const gx = 0.3, cw = (CW - gx * 2) / 3, cy = 3.75, ch = 2.6;
      cards.slice(0, 3).forEach((m, i) => { const cx = MX + i * (cw + gx); card(s, cx, cy, cw, ch, m.cat || cat);
        s.addText(m.h, { x: cx + 0.26, y: cy + 0.18, w: cw - 0.5, h: 0.4, fontFace: BRAND.font.display, fontSize: 15, bold: true, color: BRAND.cats[m.cat || cat].d, margin: 0 });
        s.addText(m.t, { x: cx + 0.26, y: cy + 0.68, w: cw - 0.5, h: ch - 0.85, fontFace: BRAND.font.body, fontSize: 11.5, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.06, margin: 0 }); });
      footer(s, page, total); return s;
    },
    /* 핵심 수식 (편집 가능 텍스트) */
    equations({ kicker = "Key Equations", title = "핵심 수식 · 복사 가능한 텍스트", cat = "amber", items }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      equationList(s, items, { y: 1.66, rowH: 1.0 }); footer(s, page, total); return s;
    },
    /* 평가: 좌 ROC 그래프 + 우 직관 + 혼동행렬 + 지표식 */
    evaluation({ kicker = "평가 · 검증", title, cat = "rose", figure, intro, metricsText, note }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const img = F(figure), pb = fitBox(img, 5.7, 4.6, 0.18); imagePanel(s, { x: MX, y: 1.7 + (4.6 - pb.h) / 2, w: pb.w, h: pb.h, img, pad: 0.18 });
      const rx = 6.55, rw = CW - (rx - MX);
      s.addText(intro, { x: rx, y: 1.72, w: rw, h: 0.95, fontFace: BRAND.font.body, fontSize: 12.5, color: BRAND.text, valign: "top", lineSpacingMultiple: 1.12, margin: 0 });
      matrix2x2(s, { x: rx, y: 2.75, w: rw * 0.62, h: 2.2, cat, cells: [{ k: "TP", v: "적중", good: true }, { k: "FP", v: "오탐", good: false }, { k: "FN", v: "누락", good: false }, { k: "TN", v: "정답", good: true }] });
      if (metricsText) s.addText(metricsText, { x: rx + rw * 0.66, y: 2.8, w: rw * 0.34, h: 2.1, fontFace: BRAND.font.mono, fontSize: 10.5, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.3, margin: 0 });
      if (note) s.addText(note, { x: MX, y: 6.15, w: CW, h: 0.3, fontFace: BRAND.font.body, fontSize: 10.5, italic: true, color: BRAND.muted, margin: 0 });
      footer(s, page, total); return s;
    },
    /* 넓게 훑기: 개념 카드 그리드 (2 또는 3열) */
    breadthGrid({ kicker, title, cat = "slate", items, cols = 3 }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      conceptGrid(s, items, { cat, cols, y: 1.7, h: 4.7 }); footer(s, page, total); return s;
    },
    /* 본질: 학습 루프 재방문 (다크) + 합성 문장 */
    essenceLoop({ kicker = "ESSENCE", title, stages, synthesisRuns, cat = "violet" }) {
      page++; const s = newSlide(true);
      s.addShape(shapes.OVAL, { x: 10.2, y: -1.8, w: 5.4, h: 5.4, fill: { color: BRAND.primary, transparency: 86 }, line: { type: "none" } });
      s.addText(kicker, { x: 0.7, y: 0.58, w: 9, h: 0.3, fontFace: BRAND.font.mono, fontSize: 11, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
      s.addText(title, { x: 0.7, y: 0.9, w: 12, h: 0.6, fontFace: BRAND.font.display, fontSize: 26, bold: true, color: BRAND.white, margin: 0 });
      flow(s, stages, { y: 2.35, h: 1.4, cat, onDark: true });
      const ly = loopArrow(s, 3.75, BRAND.purpleLite);
      s.addText("반복 학습 (epoch)", { x: MX, y: ly + 0.05, w: CW, h: 0.3, fontFace: BRAND.font.mono, fontSize: 10, color: BRAND.purpleLite, align: "center", margin: 0 });
      s.addText(synthesisRuns, { x: 0.7, y: 4.95, w: 12, h: 1.0, fontFace: BRAND.font.body, fontSize: 13.5, lineSpacingMultiple: 1.18, valign: "top", margin: 0 });
      footer(s, page, total); return s;
    },
    /* 호기심: Q&A 카드 4 + 링크 (다크) */
    curiosity({ kicker = "CURIOSITY", title, qa, footerText = "" }) {
      page++; const s = newSlide(true);
      s.addShape(shapes.OVAL, { x: -1.5, y: 3.2, w: 5.2, h: 5.2, fill: { color: BRAND.purple, transparency: 84 }, line: { type: "none" } });
      s.addText(kicker, { x: 0.7, y: 0.7, w: 9, h: 0.3, fontFace: BRAND.font.mono, fontSize: 11, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
      s.addText(title, { x: 0.7, y: 1.05, w: 12, h: 0.6, fontFace: BRAND.font.display, fontSize: 28, bold: true, color: BRAND.white, margin: 0 });
      const gx = 0.4, cw = (11.9 - gx) / 2;
      qa.slice(0, 4).forEach((q, i) => { const r = Math.floor(i / 2), c = i % 2, cx = 0.7 + c * (cw + gx), cy = 2.0 + r * 1.55;
        s.addShape(shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w: cw, h: 1.35, rectRadius: 0.08, fill: { color: BRAND.bgDarkAlt }, line: { color: "26324F", width: 1 } });
        s.addText("Q", { x: cx + 0.22, y: cy + 0.16, w: 0.5, h: 0.4, fontFace: BRAND.font.mono, fontSize: 15, bold: true, color: BRAND.purpleLite, margin: 0 });
        s.addText(q.q, { x: cx + 0.7, y: cy + 0.16, w: cw - 0.95, h: 0.4, fontFace: BRAND.font.display, fontSize: 12.5, bold: true, color: BRAND.white, valign: "middle", margin: 0 });
        s.addText(q.a, { x: cx + 0.7, y: cy + 0.6, w: cw - 0.95, h: 0.66, fontFace: BRAND.font.body, fontSize: 10.8, color: "AEB8CC", valign: "top", lineSpacingMultiple: 1.05, margin: 0 }); });
      s.addText([{ text: (footerText || ""), options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 12 } }, { text: "더 많은 학습 도구 → insighta.one", options: { color: BRAND.purpleLite, bold: true, fontFace: BRAND.font.mono, fontSize: 12.5, hyperlink: { url: LINK } } }], { x: 0.7, y: 6.65, w: 12, h: 0.4, valign: "middle", margin: 0 });
      footer(s, page, total); return s;
    },
    save(fileName) { return pres.writeFile({ fileName }); },
    get page() { return page; },
  };
  return T;
}
module.exports = { makeTemplates, pngSize, fitBox };
