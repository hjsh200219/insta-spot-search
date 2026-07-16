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


def die(code, msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def fmt_ts(seconds):
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def check_binaries(need_ytdlp):
    missing = [b for b in (["yt-dlp"] if need_ytdlp else []) + ["ffmpeg", "ffprobe"]
               if shutil.which(b) is None]
    if missing:
        die(2, f"missing binaries: {', '.join(missing)} — install with: brew install {' '.join(missing)}")


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


def extract_frames(video_path, out_dir, duration, max_frames, resolution, fps_override):
    frames_dir = os.path.join(out_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    # clamp only the auto-computed rate; an explicit --fps override is honored as-is
    fps = fps_override if fps_override is not None else min(2.0, max_frames / max(duration, 1.0))
    r = run(["ffmpeg", "-y", "-v", "error", "-i", video_path,
             "-vf", f"fps={fps:.4f},scale={resolution}:-2",
             "-q:v", "2", os.path.join(frames_dir, "f_%03d.jpg")])
    if r.returncode != 0:
        die(5, f"ffmpeg frame extraction failed: {r.stderr.strip()[-300:]}")
    all_paths = sorted(glob.glob(os.path.join(glob.escape(frames_dir), "f_*.jpg")))
    if len(all_paths) > max_frames:
        # sample evenly across the whole video instead of truncating the tail
        step = len(all_paths) / max_frames
        picked = [(int(i * step), all_paths[int(i * step)]) for i in range(max_frames)]
    else:
        picked = list(enumerate(all_paths))
    return [{"path": p, "t": fmt_ts((idx + 0.5) / fps)} for idx, p in picked]


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


def transcribe(audio_path):
    """Optional Whisper pass. Reuses the watch skill's key file; silently skips without a key."""
    env = load_env_file(os.path.expanduser("~/.config/watch/.env"))
    groq = os.environ.get("GROQ_API_KEY") or env.get("GROQ_API_KEY")
    oai = os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    if groq:
        url, key, model = ("https://api.groq.com/openai/v1/audio/transcriptions",
                           groq, "whisper-large-v3")
    elif oai:
        url, key, model = ("https://api.openai.com/v1/audio/transcriptions",
                           oai, "whisper-1")
    else:
        return None
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
    ap.add_argument("--audio", action="store_true",
                    help="also extract audio and transcribe if a Whisper key exists")
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
                            args.max_frames, args.resolution, args.fps)

    transcript = None
    audio_path = None
    if args.audio:
        audio_path = os.path.join(out_dir, "audio.m4a")
        r = run(["ffmpeg", "-y", "-v", "error", "-i", video_path,
                 "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", audio_path])
        if r.returncode != 0:
            print("NOTE: audio extraction failed (video may have no audio track)", file=sys.stderr)
            audio_path = None
        else:
            transcript = transcribe(audio_path)

    comments = [
        {"author": c.get("author"), "text": (c.get("text") or "").strip()}
        for c in (info.get("comments") or [])[: args.comments]
        if (c.get("text") or "").strip()
    ]

    report = {
        "source": args.source,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "uploader_id": info.get("channel") or info.get("uploader_id"),
        "upload_date": info.get("upload_date"),
        "duration_sec": round(duration, 1),
        "location": info.get("location"),
        "description": info.get("description"),
        "comments": comments,
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
    print(f"\n--- COMMENTS ({len(comments)}) ---")
    for c in comments:
        print(f"- [{c['author']}] {c['text'][:200]}")
    if not comments:
        print("(none fetched)")
    print(f"\n--- FRAMES ({len(frames)}) — Read ALL of these in one parallel batch ---")
    for fr in frames:
        print(f"{fr['path']}  t={fr['t']}")
    print("\n--- AUDIO TRANSCRIPT ---")
    print(transcript or "(none — pass --audio with a Whisper key in ~/.config/watch/.env to enable)")
    print(f"\nwork dir: {out_dir}")
    print(f"report json: {os.path.join(out_dir, 'report.json')}")


if __name__ == "__main__":
    main()
