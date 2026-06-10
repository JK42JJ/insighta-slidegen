/* extract_resources_example.js — 스테이지 1~3 → 리소스 번들 → orchestrate.
 * RunPod 엔드포인트(Qwen3-VL vLLM, Pix2Text)는 실제 값으로 교체. */
const path = require("path");
const { extractResources } = require(path.join(__dirname, "..", "scripts", "extract_resources.js"));
const { orchestrate, callOpenRouter } = require(path.join(__dirname, "..", "scripts", "orchestrate.js"));

(async () => {
  // ① PySceneDetect/ffmpeg+pHash로 뽑은 프레임을 S3에 올리고 presigned URL 확보(EC2)
  const frames = [ { idx: 1, ts: "00:30", url: "https://s3..../f1.png" } /* ... */ ];

  // ②③ RunPod 호출 → 리소스 번들 (차트=Qwen-VL, 수식/표=Pix2Text)
  const resources = await extractResources(
    { title: "강의 제목", transcript: "...자막...", frames },
    { qwen: { endpoint: process.env.QWEN_VLLM_URL, apiKey: process.env.RUNPOD_KEY },
      pix2text: { endpoint: process.env.PIX2TEXT_URL, apiKey: process.env.RUNPOD_KEY } }
  );

  // ④ OpenRouter(Sonnet) 추출 → buildRecipe → validate → 되먹임 루프
  const llm = (messages) => callOpenRouter(messages, { model: "anthropic/claude-sonnet-4" });
  const r = await orchestrate(resources, "out.pptx", { llm, minSlides: 12, maxAttempts: 3 });
  console.log(r);
})();
