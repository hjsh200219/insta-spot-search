# Harness Setup — insta-spot-search

이 리포에서 **구현을 시작하기 전에 통과해야 하는 체크리스트(SSOT)**와 **공유 모듈
레지스트리**다. 성숙도 채점 기준은 [principles.md](./principles.md), 레이어/의존 규칙은
[layer-rules.md](../design-docs/layer-rules.md), 진입점 지도는 [AGENTS.md](../../AGENTS.md).

소스 3개 스크립트(`setup.py`·`ingest.py`·`lookup.py`)와 `SKILL.md`짜리 소규모 스킬
리포다. 체크리스트도 그에 맞춰 **가볍게, 그러나 실재하는 계약만** 담는다("지도지
핸드북이 아니다").

---

## Pre-Implementation Checklist

새 기능/리팩터/버그픽스를 코드로 옮기기 **전에** 아래를 훑는다. 그룹별로.

### 구조 / 공통화

- [ ] **stdlib 전용** — 새 pip 의존성 0. 서드파티 import 금지, 매니페스트(`requirements.txt`
      등) 추가 금지. 무거운 일은 외부 바이너리 subprocess로. → [layer-rules §3](../design-docs/layer-rules.md)
- [ ] **subprocess는 리스트 인자만** — `shell=True` 절대 금지. `run()` 헬퍼 사용, glob 경로는
      `glob.escape()`. → [layer-rules §4](../design-docs/layer-rules.md)
- [ ] **exit code는 기존 계약 재사용** — `ingest.py` `0/2/3/4/5`, `setup.py` `0/2`. **새 코드
      만들지 말 것.** `die(code,msg)`로 종료하고 SKILL.md "Failure modes" 표와 매핑 유지.
- [ ] **진입점 상호 import 금지** — `setup.py`↔`ingest.py`는 서로 import 안 함. 공통화는 새
      공유 모듈로(한쪽을 라이브러리化 금지). → [layer-rules §1](../design-docs/layer-rules.md)
- [ ] **함수는 작게(<50줄)** — 한 함수가 커지면 파이프라인 단계로 쪼갠다.
- [ ] **early return** — 깊은 중첩 대신 실패/특수 케이스를 앞에서 걸러 반환한다.
- [ ] **try/except로 오류를 삼키지 말 것** — `scan_profile`/`transcribe`처럼 **의도적으로**
      best-effort인 곳만 삼키고 stderr `NOTE:`를 남긴다. 나머지는 `die()`로 드러낸다.
- [ ] **Search Before Building** — 아래 §공유 모듈 레지스트리를 **먼저** 확인한다. 이미 있는
      정규식/검증기/헬퍼를 재구현하지 않는다.

### 데이터 / 성능

- [ ] **yt-dlp/ffmpeg subprocess 중복 호출 회피** — 같은 URL/영상에 대해 다운로드·프로브를
      두 번 돌리지 않는다. 한 번 받은 `video.*`/`video.info.json`을 재사용한다.
- [ ] **추출한 메타데이터 재사용** — `info.json`의 `location`/`description`/`comments`를 다시
      네트워크로 긁지 말고 이미 로드한 `info` 딕셔너리에서 읽는다.
- [ ] **재다운로드 금지** — `--start/--end` 줌 재추출은 **이미 받은 로컬 영상**에 대해 프레임만
      다시 뽑는다(원본을 다시 내려받지 않는다). `out_dir` 재사용 시 stale `video.*`/`f_*.jpg`는
      기존 로직대로 정리한다.

### 안정성 / 보안

- [ ] **비밀정보 커밋 금지** — 리포에 `.env`·키·쿠키 파일을 넣지 않는다.
- [ ] **Whisper 키는 리포 밖** — `~/.config/watch/.env` 또는 env에서만 읽는다(`watch` 스킬과
      공유). 코드/문서에 키를 하드코딩하지 않는다. → [docs/SECURITY.md](../SECURITY.md)
- [ ] **쿠키는 디스크에 저장 안 함** — `--cookies-from-browser`로 yt-dlp가 브라우저에서 직접
      읽게 하고, 쿠키 파일을 만들거나 커밋하지 않는다.
- [ ] **프라이버시 가드레일** — 공개 장소(업소·관광지) 전용. 개인 집·직장·동선 추적, 제3자
      사적 공간 특정, 스토킹/괴롭힘 정황이면 **거부**한다. → [core-beliefs §3](../design-docs/core-beliefs.md)

### 품질 게이트

- [ ] **preflight 통과** — 배포/커밋 전:
      ```bash
      python3 skills/insta-spot-search/scripts/setup.py --check   # 기대: exit 0(무음)
      ```
- [ ] **문서-코드 정합성 검증** — 문서/경로/불변식이 코드와 어긋나지 않는지:
      ```bash
      python3 scripts/verify-docs.py                              # 기대: 전부 PASS, exit 0
      ```
      package.json이 없어 자동 훅에 걸 데가 없다. **수동으로 / [harness-gc](./gc-history.md)
      흐름에서** 돌린다. stdlib-only·exit code 계약·문서 경로 실재를 검사한다.
- [ ] **순수 함수 테스트 유지/추가** — `parse_ts`/정규식(`LOGIN_WALL_PAT`·`COOKIE_ERR_PAT`·
      `PLACE_WORD_PAT`·`REGION_PAT`·`OVERSEAS_PAT`)/`load_env_file`를 건드리면 stdlib
      `unittest`로 회귀 테스트를 추가하거나 갱신한다. → 대상 목록 [docs/QUALITY.md](../QUALITY.md)
- [ ] **exit code 바꾸면 표도 갱신** — 코드/의미 변경 시 SKILL.md "Failure modes" 표를 **같은
      커밋에서** 갱신(계약 드리프트 방지).

### 문체 / 카피

- [ ] **챗봇 보이스 금지** — 사용자/에이전트 대상 stdout·문서에 "물론이죠!", "기꺼이 도와
      드릴게요" 같은 어시스턴트 말투를 쓰지 않는다.
- [ ] **AI-slop 금지** — 불필요한 감탄·상투구·과장된 의의 부여·빈 요약을 넣지 않는다.
      상태는 `NOTE:`/`[setup]` 접두의 사실 진술로만.
- [ ] **이중언어 README 톤 유지** — README 수정 시 기존 영/한 병기 구조와 담백한 톤을 지킨다.

> **권장(미설치, 필수 아님)**: `/sh:harness-setup --infra`로 knip / coverage / husky 등
> 운영 인프라를 설치할 수 있다 — **현재 미설치**. 소스 3파일·package.json 없는 리포라
> 이들은 **선택적 미래 인프라**이지 지금의 활성 게이트가 아니다. 도입은 [principles.md]
> (./principles.md)의 "하네스 단순화 원칙"에 비추어 실익이 확인될 때만.

---

## 공유 모듈 레지스트리 (Search Before Building)

새로 만들기 전에 여기부터 본다. 이미 있는 것을 재구현하면 중복 부채가 된다.

| 자산 | 위치 | 재사용 지침 |
|------|------|-------------|
| exit code 계약 `0/2/3/4/5`(ingest), `0/2`(setup) | `ingest.py:die()`, SKILL.md 표 | 새 코드 만들지 말고 이 5개 안에서 매핑. → [layer-rules §5](../design-docs/layer-rules.md) |
| `LOGIN_WALL_PAT` | `ingest.py` 모듈 전역 | 로그인 벽/레이트리밋 판별. `download`·`scan_profile` 재사용 중 — 새 정규식 만들지 말 것 |
| `COOKIE_ERR_PAT` | `ingest.py` 모듈 전역 | 쿠키 추출 실패 판별. 쿠키 관련 오류 분기는 이걸 쓴다 |
| `PLACE_WORD_PAT`·`REGION_PAT`·`OVERSEAS_PAT` | `ingest.py` 모듈 전역 | 댓글 지명 유출 후보 필터(국내/해외). false positive 허용 설계 — 새 패턴 추가는 여기 상수에 |
| 입력 검증기 `positive_int`·`positive_float`·`nonneg_int`·`parse_ts` | `ingest.py` | argparse `type=`에 재사용. 새 수치/타임스탬프 인자는 이걸 붙인다 |
| `load_env_file(path)` | `ingest.py` | `export ` 접두·따옴표·`#` 주석 처리 포함한 .env 파서. 키 로딩은 이걸 쓴다 |
| `whisper_backend()` | `ingest.py` | Whisper 키 탐지(GROQ→OPENAI 우선순위). 전사 백엔드 선택은 이 함수로 |
| `run(cmd, **kw)` | `ingest.py` | 리스트 인자 subprocess 래퍼(capture+text). 모든 외부 호출은 이걸 통해 |
| `_brew_pkgs(missing)` | `setup.py` | 바이너리→brew 패키지 매핑(ffprobe→ffmpeg 축약). 설치 힌트는 이 매핑 위에 |
| `REQUIRED_BINARIES` | `setup.py` | 필요 바이너리 목록. 바이너리 요구사항 변경은 여기 한 곳 |
| `_reject_if_internal(url)` / `HttpsOnlyRedirectHandler` | `lookup.py` | SSRF 내부IP 차단(`getaddrinfo`+`ipaddress`) + HTTPS 전용 리다이렉트 검사. 새 조회/다운로드 로직은 이걸 재사용 |
| `TIMEOUT`·`MAX_IMAGE_BYTES` | `lookup.py` | 네트워크 타임아웃(15초)·이미지 크기 상한(15MB) 상수 |
| `die(code,msg)` (lookup) | `lookup.py` | exit `2`/`4` 종료. **주의**: `ingest.py:die()`와 별개 정의(중복 — 아래 통합 후보 (c)) |
| `_resolve_dest(out_dir,name)` | `lookup.py` | `--out-dir` 내부 confinement 검사(commonpath+realpath). `ingest.py:_resolve_created()`와 알고리즘 상이(아래 통합 후보 (d)) |

### 통합 예정 후보 (touched-when-consolidate)

감사에서 나온 알려진 중복이다. **해당 코드를 손댈 때** 여기로 합친다(그 전에 선제
리팩터하지 말 것 — 소규모 리포의 마찰만 늘린다).

- **쿠키 재시도 패턴** — `attempts = [[]]; if cookies_browser != "none": attempts.append([...])`
  이 `download()`·`scan_profile()`에 중복. 둘 중 하나를 만질 때 공유 헬퍼로 추출.
- **바이너리 체크 이중 구현** — `setup.py:_check_binaries()`와 `ingest.py:check_binaries()`가
  별개 구현(`REQUIRED_BINARIES`도 각각). 공통화 시 **새 공유 모듈**을 두 진입점이 import
  (진입점끼리 import 금지 — [layer-rules §1](../design-docs/layer-rules.md)).
- **(c) `die()` 이중 정의** — `ingest.py:86`(typed, `-> NoReturn`)과 `lookup.py:49`(untyped)가
  사실상 동일한 3줄 헬퍼를 각자 구현. 셋 중 하나를 만질 때 공유 모듈로 추출.
- **(d) 경로 봉쇄 로직 2종** — `lookup.py:153` `_resolve_dest()`(commonpath+realpath)와
  `ingest.py:213` `_resolve_created()`(part-walk+islink+realpath.startswith)가 "base 밖
  이스케이프·심링크 이탈 차단"이라는 같은 목적을 다른 알고리즘으로 구현. 한쪽만
  강화되면 방어가 갈릴 수 있어 통합 시 알고리즘도 통일할 것.

상세 부채·우선순위는 [tech-debt-tracker](../exec-plans/tech-debt-tracker.md).

---

## 상태 프로토콜

작업/검증 결과는 다음 4개 상태 중 하나로 **명시**해 보고한다:

- **DONE** — 목표 달성 + 관련 게이트 통과, 미해결 우려 없음.
- **DONE_WITH_CONCERNS** — 동작하지만 남은 리스크/부채 있음(우려 명시 + 부채 트래커 등재).
- **BLOCKED** — 외부 요인(로그인 벽·키 부재·네트워크)으로 진행 불가. 원인과 필요한 것 명시.
- **NEEDS_CONTEXT** — 요구사항/입력이 모자라 진행 전 확인 필요.

> **3회 규칙**: 같은 접근으로 3번 실패하면 멈추고 에스컬레이트한다(상태를 BLOCKED 또는
> NEEDS_CONTEXT로 전환하고 무엇을 시도했는지·무엇이 필요한지 적는다). 같은 방법을
> 반복해 컨텍스트를 태우지 않는다.

---

## 운영 인프라 (Python 적응)

`--infra` 운영 인프라를 이 리포에 맞춰 설치했다. 기본 `--infra` 는 Node/Next.js용
(knip·husky·lint-staged·vitest·`logger.ts`·`withErrorHandler`)이지만, 이 리포는
**Python 3 stdlib 전용(package.json·node·npm 없음, pip 의존성 0)** 이라 그대로 쓸 수
없다. 아래처럼 stdlib 도구로 **적응**했고, Node 전용 항목은 **의도적으로 생략**했다.

### 설치한 것 (활성 게이트)

| 항목 | 위치 | 대응하는 Node 도구 | 실행 |
|------|------|--------------------|------|
| 통합 품질 게이트 | `scripts/gc.sh` | knip+vitest 통합 러너 | `bash scripts/gc.sh` |
| 순수 함수 스모크 테스트 | `tests/test_ingest.py`·`tests/test_setup.py` | vitest | `python3 -m unittest discover -s tests` |
| git pre-commit 훅 | `.githooks/pre-commit` + `core.hooksPath=.githooks` | husky + lint-staged | 커밋 시 자동(우회: `git commit --no-verify`) |
| 실행 로그 | `docs/harness/gc-script-log.md` | CI 로그 | gc.sh가 매 실행 append |

`scripts/gc.sh` 실행 순서: **py_compile("build") → verify-docs → preflight(setup.py --check)
→ ruff(선택) → unittest → coverage(선택)**. 마지막에 PASS/FAIL 배너를 내고 하드 실패 시
exit 1. preflight의 외부 바이너리(yt-dlp/ffmpeg) 부재는 **런타임 의존이지 리포 의존이
아니므로 WARN** 으로만 처리하고 게이트를 깨지 않는다(스크립트 자체가 죽으면 FAIL).

### 선택적(설치돼 있을 때만 실행)

- **ruff** — PATH에 있으면 `ruff check`, 없으면 "skipped (optional)". **필수 의존 아님**.
- **coverage.py** — `import coverage` 성공 시 `coverage run`+`report`, 없으면 skip.
  둘 다 pip 패키지라 **없어도 게이트는 통과** 한다(stdlib-only 불변식 유지).

### 의도적으로 생략한 것 (Node 전용)

- **knip / husky / lint-staged / vitest** — package.json·node·npm이 없어 부착점 자체가
  없다. 각각 py_compile·git `core.hooksPath`·pre-commit 스크립트·`unittest`로 대체.
- **`logger.ts` / 로깅 모듈(`logging.py`) — 만들지 않음.** 이 리포는 상태·경고를
  stderr `NOTE:`/`[setup]` 접두 규약(ARCHITECTURE.md 교차 관심사 "로깅/상태")으로만
  내보내고, Simplicity-First·stdlib-only를 강제한다. 소스 3파일(`setup.py`·`ingest.py`·
  `lookup.py`)짜리 스킬에 로거 모듈을 추가하는 것은 **요청되지 않은 단일 사용
  추상화**이자 불변식 위반이므로 넣지 않는다.
  새 상태 메시지가 필요하면 기존 `NOTE:`/`[setup]` 접두 규약을 따른다.

### 이제 활성인 품질 게이트 명령

```bash
bash scripts/gc.sh                              # 통합 게이트(빌드+문서+preflight+테스트+선택도구)
python3 -m unittest discover -s tests           # 테스트만
python3 scripts/verify-docs.py                  # 문서-코드 정합성만
```
