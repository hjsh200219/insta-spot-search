# 기술부채 트래커 — insta-spot-search

감사(`_workspace/00_audit.md`)에서 확인된 실재 부채. v0.4.x 배포 후 코드를 다시
대조해(2026-07-17) 상태를 갱신했다. 소규모 리포라 항목은 적지만 전부 코드
근거가 있다. 우선순위: 🔴 높음 / 🟡 중간 / 🟢 낮음.

| # | 항목 | 위치 | 영향 | 우선순위 |
|---|------|------|------|----------|
| a | 쿠키 재시도 커맨드 조립 중복 | `ingest.py` `download()` (308) · `scan_profile()` (502) | `cmd = base[:1] + ["--cookies-from-browser", cookies_browser] + base[1:]` 형태의 재시도 커맨드 조립이 두 함수에 복붙됨(로그인 벽 판정도 `download()`는 미리 계산한 `login_wall` bool, `scan_profile()`은 인라인 `LOGIN_WALL_PAT.search(...)`로 각자 씀). v0.4.x에서 재시도 트리거 조건("사용자가 명시적으로 브라우저 지정 + 로그인 벽")은 두 함수가 동일하게 통일됐지만, 커맨드 조립 코드 자체의 중복은 남아 있어 한쪽만 고치면 동작이 갈릴 수 있음 | 🟡 중간 |
| b | 바이너리 체크 이중 구현 | `setup.py` `_check_binaries()`/`REQUIRED_BINARIES`(33, 40) · `ingest.py` `check_binaries()`(122) | 필요 바이너리 목록·검사 로직이 두 파일에 별개로 존재. `yt-dlp` 필요 여부 분기까지 갈라져 드리프트 위험. v0.4.x에서도 공유 모듈 미도입 상태 그대로 | 🟡 중간 |
| d | 실네트워크 e2e 테스트 갭 (단위 자동화는 해소) | `tests/`(stdlib `unittest`, 144 케이스 — 7개 파일 + 공유 헬퍼 `_harness.py`) | **R1–R9 완료 조건 단위 자동화 해소(2026-07-17).** `test_skill_paths.py`(R1: 실제 `zsh -c`/`sh -c` 격리 셸 `SKILL_DIR` 해석), `test_cleanup.py`(R2: 소유권·`--cleanup` 경계 거부 전수), `test_lookup.py`(R3: HTTPS/리다이렉트/경로 이스케이프/이미지 MIME/크기 상한/인젝션/SSRF 내부IP/TOCTOU), `test_ingest_contract.py`(R4 쿠키·오디오 opt-in 0회 / R5 report.json schema v1 / R6 timeout·빈 프레임·`nan`·`inf` / R7 Whisper 키 헤더 전용 / R9 `--comments 0`→`--no-write-comments`), `test_ingest_hardening.py`(소유권 idempotency·null info.json·probe 유한성·staging 안전·fps clamp). 전 스위트 144/144 green, 실패 테스트 없음. `verify-docs.py`는 7체크로 확장 완료. **남은 갭은 실네트워크·실바이너리 e2e**(다운로드/프레임/전사 종단)뿐 — 본질적으로 CI 부적합이라 수동 스모크([QUALITY.md](../QUALITY.md) 게이트 6)로만 커버 | 🟢 낮음 (단위 자동화 완료, 실네트워크 e2e만 수동) |
| e | `die(code,msg)` 이중 정의 (신규) | `ingest.py:86`(typed, `-> NoReturn`) · `lookup.py:49`(untyped) | v0.4.x에서 `lookup.py`가 추가되며 사실상 동일한 3줄 exit 헬퍼가 두 진입점에 복제됨. 시그니처도 갈려(타입힌트 유무) 스타일 일관성 이슈를 겸함 | 🟢 낮음 (consolidate when touched) |
| f | 경로 봉쇄 로직 2종 — 발산형 구현 (신규) | `lookup.py:153` `_resolve_dest()`(commonpath+realpath) · `ingest.py:213` `_resolve_created()`(part-walk+islink+realpath.startswith) | "base 디렉터리 밖 이스케이프·심링크 이탈 차단"이라는 같은 보안 목적을 서로 다른 알고리즘으로 구현. 한쪽만 강화되면 방어가 갈릴 드리프트 리스크 | 🟢 낮음 (consolidate when touched) |
| g | `ingest.py:main()` 비대화 (<50줄 컨벤션 위반) | `ingest.py:575`(~285줄, 575–857) | argparse + 소유권 판정 + download + probe + frames + audio + `_place` 배치 + `_remove_stale` + report.json + stdout 리포트를 한 함수가 처리. 리포 자체 컨벤션(harness-setup.md "함수는 작게(<50줄)")을 위반. 스테이징/매니페스트 헬퍼(`_prepare_staging`/`_place`/`_remove_stale` 등)는 이미 적정 크기로 분리됐으나 `main()` 자체는 파이프라인 단계 함수로 상위 분해가 안 됨 | 🟡 중간 (decompose into per-stage functions — Manual) |
| h | `setup.py` 테스트 커버리지 낮음 (~28%) | `setup.py`(`_install_macos`/`_hint_linux`/`_hint_windows`/`cmd_install`) | host-mutating(brew install) + 동의 게이트 분기가 실측 커버리지 28%로 사실상 미검증. 코드 자체는 깨끗하나 "동작한다"만 알 뿐 "잘 동작한다"를 증명하지 못함 | 🟢/🟡 (add consent-gate + install-path tests — Manual) |

## 해소된 항목 (RESOLVED)

| # | 항목 | 해소 내용 |
|---|------|-----------|
| c | Whisper API 키 argv 노출 | ~~`curl -H "Authorization: Bearer {key}"`로 키를 자식 프로세스 argv에 실어 `ps`/`/proc`에서 노출 가능~~ → **v0.4.x에서 해소.** `transcribe()`가 `curl` 자식 프로세스를 없애고 stdlib `urllib.request`로 직접 HTTP POST하며, Bearer 키는 `req.add_header("Authorization", "Bearer " + key)`로 **HTTP 헤더에만** 실린다. 저장소 전체에서 `Authorization`/`Bearer` 문자열은 이 `add_header` 호출부와 그 설명 docstring에만 나타나고, 어떤 subprocess argv 리스트에도 나타나지 않는다(grep으로 확인). 실패 메시지도 `_scrub()`으로 키를 마스킹한 짧은 본문만 남긴다. 상세: [docs/SECURITY.md](../SECURITY.md#whisper-자격증명-argv-노출--해결됨) |

## 해소 방향 (제안)

- **a, b 함께**: `ingest.py`·`setup.py`·`lookup.py`가 공유할 수 있는 작은 헬퍼(예:
  `scripts/_deps.py` — `REQUIRED_BINARIES`, `missing_binaries()`, `cookie_retry_cmd()`)를
  두고 필요한 쪽에서 import. 단, **stdlib 전용/외부 의존 0 불변식은 유지**(내부 모듈이므로 OK).
  세 스크립트가 지금은 서로 import하지 않는 독립 진입점이라(→ [ARCHITECTURE.md](../../ARCHITECTURE.md)),
  공유 모듈 도입은 그 독립성을 깨지 않는 선(같은 `scripts/` 내 로컬 import)에서.
- **c**: DONE — 위 "해소된 항목" 참고. 추가 조치 불필요.
- **d (단위 자동화 DONE)**: R1–R9 완료 조건은 `test_ingest_contract.py`·
  `test_ingest_hardening.py`·`test_cleanup.py`·`test_lookup.py`·`test_skill_paths.py`로
  전부 커버됐고(144/144 green), `verify-docs.py`도 7체크로 확장 완료. 추가 조치 불필요.
  남은 것은 실네트워크·실바이너리 종단(e2e)뿐이며 CI 부적합이라 릴리스 전 수동 스모크
  ([QUALITY.md](../QUALITY.md) 게이트 6)로만 커버한다.
- **e, f**: 위 a·b와 같은 결로, **해당 코드를 손댈 때** 공유 모듈로 통합(예:
  `die()`는 `_deps.py`에, 경로 봉쇄는 알고리즘을 통일한 뒤 공유 헬퍼로). 선제 리팩터는
  하지 않는다 — [harness-setup.md](../harness/harness-setup.md) 통합 예정 후보 (c)·(d) 참고.
  **미해소.**
- **g, h**: 미해소(Manual). g는 `ingest.py:main()`을 파이프라인 단계 함수(download-stage/
  frame-stage/audio-stage/report-stage)로 분해해야 하고, h는 `setup.py`의 설치/힌트
  분기를 subprocess/platform 목킹 테스트로 커버해야 한다. 둘 다 이 GC 사이클에서 **조치하지
  않았다** — 다음 작업에서 손댈 때 처리.

## 참고 (부채 아님 — 관찰 항목)

- `LOGIN_WALL_PAT`은 `download()`·`scan_profile()` 양쪽에서 쓰이지만 이미 모듈 전역
  상수라 중복이 아니다(공유 정상).
- `setup.py`의 `_hint_linux`/`_hint_windows`가 `_brew_pkgs` 위에서 유사 분기를
  반복하나, 플랫폼별 문구가 달라 무리한 통합은 가독성을 해칠 수 있어 보류.
- `mypy --check-untyped-defs`는 `setup.py`/`ingest.py`/`lookup.py` 3파일 모두
  0 issues(2026-07-17 재확인) — R9의 mypy 완료 조건은 충족 상태.
