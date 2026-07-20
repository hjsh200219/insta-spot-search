# gc.sh Run Log — insta-spot-search

`scripts/gc.sh`(통합 품질 게이트) 실행 이력. 각 실행이 아래에 한 블록을 **append**한다.

> 이 파일은 `scripts/gc.sh` 전용이다. 성숙도 채점(`/sh:harness-gc`) 이력은 별도
> 파일 [gc-history.md](./gc-history.md)에 있다 — **두 파일의 스키마를 섞지 말 것.**
> gc.sh는 py_compile → verify-docs → preflight → (ruff) → unittest → (coverage)
> 순으로 돌고 PASS/FAIL 배너를 낸다. 상세 게이트는 [harness-setup.md](./harness-setup.md).

## 2026-07-17 09:09:08 +0900 — PASS
- PASS  syntax (py_compile, 6 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 09:10:05 +0900 — PASS
- PASS  syntax (py_compile, 6 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 09:46:12 +0900 — FAIL
- PASS  syntax (py_compile, 9 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- FAIL  unittest
- FAIL  coverage run

## 2026-07-17 09:55:27 +0900 — PASS
- PASS  syntax (py_compile, 12 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 10:16:58 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 10:35:55 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 10:37:30 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 10:41:06 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 11:22:43 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 11:22:57 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 11:30:00 +0900 — PASS
- PASS  syntax (py_compile, 13 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 11:31:26 +0900 — PASS
- PASS  syntax (py_compile, 14 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-17 11:32:54 +0900 — PASS
- PASS  syntax (py_compile, 14 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage

## 2026-07-20 13:23:30 +0900 — PASS
- PASS  syntax (py_compile, 14 files)
- PASS  docs verify
- PASS  preflight (binaries present)
- SKIP  ruff (not installed)
- PASS  unittest
- PASS  coverage
