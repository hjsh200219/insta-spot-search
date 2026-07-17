# ARCHITECTURE — insta-spot-search

릴스/쇼츠 URL 하나를 "장소 식별 리포트"로 바꾸는 **레이어 0~6 파이프라인**.
Python 3 표준 라이브러리만으로 짜인 세 CLI 스크립트(`setup.py`, `ingest.py`,
`lookup.py`)가 원료(프레임·캡션·댓글·전사·지오코드·후보 이미지)를 뽑아
`report.json`(schema v1)으로 넘기면, `SKILL.md`가 지시하는 대로 Claude가
판독→검색→검증→리포트를 수행한다. 세 CLI가 공통으로 쓰는 작은 로직(바이너리
체크·쿠키 재시도·경로 봉쇄·`die()`)은 네 번째 소스 파일 `_common.py`에 있다 —
CLI가 아니라 세 진입점이 로컬 import하는 공유 헬퍼 모듈이다(아래 "의존 방향" 참고).

핵심 경계: **Python은 결정론적 추출/조회만 하고, 무엇을 검색하고 어떻게
판단할지는 Claude가 한다.** 둘을 잇는 계약은 (1) `report.json`(schema_version 1)
/ stdout 리포트, (2) 구조화된 exit code다.

---

## 레이어 0~6 파이프라인

| # | 레이어 | 구현 위치 | 하는 일 |
|---|--------|-----------|---------|
| 0 | Setup / Preflight | `scripts/setup.py` → `cmd_check()` / `cmd_install()` / `cmd_json()`, `_status()`(`_common.missing_binaries(_common.REQUIRED_BINARIES)` 호출), `_brew_pkgs()` | `yt-dlp`/`ffmpeg`/`ffprobe` 존재 확인. 성공 시 무음(exit 0), 없으면 exit 2. macOS 자동설치(`brew install`)는 조회 전용 경계를 벗어난 host mutation이므로 `--yes` 또는 TTY `[y/N]` 동의가 있어야 실행된다 |
| 1 | Ingest / Download | `scripts/ingest.py` → `download()`, `_prepare_staging()`, `_place()` | `yt-dlp`로 영상 + `video.info.json`을 `<work_dir>/.staging/`에 받는다. 기본은 **익명 다운로드**(`--cookies-browser none`) — 로그인 벽을 만나고 **사용자가 명시적으로 브라우저를 지정했을 때만** `--cookies-from-browser`로 재시도한다. 성공 후에만 스테이징 결과를 워크스페이스로 이동(비파괴적, 아래 참고) |
| 2 | Frame Extract | `probe_duration()` → `extract_frames()` | `ffprobe`로 길이 측정 → `ffmpeg`로 스테이징 디렉터리에 프레임 추출(기본 최대 24장, 폭 1024px). `--start/--end`로 구간 고해상 재추출. `--max-frames`를 넘는 프레임은 **디스크에서도 삭제**(리포트 목록뿐 아니라 실제 파일 수도 상한) |
| 3 | Audio Transcript | `whisper_backend()` → `transcribe()` | **opt-in**(`--audio` 플래그가 있을 때만). 키가 있어도 `--audio` 없으면 추출·업로드 0회. `ffmpeg`로 mono 16k 오디오 추출 후 Groq/OpenAI 전사 API 호출 — 전송은 `curl`이 아니라 stdlib `urllib`로 하며 Bearer 키는 **HTTP 헤더로만** 전달(자식 프로세스 argv에 노출되지 않음) |
| 4 | Clue Mining | `PLACE_WORD_PAT`·`REGION_PAT`·`OVERSEAS_PAT` 필터 + `scan_profile()` | 댓글에서 지명 유출 후보를 정규식으로 필터해 좋아요순 정렬(`flagged_comments`). `--profile-scan`이면 업로더 최근 게시물 location 태그를 지역 prior로 수집 |
| 5 | Report | `_build_report()`/`_write_report()`/`_print_report()`, `write_manifest()` | `report.json`(**schema_version 1** — `source_access`/`video_path`/`work_dir_owned`/`status`/`warnings`/`audio.*` 포함) + 사람용 stdout 리포트 생성(외부 원문은 `UNTRUSTED CONTENT`로 표시). 이번 실행이 만든 파일 목록을 `.insta-spot-manifest.json`에 기록. `main()`은 이 단계 함수들을 포함해 파이프라인 전 단계를 순서대로 호출하는 26줄짜리 얇은 오케스트레이터일 뿐, 로직 자체를 갖고 있지 않다 |
| 6 | Orchestration / Search / Verify / Output | `skills/insta-spot-search/SKILL.md` (+ `scripts/lookup.py`) | Claude가 프레임 병렬 판독 → 국내/해외 분기 → 검색 레그 병렬 실행 → **`lookup.py`**(신규 stdlib 어댑터)로 Kakao/Nominatim 지오코드 + 후보 이미지 다운로드 → 교차 검증 → 신뢰도·근거 리포트. 마무리는 `ingest.py --cleanup <dir>`(매니페스트 범위 한정)로 정리 |

> 레이어 0~5는 결정론적 Python(레이어 6 안에서 호출되는 `lookup.py`도 결정론적
> 조회다). 레이어 6 **자체의 판단**(무엇을 검색하고 어떤 후보를 채택할지)만
> Claude가 SKILL.md 지시에 따라 수행하는 비결정론적 추론 단계다. Python은
> 레이어 6에 "판단하지 않은 원료"만 넘긴다(예: `flagged_comments`는 false
> positive를 허용하고 최종 판단은 Claude가 함 — `ingest.py` 주석 "False
> positives are fine — the agent judges").

---

## 워크스페이스 소유권 + 비파괴적 갱신

- **소유권 판정**: `--out-dir`를 생략(자동 tempdir)했거나, 지정한 경로가 이번
  실행 전 존재하지 않았으면 `owned=true`. 이미 존재하던 `--out-dir`를 재사용하면
  `owned=false`. `report.json.work_dir_owned`에 기록된다.
- **스테이징**: 다운로드·프레임 추출·오디오 추출은 전부 `<work_dir>/.staging/`
  안에서 일어난다. 파이프라인 전체가 성공한 뒤에만 `_place()`가 스테이징 결과를
  워크스페이스 최종 위치로 옮긴다 — 실패한 실행은 기존 `video.*`, `frames/f_*.jpg`,
  `video.notes.txt` 같은 사용자 파일을 절대 건드리지 않는다.
- **매니페스트**: 이번 실행이 만든 상대경로 목록을 `.insta-spot-manifest.json`
  (`{schema_version, owned, created:[...], work_dir}`)에 기록한다. `_place()`는
  매니페스트에 없는(=사용자가 넣어둔) 기존 파일을 덮어써야 하면 즉시 실패한다
  (해당 단계의 exit code로 die). 이전 실행은 만들었지만 이번 실행은 만들지 않은
  파일(예: 지난번엔 `--audio`, 이번엔 아님)은 `_remove_stale()`이 정리한다.
- **`--cleanup DIR`**: 대상 디렉터리에 `owned:true` 매니페스트가 있을 때만
  동작하며, 매니페스트에 적힌 파일만 삭제한다. 해석된 경로가 워크스페이스를
  벗어나거나 심볼릭 링크 경계를 넘으면, 또는 대상이 저장소 루트(`.git` 존재)·
  홈 디렉터리·`/`·빈 경로면 exit 2로 거부한다. 호출자가 넘긴 디렉터리 자체를
  재귀 삭제하는 로직은 없다(범용 `rm -rf` 없음).

---

## `report.json` 계약 (schema v1)

`ingest.py`가 쓰고 후속 단계(SKILL.md의 줌·정리 Step)가 읽는 **단일 기계 계약**.
stdout은 사람이 읽는 요약일 뿐 SSOT가 아니다. 핵심 필드:

- `schema_version` (현재 `1`)
- `source_access` — `anonymous` / `cookie-assisted` / `local` 중 하나
- `video_path` — 실제 다운로드된 컨테이너 확장자(mp4/webm/mkv…)를 반영한 절대경로.
  로컬 입력이면 원본 경로. 줌 재추출은 이 필드를 읽지 하드코딩한 `.mp4`를 가정하지 않는다
- `work_dir`, `work_dir_owned`
- `status`(`ok`/`partial`), `warnings`(비치명 실패 사유 목록 — 예: 오디오 추출 실패)
- `frames`(`{path, t}` 목록), `frame_count == len(frames)`
- `audio.{enabled, provider, uploaded, path, transcript}`
- 기존 메타데이터·댓글(`comments`/`flagged_comments`)·`profile_posts` 필드

스키마를 바꾸는 변경은 `schema_version`을 올리고 같은 커밋에서 `SKILL.md`·이
문서·테스트를 함께 갱신한다.

---

## 데이터 흐름

```
reel URL (또는 로컬 video path)
        │
        ▼
[L1] download() ──yt-dlp(기본 익명)──► .staging/video.<ext> + video.info.json
        │            (로그인벽 + 브라우저 명시 시에만 쿠키 재시도)
        ▼
[L2] probe_duration() ─ffprobe→ duration
     extract_frames()  ─ffmpeg─►  .staging/frames/f_NNN.jpg (max-frames 초과분은 삭제)
        │
        ▼
[L3] --audio 있고 whisper_backend()? ──yes──► ffmpeg→audio.m4a ──urllib(Bearer 헤더)──► Groq/OpenAI ──► transcript
        │  (--audio 없거나 키 없으면 완전히 건너뜀)
        ▼
[L4] PLACE_WORD_PAT/REGION_PAT/OVERSEAS_PAT ──► flagged_comments (좋아요순)
     scan_profile()? ──yt-dlp -J──► profile_posts (location prior)
        │
        ▼
[L5] _place()로 스테이징→워크스페이스 이동 + 매니페스트 기록
     report.json(schema v1) + stdout 리포트 (frames·caption·flagged·transcript·work_dir)
        │
        ▼  (Claude가 SKILL.md 지시로 인계받음 — report.json이 SSOT)
[L6] 프레임 Read(병렬) → 국내/해외 분기 → 검색 레그 병렬
     (크로스플랫폼 / Naver / lookup.py geocode-kakao / lookup.py geocode-nominatim
      / lookup.py fetch-image) → 교차 검증 → 최종 리포트
     끝나면 ingest.py --cleanup <work_dir> (매니페스트 범위 정리)
```

`location` 태그가 이미 있으면(게시자가 장소를 태그) 레이어 6은 검색을 생략하고
검증만 한 뒤 종료한다(SKILL.md Step 1 "jackpot — verify then done"). 줌인
재추출이 필요하면 레이어 6은 `report.json.video_path`를 읽어 `ingest.py`를
`--start/--end/--resolution`으로 재호출한다(레이어 1~2 재실행, 레이어 3~5는
스킵 조건 없음 — 동일 파이프라인 재사용).

---

## 의존 방향

- `setup.py` · `ingest.py` · `lookup.py`는 **서로 import하지 않는 독립 CLI
  진입점**이다. 셋 다 `if __name__ == "__main__"`로 실행된다. 넷째 소스 파일
  `_common.py`는 CLI가 아니라(`__main__` 블록 없음) 세 진입점이 각자
  `sys.path.insert(0, <자기 dir>)` 후 `from _common import ...`로 로컬
  import하는 공유 헬퍼 모듈이다 — `die()`/`REQUIRED_BINARIES`+
  `missing_binaries()`/`cookie_retry_attempts()`/`resolve_within()`이 여기
  있다. 세 진입점이 서로를 import하지 않는 독립성 불변식은 그대로 유지된다
  (진입점↔진입점 import는 여전히 금지 — 진입점→공유 헬퍼 import만 허용).
- 오케스트레이션 방향은 **SKILL.md → (setup.py, ingest.py, lookup.py)**
  단방향이다. SKILL.md가 Bash 블록으로 세 스크립트를 순서대로 호출하고,
  각 스크립트의 exit code/stdout(ingest는 report.json도)을 읽어 다음 행동을
  결정한다. 스크립트는 SKILL.md를 알지 못한다.
- 스크립트 간 결합은 오직 **파일시스템**을 통해서만 일어난다: `ingest.py`가
  바이너리 부재를 만나면 `check_binaries()`가 `setup.py` 경로를 안내 메시지로
  가리킨다(코드 호출이 아니라 텍스트 힌트). `lookup.py`가 저장한 후보 이미지는
  같은 워크스페이스 안에 놓여 Claude가 Read로 이어서 연다.

```
        SKILL.md  (오케스트레이터 / SSOT)
        │  Bash 호출 + exit code 판독 + report.json 파싱
        ├──────────────► setup.py    (preflight/installer, 독립)  ──┐
        ├──────────────► ingest.py   (추출 파이프라인, 독립)      ──┼─import─► _common.py (공유 헬퍼, CLI 아님)
        └──────────────► lookup.py   (geocode/이미지 조회 어댑터, 독립) ──┘
                              │
                              └─ report.json / stdout / 저장 이미지 ─► Claude (L6)
```

---

## 교차 관심사 (cross-cutting)

| 관심사 | 위치 | 계약/규약 |
|--------|------|-----------|
| 로깅/상태 | `ingest.py`·`setup.py`·`lookup.py` 전역 | 상태·경고는 stderr `NOTE:`/`[setup]`/`ERROR:` 접두로만. 성공한 preflight는 **무음**(SKILL.md가 상태줄 스팸 안 내도록) |
| 종료 코드 계약 | `ingest.py`가 쓰는 `_common.die(code,msg)` | `0` ok · `2` 바이너리 없음 / 사용법 오류 / **cleanup 경계 위반** · `3` 로그인 벽(쿠키 재시도도 실패) · `4` 다운로드·프로브 실패(timeout 포함) · `5` 프레임 추출 실패(timeout·빈 프레임 포함) 또는 워크스페이스 쓰기 실패. SKILL.md "Failure modes" 표와 1:1 매핑 |
| `lookup.py` 종료 코드 | `lookup.py`가 쓰는 `_common.die(code,msg)` | `0` ok · `2` 사용법/검증 오류(스킴·크기·MIME·경로 이스케이프) · `4` 네트워크/HTTP 실패. `ingest.py`와 별개의 작은 계약(같은 `die()` 함수를 공유하지만 각자 다른 코드 집합으로 매핑) |
| 오류 분류 | `LOGIN_WALL_PAT` / `COOKIE_ERR_PAT` (정규식) | stderr를 정규식으로 분류해 "로그인 벽 + 브라우저 명시 시에만 쿠키 재시도, 아니면 즉시 중단" 결정 |
| API 키/비밀 | `whisper_backend()` → 환경변수 또는 `~/.config/watch/.env` | GROQ/OPENAI 키는 env 또는 리포 **외부** 파일에서만 읽음. `transcribe()`가 stdlib `urllib`로 Bearer 헤더 전송 — 자식 프로세스 argv에 실리지 않음. 자세한 표면은 `docs/SECURITY.md` |
| 외부 네트워크 | `download()`(yt-dlp) · `transcribe()`(urllib→Groq/OpenAI, `--audio` opt-in 시에만) · `lookup.py`(urllib→k-skill-proxy Kakao, Nominatim, 후보 이미지) | 오디오 클립이 제3자로 나가는 것이 **유일한 opt-in 데이터 유출 표면**. 그 외는 다운로드/조회이며 SKILL.md는 더 이상 `curl`을 직접 조립하지 않는다 |
| 쿠키/인증 | `--cookies-browser`(기본 `none`) | 기본 익명 다운로드. 사용자가 명시적으로 브라우저를 지정하고 익명이 로그인 벽에 막혔을 때만 yt-dlp가 브라우저에서 직접 읽는다(디스크 미저장). `report.json.source_access`에 결과 기록 |
| 작업공간 소유권 | `read_manifest()`/`write_manifest()`/`cleanup()` | 위 "워크스페이스 소유권 + 비파괴적 갱신" 섹션 참고 |
| 경로 안전 | `glob.escape()`(`download`·`extract_frames`), `_common.resolve_within()`(경로 이스케이프·심링크 방어 — `ingest.py`의 `_remove_stale()`/`cleanup()`과 `lookup.py`의 `_resolve_dest()`가 공유), 리스트 인자 subprocess | 모든 glob은 `glob.escape(dir)`로 감싸 특수문자 경로 방어. subprocess는 전부 리스트 인자 — `shell=True` 없음 |
| 입력 검증 | `positive_int`/`positive_float`/`nonneg_int`/`parse_ts` | argparse 타입 검증기로 CLI 인자를 진입 시점에 방어. `positive_float`는 `math.isfinite()`로 `nan`/`inf`/`-inf`도 거부(R6) |
