/* orchestrate.js — 파이프라인 4단계 '실행 하네스'.
 * 리소스(구간요약+스냅샷 레이블+수식 LaTeX+그래프 설명) → LLM(OpenRouter Sonnet) 추출
 * → buildRecipe → validate_deck.py → FAIL이면 검증결과를 LLM에 되먹여 PASS까지 반복.
 *
 * OpenRouter는 LLM 텍스트 API일 뿐이라, 빌드·검증·재시도는 이 코드(당신 인프라)가 담당한다.
 * 이 자가수정 루프가 'Sonnet 체급으로도 동급 품질'을 만드는 메커니즘이다.
 *
 *   const { orchestrate } = require("./orchestrate.js");
 *   const r = await orchestrate(resources, "out.pptx", { link, minSlides: 12 });
 *   // resources = { title, description?, transcript, segments?, figureLabels?, formulas?, charts? }
 */
const path = require("path");
const { execFileSync } = require("child_process");
const { route, buildExtractionPrompt } = require(path.join(__dirname, "router.js"));
const { buildRecipe } = require(path.join(__dirname, "deck_recipes.js"));

/* OpenRouter (Claude Sonnet) 호출 — messages[] → text. 키 없으면 llm 주입 필요. */
async function callOpenRouter(messages, { model = "anthropic/claude-sonnet-4", apiKey = process.env.OPENROUTER_API_KEY, max_tokens = 8000 } = {}) {
  if (!apiKey) throw new Error("OPENROUTER_API_KEY 없음 — llm 함수를 주입하거나 키를 설정하세요.");
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ model, max_tokens, messages }),
  });
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "";
}

function parseJSON(s) { return JSON.parse(String(s).replace(/```json|```/g, "").trim()); }

/* validate_deck.py 실행 → {pass, report} */
function validate(outPath, minSlides = 12) {
  try {
    const out = execFileSync("python3", [path.join(__dirname, "validate_deck.py"), outPath, "--min-slides", String(minSlides)], { encoding: "utf8" });
    return { pass: true, report: out };
  } catch (e) {
    return { pass: false, report: (e.stdout || "") + (e.stderr || "") };
  }
}

/* 리소스 번들 → 추출 프롬프트(스킬 밀도·메타 규칙 + 영상 분석 리소스). */
function buildResourcePrompt(type, r) {
  return [
    buildExtractionPrompt(type, { title: r.title, transcript: r.transcript }),
    "── 영상 분석 리소스(이미 추출됨) ──",
    "구간 요약: " + JSON.stringify(r.segments || []),
    "스냅샷 레이블(그래프/수식 종류·위치): " + JSON.stringify(r.figureLabels || []),
    "수식(LaTeX/기호): " + JSON.stringify(r.formulas || []),
    "그래프 설명/데이터 포인트: " + JSON.stringify(r.charts || []),
    "주의: 그래프/수식은 '재작도·재렌더' 대상이다. 원본 스크린샷을 붙이지 말고, 핵심 데이터·관계·수식만 콘텐츠 필드로 옮겨라(스킬이 네이티브 도형/고해상 그래프/텍스트 수식으로 렌더한다).",
  ].join("\n\n");
}

/* 메인: 분류 → 추출 → 빌드 → 검증 → 되먹임(자가수정) 루프. */
async function orchestrate(resources, outPath, opts = {}) {
  const { llm = (m) => callOpenRouter(m, opts.openrouter || {}), classify, minSlides = 12, maxAttempts = 3, link } = opts;
  const routed = classify
    ? await classify(resources)
    : await route({ title: resources.title, description: resources.description, transcript: resources.transcript }, { mode: "hybrid", llm: (p) => llm([{ role: "user", content: p }]) });
  const type = routed.type;

  const messages = [{ role: "user", content: buildResourcePrompt(type, resources) }];
  let lastReport = "";
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const raw = await llm(messages);
    let content;
    try { content = parseJSON(raw); }
    catch (e) {
      messages.push({ role: "assistant", content: raw }, { role: "user", content: "JSON 파싱 실패. 설명 없이 스키마에 맞는 순수 JSON만 다시 출력하라." });
      continue;
    }
    await buildRecipe(type, content, outPath, { link, silent: true });
    const v = validate(outPath, minSlides);
    if (v.pass) return { ok: true, type, attempts: attempt, out: outPath, routedFrom: routed.source };
    lastReport = v.report;
    messages.push(
      { role: "assistant", content: raw },
      { role: "user", content: "아래 검증 결과의 FAIL 항목을 고쳐 콘텐츠 JSON을 다시 출력하라. 간지(빈 섹션 구분) 추가는 금지 — 리서치로 실질 단위(단계/항목/논점/섹션)를 보강해 분량을 채운다. 설명 없이 순수 JSON만.\n\n" + v.report },
    );
  }
  return { ok: false, type, attempts: maxAttempts, out: outPath, report: lastReport };
}

module.exports = { orchestrate, callOpenRouter, validate, buildResourcePrompt };
