"""Shared test harness for the v0.4.x regression suite (R8).

stdlib only (unittest.mock / io / subprocess / tempfile). No network, no real
API keys, no real browser cookies. The scripts are loaded by PATH (they are not
a package) with importlib, reusing the pattern from the existing tests.

Nothing here is collected by ``unittest discover`` — the filename does not match
``test*.py`` — so this is a plain helper module the test files import.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "insta-spot-search"
SCRIPTS = SKILL / "scripts"
INGEST_PY = SCRIPTS / "ingest.py"
LOOKUP_PY = SCRIPTS / "lookup.py"
SETUP_PY = SCRIPTS / "setup.py"
SKILL_MD = SKILL / "SKILL.md"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Loaded once for the whole suite. Distinct names avoid clashing with the
# characterization tests that load the same files under other names.
ingest = load_module("iss_ingest_contract", INGEST_PY)
lookup = load_module("iss_lookup", LOOKUP_PY)


# ---------------------------------------------------------------------------
# Fake subprocess.run for ingest.py — simulates yt-dlp / ffprobe / ffmpeg.
# Records every argv so tests can assert on the exact command lines built,
# and can inject a per-stage TimeoutExpired.
# ---------------------------------------------------------------------------
class FakeProc:
    def __init__(self, *, video_ext="mp4", duration="12.5",
                 write_info=True, info=None, frames=10,
                 download_rc=0, download_stderr="",
                 anon_login_wall=False, cookie_retry_rc=0,
                 frame_rc=0, frame_stderr="", audio_rc=0,
                 profile_rc=0, profile_stdout="{}",
                 timeout_on=None):
        self.video_ext = video_ext
        self.duration = duration
        self.write_info = write_info
        self.info = {} if info is None else info
        self.frames = frames
        self.download_rc = download_rc
        self.download_stderr = download_stderr
        self.anon_login_wall = anon_login_wall
        self.cookie_retry_rc = cookie_retry_rc
        self.frame_rc = frame_rc
        self.frame_stderr = frame_stderr
        self.audio_rc = audio_rc
        self.profile_rc = profile_rc
        self.profile_stdout = profile_stdout
        self.timeout_on = timeout_on
        self.calls = []

    # subprocess.run(cmd, capture_output=True, text=True, timeout=...)
    def __call__(self, cmd, *args, **kwargs):
        cmd = list(cmd)
        self.calls.append(cmd)
        timeout = kwargs.get("timeout")
        prog = os.path.basename(cmd[0])
        if prog == "yt-dlp":
            return self._ytdlp(cmd, timeout)
        if prog == "ffprobe":
            return self._ffprobe(cmd, timeout)
        if prog == "ffmpeg":
            return self._ffmpeg(cmd, timeout)
        raise AssertionError(f"unexpected subprocess call: {cmd!r}")

    @staticmethod
    def _cp(cmd, rc, out="", err=""):
        return subprocess.CompletedProcess(cmd, rc, out, err)

    def _ytdlp(self, cmd, timeout):
        if "-J" in cmd:  # profile scan
            return self._cp(cmd, self.profile_rc, self.profile_stdout, "")
        cookie_retry = "--cookies-from-browser" in cmd
        if not cookie_retry:
            if self.timeout_on == "download":
                raise subprocess.TimeoutExpired(cmd, timeout)
            if self.anon_login_wall:
                return self._cp(cmd, 1, "",
                                "ERROR: HTTP Error 403: Forbidden — login required")
            if self.download_rc != 0:
                return self._cp(cmd, self.download_rc, "", self.download_stderr)
        elif self.cookie_retry_rc != 0:
            return self._cp(cmd, self.cookie_retry_rc, "", self.download_stderr)
        # success → create the video file + info.json from the -o template
        tmpl = cmd[cmd.index("-o") + 1]
        vpath = tmpl.replace("%(ext)s", self.video_ext)
        Path(vpath).parent.mkdir(parents=True, exist_ok=True)
        Path(vpath).write_bytes(b"FAKE-VIDEO-BYTES")
        if self.write_info:
            info_path = os.path.join(os.path.dirname(tmpl), "video.info.json")
            with open(info_path, "w") as f:
                json.dump(self.info, f)
        return self._cp(cmd, 0, "", "")

    def _ffprobe(self, cmd, timeout):
        if self.timeout_on == "probe":
            raise subprocess.TimeoutExpired(cmd, timeout)
        return self._cp(cmd, 0, f"{self.duration}\n", "")

    def _ffmpeg(self, cmd, timeout):
        if "-vn" in cmd:  # audio extraction
            if self.timeout_on == "audio":
                raise subprocess.TimeoutExpired(cmd, timeout)
            if self.audio_rc == 0:
                Path(cmd[-1]).write_bytes(b"FAKE-AUDIO")
            return self._cp(cmd, self.audio_rc, "", "")
        # frame extraction: last arg is .../f_%03d.jpg
        if self.timeout_on == "frame":
            raise subprocess.TimeoutExpired(cmd, timeout)
        frames_dir = os.path.dirname(cmd[-1])
        Path(frames_dir).mkdir(parents=True, exist_ok=True)
        for i in range(1, self.frames + 1):
            Path(os.path.join(frames_dir, f"f_{i:03d}.jpg")).write_bytes(b"JPGDATA")
        return self._cp(cmd, self.frame_rc, "", self.frame_stderr)


@contextlib.contextmanager
def _env_overrides(env):
    saved = {}
    if env:
        for k, v in env.items():
            saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_ingest(argv, fake, urlopen=None, env=None):
    """Drive ingest.main() with a faked subprocess/urllib layer.

    Returns (exit_code, stdout, stderr). exit_code is 0 on a clean return.
    """
    out, err = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    sys.argv = ["ingest.py"] + list(argv)
    code = 0
    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(_env_overrides(env))
            stack.enter_context(mock.patch.object(ingest.subprocess, "run", fake))
            stack.enter_context(mock.patch.object(
                ingest.shutil, "which", side_effect=lambda n: "/usr/bin/" + n))
            if urlopen is not None:
                stack.enter_context(mock.patch.object(
                    ingest.urllib.request, "urlopen", urlopen))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            try:
                ingest.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue()


def read_report(work_dir):
    with open(os.path.join(work_dir, "report.json")) as f:
        return json.load(f)


def read_manifest(work_dir):
    with open(os.path.join(work_dir, ".insta-spot-manifest.json")) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fake urllib for the transcription HTTP call (ingest.transcribe).
# ---------------------------------------------------------------------------
class _CtxBody:
    def __init__(self, body):
        self._body = body

    def read(self, *a):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeUrlopen:
    """Captures the urllib Request (so tests can inspect headers) and returns
    a canned response body. Records nothing on the wire."""

    def __init__(self, body=b"a whisper transcript"):
        self.body = body
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return _CtxBody(self.body)


# ---------------------------------------------------------------------------
# Fake urllib opener for lookup.py (build_opener(...).open()).
# ---------------------------------------------------------------------------
class FakeHeaders:
    def __init__(self, d):
        self._d = {k.lower(): v for k, v in (d or {}).items()}

    def get(self, name, default=None):
        return self._d.get(name.lower(), default)


class FakeResp:
    def __init__(self, body=b"", headers=None, status=200):
        self._buf = io.BytesIO(body)
        self.headers = FakeHeaders(headers)
        self.status = status

    def read(self, size=-1):
        if size is None or size < 0:
            return self._buf.read()
        return self._buf.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """Stand-in for build_opener(...). ``resp_factory(req)`` returns a FakeResp
    or raises (e.g. lookup._SchemeError) to simulate a rejected redirect."""

    def __init__(self, resp_factory):
        self._factory = resp_factory
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        return self._factory(req)


def run_lookup(argv, opener=None):
    """Drive lookup.main(). Returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    sys.argv = ["lookup.py"] + list(argv)
    code = 0
    try:
        with contextlib.ExitStack() as stack:
            if opener is not None:
                stack.enter_context(mock.patch.object(
                    lookup.urllib.request, "build_opener", return_value=opener))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            try:
                lookup.main()
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue()
