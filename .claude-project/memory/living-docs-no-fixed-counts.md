---
name: living-docs-no-fixed-counts
description: 살아있는 문서(AGENTS.md 등)에는 테스트 수 같은 고정 숫자를 넣지 않는다 — 드리프트 방지
type: project
created: 2026-07-20
---

AGENTS.md에 하드코딩됐던 테스트 개수(144)가 실제(175→182)와 어긋나 있었다. 채택한 수정: **살아있는 문서에서는 고정 카운트를 제거**하고, 날짜가 박힌 스냅샷 문서(tech-debt-tracker, PRD)만 고정 숫자를 유지한다.

**Why:** 계속 갱신되는 문서에 검증 없이 늘어나는 숫자를 박아두면 코드와 반드시 어긋난다(anti-drift). 스냅샷 문서는 "그 시점 사실"이므로 고정 숫자가 정당하다.
**How to apply:** AGENTS.md·README·SKILL.md 같은 living doc을 편집할 때 "테스트 N개", "체크 M건" 같은 카운트는 넣지 말고 서술로 대체한다. 고정 숫자가 필요하면 날짜 스냅샷 문서에만 둔다.
