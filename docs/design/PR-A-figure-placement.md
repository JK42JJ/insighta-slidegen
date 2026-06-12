# PR-A 설계 — figure 배치 복원 + 렌더 품질 기준 (구현 전 설계안)

> 상태: **설계만**. 구현은 James 승인 후. 측정에서 확정된 최대 품질 갭
> (CV 수치화 figure가 덱에 미배치 → 산출물이 LLM-only와 무차별)을 닫는다.
> 목표: "스크린샷 크롭 붙이기"가 아니라 **수치화 데이터의 충실한 재렌더**.

---

## 0. 문제 (측정 13차에서 코드로 확정)

CV가 영상당 figure 수~십수 개를 수치화(chart struct / LaTeX)하고 chart_regen이
300dpi PNG까지 생성하지만, **덱에 0장 배치**된다. 두 단절:

- **단절 ①** `src/deck/orchestrate-runner.ts:290` — `regenCharts()`가 PNG를
  만들지만 `:300` orchestrate opts에 자산 통로가 없어 `chartAssets`는 고아.
- **단절 ②** `deck/scripts/deck_recipes.js` — `img` 참조 0건. 배치 프리미티브
  (`imagePanel`/`figure`/`equationList`, `insighta_deck.js:234-246`)는 존재하나
  어떤 PLAN도 호출 안 함. LLM content 스키마에 이미지 키 없음.
- **validate 맹점** `deck/scripts/validate_deck.py:7` — 하드 FAIL은 오버플로/
  분량/메타 3종뿐. 차트·이미지는 `:86-89`에서 집계만 → 차트 0이어도 PASS.
  따라서 G1은 figure 배치에 구조적으로 맹목.

---

## 1. PR-A 변경 설계 (4개 레이어, 편집 순서 = DB→없음 / 계약→소비→게이트)

### 1a. resources 번들에 렌더 산출물 좌표를 실어 보낸다 (계약)

bundle.py의 `charts[]`/`formulas[]` 엔트리는 이미 `snapshot`(인접 키프레임
인덱스)·`t`·`struct`/`latex`를 가진다(확인필). **각 엔트리에 안정적
`figure_id`를 추가**해 PNG 파일명과 1:1 매칭 키로 삼는다. 번들은 여전히
DATA/LaTeX만 — 픽셀 없음(ADR 0003 P2 유지).

```
charts[i]  += { "figure_id": "<cv_figure_id>" }   # chart_regen PNG 파일명 키
formulas[i] += { "figure_id": "<cv_figure_id>" }
```

### 1b. 러너가 chartAssets를 buildRecipe까지 전달한다 (단절 ① 봉합)

`orchestrate-runner.ts`: `regenCharts()`가 `{figure_id → pngPath}` 맵을
반환하도록 바꾸고(현재는 snapshot 기준 배열), `orchestrateOpts`에
`figureAssets` 키로 주입. `equationList`용 LaTeX는 번들 `formulas[]`에 이미
있으므로 별도 렌더 없이 텍스트 수식으로 전달(추후 mathtext PNG 옵션).

```ts
const orchestrateOpts = { llm, minSlides, link?, classify?,
                          figureAssets /* {figure_id: pngPath} */ };
```

### 1c. vendored 레시피가 figure를 소비한다 (단절 ② 봉합 — **upstream 개정 + 재vendor**)

> **⚠️ D7 예외 (이 PR 한정, James 승인 2026-06-12)**: upstream
> `insighta-visual-deck` 레포가 로컬·GitHub 어디에도 실재하지 않음을 확인했다
> (`gh repo list` + 로컬 find 음성). 정석 "upstream 개정 → 재vendor"가 불가하여,
> **이 PR에 한해 vendored `deck/scripts/*.js`를 직접 편집**한다(ADR 0003 D7
> 바이트 불가침의 1회성 예외). deck/엔 해시락·바이트검증 가드가 없어 기술적
> 차단은 없으나, 예외를 영구화하지 않는다 — **후속 PR 목록에 "D7 정리:
> deck/를 정식 first-party로 편입하거나 upstream 레포 신설"을 등재**(아래 §5).

deck/를 직접 편집한다(상기 예외). 세 곳:

1. **content 스키마 확장** — 섹션/콘텐츠 블록에 선택적 `figureRef` 키:
   ```
   section.figureRef = { figure_id, kind: "chart"|"diagram"|"table"|"equation",
                         caption }
   ```
   LLM이 "이 슬라이드에 이 figure를 배치"를 **지정만** 한다(이미지 경로는 모름).
2. **PLAN이 소비** — `deck_recipes.js`의 conceptDeep/processSteps deepUnit 등에
   `figureRef`가 있으면 `["figure"/"imagePanel", {img: assets[figure_id], caption}]`
   또는 kind=equation이면 `["equationList", {items: [...]}]`를 plan에 push.
   `assets[figure_id]`가 없으면(렌더 실패) **label-only 폴백**(현 동작 유지 —
   raw frame 금지).
3. **buildRecipe 서명** — `buildRecipe(type, content, outPath, {link, figureAssets})`로
   확장, plan 빌드 시 figure_id→path 치환.

### 1d. validate가 figure 배치를 게이트한다 (맹점 봉합)

`validate_deck.py`에 **하드 FAIL 1종 추가**: 입력 리소스에 renderable figure가
N개 이상인 영상(차트형·수식형)인데 덱 이미지 수 < 임계면 FAIL.

```
--require-figures K   # 번들 charts+formulas 개수 기반으로 러너가 산정해 전달
# 덱 media 수 < min(K, FLOOR) → FAIL: "figure 미배치 — CV 산출물이 덱에 없음"
```

차트·수식이 애초에 없는 영상(순수 강의)은 K=0 → 게이트 면제. 이로써 **G1이
figure 배치 품질을 잡게 되어** 제품 본질과 측정이 정렬된다.

---

## 2. figure 렌더 품질 기준 (academic-report-builder 차용 — chart_regen/redraw 규칙)

스킬 SKILL.md 11개 불변식 중 CV→figure 재생성에 적용할 항목. **현 redraw.py는
대부분 미구현 스텁**이라, 이 기준이 redraw.py 구현 규약이 된다.

### 2a. 도형(diagram/구조도/표) = Graphviz 자동 레이아웃 (불변식 1·11)
- `FancyBboxPatch` 수동 좌표 배치 **금지** — 반드시 겹쳐 폐기 대상.
- figlib.py 5종 헬퍼 패턴 차용: `layered_cluster` / `horizontal_pipeline` /
  `mapping_matrix` / `vertical_stack` / `swimlane`.
- CV의 diagram struct(노드·엣지 추출 시)를 이 5종에 매핑. **단 현 CV는
  diagram을 struct로 수치화하지 않음**(chart/equation만) → diagram은 PR-A
  범위에서 **label-only 유지**, struct 추출은 별도 PR(범위 명시).

### 2b. 데이터 차트(막대·선·산점도) = matplotlib (불변식 10)
- 현 `chart_regen.py`가 이 경로(line/bar/scatter struct → PNG). **추가 규칙**:
  비례 수치 극단(예 80 vs 2700)이면 **broken-axis 2단 패널**.
- 막대는 `Rectangle`, `FancyBboxPatch.rounding_size` **금지**(좁은 막대 원형
  뭉갬).

### 2c. 고밀도 기준 (불변식 11 — figdense, dense-figure-recipes.md)
- 노드/차트에 **라벨만 있으면 미완성**. 정량 정보(수치·표·축값)를 넣는 게 상한.
- chart_regen 출력에 axes 단위·series 값 레이블을 강제(struct에 있으면 누락 금지).
- figdense 빌딩블록(저수준 HTML-like 노드 반환)을 CV 산출에 매핑:
  `spec_node`(제목+키·값 행) ← chart struct의 series 메타 / `stage_node`
  (N입력→M출력) ← 파이프라인형 diagram / `matrix_table`(행×열 ●/○) ←
  비교표 struct / `kv_panel`(키·값) ← 단일 수치군. `figdense`는 Digraph를
  **직접** 조립(figlib와 달리 헬퍼가 레이아웃을 안 만듦) — render(g, path, dpi=600).
- broken-axis(2b)는 dense-recipe 5번 패턴: 2단 subplots, 막대=`Rectangle`
  (rounding 없음), 좁은 막대는 막대 위 callout+leader, 패널 경계 걸친 막대는
  `"T4 ▶"` 안내.

### 2d. 수식(equation) = LaTeX 렌더
- 번들 `formulas[].latex`(UniMERNet OCR) → matplotlib mathtext 또는 pdflatex
  standalone → PNG/SVG. **저신뢰(conf<0.7)는 `unverified` 플래그 유지**, 억지
  렌더 금지(ADR 0003 D3).

### 2e. 품질 퇴행 금지 점검 (불변식 11)
- 생성 PNG를 **view로 시각 점검** — 겹침·잘림·정보부족이면 좌표 조정이 아니라
  **struct(노드/엣지/series) 수정 후 재생성**. CI엔 못 넣으므로 **렌더 후
  자동 점검**(빈 이미지·단색 비율·텍스트 OCR 라운드트립) 휴리스틱을 redraw에 내장.

### 2f. 한글 렌더 (불변식 2·8)
- Graphviz(도형) = fontconfig 경유 → `install_korean_font()`로 `~/.fonts` 설치 +
  `fc-cache` **선행 필수**(빠뜨리면 □ 두부). NanumGothic TTF 동봉.
- matplotlib(차트) = `fm.fontManager.addfont()`로 충분.
- 결손 글리프(①②③✓✕) 자동 치환((1)(2)(3)/○/×).

---

## 3. Sonnet 기준 프롬프트 타이트닝 (스킬은 Opus급 — 하네스는 Sonnet급)

academic-report-builder는 상위 모델이 자유 작성하는 전제. 프로드 하네스의
LLM은 **주입형·도구 없음**(ADR 0003 D2)이고 Sonnet급이므로 자유도를 줄인다.

| 항목 | Opus 전제 (스킬) | Sonnet 타이트닝 (하네스) |
|---|---|---|
| 출력 스키마 | 느슨한 블록 리스트, 모델이 구성 | **JSON 스키마 고정** — figureRef 필드·enum·필수키 명시, 예시 2개 인라인 |
| figure 배치 판단 | 모델이 "어디 둘지" 추론 | **결정론적 배치 후보 제시** — 러너가 snapshot→섹션 매핑을 미리 계산해 "이 figure_id를 이 섹션에" 후보를 프롬프트에 주입, 모델은 채택/기각만 |
| stat/struct 형태 | 모델이 올바른 형태 생성 가정 | **이미 b018232 정규화 적용** — metrics/scores 형태 교정. figureRef도 동일 정규화 추가 |
| 자유 서술 | 모델이 밀도 자가 판단 | **검증 되먹임 루프**(현존) + figure 게이트(1d)로 강제 |
| 재시도 | — | 빌더 크래시 재시도(8a0da88) + per-crop 스킵(c3f0d0e) 유지 |

핵심: **모델에게 figure를 "만들라"가 아니라 "배치 후보 중 고르라"**로 과제를
축소. 렌더는 결정론적 코드(chart_regen/redraw), 모델은 어느 슬라이드에 어느
figure_id를 붙일지 선택 + 캡션 작성만.

---

## 4. 존재 이유 검증 실험 (slidegen 존속/폐기 판정)

동일 영상 **V02·V08**(13차 PASS본 보유)에 대해 두 덱을 나란히 생성·비교:

| 축 | A: 수선 파이프라인 (PR-A 적용) | B: v2-요약-only LLM |
|---|---|---|
| 입력 | CV figure(chart_regen PNG) + v2 | **v2 rich-summary 텍스트만** |
| 경로 | acquire→CV→numerize→figureRef 배치 | v2 → buildRecipe (figure 없음) |
| 산출 | figure 배치된 .pptx | 텍스트 .pptx (현 13차 산출물과 동일) |

**비교 축 = 시각자료 충실도**: 영상 실물의 차트/표/수식이 덱에 충실히 재현됐는가
(A) vs 텍스트 서술로 대체됐는가(B). 측정:
- figure 배치 수 (A는 ≥K, B는 0)
- 수동 대조(James): 덱 figure ↔ 영상 실물 프레임 일치도 (1~5)
- **판정**: A가 B 대비 시각자료 충실도에서 유의하게 우월하지 않으면 → CV
  파이프라인의 존재 이유 없음 → slidegen 폐기/재설계 근거. 우월하면 → 존속 +
  PR-A 정식 머지.

절차: B는 `extractFigures`를 빈 figures로 스텁(또는 `--no-cv` 플래그 신설)해
같은 buildRecipe로 생성. 동일 LLM·동일 시드 조건, figureRef만 차이.

---

## 5. 구현 순서 (승인 후) + 보류 유지

1. bundle figure_id (1a) — 서비스, 테스트
2. redraw.py 렌더 구현 (2절 기준) — Graphviz 도형/matplotlib 차트/LaTeX, view 점검 휴리스틱
3. upstream insighta-visual-deck 레시피 확장 (1c) → 재vendor (D7 절차)
4. 러너 figureAssets 통로 (1b) + Sonnet 프롬프트 타이트닝 (3절)
5. validate figure 게이트 (1d)
6. 비교 실험 (4절) → James 판정

**보류 유지**: 측정 전 머지 금지(worktree-prh2-proxy) · 키 로테이션
(VLLM/YOLO/Webshare/포드 SSH) · 후속 PR 누적 목록:
- DB 직접접근(captions/keyframes) 백엔드 경유 전환
- 모델 핸드오프 presigned §4 통일 (현 data URL)
- slide_figures·slide_keyframes raw-DDL 드리프트 해소
- acquire 에러 메시지 redaction (프록시 자격 노출)
- GH Secret `SLIDEGEN_VLM_BASE_URL` 값 교정 (`/v1` 제거)
- **D7 정리: deck/를 정식 first-party로 편입하거나 upstream 레포 신설**
  (이 PR의 D7 1회성 예외를 영구화하지 않기 위함 — James 조건)
- CV 서비스 단계 트리의 로컬 pull 자동화 (현 ops scp)
- **diagram/table struct 렌더러 (Graphviz figlib/figdense 차용) — 우선순위 근거:
  V02 실측 numerize 16건 중 13건(diagram 12·table 2 — chart 3만 렌더 가능)이
  렌더러 부재로 label-only. 즉 현 chart_regen 커버리지 3/16(19%). diagram struct
  추출 + figlib 배치로 이 13건을 덱에 올리는 것이 figure 충실도의 최대 레버.**
