# Harness Maturity Framework — insta-spot-search

하네스 성숙도를 L1~L5로 매기는 프레임워크. 채점 기준은 [principles.md](./principles.md),
점수대별 개선 행동은 [fix-catalog.md](./fix-catalog.md).

## 4-차원 가중 평균

성숙도는 아래 4개 차원의 점수(0~4)를 가중 평균해 산출한다. 소규모 스킬 리포라
"운영 인프라"의 가중치를 낮춰 문서/검증에 무게를 둔다.

| 차원 | 가중치 | 이 리포에서 측정 대상 |
|------|--------|------------------------|
| 문서화 | 0.30 | `AGENTS.md`·`ARCHITECTURE.md`·`SECURITY.md`·core-beliefs가 코드 근거로 존재하고 지도 역할을 하는가 |
| 아키텍처 강제 | 0.25 | stdlib 전용·subprocess 안전·exit code 계약·프라이버시 가드레일이 문서로 강제되고 코드와 일치하는가 |
| 검증 자동화 | 0.30 | preflight 스모크 + 순수 함수 단위 테스트 + exit code 계약 검증의 자동화 정도 |
| 운영 인프라 | 0.15 | `.claude/settings.json` 권한 경계, CI, 릴리스 절차의 유무 |

가중 평균 점수 → 레벨 매핑: **L1** 0.0–0.9 · **L2** 1.0–1.9 · **L3** 2.0–2.9 ·
**L4** 3.0–3.5 · **L5** 3.6–4.0.

## 레벨 정의 (앵커)

### L1 — Ad-hoc (초기)
문서가 코드에만 암묵적으로 존재. 진입점/아키텍처 문서 없음. 테스트 0개. 권한 경계 없음.
새 기여자/에이전트가 파이프라인을 알려면 소스 전량을 읽어야 함.

### L2 — Documented (문서화)
`AGENTS.md`·`ARCHITECTURE.md`가 존재하고 레이어/데이터흐름/컨벤션/가드레일이 코드 근거로
기술됨. 보안 표면이 `SECURITY.md`에 집약. 권한 경계(`.claude/settings.json`) 설정. 다만
검증은 **preflight 스모크(수동)에 의존**하고 자동 단위 테스트는 아직 없음.

### L3 — Verified (검증)
순수 함수(`parse_ts`·`_brew_pkgs`·`load_env_file`·정규식) 단위 테스트와 exit code 계약
테스트가 실재하고 통과. "no pip deps" 불변식이 자동 검사됨. 부채가 트래커에서 능동 관리됨.

### L4 — Enforced (강제)
검증이 CI로 자동 실행되어 회귀가 머지 전에 차단됨. 문서-코드 계약(SKILL.md 실패 모드 표
↔ exit code)이 자동 또는 리뷰 체크리스트로 강제됨. tech-debt 항목 a/b/c가 해소됨.

### L5 — Self-improving (자기개선)
하네스가 주기적으로 재검증되어(단순화 원칙) 불필요한 규칙을 걷어내고, `harness-gc`
이력이 성숙도 추세를 추적하며, 새 리스크가 나타나면 게이트가 선제적으로 추가됨.

## 현재 상태

**L3 (Verified, 상단) — L3→L4 전환 중.** v0.4.x 하네스 오버홀로 검증 자동화 차원이
자동 테스트 0개에서 `tests/`의 stdlib `unittest` 144케이스(7개 파일 + 공유 헬퍼
`tests/_harness.py`)로 올라섰고, `scripts/verify-docs.py`(7체크)와 `scripts/gc.sh`
(syntax→docs→preflight→tests→coverage 통합 게이트, `.githooks/pre-commit` 연동)가
상시 실행된다. 순수 함수·exit code 계약·`--cleanup`/`lookup.py` 경계 테스트가 전부
자동 검증되며(부채 항목 d 중 단위 자동화분 해소), 문서화·아키텍처 강제 차원은 이미
L2를 넘어선 상태다. L4로 올라가려면 남은 게이트는 **CI 자동 실행**(회귀가 머지 전에
차단되는 것)뿐이다 — `.githooks/pre-commit`은 로컬 훅이라 `--no-verify`로 우회 가능
하다(tech-debt-tracker 항목 a/b도 미해소). 실측 점수는 [gc-history.md](./gc-history.md)에
기록한다.
