/* router.js — Layer 3: 임의 영상 → 유형 분류 → (LLM 내용추출) → 레시피 빌드.
 *
 * 하이브리드 분류: 휴리스틱(키워드·구조) 1차 → 불확실하면 LLM 확정.
 * 코드는 결정적·테스트 가능. LLM 호출은 주입(inject)식이라 Claude API/OpenRouter 어디든 꽂힌다.
 *
 *   const { route, buildFromVideo, buildExtractionPrompt } = require("./router.js");
 *   const type = await route({ title, description, transcript }, { mode: "hybrid", llm });
 *   await buildFromVideo({ title, description, transcript }, "out.pptx", { extract, classify, link });
 */
const path = require("path");
const { buildRecipe, RECIPE_TYPES } = require(path.join(__dirname, "deck_recipes.js"));

/* 유형 정의(분류 프롬프트·문서 공용) */
const TYPES = {
  explainer: "개념·원리를 가르치는 강의/설명 (what is, 기초, 원리, explained)",
  howto:     "단계로 따라 하는 방법/튜토리얼 (how to, tutorial, 설치, 만들기, 방법)",
  review:    "제품·기술을 평가/비교 (review, vs, 비교, 후기, 장단점, best)",
  interview: "대담/팟캐스트/AMA 등 문답·대화 (interview, podcast, Q&A, guest, 대담)",
  news:      "사건·발표의 분석/브리핑 (news, breaking, 분석, 사태, explained event)",
  listicle:  "순위/리스트 (top N, N가지, best 10, ranking, 리스트)",
  story:     "사례·다큐·서사 (story of, case study, 흥망, 다큐, 이야기)",
  talk:      "주장 중심 발표/키노트/피치 (keynote, talk, TED, 강연, pitch)",
};

/* 키워드 사전(영/한). title 가중3 · description 2 · transcript 1 */
const KW = {
  explainer: ["explained", "what is", "introduction to", "intro to", "basics", "fundamental", "기초", "개념", "원리", "이해", "쉽게", "정리"],
  howto:     ["how to", "how-to", "tutorial", "step by step", "guide", "setup", "set up", "install", "build a", "방법", "하는 법", "튜토리얼", "설치", "만들기", "셋업", "가이드", "따라하기"],
  review:    ["review", "vs", "versus", "comparison", "compare", "best ", "worth it", "hands-on", "리뷰", "후기", "비교", "장단점", "추천", "내돈내산"],
  interview: ["interview", "podcast", "conversation with", "ama", "q&a", "qna", "sit down", "guest", "인터뷰", "팟캐스트", "대담", "문답", "초대"],
  news:      ["news", "breaking", "what happened", "explained:", "report", "announce", "analysis", "뉴스", "속보", "사태", "발표", "분석", "정리해드립니다", "이슈"],
  listicle:  ["top ", "best ", " ways", " things", " reasons", " tips", " tools", "ranking", "가지", "순위", "리스트", "베스트", "추천 "],
  story:     ["story of", "the rise", "the fall", "how they built", "case study", "documentary", "journey", "흥망", "사례", "이야기", "다큐", "성공기", "실패기"],
  talk:      ["keynote", " talk", "ted", "tedx", "lecture", "presentation", "pitch", "강연", "발표", "키노트", "피치", "세미나"],
};
const NUM_TITLE = /\b(top\s*)?\d{1,2}\b|\d{1,2}\s*(가지|개|선|위)/i; // 리스티클 신호

function _scan(text, words) {
  if (!text) return 0;
  const t = text.toLowerCase(); let n = 0;
  for (const w of words) { if (t.includes(w)) n++; }
  return n;
}

/* 휴리스틱 분류 — 결정적. {type, confidence(0~1), scores, signals} */
function classifyHeuristic({ title = "", description = "", transcript = "" } = {}) {
  const tSample = String(transcript).slice(0, 4000);
  const scores = {};
  for (const k of Object.keys(KW)) {
    scores[k] = _scan(title, KW[k]) * 3 + _scan(description, KW[k]) * 2 + _scan(tSample, KW[k]);
  }
  if (NUM_TITLE.test(title)) scores.listicle += 3;
  // 인터뷰 구조 신호: 화자 라벨/물음표 빈도
  const q = (tSample.match(/\?/g) || []).length;
  if (q >= 8) scores.interview += 2;
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  const [top, topScore] = ranked[0];
  const second = ranked[1][1];
  const total = ranked.reduce((s, [, v]) => s + v, 0) || 1;
  // confidence: 1위 점수 비중 + 1·2위 격차
  const confidence = Math.min(1, (topScore / total) * 0.6 + ((topScore - second) / (topScore || 1)) * 0.4);
  const type = topScore === 0 ? "explainer" : top; // 신호 없으면 가장 범용
  return { type, confidence: topScore === 0 ? 0.2 : Number(confidence.toFixed(2)), scores, signals: { numTitle: NUM_TITLE.test(title), questions: q } };
}

/* LLM 분류 프롬프트(주입형 llm 함수에 전달). JSON만 출력하도록 강제. */
function buildClassifyPrompt({ title = "", description = "", transcript = "" }) {
  const list = Object.entries(TYPES).map(([k, v]) => `- ${k}: ${v}`).join("\n");
  return [
    "다음 영상의 유형을 아래 8개 중 하나로 분류하라. 설명 없이 JSON만 출력한다.",
    "유형:\n" + list,
    `제목: ${title}`,
    `설명: ${String(description).slice(0, 500)}`,
    `자막(발췌): ${String(transcript).slice(0, 2000)}`,
    '출력 형식(JSON): {"type":"<위 8개 중 하나>","confidence":0~1,"reason":"한 줄"}',
  ].join("\n\n");
}

/* (선택) Anthropic Messages API 직접 호출 — 서비스/프로덕션용. 키 없으면 사용하지 않음. */
async function callAnthropic(prompt, { model = "claude-haiku-4-5", apiKey = process.env.ANTHROPIC_API_KEY } = {}) {
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY 없음 — llm 함수를 주입하거나 키를 설정하세요.");
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01" },
    body: JSON.stringify({ model, max_tokens: 300, messages: [{ role: "user", content: prompt }] }),
  });
  const data = await res.json();
  return (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
}

/* 라우팅: 휴리스틱 → 불확실하면 LLM 확정. llm(prompt)->string(JSON) 주입식. */
async function route(input, { mode = "hybrid", llm, threshold = 0.45 } = {}) {
  const h = classifyHeuristic(input);
  if (mode === "heuristic" || !llm) return { ...h, source: "heuristic" };
  if (mode === "hybrid" && h.confidence >= threshold) return { ...h, source: "heuristic" };
  // LLM 확정
  try {
    const raw = await llm(buildClassifyPrompt(input));
    const j = JSON.parse(String(raw).replace(/```json|```/g, "").trim());
    const type = RECIPE_TYPES.includes(j.type) ? j.type : h.type;
    return { type, confidence: j.confidence ?? h.confidence, reason: j.reason, scores: h.scores, source: "llm" };
  } catch (e) {
    return { ...h, source: "heuristic(fallback)", error: String(e) };
  }
}

/* 내용 추출 계약: 유형별 필수 필드. LLM이 이 스키마의 JSON을 자막에서 생성해야 한다. */
const EXTRACT_SCHEMA = {
  explainer: "{title, subtitle, pills?, overview:[{h,t}]>=3, sections:[{title, tagline, definition, how:[..3+], points:[{h,t}>=2], intuition, compare?, examples?}]>=6, compare?:{headers,rows}, metrics?, essence?:[{h,t}], curiosity?:[{q,a}], actions?:[..]}",
  howto:     "{title, subtitle, overview:[{h,t}]>=3, prereq?:[{h,t}], steps:[{title, summary(2문장), details:[..3+], points:[{h,t}>=2], note}]>=5, tools?:{headers,rows}, pitfalls?:{do:[..],dont:[..]}, troubleshoot?:[{h,t}], metrics?, actions?:[..]}",
  review:    "{title, subtitle, summary:[{h,t}]>=3, criteria?:[{h,t}], table?:{headers,rows}, options:[{title, summary, details:[..], points:[{h,t}], note}]>=3, pros?, cons?, scores?, useCases?:[{h,t}], quote?, recommend?:[..]}",
  interview: "{title, subtitle, takeaways:[{h,t}]>=3, speaker?:[{h,t}], themes:[{title, summary, details:[..], points:[{h,t}], note}]>=4, qa:[{q,a}]>=4, quote?, implications?:[{h,t}], actions?:[..]}",
  news:      "{title, subtitle, what:[{h,t}]>=3, metrics?, causes?:[..], effects?:[..], angles:[{title, summary, details:[..], points:[{h,t}], note}]>=4, timeline?, reactions?:{pro:[..],con:[..]}, outlook?:[{h,t}], watch?:[..]}",
  listicle:  "{title, subtitle, criteria?:[{h,t}], items:[{rank, title, desc, details:[..], points:[{h,t}], note}]>=6, topCompare?:{headers,rows}, actions?:[..]}",
  story:     "{title, subtitle, background:[{h,t}]>=3, timeline?, phases:[{title, summary, details:[..], points:[{h,t}], note}]>=4, turning?:{win:[..],miss:[..]}, quote?, metrics?, lessons?:[{h,t}], actions?:[..]}",
  talk:      "{title, subtitle, thesis:[{h,t}]>=3, metrics?, arguments:[{title, summary, details:[..], points:[{h,t}], note}]>=4, compare?:{headers,rows}, quote?, plan?:[{title,sub}], impact?:[{h,t}], asks?:[..]}",
};
const DENSITY_RULE = "분량·밀도 규칙(상용): 12~20장. 각 단계/항목/주제/쟁점/국면/논점은 details(3+)와 points({h,t} 2+)로 채운 '심화 단위'로 만들어 한 장씩 깊게 다룬다(이것이 길이를 자연스럽게 늘린다 — 빈 간지·섹션 구분 금지). keyPoints류는 {h,t} 2문장. 수치는 metrics, 비교는 table로 해석과 함께. 본문에 '영상/출처/채널/타임스탬프(mm:ss)' 등 메타 표현 금지 — 주제 자체만 설명.";
function buildExtractionPrompt(type, input) {
  return [
    `이 영상을 '${type}' 유형 슬라이드 덱으로 만들기 위한 콘텐츠를 자막에서 추출하라.`,
    DENSITY_RULE,
    "설명 없이 아래 스키마에 맞는 JSON만 출력한다.",
    "스키마: " + (EXTRACT_SCHEMA[type] || EXTRACT_SCHEMA.explainer),
    `제목: ${input.title || ""}`,
    `자막: ${String(input.transcript || "").slice(0, 12000)}`,
  ].join("\n\n");
}

/* 오케스트레이터: 분류 → 내용추출(LLM 주입) → 레시피 빌드. */
async function buildFromVideo(input, outPath, { classify, extract, llm, link, mode = "hybrid" } = {}) {
  const routed = classify ? await classify(input) : await route(input, { mode, llm });
  const type = routed.type;
  if (!extract) throw new Error("extract 함수 필요 — 자막→콘텐츠(JSON) 변환은 LLM 단계. buildExtractionPrompt(type,input) 사용.");
  const content = await extract(type, input); // {type 스키마}의 객체
  await buildRecipe(type, content, outPath, { link });
  return { type, routed, slides: undefined, out: outPath };
}

module.exports = { classifyHeuristic, buildClassifyPrompt, callAnthropic, route, buildExtractionPrompt, buildFromVideo, TYPES, EXTRACT_SCHEMA, RECIPE_TYPES };
