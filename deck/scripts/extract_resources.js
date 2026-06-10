/* extract_resources.js — 스테이지 1~3을 묶어 orchestrate.js가 먹는 리소스 번들을 만든다.
 * EC2(BE)에서 실행, RunPod GPU 서비스(Qwen3-VL vLLM + Pix2Text)를 HTTP로 호출.
 * 대용량 이미지는 S3 presigned URL로 전달(payload 경량화).
 *
 *   const { extractResources } = require("./extract_resources.js");
 *   const resources = await extractResources(
 *     { title, transcript, frames: [{ idx, ts, url }] },   // url = S3 presigned
 *     { qwen: {endpoint, apiKey}, pix2text: {endpoint, apiKey} }
 *   );
 *   // → { title, transcript, segments, figureLabels, formulas, charts } → orchestrate(resources, out)
 *
 * 도구 선택(압축 스택): 차트→데이터는 Qwen3-VL이 직접(전용 차트모델 불필요),
 *   수식/표는 Pix2Text(정밀). 분류·구간요약도 Qwen3-VL.
 */

/* Qwen3-VL (vLLM, OpenAI 호환) 호출 — 이미지 URL + 텍스트 → 응답 텍스트 */
async function callQwenVL(parts, { endpoint, apiKey, model = "Qwen/Qwen3-VL-8B-Instruct", max_tokens = 1500 } = {}) {
  if (!endpoint) throw new Error("Qwen vLLM endpoint 필요(RunPod)");
  const content = parts.map((p) => (p.image ? { type: "image_url", image_url: { url: p.image } } : { type: "text", text: p.text }));
  const res = await fetch(endpoint.replace(/\/$/, "") + "/v1/chat/completions", {
    method: "POST",
    headers: { "content-type": "application/json", ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) },
    body: JSON.stringify({ model, max_tokens, messages: [{ role: "user", content }] }),
  });
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "";
}

/* Pix2Text (FastAPI 핸들러) 호출 — 이미지 URL → {formulas:[{latex,bbox}], tables, text} */
async function callPix2Text(imageUrl, { endpoint, apiKey } = {}) {
  if (!endpoint) throw new Error("Pix2Text endpoint 필요(RunPod)");
  const res = await fetch(endpoint.replace(/\/$/, "") + "/parse", {
    method: "POST",
    headers: { "content-type": "application/json", ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) },
    body: JSON.stringify({ image_url: imageUrl }),
  });
  return res.json(); // { formulas:[{latex,bbox}], tables:[{headers,rows}], text }
}

function parseJSON(s) { try { return JSON.parse(String(s).replace(/```json|```/g, "").trim()); } catch { return null; } }

const CLASSIFY_FRAME = '이 슬라이드 프레임의 주요 시각요소를 분류하라. 설명 없이 JSON만: {"kind":"chart|formula|table|diagram|text|photo","note":"한 줄 설명"}';
const CHART_TO_DATA = '이 차트를 재작도할 수 있도록 핵심만 추출하라. 정확한 픽셀값이 아니라 통찰과 대략 수치면 된다. 설명 없이 JSON만: {"kind":"line|bar|scatter|pie","axes":{"x":"","y":""},"insight":"한 문장","points":[{"label":"","value":0}]}';

/* 메인: 프레임 분류 → (차트/수식/표) 분기 추출 → 구간 요약 → 번들 조립.
 * 테스트/주입용으로 qwenCall·pixCall·summarize 를 opts로 교체 가능. */
async function extractResources(input, opts = {}) {
  const { title, transcript, frames = [], segments: givenSegments } = input;
  const qwenCall = opts.qwenCall || ((parts) => callQwenVL(parts, opts.qwen));
  const pixCall = opts.pixCall || ((url) => callPix2Text(url, opts.pix2text));

  const figureLabels = [], formulas = [], charts = [];
  for (const f of frames) {
    const cls = parseJSON(await qwenCall([{ image: f.url }, { text: CLASSIFY_FRAME }])) || { kind: "text" };
    figureLabels.push({ snapshot: f.idx, ts: f.ts, kind: cls.kind, note: cls.note });
    if (cls.kind === "chart") {
      const c = parseJSON(await qwenCall([{ image: f.url }, { text: CHART_TO_DATA }]));
      if (c) charts.push({ snapshot: f.idx, ...c });
    } else if (cls.kind === "formula" || cls.kind === "table") {
      const p = await pixCall(f.url).catch(() => null);
      if (p) {
        (p.formulas || []).forEach((m) => formulas.push({ snapshot: f.idx, latex: m.latex, note: cls.note }));
        (p.tables || []).forEach((t) => charts.push({ snapshot: f.idx, kind: "table", headers: t.headers, rows: t.rows }));
      }
    }
  }

  // 구간 요약: 전사 토픽 세분화(Qwen 또는 주입). 미제공 시 Qwen에 위임.
  let segments = givenSegments;
  if (!segments) {
    const raw = await qwenCall([{ text: `다음 자막을 의미 단위로 5~8구간으로 나눠 각 구간 요약을 JSON 배열로만 출력하라. 형식:[{"t":"mm:ss-mm:ss","summary":""}]\n\n${String(transcript).slice(0, 12000)}` }]);
    segments = parseJSON(raw) || [];
  }

  return { title, transcript, segments, figureLabels, formulas, charts };
}

module.exports = { extractResources, callQwenVL, callPix2Text };
