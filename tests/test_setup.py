"""Characterization tests for the pure functions in setup.py.

stdlib `unittest` only (no pip deps). setup.py is not a package, so we load it
by path with importlib. These assert the CURRENT real behavior of the code.
"""
import importlib.util
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SETUP = _REPO / "skills" / "insta-spot-search" / "scripts" / "setup.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


setup = _load("iss_setup", _SETUP)


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


if __name__ == "__main__":
    unittest.main()
