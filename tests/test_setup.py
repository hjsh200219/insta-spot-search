"""Characterization tests for setup.py: pure functions AND the host-mutating /
consent-gated / platform-dispatch branches (item h — these were previously
unverified at ~28% coverage).

stdlib `unittest` (+ `unittest.mock`) only, no pip deps. setup.py is not a
package, so we load it by path with importlib. These assert the CURRENT real
behavior of the code — if a test and the code disagree, the code wins (fix
the test, not setup.py).

Everything that could touch the real host (subprocess.run / brew / network)
is mocked. `subprocess.run` is asserted to be called ONLY when consent was
actually given (--yes or an interactive "y") — this is the security-relevant
invariant of the whole module (R9 consent gate).
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO = Path(__file__).resolve().parents[1]
_SETUP = _REPO / "skills" / "insta-spot-search" / "scripts" / "setup.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


setup = _load("iss_setup", _SETUP)


def _brew_present():
    """Patch shutil.which so only 'brew' resolves (to a fake path)."""
    return mock.patch.object(
        setup.shutil, "which",
        side_effect=lambda n: "/opt/homebrew/bin/brew" if n == "brew" else None,
    )


class TestBrewPkgs(unittest.TestCase):
    def test_ffprobe_and_ffmpeg_collapse_to_ffmpeg(self):
        # both binaries ship in the single `ffmpeg` brew formula → deduped.
        self.assertEqual(setup._brew_pkgs(["ffprobe", "ffmpeg"]), ["ffmpeg"])

    def test_ffprobe_alone_maps_to_ffmpeg(self):
        self.assertEqual(setup._brew_pkgs(["ffprobe"]), ["ffmpeg"])

    def test_ytdlp_maps_to_itself(self):
        self.assertEqual(setup._brew_pkgs(["yt-dlp"]), ["yt-dlp"])

    def test_all_three_missing(self):
        self.assertEqual(
            setup._brew_pkgs(["yt-dlp", "ffmpeg", "ffprobe"]),
            ["yt-dlp", "ffmpeg"],
        )

    def test_empty(self):
        self.assertEqual(setup._brew_pkgs([]), [])

    def test_order_preserved(self):
        # ffmpeg first, then yt-dlp — insertion order is preserved (not sorted).
        self.assertEqual(setup._brew_pkgs(["ffmpeg", "yt-dlp"]), ["ffmpeg", "yt-dlp"])


class TestRequiredBinaries(unittest.TestCase):
    def test_required_binaries_contract(self):
        # The setup preflight requires exactly these three external binaries.
        self.assertEqual(setup.REQUIRED_BINARIES, ["yt-dlp", "ffmpeg", "ffprobe"])


class TestStatus(unittest.TestCase):
    def test_status_shape(self):
        # _status() returns a dict with the fields SKILL.md/agents parse.
        s = setup._status()
        self.assertIn("status", s)
        self.assertIn("missing_binaries", s)
        self.assertIn("platform", s)
        self.assertIn(s["status"], ("ready", "needs_install"))
        self.assertIsInstance(s["missing_binaries"], list)


class TestInstallMacos(unittest.TestCase):
    """_install_macos: brew-absent hint, brew-present success/failure, and the
    exact `brew install <pkgs>` argv built from _brew_pkgs(missing)."""

    def test_install_macos_no_brew(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(setup.shutil, "which", return_value=None))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            ok, msg = setup._install_macos(["yt-dlp", "ffmpeg"], auto_yes=True)
        self.assertFalse(ok)
        self.assertIn("Homebrew not installed", msg)
        self.assertIn("https://brew.sh", msg)
        # falls back to a manual-install hint built from _brew_pkgs, not raw `missing`.
        self.assertIn("brew install " + " ".join(setup._brew_pkgs(["yt-dlp", "ffmpeg"])), msg)
        run_mock.assert_not_called()

    def test_install_macos_brew_present_success(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            run_mock = stack.enter_context(mock.patch.object(
                setup.subprocess, "run",
                return_value=subprocess.CompletedProcess(["brew"], 0)))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            ok, msg = setup._install_macos(["ffmpeg", "ffprobe"], auto_yes=True)
        self.assertTrue(ok)
        self.assertEqual(msg, "installed via brew: ffmpeg")
        run_mock.assert_called_once_with(["brew", "install", "ffmpeg"])

    def test_install_macos_brew_present_failure(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(
                setup.subprocess, "run",
                return_value=subprocess.CompletedProcess(["brew"], 1)))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            ok, msg = setup._install_macos(["yt-dlp"], auto_yes=True)
        self.assertFalse(ok)
        self.assertEqual(msg, "brew install failed")

    def test_install_macos_brew_argv_built_from_brew_pkgs(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            run_mock = stack.enter_context(mock.patch.object(
                setup.subprocess, "run",
                return_value=subprocess.CompletedProcess(["brew"], 0)))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            setup._install_macos(["yt-dlp", "ffmpeg", "ffprobe"], auto_yes=True)
        expected = ["brew", "install", *setup._brew_pkgs(["yt-dlp", "ffmpeg", "ffprobe"])]
        run_mock.assert_called_once_with(expected)


class TestConsentGate(unittest.TestCase):
    """R9: `brew install` is a host mutation — it must NEVER run without
    explicit consent (--yes, or an interactive 'y'). subprocess.run-never-
    called-without-consent is asserted explicitly in every refusal path."""

    def test_consent_gate_non_tty_refuses(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(sys.stdin, "isatty", return_value=False))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stderr(err))
            ok, msg = setup._install_macos(["ffmpeg"], auto_yes=False)
        self.assertFalse(ok)
        self.assertIn("consent required", msg)
        self.assertIn("re-run with --yes", msg)
        stderr_out = err.getvalue()
        self.assertIn("brew install ffmpeg", stderr_out)
        self.assertIn("re-run with --yes", stderr_out)
        run_mock.assert_not_called()

    def test_consent_gate_tty_user_declines(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(sys.stdin, "isatty", return_value=True))
            stack.enter_context(mock.patch("builtins.input", return_value="n"))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            ok, msg = setup._install_macos(["ffmpeg"], auto_yes=False)
        self.assertFalse(ok)
        self.assertEqual(msg, "install declined by user")
        run_mock.assert_not_called()

    def test_consent_gate_tty_eof_treated_as_decline(self):
        # input() raising EOFError (e.g. stdin closed mid-prompt) must be
        # treated as a refusal, not propagate and crash the installer.
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(sys.stdin, "isatty", return_value=True))
            stack.enter_context(mock.patch("builtins.input", side_effect=EOFError))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            ok, msg = setup._install_macos(["ffmpeg"], auto_yes=False)
        self.assertFalse(ok)
        self.assertEqual(msg, "install declined by user")
        run_mock.assert_not_called()

    def test_consent_gate_tty_user_accepts(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(sys.stdin, "isatty", return_value=True))
            stack.enter_context(mock.patch("builtins.input", return_value="y"))
            run_mock = stack.enter_context(mock.patch.object(
                setup.subprocess, "run",
                return_value=subprocess.CompletedProcess(["brew"], 0)))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            ok, msg = setup._install_macos(["ffmpeg"], auto_yes=False)
        self.assertTrue(ok)
        self.assertEqual(msg, "installed via brew: ffmpeg")
        run_mock.assert_called_once_with(["brew", "install", "ffmpeg"])

    def test_consent_gate_yes_flag_skips_prompt(self):
        # --yes must bypass the prompt entirely — input() must not even be
        # invoked (a call would raise here and fail the test).
        with contextlib.ExitStack() as stack:
            stack.enter_context(_brew_present())
            stack.enter_context(mock.patch.object(sys.stdin, "isatty", return_value=True))
            stack.enter_context(mock.patch(
                "builtins.input",
                side_effect=AssertionError("input() must not be called with --yes")))
            run_mock = stack.enter_context(mock.patch.object(
                setup.subprocess, "run",
                return_value=subprocess.CompletedProcess(["brew"], 0)))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            ok, msg = setup._install_macos(["ffmpeg"], auto_yes=True)
        self.assertTrue(ok)
        run_mock.assert_called_once_with(["brew", "install", "ffmpeg"])


class TestHints(unittest.TestCase):
    """_hint_linux / _hint_windows: exact package-specific hint strings."""

    def test_hint_linux_all_missing(self):
        hint = setup._hint_linux(["yt-dlp", "ffmpeg", "ffprobe"])
        expected = (
            "ffmpeg: `sudo apt install ffmpeg` (or `sudo dnf install ffmpeg`)\n  "
            "yt-dlp: `pipx install yt-dlp` (or `pip install --user yt-dlp`)"
        )
        self.assertEqual(hint, expected)

    def test_hint_linux_ffmpeg_only(self):
        hint = setup._hint_linux(["ffmpeg", "ffprobe"])
        self.assertEqual(hint, "ffmpeg: `sudo apt install ffmpeg` (or `sudo dnf install ffmpeg`)")

    def test_hint_linux_ytdlp_only(self):
        hint = setup._hint_linux(["yt-dlp"])
        self.assertEqual(hint, "yt-dlp: `pipx install yt-dlp` (or `pip install --user yt-dlp`)")

    def test_hint_windows_all_missing(self):
        hint = setup._hint_windows(["yt-dlp", "ffmpeg", "ffprobe"])
        expected = (
            "ffmpeg: `winget install Gyan.FFmpeg`\n  "
            "yt-dlp: `winget install yt-dlp.yt-dlp` (or `pip install --user yt-dlp`)"
        )
        self.assertEqual(hint, expected)

    def test_hint_windows_ffmpeg_only(self):
        hint = setup._hint_windows(["ffmpeg", "ffprobe"])
        self.assertEqual(hint, "ffmpeg: `winget install Gyan.FFmpeg`")

    def test_hint_windows_ytdlp_only(self):
        hint = setup._hint_windows(["yt-dlp"])
        self.assertEqual(
            hint, "yt-dlp: `winget install yt-dlp.yt-dlp` (or `pip install --user yt-dlp`)")


class TestCmdCheck(unittest.TestCase):
    def test_cmd_check_ready_is_silent_exit_0(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(setup, "missing_binaries", return_value=[]))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_check()
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_cmd_check_missing_exits_2_with_hint(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["ffmpeg", "ffprobe"]))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_check()
        self.assertEqual(code, 2)
        self.assertIn("missing binaries: ffmpeg, ffprobe", err.getvalue())
        self.assertIn("setup.py", err.getvalue())


class TestCmdJson(unittest.TestCase):
    def test_cmd_json_ready(self):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(setup, "missing_binaries", return_value=[]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Darwin"))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = setup.cmd_json()
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload, {"status": "ready", "missing_binaries": [], "platform": "Darwin"})

    def test_cmd_json_needs_install(self):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["yt-dlp"]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Linux"))
            stack.enter_context(contextlib.redirect_stdout(out))
            code = setup.cmd_json()
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            payload,
            {"status": "needs_install", "missing_binaries": ["yt-dlp"], "platform": "Linux"})


class TestCmdInstall(unittest.TestCase):
    """cmd_install dispatch: all-present short-circuit, and per-platform
    routing (Darwin -> _install_macos, Linux/Windows/other -> print-only
    hints, never installing)."""

    def test_cmd_install_all_present(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(setup, "missing_binaries", return_value=[]))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install()
        self.assertEqual(code, 0)
        self.assertIn("all dependencies present", err.getvalue())
        self.assertIn("ready", err.getvalue())
        run_mock.assert_not_called()

    def test_cmd_install_darwin_dispatches_to_install_macos(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", side_effect=[["ffmpeg"], []]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Darwin"))
            install_mock = stack.enter_context(mock.patch.object(
                setup, "_install_macos", return_value=(True, "installed via brew: ffmpeg")))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install(auto_yes=True)
        self.assertEqual(code, 0)
        install_mock.assert_called_once_with(["ffmpeg"], True)
        self.assertIn("ready. insta-spot-search is fully set up.", err.getvalue())

    def test_cmd_install_darwin_still_missing_after_install(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", side_effect=[["ffmpeg"], ["ffmpeg"]]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Darwin"))
            stack.enter_context(mock.patch.object(
                setup, "_install_macos", return_value=(True, "installed via brew: ffmpeg")))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install(auto_yes=True)
        self.assertEqual(code, 2)
        self.assertIn("still missing after install: ffmpeg", err.getvalue())

    def test_cmd_install_darwin_install_declined_or_failed(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["ffmpeg"]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Darwin"))
            stack.enter_context(mock.patch.object(
                setup, "_install_macos", return_value=(False, "brew install failed")))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install()
        self.assertEqual(code, 2)
        self.assertIn("brew install failed", err.getvalue())

    def test_cmd_install_linux_hint(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["yt-dlp", "ffmpeg"]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Linux"))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install()
        self.assertEqual(code, 2)
        self.assertIn("dependencies missing on Linux", err.getvalue())
        self.assertIn(setup._hint_linux(["yt-dlp", "ffmpeg"]), err.getvalue())
        run_mock.assert_not_called()

    def test_cmd_install_windows_hint(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["ffmpeg"]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="Windows"))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install()
        self.assertEqual(code, 2)
        self.assertIn("dependencies missing on Windows", err.getvalue())
        self.assertIn(setup._hint_windows(["ffmpeg"]), err.getvalue())
        run_mock.assert_not_called()

    def test_cmd_install_unsupported_platform(self):
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                setup, "missing_binaries", return_value=["ffmpeg"]))
            stack.enter_context(mock.patch.object(
                setup.platform, "system", return_value="FreeBSD"))
            run_mock = stack.enter_context(mock.patch.object(setup.subprocess, "run"))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = setup.cmd_install()
        self.assertEqual(code, 2)
        self.assertIn("unsupported platform (FreeBSD)", err.getvalue())
        self.assertIn("install manually: ffmpeg", err.getvalue())
        run_mock.assert_not_called()


class TestMainDispatch(unittest.TestCase):
    """main(): routes --check/--json/bare/--yes to the right cmd_* and
    propagates its return code."""

    def test_main_check_dispatch(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--check"]))
            m = stack.enter_context(mock.patch.object(setup, "cmd_check", return_value=0))
            code = setup.main()
        self.assertEqual(code, 0)
        m.assert_called_once_with()

    def test_main_json_dispatch(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--json"]))
            m = stack.enter_context(mock.patch.object(setup, "cmd_json", return_value=0))
            code = setup.main()
        self.assertEqual(code, 0)
        m.assert_called_once_with()

    def test_main_bare_dispatches_install_without_auto_yes(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py"]))
            m = stack.enter_context(mock.patch.object(setup, "cmd_install", return_value=0))
            code = setup.main()
        self.assertEqual(code, 0)
        m.assert_called_once_with(auto_yes=False)

    def test_main_yes_flag_dispatches_install_with_auto_yes(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--yes"]))
            m = stack.enter_context(mock.patch.object(setup, "cmd_install", return_value=0))
            code = setup.main()
        self.assertEqual(code, 0)
        m.assert_called_once_with(auto_yes=True)

    def test_main_propagates_nonzero_exit_code(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--check"]))
            stack.enter_context(mock.patch.object(setup, "cmd_check", return_value=2))
            code = setup.main()
        self.assertEqual(code, 2)

    def test_main_unknown_flag_is_usage_error_never_installs(self):
        # A typo of --check must NOT fall through into installer mode.
        err = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--chekc"]))
            install_mock = stack.enter_context(
                mock.patch.object(setup, "cmd_install", return_value=0))
            stack.enter_context(contextlib.redirect_stderr(err))
            with self.assertRaises(SystemExit) as cm:
                setup.main()
        self.assertEqual(cm.exception.code, 2)
        install_mock.assert_not_called()

    def test_main_help_exits_0_never_installs(self):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", ["setup.py", "--help"]))
            install_mock = stack.enter_context(
                mock.patch.object(setup, "cmd_install", return_value=0))
            stack.enter_context(contextlib.redirect_stdout(out))
            with self.assertRaises(SystemExit) as cm:
                setup.main()
        self.assertEqual(cm.exception.code, 0)
        install_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
