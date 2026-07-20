---
name: ssrf-ipaddress-gotcha
description: Python ipaddress의 is_private만으로는 SSRF 차단 불충분 — is_multicast or not is_global 사용
type: project
created: 2026-07-20
---

lookup.py의 SSRF 방어(`_reject_if_internal`)에서 얻은 라이브 프로빙 결과:

- `ip.is_private`는 CGNAT 대역 `100.64.0.0/10`을 놓친다 (is_private=False **그리고** is_global=False).
- 전역 스코프 IPv6 멀티캐스트 `ff0e::/16`은 `is_global=True`로 보고된다.

따라서 견고한 내부 주소 거부 조건은: `ip.is_multicast or not ip.is_global`

**Why:** `is_private`만 검사하면 CGNAT로 우회하는 SSRF를 통과시키고, `is_global`만 검사하면 전역 멀티캐스트를 놓친다. 두 표준 속성 어느 하나로도 완전하지 않다는 것을 실측으로 확인했다.
**How to apply:** URL/호스트에서 해석한 모든 IP를 검증할 때 `is_private`/`is_loopback` 나열식 대신 `ip.is_multicast or not ip.is_global` 단일 조건을 쓴다. 이미 lookup.py의 `_reject_if_internal`에 구현됨 — 새 네트워크 대상 코드에도 동일 조건 재사용. 관련: [[cli-unknown-flags-usage-error]]
