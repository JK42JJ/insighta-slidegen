# 로드맵 2 설계 — diagram/table 렌더러 (Graphviz figlib/figdense 차용)

> 상태: **설계만**. 구현은 승인 후. 목표: numerize가 추출한 diagram/table
> struct를 덱-삽입 가능한 PNG로 렌더 — 현 chart_regen은 line/bar/scatter만
> 커버(V02 16건 중 3건=19%; 나머지 diagram 11·table 2는 렌더러 부재로 label-only).
> 이 렌더러로 V02 계열(다이어그램 중심)이 살아나야 §4 존속/폐기 재판정이 공정.

## 0. 근거 (검수·측정 실측)

- V02 numerize 16건: chart 3(렌더O) / **diagram 11 · table 2(렌더X)** → 커버 3/16.
- V01 게이트 검증: 9 차트 통과 중 scatter/bar 3건 렌더, **donut/pie 4건도 렌더X**
  → 데이터차트조차 chart_regen 미지원 유형 존재(부수 발견).
- 즉 렌더러 커버리지가 figure 충실도의 최대 레버. diagram/table이 본 PR 핵심,
  donut/pie는 chart_regen 확장(부수).

## 1. 입력 계약 — numerize가 내는 diagram/table struct

현 mode-B는 table struct(`{headers, rows}`)를 이미 냄. **diagram struct는 현재
미생성**(figure_extract가 diagram kind에 struct 없이 통과) → 이 PR에서 **diagram
struct 스키마를 numerize 프롬프트에 추가**해야 렌더 입력이 생긴다:

```
diagram struct (신규):
{ "diagram_type": "flow"|"tree"|"layered"|"matrix"|"swimlane",
  "nodes": [{"id","label","group"?}], "edges": [{"from","to","style"?}],
  "insight": "" }
table struct (기존): { "headers": [], "rows": [[]] }
```

figlib 5종에 매핑:
| diagram_type | figlib 헬퍼 |
|---|---|
| flow | `horizontal_pipeline(stages, in_node, out_node)` |
| tree / layered | `layered_cluster_diagram(clusters, edges)` |
| matrix | `mapping_matrix(col_headers, row_headers, cells)` |
| swimlane | `swimlane(lanes, steps, order)` |
| (table) | `mapping_matrix` 또는 네이티브 pptx 표(기존) |

## 2. 렌더러 — `py/deck_tools/diagram_regen.py` (신규, chart_regen 형제)

- **Graphviz 자동 레이아웃만**(불변식 1: matplotlib FancyBboxPatch 좌표 금지 —
  반드시 겹침). figlib 5종 헬퍼 패턴을 first-party로 이식(스킬은 문서빌더라
  도형부만 차용; figlib.py를 vendor하지 않고 패턴 재구현 — 라이선스·결합 최소화).
- 고밀도 필요시 figdense 패턴(노드 내 표, 불변식 11: 라벨만이면 미완성).
- struct→Digraph 조립 → `render(dpi=300)` → 흰 여백(finalize_png 패턴).
- **자가점검**(불변식 11): 렌더 PNG ink 검사(chart_regen `_has_enough_ink`
  재사용) + 노드 수 0이면 None(label-only 폴백).
- 실패/미지원 diagram_type → None → label-only(원본 프레임 금지, ADR 0003 P2).

## 3. 한글 fontconfig 선행 (불변식 2·8) — **필수**

Graphviz(dot)는 fontconfig 경유라 폰트 시스템 설치가 선행돼야 한글이 □ 안 됨:
- `install_korean_font(NanumGothic.ttf)` 패턴 — `~/.fonts` 설치 + `fc-cache`.
- NanumGothic TTF를 `py/deck_tools/assets/`에 동봉(스킬 assets에서). matplotlib은
  `addfont`로 충분하나 Graphviz는 fontconfig 필수.
- 서비스 기동 시 1회 설치(app 시작 훅) + 렌더 전 가드.
- 결손 글리프(①②③✓✕) 자동 치환((1)(2)(3)/○/×).

## 4. 배선 (기존 figureRef 경로 재사용 — §1b/1c 그대로)

- regenCharts(orchestrate-runner)에 diagram/table 분기 추가: charts[]·formulas[]
  처럼 diagram/table struct → `python -m deck_tools.diagram_regen` → figure_id PNG.
- bundle.py: diagram/table figure에도 figure_id 부여(이미 charts/formulas엔 있음).
  현재 diagram/table은 charts[]에 kind로 섞여 있음 → 렌더 분기는 kind 기준.
- 배치는 기존 figureSlide(§1c)·validate figure 게이트(§1d) 무변경 재사용.

## 5. 게이트와의 정합

선정 게이트(완결)는 diagram/table을 이미 통과시킴(MODE_B_FIGURE_KINDS 포함).
insight↔series 일치 검증은 chart 전용 — diagram/table엔 node/edge 정합 검증
신설(엣지가 존재하지 않는 노드를 참조하면 reject).

## 6. 테스트 + 검증

- py/tests: diagram_regen 5종 타입 + 한글 라벨 + ink 자가점검 + 미지원→None.
- 통합: V02 게이트 ON 재실행 → diagram/table struct가 렌더·배치되는지(현 3/16
  → 목표 대폭 상승) before/after. donut/pie chart_regen 확장은 별도 작은 PR.

## 7. 구현 순서 (승인 후)
1. numerize 프롬프트에 diagram struct 스키마 추가 + node/edge 정합 게이트
2. `diagram_regen.py`(figlib 5종 패턴) + 한글 fontconfig 설치 + 자가점검
3. assets/NanumGothic 동봉, 서비스 기동 훅
4. regenCharts diagram/table 분기 + figure_id
5. py/tests + V02 before/after 재실행

## 보류·후속 유지
머지 금지 · 키 로테이션(VLLM/YOLO/Webshare/포드 SSH) · RunPod 정지 ·
후속 PR(수식 dedup · 판서 `?` placeholder 후처리 · donut/pie chart_regen 확장 ·
LLM under-reference 프롬프트 · DB 백엔드경유 · presigned §4 · raw-DDL 드리프트 ·
acquire redaction · GH Secret VLM URL · D7 정리 · 단계트리 로컬 pull 자동화).
