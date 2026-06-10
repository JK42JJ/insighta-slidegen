/* orchestrate_example.js — 파이프라인 4단계 하네스 사용 예시.
 * 영상 분석 리소스(구간요약+스냅샷 레이블+수식 LaTeX+그래프 설명) → 덱 자동 생성.
 * 실제로는 llm에 OpenRouter(Sonnet) 호출을 주입한다. */
const path = require("path");
const { orchestrate, callOpenRouter } = require(path.join(__dirname, "..", "scripts", "orchestrate.js"));

// 1~3단계(Katna 스냅샷 → Qwen3-VL 분류·레이블 → 수식/그래프 텍스트화) 결과를 이 형태로 모은다:
const resources = {
  title: "What is machine learning? explained",
  description: "introduction to basics",
  transcript: "...(자막 전문)...",
  segments: [ { t: "00:00-02:10", summary: "지도학습 개요..." } /* ...구간별 요약 */ ],
  figureLabels: [ { snapshot: 5, kind: "graph", bbox: [x, y, w, h], note: "회귀 적합선" } ],
  formulas: [ { latex: "\\theta \\leftarrow \\theta - \\eta \\nabla J(\\theta)", note: "경사하강 갱신식" } ],
  charts: [ { kind: "line", insight: "검증오차 U자", points: "대략 epoch↑ → train↓, val↓후↑" } ],
};

(async () => {
  // 프로덕션: OpenRouter Sonnet 주입
  const llm = (messages) => callOpenRouter(messages, { model: "anthropic/claude-sonnet-4" }); // OPENROUTER_API_KEY 필요
  const r = await orchestrate(resources, "out.pptx", { llm, minSlides: 12, maxAttempts: 3, link: "https://insighta.one" });
  console.log(r); // { ok, type, attempts, out } — PASS까지 자가수정 반복
})();
