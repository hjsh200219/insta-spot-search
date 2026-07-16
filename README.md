# insta-spot-search

인스타그램 릴스(틱톡/쇼츠 포함) 홍보 영상 속 장소를 역추적하는 Claude Code 스킬.

"팔로우하고 댓글 남기면 DM으로 위치 알려드려요" 하는 릴스 — 영상 자체에 남은 단서(화면 자막, 간판, 지형지물, 캡션, 댓글)로 장소를 직접 찾아낸다.

## 설치 (Claude Code 플러그인)

Claude Code 안에서:

```
/plugin marketplace add hjsh200219/insta-spot-search
/plugin install insta-spot-search@insta-spot-search
```

요구 바이너리: `yt-dlp`, `ffmpeg`. **직접 설치할 필요 없다** — 스킬 첫 실행 시 preflight가 자동 감지해 macOS면 Homebrew로 자동 설치하고, Linux/Windows면 정확한 설치 명령을 안내한다.

## 사용

```
/insta-spot-search https://www.instagram.com/reels/XXXX/
```

또는 자연어: "이 릴스 어디야? <URL>" / 로컬 파일 경로도 가능.

추가 힌트를 주면 정확도가 올라간다: `/insta-spot-search <URL> 강원도 바닷가 같아`

## 동작

1. `scripts/ingest.py` — yt-dlp로 메타데이터·캡션·댓글·location 태그 추출, 영상 다운로드, ffmpeg로 프레임 추출(기본 24장, 1024px)
2. Claude가 프레임을 읽고 단서 인벤토리 작성 (간판, 다리, 등대, 자막, 해시태그 …)
3. 검색 레그 병렬 실행 — Kakao Local 키워드 검색, 웹/네이버 블로그 시그니처 검색, 업로더 역추적
4. 후보별 교차 검증(반증 시도) 후 신뢰도(확정/유력/후보)와 근거를 붙여 리포트

실전 예: 19초 드론 릴스 하나로 강릉 사천진해변을 주소·지도 링크까지 확정 (아치교·노란 등대·해루질 바위 단서 교차 대조).

## 참고

- Instagram이 비로그인 접근을 막으면 브라우저 쿠키로 자동 재시도 (`--cookies-browser`, 기본 chrome). Chrome에 인스타 로그인만 되어 있으면 된다.
- "empty media response" 에러 → `brew upgrade yt-dlp` (Instagram 추출기가 구버전에서 자주 깨짐)
- 선택: 나레이션 전사(`--audio`)는 `~/.config/watch/.env`의 `GROQ_API_KEY`/`OPENAI_API_KEY` 재사용
- 영상·프레임은 로컬 tmp에만 저장. 외부 업로드 없음.

## 개발자용 (단독 스킬 설치)

```bash
git clone https://github.com/hjsh200219/insta-spot-search
ln -sfn "$(pwd)/insta-spot-search/skills/insta-spot-search" ~/.claude/skills/insta-spot-search
```

## 가드레일

공개 장소(업소·관광지) 홍보 콘텐츠 전용. 개인의 집·동선 추적 목적 사용은 거부한다.

## License

MIT
