"""R3 — lookup.py structured adapter: scheme, redirect, path-escape, content-type,
size cap, and injection-inert search terms.

lookup.py enforces HTTPS-only on the FIRST hop (``if scheme != "https": die(2)``).
A plain-HTTP localhost server can therefore never be reached by the real code
path, and stdlib cannot mint a trusted self-signed cert for an HTTPS localhost
server. So the network transport is mocked at ``urllib.request.build_opener``
(explicitly sanctioned: "Mock ... urllib where you must simulate ... HTTP") — the
scheme gate, Request construction, header wiring, redirect handling, Content-Type
check and streamed size cap all run for real; only the socket is a fake.
"""
import contextlib
import io
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling _harness
from _harness import FakeOpener, FakeResp, lookup, run_lookup


def _exit_code(fn, *args):
    """Call a die()-ing helper, swallow its stderr, return the SystemExit code."""
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            fn(*args)
        except SystemExit as e:
            return e.code
    return None

IMG_HEADERS = {"Content-Type": "image/jpeg"}
JSON_HEADERS = {"Content-Type": "application/json"}
JPEG_BODY = b"\xff\xd8\xff\xe0FAKEJPEG\xff\xd9"

# socket.getaddrinfo returns 5-tuples (family, type, proto, canonname, sockaddr).
# lookup._reject_if_internal reads sockaddr[0] (the IP string), so canned
# addrinfo lists are all we need — no real DNS, no real socket.
PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
LOOPBACK_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
METADATA_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
PRIVATE_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]
CGNAT_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("100.64.0.1", 0))]


def _json_opener():
    return FakeOpener(lambda req: FakeResp(b'{"documents":[]}', JSON_HEADERS))


class _PublicDNS(unittest.TestCase):
    """Default every resolved host to a public IP so the real code paths never
    touch real DNS and the SSRF guard admits the request. SSRF-specific tests
    override lookup.socket.getaddrinfo per-test."""

    def setUp(self):
        p = mock.patch.object(lookup.socket, "getaddrinfo",
                              return_value=PUBLIC_ADDRINFO)
        p.start()
        self.addCleanup(p.stop)


class TestR3SchemeAndRedirect(_PublicDNS):
    def test_R3_non_https_url_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "http://example.com/x.jpg", "--out-dir", d])
        self.assertEqual(code, 2)
        self.assertIn("non-https", err)

    def test_R3_missing_scheme_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "example.com/x.jpg", "--out-dir", d])
        self.assertEqual(code, 2)

    def test_R3_redirect_to_non_https_rejected(self):
        # A redirect that leaves HTTPS surfaces as _SchemeError inside _open,
        # which maps to exit 2.
        def factory(req):
            raise lookup._SchemeError("http")

        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d],
                opener=FakeOpener(factory))
        self.assertEqual(code, 2)
        self.assertIn("non-https redirect", err)

    def test_R3_redirect_handler_rejects_http_scheme(self):
        h = lookup.HttpsOnlyRedirectHandler()
        with self.assertRaises(lookup._SchemeError):
            h.redirect_request(None, None, 302, "Found", {}, "http://evil.example/x")

    def test_R3_redirect_handler_rejects_data_scheme(self):
        h = lookup.HttpsOnlyRedirectHandler()
        with self.assertRaises(lookup._SchemeError):
            h.redirect_request(None, None, 302, "Found", {}, "data:text/html,x")


class TestR3PathEscape(_PublicDNS):
    def test_R3_name_relative_escape_rejected(self):
        self.assertEqual(_exit_code(lookup._safe_name, "../x.jpg"), 2)

    def test_R3_name_absolute_rejected(self):
        self.assertEqual(_exit_code(lookup._safe_name, "/etc/passwd"), 2)

    def test_R3_name_dotdot_rejected(self):
        self.assertEqual(_exit_code(lookup._safe_name, ".."), 2)

    def test_R3_name_with_separator_rejected(self):
        self.assertEqual(_exit_code(lookup._safe_name, "sub/dir/x.jpg"), 2)

    def test_R3_fetch_image_relative_escape_name_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d,
                 "--name", "../escape.jpg"], opener=_json_opener())
        self.assertEqual(code, 2)

    def test_R3_resolve_dest_stays_inside_out_dir(self):
        with tempfile.TemporaryDirectory() as d:
            dest = lookup._resolve_dest(d, "cand_01.jpg")
            self.assertTrue(os.path.realpath(dest).startswith(os.path.realpath(d)))


class TestR3FetchImageValidation(_PublicDNS):
    def test_R3_non_image_content_type_rejected(self):
        opener = FakeOpener(lambda req: FakeResp(b"<html>", {"Content-Type": "text/html"}))
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "https://ok.example/x", "--out-dir", d], opener=opener)
        self.assertEqual(code, 2)
        self.assertIn("not an image", err)

    def test_R3_oversize_body_rejected(self):
        # Shrink the cap so the test body stays tiny and fast.
        opener = FakeOpener(lambda req: FakeResp(b"A" * 4096, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            old = lookup.MAX_IMAGE_BYTES
            lookup.MAX_IMAGE_BYTES = 1024
            try:
                code, _out, err = run_lookup(
                    ["fetch-image", "https://ok.example/big.jpg", "--out-dir", d],
                    opener=opener)
            finally:
                lookup.MAX_IMAGE_BYTES = old
        self.assertEqual(code, 2)
        self.assertIn("exceeds max size", err)

    def test_R3_oversize_body_not_written(self):
        opener = FakeOpener(lambda req: FakeResp(b"A" * 4096, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            old = lookup.MAX_IMAGE_BYTES
            lookup.MAX_IMAGE_BYTES = 1024
            try:
                run_lookup(["fetch-image", "https://ok.example/big.jpg",
                            "--out-dir", d, "--name", "cand_01.jpg"], opener=opener)
            finally:
                lookup.MAX_IMAGE_BYTES = old
            self.assertFalse(os.path.exists(os.path.join(d, "cand_01.jpg")))

    def test_R3_fetch_image_success_writes_file(self):
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            code, out, _err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d,
                 "--name", "cand_01.jpg"], opener=opener)
            # lookup prints the realpath-resolved dest (macOS /var -> /private/var).
            dest = os.path.realpath(os.path.join(d, "cand_01.jpg"))
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), dest)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), JPEG_BODY)

    def test_R3_fetch_image_sends_user_agent(self):
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            run_lookup(["fetch-image", "https://ok.example/x.jpg", "--out-dir", d],
                       opener=opener)
        self.assertEqual(opener.requests[0].get_header("User-agent"),
                         lookup.USER_AGENT)


class TestR3InjectionInertSearchTerms(_PublicDNS):
    def test_R3_leading_dash_query_is_inert_value(self):
        # "-rf" must be a positional search VALUE (via _preprocess_argv), not an
        # option and not a shell token — no argparse error, encoded into the URL.
        opener = _json_opener()
        code, _out, _err = run_lookup(["geocode-kakao", "-rf"], opener=opener)
        self.assertEqual(code, 0)
        self.assertIn("q=-rf", opener.requests[0].full_url)

    def test_R3_shell_metachars_are_urlencoded_not_executed(self):
        opener = _json_opener()
        code, _out, _err = run_lookup(
            ["geocode-kakao", "--limit=9; echo PWNED"], opener=opener)
        url = opener.requests[0].full_url
        self.assertEqual(code, 0)
        # semicolon + space are percent/plus encoded; nothing was shelled out.
        self.assertIn("echo+PWNED", url)
        self.assertIn("%3B", url)               # the ';' is encoded
        self.assertNotIn("; echo PWNED", url)   # never a raw shell fragment

    def test_R3_newline_in_query_is_inert(self):
        opener = _json_opener()
        code, _out, _err = run_lookup(["geocode-kakao", "a\nb"], opener=opener)
        self.assertEqual(code, 0)
        self.assertNotIn("\n", opener.requests[0].full_url)
        self.assertIn("a%0Ab", opener.requests[0].full_url)

    def test_R3_geocode_kakao_https_and_base_url(self):
        opener = _json_opener()
        old = os.environ.get("KSKILL_PROXY_BASE_URL")
        os.environ["KSKILL_PROXY_BASE_URL"] = "https://proxy.example"
        try:
            code, out, _err = run_lookup(["geocode-kakao", "카페"], opener=opener)
        finally:
            if old is None:
                os.environ.pop("KSKILL_PROXY_BASE_URL", None)
            else:
                os.environ["KSKILL_PROXY_BASE_URL"] = old
        url = opener.requests[0].full_url
        self.assertEqual(code, 0)
        self.assertTrue(url.startswith("https://proxy.example/v1/kakao-map/search/keyword?"))
        self.assertIn("q=", url)
        # geocode prints the parsed JSON to stdout
        self.assertIn("documents", out)

    def test_R3_geocode_nominatim_sets_user_agent_and_https(self):
        opener = FakeOpener(lambda req: FakeResp(b"[]", JSON_HEADERS))
        code, _out, _err = run_lookup(["geocode-nominatim", "Da Nang"], opener=opener)
        req = opener.requests[0]
        self.assertEqual(code, 0)
        self.assertTrue(req.full_url.startswith("https://nominatim.openstreetmap.org/search?"))
        self.assertEqual(req.get_header("User-agent"), lookup.USER_AGENT)


class TestSsrfGuard(unittest.TestCase):
    """Reject SSRF at internal/loopback/link-local/reserved addresses on the
    first hop and on redirects; still allow public addresses."""

    def _fetch(self, addrinfo, url="https://internal.example/x.jpg"):
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(lookup.socket, "getaddrinfo",
                                  return_value=addrinfo):
            return run_lookup(
                ["fetch-image", url, "--out-dir", d], opener=opener)

    def test_first_hop_loopback_rejected(self):
        code, _out, err = self._fetch(LOOPBACK_ADDRINFO)
        self.assertEqual(code, 2)
        self.assertIn("internal/reserved", err)

    def test_first_hop_metadata_endpoint_rejected(self):
        code, _out, err = self._fetch(METADATA_ADDRINFO)  # 169.254.169.254
        self.assertEqual(code, 2)
        self.assertIn("169.254.169.254", err)

    def test_first_hop_private_rejected(self):
        code, _out, _err = self._fetch(PRIVATE_ADDRINFO)  # 10.0.0.5
        self.assertEqual(code, 2)

    def test_first_hop_cgnat_shared_range_rejected(self):
        # 100.64.0.0/10 is neither is_private nor is_global — the guard rejects
        # every non-global range, not just RFC1918
        code, _out, err = self._fetch(CGNAT_ADDRINFO)
        self.assertEqual(code, 2)
        self.assertIn("100.64.0.1", err)

    def test_first_hop_public_allowed(self):
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(lookup.socket, "getaddrinfo",
                                  return_value=PUBLIC_ADDRINFO):
            code, out, _err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d,
                 "--name", "cand_01.jpg"], opener=opener)
            dest = os.path.realpath(os.path.join(d, "cand_01.jpg"))
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), dest)
            self.assertTrue(os.path.isfile(dest))

    def test_geocode_first_hop_internal_rejected(self):
        # Defense in depth: geocode hosts flow through _open too.
        with mock.patch.object(lookup.socket, "getaddrinfo",
                               return_value=LOOPBACK_ADDRINFO):
            code, _out, err = run_lookup(["geocode-kakao", "test"],
                                         opener=_json_opener())
        self.assertEqual(code, 2)
        self.assertIn("internal/reserved", err)

    def test_resolution_failure_exit_4(self):
        def boom(*_a, **_k):
            raise socket.gaierror("Name or service not known")

        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(lookup.socket, "getaddrinfo", side_effect=boom):
            code, _out, err = run_lookup(
                ["fetch-image", "https://nope.example/x.jpg", "--out-dir", d],
                opener=opener)
        self.assertEqual(code, 4)
        self.assertIn("could not resolve host", err)

    def test_redirect_handler_rejects_internal_ip(self):
        # The guard fires inside redirect_request, before the hop is followed.
        h = lookup.HttpsOnlyRedirectHandler()
        with mock.patch.object(lookup.socket, "getaddrinfo",
                               return_value=LOOPBACK_ADDRINFO):
            with self.assertRaises(lookup._AddressError):
                h.redirect_request(None, None, 302, "Found", {},
                                   "https://internal.example/y")

    def test_redirect_internal_surfaces_exit_2(self):
        # A redirect to an internal host surfaces from _open as exit 2. The
        # first hop resolves public; the opener raises _AddressError to mimic
        # the redirect handler rejecting the next hop.
        def factory(req):
            raise lookup._AddressError("127.0.0.1")

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(lookup.socket, "getaddrinfo",
                                  return_value=PUBLIC_ADDRINFO):
            code, _out, err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d],
                opener=FakeOpener(factory))
        self.assertEqual(code, 2)
        self.assertIn("internal/reserved", err)


class TestFetchImageDashGuard(_PublicDNS):
    """A '-'-prefixed / option-looking image URL is a positional value, never
    parsed as an argparse option (fails safe with exit 2, never mis-parsed)."""

    def test_leading_dash_url_is_value_not_option(self):
        # Reaching _open's non-https rejection proves the URL was treated as the
        # positional value (not rejected by argparse as an unknown option).
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "-rf", "--out-dir", d], opener=_json_opener())
        self.assertEqual(code, 2)
        self.assertIn("non-https", err)

    def test_option_looking_url_not_swallowed_as_out_dir(self):
        # An "--out-dir=..."-looking URL must stay the URL value; it is never
        # allowed to redirect the actual output directory.
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = run_lookup(
                ["fetch-image", "--out-dir=/etc/evil", "--out-dir", d],
                opener=_json_opener())
        self.assertEqual(code, 2)
        self.assertIn("non-https", err)


class TestFetchImageTocTou(_PublicDNS):
    """O_EXCL/O_NOFOLLOW close the write TOCTOU: no clobber, no symlink follow."""

    def test_o_excl_refuses_existing_file(self):
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            existing = os.path.join(d, "cand_01.jpg")
            with open(existing, "wb") as f:
                f.write(b"OLD")
            code, _out, err = run_lookup(
                ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d,
                 "--name", "cand_01.jpg"], opener=opener)
            self.assertEqual(code, 2)
            self.assertIn("already exists", err)
            with open(existing, "rb") as f:
                self.assertEqual(f.read(), b"OLD")  # not clobbered

    def test_o_nofollow_refuses_swapped_symlink(self):
        # Simulate the TOCTOU race: a symlink appears at dest AFTER the
        # containment check (patched _resolve_dest stands in for the swap).
        opener = FakeOpener(lambda req: FakeResp(JPEG_BODY, IMG_HEADERS))
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "attacker_target")
            link = os.path.join(d, "cand_01.jpg")

            def swap(_out_dir, _name):
                os.symlink(target, link)
                return link

            with mock.patch.object(lookup, "_resolve_dest", side_effect=swap):
                code, _out, _err = run_lookup(
                    ["fetch-image", "https://ok.example/x.jpg", "--out-dir", d,
                     "--name", "cand_01.jpg"], opener=opener)
            self.assertEqual(code, 2)
            self.assertFalse(os.path.exists(target))  # write did not follow link
            self.assertTrue(os.path.islink(link))     # link left intact


if __name__ == "__main__":
    unittest.main()
