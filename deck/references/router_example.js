/* router_example.js — Layer3 사용 예시.
 * (1) 휴리스틱 분류만으로 유형 판별  (2) buildFromVideo로 영상→덱 전 과정 배선.
 * 실제 서비스에선 llm/extract에 Claude API(또는 OpenRouter) 호출을 주입한다. */
const path = require("path");
const { classifyHeuristic, buildExtractionPrompt, buildFromVideo, callAnthropic } = require(path.join(__dirname, "..", "scripts", "router.js"));

// (1) 분류
const video = { title: "How to Deploy a Node App with Docker — Step by Step", description: "tutorial guide", transcript: "..." };
console.log(classifyHeuristic(video)); // → { type: "howto", confidence, ... }

// (2) 프로덕션 배선 예시 (의사코드)
//   const llm = (prompt) => callAnthropic(prompt, { model: "claude-haiku-4-5" }); // 또는 OpenRouter fetch
//   const extract = async (type, input) => JSON.parse((await llm(buildExtractionPrompt(type, input))).replace(/```json|```/g, "").trim());
//   await buildFromVideo(video, "out.pptx", { extract, llm, link: "https://insighta.one" });

// (테스트용) extract 스텁으로 배선만 확인하려면:
//   await buildFromVideo(video, "out.pptx", { mode: "heuristic", extract: async () => ({ title: "...", steps: [{title:"A",sub:"a"}] }) });
