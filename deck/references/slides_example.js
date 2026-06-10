/* build_atoms_demo.js — 12개 범용 장표 원자를 각 1장씩 생성(렌더/검증용). */
const path = require("path");
const SK = path.join(__dirname, "..");
const { createDeck } = require(path.join(SK, "scripts", "insighta_deck.js"));
const { makeSlides } = require(path.join(SK, "scripts", "slide_templates.js"));

const D = createDeck({ title: "범용 장표 원자 데모" });
const S = makeSlides(D, { total: 12, link: "https://insighta.one" });

S.sectionDivider({ no: "01", kicker: "SECTION", title: "범용 장표 원자 12종", subtitle: "도메인 무관 · 어떤 주제든 조합 가능" });

S.agenda({ title: "목차", items: [
  { label: "배경과 문제", desc: "왜 이 주제가 중요한가" },
  { label: "핵심 개념", desc: "꼭 알아야 할 3가지" },
  { label: "비교와 선택", desc: "대안별 장단점" },
  { label: "단계별 적용", desc: "실행 프로세스" },
  { label: "결론과 다음 단계", desc: "요약·행동" },
]});

S.keyPoints({ title: "핵심 메시지", lead: "영상에서 반드시 챙겨야 할 포인트.", cat: "blue", points: [
  { h: "문제 정의가 절반이다", t: "무엇을 풀지 명확히 하면 해법은 따라온다." },
  { h: "데이터가 결정한다", t: "직관보다 측정 가능한 신호에 의존하라." },
  { h: "작게 시작해 반복", t: "완성형이 아니라 빠른 피드백 루프를 노린다." },
  { h: "일반화가 목표", t: "훈련 성능이 아니라 새 상황 성능이 중요하다." },
]});

S.twoColumn({ title: "장점 vs 한계", cat: "emerald",
  left: { h: "장점", cat: "emerald", items: ["빠른 적용과 낮은 비용", "해석이 쉬워 설득력", "적은 데이터로도 동작", "유지보수 용이"] },
  right: { h: "한계", cat: "rose", items: ["복잡한 패턴엔 약함", "특징 설계에 의존", "확장성 제약", "노이즈에 민감"] },
});

S.comparisonTable({ title: "대안 비교", intro: "세 가지 접근을 기준별로 정리.", cat: "slate",
  headers: ["기준", "방식 A", "방식 B", "방식 C"],
  rows: [
    ["비용", "낮음", "중간", "높음"],
    ["정확도", "보통", "높음", "매우 높음"],
    ["속도", "빠름", "보통", "느림"],
    ["적합 상황", "프로토타입", "운영 서비스", "대규모"],
  ]});

S.processSteps({ title: "적용 프로세스", cat: "blue", note: "각 단계는 이전 단계의 출력을 입력으로 받는다.",
  steps: [
    { title: "수집", sub: "원천 데이터 확보" },
    { title: "정제", sub: "결측·이상치 처리" },
    { title: "학습", sub: "모델 적합" },
    { title: "평가", sub: "교차검증" },
    { title: "배포", sub: "모니터링" },
  ]});

S.listRanked({ title: "꼭 봐야 할 5가지", cat: "amber", items: [
  { title: "기초 개념 정리", desc: "용어와 직관부터" },
  { title: "대표 사례 분석", desc: "성공·실패 패턴" },
  { title: "도구 활용법", desc: "실무 워크플로우" },
  { title: "흔한 함정", desc: "피해야 할 실수" },
  { title: "다음 학습 경로", desc: "심화 자료" },
]});

S.timeline({ title: "발전 연표", cat: "violet", milestones: [
  { date: "1958", title: "퍼셉트론", desc: "선형 분류기 제안" },
  { date: "1986", title: "역전파", desc: "다층 학습 대중화" },
  { date: "2012", title: "AlexNet", desc: "딥러닝 전환점" },
  { date: "2017", title: "Transformer", desc: "어텐션 기반" },
  { date: "2022", title: "LLM 확산", desc: "생성형 대중화" },
]});

S.kpis({ title: "핵심 지표", cat: "blue", note: "한 화면에서 규모를 직관적으로 전달.", stats: [
  { value: "2.8B", label: "월간 활성 사용자" },
  { value: "15.3", unit: "%", label: "top-5 오류 (AlexNet)" },
  { value: "228", unit: "x", label: "실시간 대비 처리 속도" },
  { value: "0.04", unit: "$/h", label: "ASR 단가" },
]});

S.quote({ cat: "violet", text: "복잡한 세계를 이해하는 가장 좋은 방법은, 그것을 하나의 단순한 루프로 환원해 보는 것이다.",
  author: "발표자", role: "주제 전문가" });

S.qna({ title: "자주 묻는 질문", cat: "emerald", pairs: [
  { q: "초보자도 따라할 수 있나요?", a: "네 — 기초 개념부터 단계적으로 구성되어 있습니다." },
  { q: "어떤 도구가 필요한가요?", a: "무료 오픈소스만으로 전 과정을 재현할 수 있습니다." },
  { q: "데이터가 적으면?", a: "전이학습·증강·정규화로 과적합을 완화합니다." },
  { q: "다음엔 무엇을?", a: "심화 자료와 실습 과제를 별첨에서 안내합니다." },
]});

S.closingCTA({ title: "정리 — 다음 단계", subtitle: "오늘 다룬 내용을 행동으로.",
  points: ["핵심 개념 3가지를 직접 예제로 재현해 보기", "비교 표 기준으로 내 상황에 맞는 방식 선택", "단계별 프로세스를 작은 프로젝트에 적용"],
  contact: "문의: hello@insighta.one" });

S.save("atoms_demo.pptx").then((f) => console.log("WROTE", f, "| slides:", S.page));
