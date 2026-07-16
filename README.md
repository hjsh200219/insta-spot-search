# insta-spot-search

**English** | [한국어](#한국어)

A Claude Code skill that reverse-locates the place shown in a promotional
Instagram Reel (TikTok / Shorts too).

You know the reels that hide the location — *"follow me and drop a comment,
I'll DM you where this is."* This skill finds the place directly, from the
clues left in the video itself: on-screen captions, signage, landmarks, the
post caption, and the comments. Works for spots in **Korea and overseas**.

## Install (Claude Code plugin)

Inside Claude Code:

```
/plugin marketplace add hjsh200219/insta-spot-search
/plugin install insta-spot-search@insta-spot-search
```

Required binaries: `yt-dlp`, `ffmpeg`. **You don't install them yourself** — on
first run a preflight detects what's missing and auto-installs via Homebrew on
macOS, or prints the exact install commands on Linux/Windows.

## Usage

```
/insta-spot-search https://www.instagram.com/reels/XXXX/
```

Or just ask: *"Where is this reel? <URL>"* — a local video file path works too.

Extra hints improve accuracy: `/insta-spot-search <URL> looks like a beach in Gangwon`.

## How it works

1. `scripts/ingest.py` — yt-dlp pulls metadata, caption, comments, and any
   location tag; downloads the video; ffmpeg extracts frames (24 @ 1024px by
   default, tuned for reading on-screen text and signage).
2. Claude reads the frames and builds a clue inventory (signs, bridges,
   lighthouses, burned-in captions, hashtags, coastline shape …).
3. Search legs run in parallel — cross-platform uploader lookup, landmark
   signature search (Naver blogs for Korea, travel blogs / TripAdvisor for
   overseas), Kakao Local (Korea) or Nominatim geocoding (overseas).
4. Each candidate is cross-verified (actively trying to *disprove* it) before a
   report is written with a confidence level (confirmed / likely / candidate),
   the evidence, and a map link.

Real run: a single 19-second drone reel was pinned to Sacheonjin Beach in
Gangneung, Korea — address and map link included — by cross-matching the arch
footbridge, the yellow breakwater lighthouse, and the granite tide-pool rocks.

### Accuracy features (v0.3.0)

- **Comment mining** — flags location-leak comments (Korean + overseas
  place-name patterns), sorted by likes. Popular reels almost always have
  someone who names the spot.
- **Domestic / overseas branching** — a region-heuristic table (coast type,
  phone area codes, driving side, foreign signage) narrows the search area
  before any query runs.
- **Narration transcription** — on by default when a Whisper key exists; TTS
  narration often says things the captions don't.
- **Zoom refine** (`--start`/`--end` + `--resolution 2048`) — re-extract a
  segment at high resolution to read small signs, from the already-downloaded
  video (no re-download).
- **Profile scan** (`--profile-scan N`) — the uploader's recent-post location
  tags as a region prior (best-effort).

## Notes

- If Instagram blocks anonymous access, the script auto-retries with browser
  cookies (`--cookies-browser`, default `chrome`) — just be logged into
  Instagram in Chrome. Public promotional reels usually work without login.
- `empty media response` error → `brew upgrade yt-dlp` (Instagram extractors
  break often on old versions).
- Optional narration transcription reuses `GROQ_API_KEY` / `OPENAI_API_KEY`
  from `~/.config/watch/.env` (shared with the `watch` skill). No key → skipped.
- Video and frames stay in a local tmp dir. Nothing is uploaded (except the
  audio clip to your Whisper provider, only when transcription is enabled).

## Developer (standalone skill install)

```bash
git clone https://github.com/hjsh200219/insta-spot-search
ln -sfn "$(pwd)/insta-spot-search/skills/insta-spot-search" ~/.claude/skills/insta-spot-search
```

## Guardrail

For public places (businesses, tourist spots) promoted in content only. The
skill refuses requests aimed at tracking a private individual's home or
movements.

## License

MIT

---

## 한국어

인스타그램 릴스(틱톡/쇼츠 포함) 홍보 영상 속 장소를 역추적하는 Claude Code 스킬.

"팔로우하고 댓글 남기면 DM으로 위치 알려드려요" 하는 릴스 — 영상 자체에 남은
단서(화면 자막, 간판, 지형지물, 캡션, 댓글)로 장소를 직접 찾아낸다. **국내·해외
모두 지원**.

### 설치 (Claude Code 플러그인)

Claude Code 안에서:

```
/plugin marketplace add hjsh200219/insta-spot-search
/plugin install insta-spot-search@insta-spot-search
```

요구 바이너리: `yt-dlp`, `ffmpeg`. **직접 설치할 필요 없다** — 스킬 첫 실행 시
preflight가 자동 감지해 macOS면 Homebrew로 자동 설치하고, Linux/Windows면 정확한
설치 명령을 안내한다.

### 사용

```
/insta-spot-search https://www.instagram.com/reels/XXXX/
```

또는 자연어: "이 릴스 어디야? <URL>" / 로컬 파일 경로도 가능.

추가 힌트를 주면 정확도가 올라간다: `/insta-spot-search <URL> 강원도 바닷가 같아`

### 동작

1. `scripts/ingest.py` — yt-dlp로 메타데이터·캡션·댓글·location 태그 추출, 영상
   다운로드, ffmpeg로 프레임 추출(기본 24장, 1024px — 화면 자막·간판 판독용).
2. Claude가 프레임을 읽고 단서 인벤토리 작성 (간판, 다리, 등대, 자막, 해시태그 …).
3. 검색 레그 병렬 실행 — 크로스플랫폼 업로더 역추적, 지형지물 시그니처 검색(국내
   네이버 블로그 / 해외 여행 블로그·TripAdvisor), Kakao Local(국내) 또는
   Nominatim 지오코딩(해외).
4. 후보별 교차 검증(반증 시도) 후 신뢰도(확정/유력/후보)와 근거, 지도 링크를
   붙여 리포트.

실전 예: 19초 드론 릴스 하나로 강릉 사천진해변을 주소·지도 링크까지 확정
(아치교·노란 등대·해루질 바위 단서 교차 대조).

#### 정확도 기능 (v0.3.0)

- **댓글 지명 필터** — 국내·해외 지명 패턴을 매칭해 위치 유출 댓글을 좋아요순으로
  표시. 인기 릴스엔 장소를 흘린 사람이 거의 항상 있다.
- **국내/해외 분기** — 지역 판별 휴리스틱 표(물색, 전화 지역번호, 주행 방향, 외국어
  간판)로 검색 전에 권역을 좁힌다.
- **나레이션 전사** — Whisper 키가 있으면 기본 켜짐. 자막에 없는 정보가 나레이션에
  있는 경우가 많다.
- **줌 재추출** (`--start`/`--end` + `--resolution 2048`) — 작은 간판 판독용으로
  특정 구간만 고해상 재추출(이미 받은 영상 재사용, 재다운로드 없음).
- **프로필 스캔** (`--profile-scan N`) — 업로더 최근 게시물 location 태그를 지역
  prior로 활용 (best-effort).

### 참고

- Instagram이 비로그인 접근을 막으면 브라우저 쿠키로 자동 재시도
  (`--cookies-browser`, 기본 chrome). Chrome에 인스타 로그인만 되어 있으면 된다.
  공개 홍보 릴스는 대개 로그인 없이 된다.
- "empty media response" 에러 → `brew upgrade yt-dlp` (Instagram 추출기가
  구버전에서 자주 깨짐).
- 나레이션 전사는 `~/.config/watch/.env`의 `GROQ_API_KEY`/`OPENAI_API_KEY`
  재사용(watch 스킬과 공유). 키 없으면 생략.
- 영상·프레임은 로컬 tmp에만 저장. 외부 업로드 없음(전사 켠 경우 오디오 클립만
  Whisper 제공사로 전송).

### 개발자용 (단독 스킬 설치)

```bash
git clone https://github.com/hjsh200219/insta-spot-search
ln -sfn "$(pwd)/insta-spot-search/skills/insta-spot-search" ~/.claude/skills/insta-spot-search
```

### 가드레일

공개 장소(업소·관광지) 홍보 콘텐츠 전용. 개인의 집·동선 추적 목적 사용은 거부한다.

### License

MIT
