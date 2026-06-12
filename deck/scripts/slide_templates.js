/* slide_templates.js — Layer 1: 도메인 무관 '낱장 장표' 원자 12종.
 * 어떤 영상 유형의 덱이든 이 원자들을 조합(Layer 2 레시피)해 만든다. 좌표는 여기서만 다룬다.
 *
 *   const { createDeck } = require("./insighta_deck.js");
 *   const { makeSlides } = require("./slide_templates.js");
 *   const D = createDeck({ title: "..." });
 *   const S = makeSlides(D, { total: 10, link: "https://insighta.one" });
 *   S.sectionDivider({...}); S.keyPoints({...}); ... ; S.save("out.pptx");
 *
 * 모든 메서드: 슬라이드 생성·푸터·페이지번호 자동. 다크 원자는 흰색 제목을 직접 렌더(header 미사용).
 */
function makeSlides(D, opts = {}) {
  const { pres, BRAND, shapes, newSlide, footer, header, flow, statCallout, chips, table, matrix2x2, connect, MX, CW } = D;
  const total = opts.total || 0;
  const LINK = opts.link || "https://insighta.one";
  const PAGE_W = 13.333;
  let page = 0;
  const C = (c) => BRAND.cats[c] || BRAND.cats.blue;

  function card(s, x, y, w, h, cat, alt) {
    const cc = C(cat);
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.07, fill: { color: alt ? BRAND.surfaceAlt : BRAND.surface }, line: { color: BRAND.line, width: 1 } });
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w: 0.09, h, rectRadius: 0.04, fill: { color: cc.c }, line: { type: "none" } });
  }
  function bullets(s, x, y, w, items, cat, fs = 11.5, rh = 0.5) {
    const cc = C(cat); let yy = y;
    items.forEach((it) => {
      s.addShape(shapes.OVAL, { x, y: yy + 0.07, w: 0.12, h: 0.12, fill: { color: cc.c }, line: { type: "none" } });
      s.addText(it, { x: x + 0.26, y: yy - 0.02, w: w - 0.26, h: rh, fontFace: BRAND.font.body, fontSize: fs, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
      yy += rh;
    });
    return yy;
  }
  function pill(s, x, y, label, value) {
    const w = 0.5 + (String(label).length + String(value).length) * 0.11;
    s.addShape(shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.46, rectRadius: 0.23, fill: { type: "none" }, line: { color: "3B4A6B", width: 1.25 } });
    s.addText([{ text: label + "  ", options: { color: BRAND.faint, fontFace: BRAND.font.mono, fontSize: 9.5 } }, { text: String(value), options: { color: BRAND.white, bold: true, fontFace: BRAND.font.display, fontSize: 11 } }], { x: x + 0.2, y, w: w - 0.3, h: 0.46, align: "left", valign: "middle", margin: 0 });
    return w;
  }
  function darkBase(kicker, title, subtitle, ovalLeft) {
    const s = newSlide(true);
    if (ovalLeft) s.addShape(shapes.OVAL, { x: -1.5, y: 3.2, w: 5.2, h: 5.2, fill: { color: BRAND.purple, transparency: 84 }, line: { type: "none" } });
    else s.addShape(shapes.OVAL, { x: 10.2, y: -1.8, w: 5.4, h: 5.4, fill: { color: BRAND.primary, transparency: 86 }, line: { type: "none" } });
    if (kicker) s.addText(kicker.toUpperCase(), { x: 0.7, y: 0.62, w: 11, h: 0.3, fontFace: BRAND.font.mono, fontSize: 11, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
    if (title) s.addText(title, { x: 0.7, y: 0.98, w: 12, h: 0.7, fontFace: BRAND.font.display, fontSize: 30, bold: true, color: BRAND.white, margin: 0 });
    if (subtitle) s.addText(subtitle, { x: 0.72, y: 1.74, w: 11.6, h: 0.5, fontFace: BRAND.font.body, fontSize: 14, color: "AEB8CC", margin: 0 });
    return s;
  }

  const S = {
    /* 0. 표지 (다크) */
    title({ kicker, title, subtitle, pills = [], brandLine = "" }) {
      page++; const s = newSlide(true);
      s.addShape(shapes.OVAL, { x: 9.0, y: -2.0, w: 6.6, h: 6.6, fill: { color: BRAND.purple, transparency: 82 }, line: { type: "none" } });
      s.addShape(shapes.OVAL, { x: 11.0, y: 2.6, w: 4.4, h: 4.4, fill: { color: BRAND.primary, transparency: 86 }, line: { type: "none" } });
      if (kicker) s.addText(kicker.toUpperCase(), { x: 0.7, y: 1.5, w: 11, h: 0.3, fontFace: BRAND.font.mono, fontSize: 12, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
      s.addText(title, { x: 0.7, y: 1.95, w: 11.4, h: 1.4, fontFace: BRAND.font.display, fontSize: 46, bold: true, color: BRAND.white, margin: 0 });
      if (subtitle) s.addText(subtitle, { x: 0.72, y: 3.45, w: 11.6, h: 0.6, fontFace: BRAND.font.body, fontSize: 15, color: "AEB8CC", margin: 0 });
      let x = 0.72; pills.forEach((p) => { x += pill(s, x, 4.55, p[0], p[1]) + 0.2; });
      s.addText([{ text: "Insighta", options: { bold: true, color: BRAND.white, fontFace: BRAND.font.display, fontSize: 15 } }, { text: brandLine ? "   " + brandLine + " · " : "   ", options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 11 } }, { text: "insighta.one", options: { color: BRAND.purpleLite, fontFace: BRAND.font.mono, fontSize: 11, bold: true, hyperlink: { url: LINK } } }], { x: 0.7, y: 6.7, w: 11.6, h: 0.4, align: "left", valign: "middle", margin: 0 });
      footer(s, page, total); return s;
    },

    /* 1. 섹션 구분 (다크) */
    sectionDivider({ no, kicker = "SECTION", title, subtitle, cat = "violet" }) {
      page++; const s = newSlide(true); const cc = C(cat);
      s.addShape(shapes.OVAL, { x: 9.4, y: -1.8, w: 6.0, h: 6.0, fill: { color: BRAND.purple, transparency: 84 }, line: { type: "none" } });
      s.addShape(shapes.ROUNDED_RECTANGLE, { x: 0.7, y: 2.55, w: 0.16, h: 2.2, rectRadius: 0.06, fill: { color: cc.c }, line: { type: "none" } });
      s.addText((no != null ? kicker + " " + no : kicker).toUpperCase(), { x: 1.02, y: 2.62, w: 11, h: 0.34, fontFace: BRAND.font.mono, fontSize: 13, bold: true, color: BRAND.purpleLite, charSpacing: 3, margin: 0 });
      s.addText(title, { x: 1.0, y: 3.05, w: 11.4, h: 1.2, fontFace: BRAND.font.display, fontSize: 40, bold: true, color: BRAND.white, margin: 0 });
      if (subtitle) s.addText(subtitle, { x: 1.02, y: 4.35, w: 11, h: 0.6, fontFace: BRAND.font.body, fontSize: 14, color: "AEB8CC", margin: 0 });
      footer(s, page, total); return s;
    },

    /* 2. 목차 (라이트) */
    agenda({ kicker = "Agenda", title = "목차", items, cat = "blue" }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      const n = Math.min(items.length, 6), rh = Math.min(0.84, (5.0) / n);
      const y0 = 1.78 + Math.max(0, (5.0 - rh * n) / 2);
      items.slice(0, 8).forEach((it, i) => {
        const cy = y0 + i * rh;
        s.addShape(shapes.OVAL, { x: MX, y: cy, w: 0.5, h: 0.5, fill: { color: cc.t }, line: { color: cc.c, width: 1.5 } });
        s.addText(String(i + 1), { x: MX, y: cy, w: 0.5, h: 0.5, align: "center", valign: "middle", fontFace: BRAND.font.display, fontSize: 16, bold: true, color: cc.d, margin: 0 });
        s.addText(it.label, { x: MX + 0.72, y: cy + (it.desc ? 0 : 0.08), w: CW - 0.72, h: 0.32, fontFace: BRAND.font.display, fontSize: 15, bold: true, color: BRAND.text, valign: "middle", margin: 0 });
        if (it.desc) s.addText(it.desc, { x: MX + 0.72, y: cy + 0.3, w: CW - 0.72, h: 0.24, fontFace: BRAND.font.body, fontSize: 11, color: BRAND.muted, valign: "top", margin: 0 });
        if (i < n - 1) connect(s, MX + 0.72, cy + rh - 0.06, MX + CW, cy + rh - 0.06, BRAND.line, 0.75);
      });
      footer(s, page, total); return s;
    },

    /* 3. 핵심 메시지 (라이트) — 3~5 포인트 */
    keyPoints({ kicker = "Key Points", title, cat = "blue", lead, points }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      if (lead) s.addText(lead, { x: MX, y: 1.6, w: CW, h: 0.5, fontFace: BRAND.font.body, fontSize: 13.5, color: BRAND.text, valign: "top", margin: 0 });
      const y0 = lead ? 2.25 : 1.7, end = 6.55, n = Math.min(points.length, 5), gap = 0.18;
      const MAXRH = 1.2; // 카드 높이 상한 — 항목이 적어도 풍선처럼 늘어나지 않게
      const rh = Math.min(MAXRH, (end - y0 - gap * (n - 1)) / n);
      const blockH = rh * n + gap * (n - 1), yTop = y0 + Math.max(0, (end - y0 - blockH) / 2); // 중앙 정렬
      points.slice(0, 5).forEach((p, i) => {
        const cy = yTop + i * (rh + gap); card(s, MX, cy, CW, rh, cat);
        s.addText(p.h, { x: MX + 0.3, y: cy + 0.14, w: CW - 0.6, h: 0.36, fontFace: BRAND.font.display, fontSize: 14.5, bold: true, color: C(cat).d, margin: 0 });
        if (p.t) s.addText(p.t, { x: MX + 0.3, y: cy + 0.52, w: CW - 0.6, h: rh - 0.6, fontFace: BRAND.font.body, fontSize: 11.5, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
      });
      footer(s, page, total); return s;
    },

    /* 4. 2단 비교 (라이트) */
    twoColumn({ kicker = "Compare", title, cat = "blue", left, right }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const y0 = 1.72, h = 4.8, gap = 0.4, cw = (CW - gap) / 2;
      [[MX, left], [MX + cw + gap, right]].forEach(([x, col]) => {
        const c = col.cat || cat; card(s, x, y0, cw, h, c);
        s.addText(col.h, { x: x + 0.28, y: y0 + 0.2, w: cw - 0.5, h: 0.44, fontFace: BRAND.font.display, fontSize: 17, bold: true, color: C(c).d, margin: 0 });
        bullets(s, x + 0.3, y0 + 0.95, cw - 0.6, col.items.slice(0, 6), c, 12, 0.62);
      });
      footer(s, page, total); return s;
    },

    /* 5. 비교 표 (라이트, 네이티브 표) */
    comparisonTable({ kicker = "Comparison", title, cat = "slate", intro, headers, rows, colW }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      if (intro) s.addText(intro, { x: MX, y: 1.6, w: CW, h: 0.4, fontFace: BRAND.font.body, fontSize: 12.5, color: BRAND.muted, margin: 0 });
      const w = CW, cw = colW || headers.map((_, i) => (i === 0 ? w * 0.26 : (w * 0.74) / (headers.length - 1)));
      const top = intro ? 2.1 : 1.74, end = 6.6, nRows = rows.length + 1;
      const rowH = Math.min(1.05, (end - top) / nRows);                // 행 높이로 세로 채움(상한)
      const y = top + Math.max(0, (end - top - rowH * nRows) / 2);     // 블록 중앙 정렬
      table(s, { x: MX, y, w, headers, rows, cat, colW: cw, fontSize: 11.5, rowH });
      footer(s, page, total); return s;
    },

    /* 6. 프로세스·단계 (라이트, 번호 + 화살표) */
    processSteps({ kicker = "Process", title, cat = "blue", steps, note }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      const n = Math.min(steps.length, 5), gap = 0.34, bw = (CW - gap * (n - 1)) / n, by = 2.45, bh = 3.0;
      steps.slice(0, 5).forEach((st, i) => {
        const bx = MX + i * (bw + gap);
        s.addShape(shapes.ROUNDED_RECTANGLE, { x: bx, y: by, w: bw, h: bh, rectRadius: 0.08, fill: { color: cc.t }, line: { color: cc.c, width: 1.25 } });
        s.addShape(shapes.OVAL, { x: bx + 0.2, y: by - 0.28, w: 0.56, h: 0.56, fill: { color: cc.c }, line: { color: BRAND.surface, width: 2 } });
        s.addText(String(i + 1), { x: bx + 0.2, y: by - 0.28, w: 0.56, h: 0.56, align: "center", valign: "middle", fontFace: BRAND.font.display, fontSize: 18, bold: true, color: BRAND.white, margin: 0 });
        s.addText(st.title, { x: bx + 0.24, y: by + 0.46, w: bw - 0.48, h: 0.5, fontFace: BRAND.font.display, fontSize: 13.5, bold: true, color: cc.d, valign: "top", lineSpacingMultiple: 1.0, margin: 0 });
        if (st.sub) s.addText(st.sub, { x: bx + 0.24, y: by + 1.02, w: bw - 0.48, h: bh - 1.1, fontFace: BRAND.font.body, fontSize: 11, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
        if (i < n - 1) connect(s, bx + bw + 0.03, by + bh / 2, bx + bw + gap - 0.03, by + bh / 2, cc.c, 2, true);
      });
      if (note) s.addText(note, { x: MX, y: by + bh + 0.4, w: CW, h: 0.4, fontFace: BRAND.font.body, fontSize: 11, italic: true, color: BRAND.muted, margin: 0 });
      footer(s, page, total); return s;
    },

    /* 7. 순위 리스트 (라이트, Top-N) */
    listRanked({ kicker = "Ranking", title, cat = "amber", items }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      const n = Math.min(items.length, 8), y0 = 1.7, end = 6.62, MAXRH = 0.92;
      const rh = Math.min(MAXRH, (end - y0) / n), yTop = y0 + Math.max(0, (end - y0 - rh * n) / 2);
      items.slice(0, 8).forEach((it, i) => {
        const cy = yTop + i * rh; card(s, MX, cy, CW, rh - 0.14, cat, i % 2 === 1);
        s.addText(String(it.rank || i + 1), { x: MX + 0.18, y: cy, w: 0.9, h: rh - 0.14, align: "center", valign: "middle", fontFace: BRAND.font.display, fontSize: 24, bold: true, color: cc.c, margin: 0 });
        const tight = rh < 0.86 || !it.desc;
        if (tight) {
          s.addText(it.title, { x: MX + 1.2, y: cy, w: CW - 1.4, h: rh - 0.14, fontFace: BRAND.font.display, fontSize: 14, bold: true, color: BRAND.text, valign: "middle", margin: 0 });
        } else {
          s.addText(it.title, { x: MX + 1.2, y: cy + 0.12, w: CW - 1.4, h: 0.36, fontFace: BRAND.font.display, fontSize: 14, bold: true, color: BRAND.text, valign: "middle", margin: 0 });
          s.addText(it.desc, { x: MX + 1.2, y: cy + (rh - 0.14) / 2, w: CW - 1.4, h: rh / 2 - 0.1, fontFace: BRAND.font.body, fontSize: 11, color: BRAND.muted, valign: "top", margin: 0 });
        }
      });
      footer(s, page, total); return s;
    },

    /* 8. 타임라인 (라이트, 가로 마일스톤) */
    timeline({ kicker = "Timeline", title, cat = "blue", milestones }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      const n = Math.min(milestones.length, 5), x0 = MX + 1.15, x1 = MX + CW - 1.15, baseY = 3.7;
      connect(s, x0, baseY, x1, baseY, cc.c, 2.5);
      milestones.slice(0, 5).forEach((m, i) => {
        const x = n === 1 ? (x0 + x1) / 2 : x0 + i * ((x1 - x0) / (n - 1));
        s.addShape(shapes.OVAL, { x: x - 0.11, y: baseY - 0.11, w: 0.22, h: 0.22, fill: { color: cc.c }, line: { color: BRAND.surface, width: 2 } });
        if (m.date) s.addText(m.date, { x: x - 1.0, y: baseY - 0.62, w: 2.0, h: 0.3, align: "center", fontFace: BRAND.font.mono, fontSize: 11, bold: true, color: cc.d, margin: 0 });
        s.addText(m.title, { x: x - 1.13, y: baseY + 0.22, w: 2.26, h: 0.5, align: "center", fontFace: BRAND.font.display, fontSize: 12.5, bold: true, color: BRAND.text, valign: "top", lineSpacingMultiple: 1.0, margin: 0 });
        if (m.desc) s.addText(m.desc, { x: x - 1.18, y: baseY + 0.92, w: 2.36, h: 1.4, align: "center", fontFace: BRAND.font.body, fontSize: 10, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
      });
      footer(s, page, total); return s;
    },

    /* 9. 핵심 지표 (라이트, 큰 수치) */
    kpis({ kicker = "Key Metrics", title, cat = "blue", stats, note }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const cycle = ["blue", "emerald", "violet", "amber"], n = Math.min(stats.length, 4), gap = 0.3, cw = (CW - gap * (n - 1)) / n;
      const h = 2.7, y = 1.7 + Math.max(0, (4.9 - h - (note ? 0.5 : 0)) / 2); // 세로 중앙 정렬(노트 공간 고려)
      stats.slice(0, 4).forEach((st, i) => {
        statCallout(s, { x: MX + i * (cw + gap), y, w: cw, h, value: st.value, unit: st.unit, label: st.label, cat: st.cat || cycle[i % 4] });
      });
      if (note) s.addText(note, { x: MX, y: y + h + 0.2, w: CW, h: 0.4, align: "center", fontFace: BRAND.font.body, fontSize: 11.5, italic: true, color: BRAND.muted, margin: 0 });
      footer(s, page, total); return s;
    },

    /* 10. 인용·강조 (다크, 풀쿼트) */
    quote({ text, author, role, cat = "violet", kicker = "Quote" }) {
      page++; const s = newSlide(true);
      s.addShape(shapes.OVAL, { x: 10.0, y: 2.8, w: 5.6, h: 5.6, fill: { color: BRAND.purple, transparency: 86 }, line: { type: "none" } });
      s.addText("\u201C", { x: 0.7, y: 0.7, w: 3, h: 2.2, fontFace: BRAND.font.display, fontSize: 150, bold: true, color: C(cat).c, margin: 0 });
      s.addText(text, { x: 1.0, y: 2.55, w: 11.3, h: 2.6, fontFace: BRAND.font.display, fontSize: 27, bold: true, color: BRAND.white, valign: "top", lineSpacingMultiple: 1.18, margin: 0 });
      s.addShape(shapes.ROUNDED_RECTANGLE, { x: 1.02, y: 5.5, w: 0.5, h: 0.06, rectRadius: 0.03, fill: { color: BRAND.purpleLite }, line: { type: "none" } });
      if (author) s.addText([{ text: author, options: { bold: true, color: BRAND.white, fontFace: BRAND.font.display, fontSize: 15 } }, ...(role ? [{ text: "   " + role, options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 12 } }] : [])], { x: 1.02, y: 5.7, w: 11, h: 0.4, valign: "middle", margin: 0 });
      footer(s, page, total); return s;
    },

    /* 11. Q&A (라이트, 카드 2열) */
    qna({ kicker = "Q&A", title, cat = "emerald", pairs }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      const n = Math.min(pairs.length, 4), gap = 0.4, cw = (CW - gap) / 2, ch = 2.3, rowGap = 0.25;
      const nrows = Math.ceil(n / 2), blockH = nrows * ch + (nrows - 1) * rowGap;
      const y0 = 1.74 + Math.max(0, (6.6 - 1.74 - blockH) / 2);
      pairs.slice(0, 4).forEach((p, i) => {
        const r = Math.floor(i / 2), c = i % 2, cx = MX + c * (cw + gap), cy = y0 + r * (ch + rowGap);
        card(s, cx, cy, cw, ch, cat, true);
        s.addText("Q", { x: cx + 0.24, y: cy + 0.18, w: 0.5, h: 0.4, fontFace: BRAND.font.mono, fontSize: 16, bold: true, color: cc.c, margin: 0 });
        s.addText(p.q, { x: cx + 0.72, y: cy + 0.18, w: cw - 0.95, h: 0.7, fontFace: BRAND.font.display, fontSize: 13, bold: true, color: BRAND.text, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
        s.addText("A", { x: cx + 0.24, y: cy + 1.0, w: 0.5, h: 0.4, fontFace: BRAND.font.mono, fontSize: 16, bold: true, color: cc.d, margin: 0 });
        s.addText(p.a, { x: cx + 0.72, y: cy + 1.0, w: cw - 0.95, h: ch - 1.15, fontFace: BRAND.font.body, fontSize: 11, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 });
      });
      footer(s, page, total); return s;
    },

    /* 12. 마무리·CTA (다크) */
    closingCTA({ kicker = "Takeaways", title, subtitle, points = [], contact, footerText }) {
      page++; const s = darkBase(kicker, title, subtitle, true);
      const y0 = subtitle ? 2.5 : 2.2;
      points.slice(0, 3).forEach((p, i) => {
        const cy = y0 + i * 0.92;
        s.addShape(shapes.ROUNDED_RECTANGLE, { x: 0.7, y: cy, w: 11.9, h: 0.78, rectRadius: 0.07, fill: { color: BRAND.bgDarkAlt }, line: { color: "26324F", width: 1 } });
        s.addText("→", { x: 0.95, y: cy, w: 0.5, h: 0.78, valign: "middle", fontFace: BRAND.font.display, fontSize: 18, bold: true, color: BRAND.purpleLite, margin: 0 });
        s.addText(p, { x: 1.5, y: cy, w: 10.9, h: 0.78, valign: "middle", fontFace: BRAND.font.body, fontSize: 13.5, color: "E2E8F0", lineSpacingMultiple: 1.0, margin: 0 });
      });
      s.addText([{ text: (footerText || "더 알아보기 → "), options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 12.5 } }, { text: "insighta.one", options: { color: BRAND.purpleLite, bold: true, fontFace: BRAND.font.mono, fontSize: 13, hyperlink: { url: LINK } } }, ...(contact ? [{ text: "    " + contact, options: { color: BRAND.faint, fontFace: BRAND.font.body, fontSize: 11.5 } }] : [])], { x: 0.7, y: 6.5, w: 12, h: 0.4, valign: "middle", margin: 0 });
      footer(s, page, total); return s;
    },

    /* 13. 개념 심화 (라이트, 이미지 없이 한 개념을 꽉 채움) — 적응형 explainer의 핵심 */
    conceptDeep({ kicker = "Concept", title, cat = "blue", definition, how = [], points = [], intuition }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat }); const cc = C(cat);
      if (definition) s.addText(definition, { x: MX, y: 1.58, w: CW, h: 0.74, fontFace: BRAND.font.body, fontSize: 13.5, color: BRAND.text, valign: "top", lineSpacingMultiple: 1.12, margin: 0 });
      const colY = 2.5, colH = 3.32, gap = 0.4, lw = (CW - gap) * 0.46, rw = (CW - gap) * 0.54, rx = MX + lw + gap;
      // 좌: 작동 방식(번호 단계)
      card(s, MX, colY, lw, colH, cat);
      s.addText("작동 방식", { x: MX + 0.26, y: colY + 0.16, w: lw - 0.5, h: 0.34, fontFace: BRAND.font.display, fontSize: 13, bold: true, color: cc.d, margin: 0 });
      { const hs = how.slice(0, 4), n = Math.max(hs.length, 1), rh = Math.min(0.92, (colH - 0.66) / n); let yy = colY + 0.62;
        hs.forEach((st, i) => { s.addShape(shapes.OVAL, { x: MX + 0.26, y: yy + 0.02, w: 0.36, h: 0.36, fill: { color: cc.c }, line: { type: "none" } });
          s.addText(String(i + 1), { x: MX + 0.26, y: yy + 0.02, w: 0.36, h: 0.36, align: "center", valign: "middle", fontFace: BRAND.font.display, fontSize: 12, bold: true, color: BRAND.white, margin: 0 });
          s.addText(typeof st === "string" ? st : st.t, { x: MX + 0.74, y: yy, w: lw - 1.0, h: rh, fontFace: BRAND.font.body, fontSize: 11.5, color: BRAND.muted, valign: "top", lineSpacingMultiple: 1.05, margin: 0 }); yy += rh; }); }
      // 우: 핵심 포인트
      card(s, rx, colY, rw, colH, cat === "blue" ? "violet" : "blue");
      const rc = C(cat === "blue" ? "violet" : "blue");
      s.addText("핵심 포인트", { x: rx + 0.26, y: colY + 0.16, w: rw - 0.5, h: 0.34, fontFace: BRAND.font.display, fontSize: 13, bold: true, color: rc.d, margin: 0 });
      { const ps = points.slice(0, 3), n = Math.max(ps.length, 1), rh = (colH - 0.66) / n; let yy = colY + 0.62;
        ps.forEach((p) => { s.addShape(shapes.OVAL, { x: rx + 0.28, y: yy + 0.06, w: 0.13, h: 0.13, fill: { color: rc.c }, line: { type: "none" } });
          s.addText([{ text: (p.h ? p.h + "  " : ""), options: { bold: true, color: rc.d, fontFace: BRAND.font.display, fontSize: 12 } }, { text: p.t || "", options: { color: BRAND.muted, fontFace: BRAND.font.body, fontSize: 11.5 } }], { x: rx + 0.54, y: yy, w: rw - 0.8, h: rh - 0.08, valign: "top", lineSpacingMultiple: 1.06, margin: 0 }); yy += rh; }); }
      // 하단 직관 콜아웃
      if (intuition) { s.addShape(shapes.ROUNDED_RECTANGLE, { x: MX, y: 6.0, w: CW, h: 0.62, rectRadius: 0.07, fill: { color: cc.t }, line: { color: cc.c, width: 1 } });
        s.addText([{ text: "직관  ", options: { bold: true, color: cc.d, fontFace: BRAND.font.display, fontSize: 11.5 } }, { text: intuition, options: { color: BRAND.text, fontFace: BRAND.font.body, fontSize: 11.5 } }], { x: MX + 0.26, y: 6.0, w: CW - 0.5, h: 0.62, valign: "middle", lineSpacingMultiple: 1.05, margin: 0 }); }
      footer(s, page, total); return s;
    },

    /* 14. 재생성 figure (PR-A) — CV가 수치화→재렌더한 PNG를 본문 폭으로 배치.
       원본 스크린샷이 아니라 chart_regen/equation 렌더 결과만 들어온다(ADR 0003 P2). */
    figureSlide({ kicker = "Figure", title, cat = "blue", img, caption }) {
      page++; const s = newSlide(); header(s, { kicker, title, cat });
      const y = 1.62, h = 4.4;
      s.addImage({ path: img, x: MX, y, w: CW, h, sizing: { type: "contain", w: CW, h } });
      if (caption) s.addText(caption, { x: MX, y: y + h + 0.12, w: CW, h: 0.4, align: "center", fontFace: BRAND.font.body, fontSize: 11.5, italic: true, color: BRAND.muted, margin: 0 });
      footer(s, page, total); return s;
    },

    save(fileName) { return pres.writeFile({ fileName }); },
    get page() { return page; },
  };
  return S;
}
module.exports = { makeSlides };
