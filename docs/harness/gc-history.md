# Harness GC History — insta-spot-search

`/sh:harness-gc`(하네스 가비지 컬렉션: 성숙도 채점 + 개선 조치) 실행 이력.
채점 기준은 [principles.md](./principles.md), 레벨 산정은
[maturity-framework.md](./maturity-framework.md), 조치 카탈로그는
[fix-catalog.md](./fix-catalog.md).

| 날짜 | 성숙도 점수 | 주요 조치 | 비고 |
|------|-------------|-----------|------|
| 2026-07-17 | ≈3.0 / 4 (L3, 상단) | Run#1 baseline — v0.4.x 오버홀 후 첫 채점. Auto수정: `lookup.py:78` mypy union-attr 해소 + 문서 신선도 10파일 동기화 | 검증차원 1.0→2.8 (0-테스트 → 144-테스트). L4 게이트 = CI |

> 첫 `/sh:harness-gc` 실행이 이 표를 채운다. 각 실행은 (1) 12원칙 채점과 4-차원 가중
> 평균으로 성숙도 점수/레벨을 산출하고, (2) 가장 낮은 원칙에 fix-catalog의 조치를
> 적용한 뒤, (3) 날짜·점수·주요 조치를 한 행으로 추가한다. 회의적 평가 원칙에 따라
> 증거 없는 점수 상승은 기록하지 않는다.

---

## 2026-07-17 (Run #1)

- 모드: full
- 문서 신선도: 82% → (Auto수정 후) 신선도 이슈 해소 (10개 문서 동기화)
- 아키텍처 준수율: ≈89% (import/레이어 위반 0, 중복 4건·복잡도 1건 부채 등재)
- 품질 등급: **B+ (GPA 3.26)** — `setup.py` C+ 🔴(커버리지 28%)가 유일한 임계 미달
- 하네스 성숙도: **L3 (≈3.0/4, 상단)** — A(문서화) 3.4 / B(강제) 3.2 / C(검증) 2.8 / D(운영) 2.2
- 원칙 평균: 7.83/10 · 최약 3: **P6 테스트·커버리지(6), P10 권한경계(6), P12 문서최신성(6)**
- Knip strict: N/A (Python — stdlib-import 체크는 verify-docs가 커버)
- 발견 이슈: Auto수정 즉시 적용(mypy 1건 + 문서 10파일), 수동 검토 부채 4건 등재(a·b 중복, e·f 신규 중복, g main() 285L, h setup 28%)
- 반복 드리프트: 없음 (Run #1)
- 예방 스크립트: 기존 `verify-docs.py`(7체크) 유지 — 신규 생성 불필요
- 하네스 메타 검증: 해당 없음 (3회 미만)
- L4 승급 조건: **CI 머지전 차단 게이트** (`/sh:harness-setup --infra`, by-design 옵트인) + coverage 임계값 강제 + setup.py 커버리지 ↑
- 실행 상태: **DONE_WITH_CONCERNS** (setup.py 커버리지 🔴 — 부채 h로 등재, Manual)
