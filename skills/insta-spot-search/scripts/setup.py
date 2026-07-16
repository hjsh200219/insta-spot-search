#!/usr/bin/env python3
"""Setup / preflight for insta-spot-search.

Modes:
  setup.py --check   Silent preflight. Exit 0 if ready, 2 if binaries missing.
  setup.py --json    Machine-readable status for the agent to parse.
  setup.py           Installer. Auto-installs yt-dlp + ffmpeg (macOS/brew),
                     prints exact commands on Linux/Windows.

Design:
- Silent on success: --check exits 0 with no output when everything's present
  so the skill doesn't spam a status line on every invocation.
- Idempotent: re-running is safe — brew skips already-installed packages.
- Never sudo. On macOS, auto-install via brew. Elsewhere, print exact commands.
- No API key handling here — Whisper narration transcription is optional and
  reuses ~/.config/watch/.env when present (see SKILL.md).
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_BINARIES = ["yt-dlp", "ffmpeg", "ffprobe"]


def _which(name: str) -> str | None:
    return shutil.which(name)


def _check_binaries() -> list[str]:
    return [b for b in REQUIRED_BINARIES if not _which(b)]


def _brew_pkgs(missing: list[str]) -> list[str]:
    pkgs: list[str] = []
    for b in missing:
        pkg = "ffmpeg" if b in ("ffmpeg", "ffprobe") else b
        if pkg not in pkgs:
            pkgs.append(pkg)
    return pkgs


def _install_macos(missing: list[str]) -> tuple[bool, str]:
    if _which("brew") is None:
        return False, (
            "Homebrew not installed. Get it from https://brew.sh, then re-run setup — "
            "or install manually: brew install " + " ".join(_brew_pkgs(missing))
        )
    pkgs = _brew_pkgs(missing)
    cmd = ["brew", "install", *pkgs]
    print(f"[setup] running: {' '.join(cmd)}", file=sys.stderr)
    if subprocess.run(cmd).returncode != 0:
        return False, "brew install failed"
    return True, f"installed via brew: {', '.join(pkgs)}"


def _hint_linux(missing: list[str]) -> str:
    pkgs = _brew_pkgs(missing)
    hints = []
    if "ffmpeg" in pkgs:
        hints.append("ffmpeg: `sudo apt install ffmpeg` (or `sudo dnf install ffmpeg`)")
    if "yt-dlp" in pkgs:
        hints.append("yt-dlp: `pipx install yt-dlp` (or `pip install --user yt-dlp`)")
    return "\n  ".join(hints)


def _hint_windows(missing: list[str]) -> str:
    pkgs = _brew_pkgs(missing)
    hints = []
    if "ffmpeg" in pkgs:
        hints.append("ffmpeg: `winget install Gyan.FFmpeg`")
    if "yt-dlp" in pkgs:
        hints.append("yt-dlp: `winget install yt-dlp.yt-dlp` (or `pip install --user yt-dlp`)")
    return "\n  ".join(hints)


def _status() -> dict:
    missing = _check_binaries()
    return {
        "status": "ready" if not missing else "needs_install",
        "missing_binaries": missing,
        "platform": platform.system(),
    }


def cmd_check() -> int:
    s = _status()
    if s["status"] == "ready":
        return 0
    installer = Path(__file__).resolve()
    sys.stderr.write(
        f"[insta-spot-search] missing binaries: {', '.join(s['missing_binaries'])}. "
        f"Run: python3 {installer}\n"
    )
    sys.stderr.flush()
    return 2


def cmd_json() -> int:
    json.dump(_status(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_install() -> int:
    missing = _check_binaries()
    if not missing:
        print("[setup] all dependencies present (yt-dlp, ffmpeg, ffprobe). ready.")
        return 0

    system = platform.system()
    if system == "Darwin":
        ok, msg = _install_macos(missing)
        print(f"[setup] {msg}", file=sys.stderr)
        if not ok:
            return 2
        still = _check_binaries()
        if still:
            print(f"[setup] still missing after install: {', '.join(still)}", file=sys.stderr)
            return 2
        print("[setup] ready. insta-spot-search is fully set up.")
        return 0

    if system == "Linux":
        print("[setup] dependencies missing on Linux — install:", file=sys.stderr)
        print("  " + _hint_linux(missing), file=sys.stderr)
        return 2
    if system == "Windows":
        print("[setup] dependencies missing on Windows — install:", file=sys.stderr)
        print("  " + _hint_windows(missing), file=sys.stderr)
        return 2

    print(f"[setup] unsupported platform ({system}). install manually: {', '.join(missing)}",
          file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check":
            return cmd_check()
        if sys.argv[1] == "--json":
            return cmd_json()
    return cmd_install()


if __name__ == "__main__":
    raise SystemExit(main())
