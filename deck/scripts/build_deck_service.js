/* build_deck_service.js — 임의 mandala book_json → .pptx (결정성, fail-closed).
 * insighta 버튼이 부를 빌드 서비스의 핵심 로직. LLM auto-route 없음 — book_json을
 * 규칙으로 visual-deck 콘텐츠 객체에 매핑(A1 결정성 매퍼) → makeTemplates 빌드.
 *
 * 사용: node build_deck_service.js <book_json_path> <out.pptx> [figures_json_path]
 *   figures_json(선택): [{figure_id, kind:'diagram'|'table'|'chart', struct, png?}]
 *   - diagram/chart: struct → deck_tools 재작도 PNG → figureFull
 *   - table: struct(headers/rows) → comparisonTable(네이티브)
 * 출력: stdout JSON {ok, slides, out}. fail-closed: figure 없거나 깨지면 텍스트 덱 완성.
 */
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { createDeck } = require("./insighta_deck.js");
const { makeTemplates } = require("./deck_templates.js");

const SK = __dirname;
const PY = process.env.SLIDEGEN_PY || "python3";
const CATS = ["blue", "emerald", "violet", "amber", "rose", "slate"];
const asArr = (v) => (Array.isArray(v) ? v : []);
// 결정성 provenance 제거: 소스 narrative의 "이 영상에서는/본 강의/강사/채널 구독"
// 같은 출처·메타 구문을 덱에 넣기 전에 제거(주제 어휘 "영상 제작"은 보존).
const PROV = /(?:이|본|그)\s*영상[^\s,.]*[\s,]*|영상\s*에서[^\s,.]*[\s,]*|본\s*강의[^\s,.]*[\s,]*|강사님?[^\s,.]*[\s,]*|채널\s*구독[^\s,.]*\s*|구독.{0,8}좋아요\s*/g;
const str = (v) => (typeof v === "string" ? v.replace(PROV, "").replace(/\s{2,}/g, " ").trim() : "");
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/* diagram/chart struct → 재작도 PNG (deck_tools). 실패 시 null(fail-closed). */
function renderFigure(struct, kind, figId, figDir) {
  try {
    const out = path.join(figDir, `${figId}.png`);
    const mod = kind === "chart" ? "deck_tools.chart_regen" : "deck_tools.diagram_regen";
    const st = { ...struct }; delete st.insight; // 영문 baked 캡션 제거
    const res = execFileSync(PY, ["-m", mod], {
      cwd: process.env.SLIDEGEN_PY_DIR || path.join(SK, "..", "..", "py"),
      input: JSON.stringify({ struct: st, out }), encoding: "utf8", timeout: 60000,
    });
    const png = (JSON.parse(res) || {}).png;
    return png && fs.existsSync(png) ? path.basename(png) : null;
  } catch { return null; }
}

function buildDeck(book, figures, outPath) {
  const figDir = fs.mkdtempSync(path.join(require("os").tmpdir(), "deckfigs-"));
  const chapters = asArr(book.chapters).filter((c) => asArr(c.sections).length);
  const title = str(book.mandala_title) || "Insighta 만다라";
  const prog = (pct, stage) => process.stderr.write(`PROGRESS ${pct} ${stage}\n`);
  prog(5, "map");
  // 실계약: one_liner 없음 → 첫 narrative를 리드 문장으로. chapter.intro="" 는 안 씀.
  let firstNarr = "";
  for (const c of chapters) { for (const s of asArr(c.sections)) { const n = str(s.narrative); if (n) { firstNarr = n; break; } } if (firstNarr) break; }
  // 실계약: section.qa 실재 → curiosity에 실제 Q&A 사용(narrative 합성보다 우수).
  const allQa = [];
  for (const c of chapters) for (const s of asArr(c.sections)) for (const q of asArr(s.qa)) { if (str(q.q) && str(q.a)) allQa.push({ q: clip(str(q.q), 60), a: clip(str(q.a), 90) }); }

  // figure 분류 (입력 있을 때만; 없으면 텍스트 덱 — fail-closed)
  const figList = asArr(figures);
  const tables = figList.filter((f) => f.kind === "table" && f.struct && asArr(f.struct.headers).length && asArr(f.struct.rows).length);
  const figDiagrams = figList.filter((f) => (f.kind === "diagram" || f.kind === "chart") && f.struct);
  const diagrams = [];
  figDiagrams.forEach((f, idx) => {
    prog(10 + Math.round(60 * idx / Math.max(1, figDiagrams.length)), `render ${idx + 1}/${figDiagrams.length}`);
    const png = f.png && fs.existsSync(f.png) ? (fs.copyFileSync(f.png, path.join(figDir, `${f.figure_id}.png`)), `${f.figure_id}.png`)
      : renderFigure(f.struct, f.kind, f.figure_id || `fig${diagrams.length}`, figDir);
    if (png) diagrams.push({ ...f, png }); // 실패 시 skip(fail-closed)
  });
  prog(75, "assemble");

  // 슬라이드 수 계산(total 정확)
  const chapSlides = chapters.length;
  const total = 1 /*title*/ + 1 /*roadmap*/ + 1 /*conceptMap*/ + chapSlides + tables.length + diagrams.length + 1 /*essence*/ + 1 /*curiosity*/;
  const D = createDeck({ title, footer: title });
  const T = makeTemplates(D, { total, figDir, link: "https://insighta.one" });

  T.title({
    kicker: "INSIGHTA · 만다라", title: clip(title, 40),
    subtitle: clip(firstNarr || "여러 영상을 한 흐름으로 종합한 학습 덱", 70),
    pills: [["주제군", String(chapters.length)], ["영상", String(book.source_videos || asArr(book.chapters).reduce((n, c) => n + asArr(c.sections).length, 0))], ["구성", "개념지도+종합"]],
  });

  T.roadmapLoop({
    title: "큰 그림: 주제군들이 한 흐름으로",
    intro: clip(firstNarr || "주제군들은 아래 흐름으로 이어진다.", 90),
    stages: chapters.slice(0, 5).map((c) => ({ title: clip(str(c.title) || "", 10), sub: clip(str((asArr(c.sections)[0] || {}).title) || "", 12) })),
    loopNote: "주제군을 차례로 익히면 전체 그림이 완성된다",
    hooks: chapters.slice(0, 3).map((c) => ({ q: clip(str(c.title) || "주제", 26) + "?", a: clip(str((asArr(c.sections)[0] || {}).narrative) || "핵심을 탐구한다.", 70) })),
  });

  T.conceptMap({
    title: "한눈에 보는 지도",
    categories: chapters.slice(0, 6).map((c, i) => ({
      cat: CATS[i % CATS.length], name: clip(str(c.title) || `주제 ${i + 1}`, 18),
      count: asArr(c.sections).length,
      concepts: asArr(c.sections).slice(0, 6).map((s) => clip(str(s.title) || "—", 22)),
    })),
  });

  // 셀(주제군)마다 종합 슬라이드 — sections를 breadthGrid 항목으로(figure 없는 셀)
  chapters.forEach((c, i) => {
    const items = asArr(c.sections).slice(0, 6).map((s) => ({
      term: clip(str(s.title) || "—", 26),
      desc: clip(str(s.narrative) || str(s.summary) || "", 80),
    }));
    T.breadthGrid({ kicker: clip(str(c.title) || "주제", 20), title: clip(str(c.title) || `주제 ${i + 1}`, 30), cat: CATS[i % CATS.length], cols: items.length > 4 ? 3 : 2, items });
  });

  // 표 figure → 네이티브 비교표
  tables.forEach((f, i) => T.comparisonTable({
    kicker: "데이터 · 비교", title: clip(str(f.title) || "비교표", 30), cat: CATS[i % CATS.length],
    intro: clip(str(f.caption) || "", 90), headers: f.struct.headers.map((h) => clip(str(h) || "", 22)),
    rows: f.struct.rows.slice(0, 6).map((r) => asArr(r).map((cell) => clip(String(cell ?? ""), 28))),
  }));

  // diagram/chart figure → figureFull(하단 핵심포인트 카드로 채움)
  diagrams.forEach((f, i) => {
    const nodes = asArr(f.struct.nodes).map((n) => str(n.label) || str(n.id)).filter(Boolean).slice(0, 3);
    T.figureFull({
      kicker: "FIGURE", title: clip(str(f.title) || "개념 도식", 30), cat: CATS[i % CATS.length], figure: f.png,
      caption: clip(str(f.caption) || "CV 추출 → 벡터 재작도", 80),
      points: nodes.map((n, j) => ({ h: clip(n, 16), t: "" })).slice(0, 3).length
        ? [{ h: "구조", t: "CV가 프레임에서 추출한 구조를 벡터로 재작도." }, { h: "단계", t: clip(nodes.join(" → "), 70) }]
        : [],
    });
  });

  T.essenceLoop({
    title: clip(`본질 — ${title}`, 44),
    stages: chapters.slice(0, 5).map((c) => ({ title: clip(str(c.title) || "", 10), sub: "" })),
    loopNote: "각 주제군이 한 흐름으로 이어진다",
    synthesisRuns: [{ text: title, options: { bold: true, color: "C7D2FE" } }, { text: " — 주제군들을 하나의 일관된 학습 흐름으로 종합한다.", options: { color: "AEB8CC" } }],
  });

  T.curiosity({
    title: "더 들어가 보고 싶다면", footerText: "각 주제군을 직접 깊이 파보자. ",
    qa: (allQa.length ? allQa.slice(0, 4)
      : chapters.slice(0, 4).map((c) => ({ q: clip(str(c.title) || "주제", 30) + "?", a: clip(str((asArr(c.sections)[0] || {}).narrative) || "핵심 개념을 더 탐구해보자.", 90) }))),
  });

  prog(92, "save");
  return T.save(outPath).then(() => { prog(100, "done"); return { ok: true, slides: T.page, out: outPath, figures: { tables: tables.length, diagrams: diagrams.length } }; });
}

(async () => {
  const [bookPath, outPath, figPath] = process.argv.slice(2);
  if (!bookPath || !outPath) { console.error("usage: node build_deck_service.js <book_json> <out.pptx> [figures_json]"); process.exit(2); }
  const book = JSON.parse(fs.readFileSync(bookPath, "utf8"));
  const figures = figPath && fs.existsSync(figPath) ? JSON.parse(fs.readFileSync(figPath, "utf8")) : [];
  try {
    const r = await buildDeck(book, figures, outPath);
    console.log(JSON.stringify(r));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, error: String(e).slice(0, 300) }));
    process.exit(1);
  }
})();
