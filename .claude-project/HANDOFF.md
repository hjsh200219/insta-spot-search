---
created: 2026-07-20T14:03:00+09:00
project: insta-spot-search
summary: 코드 리뷰 후속 8건 수정·테스트·푸시 완료(commit 103224f), 남은 부채는 실네트워크 e2e 뿐
---

## Session Digest

스킬 스크립트(`setup.py`/`ingest.py`/`lookup.py`) 코드 리뷰에서 신규 개선 8건을 찾아
전부 수정하고 테스트(182/182 green)·품질 게이트(`scripts/gc.sh` PASS)·mypy(0 issues)
통과 후 `103224f`로 커밋·origin/main 푸시했다. 기존 기술부채 트래커 항목과 중복 없는
신규 발견만 다뤘다.

## Progress

**완료**
- setup.py: `main()` argparse 전환 — 미인식 플래그(오타/`--help`)가 installer로 폴스루하던 버그 제거(exit 2). `[setup]` 상태 메시지 stdout→stderr.
- ingest.py: `--end <= --start` 사전 거부(exit 2, 다운로드 전) / `--profile-scan` 인스타그램 소스 전용 게이트 + 핸들 percent-encoding / `fmt_ts()` H:MM:SS 지원.
- lookup.py: SSRF 필터 `is_multicast or not is_global`로 강화(CGNAT 등 비글로벌 차단) / Nominatim UA 연락처 추가.
- 테스트 7건 신규(175→182), AGENTS.md 고정 테스트 수 제거, SKILL.md `--profile-scan` 인스타 전용 명시.
- 커밋·푸시 완료(103224f), Pack Memory 3건 저장.

**미완료** — 없음(요청 범위 전부 완료).

## Next Steps

1. (선택) 릴리스 전 실네트워크·실바이너리 e2e 수동 스모크 — 다운로드/프레임/전사 종단, [QUALITY.md](../docs/QUALITY.md) 게이트 6.
2. (선택) v0.4.x 패치 태그 발행 원하면 CHANGELOG 갱신 + 태그.
3. AGENTS.md `주요 옵션` 라인에 `--profile-scan` 인스타 전용 caveat 추가 검토(SKILL.md엔 반영됨, AGENTS.md는 미반영 — surgical 판단으로 이번엔 보류).

## Blockers

- 없음. (Pack 분석 에이전트 3개는 Anthropic 세션 한도 도달로 실패 — 코드/커밋과 무관, Memory/HANDOFF는 메인 세션이 직접 작성해 보완함.)

## Watch Out

- SSRF 조건은 `is_private` 나열로 되돌리지 말 것 — CGNAT 100.64/10 등에 구멍. `ssrf-ipaddress-gotcha` 메모리 참고.
- 리뷰에서 **안 고치기로 판정**한 것: `_remove_stale`의 PathEscape 조용한 스킵(cleanup die와 의도된 비대칭), ingest의 http:// 허용(yt-dlp 소스), fetch-image SVG content-type(저위험). 재리뷰 시 재지적 말 것.
- 남은 유일 부채: 실네트워크 e2e(트래커 항목 d) — CI 부적합, 수동 스모크로만 커버.

## Files Touched

- skills/insta-spot-search/scripts/setup.py
- skills/insta-spot-search/scripts/ingest.py
- skills/insta-spot-search/scripts/lookup.py
- skills/insta-spot-search/SKILL.md
- AGENTS.md
- tests/test_setup.py, tests/test_ingest.py, tests/test_ingest_contract.py, tests/test_lookup.py
