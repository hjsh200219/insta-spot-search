# Core Beliefs — insta-spot-search

이 리포에서 코드/에이전트가 따르는 운영 신념. 감사와 실제 코드에서 도출한,
"이건 협상 대상이 아니다"에 가까운 원칙들이다. 새 기능/리팩터는 이 신념을 깨지 않는
선에서 한다. 진입점은 [AGENTS.md](../../AGENTS.md), 구조는 [ARCHITECTURE.md](../../ARCHITECTURE.md).

## 1. stdlib 전용 — pip 의존성 0은 하드 불변식

`ingest.py`·`setup.py`는 `argparse/glob/json/os/re/shutil/subprocess/sys/tempfile/
platform/pathlib`만, `lookup.py`는 `argparse/ipaddress/json/os/socket/sys/urllib.*`만
쓴다. 새 서드파티 의존성을 추가하지 않는다. 이유: 이 스킬은 사용자 머신에서 preflight
한 번으로 바로 돌아야 하고, 무거운 설치 단계가 채택 장벽이 된다. 무거운 일(다운로드·
트랜스코딩·전사)은 외부 **바이너리**(yt-dlp/ffmpeg/curl)에 subprocess로 위임하지,
파이썬 패키지로 끌어오지 않는다. `lookup.py`는 SKILL.md가 예전에 직접 조립하던
지오코딩/이미지 다운로드 `curl` 호출을 stdlib `urllib.request`만으로 대체해 이
신념을 그대로 잇는다(검증은 코드로, 서드파티 HTTP 라이브러리는 들이지 않는다).

## 2. 조회 전용 / query-only 도구

이 스킬은 읽기·추출·검색만 한다. 팔로우·댓글·DM·좋아요 같은 **쓰기/자동화 행위를
절대 하지 않는다**(SKILL.md "조회 전용. 팔로우/댓글/DM 자동화 절대 없음"). yt-dlp는
공개 메타데이터·영상을 받고, 검색 레그는 조회 API만 부른다. 계정을 대신 조작하는
어떤 경로도 만들지 않는다.

## 3. 프라이버시 우선 가드레일

공개 장소(업소·관광지) 홍보 콘텐츠 전용이다. 개인의 집·직장·동선 추적, 제3자의
사적 공간 위치 특정, 스토킹·괴롭힘 정황이면 **거부한다**(SKILL.md "When NOT to use").
이 판단은 기능이 아니라 전제다 — 정확도를 높이는 어떤 기능도 이 경계를 넘도록
설계하지 않는다.

## 4. subprocess 안전

모든 외부 명령은 **리스트 인자**로 호출하고 `shell=True`를 쓰지 않는다(`run()` 헬퍼).
경로를 glob에 넣을 때는 항상 `glob.escape()`로 감싼다(`download`·`extract_frames`).
SKILL.md의 `curl`도 `--data-urlencode`로 인젝션을 막는다. 사용자 입력(URL·경로·힌트)이
셸 해석에 노출되는 지점을 만들지 않는다.

## 5. 구조화된 exit code = Python과 SKILL.md의 계약

`ingest.py`는 `die(code,msg)`로 `0/2/3/4/5`, `setup.py`는 `0/2`, `lookup.py`는 `0/2/4`를
반환한다. 이 코드가
Claude(SKILL.md)가 다음에 무엇을 할지 결정하는 **유일한 기계 계약**이다(예: exit 3 →
쿠키 재시도 안내, exit 2 → 설치 스크립트). 사람이 읽을 설명은 stderr `NOTE:`로 덧붙이되,
분기 판단은 코드로 한다. 그래서 코드/의미를 바꾸면 SKILL.md "Failure modes" 표를 같은
커밋에서 갱신한다 — 계약 드리프트는 곧 오작동이다.

## 6. 결정론적 추출 vs 비결정론적 추론의 분리

Python은 "판단하지 않은 원료"만 만든다. 예: `flagged_comments`는 false positive를
일부러 허용하고("False positives are fine — the agent judges") 최종 판단은 Claude가
한다. 추출(결정론)과 추론·검증(Claude)을 섞지 않는 것이 재현성·디버깅·프라이버시
판단의 명료성을 지킨다.
