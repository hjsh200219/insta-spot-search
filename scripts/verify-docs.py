#!/usr/bin/env python3
"""verify-docs — check that insta-spot-search docs still match the code.

Stdlib-only. Run manually or in the harness-gc flow (there is no package.json to
hook into):

    python3 scripts/verify-docs.py        # exit 0 if all checks PASS, 1 otherwise

Checks:
  1. Referenced paths exist        setup.py / ingest.py / SKILL.md
  2. stdlib-only invariant         no third-party (or cross-entrypoint) imports
  3. exit-code contract            ingest.py die() codes 2/3/4/5, lookup.py 0/2/4
  4. markdown link existence       repo-internal relative links in *.md resolve
  5. no shell=True                 subprocess calls stay list-args only
  6. no live 'rm -rf'              only manifest-scoped Python cleanup allowed
  7. no secret-in-argv             Authorization: Bearer never in a child argv

See docs/design-docs/layer-rules.md (§3, §5) and docs/harness/harness-setup.md.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "skills" / "insta-spot-search" / "scripts"
INGEST = SCRIPTS / "ingest.py"
SETUP = SCRIPTS / "setup.py"
LOOKUP = SCRIPTS / "lookup.py"
SKILL = REPO / "skills" / "insta-spot-search" / "SKILL.md"

# This checker's own file. It legitimately spells out the banned patterns below
# (as regex literals, check labels, and docstrings) so it must exempt itself from
# the checks that grep scripts/*.py for those same literal patterns — otherwise
# the checker would perpetually fail on its own source.
SELF = Path(__file__).resolve()

# Paths that AGENTS.md / ARCHITECTURE.md promise exist.
REQUIRED_PATHS = [SETUP, INGEST, SKILL]

# Python files whose imports must stay stdlib-only. lookup.py is scanned too now
# that it imports the shared _common module (its import is allowlisted below).
STDLIB_ONLY_FILES = [INGEST, SETUP, LOOKUP]

# The two independent CLI entrypoints — importing one from the other violates the
# "independent entrypoints" invariant (layer-rules §1), so their bare module names
# must NOT appear as imports.
ENTRYPOINT_MODULES = {"setup", "ingest"}

# Genuinely stdlib-only shared modules that entrypoints may import (layer-rules §1:
# shared code goes into a NEW module the entrypoints import, never one entrypoint
# importing another). `_common` is scripts/_common.py — a LOCAL sibling module, not
# a third-party dep — so `import _common` / `from _common import ...` is permitted.
LOCAL_SHARED_MODULES: set[str] = {"_common"}

# Fallback stdlib allowlist for Python < 3.10 (no sys.stdlib_module_names). Covers
# the modules these scripts actually use plus common stdlib, kept intentionally small.
_STDLIB_FALLBACK = {
    "__future__", "argparse", "ast", "collections", "contextlib", "csv",
    "dataclasses", "datetime", "functools", "glob", "hashlib", "io", "ipaddress",
    "itertools", "json", "math", "os", "pathlib", "platform", "random", "re",
    "shlex", "shutil", "socket", "subprocess", "sys", "tempfile", "textwrap",
    "time", "typing", "unittest", "urllib", "uuid",
}

# ingest.py exit-code contract (must match SKILL.md "Failure modes" + ARCHITECTURE).
REQUIRED_EXIT_CODES = ["2", "3", "4", "5"]

# lookup.py exit-code contract (CONTRACT.md §5): 0 ok is implicit/documented only
# (no die(0, ...) call exists since success falls through main() rather than
# calling die()); 2 and 4 must be reachable via an explicit die()/sys.exit().
LOOKUP_EXIT_CODES = ["2", "4"]

# --- patterns for the R8 safety-net checks (markdown links, shell=True, rm -rf,
# secret-in-argv). Kept near the other module-level contracts above. ---
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
SHELL_TRUE_RE = re.compile(r"shell\s*=\s*True")
RM_RF_RE = re.compile(r"\brm\s+-rf\b")
RM_RF_LIST_RE = re.compile(r"""["']rm["']\s*,\s*["']-rf["']""")
SECRET_ARGV_RE = re.compile(r"""["']-H["']\s*,\s*f?["']Authorization:\s*Bearer""")


def _stdlib_names() -> set[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names) | {"__future__"}
    return set(_STDLIB_FALLBACK)


def _top_level_imports(path: Path) -> list[str]:
    """Top-level package name of every absolute import in a file (skips relative)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import -> local, not third-party
            if node.module:
                mods.append(node.module.split(".")[0])
    return mods


def check_paths() -> tuple[bool, list[str]]:
    problems = [f"missing: {p.relative_to(REPO)}" for p in REQUIRED_PATHS if not p.is_file()]
    return (not problems), problems


def check_stdlib_only() -> tuple[bool, list[str]]:
    stdlib = _stdlib_names()
    problems: list[str] = []
    for path in STDLIB_ONLY_FILES:
        if not path.is_file():
            problems.append(f"cannot scan (missing): {path.relative_to(REPO)}")
            continue
        for mod in _top_level_imports(path):
            if mod in stdlib or mod in LOCAL_SHARED_MODULES:
                continue
            rel = path.relative_to(REPO)
            if mod in ENTRYPOINT_MODULES:
                problems.append(
                    f"{rel}: imports entrypoint '{mod}' — entrypoints must stay "
                    f"independent (layer-rules §1)"
                )
            else:
                problems.append(
                    f"{rel}: non-stdlib import '{mod}' — pip deps are forbidden "
                    f"(layer-rules §3)"
                )
    return (not problems), problems


def check_exit_codes() -> tuple[bool, list[str]]:
    problems: list[str] = []
    if not INGEST.is_file():
        problems.append(f"cannot scan (missing): {INGEST.relative_to(REPO)}")
    else:
        src = INGEST.read_text(encoding="utf-8")
        for code in REQUIRED_EXIT_CODES:
            # match die(2, ... or sys.exit(2) style references
            if not re.search(rf"(?:die|sys\.exit)\(\s*{code}\b", src):
                problems.append(f"ingest.py no longer references exit code {code} via die()/sys.exit()")

    if not LOOKUP.is_file():
        problems.append(f"cannot scan (missing): {LOOKUP.relative_to(REPO)}")
    else:
        src = LOOKUP.read_text(encoding="utf-8")
        for code in LOOKUP_EXIT_CODES:
            if not re.search(rf"(?:die|sys\.exit)\(\s*{code}\b", src):
                problems.append(f"lookup.py no longer references exit code {code} via die()/sys.exit()")
        # exit 0 is the implicit success path (no die(0, ...) call exists) — require
        # it to stay documented in the module docstring instead of grepping for a call.
        if not re.search(r"\b0\s+ok\b", src):
            problems.append("lookup.py no longer documents exit code 0 ('0 ok') in its docstring")

    return (not problems), problems


def _iter_fence_lines(path: Path) -> "list[tuple[int, str, bool]]":
    """(lineno, line, in_fence) for every line, tracking ``` / ~~~ fence state.

    The fence delimiter line itself is reported with the *post-toggle* state and
    is never itself treated as scannable content by callers.
    """
    out: "list[tuple[int, str, bool]]" = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append((lineno, line, in_fence))
            continue
        out.append((lineno, line, in_fence))
    return out


def _markdown_targets() -> "list[Path]":
    targets = [REPO / "AGENTS.md", REPO / "ARCHITECTURE.md", REPO / "README.md", SKILL]
    targets += sorted((REPO / "docs").rglob("*.md"))
    seen: "set[Path]" = set()
    ordered: "list[Path]" = []
    for p in targets:
        if p.is_file() and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _scanned_py_files() -> "list[Path]":
    """*.py under scripts/ (excluding this checker itself) + skills/** (R8/CONTRACT §9)."""
    files: "list[Path]" = []
    scripts_dir = REPO / "scripts"
    if scripts_dir.is_dir():
        files += sorted(p for p in scripts_dir.glob("*.py") if p.resolve() != SELF)
    skills_dir = REPO / "skills"
    if skills_dir.is_dir():
        files += sorted(skills_dir.rglob("*.py"))
    return files


def check_markdown_links() -> tuple[bool, list[str]]:
    """Repo-internal relative markdown links must resolve (fenced code blocks skipped)."""
    problems: list[str] = []
    for md in _markdown_targets():
        for lineno, line, in_fence in _iter_fence_lines(md):
            if in_fence:
                continue
            for m in LINK_RE.finditer(line):
                target = m.group(1).strip()
                if not target or target.startswith("#"):
                    continue  # pure in-page anchor
                if "://" in target or target.startswith("mailto:"):
                    continue  # external link — out of scope
                path_part = target.split(" ", 1)[0]  # drop an optional "title"
                path_part = path_part.split("#", 1)[0]  # drop an anchor fragment
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    problems.append(f"{md.relative_to(REPO)}:{lineno}: broken link -> {target}")
    return (not problems), problems


def check_no_shell_true() -> tuple[bool, list[str]]:
    """subprocess calls must stay list-args only — shell=True is forbidden (CONTRACT §0)."""
    problems: list[str] = []
    for path in _scanned_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SHELL_TRUE_RE.search(line):
                problems.append(f"{path.relative_to(REPO)}:{lineno}: forbidden shell=True")
    return (not problems), problems


def check_no_live_rm_rf() -> tuple[bool, list[str]]:
    """Ban a *live* `rm -rf` invocation (R2). Prose forbidding it is fine — only an
    actual command inside a SKILL.md bash fence, or an os.system/subprocess call in
    Python, counts as a violation."""
    problems: list[str] = []
    if SKILL.is_file():
        for lineno, line, in_fence in _iter_fence_lines(SKILL):
            if in_fence and RM_RF_RE.search(line):
                problems.append(f"{SKILL.relative_to(REPO)}:{lineno}: live 'rm -rf' inside a bash block")

    for path in _scanned_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue  # comment/policy text, not an executable invocation
            if RM_RF_RE.search(line) or RM_RF_LIST_RE.search(line):
                problems.append(f"{path.relative_to(REPO)}:{lineno}: live 'rm -rf' invocation")
    return (not problems), problems


def check_no_secret_argv() -> tuple[bool, list[str]]:
    """R7: the Whisper Bearer key must travel in an HTTP header, never a child argv.
    Flags the curl `"-H", f"Authorization: Bearer ..."` anti-pattern; a header dict
    (urllib `req.add_header(...)` / `headers={...}`) is not a subprocess argv and is fine.
    """
    problems: list[str] = []
    for path in _scanned_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SECRET_ARGV_RE.search(line):
                problems.append(
                    f"{path.relative_to(REPO)}:{lineno}: Authorization Bearer key in a "
                    f"child-process argv (use an HTTP header, not curl -H)"
                )
    return (not problems), problems


CHECKS = [
    ("1. referenced paths exist", check_paths),
    ("2. stdlib-only invariant", check_stdlib_only),
    ("3. exit-code contract (ingest 2/3/4/5, lookup 0/2/4)", check_exit_codes),
    ("4. repo-internal markdown links resolve", check_markdown_links),
    ("5. no shell=True (list-args only)", check_no_shell_true),
    ("6. no live 'rm -rf' invocation", check_no_live_rm_rf),
    ("7. no secret-in-argv (Authorization: Bearer)", check_no_secret_argv),
]


def main() -> int:
    all_ok = True
    print("=== verify-docs: insta-spot-search ===")
    for name, fn in CHECKS:
        ok, problems = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        for p in problems:
            print(f"        - {p}")
        all_ok = all_ok and ok
    print("---")
    print("RESULT:", "PASS — docs match code" if all_ok else "FAIL — see above")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
