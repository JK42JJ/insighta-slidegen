/* build_via_templates.js — 좌표/레이아웃 없이 '콘텐츠만'으로 15장 덱을 만든다.
 * 템플릿 모듈이 모든 배치를 처리 → 약한 모델도 동일 구조를 재현하도록. */
const path = require("path");
const SK = path.join(__dirname, "..");
const { createDeck } = require(path.join(SK, "scripts", "insighta_deck.js"));
const { makeTemplates } = require(path.join(SK, "scripts", "deck_templates.js"));

const D = createDeck({ title: "머신러닝 & AI 핵심 개념" });
const T = makeTemplates(D, { total: 15, figDir: path.join(SK, "figs"), link: "https://insighta.one" });

T.title({
  kicker: "AI · MACHINE LEARNING",
  title: "머신러닝 & AI 핵심 개념",
  subtitle: "용어를 외우는 게 아니라, 하나의 학습 루프로 ‘왜 그렇게 배우는가’를 이해한다",
  pills: [["개념", "90+"], ["수준", "입문 → 직관"], ["구성", "개념 지도 + 수식"]],
});

T.roadmapLoop({
  title: "기계가 ‘배운다’는 것은 무엇인가",
  intro: "머신러닝의 거의 모든 개념은 아래 한 바퀴를 도는 일에 속한다. 각 단계를 차례로 살펴본다.",
  stages: [{ title: "데이터", sub: "전처리·특징" }, { title: "모델", sub: "가설을 세움" }, { title: "손실", sub: "틀린 정도 측정" }, { title: "최적화", sub: "경사하강으로 개선" }, { title: "평가", sub: "일반화 확인" }],
  hooks: [
    { q: "왜 직선/곡선이 아니라 ‘학습’인가?", a: "규칙을 사람이 짜는 대신, 데이터에서 자동으로 찾는다." },
    { q: "무엇이 ‘좋은’ 모델인가?", a: "훈련이 아니라 처음 보는 데이터에서 잘 맞아야 한다(일반화)." },
    { q: "딥러닝은 왜 특별한가?", a: "특징을 사람이 만들지 않고 층층이 스스로 학습한다." },
  ],
});

T.conceptMap({
  title: "한눈에 보는 개념 지도",
  categories: [
    { cat: "blue", name: "학습 패러다임", count: 6, concepts: ["지도/비지도", "강화학습", "전이학습", "사전학습", "지식이전", "Human-in-the-loop"] },
    { cat: "emerald", name: "모델 계열", count: 6, concepts: ["선형·로지스틱 회귀", "의사결정 트리", "SVM", "랜덤포레스트·배깅", "나이브 베이즈", "앙상블"] },
    { cat: "violet", name: "신경망 구조", count: 7, concepts: ["ANN·퍼셉트론", "CNN", "RNN·LSTM", "Transformer", "GAN", "VAE"] },
    { cat: "amber", name: "구성요소·최적화", count: 6, concepts: ["활성화함수", "역전파·드롭아웃", "경사하강·SGD", "학습률", "손실·비용함수", "정규화"] },
    { cat: "rose", name: "평가·검증", count: 7, concepts: ["혼동행렬", "정밀도·재현율", "AUC-ROC", "MSE·RMSE·R²", "교차검증", "그리드서치"] },
    { cat: "slate", name: "데이터·거리·수학", count: 9, concepts: ["전처리·특징공학", "거리·유사도", "선형대수", "차원축소(PCA)", "클러스터링", "불균형·결측"] },
  ],
});

T.taxonomy({
  title: "세 가지 학습 방식", note: "모델을 ‘무엇으로 배우는가(레이블 유무·보상)’ 기준으로 분류",
  branches: [
    { name: "지도학습", cat: "blue", tag: "정답(레이블)을 보고 배운다", groups: [{ sub: "회귀", items: ["선형 회귀", "로지스틱 회귀"] }, { sub: "분류", items: ["SVM", "의사결정 트리", "랜덤 포레스트", "나이브 베이즈"] }] },
    { name: "비지도학습", cat: "emerald", tag: "정답 없이 구조를 찾는다", groups: [{ sub: "클러스터링", items: ["K-평균", "계층적"] }, { sub: "차원축소", items: ["PCA"] }] },
    { name: "강화학습", cat: "violet", tag: "시행착오의 보상으로 배운다", groups: [{ sub: "보상 기반", items: ["에이전트–환경 상호작용", "누적 보상 최대화"] }] },
  ],
});

T.teach({
  kicker: "모델 · 회귀", title: "가장 단순한 학습: 선 긋기", cat: "emerald", figure: "t_regression.png",
  lead: "회귀는 입력 x와 출력 y의 관계를 가장 잘 설명하는 함수를 찾는 일이다. 가장 단순한 형태가 직선 적합이다.",
  points: ["각 점과 직선의 세로 거리(잔차)를 잰다", "잔차 제곱의 합(MSE)이 최소가 되는 직선을 고른다", "로지스틱 회귀는 같은 아이디어를 ‘확률’에 적용한 것"],
  aha: "‘예측이 얼마나 틀렸나’를 숫자로 정의하면, 학습은 그 숫자를 줄이는 문제로 바뀐다.",
});

T.evolution({
  kicker: "신경망 구조", title: "신경망의 진화",
  stages: [{ title: "퍼셉트론", sub: "선형 분류기" }, { title: "ANN", sub: "다층·역전파" }, { title: "CNN", sub: "합성곱·이미지" }, { title: "RNN→LSTM", sub: "시퀀스·기억" }, { title: "Transformer", sub: "self-attention" }],
  timeline: "1958 퍼셉트론        1986 역전파 대중화        2012 AlexNet (딥러닝 전환점)        2017 Transformer",
  cards: [
    { cat: "violet", h: "CNN", t: "합성곱으로 국소 특징을 자동 추출. 2012 AlexNet이 ImageNet top-5 오류 26%→15%로 낮추며 딥러닝 부흥을 촉발했다." },
    { cat: "blue", h: "Transformer", t: "재귀 없이 self-attention으로 시퀀스를 병렬 처리. ‘Attention Is All You Need’(Vaswani 2017)가 오늘날 LLM의 토대." },
    { cat: "emerald", h: "GAN · VAE", t: "생성 모델. GAN(Goodfellow 2014)은 생성자–판별자 경쟁, VAE는 변분 추론으로 잠재공간을 학습." },
  ],
});

T.dualTeach({
  kicker: "구성요소 · 최적화", title: "뉴런은 어떻게 배우나", cat: "amber",
  figures: ["t_activation.png", "t_gradient.png"],
  notes: [
    { h: "활성화 함수", t: "각 뉴런은 가중합을 비선형 함수에 통과시킨다. 비선형성이 없으면 층을 쌓아도 직선 하나와 같다 — 깊은 표현의 핵심." },
    { h: "경사 하강 + 역전파", t: "손실의 기울기를 역전파로 구해, 기울기 반대 방향으로 가중치를 조금씩 옮긴다. 학습률이 그 보폭." },
  ],
});

T.teach({
  kicker: "구성요소 · 최적화", title: "과적합: 외우기 vs 이해하기", cat: "rose", figure: "t_overfit.png",
  lead: "훈련 데이터에 너무 맞추면 새 데이터에서 오히려 틀린다. 검증 오차가 다시 오르는 순간이 ‘외우기 시작’ 신호다.",
  points: ["훈련 오차는 계속 줄지만 검증 오차는 U자", "최저점에서 멈추기 = 조기 종료(early stopping)", "드롭아웃·L1/L2 정규화로 과적합을 억제"],
  aha: "좋은 모델의 기준은 훈련 점수가 아니라 ‘처음 보는 데이터’ 성능 = 일반화다.",
});

T.equations({
  items: [
    { name: "경사 하강법", desc: "손실 기울기 반대로 갱신 (η=학습률)", cat: "blue", expr: "θ ← θ − η · ∇J(θ)" },
    { name: "평균제곱오차 (MSE)", desc: "회귀 손실 = 잔차 제곱 평균", cat: "emerald", expr: "MSE = (1/n) · Σ (yᵢ − ŷᵢ)²" },
    { name: "시그모이드", desc: "실수를 0–1 확률로 압축", cat: "violet", expr: "σ(x) = 1 / (1 + exp(−x))" },
    { name: "소프트맥스", desc: "점수 벡터를 확률 분포로", cat: "amber", expr: "softmax(zᵢ) = exp(zᵢ) / Σⱼ exp(zⱼ)" },
    { name: "베이즈 정리", desc: "사전확률을 관측으로 갱신", cat: "rose", expr: "P(A|B) = P(B|A) · P(A) / P(B)" },
  ],
});

T.evaluation({
  title: "얼마나 믿을 수 있나", figure: "t_roc.png",
  intro: "정확도 하나로는 부족하다. 불균형 데이터에선 ‘무엇을 놓치고(재현율) 무엇을 잘못 맞히나(정밀도)’를 함께 본다.",
  metricsText: "정밀도 = TP/(TP+FP)\n재현율 = TP/(TP+FN)\nF1 = 둘의 조화평균\nAUC = ROC 아래 면적",
  note: "교차검증으로 데이터를 갈아끼우며 평가하면 운 좋은 한 번을 걸러낼 수 있다.",
});

T.teach({
  kicker: "데이터 · 수학", title: "정답 없이 묶기: 군집화", cat: "slate", figure: "t_kmeans.png",
  lead: "레이블이 없을 때, 가까운 것끼리 묶어 구조를 찾는다. ‘가깝다’의 정의(거리)가 결과를 좌우한다.",
  points: ["K-평균: 각 점을 가장 가까운 중심에 배정 → 중심 갱신 반복", "거리: 유클리디안(L2)·맨해튼(L1)·코사인(방향)", "코사인 유사도는 문서·임베딩 비교에 강함"],
  aha: "지도학습이 ‘정답 맞히기’라면, 군집화는 ‘비슷한 것 발견하기’다.",
});

T.breadthGrid({
  kicker: "모델 계열", title: "알고리즘 빠른 지도", cat: "emerald", cols: 2,
  items: [
    { term: "의사결정 트리", desc: "특징 분할의 연쇄 — 해석 쉬움" },
    { term: "랜덤 포레스트·배깅", desc: "다수 트리 평균 → 분산↓·과적합에 강함" },
    { term: "SVM", desc: "마진 최대 초평면 — 커널로 비선형" },
    { term: "나이브 베이즈", desc: "베이즈 + 독립 가정 — 텍스트에 강함" },
    { term: "전이·사전학습", desc: "남의 지식 재활용 — 적은 데이터에 유리" },
    { term: "앙상블", desc: "여러 모델 결합 — 보통 단일보다 우수" },
  ],
});

T.breadthGrid({
  kicker: "데이터 · 거리 · 수학", title: "토대가 되는 도구들", cat: "slate", cols: 3,
  items: [
    { term: "전처리·특징공학", desc: "정제·스케일링·특징 설계" },
    { term: "차원축소(PCA)", desc: "분산 최대 축으로 압축" },
    { term: "계층적 클러스터링", desc: "병합/분할 계층 구조" },
    { term: "코사인·해밍·자카드", desc: "방향·문자열·집합 유사도" },
    { term: "선형대수", desc: "행렬곱·야코비·헤시안" },
    { term: "불균형·결측·이상치", desc: "오버샘플링·결측처리·이상탐지" },
  ],
});

T.essenceLoop({
  title: "본질 — 모든 개념은 하나의 학습 루프다",
  stages: [{ title: "데이터", sub: "전처리·특징" }, { title: "모델", sub: "회귀~신경망" }, { title: "손실", sub: "틀린 정도" }, { title: "최적화", sub: "경사하강" }, { title: "평가·일반화", sub: "교차검증" }],
  synthesisRuns: [
    { text: "데이터·수학", options: { bold: true, color: "C7D2FE" } }, { text: "이 입력을 만들고, ", options: { color: "AEB8CC" } },
    { text: "모델·신경망", options: { bold: true, color: "C7D2FE" } }, { text: "이 가설을 세우며, ", options: { color: "AEB8CC" } },
    { text: "손실·경사하강", options: { bold: true, color: "C7D2FE" } }, { text: "이 학습을 굴리고, ", options: { color: "AEB8CC" } },
    { text: "평가·검증", options: { bold: true, color: "C7D2FE" } }, { text: "이 일반화를 확인한다. 이 한 바퀴가 곧 ‘학습’이다.", options: { color: "AEB8CC" } },
  ],
});

T.curiosity({
  title: "여기서 더 들어가 보고 싶다면", footerText: "핵심 개념을 직접 구현하며 익혀보자. ",
  qa: [
    { q: "경사하강은 항상 최소점에 닿을까?", a: "볼록이 아니면 지역 최소·안장점에 갇힐 수 있다 — 모멘텀·Adam이 등장한 이유." },
    { q: "Transformer는 왜 RNN을 이겼나?", a: "순차 처리를 버리고 병렬화 → 더 크게, 더 빠르게 학습 가능." },
    { q: "데이터가 적으면?", a: "전이학습·사전학습·데이터 증강·정규화로 과적합을 막는다." },
    { q: "평가가 거짓말을 할 때는?", a: "데이터 누수·불균형·잘못된 분할 — 교차검증과 적절한 지표로 점검." },
  ],
});

T.save("insighta_concept_deck.pptx").then((f) => console.log("WROTE", f, "| slides:", T.page));
