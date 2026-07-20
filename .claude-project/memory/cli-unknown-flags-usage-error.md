---
name: cli-unknown-flags-usage-error
description: CLI 진입점은 알 수 없는 플래그를 usage error(exit 2)로 — 기본 동작 모드로 흘려보내지 않음
type: project
created: 2026-07-20
---

setup.py 버그: `--help` 등 인식하지 못한 플래그가 usage error로 걸리지 않고 installer 모드로 흘러가 실제로 설치를 실행했다. argparse 패턴으로 고쳐 **알 수 없는 플래그는 항상 usage error(exit 2)** 로 종료하게 했다.

**Why:** 이 리포의 기본 동작(setup.py = 설치)은 부작용이 있는 destructive 모드다. 알 수 없는 입력이 기본 모드로 fall-through하면 사용자가 의도하지 않은 설치를 유발한다. 구조화 exit code 계약(setup 0/2)과도 일치.
**How to apply:** setup.py·ingest.py·lookup.py 등 진입점에서 argparse가 미인식 인자를 만나면 exit 2로 끝나게 하고, "인자 없음/미인식 → 기본 액션 실행" 같은 fall-through를 만들지 않는다. 관련: [[ssrf-ipaddress-gotcha]]
