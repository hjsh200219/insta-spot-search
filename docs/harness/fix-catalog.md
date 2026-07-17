# Harness Fix Catalog — insta-spot-search

원칙([principles.md](./principles.md)) × 점수대별 개선 행동. 채점 후 낮은 원칙을
집어 이 카탈로그에서 해당 점수대의 행동을 적용한다. 성숙도 레벨은
[maturity-framework.md](./maturity-framework.md), 부채 상세는
[../exec-plans/tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md).

## 템플릿

| 원칙 | 점수대 | 개선 행동 | 산출물/검증 |
|------|--------|-----------|-------------|
| (원칙명) | 0–1 | 존재하게 만드는 최소 조치 | 무엇이 생기면 통과인가 |
| (원칙명) | 2 | 부분 → 양호로 끌어올리는 조치 | " |
| (원칙명) | 3 | 양호 → 모범(자동화/강제) | " |

## 이 리포에 적용되는 구체 항목

| 원칙 | 점수대 | 개선 행동 | 산출물/검증 |
|------|--------|-----------|-------------|
| 6 테스트 자동화 | 0–1 | `unittest`로 `parse_ts` 테스트부터 추가(네트워크·바이너리 불필요) | `tests/test_parse_ts.py` 통과 |
| 6 테스트 자동화 | 2 | `_brew_pkgs`·`load_env_file`·정규식(`LOGIN_WALL_PAT` 등)까지 커버 확대 | 순수 함수 테스트 전체 통과 |
| 6 테스트 자동화 | 3 | exit code 계약 테스트 + CI 워크플로에 편입 | push마다 자동 실행 |
| 3 코드 컨벤션 | 2 | "no pip deps" 불변식을 자동 검사(`grep`로 서드파티 import 탐지) | QUALITY.md 게이트 4 스크립트화 |
| 4 보안 표면 | 2 | argv 키 노출(부채 c) 완화 — 헤더를 stdin/파일로 전달하도록 `transcribe()` 수정 | argv에 키 미노출 확인(`ps`) |
| 7 기술부채 | 3 | 쿠키 재시도(부채 a)·바이너리 체크(부채 b)를 `scripts/_deps.py`로 추출 | 두 스크립트가 같은 헬퍼 사용, 중복 제거 |
| 8 오류 계약 | 3 | exit code ↔ SKILL.md 실패 모드 표 일치를 리뷰 체크리스트/테스트로 강제 | 코드 변경 시 표 갱신 누락 차단 |
| 5 품질 게이트 | 2 | preflight 스모크를 CI 잡으로 편입(`setup.py --json` 파싱) | CI에서 `status:ready` 확인 |
| 10 권한 경계 | 0–1 | `.claude/settings.json` `permissions.deny`에 `.env`·`secrets/**`·Whisper 키 파일 등록 | 파일 존재 + 항목 포함 |
| 1 진입점 | 0–1 | `AGENTS.md`를 지도(링크 아웃)로 작성, 핸드북화 금지(~100줄) | 존재 + 각 docs로 링크 |

## 사용법

1. `/sh:harness-gc`(또는 수동 채점)로 12원칙을 채점한다.
2. 가장 낮은 원칙 2~3개를 고른다(회의적 평가: 증거 없으면 낮게).
3. 해당 원칙·점수대 행에서 개선 행동을 실행하고, "산출물/검증"으로 완료를 확인한다.
4. 결과를 [gc-history.md](./gc-history.md)에 기록한다.
