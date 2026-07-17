"""Fast-follow hardening regressions for ingest.py (additive to the R2/R4-R9 suite).

Covers reviewer-confirmed residual findings from the v0.4.x review:
  1. ownership idempotency across re-ingests into a tool-created --out-dir
  2. a non-dict video.info.json (literal `null`) must not crash with exit 1
  3. probe_duration rejects a non-finite ffprobe duration (exit 4)
  4. _prepare_staging never deletes a user's real .staging/ in a non-owned dir
  5. _remove_stale routes removals through the workspace containment guard
  6. an explicit --fps is clamped to a sane ceiling

Same faked subprocess layer as test_ingest_contract (no network / binaries / keys).
"""
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling _harness
from _harness import (FakeProc, ingest, read_manifest, read_report, run_ingest)

URL = "https://www.instagram.com/reel/ABC123/"
MANIFEST_NAME = ingest.MANIFEST_NAME
STAGING_NAME = ingest.STAGING_NAME


class _IngestCase(unittest.TestCase):
    def tmpdir(self):
        d = tempfile.mkdtemp(prefix="iss-harden-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def fresh_out(self):
        return os.path.join(self.tmpdir(), "work")


# ---------------------------------------------------------------------------
# 1. Ownership idempotency — re-ingest keeps work_dir_owned=True, cleanup works
# ---------------------------------------------------------------------------
class TestOwnershipIdempotency(_IngestCase):
    def test_reingest_preserves_ownership_and_cleanup_succeeds(self):
        out = self.fresh_out()  # does not exist yet → tool owns it on first run

        code1, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())
        self.assertEqual(code1, 0)
        self.assertTrue(read_report(out)["work_dir_owned"])
        self.assertTrue(read_manifest(out)["owned"])

        # Re-ingest into the SAME dir. It now exists, but a prior owned manifest is
        # present, so ownership must be preserved (not flipped to False).
        code2, _o2, _e2 = run_ingest([URL, "--out-dir", out], FakeProc())
        self.assertEqual(code2, 0)
        self.assertTrue(read_report(out)["work_dir_owned"])
        self.assertTrue(read_manifest(out)["owned"])

        # And because ownership survived, --cleanup on the owned manifest succeeds.
        code3, _o3, _e3 = run_ingest(["--cleanup", out], FakeProc())
        self.assertEqual(code3, 0)
        self.assertFalse(os.path.exists(os.path.join(out, MANIFEST_NAME)))


# ---------------------------------------------------------------------------
# 2. Non-dict info.json (literal `null`) must not raise a raw traceback / exit 1
# ---------------------------------------------------------------------------
class TestNonDictInfoJson(_IngestCase):
    def test_null_info_json_exits_cleanly(self):
        out = self.fresh_out()
        fake = FakeProc()
        fake.info = None  # video.info.json will contain the literal `null`
        code, _o, _e = run_ingest([URL, "--out-dir", out], fake)
        self.assertEqual(code, 0)          # clean exit, NOT a traceback/exit 1
        self.assertNotEqual(code, 1)
        rep = read_report(out)             # report still produced and well-formed
        self.assertEqual(rep["schema_version"], 1)
        self.assertIsNone(rep["title"])    # metadata degrades to null, no crash


# ---------------------------------------------------------------------------
# 3. probe_duration rejects a non-finite duration (exit 4)
# ---------------------------------------------------------------------------
class TestNonFiniteDuration(_IngestCase):
    def test_infinite_duration_exit_4(self):
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out()],
                                   FakeProc(duration="inf"))
        self.assertEqual(code, 4)
        self.assertIn("duration", err.lower())


# ---------------------------------------------------------------------------
# 4. _prepare_staging refuses to delete a user's real .staging/ (non-owned dir)
# ---------------------------------------------------------------------------
class TestStagingSafety(_IngestCase):
    def test_refuses_to_delete_user_staging_in_nonowned_dir(self):
        out = self.tmpdir()  # pre-existing, user-supplied → NOT owned
        user_staging = os.path.join(out, STAGING_NAME)
        os.makedirs(user_staging)
        Path(user_staging, "important.txt").write_text("user data")

        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())

        self.assertEqual(code, 2)  # refuse rather than delete user content
        self.assertEqual(Path(user_staging, "important.txt").read_text(), "user data")


# ---------------------------------------------------------------------------
# 5. _remove_stale honors the containment guard for a hand-edited manifest
# ---------------------------------------------------------------------------
class TestRemoveStaleContainment(_IngestCase):
    def test_manifest_dotdot_entry_does_not_delete_outside_workspace(self):
        parent = self.tmpdir()
        out = os.path.join(parent, "work")
        os.makedirs(out)
        victim = os.path.join(parent, "victim.txt")  # lives OUTSIDE the workspace
        Path(victim).write_text("do not delete")

        # Hand-edited owned manifest whose 'created' list escapes with '../'.
        Path(out, MANIFEST_NAME).write_text(json.dumps({
            "schema_version": 1, "owned": True,
            "created": ["../victim.txt"], "work_dir": out,
        }))

        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())

        self.assertEqual(code, 0)               # normal run
        self.assertTrue(os.path.exists(victim))  # the escaping entry was NOT deleted
        self.assertEqual(Path(victim).read_text(), "do not delete")


# ---------------------------------------------------------------------------
# 6. explicit --fps is clamped to the ceiling
# ---------------------------------------------------------------------------
class TestFpsClamp(_IngestCase):
    def _frame_vf(self, fake):
        for cmd in fake.calls:
            if (os.path.basename(cmd[0]) == "ffmpeg"
                    and "-vf" in cmd and "-vn" not in cmd):
                return cmd[cmd.index("-vf") + 1]
        self.fail("no ffmpeg frame-extraction command was issued")

    def test_explicit_fps_is_clamped(self):
        out = self.fresh_out()
        fake = FakeProc(frames=5)
        code, _o, _e = run_ingest([URL, "--out-dir", out, "--fps", "1000"], fake)
        self.assertEqual(code, 0)
        vf = self._frame_vf(fake)
        m = re.search(r"fps=([0-9.]+)", vf)
        self.assertIsNotNone(m, f"no fps= in vf filter: {vf!r}")
        self.assertLessEqual(float(m.group(1)), ingest.FPS_CEILING)


if __name__ == "__main__":
    unittest.main()
