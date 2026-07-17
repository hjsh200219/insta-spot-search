"""R1 — isolated-shell path resolution + SKILL.md Bash-block hygiene.

The v0.3.x regression was: subsequent Bash blocks ran in fresh shells that did
NOT inherit ``$SKILL_DIR``, so ``python3 "$SKILL_DIR/scripts/setup.py"`` collapsed
to ``python3 "/scripts/setup.py"`` (No such file). These tests run the SKILL.md
resolver in a real fresh ``zsh -c`` (or ``sh -c``) subprocess and assert the path
resolves correctly, plus statically verify every Bash block redefines SKILL_DIR.

stdlib only. A fake yt-dlp/ffmpeg/ffprobe PATH makes ``setup.py --check`` exit 0
deterministically regardless of what the host has installed.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling _harness
from _harness import REPO, SKILL, SKILL_MD

# The two-line resolver copied verbatim from SKILL.md Step 0.
RESOLVER = (
    'SKILL_DIR="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/skills/insta-spot-search}"\n'
    'SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"\n'
)


def _shell():
    return shutil.which("zsh") or shutil.which("sh") or "/bin/sh"


def _fake_bin_dir():
    """A temp dir with executable yt-dlp/ffmpeg/ffprobe stubs (exit 0)."""
    d = tempfile.mkdtemp(prefix="iss-fakebin-")
    for name in ("yt-dlp", "ffmpeg", "ffprobe"):
        p = Path(d) / name
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return d


def _run_block(script, env):
    return subprocess.run([_shell(), "-c", script], capture_output=True, text=True,
                          env=env, timeout=60)


class TestR1IsolatedShell(unittest.TestCase):
    def setUp(self):
        self.fakebin = _fake_bin_dir()
        self.addCleanup(shutil.rmtree, self.fakebin, ignore_errors=True)
        # Minimal, explicit env — a genuinely fresh shell, not the parent's.
        self.base_env = {
            "PATH": self.fakebin + os.pathsep + os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", "/tmp"),
        }

    def test_R1_isolated_shell_resolves_setup_check(self):
        env = dict(self.base_env, CLAUDE_PLUGIN_ROOT=str(REPO))
        script = RESOLVER + 'python3 "$SKILL_DIR/scripts/setup.py" --check\n'
        r = _run_block(script, env)
        # The /scripts/ collapse must NOT recur.
        self.assertNotIn("/scripts/setup.py", r.stderr)
        self.assertNotIn("can't open file", r.stderr)
        self.assertNotIn("No such file or directory", r.stderr)
        # With deps present on PATH, --check is silent success.
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")

    def test_R1_isolated_shell_does_not_resolve_to_root_scripts(self):
        # Prove the failure mode is detectable: with SKILL_DIR unset the path
        # WOULD collapse to /scripts/... — confirm the resolver prevents it by
        # echoing the resolved path.
        env = dict(self.base_env, CLAUDE_PLUGIN_ROOT=str(REPO))
        script = RESOLVER + 'printf "%s\\n" "$SKILL_DIR/scripts/setup.py"\n'
        r = _run_block(script, env)
        self.assertEqual(r.returncode, 0)
        resolved = r.stdout.strip()
        self.assertFalse(resolved.startswith("/scripts/"),
                         f"resolved to root /scripts: {resolved!r}")
        self.assertEqual(resolved, str(SKILL / "scripts" / "setup.py"))

    def test_R1_isolated_shell_ingest_path_exists(self):
        # The ingest path (used by Step 1) resolves to a real file too.
        env = dict(self.base_env, CLAUDE_PLUGIN_ROOT=str(REPO))
        script = RESOLVER + 'test -f "$SKILL_DIR/scripts/ingest.py" && echo OK\n'
        r = _run_block(script, env)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")
        self.assertEqual(r.stdout.strip(), "OK")

    def test_R1_isolated_shell_spaces_and_brackets_in_plugin_root(self):
        # A plugin root with spaces + [brackets] must still resolve because
        # SKILL.md quotes every dynamic path. We build a weird-named dir whose
        # skills/ symlinks to the real skill tree.
        weird_parent = tempfile.mkdtemp(prefix="iss-weird-")
        self.addCleanup(shutil.rmtree, weird_parent, ignore_errors=True)
        weird_root = os.path.join(weird_parent, "plug in [v0.4] root")
        os.makedirs(weird_root)
        os.symlink(str(REPO / "skills"), os.path.join(weird_root, "skills"))
        env = dict(self.base_env, CLAUDE_PLUGIN_ROOT=weird_root)
        script = RESOLVER + 'python3 "$SKILL_DIR/scripts/setup.py" --check\n'
        r = _run_block(script, env)
        self.assertNotIn("can't open file", r.stderr)
        self.assertNotIn("No such file or directory", r.stderr)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")

    def test_R1_isolated_shell_falls_back_to_claude_skill_dir(self):
        # Second line of the resolver: with no CLAUDE_PLUGIN_ROOT, fall back to
        # CLAUDE_SKILL_DIR (the other harness that installs the skill).
        env = dict(self.base_env, CLAUDE_SKILL_DIR=str(SKILL))
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        script = RESOLVER + 'python3 "$SKILL_DIR/scripts/setup.py" --check\n'
        r = _run_block(script, env)
        self.assertNotIn("/scripts/setup.py", r.stderr)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")


def _bash_blocks(md_text):
    """Yield the body of every ```bash fenced block in the markdown."""
    blocks, cur, in_block = [], [], False
    for line in md_text.splitlines():
        if not in_block and re.match(r"^```\s*bash\s*$", line.strip()):
            in_block, cur = True, []
            continue
        if in_block and line.strip() == "```":
            blocks.append("\n".join(cur))
            in_block = False
            continue
        if in_block:
            cur.append(line)
    return blocks


class TestR1SkillMdBlocks(unittest.TestCase):
    def setUp(self):
        self.md = Path(SKILL_MD).read_text(encoding="utf-8")
        self.blocks = _bash_blocks(self.md)

    def test_R1_skill_md_has_bash_blocks(self):
        self.assertGreater(len(self.blocks), 0, "no ```bash blocks found in SKILL.md")

    def test_R1_every_block_using_skill_dir_redefines_it(self):
        uses = re.compile(r"\$\{SKILL_DIR\}|\$SKILL_DIR")
        defines = re.compile(r"(^|;|\s)SKILL_DIR=")
        offenders = []
        for i, block in enumerate(self.blocks):
            if uses.search(block) and not defines.search(block):
                offenders.append(i)
        self.assertEqual(offenders, [],
                         f"bash blocks reference $SKILL_DIR without redefining it: {offenders}")

    def test_R1_dynamic_paths_are_quoted(self):
        # Every use of the SKILL_DIR path in a python3/test invocation is quoted.
        for block in self.blocks:
            for m in re.finditer(r"\$\{SKILL_DIR\}/scripts/\S+", block):
                snippet = block[max(0, m.start() - 1):m.start()]
                self.assertEqual(snippet, '"',
                                 f"unquoted SKILL_DIR path in block:\n{block}")


if __name__ == "__main__":
    unittest.main()
