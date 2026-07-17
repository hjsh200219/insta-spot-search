# 기술부채 트래커 — insta-spot-search

감사(`_workspace/00_audit.md`)에서 확인된 실재 부채. v0.4.x 배포 후 코드를 다시
대조해(2026-07-17) 상태를 갱신했다. 소규모 리포라 항목은 적지만 전부 코드
근거가 있다. 우선순위: 🔴 높음 / 🟡 중간 / 🟢 낮음.

| # | 항목 | 위치 | 영향 | 우선순위 |
|---|------|------|------|----------|
| d | 실네트워크 e2e 테스트 갭 (단위 자동화는 해소) | `tests/`(stdlib `unittest`, 175 케이스 — 7개 파일 + 공유 헬퍼 `_harness.py`) | **R1–R9 완료 조건 단위 자동화 해소(2026-07-17).** `test_skill_paths.py`(R1: 실제 `zsh -c`/`sh -c` 격리 셸 `SKILL_DIR` 해석), `test_cleanup.py`(R2: 소유권·`--cleanup` 경계 거부 전수), `test_lookup.py`(R3: HTTPS/리다이렉트/경로 이스케이프/이미지 MIME/크기 상한/인젝션/SSRF 내부IP/TOCTOU), `test_ingest_contract.py`(R4 쿠키·오디오 opt-in 0회 / R5 report.json schema v1 / R6 timeout·빈 프레임·`nan`·`inf` / R7 Whisper 키 헤더 전용 / R9 `--comments 0`→`--no-write-comments`), `test_ingest_hardening.py`(소유권 idempotency·null info.json·probe 유한성·staging 안전·fps clamp). 전 스위트 175/175 green, 실패 테스트 없음. `verify-docs.py`는 7체크로 확장 완료. **남은 갭은 실네트워크·실바이너리 e2e**(다운로드/프레임/전사 종단)뿐 — 본질적으로 CI 부적합이라 수동 스모크([QUALITY.md](../QUALITY.md) 게이트 6)로만 커버 | 🟢 낮음 (단위 자동화 완료, 실네트워크 e2e만 수동) |

## 해소된 항목 (RESOLVED)

| # | 항목 | 해소 내용 |
|---|------|-----------|
| a | 쿠키 재시도 커맨드 조립 중복 | ~~`cmd = base[:1] + ["--cookies-from-browser", cookies_browser] + base[1:]` 형태의 재시도 커맨드 조립이 `download()`(308)·`scan_profile()`(502)에 복붙됨~~ → **해소.** 새 공유 헬퍼 `scripts/_common.py:cookie_retry_attempts(cookies_browser)`(48–58)가 재시도 사다리를 `[[]]`(쿠키 비활성) 또는 `[[], ["--cookies-from-browser", browser]]`로 반환한다. `ingest.py:download()`(295 부근)와 `ingest.py:scan_profile()`(490 부근) 둘 다 이 함수 하나를 호출해 `attempts[1]`을 그대로 splice — 커맨드 조립 로직이 이제 한 곳에만 있다. |
| b | 바이너리 체크 이중 구현 | ~~필요 바이너리 목록·검사 로직이 `setup.py`/`ingest.py`에 별개로 존재~~ → **해소.** `scripts/_common.py`의 `REQUIRED_BINARIES`(31)와 `missing_binaries(binaries)`(40–45)로 단일화. `setup.py:_status()`(101)·`cmd_install()`(129, 140)이 `missing_binaries(REQUIRED_BINARIES)`를 쓰고, `ingest.py:check_binaries()`(129–137)는 URL 소스 여부에 따라 자기 리스트(`yt-dlp` 필요 여부만 분기)를 조립한 뒤 같은 `missing_binaries()`를 호출한다 — `shutil.which` 순회 로직 자체는 한 곳. |
| c | Whisper API 키 argv 노출 | ~~`curl -H "Authorization: Bearer {key}"`로 키를 자식 프로세스 argv에 실어 `ps`/`/proc`에서 노출 가능~~ → **v0.4.x에서 해소.** `transcribe()`가 `curl` 자식 프로세스를 없애고 stdlib `urllib.request`로 직접 HTTP POST하며, Bearer 키는 `req.add_header("Authorization", "Bearer " + key)`로 **HTTP 헤더에만** 실린다. 저장소 전체에서 `Authorization`/`Bearer` 문자열은 이 `add_header` 호출부와 그 설명 docstring에만 나타나고, 어떤 subprocess argv 리스트에도 나타나지 않는다(grep으로 확인). 실패 메시지도 `_scrub()`으로 키를 마스킹한 짧은 본문만 남긴다. 상세: [docs/SECURITY.md](../SECURITY.md#whisper-자격증명-argv-노출--해결됨) |
| e | `die(code,msg)` 이중 정의 | ~~`ingest.py:86`(typed, `-> NoReturn`) · `lookup.py:49`(untyped)에 사실상 동일한 3줄 exit 헬퍼가 복제됨~~ → **해소.** `scripts/_common.py:die(code, msg)`(34–37) 하나로 통합. `ingest.py`(43번째 줄에서 import)와 `lookup.py`(33번째 줄에서 import) 모두 자체 정의를 지우고 `from _common import die`로 재사용한다. 시그니처 드리프트(타입힌트 유무) 문제도 함께 해소. |
| f | 경로 봉쇄 로직 2종 — 발산형 구현 | ~~`lookup.py:153` `_resolve_dest()`(commonpath+realpath) · `ingest.py:213` `_resolve_created()`(part-walk+islink+realpath.startswith)가 같은 목적을 다른 알고리즘으로 구현~~ → **해소.** `scripts/_common.py:resolve_within(base, target)`(67–97)가 두 알고리즘을 하나로 통일 — 절대/빈/`.`/`..` 컴포넌트 거부, 중간 컴포넌트별 `islink` 워크, 최종 realpath containment까지 두 원본 구현보다 엄격한 상위집합으로 재구현했다. `lookup.py:_resolve_dest()`(153–164)는 이제 이 함수에 위임하는 얇은 wrapper이고, `ingest.py`의 `_remove_stale()`(198)·`cleanup()`(241)도 직접 `resolve_within()`을 호출한다 — 경로 봉쇄 알고리즘은 이제 하나뿐이다. |
| g | `ingest.py:main()` 비대화 (<50줄 컨벤션 위반) | ~~`ingest.py:575`(~285줄, 575–857)가 argparse + 소유권 판정 + download + probe + frames + audio + 배치 + report.json + stdout 리포트를 한 함수에서 처리~~ → **해소.** `main()`이 935–960의 **26줄**로 축소됐다. argparse(`_parse_args`, 616)·워크스페이스 판정(`_resolve_workspace`, 649)·소스 획득(`_acquire_source`, 679)·프레임 추출(`_extract_stage`, 713)·오디오(`_audio_stage`, 722)·아티팩트 배치(`_place_artifacts`, 769)·리포트 구성/기록/출력(`_build_report` 812 / `_write_report` 869 / `_print_report` 882)으로 파이프라인 단계별 함수 분해 + 단계 간 전달값을 타입화한 `Workspace`/`Source`/`Audio`/`Artifacts` dataclass(579–615)를 도입했다. `main()`은 이 헬퍼들을 순서대로 호출하는 얇은 오케스트레이터가 됐다. |
| h | `setup.py` 테스트 커버리지 낮음 (~28%) | ~~host-mutating(brew install) + 동의 게이트 분기가 실측 커버리지 28%로 사실상 미검증~~ → **해소.** `tests/test_setup.py`(464줄, 39개 테스트 — 기존 8개 순수함수 테스트에 31개 추가)가 `TestInstallMacos`(brew 유무/성공/실패/argv 조립)·`TestConsentGate`(TTY 승인/거부/EOF, non-TTY 거부, `--yes` 스킵)·`TestHints`(Linux/Windows 힌트 분기)·`TestCmdCheck`/`TestCmdJson`/`TestCmdInstall`/`TestMainDispatch`를 전부 `unittest.mock.patch`로 목킹해 커버한다. 실측 커버리지 28%→**99%**(`coverage run` 재확인 — 107 statements 중 미커버 1줄은 `if __name__ == "__main__":` 가드뿐). subprocess 호출은 전부 patch돼 있어 동의 없이 실제 `brew install`이 실행되지 않음을 각 테스트가 assert한다. |

## 해소 방향 (제안)

- **a, b**: DONE — 위 "해소된 항목" 참고. `scripts/_common.py`의 `cookie_retry_attempts()`/
  `REQUIRED_BINARIES`+`missing_binaries()`로 통합됐고, 세 스크립트는 여전히 서로 import하지
  않는 독립 진입점이다(→ [ARCHITECTURE.md](../../ARCHITECTURE.md)) — `_common.py`는 셋이
  공통으로 import하는 로컬 헬퍼 모듈일 뿐 진입점이 아니므로 독립성 불변식은 유지된다.
  추가 조치 불필요.
- **c**: DONE — 위 "해소된 항목" 참고. 추가 조치 불필요.
- **d (단위 자동화 DONE)**: R1–R9 완료 조건은 `test_ingest_contract.py`·
  `test_ingest_hardening.py`·`test_cleanup.py`·`test_lookup.py`·`test_skill_paths.py`로
  전부 커버됐고(175/175 green), `verify-docs.py`도 7체크로 확장 완료. 추가 조치 불필요.
  남은 것은 실네트워크·실바이너리 종단(e2e)뿐이며 CI 부적합이라 릴리스 전 수동 스모크
  ([QUALITY.md](../QUALITY.md) 게이트 6)로만 커버한다. **유일하게 남은 미해소 항목.**
- **e, f**: DONE — 위 "해소된 항목" 참고. `_common.py:die()`와 `_common.py:resolve_within()`로
  통합됐다. 추가 조치 불필요.
- **g, h**: DONE — 위 "해소된 항목" 참고. g는 `ingest.py:main()`을 파이프라인 단계 함수로
  분해했고(26줄), h는 `setup.py` 설치/동의/힌트 분기를 subprocess/platform 목킹 테스트로
  커버해 실측 커버리지 99%를 달성했다. 추가 조치 불필요.

## 참고 (부채 아님 — 관찰 항목)

- `LOGIN_WALL_PAT`은 `download()`·`scan_profile()` 양쪽에서 쓰이지만 이미 모듈 전역
  상수라 중복이 아니다(공유 정상).
- `setup.py`의 `_hint_linux`/`_hint_windows`가 `_brew_pkgs` 위에서 유사 분기를
  반복하나, 플랫폼별 문구가 달라 무리한 통합은 가독성을 해칠 수 있어 보류.
- `mypy --check-untyped-defs`는 `setup.py`/`ingest.py`/`lookup.py`/`_common.py` 4파일
  모두 0 issues(2026-07-17 재확인) — R9의 mypy 완료 조건은 충족 상태.
