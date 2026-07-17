#!/usr/bin/env python3
"""Shared stdlib-only helpers for the insta-spot-search entrypoints.

NOT an entrypoint — no CLI, no ``__main__``. ``setup.py`` / ``ingest.py`` /
``lookup.py`` each prepend their own ``scripts/`` dir to ``sys.path`` and then
``import _common`` to reuse these helpers. Keeping the shared logic HERE (rather
than one entrypoint importing another) preserves the "independent sibling CLIs"
invariant — see docs/design-docs/layer-rules.md §1 (공유 코드는 새 공유 모듈로,
진입점끼리 import 금지).

Contents:
  die                   uniform ``ERROR: ...`` to stderr + ``sys.exit`` (item e)
  REQUIRED_BINARIES     external binaries the skill shells out to (item b)
  missing_binaries      which of a caller's binary list are absent from PATH
  cookie_retry_attempts yt-dlp cookie-retry ladder (item a)
  PathEscape            raised by resolve_within on any containment failure
  resolve_within        SECURITY-CRITICAL unified path containment (item f)

stdlib-only, zero pip deps (an internal module, not third-party).
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import NoReturn

# The external binaries the skill drives via subprocess. Single source of truth
# shared by setup.py (preflight/installer) and ingest.py (runtime check builds a
# subset — yt-dlp is only needed for URL sources).
REQUIRED_BINARIES = ["yt-dlp", "ffmpeg", "ffprobe"]


def die(code: int, msg: str) -> NoReturn:
    """Print ``ERROR: <msg>`` to stderr and exit with ``code``."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def missing_binaries(binaries: list[str]) -> list[str]:
    """Return the subset of ``binaries`` not found on PATH (via ``shutil.which``).

    Callers pass whichever list they need (setup.py passes REQUIRED_BINARIES;
    ingest.py builds its own so yt-dlp is only required for URL sources)."""
    return [b for b in binaries if shutil.which(b) is None]


def cookie_retry_attempts(cookies_browser: str) -> list[list[str]]:
    """yt-dlp retry ladder shared by ingest.download() and ingest.scan_profile().

    Returns ``[[]]`` when cookies are disabled (``cookies_browser == "none"``),
    else ``[[], ["--cookies-from-browser", <browser>]]``. Each element is the
    EXTRA flag fragment a caller splices into its base yt-dlp argv (the empty
    list is the plain anonymous attempt; the second element is the cookie-assisted
    retry). Centralizing the fragment keeps the two call sites from drifting."""
    if cookies_browser == "none":
        return [[]]
    return [[], ["--cookies-from-browser", cookies_browser]]


class PathEscape(Exception):
    """resolve_within rejected a target: it was absolute, contained an empty /
    ``.`` / ``..`` component, crossed a symlinked path component, or resolved to
    a realpath outside ``base``. Each caller maps this to its own exit code."""


def resolve_within(base: str, target: str) -> str:
    """Return the resolved absolute path of ``target`` inside ``base``, or raise
    ``PathEscape`` if it would escape. SECURITY-CRITICAL (item f).

    Unifies lookup.py's ``_resolve_dest`` (commonpath+realpath) and ingest.py's
    ``_resolve_created`` (per-part islink walk + realpath containment) into one
    helper that is at least as strict as BOTH:

      * reject an absolute or empty ``target``;
      * reject any empty / ``.`` / ``..`` path component;
      * reject if ANY intermediate component (or the leaf) is a symlink — this
        per-part islink walk defends against symlink swaps even when the final
        realpath happens to land back inside ``base``;
      * reject if the realpath of the joined path is outside realpath(``base``).

    ``target`` is a POSIX-style relative path (components split on ``/``).
    """
    if not target or os.path.isabs(target):
        raise PathEscape(target)
    base_real = os.path.realpath(base)
    cur = base_real
    for part in target.split("/"):
        if part in ("", ".", ".."):
            raise PathEscape(target)
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise PathEscape(target)
    resolved = os.path.realpath(cur)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise PathEscape(target)
    return resolved
