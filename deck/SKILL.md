---
name: insighta-visual-deck
description: >-
  Build Insighta-branded EDUCATIONAL concept decks (.pptx) by filling CONTENT into
  pre-built, tested slide templates — the model never computes coordinates. Decks
  teach a subject's essence: a source gives the skeleton, web research fills detail,
  high-resolution concept graphs (matplotlib) carry information, native objects
  (charts/tables/shapes) and Unicode-text equations stay editable, a synthesis
  slide ties it together, a curiosity slide provokes questions, and a Markdown
  appendix holds overflow detail. Includes an automated validator. Use whenever the
  user wants Insighta slides, a deck, "슬라이드덱/발표자료/PPT", or to turn a summary/
  topic into a branded, reusable, editable teaching deck. Designed so weaker models
  (e.g. Sonnet via API/OpenRouter) reproduce the same quality. Pretendard + JetBrains Mono.
license: >-
  Vendored from the insighta-visual-deck skill. Brand tokens are product design
  constants, not secrets. Fonts: Pretendard / JetBrains Mono, SIL OFL 1.1 (see
  assets/fonts/).
---

# Insighta Visual Deck

**핵심 원리: 판단을 코드로 내려, 모델은 ‘내용’만 채운다.** 좌표·비율·화살표·QA를 모델이
즉흥 계산하면 모델 체급에 따라 품질이 갈린다. 그래서 검증된 레이아웃을 `deck_templates.js`로
캡슐화했다. **절대 좌표를 직접 쓰지 말고 템플릿 메서드에 콘텐츠 객체만 전달**한다.

## 가장 빠른 길 (이것만 지키면 된다)
1. `references/deck_example.js`를 복사한다(콘텐츠만 들어간 15장 실예시).
2. 텍스트·데이터만 본인 주제로 바꾼다. 좌표·`addText`·`addShape`를 새로 쓰지 않는다.
3. 필요한 교육 그래프를 `figures.py`로 생성한다.
4. 빌드 → **`validate_deck.py`로 자동 검증** → 통과할 때까지 콘텐츠/그래프만 수정.


## 서비스 진입점 (임의 영상 1줄)
```js
const { buildFromVideo } = require("./scripts/router.js");
await buildFromVideo({ title, description, transcript }, "out.pptx",
  { extract: async (type, input) => JSON.parse(await llm(buildExtractionPrompt(type, input))), llm, link });
```
분류는 자동(휴리스틱+LLM). `extract`는 자막→유형 스키마 JSON 변환(LLM) — `buildExtractionPrompt`가 프롬프트를 제공.

## 아키텍처 (3 레이어) — 임의 영상 → 유형별 덱
서비스는 어떤 정보형 영상이 와도 그 **유형에 맞는 덱**을 생성해야 한다. 이를 위해 3단으로 분리한다.
- **Layer 1 · 범용 장표 원자** `scripts/slide_templates.js` → `makeSlides(D,{total,link})`.
  도메인 무관 낱장 14종(+title, +conceptDeep): `sectionDivider · agenda · keyPoints · twoColumn · comparisonTable ·
  processSteps · listRanked · timeline · kpis · quote · qna · closingCTA`. 콘텐츠만 받고 좌표는 내부 처리.
- **Layer 2 · 덱 레시피(유형별 조합)** `scripts/deck_recipes.js` → `buildRecipe(type, content, out, {link})`.
  7종: `howto · review · interview · news · listicle · story · talk` (강의=explainer는 `references/deck_example.js`의
  학습 덱 레시피). 콘텐츠 객체만 주면 유형에 맞는 장표 순서로 자동 조합·저장. 스키마는 `references/recipe_example.js` 참조.
  **밀도 규칙**: keyPoints.points 는 `{h,t}`로 2문장 분량, 한 줄 나열(agenda/listRanked)은 보조로만,
  수치는 kpis·비교는 comparisonTable/twoColumn으로 *해석과 함께*. 각 레시피는 최소 1개 설명형(표/비교/지표/단계) 포함.
  유형↔구성:  ①강의→개념학습 ②하우투→processSteps ③리뷰→comparison/twoColumn
  ④인터뷰→qna/quote ⑤뉴스→keyPoints/twoColumn ⑥리스티클→listRanked ⑦사례→timeline ⑧발표→keyPoints/kpis/closingCTA.
- **Layer 3 · 라우터** `scripts/router.js`. 하이브리드 분류(휴리스틱→불확실 시 LLM 확정) + 내용추출 계약 + 오케스트레이터.
  - **explainer 표준 = 그래프형 15장**(`references/deck_example.js`, makeTemplates): 표지→큰그림(루프+호기심훅)→개념지도→분류트리→교육그래프(회귀/활성화·경사하강/과적합/ROC/군집)+직관→신경망진화→수식→평가→모델계열→데이터·수학→본질→호기심. **간지(섹션 구분) 슬라이드 금지** — 모든 장이 실질 내용. 교육 그래프는 `figures.py`로 주제에 맞게 생성.
  - **레시피 7종(howto·review·interview·news·listicle·story·talk)도 12~20장**: 각 단계/항목/주제/쟁점/국면/논점을 `conceptDeep` '심화 단위 루프'로 한 장씩 깊게 다뤄 분량을 실질 내용으로 채운다(간지 금지). 스키마는 `references/recipe_example.js`.
  - (폴백) 그래프를 만들 수 없을 때만 `buildRecipe("explainer",{sections})` — `conceptDeep`(정의+작동방식+핵심+직관) 한 장씩, 역시 간지 없이.
  - `classifyHeuristic(input)` 결정적 분류(키워드·구조, conf 반환). `route(input,{mode,llm})` 하이브리드.
  - `buildExtractionPrompt(type,input)` 자막→유형 스키마 JSON 변환 프롬프트(밀도·메타금지 규칙 내장).
  - `buildFromVideo(input,out,{classify,extract,llm,link})` 분류→추출(LLM 주입)→`buildRecipe` 까지 자동.
  - LLM은 주입식 → Claude API(`callAnthropic`)·OpenRouter 어디든 연결. 키 없으면 휴리스틱만으로도 동작.

Layer 1 사용 예(낱장 조합만으로 덱 구성):
```js
const { createDeck } = require("./scripts/insighta_deck.js");
const { makeSlides } = require("./scripts/slide_templates.js");
const D = createDeck({ title: "..." });
const S = makeSlides(D, { total: 10, link: "https://insighta.one" });
S.sectionDivider({...}); S.keyPoints({...}); S.comparisonTable({...}); S.closingCTA({...});
S.save("out.pptx");
```
콘텐츠 스키마는 `references/slides_example.js`(12원자 1장씩)에 1:1로 있다.



## 파이프라인 통합 — 영상 → 덱 4단계 하네스 (orchestrate.js)
외부 영상 파이프라인을 이 스킬에 연결하는 진입점. **OpenRouter(Sonnet)는 LLM 텍스트 API일 뿐**이므로,
빌드·검증·재시도는 이 코드(`scripts/orchestrate.js`)가 담당한다 — 이 자가수정 루프가 체급 격차를 닫는다.
```
[1] Katna 등: 스냅샷 추출(+타임스탬프)        ← 로컬, 결정적
[2] Qwen3-VL-8B: 스냅샷 분류·레이블(그래프/수식), 구간 요약   ← 로컬 VLM (분류·설명 전담)
    · 그래프/수식 bbox: Document-YOLO + 수식 OCR(Mathpix/LaTeX-OCR)를 '코드가' 결정적으로 실행
      (8B 모델에 에이전트 툴콜을 맡기지 말 것 — 신뢰성 최약점)
[3] 리소스 번들 = {title, transcript, segments, figureLabels, formulas, charts}
[4] orchestrate(resources, out): route(분류) → Sonnet 추출(JSON) → buildRecipe → validate_deck
      → FAIL이면 검증 결과를 Sonnet에 되먹여 PASS까지 반복(maxAttempts)         ← 당신 인프라
```
압축 스택(권장): 스냅샷=PySceneDetect 또는 ffmpeg+pHash(슬라이드 전환), 차트→데이터=Qwen3-VL 직접(전용 차트모델 불필요 — VLM이 DePlot/UniChart 능가), 수식/표/레이아웃=Pix2Text(Mathpix 대안). 스테이지 1~3은 `scripts/extract_resources.js`가 RunPod(Qwen-VL vLLM + Pix2Text) 호출로 리소스 번들 조립 → orchestrate에 전달. CV 특화학습은 베이스+프롬프트로 시작하고, 필요 시 소형 레이아웃 YOLO 파인튜닝 우선(8B VLM LoRA는 측정된 갭이 쌓인 뒤).

원칙: **스냅샷=데이터 소스, 최종=재생성**(원본 프레임 금지 → 네이티브 도형/고해상 그래프/텍스트 수식).
구간/장수는 15 고정이 아니라 **콘텐츠가 정하는 12~20장**(레시피가 처리). 예시: `references/orchestrate_example.js`.

## 모델 체급과 무관하게 동급 품질 — 자가수정 루프 (가장 중요)
이 스킬의 목적은 *눈으로* 판정하던 품질을 **코드가 판정**하게 만들어, 약한 모델(Sonnet 등)도
같은 결과에 수렴시키는 것이다. 따라서 덱 생성은 **반드시 다음 루프**를 돈다:
```
빌드 → python scripts/validate_deck.py out.pptx → FAIL 항목 수정 → PASS까지 반복
```
`validate_deck.py`(v2)가 *사람 눈 대신* 잡는 결함(전부 FAIL):
- **간지/저밀도**: 글자도 적고 이미지·표·도형(≥7)도 없는 빈 전환 장표 → 분량 채우기 꼼수 차단.
- **세로 빈 공간**: 콘텐츠가 위만 차고 아래가 빔(시각요소 없는 경우).
- **메타 표현**: 본문의 '영상/출처/별첨/VIDEO DIGEST/채널/타임스탬프(mm:ss)' → 독립 주제 자료 위배.
- **오버플로**: 텍스트 도형이 슬라이드 밖.
- **분량**: 기본 최소 12장(`--min-slides`).
참고(정보성): 장표별 본문 글자수 범위(균일할수록 좋음), 네이티브 표/차트·이미지 수.

**동급 품질이 가능한가?** — 위 다섯 결함은 이번 작업에서 *내가 눈으로 잡아 고친* 바로 그 실패들이고,
이제 전부 기계가 잡는다. 모델은 보지 않고도 PASS까지 고치면 되므로 **구조·밀도·간지·메타·분량·오버플로**
품질은 체급과 무관하게 수렴한다. 다만 검증기가 아직 못 보는 영역(색 조화·카피 문장력 같은 미세 취향)에는
잔여 격차가 남는다 — 그 부분은 brand.md 토큰·예시 고정으로 최소화한다.

## 절대 규칙 (이번 프로젝트에서 확인된 실패를 규칙화)
- **분량 표준(상용): 12~20장**(최소 12~15, 최대 20). 부족하면 억지 분할이 아니라 **리서치로 각 장표 내용을 채워** 자연스럽게 늘린다. `validate_deck.py --min-slides 12` 로 강제.
- **간지(섹션 구분만 있는 슬라이드) 금지**: 분량 채우기용 빈 전환 장표는 상용 품질이 아니다. 모든 장이 실질 내용(개념·그래프·표·비교·지표)을 담아야 한다.
- **세로 채움/정렬**: 모든 콘텐츠 장표는 본문 영역을 균일하게 채운다. 항목이 적으면 카드 높이를 키우지 말고 **블록을 세로 중앙정렬**, 표/지표는 행 높이로 영역을 채운다(상한 내).
- **DO 주제 자체만 설명**(독립 자료). DON'T 제작/출처 언급 — "영상에서·출처 영상·이 덱은·동반 별첨·VIDEO DIGEST·채널명" 같은 메타 표현, 그리고 영상 위치를 가리키는 타임스탬프(3:07 등)를 슬라이드 본문에 넣지 말 것(상세 위치는 별첨에만).
- **DO 템플릿만 사용**. DON'T 좌표 직접 계산(오버플로·비율 깨짐의 원인).
- **DO 주제에 충실**. DON'T 도구·파이프라인 등 메타 내용 삽입(예: ‘개념 수’ 같은 분류 통계 차트 = 정보 0, 금지).
- **DO 개념을 가르친다** = 그래프(정보) + 직관 + ‘왜 중요’. DON'T 한 줄 정의 나열(정보밀도가 안 오름).
- **DO 데이터 그래프는 고해상 PNG**(matplotlib, `figures.py`). DON'T 네이티브 차트로 정보형 그래프 대체(해상도·표현력 저하).
- **DO 구조는 네이티브**(표·트리·플로우·매트릭스). **수식은 유니코드 텍스트**(복사 가능). DON'T 수식을 이미지로.
- **DO 본질 통합 슬라이드 + 호기심 슬라이드 + insighta.one 링크 + 별첨**. 
- **DO 다크 샌드위치**(표지·본질·호기심 다크, 본문 라이트), 제목 밑줄/전면 컬러바 금지.
- **DO 마지막에 validate_deck.py PASS 확인**. 오버플로 0.

## 워크플로우
### STEP 0 — 주제·뼈대
무엇을 가르칠지 확정, 소스(요약/트랜스크립트)에서 개념·구조를 뽑는다.
### STEP 1 — 리서치/팩트체크
`web_search`로 핵심 정의·연도·출처를 검증·보강(소스 오류 정정). 출처는 별첨에 기록.
### STEP 2 — 셋업
```bash
mkdir -p ~/.fonts && cp assets/fonts/*.ttf ~/.fonts/ && fc-cache -f ~/.fonts >/dev/null
pip install graphviz matplotlib pillow --break-system-packages
npm install pptxgenjs
```
### STEP 3 — 교육 그래프 생성 (figures.py 카탈로그)
```bash
python -c "import sys; sys.path.insert(0,'scripts'); import figures; figures.generate_teaching('figs')"
```
제공 함수: `teach_regression`(회귀 적합), `teach_activation`(σ/tanh/ReLU), `teach_gradient`(경사하강),
`teach_overfit`(훈련vs검증), `teach_roc`(ROC/AUC), `teach_kmeans`(군집). 새 개념은 같은 패턴(투명 배경,
브랜드색, `_ax()` 헬퍼)으로 추가. **각 PNG를 view로 점검**(흰 배경 flatten).
### STEP 4 — 덱 작성 (템플릿)
```js
const { createDeck } = require("./scripts/insighta_deck.js");
const { makeTemplates } = require("./scripts/deck_templates.js");
const D = createDeck({ title: "..." });
const T = makeTemplates(D, { total: 15, figDir: "figs", link: "https://insighta.one" });
T.title({...}); T.roadmapLoop({...}); T.conceptMap({...}); T.taxonomy({...});
T.teach({...}); T.evolution({...}); T.dualTeach({...}); T.equations({...});
T.evaluation({...}); T.breadthGrid({...}); T.essenceLoop({...}); T.curiosity({...});
T.save("out.pptx");
```
페이지 번호·푸터·레이아웃은 템플릿이 자동 처리. 콘텐츠 스키마는 `references/deck_example.js` 참조.
### STEP 5 — 별첨
슬라이드에 안 담기는 정의·수식·출처·정정을 Markdown으로(`references/appendix_example.md` 구조).
### STEP 6 — 렌더 & 자동 검증 (생략 금지)
```bash
bash scripts/render.sh out.pptx /tmp/render          # PNG 미리보기
python scripts/validate_deck.py out.pptx --min-slides 12
```
검증 항목: 오버플로 0 · 수식 텍스트 · 하이퍼링크 · 임베딩 수 · 슬라이드 수. **PASS까지 콘텐츠만 수정.**
미리보기 PNG도 view로 한 번 훑는다(대비·잘림).
### STEP 7 — 전달
PPTX + 별첨.md를 `/mnt/user-data/outputs/`로, `present_files`.

## 템플릿 목록 (deck_templates.js)
`title` · `roadmapLoop`(루프+호기심훅) · `conceptMap`(6카테고리) · `taxonomy`(네이티브 트리) ·
`teach`(그래프+직관+‘직관’콜아웃) · `dualTeach`(그래프2) · `evolution`(플로우+연표+카드) ·
`equations`(텍스트 수식) · `evaluation`(ROC+혼동행렬) · `breadthGrid`(카드 그리드) ·
`essenceLoop`(본질 루프, 다크) · `curiosity`(Q&A+링크, 다크). 각 메서드 인자는 예시 파일에 1:1로 있음.

## 번들 리소스
```
insighta-visual-deck/
├── SKILL.md
├── scripts/
│   ├── insighta_deck.js     저수준 컴포넌트(차트·표·도형·수식·커넥터)
│   ├── slide_templates.js   ★ Layer1 범용 장표 원자 12종(도메인 무관)
│   ├── router.js            ★ Layer3 분류·추출계약·오케스트레이터(buildFromVideo)
│   ├── deck_recipes.js      Layer2 레시피 8종(유형→장표 조합) + buildRecipe()
│   ├── deck_templates.js    Layer2 학습 덱(explainer) 템플릿 — 교육 그래프 조합
│   ├── figures.py           교육 그래프 카탈로그(matplotlib) + (선택)Graphviz
│   ├── validate_deck.py     ★ 자동 검증(오버플로·수식텍스트·링크 등)
│   └── render.sh            pptx→png
├── references/
│   ├── brand.md             토큰 + 컴포넌트/템플릿 API + do/don't
│   ├── deck_example.js      Layer2 예시(학습 개념 덱 15장)
│   ├── slides_example.js    Layer1 예시(범용 원자 12종 1장씩)
│   ├── recipe_example.js    Layer2 예시(howto·review 콘텐츠 스키마)
│   ├── router_example.js    ★ Layer3 예시(분류 + buildFromVideo 배선)
│   └── appendix_example.md  별첨 핸드아웃 예시
└── assets/fonts/            Pretendard(4) + JetBrains Mono(2)
```
