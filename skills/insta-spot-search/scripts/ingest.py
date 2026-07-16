#!/usr/bin/env python3
"""insta-spot-search ingest — turn a reel URL (or local video) into location-clue raw material.

Outputs into a work directory:
  video.<ext>      downloaded video (URL sources only)
  video.info.json  yt-dlp metadata incl. description + comments + location tag
  frames/f_NNN.jpg extracted frames (default max 24, width 1024 for on-screen text)
  audio.m4a        (--audio only) mono 16k audio
  report.json      structured summary for the calling agent

Exit codes: 0 ok / 2 missing binaries / 3 login wall (cookie retry failed too)
            4 download or probe failed / 5 frame extraction failed
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

LOGIN_WALL_PAT = re.compile(
    r"empty media response|log ?in required|log ?in to|rate.?limit|restricted"
    r"|HTTP Error 40[13]",
    re.IGNORECASE,
)
COOKIE_ERR_PAT = re.compile(
    r"cookie database|not supported for cookies|keyring", re.IGNORECASE
)

# Korean place-name heuristics for spotting location leaks in comments.
# False positives are fine — the agent judges; missing a leak is the real cost.
PLACE_WORD_PAT = re.compile(
    r"[가-힣]{1,8}(?:해수욕장|해변|해안|항|포구|방파제|등대|계곡|폭포|수목원|휴양림|"
    r"캠핑장|야영장|글램핑|오토캠핑|펜션|리조트|풀빌라|전망대|출렁다리|케이블카)"
)
REGION_PAT = re.compile(
    r"(?:서울|부산|대구|인천|광주|대전|울산|세종|제주|강원|경기|충북|충남|전북|전남|경북|경남)"
    r"|[가-힣]{1,4}(?:시|군)\s?[가-힣]{1,6}(?:읍|면|동|리)\b"
)
# top overseas destinations for Korean travelers + generic overseas place words
OVERSEAS_PAT = re.compile(
    r"(?:다낭|나트랑|푸꾸옥|호이안|하노이|호치민|발리|세부|보라카이|팔라완|마닐라|방콕|파타야|"
    r"치앙마이|푸켓|코사무이|오사카|도쿄|후쿠오카|오키나와|삿포로|교토|나고야|유후인|벳푸|"
    r"타이베이|가오슝|타이중|홍콩|마카오|싱가포르|쿠알라룸푸르|코타키나발루|랑카위|"
    r"하와이|괌|사이판|몰디브|칸쿤|두바이|이스탄불|산토리니|니스|바르셀로나|파리|로마|프라하|"
    r"뉴욕|엘에이|시드니|멜버른|퀸스타운|오클랜드)"
    r"|[가-힣A-Za-z]{2,12}\s?(?:비치|라군|사원|야시장|몰|스카이워크)"
    r"|[A-Z][A-Za-z]+ (?:Beach|Island|Bay|Temple|Falls|Lagoon)"
)


def die(code, msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def fmt_ts(seconds):
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def parse_ts(v):
    """'SS', 'MM:SS', or 'HH:MM:SS' -> seconds (float)."""
    parts = v.split(":")
    if not 1 <= len(parts) <= 3:
        raise argparse.ArgumentTypeError(f"bad timestamp: {v}")
    try:
        sec = 0.0
        for p in parts:
            sec = sec * 60 + float(p)
    except ValueError:
        raise argparse.ArgumentTypeError(f"bad timestamp: {v}")
    if sec < 0:
        raise argparse.ArgumentTypeError("timestamp must be >= 0")
    return sec


def check_binaries(need_ytdlp):
    missing = [b for b in (["yt-dlp"] if need_ytdlp else []) + ["ffmpeg", "ffprobe"]
               if shutil.which(b) is None]
    if missing:
        setup = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup.py")
        die(2, f"missing binaries: {', '.join(missing)} — run: python3 {setup}")


def download(url, out_dir, comments_wanted, cookies_browser):
    # clear stale files from a reused out-dir so the video.* glob can't pick an old download
    for p in glob.glob(os.path.join(glob.escape(out_dir), "video.*")):
        os.remove(p)

    base_cmd = [
        "yt-dlp", "--no-update", "--no-playlist",
        "--write-info-json",
        "-o", os.path.join(out_dir, "video.%(ext)s"),
        url,
    ]
    if comments_wanted:
        base_cmd.insert(1, "--write-comments")

    attempts = [[]]
    if cookies_browser != "none":
        attempts.append(["--cookies-from-browser", cookies_browser])

    last = None
    for idx, extra in enumerate(attempts):
        last = run(base_cmd[:1] + extra + base_cmd[1:])
        if last.returncode == 0:
            return
        stderr = last.stderr or ""
        if COOKIE_ERR_PAT.search(stderr):
            tail = "\n".join(stderr.strip().splitlines()[-6:])
            die(4, f"cookie extraction from browser '{cookies_browser}' failed — "
                   f"try another --cookies-browser or close the browser.\n{tail}")
        if not LOGIN_WALL_PAT.search(stderr):
            break  # not a login wall — retrying with cookies won't help
        if idx + 1 < len(attempts):
            print(f"NOTE: source blocked anonymous access, retrying with "
                  f"--cookies-from-browser {cookies_browser} ...", file=sys.stderr)

    err = (last.stderr or "").strip().splitlines()
    tail = "\n".join(err[-6:])
    if LOGIN_WALL_PAT.search(last.stderr or ""):
        hint = (" — even cookie retry failed; check that the browser is logged in"
                if len(attempts) > 1 else
                " — rerun with --cookies-browser chrome (or safari/firefox) to retry with login cookies")
        die(3, f"login wall{hint}.\n{tail}")
    die(4, f"yt-dlp failed (URL may be deleted/private/mistyped).\n{tail}")


def probe_duration(video_path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        die(4, f"ffprobe could not read duration of {video_path}")


def extract_frames(video_path, out_dir, duration, max_frames, resolution, fps_override,
                   start=None, end=None):
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    # clear stale frames from a previous run (e.g. a high-res --start/--end refine pass)
    for p in glob.glob(os.path.join(glob.escape(frames_dir), "f_*.jpg")):
        os.remove(p)

    seg_start = min(start or 0.0, max(duration - 0.1, 0.0))
    seg_end = min(end, duration) if end is not None else duration
    if seg_end <= seg_start:
        die(5, f"--end ({seg_end}s) must be after --start ({seg_start}s)")
    seg_len = seg_end - seg_start

    # clamp only the auto-computed rate; an explicit --fps override is honored as-is
    fps = fps_override if fps_override is not None else min(2.0, max_frames / max(seg_len, 1.0))
    r = run(["ffmpeg", "-y", "-v", "error",
             "-ss", f"{seg_start:.3f}", "-t", f"{seg_len:.3f}", "-i", video_path,
             "-vf", f"fps={fps:.4f},scale={resolution}:-2",
             "-q:v", "2", os.path.join(frames_dir, "f_%03d.jpg")])
    if r.returncode != 0:
        die(5, f"ffmpeg frame extraction failed: {r.stderr.strip()[-300:]}")
    all_paths = sorted(glob.glob(os.path.join(glob.escape(frames_dir), "f_*.jpg")))
    if len(all_paths) > max_frames:
        # sample evenly across the segment instead of truncating the tail
        step = len(all_paths) / max_frames
        picked = [(int(i * step), all_paths[int(i * step)]) for i in range(max_frames)]
    else:
        picked = list(enumerate(all_paths))
    # timestamps are absolute on the original video timeline
    return [{"path": p, "t": fmt_ts(seg_start + (idx + 0.5) / fps)} for idx, p in picked]


def load_env_file(path):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip()
                    if v[:1] in ("'", '"'):
                        v = v.strip("'\"")
                    else:
                        v = v.split(" #", 1)[0].strip()
                    env[k.strip()] = v
    except OSError:
        pass
    return env


def whisper_backend():
    """(url, key, model) if a Whisper key is configured, else None.
    Reuses the watch skill's key file so users set it up once."""
    env = load_env_file(os.path.expanduser("~/.config/watch/.env"))
    groq = os.environ.get("GROQ_API_KEY") or env.get("GROQ_API_KEY")
    oai = os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    if groq:
        return ("https://api.groq.com/openai/v1/audio/transcriptions", groq, "whisper-large-v3")
    if oai:
        return ("https://api.openai.com/v1/audio/transcriptions", oai, "whisper-1")
    return None


def transcribe(audio_path, backend):
    url, key, model = backend
    try:
        r = run(["curl", "-fsS", "-X", "POST", url,
                 "-H", f"Authorization: Bearer {key}",
                 "-F", f"file=@{audio_path}",
                 "-F", f"model={model}",
                 "-F", "response_format=text"])
    except FileNotFoundError:
        print("NOTE: curl not found — skipping transcription", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"NOTE: whisper transcription failed: {r.stderr.strip()[-200:]}", file=sys.stderr)
        return None
    return r.stdout.strip() or None


def scan_profile(handle, n, cookies_browser):
    """Fetch metadata of the uploader's N most recent posts — location tags on
    sibling posts are a strong region prior. Best-effort: returns [] on any failure."""
    url = f"https://www.instagram.com/{handle}/"
    base = ["yt-dlp", "--no-update", "-J", "--playlist-items", f"1:{n}", url]
    attempts = [[]]
    if cookies_browser != "none":
        attempts.append(["--cookies-from-browser", cookies_browser])
    r = None
    for extra in attempts:
        try:
            r = run(base[:1] + extra + base[1:], timeout=240)
        except subprocess.TimeoutExpired:
            print("NOTE: profile scan timed out — skipping", file=sys.stderr)
            return []
        if r.returncode == 0 or not LOGIN_WALL_PAT.search(r.stderr or ""):
            break
    if r is None or r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()[-1:] if r else []
        print(f"NOTE: profile scan failed — skipping. {' '.join(tail)}", file=sys.stderr)
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    posts = []
    for e in (data.get("entries") or [])[:n]:
        if isinstance(e, dict):
            posts.append({
                "id": e.get("id") or e.get("display_id"),
                "upload_date": e.get("upload_date"),
                "location": e.get("location"),
                "caption_head": (e.get("description") or "")[:160],
            })
    return posts


def positive_int(v):
    iv = int(v)
    if iv <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return iv


def positive_float(v):
    fv = float(v)
    if fv <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return fv


def nonneg_int(v):
    iv = int(v)
    if iv < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return iv


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="video URL or local file path")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--max-frames", type=positive_int, default=24)
    ap.add_argument("--resolution", type=positive_int, default=1024)
    ap.add_argument("--fps", type=positive_float, default=None)
    ap.add_argument("--comments", type=nonneg_int, default=40,
                    help="max comments to include in the report (0 = skip fetching)")
    ap.add_argument("--start", type=parse_ts, default=None,
                    help="extract frames from this timestamp (SS or MM:SS) — for high-res refine passes")
    ap.add_argument("--end", type=parse_ts, default=None,
                    help="extract frames up to this timestamp")
    ap.add_argument("--profile-scan", type=positive_int, default=None, metavar="N",
                    help="also fetch the uploader's N recent posts (location tags = region prior)")
    ap.add_argument("--no-audio", action="store_true",
                    help="skip narration transcription (on by default when a Whisper key exists)")
    ap.add_argument("--audio", action="store_true", help=argparse.SUPPRESS)  # legacy no-op
    ap.add_argument("--cookies-browser", default="chrome",
                    choices=["chrome", "safari", "firefox", "edge", "brave", "none"],
                    help="browser to pull cookies from when the source needs login")
    args = ap.parse_args()

    is_url = args.source.startswith(("http://", "https://"))
    check_binaries(need_ytdlp=is_url)

    out_dir = args.out_dir or tempfile.mkdtemp(prefix="insta-spot-")
    os.makedirs(out_dir, exist_ok=True)

    info = {}
    if is_url:
        download(args.source, out_dir, args.comments > 0, args.cookies_browser)
        try:
            with open(os.path.join(out_dir, "video.info.json")) as f:
                info = json.load(f)
        except (OSError, json.JSONDecodeError):
            print("NOTE: no info.json — proceeding frames-only", file=sys.stderr)
        vids = [p for p in glob.glob(os.path.join(glob.escape(out_dir), "video.*"))
                if not p.endswith(".json")]
        if not vids:
            die(4, "download reported success but no video file found")
        video_path = vids[0]
    else:
        if not os.path.isfile(args.source):
            die(4, f"no such file: {args.source}")
        video_path = args.source

    duration = probe_duration(video_path)
    frames = extract_frames(video_path, out_dir, duration,
                            args.max_frames, args.resolution, args.fps,
                            start=args.start, end=args.end)

    transcript = None
    audio_path = None
    backend = whisper_backend()
    if not args.no_audio and backend:
        audio_path = os.path.join(out_dir, "audio.m4a")
        r = run(["ffmpeg", "-y", "-v", "error", "-i", video_path,
                 "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio_path])
        if r.returncode != 0:
            print("NOTE: audio extraction failed (video may have no audio track)", file=sys.stderr)
            audio_path = None
        else:
            transcript = transcribe(audio_path, backend)

    all_comments = [
        {"author": c.get("author"), "text": (c.get("text") or "").strip(),
         "likes": c.get("like_count") or 0}
        for c in (info.get("comments") or [])
        if (c.get("text") or "").strip()
    ]
    flagged = sorted(
        (c for c in all_comments
         if PLACE_WORD_PAT.search(c["text"]) or REGION_PAT.search(c["text"])
         or OVERSEAS_PAT.search(c["text"])),
        key=lambda c: -c["likes"])[:20]
    comments = all_comments[: args.comments]

    profile_posts = []
    if args.profile_scan and is_url:
        handle = info.get("channel") or info.get("uploader_id")
        if handle:
            profile_posts = scan_profile(handle, args.profile_scan, args.cookies_browser)

    report = {
        "source": args.source,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "uploader_id": info.get("channel") or info.get("uploader_id"),
        "upload_date": info.get("upload_date"),
        "duration_sec": round(duration, 1),
        "location": info.get("location"),
        "description": info.get("description"),
        "comments_total_on_post": info.get("comment_count"),
        "comments_fetched": len(all_comments),
        "comments": comments,
        "flagged_comments": flagged,
        "profile_posts": profile_posts,
        "frames": frames,
        "audio": {"path": audio_path, "transcript": transcript},
        "work_dir": out_dir,
    }
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---- human/agent-readable report ----
    print("=== INSTA-SPOT-SEARCH INGEST REPORT ===")
    print(f"source     : {args.source}")
    print(f"title      : {report['title']}")
    print(f"uploader   : {report['uploader']} (@{report['uploader_id']})")
    print(f"upload date: {report['upload_date']}")
    print(f"duration   : {report['duration_sec']}s")
    if report["location"]:
        print(f"LOCATION TAG (jackpot — verify then done): {json.dumps(report['location'], ensure_ascii=False)}")
    print("\n--- CAPTION ---")
    print(report["description"] or "(none)")
    total = info.get("comment_count")
    print(f"\n--- COMMENTS (fetched {len(all_comments)}"
          f"{f' of ~{total} total' if total else ''}) ---")
    for c in comments:
        print(f"- [{c['author']}] {c['text'][:200]}")
    if not comments:
        print("(none fetched)")
    if flagged:
        print(f"\n--- 지명 의심 댓글 ({len(flagged)}) — 위치 유출 후보, 최우선 확인 ---")
        for c in flagged:
            likes = f" (♥{c['likes']})" if c["likes"] else ""
            print(f"- [{c['author']}]{likes} {c['text'][:200]}")
    if profile_posts:
        print(f"\n--- 업로더 최근 게시물 ({len(profile_posts)}) — location 태그 = 지역 prior ---")
        for p in profile_posts:
            loc = json.dumps(p["location"], ensure_ascii=False) if p["location"] else "-"
            print(f"- [{p['upload_date']}] loc={loc} | {p['caption_head'][:100]}")
    print(f"\n--- FRAMES ({len(frames)}) — Read ALL of these in one parallel batch ---")
    for fr in frames:
        print(f"{fr['path']}  t={fr['t']}")
    print("\n--- AUDIO TRANSCRIPT ---")
    print(transcript or "(none — set GROQ_API_KEY or OPENAI_API_KEY in ~/.config/watch/.env to enable narration transcription)")
    print(f"\nwork dir: {out_dir}")
    print(f"report json: {os.path.join(out_dir, 'report.json')}")


if __name__ == "__main__":
    main()
