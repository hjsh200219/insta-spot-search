# Layer Rules — insta-spot-search

이 리포의 **레이어/의존 규칙**을 강제 가능한 불변식으로 고정한 문서다.
"아키텍처가 무엇인가"는 [ARCHITECTURE.md](../../ARCHITECTURE.md), "왜 이렇게 믿는가"는
[core-beliefs.md](./core-beliefs.md)에 있다. 이 문서는 **"무엇을 하면 규칙 위반인가"**만
다룬다. JS 리포가 아니므로 eslint/import-linter 같은 린터는 없다 —
checkable subset은 [`scripts/verify-docs.py`](../../scripts/verify-docs.py)가 강제한다(§5).

---

## 1. 세 진입점은 서로 import하지 않는다 (독립 CLI 불변식)

`setup.py`·`ingest.py`·`lookup.py`는 **서로를 import하지 않는 독립 CLI 진입점**이다.
셋 다 `if __name__ == "__main__"`로만 실행되고, 오케스트레이션은
[SKILL.md](../../skills/insta-spot-search/SKILL.md)가 Bash 블록으로 세 스크립트를
필요한 순서대로 호출하며 담당한다. `lookup.py`는 SKILL.md가 예전에 직접 조립하던
`curl` 지오코딩/이미지 다운로드 호출을 대체하는 세 번째 독립 CLI다. 스크립트는
SKILL.md를 알지 못한다.

- **금지**: `ingest.py`가 `import setup`/`import lookup` 하거나, `setup.py`·`lookup.py`가
  다른 진입점을 import하는 것 — 세 스크립트 어느 조합도 금지.
- **금지**: 한 스크립트가 다른 스크립트의 함수/상수를 재사용하려고 상대방을 import하는 것.
- 스크립트 간 결합은 오직 **파일시스템**(`ingest.py`가 만드는 `report.json`)과
  **텍스트 힌트**(`check_binaries()`가 `setup.py` 경로를 안내 메시지로 가리킴 — 코드
  호출이 아님)로만 일어난다. `lookup.py`는 그 파일시스템 결합에도 참여하지 않는
  순수 조회/다운로드 어댑터로, 결과를 stdout(JSON) 또는 저장 파일로만 돌려준다.

### 공유 코드를 추출할 때의 규칙 (방향 강제) — `_common.py` 예외

`skills/insta-spot-search/scripts/_common.py`가 이미 존재하는 **승인된 공유 헬퍼
모듈**이다. `die()`/`REQUIRED_BINARIES`+`missing_binaries()`/`cookie_retry_attempts()`/
`PathEscape`+`resolve_within()`을 담고 있으며, `if __name__ == "__main__"`이 없어
**CLI가 아니다**. `setup.py`·`ingest.py`·`lookup.py` 세 진입점이 각자
`sys.path.insert(0, <자기 dir>)` 후 `from _common import ...`로 **로컬 import**한다.

이것이 §1 "서로 import하지 않는다" 규칙의 **유일한 예외**다 — 정확히는 예외가 아니라
그 규칙이 애초에 허용하는 경로: 진입점은 **서로**를 import하지 않을 뿐, 셋이 공통으로
**공유 헬퍼 모듈**을 import하는 것은 금지 대상이 아니다. 새로 공통화하고 싶은 로직이
있다면:

- **반드시** 기존 `_common.py`에 추가하거나(새로 작은 헬퍼라면), 그래도 별도 모듈이
  필요하면 새 공유 모듈을 만들고 **필요한 진입점들이 그 모듈을 import**한다.
- **금지**: 한 진입점을 "라이브러리 겸 CLI"로 만들어 다른 진입점이 그것을 import하는 것.
  진입점끼리는 영원히 동등한 형제(sibling)여야 한다. 한쪽이 다른 쪽에 의존하면
  독립 CLI 불변식이 깨지고, `--check` 같은 경량 preflight가 무거운 파이프라인 코드를
  끌고 들어온다.
- `_common.py` 자체도 이 규칙을 지킨다: `setup.py`/`ingest.py`/`lookup.py`를 import하지
  않는다(공유 모듈이 진입점에 의존하면 방향이 뒤집힌다).

```
        SKILL.md  (오케스트레이터 / SSOT)
        │  Bash 호출 + exit code 판독
        ├──────────────► setup.py   (preflight/installer, 독립)
        ├──────────────► ingest.py  (추출 파이프라인, 독립)
        └──────────────► lookup.py  (지오코딩/이미지 다운로드 어댑터, 독립)

  허용 (지금 상태):                       금지 (어느 조합이든):
        setup.py ──┐                      setup.py ──import──► ingest.py
       ingest.py ──┼─import─► _common.py       (진입점이 진입점을 import)
       lookup.py ──┘                      _common.py ──import──► ingest.py
                                                (공유 헬퍼가 진입점에 의존)
```

소스 파일은 이제 4개다(`setup.py`·`ingest.py`·`lookup.py`·`_common.py`) — 그중
독립 CLI 진입점은 여전히 3개뿐이고 `_common.py`는 진입점이 아니다.

---

## 2. ingest.py 파이프라인 내부 의존 방향

`ingest.py` 한 파일 안에서 파이프라인은 단방향이다. 각 단계는 **이전 단계의 산출물에만**
의존하고, 절대 역방향으로 의존하지 않는다.

```
Setup(check_binaries) → Download(download) → Frame(probe_duration→extract_frames)
  → Transcript(whisper_backend→transcribe) → Clue(PLACE/REGION/OVERSEAS_PAT, scan_profile)
  → Report(main 후반: report.json + stdout)
```

- 뒤 단계는 앞 단계 출력을 읽는다: `extract_frames`는 `probe_duration`의 `duration`을,
  `transcribe`는 다운로드된 `video_path`를, Report는 앞의 모든 산출물을 모은다.
- **금지**: 앞 단계가 뒤 단계 결과에 의존하기(예: `download`가 `flagged_comments`를
  참조). 역방향 의존은 결정론적 추출 순서를 깨고 부분 실패 시 exit code 매핑을 흐린다.
- **경계**: Report(L5)까지가 결정론적 Python이다. 그 뒤 판독/검색/검증(L6)은 Claude가
  SKILL.md 지시로 수행하는 비결정론 단계다. Python은 L6에 **"판단하지 않은 원료"**만
  넘긴다(`flagged_comments`는 false positive를 허용하고 최종 판단은 Claude가 함).

---

## 3. stdlib 전용 — pip 의존성 0 (하드 불변식)

`ingest.py`·`setup.py`·`lookup.py`·`_common.py`는 파이썬 **표준 라이브러리만**
import한다(`_common.py`는 셋이 로컬 import하는 대상이므로 stdlib-only 불변식이 그대로
전파돼야 한다). 현재 사용 모듈: `argparse` `glob` `json` `os` `re` `shutil` `subprocess`
`sys` `tempfile` (`ingest.py`), `json` `platform` `shutil` `subprocess` `sys` `pathlib`
(`setup.py`), `argparse` `ipaddress` `json` `os` `socket` `sys` `urllib.*`
(`lookup.py`), `os` `shutil` `sys` `typing`(`_common.py`), 그리고
`from __future__ import annotations`.

- **금지**: 어떤 서드파티 패키지든 `import`/`from ... import` 하는 것.
- **금지**: `requirements.txt` / `pyproject.toml` / `setup.cfg` 등 의존성 매니페스트를
  추가하는 것(있으면 stdlib-only 주장이 무너진다).
- 무거운 일(다운로드·트랜스코딩·전사)은 **외부 바이너리를 subprocess로 호출**해 위임한다.
  `yt-dlp`/`ffmpeg`/`ffprobe`/`curl`은 **파이썬 패키지로 import하지 않고** 프로세스로만
  부른다. 즉 `import yt_dlp` 같은 코드는 규칙 위반이다 — 반드시 `run(["yt-dlp", ...])`.
- 이 불변식은 [`scripts/verify-docs.py`](../../scripts/verify-docs.py)가 자동 검사한다(§5).

---

## 4. subprocess 안전 — 리스트 인자, `shell=True` 금지

- 모든 외부 명령은 **리스트 인자**로 호출한다(`run()` 헬퍼 = `subprocess.run(cmd,
  capture_output=True, text=True)`).
- **금지**: `shell=True`. 문자열 명령을 셸에 넘기지 않는다 — 사용자 입력(URL·경로·힌트)이
  셸 해석에 노출되는 지점을 만들지 않기 위해서다.
- glob 대상 경로는 항상 `glob.escape()`로 감싼다(`download`·`extract_frames` 참고).
- SKILL.md의 `curl` 호출도 `--data-urlencode`로 파라미터 인젝션을 막는다.

---

## 5. 강제 수단 — import-linter는 없다, verify-docs.py가 대신한다

이 리포는 JS가 아니고(eslint 없음) `import-linter`도 설치돼 있지 않다. 대신
[`scripts/verify-docs.py`](../../scripts/verify-docs.py)가 **checkable subset**을 강제한다:

| 규칙 | verify-docs.py가 검사하는가 | 검사 방식 |
|------|:--:|-----------|
| §3 stdlib 전용 | ✅ | `ingest.py`/`setup.py`/`lookup.py`(`STDLIB_ONLY_FILES`) 세 파일 전부의 모든 import를 stdlib allowlist와 대조. `_common`은 `LOCAL_SHARED_MODULES`로 명시 허용(서드파티 아님), 그 외 서드파티 발견 시 FAIL |
| exit code 계약 | ✅ | `ingest.py`가 문서화된 코드 `2/3/4/5`를, `lookup.py`가 `2/4`를 여전히 참조하는지 확인(이 체크가 `lookup.py` 파일 존재 여부도 함께 확인) |
| 문서 경로 실재 | ✅ | AGENTS.md/ARCHITECTURE.md가 가리키는 `setup.py`/`ingest.py`/`SKILL.md` 존재 확인. `lookup.py`는 이 체크 대상이 아니고 위 exit-code 체크가 대신 존재를 확인 |
| §1 진입점 상호 import 금지 | ✅ | stdlib 스캔이 `ingest.py`/`setup.py`/`lookup.py` **세 파일 모두**를 훑어 `import setup`/`import ingest`(`ENTRYPOINT_MODULES`)가 어디서 나타나든 잡는다 — `lookup.py`가 `import ingest`/`import setup` 하는 경우도 이제 이 스캔 범위 안이다(예전엔 `lookup.py`가 스캔 대상이 아니라 갭이었으나 `_common` 도입과 함께 `STDLIB_ONLY_FILES`에 추가되며 해소됨) |
| §2 파이프라인 방향 | ❌ | 한 파일 내부 흐름이라 정적 검사 대상 아님 — 코드 리뷰로 지킴 |

- 실행: `python3 scripts/verify-docs.py` (수동 / harness-gc 흐름). 자세한 게이트는
  [harness-setup.md](../harness/harness-setup.md) 品質 게이트 절 참고.
- import-linter/eslint류를 새로 도입하지 않는다 — 소스 4파일(CLI 진입점 3개 + 공유 헬퍼
  `_common.py` 1개) 리포에 무거운 린터를 얹는 것은
  [harness principles](../harness/principles.md)의 "하네스 단순화 원칙" 위반이다.
