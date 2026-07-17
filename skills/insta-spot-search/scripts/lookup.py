#!/usr/bin/env python3
"""insta-spot-search lookup — stdlib structured adapter for geocode + image fetch.

Replaces the raw `curl` calls the SKILL used to make, so injection / scheme /
size / timeout are enforced in code (never a shell). stdlib-only, zero pip deps.

Modes:
  lookup.py geocode-kakao "<query>"                    Kakao keyword search (k-skill-proxy)
  lookup.py geocode-nominatim "<query>"                OpenStreetMap Nominatim search
  lookup.py fetch-image "<url>" --out-dir DIR [--name cand_01.jpg]

Search terms are passed as URL *values* only (urlencode) — a leading `-`,
shell metachars, or newlines are inert data, never an option or shell token.
Every request is HTTPS-only (redirects must stay HTTPS) with a finite timeout.

Exit codes: 0 ok / 2 usage or validation error (bad scheme, non-image, oversize,
            path escape, bad args) / 4 network or HTTP failure.
"""

import argparse
import ipaddress
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 15  # seconds, applied to every request
MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB cap on downloaded image body
USER_AGENT = "insta-spot-search-skill"
KAKAO_DEFAULT_BASE = "https://k-skill-proxy.nomadamas.org"
GEOCODE_CMDS = ("geocode-kakao", "geocode-nominatim")


class _SchemeError(Exception):
    """Raised when a redirect hop leaves HTTPS; mapped to exit 2."""


class _AddressError(Exception):
    """Host resolved to a private/loopback/link-local/reserved IP; exit 2."""


class _ResolveError(Exception):
    """Host could not be resolved to any IP; mapped to exit 4."""


def die(code, msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _reject_if_internal(url):
    """Resolve the URL host; reject if ANY address is private/loopback/etc.

    Runs on the FIRST hop and on every redirect hop (see redirect_request) to
    block SSRF at internal targets — 127.0.0.1, ::1, 10.x/172.16.x/192.168.x,
    and the cloud metadata endpoint 169.254.169.254 — whether reached directly
    or via a redirect from an untrusted page (SKILL Step 4). fetch-image URLs
    are attacker-influenced, so this is defense the geocode hosts also inherit.

    Inherent DNS-rebind gap: the name is resolved here for validation, then
    urllib resolves it again when it actually connects, so a hostile resolver
    could answer public now and private at connect time. Accepted for this
    threat model (one-shot image GET, not a persistent SSRF primitive); closing
    it would need a custom connection pinned to the validated IP.
    """
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise _AddressError("(no host)")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise _ResolveError(str(getattr(e, "strerror", None) or e)[:200])
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            raise _AddressError(str(info[4][0]))  # unparseable → fail closed
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise _AddressError(str(ip))


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only while they stay HTTPS and resolve to a public IP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        scheme = urllib.parse.urlparse(newurl).scheme
        if scheme != "https":
            raise _SchemeError(scheme or "(none)")
        _reject_if_internal(newurl)  # SSRF guard before following the redirect
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, headers=None):
    """Open an HTTPS URL with a finite timeout and validated redirects."""
    scheme = urllib.parse.urlparse(url).scheme
    if scheme != "https":
        die(2, f"refusing non-https URL (scheme: {scheme or '(none)'})")
    try:
        _reject_if_internal(url)  # first-hop SSRF guard
    except _AddressError as e:
        die(2, f"refusing internal/reserved address: {e.args[0]}")
    except _ResolveError as e:
        die(4, f"could not resolve host: {e.args[0]}")
    req = urllib.request.Request(url, headers=headers or {})
    opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
    try:
        return opener.open(req, timeout=TIMEOUT)
    except _SchemeError as e:
        die(2, f"refusing non-https redirect (scheme: {e.args[0]})")
    except _AddressError as e:
        die(2, f"refusing internal/reserved address: {e.args[0]}")
    except _ResolveError as e:
        die(4, f"could not resolve host: {e.args[0]}")
    except urllib.error.HTTPError as e:
        die(4, f"HTTP {e.code} {e.reason}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        die(4, f"request failed: {str(getattr(e, 'reason', e))[:200]}")


def _print_json(resp):
    try:
        obj = json.loads(resp.read().decode("utf-8", "replace"))
    except json.JSONDecodeError:
        die(4, "response was not valid JSON")
    print(json.dumps(obj, ensure_ascii=False))


def geocode_kakao(query):
    base = os.environ.get("KSKILL_PROXY_BASE_URL", KAKAO_DEFAULT_BASE).rstrip("/")
    url = f"{base}/v1/kakao-map/search/keyword?" + urllib.parse.urlencode({"q": query})
    with _open(url) as resp:
        _print_json(resp)


def geocode_nominatim(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "jsonv2", "limit": 3, "q": query})
    with _open(url, {"User-Agent": USER_AGENT}) as resp:
        _print_json(resp)


def _safe_name(name):
    if not name or name in (".", "..") or os.path.isabs(name) \
            or "/" in name or "\\" in name:
        die(2, f"unsafe output name (no path separators allowed): {name!r}")
    return name


def _resolve_dest(out_dir, name):
    """makedirs out_dir, return the resolved dest path, dying if it escapes."""
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        die(2, f"cannot use --out-dir: {e}")
    root = os.path.realpath(out_dir)
    dest = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, dest]) != root:
        die(2, "output path escapes --out-dir")
    return dest


def _read_capped(resp):
    chunks, total = [], 0
    while True:
        chunk = resp.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            die(2, f"image exceeds max size {MAX_IMAGE_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_image(url, out_dir, name):
    _safe_name(name)  # offline validation before any network use
    with _open(url, {"User-Agent": USER_AGENT}) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            die(2, f"response is not an image (Content-Type: {ctype or 'unknown'})")
        data = _read_capped(resp)  # dies before writing if oversize
    dest = _resolve_dest(out_dir, name)
    # O_NOFOLLOW + O_EXCL close the TOCTOU gap between _resolve_dest and the
    # write: a symlink swapped in after the containment check cannot redirect
    # the write (O_NOFOLLOW refuses to open it), and O_EXCL refuses to clobber
    # an existing file. 0o600 keeps the bytes owner-only.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(dest, flags, 0o600)
    except FileExistsError:
        die(2, "output path already exists (refusing to overwrite)")
    except OSError as e:
        die(2, f"cannot create image file: {e.strerror or e}")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except OSError as e:
        die(2, f"cannot write image: {e}")
    print(dest)


def _preprocess_argv(argv):
    """Keep a leading-dash search term / image URL a positional value, never an
    option.

    geocode has a single positional, so a leading ``--`` suffices. fetch-image
    has a positional URL plus options, so we lift the URL (the documented first
    slot) to the end behind ``--`` — a ``-``-prefixed or option-looking URL is
    then a value, and a mis-ordered call fails safe via argparse (exit 2) rather
    than being parsed as a flag. ``--help`` is left alone.
    """
    if len(argv) >= 2 and argv[0] in GEOCODE_CMDS and "--" not in argv:
        return [argv[0], "--", *argv[1:]]
    if len(argv) >= 2 and argv[0] == "fetch-image" and "--" not in argv \
            and argv[1] not in ("-h", "--help"):
        return [argv[0], *argv[2:], "--", argv[1]]
    return argv


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    for cmd, help_text in (("geocode-kakao", "Kakao keyword search (k-skill-proxy)"),
                           ("geocode-nominatim", "OpenStreetMap Nominatim search")):
        p = sub.add_parser(cmd, help=help_text)
        p.add_argument("query", help="search text (sent as a URL value, never a shell token)")

    pf = sub.add_parser("fetch-image", help="download an image into --out-dir",
                        allow_abbrev=False)
    pf.add_argument("url", help="https image URL")
    pf.add_argument("--out-dir", required=True, help="workspace dir the file must stay inside")
    pf.add_argument("--name", default="cand_01.jpg", help="output filename (no path separators)")

    args = ap.parse_args(_preprocess_argv(sys.argv[1:]))
    if args.command == "geocode-kakao":
        geocode_kakao(args.query)
    elif args.command == "geocode-nominatim":
        geocode_nominatim(args.query)
    elif args.command == "fetch-image":
        fetch_image(args.url, args.out_dir, args.name)


if __name__ == "__main__":
    main()
