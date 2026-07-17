"""Characterization tests for the pure functions in ingest.py.

stdlib `unittest` only (no pip deps). ingest.py is not a package, so we load it
by path with importlib. These assert the CURRENT real behavior of the code, not a
new spec — if a test and the code disagree, the code wins (fix the test).
"""
import argparse
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INGEST = _REPO / "skills" / "insta-spot-search" / "scripts" / "ingest.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ingest = _load("iss_ingest", _INGEST)


class TestParseTs(unittest.TestCase):
    def test_plain_seconds(self):
        self.assertEqual(ingest.parse_ts("90"), 90.0)

    def test_mm_ss(self):
        self.assertEqual(ingest.parse_ts("1:30"), 90.0)

    def test_hh_mm_ss(self):
        self.assertEqual(ingest.parse_ts("1:00:00"), 3600.0)

    def test_zero_ok(self):
        self.assertEqual(ingest.parse_ts("0"), 0.0)

    def test_fractional(self):
        self.assertEqual(ingest.parse_ts("1:30.5"), 90.5)

    def test_too_many_parts_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.parse_ts("1:2:3:4")

    def test_non_numeric_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.parse_ts("abc")

    def test_empty_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.parse_ts("")

    def test_negative_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.parse_ts("-5")


class TestValidators(unittest.TestCase):
    def test_positive_int_valid(self):
        self.assertEqual(ingest.positive_int("5"), 5)

    def test_positive_int_zero_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_int("0")

    def test_positive_int_negative_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_int("-3")

    def test_positive_float_valid(self):
        self.assertEqual(ingest.positive_float("1.5"), 1.5)

    def test_positive_float_zero_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_float("0")

    def test_positive_float_negative_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.positive_float("-2.0")

    def test_nonneg_int_zero_ok(self):
        # nonneg_int accepts 0 (unlike positive_int) — this is the documented contract.
        self.assertEqual(ingest.nonneg_int("0"), 0)

    def test_nonneg_int_valid(self):
        self.assertEqual(ingest.nonneg_int("40"), 40)

    def test_nonneg_int_negative_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            ingest.nonneg_int("-1")


class TestLoginWallPat(unittest.TestCase):
    def test_matches_http_403(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("ERROR: HTTP Error 403: Forbidden"))

    def test_matches_http_401(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("HTTP Error 401 Unauthorized"))

    def test_matches_login_required(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("login required to view this"))

    def test_matches_rate_limit(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("You have been rate-limited"))

    def test_matches_empty_media_response(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("empty media response"))

    def test_matches_restricted(self):
        self.assertTrue(ingest.LOGIN_WALL_PAT.search("This content is restricted"))

    def test_does_not_match_benign(self):
        self.assertIsNone(ingest.LOGIN_WALL_PAT.search("video downloaded successfully"))


class TestCookieErrPat(unittest.TestCase):
    def test_matches_cookie_database(self):
        self.assertTrue(ingest.COOKIE_ERR_PAT.search("could not read cookie database"))

    def test_matches_keyring(self):
        self.assertTrue(ingest.COOKIE_ERR_PAT.search("failed to unlock the keyring"))

    def test_matches_not_supported(self):
        self.assertTrue(ingest.COOKIE_ERR_PAT.search("not supported for cookies"))

    def test_does_not_match_benign(self):
        self.assertIsNone(ingest.COOKIE_ERR_PAT.search("everything is fine"))


class TestPlaceWordPat(unittest.TestCase):
    def test_matches_beach(self):
        self.assertTrue(ingest.PLACE_WORD_PAT.search("여기 협재해수욕장 맞나요?"))

    def test_matches_glamping(self):
        self.assertTrue(ingest.PLACE_WORD_PAT.search("가야글램핑 다녀왔어요"))

    def test_matches_camping(self):
        self.assertTrue(ingest.PLACE_WORD_PAT.search("소풍캠핑장 후기"))

    def test_does_not_match_benign(self):
        # No place-suffix token present → no match.
        self.assertIsNone(ingest.PLACE_WORD_PAT.search("정말 좋아요 최고예요"))


class TestRegionPat(unittest.TestCase):
    def test_matches_metro(self):
        self.assertTrue(ingest.REGION_PAT.search("부산 여행 다녀옴"))

    def test_matches_province(self):
        self.assertTrue(ingest.REGION_PAT.search("강원 쪽이에요"))

    def test_matches_eup_myeon_dong(self):
        self.assertTrue(ingest.REGION_PAT.search("제주시 애월읍 근처"))

    def test_does_not_match_benign(self):
        self.assertIsNone(ingest.REGION_PAT.search("맛있어 보여요"))


class TestOverseasPat(unittest.TestCase):
    def test_matches_danang(self):
        self.assertTrue(ingest.OVERSEAS_PAT.search("다낭 진짜 좋았어요"))

    def test_matches_bangkok(self):
        self.assertTrue(ingest.OVERSEAS_PAT.search("방콕 야시장 최고"))

    def test_matches_english_place(self):
        self.assertTrue(ingest.OVERSEAS_PAT.search("we went to Kata Beach yesterday"))

    def test_does_not_match_domestic(self):
        self.assertIsNone(ingest.OVERSEAS_PAT.search("서울 날씨 좋네요"))


class TestLoadEnvFile(unittest.TestCase):
    def test_parses_various_line_shapes(self):
        content = (
            "# a comment line\n"
            "\n"
            "GROQ_API_KEY=abc123\n"
            'export OPENAI_API_KEY="xyz789"\n'
            "QUOTED='single'\n"
            "WITHCOMMENT=value # trailing comment\n"
            "  SPACED = spaced_value \n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            env = ingest.load_env_file(path)
        finally:
            os.remove(path)
        self.assertEqual(env["GROQ_API_KEY"], "abc123")
        self.assertEqual(env["OPENAI_API_KEY"], "xyz789")
        self.assertEqual(env["QUOTED"], "single")
        self.assertEqual(env["WITHCOMMENT"], "value")
        self.assertEqual(env["SPACED"], "spaced_value")
        # comment/blank lines produce no keys
        self.assertNotIn("# a comment line", env)

    def test_missing_file_returns_empty(self):
        self.assertEqual(
            ingest.load_env_file("/nonexistent/definitely/not/here.env"), {}
        )


class TestFmtTs(unittest.TestCase):
    def test_round_trip_mm_ss(self):
        # fmt_ts is the inverse-ish of parse_ts for MM:SS values.
        self.assertEqual(ingest.fmt_ts(90), "01:30")
        self.assertEqual(ingest.fmt_ts(0), "00:00")


if __name__ == "__main__":
    unittest.main()
