# Insighta Brand & Component Reference

## 1. Brand Tokens

### Colors (hex, no `#` for pptxgenjs)
| Token | Hex | Use |
|---|---|---|
| `primary` | `2563EB` | 브랜드 블루 (메인) |
| `purple` | `7C3AED` | AI 액센트 (보조) |
| `purpleLite` | `A855F7` | 다크 위 키커/강조 |
| `text` | `0F172A` | 라이트 위 본문/제목 |
| `muted` | `475569` | 보조 텍스트 |
| `faint` | `94A3B8` | 캡션/페이지번호 |
| `line` | `E2E8F0` | 카드 테두리 |
| `surface` | `FFFFFF` | 라이트 배경/카드 |
| `surfaceAlt` | `F8FAFC` | 보조 패널 |
| `bgDark` | `0B1220` | 다크 배경(표지/마무리) |
| `bgDarkAlt` | `16213E` | 다크 위 카드 |

### Category palette (6개 주제 — 일관 사용)
| key | main `c` | tint `t` | deep `d` | 의미 |
|---|---|---|---|---|
| `blue` | 2563EB | EFF4FF | 1D4ED8 | 학습 패러다임 |
| `emerald` | 059669 | ECFDF5 | 047857 | 모델 계열 |
| `violet` | 7C3AED | F5F0FF | 6D28D9 | 신경망 구조 |
| `amber` | D97706 | FFF7ED | B45309 | 구성요소·최적화 |
| `rose` | E11D48 | FFF1F4 | BE123C | 평가·검증 |
| `slate` | 475569 | F1F5F9 | 334155 | 데이터·수학 |

### Typography
- Display/Body: **Pretendard** (Regular/SemiBold/Bold/ExtraBold)
- Mono (타임스탬프·라벨·코드): **JetBrains Mono** (Regular/Medium)
- 크기: 표지 제목 50 · 콘텐츠 제목 28 · 카드 용어 13.5 · 본문 10.8~11 · 캡션/모노 9.5~10.5 · 큰 수치 34

### Layout
- LAYOUT_WIDE 13.333 × 7.5", 좌우 마진 `MX=0.62`, 콘텐츠폭 `CW=12.09`
- 카드 라운드 0.06~0.08, 좌측 액센트바 폭 0.09
- 그림자: outer / blur 5 / offset 1.5 / opacity 0.06 (아주 미세하게만)

## 2. Component API (`createDeck()` 반환 헬퍼)

```js
const D = createDeck({ title });
const { pres, BRAND, shapes, newSlide, footer, header,
        conceptGrid, categoryCard, flow, statCallout, chips, matrix2x2,
        PAGE_W, PAGE_H, MX, CW } = D;
```

- `newSlide(dark=false)` → slide. dark면 배경 `bgDark`.
- `header(s, {num?, kicker?, title, cat})` — num 있으면 라운드 번호 태그. **밑줄 없음.**
- `footer(s, n, total)`
- `conceptGrid(s, items, {x,y,w,h,cols,cat,colGap,rowGap})`
  - `items: [{term, desc, ts}]` — ts는 모노로 우상단.
  - 기본 y=1.62 h=5.18. 6항목/2열이면 카드가 큼 → 여백 줄이려면 `h:4.7`.
  - 항목 많고 짧으면 `cols:3`.
- `categoryCard(s, {x,y,w,h, name, count, concepts:[..], cat})` — 맵 카드.
- `flow(s, stages, {x,y,w,h,cat,onDark})` — `stages:[{title, sub}]`, 화살표 자동.
- `statCallout(s, {x,y,w,h, value, unit?, label, cat, onDark})` — 큰 수치.
- `chips(s, labels:[..], {x,y,w,cat,title?})` — 모노 칩 행.
- `matrix2x2(s, {x,y,w,h, cells:[{k,v,good}]×4, cat})` — TP/FP/FN/TN 등.

## 3. Layout Patterns (10장 데모 기준)
1. 표지(다크): 모티프 원 + 모노 키커 + 대형 제목 + 메타 pill 행 + 워드마크
2. 개요: 좌 인사이트 카드 4 + 우 카테고리 레전드 패널(점·이름·개수)
3. 개념 맵: 2×3 `categoryCard` (개념 칩 목록)
4–5. 주제 상세: `conceptGrid` 2열 6장
6. 진화/구조: `flow` 5단계 + 보조 카드 3장
7. 부품: `conceptGrid` 2×2 + `chips`(활성화함수) + 이탤릭 노트
8. 평가: 좌 1열 카드 4 + 우 `matrix2x2` + 하단 `chips`
9. 고밀도: `conceptGrid` 3열 9장
10. 마무리(다크): `statCallout` 3 + `flow`(onDark) + 이탤릭 결론

## 4. Do / Don't
**Do** — 카드 좌측 액센트바를 모티프로 반복 · 카테고리 색 일관 · 모노로 타임스탬프/지표 라벨 · 다크 샌드위치 · 큰 수치 콜아웃으로 핵심 강조.
**Don't** — 제목 밑줄 · 전면 컬러바/사이드 리본 · 본문 중앙정렬 · 텍스트 전용 슬라이드 · 같은 그리드 10장 반복 · 크림/베이지 기본 배경 · 카드 밖으로 넘치는 글자.

## 5. QA 체크리스트
- [ ] 모든 카드 글자가 카드 안에 들어오는가 (넘침 = 최빈 결함)
- [ ] 그리드와 칩/캡션이 겹치지 않는가
- [ ] 슬라이드마다 시각요소가 있는가
- [ ] 카테고리 색이 맵↔상세에서 일치하는가
- [ ] 다크 슬라이드 위 텍스트 대비가 충분한가

## 6. Figures (figures.py) — 도형 · 차트 · 수식
academic-report-builder의 도형 핵심을 브랜드화한 Python 생성기. 모두 **투명 배경**으로
출력해 슬라이드/패널 위에 자연스럽게 얹는다.
- `diagram_*` (Graphviz, 300dpi): 노드 `fontname="Pretendard"`, `bgcolor="transparent"`.
  root는 `#0B1220`(흰 글자), 그룹/리프는 카테고리 (tint 채움 + main 테두리 + deep 글자).
- `chart_*` (matplotlib, 200dpi): `fig.patch.set_alpha(0)`, top/right spine 제거, 막대에 값 라벨.
  **라이트용**(어두운 글자) / **다크용**(흰 글자) 분리 — 다크 차트는 흰 패널 없이 `figure()`로 직접.
- `equation(out, latex, color)` (mathtext, 300dpi): 수식만 렌더. 한글 라벨은 PPTX 네이티브 텍스트로.

## 7. 새 컴포넌트 API (도형/표 삽입)
- `table(s, {x,y,w, headers, rows, cat, colW, fontSize})` — 네이티브 표. 헤더 cat 채움, 1열 강조, 짝수행 tint.
  `colW` 합 = `w`.
- `imagePanel(s, {x,y,w,h, img, dark, pad=0.2, caption, border, fill})` — 라운드 패널 안에 이미지 contain.
  다크 슬라이드엔 흰 패널로 도형을 얹는다(어두운 도형). **흰 글자 다크 차트는 패널 없이 `figure()`**.
- `figure(s, {x,y,w,h, img})` — 패널 없이 이미지 contain.

## 8. 통합 레이아웃 패턴 (12장 데모)
1 표지(다크) · 2 개요+막대차트 · 3 개념맵(카드) · 4 분류트리(Graphviz) · 5–6 주제 카드그리드 ·
7 신경망 플로우+Transformer 도형+카드 · 8 핵심 수식(LaTeX 5행) · 9 부품 카드+칩 ·
10 평가 표+혼동행렬+칩 · 11 데이터·수학 3열 · 12 마무리(다크) 차트+스탯+플로우.

## 9. 수식 입력 정책 (중요)
pptxgenjs는 PowerPoint 네이티브 수식(OMML)을 생성하지 못한다. 수식은 **유니코드 실제 텍스트**로
입력해 복사·편집 가능하게 한다(이미지 금지 — 복사 불가). `equationList()`가 JetBrains Mono로
렌더. 분수/합/지수는 인라인 표기: 분수 `a / b`, 합 `Σ`, 지수 `exp(...)`, 첨자 `ᵢ ⱼ ²`, `ŷ`.
2D 조판이 꼭 필요하면 python-pptx로 OMML XML을 주입하는 별도 경로가 필요(고비용).

## 10. 네이티브 객체 우선 (편집 가능성)
재활용·유지보수가 목적이므로 **모든 구성 객체는 편집 가능해야 한다**.
- 차트 → `nativeBarChart(s,{x,y,w,h,labels,values,color,title})` (pptxgenjs `addChart`). 색은 단일 시리즈라 막대 동일색(편집성 우선).
- 도형/트리 → 박스(`card`/ROUNDED_RECTANGLE) + `connect(s,x1,y1,x2,y2,color,width,arrow)` 커넥터 + `flow`.
- 수식 → `equationList`(유니코드 텍스트). 이미지 금지(복사 불가).
- 표 → `table`(네이티브 `<a:tbl>`).
- PNG(`imagePanel`/`figure`)는 Graphviz 자동 레이아웃이 꼭 필요한 예외에만.

## 11. 본질 통합 슬라이드
덱은 나열로 끝내지 않는다. 마지막에 개념들을 하나의 그림으로 묶는다.
예) ML: `데이터·특징 → 모델 → 손실 → 최적화 → 평가·일반화` 워크플로우 + `connect`로 반복 루프 화살표 +
6개 주제가 어디에 들어가는지 설명하는 합성 문장. (다크 슬라이드 권장)

## 12. 별첨(핸드아웃) 정책
슬라이드 = 본질, 별첨 = 디테일. 별첨은 Markdown(편집·유지보수). 구성: 주제별 용어표(정의+타임스탬프+보강),
핵심 수식(복사용 코드블록), 소스 정정, **출처 목록**. 새 항목은 표에 행 추가로 관리.

## 13. 템플릿 우선 + 자동 검증 (체급 격차 최소화)
- 좌표를 직접 계산하지 말 것. `deck_templates.js`의 `makeTemplates(D,{total,figDir,link})`가 반환하는
  메서드에 **콘텐츠 객체만** 전달한다(페이지·푸터·배치·루프 화살표 자동).
- 빌드 후 반드시 `python scripts/validate_deck.py out.pptx --min-slides N` 으로 점검 → PASS까지 수정.
- 교육 그래프는 `figures.py`의 `teach_*`(고해상 PNG). 구조(트리/플로우/표/매트릭스)와 수식(텍스트)은 네이티브.
- 정보형 차트를 네이티브 `addChart`로 대체하지 말 것(해상도·표현력 저하). 메타 통계 차트(분류 개수 등) 금지.

## 14. Layer 1 범용 장표 원자 (slide_templates.js / makeSlides)
도메인 무관 낱장 12종. 콘텐츠 객체만 전달(좌표·페이지·푸터 자동). 스키마는 slides_example.js 참조.
| 원자 | 용도 | 핵심 인자 |
|---|---|---|
| sectionDivider | 섹션 전환(다크) | no,kicker,title,subtitle,cat |
| agenda | 목차 | items:[{label,desc}],cat |
| keyPoints | 핵심 메시지 3~5 | lead?,points:[{h,t}],cat |
| twoColumn | 2단 비교 | left/right:{h,cat,items[]} |
| comparisonTable | 비교 표(네이티브) | headers,rows,colW?,intro? |
| processSteps | 단계 흐름(번호+화살표) | steps:[{title,sub}],note? |
| listRanked | 순위 리스트 Top-N | items:[{rank?,title,desc}] |
| timeline | 가로 마일스톤 | milestones:[{date,title,desc}] |
| kpis | 큰 수치 3~4 | stats:[{value,unit?,label}] |
| quote | 풀쿼트(다크) | text,author,role?,cat |
| qna | Q&A 카드 2열 | pairs:[{q,a}],cat |
| closingCTA | 마무리·CTA(다크) | title,subtitle?,points[],contact? |

## 15. Layer 2 덱 레시피 (deck_recipes.js / buildRecipe)
영상 유형 → 장표 조합. `await buildRecipe(type, content, out, {link})`. 밀도 우선.
| type | 구성(장표 순서) |
|---|---|
| howto | title → keyPoints(개요) → processSteps → keyPoints(원리) → comparisonTable(도구) → twoColumn(권장/주의) → kpis → closingCTA |
| review | title → keyPoints(평가) → comparisonTable → twoColumn(장/단) → kpis(점수) → quote(평결) → closingCTA |
| interview | title → keyPoints(takeaway) → qna×N → quote → keyPoints(시사점) → closingCTA |
| news | title → keyPoints(무엇) → kpis → twoColumn(원인/영향) → timeline → keyPoints(전망) → closingCTA |
| listicle | title → keyPoints(기준) → listRanked×N → comparisonTable(상위) → closingCTA |
| story | title → keyPoints(배경) → timeline → quote → twoColumn(교훈) → kpis → closingCTA |
| talk | title → keyPoints(주장) → kpis(근거) → comparisonTable → quote → processSteps(실행) → closingCTA |
(explainer=강의는 makeTemplates 학습 덱 — deck_example.js)

## 16. Layer 3 라우터 (router.js)
임의 영상 → 유형 분류 → 내용추출(LLM) → 레시피 빌드.
- `classifyHeuristic({title,description,transcript})` → {type,confidence,scores} (결정적, 키워드·구조).
- `route(input,{mode:"hybrid"|"heuristic", llm, threshold})` → 휴리스틱 우선, 불확실 시 LLM 확정.
- `buildExtractionPrompt(type,input)` → 자막→유형 스키마 JSON 변환 프롬프트(밀도·'메타 금지' 규칙 포함).
- `buildFromVideo(input,out,{classify?,extract,llm?,link})` → 전 과정 자동. extract는 LLM 주입.
- `callAnthropic(prompt,{model,apiKey})` → 프로덕션용 Claude API 호출(키 없으면 미사용). OpenRouter도 동일 패턴.
유형(8): explainer·howto·review·interview·news·listicle·story·talk.

## 17. conceptDeep / 적응형 explainer (분량 표준 12~20)
- `conceptDeep({kicker,title,cat,definition,how:[..],points:[{h,t}],intuition})` — 이미지 없이 한 개념을 꽉 채우는 고밀도 장표(정의+작동방식 번호단계+핵심+직관 콜아웃).
- `buildRecipe("explainer",{title,subtitle,overview,sections:[{title,tagline,definition,how,points,intuition}],compare?,metrics?,essence?,curiosity?,...})` — 섹션 수가 길이를 결정(3~7 → 12~20장). 섹션은 리서치로 밀도 확보.
- 세로 채움 원칙: keyPoints/listRanked/qna/agenda는 항목이 적으면 중앙정렬, comparisonTable/kpis는 행높이·높이로 영역을 채움.

## 18. 레시피 12~20장 표준 (deck_recipes.js) — 심화 단위 루프
간지 금지. 길이는 '심화 단위' 수가 결정: 각 단계/항목/주제/쟁점/국면/논점을 conceptDeep 한 장으로 깊게.
| type | 길이 동인(심화 단위) | 골격 |
|---|---|---|
| howto | steps(5+) | title·개요·준비물·흐름→[STEP 심화]×N·도구표·권장/주의·트러블슈팅·지표·CTA |
| review | options(3+) | title·평가·기준·비교표→[옵션 심화]×N·장단점·점수·상황별추천·인용·CTA |
| interview | themes(4+) | title·takeaway·화자→[주제 심화]×N·Q&A(4씩)·인용·시사점·CTA |
| news | angles(4+) | title·무엇·수치·원인/영향→[쟁점 심화]×N·타임라인·입장차·전망·CTA |
| listicle | items(6+) | title·기준·전체순위→[상위항목 심화]×K·상위비교·CTA |
| story | phases(4+) | title·배경·타임라인→[국면 심화]×N·교훈대비·인용·결과·교훈·CTA |
| talk | arguments(4+) | title·주장·근거→[논점 심화]×N·비교·인용·실행·임팩트·CTA |
심화 단위 = {title, summary(2문장), details:[3+], points:[{h,t} 2+], note} → conceptDeep로 렌더. 표지/마무리/인용은 검증기 밀도 면제(북엔드·풀쿼트).
