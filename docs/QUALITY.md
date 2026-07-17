# QUALITY — insta-spot-search

이 리포는 소스 5파일(독립 CLI 진입점 `setup.py`·`ingest.py`·`lookup.py`, 셋이
로컬 import하는 공유 헬퍼 `_common.py`, 오케스트레이터 `SKILL.md`)의 소규모
스킬이다. 품질 게이트도 그에 맞춰 **가볍게, 그러나 실재하는 계약을 검증**하는
데 집중한다.

## 게이트 1 — Preflight 스모크 (필수)

가장 값싼 게이트. 바이너리 계약이 살아있는지 확인한다.

```bash
python3 skills/insta-spot-search/scripts/setup.py --check   # 기대: exit 0(무음)
python3 skills/insta-spot-search/scripts/setup.py --json     # 기대: {"status":"ready",...}
```

- exit 0 + 무출력 = 통과. exit 2 = 바이너리 없음(설치 필요).
- `--json`은 `status`/`missing_binaries`/`platform` 필드를 반환 — CI/에이전트 판독용.

## 게이트 2 — stdlib `unittest` 회귀 (구현됨)

`tests/`에 7개 테스트 파일 + 공유 헬퍼 `tests/_harness.py`가 있다. 정확한 케이스
수는 `python3 -m unittest discover -s tests`로 직접 확인 — 이 문서 기준
**175 케이스, 전부 통과**. R1~R9 완료 조건마다 최소 1개 회귀 테스트가 매핑된다.

| 파일 | 커버 | R-매핑 |
|------|------|--------|
| `test_ingest.py` | `parse_ts`, `positive_int`/`positive_float`/`nonneg_int`(경계값 0/음수), `load_env_file`, `fmt_ts`, `LOGIN_WALL_PAT`/`COOKIE_ERR_PAT`/`PLACE_WORD_PAT`/`REGION_PAT`/`OVERSEAS_PAT` | 순수 함수 회귀 |
| `test_setup.py` | `_brew_pkgs`(중복 축약·순서 보존·빈 입력), `_status()` shape + **동의 게이트**(TTY 승인/거부/EOF, non-TTY 거부, `--yes` 스킵)·**brew 설치 분기**(brew 없음/성공/실패/argv 조립)·**플랫폼 힌트**(Linux/Windows)·`cmd_check`/`cmd_json`/`cmd_install`/`main()` 디스패치를 전부 `unittest.mock.patch`로 목킹(39개 테스트, `setup.py` 실측 커버리지 28%→**99%**) | 순수 함수 회귀 + 설치/동의 게이트 회귀 |
| `test_skill_paths.py` | SKILL.md의 두 줄 리졸버를 **실제 `zsh -c`/`sh -c` 서브프로세스**로 실행해 `$SKILL_DIR`가 격리 셸에서도 올바르게 해석되는지(공백·대괄호 포함 경로, `CLAUDE_SKILL_DIR` 폴백 포함) + 모든 bash 블록이 `$SKILL_DIR` 재정의를 갖는지 정적 검사 | **R1** |
| `test_cleanup.py` | `cleanup()` 해피패스(매니페스트 파일만 삭제, 비목록 파일 보존) + 거부 케이스(빈 경로, 존재하지 않는 dir, 매니페스트 없음/`owned:false`, `created` 리스트 malformed, 파일시스템 루트, 홈 디렉터리, 저장소 루트, 워크스페이스 이스케이프, 절대경로 항목, 심링크 경계) | **R2** |
| `test_lookup.py` | HTTPS 전용 스킴 검사, 리다이렉트 스킴 거부(`HttpsOnlyRedirectHandler`), 경로 이스케이프/절대경로/`..`/구분자 포함 파일명 거부, `--out-dir` 내부 confinement, 비-image Content-Type 거부, 크기 상한 초과 거부(쓰기 전에 실패), 성공 케이스, `User-Agent` 전송, 선행 `-`/셸 메타문자/개행이 URL 값으로만 들어가는 인젝션 방어, Kakao/Nominatim HTTPS+베이스URL | **R3** |
| `test_ingest_contract.py` | `_harness.py`의 `FakeProc`/`FakeUrlopen`로 네트워크 없이 `main()` 전체를 구동해: 쿠키 기본 `none`+오디오 opt-in(0회 네트워크/업로드)·`source_access`, report.json schema v1(필수 키·동적 `video_path`·`frame_count`·`status=partial`+`warnings`), timeout 매핑(download/probe→4, frame→5, audio→partial)·빈 프레임→5·`nan`/`inf`/`-inf` 거부·`--max-frames` 디스크 상한, Whisper 키가 `urllib` 헤더에만 존재(argv/stdout/report 평문 0), `--comments 0`→`--no-write-comments` | **R4·R5·R6·R7·R9** |
| `test_ingest_hardening.py` | 소유권(`owned:true`) idempotency, null/손상 `info.json` 가드, `probe_duration` 유한성 검사(nan/inf 거부), 소유하지 않은 디렉터리에 대한 staging 안전성, `--fps` 상한 clamp | **R2·R5·R6** |

stdlib `unittest`로 충분(의존성 추가 금지 불변식 유지). `tests/_harness.py`는
discover 대상이 아닌 공유 헬퍼로, `ingest.py`의 `subprocess.run`/`urllib`을
가짜(`FakeProc`/`FakeUrlopen`)로, `lookup.py` 전송 계층을 가짜 opener로 대체해
네트워크·실제 키·실제 쿠키 없이 `run_ingest()`/`run_lookup()`으로 전체 경로를
구동한다.

```bash
python3 -m unittest discover -s tests -p 'test_*.py'   # 기대: Ran 175 tests ... OK
```

- 잔여 갭: URL 다운로드/프레임/전사의 **실 네트워크·실 바이너리 종단(e2e)**은
  단위 테스트 대상이 아니다(게이트 6 수동 스모크로 커버). 추적:
  [tech-debt-tracker.md](./exec-plans/tech-debt-tracker.md) 항목 (d).

## 게이트 3 — 문서-코드 정합 검증 (`verify-docs.py`)

```bash
python3 scripts/verify-docs.py   # 기대: RESULT: PASS, exit 0
```

7개 체크를 수행한다:

1. `setup.py`/`ingest.py`/`SKILL.md` 경로 존재
2. `ingest.py`/`setup.py`/`lookup.py` 세 파일 전부의 import가 stdlib뿐인지(서드파티·상호
   entrypoint import 금지). `_common`은 세 진입점이 로컬 import하는 공유 헬퍼로 명시
   허용(서드파티 아님)
3. `ingest.py`가 `die()`/`sys.exit()`로 exit code `2`/`3`/`4`/`5`를, `lookup.py`가 `2`/`4`를 여전히 참조하는지(exit 0은 `lookup.py` 독스트링에 "0 ok" 문구가 있는지로 확인) — 텍스트/AST 매칭이며 실제 분기 도달 여부까지 검증하진 않는다
4. `AGENTS.md`/`ARCHITECTURE.md`/`README.md`/`SKILL.md`/`docs/**/*.md`의 저장소 내부 상대링크가 실제로 존재하는 파일을 가리키는지(코드 펜스 내부는 제외)
5. `scripts/*.py` + `skills/**/*.py` 전체에 `shell=True` 패턴이 없는지
6. SKILL.md의 bash 펜스 안이나 Python 코드에 **실행되는** `rm -rf`가 없는지(주석/설명 문구는 예외 — 이 문서의 "범용 `rm -rf`" 언급 자체는 위반이 아니다)
7. `["-H", "Authorization: Bearer ..."]` 형태로 Bearer 키가 자식 프로세스 argv에 실리는 패턴이 없는지(urllib 헤더 dict는 예외)

`lookup.py`도 exit-code 체크(3번)의 대상이며, `verify-docs.py` 자기 자신은
5~7번 grep 스캔에서 스스로를 제외한다(패턴 리터럴을 코드로 갖고 있으므로).

## 게이트 4 — 불변식: "no pip deps"

```bash
# import된 모듈이 전부 표준 라이브러리인지 육안/grep 확인 (requirements.txt 등 없어야 함)
grep -REn "^\s*(import|from) " skills/insta-spot-search/scripts/
```

- 서드파티 import가 등장하면 **즉시 실패**로 간주한다(stdlib 전용은 하드 불변식).
  `lookup.py`도 `argparse`/`json`/`os`/`sys`/`urllib.*`만 사용해 이 불변식을 지킨다.
  공유 헬퍼 `_common.py`도 `os`/`shutil`/`sys`/`typing`만 사용하는 stdlib-only 모듈이다
  (진입점 3개가 로컬 import하는 대상이므로 이 불변식이 그대로 전파돼야 한다).
- `pyproject.toml`/`requirements.txt`/`setup.cfg` 같은 의존성 매니페스트가 없어야 한다.

## 게이트 5 — 통합 하네스 게이트 (`scripts/gc.sh`)

Node 없는 저장소에 맞춘 `gc.sh` 6단계 통합 게이트:

```bash
bash scripts/gc.sh
```

1. **syntax** — `python3 -m py_compile`로 `ingest.py`/`lookup.py`/`setup.py`/`_common.py`/`verify-docs.py`/`tests/*.py` 컴파일 확인(필수, 실패 시 HARD FAIL)
2. **docs verify** — `python3 scripts/verify-docs.py`(위 게이트 3, 필수)
3. **preflight** — `setup.py --check`(바이너리 부재는 WARN — 리포 품질 실패 아님, 스크립트 자체 오류만 FAIL)
4. **lint(optional)** — `ruff`가 설치돼 있으면 실행, 없으면 SKIP
5. **tests** — `python3 -m unittest discover -s tests -p 'test_*.py'`(필수, 게이트 2)
6. **coverage(optional)** — `coverage.py`가 설치돼 있으면 실행, 없으면 SKIP

필수 단계(1/2/5) 중 하나라도 실패하면 전체 exit 1. 실행 결과는
`docs/harness/gc-script-log.md`에 append된다. 1단계 `PY_TARGETS`는
`INGEST`/`LOOKUP`/`SETUP`/`COMMON`/`VERIFY` + `tests/*.py`를 모두 포함하므로
`lookup.py`/`_common.py`의 문법 오류도 gc.sh 1단계가 직접 잡는다.

## 게이트 6 — 수동 스모크 (샘플 URL/로컬 영상)

CI로 돌리기 어려운(네트워크·쿠키 의존) 종단 확인. 릴리스 전 1회.

```bash
python3 skills/insta-spot-search/scripts/ingest.py "<공개 릴스 URL>" --out-dir /tmp/iss-smoke
python3 skills/insta-spot-search/scripts/ingest.py --cleanup /tmp/iss-smoke
```

- 기대: `report.json`(schema_version 1) 생성, `frames/f_*.jpg` 존재,
  `.insta-spot-manifest.json` 생성, stdout에 "INGEST REPORT" 블록.
- 로그인 벽/삭제 게시물은 exit 3/4로 **깔끔히** 실패하는지(스택트레이스 아님) 확인.
- `--cleanup`이 매니페스트에 없는 파일(`.git`이 있는 디렉터리, 홈 디렉터리,
  `/`, 빈 경로)을 대상으로 하면 exit 2로 거부하는지 수동 확인.
- 로컬 영상 경로로도 실행해 네트워크 없이 프레임 추출 경로를 확인할 수 있다.

## 상태 프로토콜

작업/검증 결과 보고는 다음 4개 상태 중 하나로 명시한다:

- **DONE** — 목표 달성 + 관련 게이트 통과, 미해결 우려 없음.
- **DONE_WITH_CONCERNS** — 동작하지만 남은 리스크/부채 있음(우려를 명시하고 부채 트래커에 등재).
- **BLOCKED** — 외부 요인(로그인 벽·키 부재·네트워크)으로 진행 불가. 차단 원인과 필요한 것을 명시.
- **NEEDS_CONTEXT** — 요구사항/입력이 모자라 진행 전 확인 필요.
