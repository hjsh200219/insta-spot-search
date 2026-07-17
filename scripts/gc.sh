#!/usr/bin/env bash
# gc.sh — integrated quality gate for insta-spot-search.
#
# This repo is Python 3 stdlib-only (no package.json / node / npm), so the
# Node-oriented --infra gate (knip / husky / lint-staged / vitest) does NOT
# apply. This adapts that gate to Python:
#
#   [1] syntax "build"  python3 -m py_compile (scripts + verify-docs + tests)
#   [2] docs verify     python3 scripts/verify-docs.py
#   [3] preflight       python3 .../setup.py --check   (missing binaries = WARN)
#   [4] lint (optional) ruff check                      (skipped if ruff absent)
#   [5] tests           python3 -m unittest discover -s tests
#   [6] coverage (opt)  python3 -m coverage ...         (skipped if coverage absent)
#
# Runs in order, reports every step, and exits 1 on any HARD failure (0 on pass).
# Each run appends a PASS/FAIL summary to docs/harness/gc-script-log.md.
# Rationale for omitting a Python logger module: docs/harness/harness-setup.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

INGEST="skills/insta-spot-search/scripts/ingest.py"
LOOKUP="skills/insta-spot-search/scripts/lookup.py"
SETUP="skills/insta-spot-search/scripts/setup.py"
VERIFY="scripts/verify-docs.py"
LOG="docs/harness/gc-script-log.md"

HARD_FAIL=0
declare -a RESULTS=()
record() { RESULTS+=("$1"); }

echo "=================================================="
echo " insta-spot-search — quality gate (scripts/gc.sh)"
echo "=================================================="

# ---- [1] syntax / "build": py_compile ----------------------------------------
echo
echo "[1/6] syntax check (py_compile)"
PY_TARGETS=("$INGEST" "$LOOKUP" "$SETUP" "$VERIFY")
if [ -d tests ]; then
  while IFS= read -r f; do PY_TARGETS+=("$f"); done < <(find tests -name '*.py' | sort)
fi
if python3 -m py_compile "${PY_TARGETS[@]}"; then
  echo "  PASS — ${#PY_TARGETS[@]} Python source(s) compile"
  record "PASS  syntax (py_compile, ${#PY_TARGETS[@]} files)"
else
  echo "  FAIL — py_compile reported a syntax error"
  record "FAIL  syntax (py_compile)"
  HARD_FAIL=1
fi

# ---- [2] docs verify ---------------------------------------------------------
echo
echo "[2/6] docs verify (verify-docs.py)"
if python3 "$VERIFY"; then
  record "PASS  docs verify"
else
  record "FAIL  docs verify"
  HARD_FAIL=1
fi

# ---- [3] preflight: missing external binaries = WARN, script crash = FAIL ----
echo
echo "[3/6] preflight (setup.py --check)"
set +e
python3 "$SETUP" --check
PRE_RC=$?
set -e
if [ "$PRE_RC" -eq 0 ]; then
  echo "  PASS — yt-dlp + ffmpeg + ffprobe present"
  record "PASS  preflight (binaries present)"
elif [ "$PRE_RC" -eq 2 ]; then
  echo "  WARN — external binaries missing. yt-dlp/ffmpeg are RUNTIME deps, not repo"
  echo "         deps, so this is not a repo-quality failure. Run: python3 $SETUP"
  record "WARN  preflight (external binaries missing — not a repo failure)"
else
  echo "  FAIL — setup.py --check itself errored (rc=$PRE_RC)"
  record "FAIL  preflight (setup.py errored rc=$PRE_RC)"
  HARD_FAIL=1
fi

# ---- [4] lint (optional): ruff -----------------------------------------------
echo
echo "[4/6] lint (ruff, optional)"
if command -v ruff >/dev/null 2>&1; then
  if ruff check "$INGEST" "$LOOKUP" "$SETUP" "$VERIFY" tests; then
    echo "  PASS — ruff clean"
    record "PASS  ruff"
  else
    echo "  FAIL — ruff reported issues"
    record "FAIL  ruff"
    HARD_FAIL=1
  fi
else
  echo "  ruff not installed — skipped (optional)"
  record "SKIP  ruff (not installed)"
fi

# ---- [5] tests: stdlib unittest ----------------------------------------------
echo
echo "[5/6] tests (python3 -m unittest discover -s tests)"
if [ -d tests ]; then
  if python3 -m unittest discover -s tests -p 'test_*.py'; then
    echo "  PASS — unittest suite green"
    record "PASS  unittest"
  else
    echo "  FAIL — unittest suite has failures"
    record "FAIL  unittest"
    HARD_FAIL=1
  fi
else
  echo "  FAIL — no tests/ directory (tests are a required gate)"
  record "FAIL  unittest (no tests dir)"
  HARD_FAIL=1
fi

# ---- [6] coverage (optional): coverage.py ------------------------------------
echo
echo "[6/6] coverage (coverage.py, optional)"
if python3 -c "import coverage" >/dev/null 2>&1; then
  if python3 -m coverage run -m unittest discover -s tests -p 'test_*.py' >/dev/null 2>&1; then
    python3 -m coverage report
    echo "  PASS — coverage measured"
    record "PASS  coverage"
  else
    echo "  FAIL — tests errored while running under coverage"
    record "FAIL  coverage run"
    HARD_FAIL=1
  fi
  rm -f "$REPO_ROOT/.coverage"
else
  echo "  coverage.py not installed — skipped (optional)"
  record "SKIP  coverage (not installed)"
fi

# ---- banner + log ------------------------------------------------------------
echo
echo "=================================================="
if [ "$HARD_FAIL" -eq 0 ]; then
  echo " RESULT: PASS — quality gate green"
else
  echo " RESULT: FAIL — see failures above"
fi
echo "=================================================="
for r in "${RESULTS[@]}"; do echo "  $r"; done

{
  echo ""
  echo "## $(date '+%Y-%m-%d %H:%M:%S %z') — $([ "$HARD_FAIL" -eq 0 ] && echo PASS || echo FAIL)"
  for r in "${RESULTS[@]}"; do echo "- $r"; done
} >> "$LOG"

exit "$HARD_FAIL"
