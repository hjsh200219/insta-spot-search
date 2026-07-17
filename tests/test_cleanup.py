"""R2 — cleanup boundary contract.

``ingest.py --cleanup DIR`` deletes ONLY the files listed in an owned manifest,
and REFUSES (exit 2) on missing/unowned manifests, dangerous roots (repo/home/
filesystem-root/empty), and manifest entries that escape the workspace or cross a
symlink. cleanup() dies via SystemExit; stderr is captured to keep test output clean.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling _harness
from _harness import ingest

MANIFEST_NAME = ".insta-spot-manifest.json"


def _write_manifest(work_dir, created, owned=True):
    data = {"schema_version": 1, "owned": owned, "created": created,
            "work_dir": os.path.abspath(work_dir)}
    with open(os.path.join(work_dir, MANIFEST_NAME), "w") as f:
        json.dump(data, f)


def _cleanup(target):
    """Run cleanup(target), swallow its stderr, return (exit_code_or_None)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            ingest.cleanup(target)
            return None
        except SystemExit as e:
            return e.code


class TestR2CleanupHappyPath(unittest.TestCase):
    def test_R2_cleanup_removes_only_manifest_files(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "frames"))
            Path(d, "video.mp4").write_bytes(b"v")
            Path(d, "frames", "f_001.jpg").write_bytes(b"j")
            Path(d, "report.json").write_text("{}")
            # A file the tool did NOT create — must survive.
            Path(d, "user_notes.txt").write_text("keep me")
            _write_manifest(d, ["video.mp4", "frames/f_001.jpg", "report.json"])

            code = _cleanup(d)
            self.assertIsNone(code)  # clean return
            self.assertFalse(os.path.exists(os.path.join(d, "video.mp4")))
            self.assertFalse(os.path.exists(os.path.join(d, "frames", "f_001.jpg")))
            self.assertFalse(os.path.exists(os.path.join(d, "report.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "user_notes.txt")))

    def test_R2_cleanup_preserves_unlisted_user_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "user_stuff"))
            Path(d, "user_stuff", "photo.jpg").write_bytes(b"x")
            Path(d, "video.mp4").write_bytes(b"v")
            _write_manifest(d, ["video.mp4"])
            _cleanup(d)
            self.assertTrue(os.path.exists(os.path.join(d, "user_stuff", "photo.jpg")))


class TestR2CleanupRefusals(unittest.TestCase):
    def test_R2_refuses_empty_path(self):
        self.assertEqual(_cleanup(""), 2)

    def test_R2_refuses_nonexistent_dir(self):
        self.assertEqual(_cleanup("/nonexistent/insta/spot/xyz"), 2)

    def test_R2_refuses_no_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_unowned_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, ["video.mp4"], owned=False)
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_malformed_created_list(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, MANIFEST_NAME), "w") as f:
                json.dump({"schema_version": 1, "owned": True, "created": "nope"}, f)
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_filesystem_root(self):
        self.assertEqual(_cleanup(os.path.sep), 2)

    def test_R2_refuses_home_directory(self):
        with tempfile.TemporaryDirectory() as home:
            _write_manifest(home, [])  # even a valid manifest can't override the guard
            with mock.patch.object(ingest.os.path, "expanduser", return_value=home):
                self.assertEqual(_cleanup(home), 2)

    def test_R2_refuses_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".git"))
            _write_manifest(d, [])
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_manifest_entry_escaping_workspace(self):
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, ["../evil.txt"])
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_absolute_manifest_entry(self):
        with tempfile.TemporaryDirectory() as d:
            _write_manifest(d, ["/etc/passwd"])
            self.assertEqual(_cleanup(d), 2)

    def test_R2_refuses_manifest_entry_crossing_symlink(self):
        with tempfile.TemporaryDirectory() as outside, \
                tempfile.TemporaryDirectory() as d:
            Path(outside, "secret.txt").write_text("secret")
            # 'link' inside the workspace points outside it.
            os.symlink(outside, os.path.join(d, "link"))
            _write_manifest(d, ["link/secret.txt"])
            self.assertEqual(_cleanup(d), 2)
            # the symlink target is untouched
            self.assertTrue(os.path.exists(os.path.join(outside, "secret.txt")))


if __name__ == "__main__":
    unittest.main()
