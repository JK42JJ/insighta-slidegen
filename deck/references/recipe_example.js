/* build_recipes_demo.js — howto·review를 신(新) 리치 스키마로 빌드(각 단위=심화 1장, 12~20장). */
const path = require("path");
const { buildRecipe } = require(path.join(__dirname, "..", "scripts", "deck_recipes.js"));

const howto = {
  title: "Docker로 앱 배포하기", subtitle: "한 번 만들면 어디서나 똑같이 도는 컨테이너 워크플로우",
  pills: [["대상", "입문 개발자"], ["스택", "Docker · CI"], ["소요", "30분"]],
  overviewTitle: "왜 컨테이너인가", overviewLead: "‘내 PC에선 됐는데’를 없애는 것이 목표다.",
  overview: [
    { h: "환경을 코드로 고정", t: "OS·런타임·의존성을 이미지에 함께 담아 어느 서버든 동일하게 재현한다." },
    { h: "격리와 이식성", t: "호스트와 분리돼 충돌이 없고, 레지스트리로 어디든 옮긴다." },
    { h: "배포가 곧 교체", t: "새 이미지로 컨테이너를 갈아끼우고, 롤백도 이전 태그로 즉시." },
  ],
  prereq: [
    { h: "Docker 설치", t: "Docker Desktop 또는 Engine. `docker version`으로 데몬 동작을 확인한다." },
    { h: "앱과 의존성 목록", t: "실행 명령과 포트, requirements/package.json 등 의존성이 정리돼 있어야 한다." },
    { h: "레지스트리 계정", t: "Docker Hub·ECR 등 이미지를 올릴 곳과 인증을 준비한다." },
  ],
  stepsNote: "각 단계는 이전 산출물(파일→이미지→태그→실행)을 입력으로 받는다.",
  steps: [
    { title: "Dockerfile 작성", summary: "앱을 이미지로 굽는 설계도를 만든다. 베이스 이미지·의존성 설치·실행 명령을 선언적으로 적는다.",
      details: ["FROM으로 베이스 이미지 선택", "COPY·RUN으로 의존성 설치", "CMD/ENTRYPOINT로 실행 명령 지정"],
      points: [{ h: "멀티스테이지", t: "빌드용과 실행용 단계를 분리해 최종 이미지를 가볍게 한다." }, { h: "레이어 순서", t: "변경 적은 의존성을 위층에 두어 캐시 적중률을 높인다." }],
      note: "Dockerfile은 ‘재현 가능한 빌드 절차’를 코드로 박제한 것." },
    { title: "이미지 빌드", summary: "Dockerfile로 실제 이미지를 생성한다. 레이어 캐시 덕분에 두 번째 빌드부터는 매우 빠르다.",
      details: ["docker build -t app:1.0 .", "각 명령이 하나의 레이어로 캐시됨", ".dockerignore로 불필요 파일 제외"],
      points: [{ h: "태그 전략", t: ":latest 대신 버전·커밋 해시로 명시해 추적성을 확보한다." }, { h: "캐시 무효화", t: "상위 레이어가 바뀌면 이후 전부 재빌드되므로 순서가 중요." }],
      note: "이미지는 불변(immutable) — 고치지 않고 새로 굽는다." },
    { title: "레지스트리 푸시", summary: "만든 이미지를 원격 저장소에 올려 어디서든 내려받게 한다. 협업과 배포의 공유 지점이다.",
      details: ["docker login으로 인증", "docker tag로 레지스트리 경로 부여", "docker push로 업로드"],
      points: [{ h: "프라이빗", t: "사내 이미지는 ECR·GHCR 등 프라이빗 레지스트리에 보관." }, { h: "스캔", t: "푸시 시 취약점 스캔을 걸어 보안 문제를 조기에 발견." }],
      note: "레지스트리는 이미지의 ‘배포 허브’." },
    { title: "컨테이너 실행", summary: "이미지를 인스턴스화해 실제로 구동한다. 포트·환경변수·볼륨을 주입해 환경에 맞춘다.",
      details: ["docker run -p 8080:80 app:1.0", "-e로 환경변수, -v로 볼륨 마운트", "--restart로 장애 시 자동 재기동"],
      points: [{ h: "비루트", t: "컨테이너를 비루트 사용자로 실행해 공격면을 줄인다." }, { h: "리소스 제한", t: "--memory·--cpus로 한 컨테이너가 호스트를 잠식하지 않게." }],
      note: "같은 이미지를 환경별 설정만 바꿔 실행 — 일관성의 핵심." },
    { title: "모니터·갱신", summary: "운영 중 로그·헬스체크로 상태를 보고, 새 버전을 무중단으로 교체한다.",
      details: ["docker logs·healthcheck로 상태 관찰", "새 태그 빌드→푸시→롤링 교체", "문제 시 이전 태그로 롤백"],
      points: [{ h: "헬스체크", t: "HEALTHCHECK로 비정상 컨테이너를 자동 감지·재기동." }, { h: "관측성", t: "로그·메트릭을 중앙 수집해 장애를 빠르게 진단." }],
      note: "배포의 끝이 아니라, 관측→개선의 루프 시작." },
  ],
  toolsTitle: "런타임·도구 비교", toolsIntro: "상황별로 컨테이너 런타임을 고른다.",
  tools: { headers: ["기준", "Docker", "Podman", "containerd"],
    rows: [["데몬", "필요", "불필요(rootless)", "경량 데몬"], ["호환", "표준", "Docker CLI 호환", "쿠버네티스 기본"], ["적합", "로컬 개발", "보안 민감", "운영 클러스터"], ["빌드", "내장", "buildah", "외부"]] },
  pitfalls: { do: ["멀티스테이지로 이미지 경량화", "태그 명시(:latest 지양)", "헬스체크·리소스 제한", "비루트 실행"],
    dont: ["비밀키를 이미지에 굽기", "거대한 베이스 이미지", "한 컨테이너에 여러 프로세스", "캐시 깨는 잦은 상위 변경"] },
  troubleshootTitle: "흔한 오류와 해결",
  troubleshoot: [
    { h: "빌드가 매번 느리다", t: "의존성 설치 레이어를 코드 COPY보다 위로 옮겨 캐시 적중률을 높인다." },
    { h: "이미지가 너무 크다", t: "slim/alpine 베이스 + 멀티스테이지로 빌드 산출물만 남긴다." },
    { h: "컨테이너가 바로 종료", t: "포그라운드 프로세스를 CMD로 실행했는지, 로그로 종료 원인을 확인한다." },
  ],
  metricsTitle: "기대 효과",
  metrics: [{ value: "초", unit: "단위", label: "캐시 적중 재빌드" }, { value: "1", unit: "이미지", label: "어디서나 동일 실행" }, { value: "즉시", label: "이전 태그 롤백" }],
  closeTitle: "정리 — 직접 배포해보기", closeSub: "작은 앱 하나를 컨테이너로 올려보자.",
  actions: ["웹앱에 Dockerfile 작성 후 빌드", "레지스트리에 푸시하고 다른 머신에서 실행", "멀티스테이지로 이미지 크기 절반으로"],
  contact: "hello@insighta.one",
};

const dunit = (title, summary, details, points, note) => ({ title, summary, details, points, note });
const review = {
  title: "API 설계: REST vs GraphQL vs gRPC", subtitle: "범용·유연·고성능 — 클라이언트가 선택을 결정한다",
  pills: [["분야", "백엔드 설계"], ["관점", "실무 선택 기준"]],
  summaryTitle: "한 줄 평가", summaryLead: "정답은 없다 — 트래픽 형태와 클라이언트가 결정한다.",
  summary: [
    { h: "REST", t: "자원 중심 표준. 캐싱·도구·생태계가 가장 두텁고 학습 곡선이 완만하다." },
    { h: "GraphQL", t: "클라이언트가 필요한 필드만 한 번에 질의해 오버페치를 없앤다." },
    { h: "gRPC", t: "HTTP/2 + 바이너리로 저지연·고처리량. 서비스 간 통신에 강하다." },
  ],
  criteriaTitle: "무엇을 보았나",
  criteria: [
    { h: "요청 효율", t: "한 화면을 그리는 데 왕복 횟수와 전송량이 얼마나 되는가." },
    { h: "캐싱·생태계", t: "표준 캐싱과 도구·레퍼런스가 충분한가." },
    { h: "스키마·계약", t: "타입 안전성과 클라이언트 코드 생성 지원 정도." },
  ],
  tableTitle: "기준별 비교", tableIntro: "대표 기준 5가지.",
  table: { headers: ["기준", "REST", "GraphQL", "gRPC"],
    rows: [["전송", "JSON/HTTP1.1", "JSON/HTTP", "binary/HTTP2"], ["요청 수", "여러 번", "한 번", "한 번"], ["캐싱", "쉬움(HTTP)", "어려움", "어려움"], ["스키마", "느슨(OpenAPI)", "강함", "강함(protobuf)"], ["적합", "공개 API", "복잡한 프런트", "서비스 간"]] },
  options: [
    dunit("REST", "자원을 URL로 표현하고 HTTP 메서드로 다루는 표준 스타일. 가장 널리 쓰여 도구·캐싱·인프라 지원이 풍부하다.",
      ["자원 단위 엔드포인트 설계", "HTTP 캐싱·상태코드 활용", "OpenAPI로 문서·검증"],
      [{ h: "강점", t: "브라우저·CDN 캐싱과 방대한 생태계, 낮은 진입장벽." }, { h: "약점", t: "화면이 복잡하면 여러 번 왕복(언더/오버페치)." }],
      "‘가장 무난한 기본값’ — 공개 API라면 1순위 후보."),
    dunit("GraphQL", "클라이언트가 필요한 데이터의 형태를 질의로 기술하면 한 번에 받아오는 쿼리 언어. 프런트 주도 개발에 적합하다.",
      ["스키마로 타입 정의", "쿼리로 필요한 필드만 요청", "리졸버로 데이터 결합"],
      [{ h: "강점", t: "오버/언더페치 제거, 화면별 맞춤 응답." }, { h: "약점", t: "HTTP 캐싱이 어렵고 N+1·쿼리 비용 관리가 필요." }],
      "화면이 다양하고 자주 바뀌는 프런트에 강하다."),
    dunit("gRPC", "protobuf로 계약을 정의하고 HTTP/2 위에서 바이너리로 통신하는 고성능 RPC. 마이크로서비스 내부 통신에 적합하다.",
      [".proto로 서비스·메시지 정의", "코드 생성으로 타입 안전 클라이언트", "스트리밍·양방향 지원"],
      [{ h: "강점", t: "낮은 지연·작은 페이로드, 강한 계약과 코드 생성." }, { h: "약점", t: "브라우저 직접 호출 제약(프록시 필요), 사람이 읽기 어려움." }],
      "내부 서비스 간 고성능 통신의 사실상 표준."),
  ],
  prosTitle: "공통 장점 vs 주의점", prosLabel: "강점이 빛나는 곳", consLabel: "주의가 필요한 곳",
  pros: ["REST: 캐싱·도구·생태계", "GraphQL: 화면별 데이터 최적화", "gRPC: 서비스 간 저지연", "셋 다 스키마·문서 자동화"],
  cons: ["REST: 복잡 화면서 왕복 증가", "GraphQL: 캐싱·N+1 관리", "gRPC: 브라우저 제약", "혼용 시 게이트웨이 복잡도"],
  scoresTitle: "선택을 가르는 축",
  scores: [{ value: "공개", label: "외부 공개 API → REST" }, { value: "유연", label: "다양한 화면 → GraphQL" }, { value: "내부", label: "서비스 간 → gRPC" }],
  useCasesTitle: "상황별 추천",
  useCases: [
    { h: "공개 플랫폼 API", t: "서드파티가 쓰고 캐싱이 중요하면 REST가 안전하다." },
    { h: "복잡한 대시보드", t: "화면마다 데이터가 달라지면 GraphQL이 군더더기를 없앤다." },
    { h: "마이크로서비스", t: "내부 호출이 잦고 지연이 중요하면 gRPC." },
  ],
  quote: { text: "프로토콜을 먼저 고르지 말고, 클라이언트가 데이터를 어떻게 쓰는지를 먼저 보라.", author: "API 설계 원칙", role: "실무 가이드" },
  closeTitle: "추천 — 이렇게 고르자", closeSub: "하나만 고집하지 말고 경계에서 조합한다.",
  recommend: ["외부 공개·캐싱 중요 → REST", "프런트 주도·다양한 뷰 → GraphQL", "내부 마이크로서비스 → gRPC + 외부엔 게이트웨이"],
  contact: "hello@insighta.one",
};

(async () => {
  await buildRecipe("howto", howto, "recipe_howto.pptx");
  await buildRecipe("review", review, "recipe_review.pptx");
  console.log("WROTE recipe_howto.pptx, recipe_review.pptx");
})();
