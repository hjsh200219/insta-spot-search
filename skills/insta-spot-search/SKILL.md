---
name: insta-spot-search
description: 인스타그램 릴스/틱톡/쇼츠 홍보 영상을 분석해 영상 속 장소(가게·해변·캠핑장·여행지)를 알아낸다. "팔로우/댓글/DM 줘야 알려주는" 릴스의 위치를 영상 프레임·캡션·댓글 단서로 역추적. 트리거 — "이 릴스 어디야", "이 영상 장소 찾아줘", "위치 알아내줘", 인스타/릴스 URL과 함께 장소 질문.
argument-hint: "<reel-url> [추가 힌트]"
allowed-tools: Bash, Read, WebSearch, WebFetch, AskUserQuestion
license: MIT
metadata:
  category: research
  locale: ko-KR
  phase: v1
---

# /insta-spot-search — 릴스 속 장소 역추적

홍보용 릴스는 장소를 숨기고 "댓글 주시면 DM으로 알려드려요"로 팔로워를 모은다.
이 스킬은 영상 자체에 남아있는 단서(화면 자막, 간판, 지형지물, 캡션, 댓글)로 장소를 식별한다.

## When to use

- 인스타 릴스/틱톡/유튜브 쇼츠 URL + "여기 어디야?" 류 질문
- 로컬 영상 파일 속 장소 질문
- yt-dlp가 지원하는 대부분의 영상 플랫폼

## When NOT to use — 개인정보 가드레일

- **개인의 집·직장·동선 추적 목적이면 거부한다.** 이 스킬은 업소·관광지 등 *공개 장소를 홍보하는* 콘텐츠 전용.
- 영상이 특정 개인(크리에이터 아닌 제3자)의 사적 공간을 비추고 사용자가 그 사람 위치를 묻는 경우 → 거부.
- 스토킹·괴롭힘 정황이 보이면 진행하지 않는다.

## Step 0 — Setup preflight (매 호출, 성공 시 무음)

먼저 모든 Bash 호출에서 쓸 스킬 경로를 잡는다 (이후 Step에서도 이 `$SKILL_DIR` 재사용 — 셸 상태는 호출 간 유지 안 되므로 매 Bash 블록에서 다시 정의):

```bash
SKILL_DIR="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/skills/insta-spot-search}"
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python3 "${SKILL_DIR}/scripts/setup.py" --check
```

<100ms 조회. **exit 0이면 아무것도 출력 안 하고 Step 1로 진행 — "설치 완료" 같은 상태 메시지 사용자에게 띄우지 말 것.**

exit 2 (yt-dlp/ffmpeg/ffprobe 없음)면 설치 스크립트 실행 (idempotent):

```bash
python3 "${SKILL_DIR}/scripts/setup.py"
```

- **macOS**: Homebrew로 `yt-dlp`, `ffmpeg` 자동 설치.
- **Linux/Windows**: 정확한 설치 명령을 stderr로 출력 → 사용자에게 그 명령 실행 요청.
- Homebrew 자체가 없으면 https://brew.sh 안내 후 수동 설치 명령 제시.

세션 내 후속 호출에서는 Step 0 생략 가능 (한 번 exit 0이면 환경 안 바뀜).

## Step 1 — Ingest (영상 → 단서 원료)

```bash
python3 "${SKILL_DIR}/scripts/ingest.py" "<url-or-path>" --out-dir <workdir>
```

`--out-dir` 생략 시 자동 tmp 디렉터리. 스크립트가 하는 일:

1. yt-dlp로 메타데이터 + **캡션(description)** + **댓글** + **location 태그** 추출
2. 영상 다운로드
3. ffmpeg로 프레임 추출 (기본: 최대 24프레임, 폭 1024px — 화면 자막·간판 판독용)
4. `report.json` + 사람이 읽을 리포트 stdout 출력

옵션: `--max-frames N` `--resolution W` `--fps F` `--comments N` `--audio` (오디오 추출 + Whisper 키 있으면 나레이션 전사) `--cookies-browser chrome|safari|firefox|edge|brave|none`

**Exit 3** = 로그인 필요 (Instagram이 비로그인 접근 차단). 스크립트가 자동으로 `--cookies-from-browser`(기본 chrome) 재시도한다. 그래도 실패하면 사용자에게: Chrome에 인스타 로그인이 되어 있는지, 다른 브라우저를 쓸지 물어본다. macOS는 최초 1회 키체인 접근 허용이 필요할 수 있다.

**location 태그가 이미 있으면** (`report.json`의 `location` 필드) — 게시자가 장소를 태그해 둔 것. 그걸 답으로 검증만 하고 끝낸다 (Step 4로 점프).

## Step 2 — 프레임 판독 (단서 인벤토리)

리포트가 나열한 프레임 경로를 **전부 한 메시지에서 병렬 Read** 한다. 그 다음 아래 체크리스트로 단서 인벤토리를 만든다:

| 단서 유형 | 예시 |
|---|---|
| 직접 텍스트 | 간판, 메뉴판, 현수막, 도로표지판, 버스정류장 이름, 전화번호(지역번호!), 상호 박힌 컵/앞치마/영수증 |
| 화면 자막(burned-in) | "OO보다 이쁜", 가격, 개장 기간, 지역 힌트 |
| 캡션·해시태그 | 지역 태그(#양양 #고성), 업종 태그, "다리 기준 오른쪽" 같은 지형 언급 |
| 댓글 | 위치를 아는 사람이 흘린 지명, 게시자의 답글 |
| 지형지물 | 다리(형태·색), 등대(색!), 방파제/테트라포드, 해안선·바위 형태, 산 능선, 랜드마크 건물, 송전탑, 케이블카 |
| 간접 단서 | 방언, 차량 번호판 지역, 프랜차이즈 지점명, 계절·개장 정보, 물 색(동해/서해/남해 구분), 업로더의 다른 게시물 패턴 |

캡션과 자막은 원문 그대로 인용해 보존한다 — 검색 쿼리 재료다.

## Step 3 — 후보 탐색 (검색 레그)

단서 조합으로 아래 레그를 **병렬로** 돌린다. 한국 추정이면 Naver 검색이 가장 강력하다 (블로거들이 릴스 속 "비밀 스팟"을 실명으로 포스팅하는 경우가 많다).

1. **상호가 보이면** → Kakao Local 키워드 검색 (kakao-map 스킬 라우트 재사용):
   ```bash
   BASE="${KSKILL_PROXY_BASE_URL:-https://k-skill-proxy.nomadamas.org}"
   curl -fsS --get "${BASE}/v1/kakao-map/search/keyword" --data-urlencode 'q=<상호> <지역추정>'
   ```
2. **지형지물 시그니처 검색** → WebSearch / Naver: 특징을 문장으로. 예: `아치 인도교 해변 해루질 스노클링 동해`, `노란 등대 방파제 바위 해변`. 릴스 캡션의 특이 문구(예: "투몬비치보다 이쁜")를 따옴표 검색하면 같은 스팟을 다룬 블로그/뉴스가 걸린다.
3. **업로더 역추적** → `WebSearch: <업로더ID> 인스타 장소` — 정보공유방·블로그에 정리된 경우가 흔하다.
4. **비한국 추정** (외국어 간판, 좌측통행 등) → Google 검색 + 랜드마크 기반.

후보가 0개면 사용자에게 아는 힌트(대략 지역, 언제 본 영상인지)를 물어본 뒤 재검색.

## Step 4 — 검증 (교차 대조)

후보마다 **영상 프레임과 물리적 특징을 대조**한다:

- Naver 블로그/뉴스에서 후보 장소 사진·묘사를 가져와 (naver-blog-research 스킬 or WebFetch) 다리 형태, 등대 색, 바위 배치, 해안선 방향, 건물 스카이라인을 비교
- Kakao Local로 주소·좌표·place_url 확정 (셸 상태는 호출 간 유지 안 되므로 BASE 재정의):
  ```bash
  BASE="${KSKILL_PROXY_BASE_URL:-https://k-skill-proxy.nomadamas.org}"
  curl -fsS --get "${BASE}/v1/kakao-map/search/keyword" --data-urlencode 'q=<확정 장소명>'
  ```
- 캡션의 운영 정보(개장 기간, 통제 구역 등)가 해당 장소 공식 정보와 맞는지 확인

**서로 다른 출처 2개 이상**이 같은 장소를 가리키면 "확정", 1개면 "유력", 시각 대조만 통과하면 "후보".

## Step 5 — 리포트

```text
📍 장소 식별 결과

결론: 강원 고성군 ○○해변 — 신뢰도: 확정
주소: 강원특별자치도 고성군 ...
지도: https://place.map.kakao.com/...

근거:
- [프레임 t=03s] 흰색 아치 인도교 — ○○교 실제 사진과 일치 (블로그 A)
- [캡션] "성수기 다리 기준 오른쪽 통제" — ○○해변 운영공지와 일치
- [프레임 t=01s] 방파제 노란 등대 — ○○항 북방파제 등대

대안 후보: △△해변 (등대 색 불일치로 제외)
```

- 신뢰도·근거·반증(제외 이유)까지 명시. 추측을 확정처럼 쓰지 않는다.
- 마지막에 작업 디렉터리 정리: 후속 질문 없을 듯하면 `rm -rf <workdir>`.

## Failure modes

| 증상 | 대응 |
|---|---|
| exit 2 (바이너리 없음) | `python3 ${SKILL_DIR}/scripts/setup.py` 실행 (macOS 자동 설치, 그 외 명령 안내) |
| exit 3 (로그인 벽) | 쿠키 재시도 자동. 실패 시 사용자에게 브라우저 로그인 상태 확인 요청. 그래도 안 되면 URL 유효성(삭제/비공개)부터 의심 |
| exit 4 (다운로드/프로브 실패) | URL 오타/삭제된 게시물/비공개 계정/쿠키 추출 실패/ffprobe 실패. stderr 원문 확인 후 사용자에게 안내 |
| exit 5 (프레임 추출 실패) | 영상 파일 손상 가능성. 재다운로드 또는 `--fps` 낮춰 재시도 |
| 이미지 캐러셀 게시물 | v1 미지원 (영상만). 스크린샷 첨부 요청 |
| 단서 부족 (일반적인 실내 등) | 솔직하게 "식별 불가" + 어떤 추가 정보가 있으면 되는지 안내 |
| yt-dlp 구버전 | Instagram 추출기는 자주 깨진다. `brew upgrade yt-dlp` 후 재시도 |

## Security & Permissions

- 영상·프레임은 로컬 tmp에만 저장. 외부 업로드 없음 (`--audio` + Whisper 키 설정 시 오디오만 Groq/OpenAI 전사 API로 전송).
- Whisper 키는 `~/.config/watch/.env` 재사용 (watch 스킬과 공유). 없으면 전사 생략.
- Instagram 쿠키는 yt-dlp가 브라우저에서 직접 읽으며 디스크에 저장하지 않는다.
- 조회 전용. 팔로우/댓글/DM 자동화 절대 없음.
