# AGENTS.md — insta-spot-search

인스타그램 릴스/틱톡/쇼츠 홍보 영상 속 **공개 장소를 역추적**하는 Claude Code
스킬(플러그인). 영상의 프레임·캡션·댓글·나레이션 단서로 가게·해변·캠핑장·여행지를
식별한다. 이 파일은 코딩 에이전트의 **진입점/리포 지도**다 — 상세는 링크로 나간다.

## Tech Stack

- **Python 3** — 표준 라이브러리 전용(`argparse/glob/json/os/re/shutil/subprocess/sys/tempfile/platform/pathlib`). **pip 의존성 0.**
- **외부 바이너리** — `yt-dlp`(다운로드), `ffmpeg`/`ffprobe`(프레임·오디오). subprocess로 호출. `curl`(전사·조회).
- **스킬 스펙** — `skills/insta-spot-search/SKILL.md`가 오케스트레이션 SSOT(Markdown).
- **외부 서비스** — Kakao Local(k-skill-proxy 경유, 키 불필요), OSM Nominatim(키 불필요), Google Maps(링크만), Groq/OpenAI Whisper(선택적 전사).

## Commands

```bash
# preflight (바이너리 확인, 성공 시 무음 exit 0 / 없으면 exit 2)
python3 skills/insta-spot-search/scripts/setup.py --check
python3 skills/insta-spot-search/scripts/setup.py --json    # 머신 판독용 상태
python3 skills/insta-spot-search/scripts/setup.py           # 설치(macOS 자동 / 그 외 안내)

# 인제스트 (영상 → 프레임/캡션/댓글/전사/report.json)
python3 skills/insta-spot-search/scripts/ingest.py "<reel-url>" --out-dir <workdir>
python3 skills/insta-spot-search/scripts/ingest.py "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["video_path"])' <workdir>/report.json)" \
  --start 6 --end 9 --resolution 2048 --out-dir <workdir>/zoom   # 줌 재추출(video_path 사용)

# 룩업 (지오코딩/이미지 다운로드 어댑터 — stdlib curl 대체)
python3 skills/insta-spot-search/scripts/lookup.py geocode-kakao "<query>"
python3 skills/insta-spot-search/scripts/lookup.py fetch-image "<url>" --out-dir <dir>

# 품질 게이트 / 테스트 / 문서 검증
bash scripts/gc.sh                                      # 통합 게이트: py_compile→verify-docs→preflight→(ruff)→unittest→(coverage)
python3 -m unittest discover -s tests -p 'test_*.py'   # stdlib 회귀 테스트(144, 의존성 0)
python3 scripts/verify-docs.py                          # 문서-코드 정합(7체크, exit 0=PASS)
git config core.hooksPath .githooks                     # pre-commit 훅 활성화(우회: --no-verify)
```

주요 옵션: `--max-frames N` `--resolution W` `--fps F` `--comments N`
`--profile-scan N` `--audio`(전사 opt-in) `--cookies-browser none|chrome|safari|firefox|edge|brave`(기본 none)
`--cleanup <dir>`(매니페스트 파일만 정리)

## Architecture (quick-ref)

6-레이어 파이프라인: **Setup/Preflight → Ingest → Frame Extract → Audio Transcript
→ Clue Mining → Report**, 이후 **SKILL.md가 Claude의 판독/검색/검증/리포트를 지시**.
`setup.py`·`ingest.py`·`lookup.py`(지오코딩/이미지 다운로드 stdlib 어댑터) 셋 다 서로
import 없는 독립 CLI 진입점, SKILL.md가 셋을 호출.
전체 데이터 흐름·의존 방향·교차 관심사 표 → **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

## Conventions (필수)

- **stdlib 전용** — 새 pip 의존성 추가 금지(하드 불변식). 표준 라이브러리로 해결.
- **subprocess는 리스트 인자만** — `shell=True` 절대 금지(`run()` 헬퍼 사용).
- **경로는 `glob.escape()`** — 모든 glob 대상 디렉터리를 감싼다(특수문자 경로 방어).
- **구조화 exit code가 계약** — `0/2/3/4/5`(ingest), `0/2/4`(lookup), `0/2`(setup). `die(code,msg)`로 종료. SKILL.md "Failure modes" 표와 매핑 — 코드 바꾸면 표도 갱신.
- **성공은 무음** — 상태/경고는 stderr `NOTE:`/`[setup]` 접두로만. `--check` 성공 시 출력 없음.
- **비밀은 리포 밖** — 키는 env 또는 `~/.config/watch/.env`에서만 읽음. 커밋 금지.

## Guardrails (프라이버시)

- **공개 장소(업소·관광지) 홍보 콘텐츠 전용.** 개인의 집·직장·동선 추적 목적이면
  **거부**한다(SKILL.md "When NOT to use").
- 영상이 제3자의 사적 공간을 비추고 그 사람 위치를 묻는 경우, 스토킹·괴롭힘
  정황이 보이면 진행하지 않는다.
- **조회 전용** — 팔로우/댓글/DM 자동화 절대 없음.

## Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 6-레이어 파이프라인·데이터 흐름·의존 방향
- [docs/SECURITY.md](./docs/SECURITY.md) — API 키/쿠키/오디오 업로드 표면
- [docs/QUALITY.md](./docs/QUALITY.md) — 품질 게이트·테스트 대상·상태 프로토콜
- [docs/exec-plans/tech-debt-tracker.md](./docs/exec-plans/tech-debt-tracker.md) — 기술부채
- [docs/harness/](./docs/harness/) — 하네스 성숙도 원칙·프레임워크·수정 카탈로그·이력
- [docs/design-docs/core-beliefs.md](./docs/design-docs/core-beliefs.md) — 운영 신념

## LLM 코딩 행동 원칙

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding — Don't assume. Don't hide confusion. Surface tradeoffs. State assumptions explicitly; if multiple interpretations exist, present them; if simpler approach exists, say so; if unclear, stop and ask.
2. Simplicity First — Minimum code that solves the problem. No speculative features, no single-use abstractions, no unrequested configurability, no error handling for impossible scenarios. If 200 lines could be 50, rewrite it.
3. Surgical Changes — Touch only what you must. Don't improve adjacent code. Match existing style. Mention unrelated dead code but don't delete it. Remove only imports/vars/functions YOUR changes made unused.
4. Goal-Driven Execution — Transform tasks into verifiable goals (write failing test first, then make it pass). For multi-step tasks, state a plan with verify steps. Loop independently until criteria met.
