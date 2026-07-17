"""R2/R4/R5/R6/R7/R9 — ingest.py end-to-end contract via a faked subprocess/urllib
layer (FakeProc / FakeUrlopen). No network, no binaries, no real keys/cookies.

The fake simulates yt-dlp/ffprobe/ffmpeg by creating the files those tools would
produce and recording every argv, so tests can assert the exact command lines
(cookie flags, --no-write-comments) and the on-disk results (frame cap, preserved
files, report schema) deterministically.
"""
import argparse
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling _harness
from _harness import (FakeProc, FakeUrlopen, ingest, read_manifest, read_report,
                      run_ingest)

URL = "https://www.instagram.com/reel/ABC123/"
FAKE_KEY = "sk-test-SECRET-KEY-should-never-leak-123"
BACKEND = ("https://api.groq.com/openai/v1/audio/transcriptions", FAKE_KEY,
           "whisper-large-v3")

REQUIRED_TOP_KEYS = {
    "schema_version", "source", "source_access", "video_path", "work_dir",
    "work_dir_owned", "status", "warnings", "title", "uploader", "uploader_id",
    "upload_date", "duration_sec", "location", "description",
    "comments_total_on_post", "comments_fetched", "comments", "flagged_comments",
    "profile_posts", "frames", "frame_count", "audio",
}
AUDIO_KEYS = {"enabled", "provider", "uploaded", "path", "transcript"}


class _IngestCase(unittest.TestCase):
    """Base with persistent temp dirs (cleaned in tearDown, not before asserts)."""

    def tmpdir(self):
        d = tempfile.mkdtemp(prefix="iss-test-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return d

    def fresh_out(self):
        """A not-yet-existing --out-dir path (so the tool owns it)."""
        return os.path.join(self.tmpdir(), "work")

    def local_video(self):
        p = os.path.join(self.tmpdir(), "clip.mp4")
        Path(p).write_bytes(b"LOCALVIDEO")
        return p


# ---------------------------------------------------------------------------
# R2 — non-destructive updates + workspace ownership
# ---------------------------------------------------------------------------
class TestR2Preservation(_IngestCase):
    def test_R2_failed_download_preserves_existing_files(self):
        out = os.path.join(self.tmpdir(), "existing")  # pre-existing (user) dir
        os.makedirs(os.path.join(out, "frames"))
        Path(out, "video.notes.txt").write_text("my notes")
        Path(out, "video.mp4").write_bytes(b"user video")
        Path(out, "frames", "f_001.jpg").write_bytes(b"user frame")

        fake = FakeProc(download_rc=1,
                        download_stderr="ERROR: Unable to download webpage: 404 Not Found")
        code, _out, _err = run_ingest([URL, "--out-dir", out], fake)

        self.assertEqual(code, 4)  # download failed → exit 4
        self.assertEqual(Path(out, "video.notes.txt").read_text(), "my notes")
        self.assertEqual(Path(out, "video.mp4").read_bytes(), b"user video")
        self.assertEqual(Path(out, "frames", "f_001.jpg").read_bytes(), b"user frame")


class TestR2Ownership(_IngestCase):
    def test_R2_work_dir_owned_true_for_created_out_dir(self):
        out = self.fresh_out()  # does not exist yet
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        self.assertTrue(read_report(out)["work_dir_owned"])
        self.assertTrue(read_manifest(out)["owned"])

    def test_R2_work_dir_owned_true_for_auto_tempdir(self):
        # No --out-dir → auto tempdir the tool creates → owned.
        code, out, _e = run_ingest([URL], FakeProc())
        self.assertEqual(code, 0)
        work_dir = None
        for line in out.splitlines():
            if line.startswith("work dir     : "):
                work_dir = line.split(" : ", 1)[1].split(" (owned=")[0]
        self.assertIsNotNone(work_dir)
        self.addCleanup(shutil.rmtree, work_dir, ignore_errors=True)
        self.assertTrue(read_report(work_dir)["work_dir_owned"])

    def test_R2_work_dir_owned_false_for_preexisting_out_dir(self):
        out = self.tmpdir()  # already exists → not owned
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        self.assertFalse(read_report(out)["work_dir_owned"])
        self.assertFalse(read_manifest(out)["owned"])


# ---------------------------------------------------------------------------
# R4 — cookies + audio are explicit opt-in
# ---------------------------------------------------------------------------
class TestR4CookiesAudioDefaults(_IngestCase):
    def test_R4_cookies_default_none_no_cookie_arg(self):
        fake = FakeProc()
        code, _o, _e = run_ingest([URL, "--out-dir", self.fresh_out()], fake)
        self.assertEqual(code, 0)
        for cmd in fake.calls:
            self.assertNotIn("--cookies-from-browser", cmd)

    def test_R4_source_access_anonymous(self):
        out = self.fresh_out()
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        self.assertEqual(read_report(out)["source_access"], "anonymous")

    def test_R4_source_access_local(self):
        out = self.fresh_out()
        code, _o, _e = run_ingest([self.local_video(), "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        self.assertEqual(read_report(out)["source_access"], "local")

    def test_R4_source_access_cookie_assisted(self):
        # Anonymous hits a login wall; explicit --cookies-browser triggers a
        # retry that succeeds → cookie-assisted, and it IS surfaced.
        out = self.fresh_out()
        fake = FakeProc(anon_login_wall=True, cookie_retry_rc=0)
        code, stdout, _e = run_ingest(
            [URL, "--out-dir", out, "--cookies-browser", "chrome"], fake)
        self.assertEqual(code, 0)
        self.assertEqual(read_report(out)["source_access"], "cookie-assisted")
        self.assertIn("cookie-assisted", stdout)
        cookie_calls = [c for c in fake.calls if "--cookies-from-browser" in c]
        self.assertEqual(len(cookie_calls), 1)
        self.assertIn("chrome", cookie_calls[0])

    def test_R4_audio_off_by_default_no_extraction_no_transcribe(self):
        # A Whisper key is present in the environment, but without --audio there
        # must be ZERO audio extraction and ZERO transcribe HTTP call.
        urlopen = mock.MagicMock()
        out = self.fresh_out()
        fake = FakeProc()
        code, stdout, _e = run_ingest(
            [URL, "--out-dir", out], fake, urlopen=urlopen,
            env={"GROQ_API_KEY": FAKE_KEY})
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        for cmd in fake.calls:
            self.assertNotIn("-vn", cmd)  # -vn == audio-only extraction
        rep = read_report(out)
        self.assertFalse(rep["audio"]["enabled"])
        self.assertFalse(rep["audio"]["uploaded"])
        self.assertIsNone(rep["audio"]["provider"])
        self.assertNotIn(FAKE_KEY, stdout)

    def test_R4_no_audio_flag_prints_deprecation_note_and_succeeds(self):
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out(), "--no-audio"],
                                   FakeProc())
        self.assertEqual(code, 0)
        self.assertIn("--no-audio is deprecated", err)


# ---------------------------------------------------------------------------
# R5 — versioned report.json schema
# ---------------------------------------------------------------------------
class TestR5ReportSchema(_IngestCase):
    def _assert_schema(self, rep):
        self.assertEqual(set(rep.keys()), REQUIRED_TOP_KEYS)
        self.assertEqual(rep["schema_version"], 1)
        self.assertEqual(set(rep["audio"].keys()), AUDIO_KEYS)
        self.assertEqual(rep["frame_count"], len(rep["frames"]))

    def test_R5_schema_keys_url_input(self):
        out = self.fresh_out()
        info = {"title": "t", "uploader": "u", "uploader_id": "uid",
                "description": "cap", "comment_count": 3}
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc(info=info))
        self.assertEqual(code, 0)
        self._assert_schema(read_report(out))

    def test_R5_schema_keys_local_input(self):
        out = self.fresh_out()
        code, _o, _e = run_ingest([self.local_video(), "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        rep = read_report(out)
        self._assert_schema(rep)
        self.assertEqual(rep["source_access"], "local")

    def test_R5_video_path_matches_dynamic_ext(self):
        # Never assume .mp4 — a .webm download must be recorded as video.webm.
        out = self.fresh_out()
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc(video_ext="webm"))
        self.assertEqual(code, 0)
        rep = read_report(out)
        self.assertTrue(rep["video_path"].endswith(os.sep + "video.webm"))
        self.assertTrue(os.path.isfile(rep["video_path"]))

    def test_R5_video_path_local_is_the_source_file(self):
        out = self.fresh_out()
        src = self.local_video()
        code, _o, _e = run_ingest([src, "--out-dir", out], FakeProc())
        self.assertEqual(code, 0)
        self.assertEqual(read_report(out)["video_path"], os.path.abspath(src))

    def test_R5_frame_count_matches_frames_len(self):
        out = self.fresh_out()
        code, _o, _e = run_ingest([URL, "--out-dir", out], FakeProc(frames=8))
        self.assertEqual(code, 0)
        rep = read_report(out)
        self.assertEqual(rep["frame_count"], len(rep["frames"]))
        self.assertEqual(rep["frame_count"], 8)

    def test_R5_partial_status_and_warning_on_degradation(self):
        # --audio requested but no key configured → non-fatal degradation.
        out = self.fresh_out()
        with mock.patch.object(ingest, "whisper_backend", return_value=None):
            code, _o, _e = run_ingest([URL, "--out-dir", out, "--audio"], FakeProc())
        self.assertEqual(code, 0)
        rep = read_report(out)
        self.assertEqual(rep["status"], "partial")
        self.assertTrue(rep["warnings"])
        self.assertTrue(any("audio" in w.lower() for w in rep["warnings"]))


# ---------------------------------------------------------------------------
# R6 — failure / timeout / resource contract
# ---------------------------------------------------------------------------
class TestR6TimeoutsAndResources(_IngestCase):
    def test_R6_download_timeout_exit_4(self):
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out()],
                                   FakeProc(timeout_on="download"))
        self.assertEqual(code, 4)
        self.assertIn("timed out", err)

    def test_R6_probe_timeout_exit_4(self):
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out()],
                                   FakeProc(timeout_on="probe"))
        self.assertEqual(code, 4)
        self.assertIn("timed out", err)

    def test_R6_frame_timeout_exit_5(self):
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out()],
                                   FakeProc(timeout_on="frame"))
        self.assertEqual(code, 5)
        self.assertIn("timed out", err)

    def test_R6_audio_timeout_is_non_fatal_partial(self):
        out = self.fresh_out()
        with mock.patch.object(ingest, "whisper_backend", return_value=BACKEND):
            code, _o, _e = run_ingest([URL, "--out-dir", out, "--audio"],
                                      FakeProc(timeout_on="audio"))
        self.assertEqual(code, 0)  # audio timeout must NOT be fatal
        rep = read_report(out)
        self.assertEqual(rep["status"], "partial")
        self.assertTrue(any("audio" in w.lower() for w in rep["warnings"]))

    def test_R6_empty_frames_exit_5(self):
        # ffmpeg returns 0 but produces zero f_*.jpg → hard failure.
        code, _o, err = run_ingest([URL, "--out-dir", self.fresh_out()],
                                   FakeProc(frames=0, frame_rc=0))
        self.assertEqual(code, 5)
        self.assertIn("no frames", err)

    def test_R6_positive_float_nan_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_float("nan")

    def test_R6_positive_float_inf_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_float("inf")

    def test_R6_positive_float_neg_inf_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_float("-inf")

    def test_R6_max_frames_caps_on_disk_frames(self):
        # A high --fps yields many staged frames; --max-frames must cap the
        # files actually left on disk, not just the report list.
        out = self.fresh_out()
        code, _o, _e = run_ingest(
            [URL, "--out-dir", out, "--max-frames", "5", "--fps", "30"],
            FakeProc(frames=30))
        self.assertEqual(code, 0)
        jpgs = [f for f in os.listdir(os.path.join(out, "frames"))
                if f.startswith("f_") and f.endswith(".jpg")]
        self.assertEqual(len(jpgs), 5)
        self.assertEqual(read_report(out)["frame_count"], 5)


# ---------------------------------------------------------------------------
# R7 — Whisper key never in argv / stdout / stderr / report (stdlib urllib only)
# ---------------------------------------------------------------------------
class TestR7WhisperKeySafety(_IngestCase):
    def _run_audio(self, out, body=b"transcript from whisper"):
        urlopen = FakeUrlopen(body=body)
        fake = FakeProc()
        with mock.patch.object(ingest, "whisper_backend", return_value=BACKEND):
            code, stdout, stderr = run_ingest(
                [URL, "--out-dir", out, "--audio"], fake, urlopen=urlopen)
        return code, stdout, stderr, urlopen, fake

    def test_R7_transcribe_goes_through_stdlib_urllib(self):
        out = self.fresh_out()
        code, _o, _e, urlopen, _f = self._run_audio(out)
        self.assertEqual(code, 0)
        self.assertEqual(len(urlopen.requests), 1)
        self.assertEqual(urlopen.requests[0].get_method(), "POST")

    def test_R7_no_curl_subprocess_spawned(self):
        out = self.fresh_out()
        code, _o, _e, _u, fake = self._run_audio(out)
        self.assertEqual(code, 0)
        for cmd in fake.calls:
            self.assertNotEqual(os.path.basename(cmd[0]), "curl")

    def test_R7_key_travels_only_in_authorization_header(self):
        out = self.fresh_out()
        code, _o, _e, urlopen, _f = self._run_audio(out)
        self.assertEqual(code, 0)
        req = urlopen.requests[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer " + FAKE_KEY)
        # The key is not smuggled into the URL or the multipart body.
        self.assertNotIn(FAKE_KEY, req.full_url)
        body = req.data if isinstance(req.data, (bytes, bytearray)) else b""
        self.assertNotIn(FAKE_KEY.encode(), body)

    def test_R7_key_absent_from_argv_stdout_stderr_and_report(self):
        out = self.fresh_out()
        code, stdout, stderr, _u, fake = self._run_audio(out)
        self.assertEqual(code, 0)
        for cmd in fake.calls:  # no argv element contains the key
            for arg in cmd:
                self.assertNotIn(FAKE_KEY, arg)
        self.assertNotIn(FAKE_KEY, stdout)
        self.assertNotIn(FAKE_KEY, stderr)
        self.assertNotIn(FAKE_KEY, Path(out, "report.json").read_text())

    def test_R7_audio_success_records_provider_and_transcript(self):
        out = self.fresh_out()
        code, _o, _e, _u, _f = self._run_audio(out)
        self.assertEqual(code, 0)
        rep = read_report(out)
        self.assertTrue(rep["audio"]["enabled"])
        self.assertTrue(rep["audio"]["uploaded"])
        self.assertEqual(rep["audio"]["provider"], "groq")
        self.assertEqual(rep["audio"]["transcript"], "transcript from whisper")


# ---------------------------------------------------------------------------
# R9 — --comments 0 command construction
# ---------------------------------------------------------------------------
class TestR9CommentsConstruction(_IngestCase):
    def _download_cmd(self, fake):
        for cmd in fake.calls:
            if os.path.basename(cmd[0]) == "yt-dlp" and "-J" not in cmd:
                return cmd
        self.fail("no yt-dlp download command was issued")

    def test_R9_comments_zero_passes_no_write_comments(self):
        fake = FakeProc()
        code, _o, _e = run_ingest(
            [URL, "--out-dir", self.fresh_out(), "--comments", "0"], fake)
        self.assertEqual(code, 0)
        cmd = self._download_cmd(fake)
        self.assertIn("--no-write-comments", cmd)
        self.assertNotIn("--write-comments", cmd)

    def test_R9_comments_nonzero_passes_write_comments(self):
        fake = FakeProc()
        code, _o, _e = run_ingest(
            [URL, "--out-dir", self.fresh_out(), "--comments", "40"], fake)
        self.assertEqual(code, 0)
        cmd = self._download_cmd(fake)
        self.assertIn("--write-comments", cmd)
        self.assertNotIn("--no-write-comments", cmd)


if __name__ == "__main__":
    unittest.main()
