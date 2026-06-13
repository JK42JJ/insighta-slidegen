/* deck_recipes.js — Layer 2: 영상 유형별 '덱 레시피'(12~20장, 간지 없음).
 * 길이는 콘텐츠가 결정한다: 각 단위(단계·항목·국면·논점)를 conceptDeep 한 장씩 꽉 채워 자연 확장.
 * 모든 장표는 실질 내용(설명형 카드·표·비교·지표·Q&A·심화). 빈 전환(간지) 금지.
 *   const { buildRecipe } = require("./deck_recipes.js");
 *   await buildRecipe("howto", content, "out.pptx", { link });
 */
const path = require("path");
const { createDeck } = require(path.join(__dirname, "insighta_deck.js"));
const { makeSlides } = require(path.join(__dirname, "slide_templates.js"));

const SEC_CYCLE = ["blue", "emerald", "violet", "amber", "rose", "slate", "blue", "emerald"];
function firstSentence(t) { return String(t || "").split(/(?<=[.!?。])\s/)[0].slice(0, 90); }

/* 심화 단위 → conceptDeep 한 장. u = {title, headline?, summary, details:[..], points:[{h,t}], note} */
function deepUnit(u, cat) {
  return ["conceptDeep", { kicker: u.kicker || u.title, title: u.headline || u.title, cat,
    definition: u.summary || u.definition, how: u.details || u.how || [], points: u.points || [], intuition: u.note || u.intuition }];
}

/* ===== 적응형 explainer (강의) ===== */
function buildExplainerPlan(c) {
  const secs = (c.sections || []).slice(0, 8);
  const overview = c.overview || secs.slice(0, 4).map((s) => ({ h: s.title, t: firstSentence(s.definition) }));
  const essence = c.essence || secs.slice(0, 4).map((s) => ({ h: s.title, t: s.intuition || firstSentence(s.definition) }));
  const P = [["title", { kicker: c.kicker || "EXPLAINER", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
  P.push(["keyPoints", { kicker: "Overview", title: c.overviewTitle || "큰 그림", cat: "blue", lead: c.overviewLead, points: overview }]);
  if (secs.length >= 4) P.push(["agenda", { kicker: "Roadmap", title: c.agendaTitle || "학습 지도", cat: "violet", items: secs.map((s) => ({ label: s.title, desc: s.tagline || firstSentence(s.definition) })) }]);
  secs.forEach((s, i) => {
    const cat = SEC_CYCLE[i % SEC_CYCLE.length];
    P.push(["conceptDeep", { kicker: s.title, title: s.headline || s.title, cat, definition: s.definition, how: s.how || [], points: s.points || [], intuition: s.intuition }]);
    if (s.compare) P.push(["comparisonTable", { kicker: s.title, title: s.compareTitle || (s.title + " — 비교"), cat, intro: s.compareIntro, headers: s.compare.headers, rows: s.compare.rows }]);
    else if (s.examples) P.push(["keyPoints", { kicker: s.title, title: s.examplesTitle || (s.title + " — 사례·적용"), cat, points: s.examples }]);
  });
  if (c.compare) P.push(["comparisonTable", { kicker: "Compare", title: c.compareTitle || "유형·접근 비교", cat: "slate", intro: c.compareIntro, headers: c.compare.headers, rows: c.compare.rows }]);
  if (c.metrics) P.push(["kpis", { kicker: "By the numbers", title: c.metricsTitle || "핵심 수치", stats: c.metrics }]);
  P.push(["keyPoints", { kicker: "Essence", title: c.essenceTitle || "본질 정리", cat: "emerald", points: essence }]);
  if (c.curiosity) P.push(["qna", { kicker: "Go deeper", title: c.curiosityTitle || "더 들어가 보기", cat: "violet", pairs: c.curiosity }]);
  P.push(["closingCTA", { title: c.closeTitle || "정리 — 다음 단계", subtitle: c.closeSub, points: c.actions || [], contact: c.contact }]);
  return P;
}

/* qna는 4개씩 분할 */
function qnaSlides(P, pairs, title, cat) {
  for (let i = 0; i < (pairs || []).length; i += 4) P.push(["qna", { kicker: "Q&A", title, cat, pairs: pairs.slice(i, i + 4) }]);
}

const PLANS = {
  /* ② 하우투 — 단계마다 한 장씩 심화 */
  howto(c) {
    const steps = (c.steps || []).slice(0, 8);
    const P = [["title", { kicker: c.kicker || "HOW-TO", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "Overview", title: c.overviewTitle || "한눈에 보기", cat: "blue", lead: c.overviewLead, points: c.overview }]);
    if (c.prereq) P.push(["keyPoints", { kicker: "Prerequisites", title: c.prereqTitle || "준비물·전제", cat: "emerald", points: c.prereq }]);
    P.push(["processSteps", { kicker: "Steps", title: c.stepsTitle || "전체 흐름", cat: "blue", steps: steps.map((s) => ({ title: s.title, sub: s.tagline || firstSentence(s.summary) })), note: c.stepsNote }]);
    steps.forEach((s, i) => P.push(deepUnit({ ...s, kicker: `STEP ${i + 1}` }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.tools) P.push(["comparisonTable", { kicker: "Options", title: c.toolsTitle || "도구·옵션 비교", cat: "slate", intro: c.toolsIntro, headers: c.tools.headers, rows: c.tools.rows }]);
    if (c.pitfalls) P.push(["twoColumn", { kicker: "Tips", title: c.pitfallsTitle || "권장 vs 주의", left: { h: "권장", cat: "emerald", items: c.pitfalls.do }, right: { h: "주의", cat: "rose", items: c.pitfalls.dont } }]);
    if (c.troubleshoot) P.push(["keyPoints", { kicker: "Troubleshooting", title: c.troubleshootTitle || "흔한 오류와 해결", cat: "rose", points: c.troubleshoot }]);
    if (c.metrics) P.push(["kpis", { kicker: "Results", title: c.metricsTitle || "기대 효과", stats: c.metrics }]);
    P.push(["closingCTA", { title: c.closeTitle || "정리 — 직접 해보기", subtitle: c.closeSub, points: c.actions || [], contact: c.contact }]);
    return P;
  },

  /* ③ 리뷰 — 후보/측면마다 한 장씩 심화 */
  review(c) {
    const opts = (c.options || []).slice(0, 6);
    const P = [["title", { kicker: c.kicker || "REVIEW", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "Verdict", title: c.summaryTitle || "한 줄 평가 요약", cat: "blue", lead: c.summaryLead, points: c.summary }]);
    if (c.criteria) P.push(["keyPoints", { kicker: "Criteria", title: c.criteriaTitle || "무엇을 보았나", cat: "emerald", points: c.criteria }]);
    if (c.table) P.push(["comparisonTable", { kicker: "Spec", title: c.tableTitle || "항목별 비교", cat: "slate", intro: c.tableIntro, headers: c.table.headers, rows: c.table.rows }]);
    opts.forEach((o, i) => P.push(deepUnit({ ...o, kicker: o.title }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.pros) P.push(["twoColumn", { kicker: "Pros & Cons", title: c.prosTitle || "장점 vs 단점", left: { h: c.prosLabel || "장점", cat: "emerald", items: c.pros }, right: { h: c.consLabel || "단점", cat: "rose", items: c.cons } }]);
    if (c.scores) P.push(["kpis", { kicker: "Scores", title: c.scoresTitle || "핵심 점수", stats: c.scores }]);
    if (c.useCases) P.push(["keyPoints", { kicker: "Who for", title: c.useCasesTitle || "상황별 추천", cat: "amber", points: c.useCases }]);
    if (c.quote) P.push(["quote", { cat: "violet", text: c.quote.text, author: c.quote.author, role: c.quote.role }]);
    P.push(["closingCTA", { title: c.closeTitle || "추천 — 누구에게?", subtitle: c.closeSub, points: c.recommend || [], contact: c.contact }]);
    return P;
  },

  /* ④ 인터뷰 — 주제마다 한 장씩 심화 + Q&A */
  interview(c) {
    const themes = (c.themes || []).slice(0, 6);
    const P = [["title", { kicker: c.kicker || "CONVERSATION", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "Takeaways", title: c.takeTitle || "핵심 메시지", cat: "blue", lead: c.takeLead, points: c.takeaways }]);
    if (c.speaker) P.push(["keyPoints", { kicker: "Context", title: c.speakerTitle || "화자·배경", cat: "emerald", points: c.speaker }]);
    themes.forEach((t, i) => P.push(deepUnit({ ...t, kicker: t.title }, SEC_CYCLE[i % SEC_CYCLE.length])));
    qnaSlides(P, c.qa, c.qaTitle || "주요 문답", "emerald");
    if (c.quote) P.push(["quote", { cat: "violet", text: c.quote.text, author: c.quote.author, role: c.quote.role }]);
    if (c.implications) P.push(["keyPoints", { kicker: "So what", title: c.implTitle || "시사점", cat: "amber", points: c.implications }]);
    P.push(["closingCTA", { title: c.closeTitle || "정리", subtitle: c.closeSub, points: c.actions || [], contact: c.contact }]);
    return P;
  },

  /* ⑤ 뉴스 — 쟁점/관점마다 한 장씩 심화 */
  news(c) {
    const angles = (c.angles || []).slice(0, 6);
    const P = [["title", { kicker: c.kicker || "BRIEFING", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "What happened", title: c.whatTitle || "무슨 일이 일어났나", cat: "blue", lead: c.whatLead, points: c.what }]);
    if (c.metrics) P.push(["kpis", { kicker: "By the numbers", title: c.metricsTitle || "핵심 수치", stats: c.metrics }]);
    if (c.causes) P.push(["twoColumn", { kicker: "Why", title: c.whyTitle || "원인과 영향", left: { h: c.causeLabel || "배경·원인", cat: "violet", items: c.causes }, right: { h: c.effectLabel || "영향·파장", cat: "amber", items: c.effects } }]);
    angles.forEach((a, i) => P.push(deepUnit({ ...a, kicker: a.title }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.timeline) P.push(["timeline", { kicker: "Timeline", title: c.timelineTitle || "전개 과정", cat: "blue", milestones: c.timeline }]);
    if (c.reactions) P.push(["twoColumn", { kicker: "Reactions", title: c.reactionsTitle || "입장 차이", left: { h: c.proLabel || "찬성·기대", cat: "emerald", items: c.reactions.pro }, right: { h: c.conLabel || "우려·반대", cat: "rose", items: c.reactions.con } }]);
    if (c.outlook) P.push(["keyPoints", { kicker: "Outlook", title: c.outlookTitle || "함의·전망", cat: "emerald", points: c.outlook }]);
    P.push(["closingCTA", { title: c.closeTitle || "정리 — 무엇을 볼 것인가", subtitle: c.closeSub, points: c.watch || [], contact: c.contact }]);
    return P;
  },

  /* ⑥ 리스티클 — 상위 항목마다 한 장씩 심화 + 전체 순위 */
  listicle(c) {
    const items = (c.items || []).slice(0, 10);
    const top = items.slice(0, 8);
    const P = [["title", { kicker: c.kicker || "RANKING", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    if (c.criteria) P.push(["keyPoints", { kicker: "Criteria", title: c.criteriaTitle || "선정 기준", cat: "blue", lead: c.criteriaLead, points: c.criteria }]);
    P.push(["listRanked", { kicker: "Ranking", title: c.listTitle || "전체 순위", cat: "amber", items: items.slice(0, 8) }]);
    top.forEach((it, i) => P.push(deepUnit({ title: (it.rank || i + 1) + ". " + it.title, headline: it.title, summary: it.desc || it.summary, details: it.details, points: it.points, note: it.note, kicker: "#" + (it.rank || i + 1) }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.topCompare) P.push(["comparisonTable", { kicker: "Head-to-head", title: c.topCompareTitle || "상위 비교", cat: "slate", intro: c.topCompareIntro, headers: c.topCompare.headers, rows: c.topCompare.rows }]);
    P.push(["closingCTA", { title: c.closeTitle || "정리 — 어떤 걸 고를까", subtitle: c.closeSub, points: c.actions || [], contact: c.contact }]);
    return P;
  },

  /* ⑦ 사례·스토리 — 국면마다 한 장씩 심화 + 타임라인 */
  story(c) {
    const phases = (c.phases || []).slice(0, 6);
    const P = [["title", { kicker: c.kicker || "CASE STUDY", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "Context", title: c.bgTitle || "배경", cat: "blue", lead: c.bgLead, points: c.background }]);
    if (c.timeline) P.push(["timeline", { kicker: "Arc", title: c.arcTitle || "전개 과정", cat: "violet", milestones: c.timeline }]);
    phases.forEach((p, i) => P.push(deepUnit({ ...p, kicker: p.title }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.turning) P.push(["twoColumn", { kicker: "Lessons", title: c.turningTitle || "무엇이 갈랐나", left: { h: c.winLabel || "결정적 선택", cat: "emerald", items: c.turning.win }, right: { h: c.missLabel || "치명적 실수", cat: "rose", items: c.turning.miss } }]);
    if (c.quote) P.push(["quote", { cat: "violet", text: c.quote.text, author: c.quote.author, role: c.quote.role }]);
    if (c.metrics) P.push(["kpis", { kicker: "Outcome", title: c.metricsTitle || "결과", stats: c.metrics }]);
    if (c.lessons) P.push(["keyPoints", { kicker: "Lessons", title: c.lessonsTitle || "교훈", cat: "emerald", points: c.lessons }]);
    P.push(["closingCTA", { title: c.closeTitle || "정리 — 우리에게 주는 의미", subtitle: c.closeSub, points: c.actions || [], contact: c.contact }]);
    return P;
  },

  /* ⑧ 발표·키노트 — 논점마다 한 장씩 심화 */
  talk(c) {
    const args = (c.arguments || []).slice(0, 6);
    const P = [["title", { kicker: c.kicker || "KEYNOTE", title: c.title, subtitle: c.subtitle, pills: c.pills || [] }]];
    P.push(["keyPoints", { kicker: "Thesis", title: c.thesisTitle || "핵심 주장", cat: "blue", lead: c.thesisLead, points: c.thesis }]);
    if (c.metrics) P.push(["kpis", { kicker: "Evidence", title: c.metricsTitle || "근거 수치", stats: c.metrics }]);
    args.forEach((a, i) => P.push(deepUnit({ ...a, kicker: a.title }, SEC_CYCLE[i % SEC_CYCLE.length])));
    if (c.compare) P.push(["comparisonTable", { kicker: "Compare", title: c.compareTitle || "기존 vs 제안", cat: "slate", intro: c.compareIntro, headers: c.compare.headers, rows: c.compare.rows }]);
    if (c.quote) P.push(["quote", { cat: "violet", text: c.quote.text, author: c.quote.author, role: c.quote.role }]);
    if (c.plan) P.push(["processSteps", { kicker: "How", title: c.planTitle || "실행 계획", cat: "blue", steps: c.plan, note: c.planNote }]);
    if (c.impact) P.push(["keyPoints", { kicker: "Impact", title: c.impactTitle || "기대 효과", cat: "emerald", points: c.impact }]);
    P.push(["closingCTA", { title: c.closeTitle || "제안 — 다음 단계", subtitle: c.closeSub, points: c.asks || [], contact: c.contact }]);
    return P;
  },
};

/* 콘텐츠 최소치 — 12장+ 보장(심화 단위 수가 핵심 길이 동인) */
const MIN = {
  howto: { steps: 5, overview: 3 }, review: { options: 3, summary: 3 }, interview: { themes: 4, takeaways: 3, qa: 5 },
  news: { angles: 4, what: 3 }, listicle: { items: 6 }, story: { phases: 4, background: 3 }, talk: { arguments: 4, thesis: 3 },
};
function checkContent(type, c) {
  if (type === "explainer") {
    const n = (c.sections || []).length;
    return n < 6 ? [`explainer.sections: ${n}개 < 권장 6개 — 12장 미만(폴백은 6섹션 필요), 리서치로 개념 확보`] : [];
  }
  const need = MIN[type] || {}, warn = [];
  for (const [k, m] of Object.entries(need)) {
    const n = Array.isArray(c[k]) ? c[k].length : 0;
    if (n < m) warn.push(`${type}.${k}: ${n}개 < 권장 ${m}개 — 12장 미만 위험, 리서치로 보강`);
  }
  return warn;
}

function planFor(type, content) {
  if (type === "explainer") return buildExplainerPlan(content);
  const fn = PLANS[type];
  if (!fn) throw new Error("unknown recipe: " + type + " (지원: explainer, " + Object.keys(PLANS).join(", ") + ")");
  return fn(content);
}

/* PR-A: place regenerated figures the LLM referenced.
 * content.figures = [{figure_id, kind, title?, caption?}] — figure_id keys into
 * opts.figureAssets ({figure_id → local PNG path}, built from chart_regen /
 * equation render). Only figures whose asset RESOLVED get a slide; an absent
 * asset is silently skipped (label-only — never a raw frame, ADR 0003 P2).
 * Returns the count placed (feeds the validate figure gate, §1d). */
function injectFigureSlides(plan, content, figureAssets, figureTables) {
  const refs = Array.isArray(content.figures) ? content.figures : [];
  if (!refs.length) return 0;
  const SEC = ["blue", "emerald", "violet", "amber", "rose", "slate"];
  const figurePlan = [];
  refs.forEach((ref, i) => {
    if (!ref || !ref.figure_id) return;
    const cat = SEC[i % SEC.length];
    // A1: a table-kind figure with a valid struct → NATIVE pptx table (editable),
    // not a 300dpi raster. Empty/unparseable struct falls through to the image
    // path below (graceful fallback — an image beats a broken empty table).
    const tbl = figureTables ? figureTables[ref.figure_id] : null;
    if (
      ref.kind === "table" && tbl &&
      Array.isArray(tbl.headers) && tbl.headers.length &&
      Array.isArray(tbl.rows) && tbl.rows.length
    ) {
      figurePlan.push(["figureTableSlide", {
        kicker: "Table", title: ref.title || ref.caption || "표",
        cat, headers: tbl.headers, rows: tbl.rows, caption: ref.caption || "",
      }]);
      return;
    }
    const img = figureAssets ? figureAssets[ref.figure_id] : null;
    if (!img) return; // unresolved → label-only (no slide)
    figurePlan.push(["figureSlide", {
      kicker: "Figure", title: ref.title || ref.caption || "그림",
      cat, img, caption: ref.caption || "",
    }]);
  });
  if (!figurePlan.length) return 0;
  // Insert before the closing slide (last plan entry) so figures sit in-body.
  const insertAt = Math.max(0, plan.length - 1);
  plan.splice(insertAt, 0, ...figurePlan);
  return figurePlan.length;
}

async function buildRecipe(type, content, outPath, opts = {}) {
  const warn = checkContent(type, content);
  if (warn.length && !opts.silent) warn.forEach((w) => console.warn("⚠ 밀도:", w));
  const plan = planFor(type, content);
  const placed = injectFigureSlides(plan, content, opts.figureAssets, opts.figureTables);
  if (placed && !opts.silent) console.warn("figures placed:", placed);
  const D = createDeck({ title: content.title || type });
  const S = makeSlides(D, { total: plan.length, link: opts.link || "https://insighta.one" });
  for (const [method, args] of plan) S[method](args);
  return S.save(outPath);
}

module.exports = { buildRecipe, planFor, checkContent, buildExplainerPlan, injectFigureSlides, PLANS, RECIPE_TYPES: ["explainer", ...Object.keys(PLANS)] };
