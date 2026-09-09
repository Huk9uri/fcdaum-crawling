# F&B QSC API Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 `.env`에 F&B 계정만 입력하면 로그인과 리포트·문제항목·품질미션 API 첫 페이지를 안전하게 검증하는 Windows용 Python 프로그램을 만든다.

**Architecture:** `config.py`가 비밀값을 환경변수에서 검증하고, `fnb_client.py`가 주입 가능한 `requests.Session`으로 인증과 API 요청을 담당한다. `crawling.py`는 이 클라이언트를 순서대로 호출해 비민감 요약만 출력하며, 외부 네트워크 없이 단위 테스트할 수 있도록 HTTP 세션 경계를 분리한다.

**Tech Stack:** Python 3.12, requests, python-dotenv, pytest

## Global Constraints

- 대상 운영체제는 Windows이다.
- 이 단계에서는 MSSQL을 읽거나 변경하지 않는다.
- 비밀번호, Cookie, Set-Cookie, access token, refresh token은 출력하거나 파일로 저장하지 않는다.
- 모든 HTTP 요청은 TLS 인증서 검증을 유지하고 30초 타임아웃을 사용한다.
- 실제 계정정보는 `.env`에만 존재하며 `.gitignore`로 제외한다.
- 목록 API는 진단 목적으로 첫 페이지 10건만 요청한다.

---

### Task 1: 환경설정 로더와 프로젝트 실행 기반

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings(base_url: str, user_id: str, password: str, timeout_seconds: int)`
- Produces: `load_settings(environ: Mapping[str, str] | None = None) -> Settings`

- [ ] **Step 1: 필수 환경변수 누락 실패 테스트 작성**

```python
import pytest

from config import ConfigError, load_settings


def test_load_settings_rejects_missing_credentials():
    with pytest.raises(ConfigError, match="FNB_USER_ID.*FNB_PASSWORD"):
        load_settings({})
```

- [ ] **Step 2: 테스트가 모듈 부재로 실패하는지 확인**

Run: `py -m pytest tests/test_config.py -v`
Expected: FAIL because `config` does not exist.

- [ ] **Step 3: 유효 설정 테스트 추가**

```python
def test_load_settings_builds_settings_from_environment():
    settings = load_settings({"FNB_USER_ID": "tester", "FNB_PASSWORD": "secret"})

    assert settings.base_url == "https://fcdaum.com"
    assert settings.user_id == "tester"
    assert settings.password == "secret"
    assert settings.timeout_seconds == 30
```

- [ ] **Step 4: 최소 설정 구현 및 템플릿 작성**

`config.py`에 불변 `Settings` 데이터클래스, `ConfigError`, `.env` 로드 후 공백 값까지 거부하는 `load_settings`를 구현한다. `.env.example`에는 `FNB_USER_ID=`와 `FNB_PASSWORD=`만 둔다. `.gitignore`에는 `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`를 추가한다. `requirements.txt`에는 `requests`, `python-dotenv`, `pytest`를 고정된 호환 버전 범위로 추가한다.

- [ ] **Step 5: 설정 테스트 통과 확인**

Run: `py -m pytest tests/test_config.py -v`
Expected: 2 passed.

### Task 2: 로그인과 공통 HTTP 오류 처리

**Files:**
- Create: `fnb_client.py`
- Create: `tests/test_fnb_client_auth.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: `FnbClient(settings: Settings, session: requests.Session | compatible object)`
- Produces: `FnbClient.login() -> dict[str, object]`
- Produces: `ApiError`, `CloudflareChallengeError`, `AuthenticationError`

- [ ] **Step 1: 로그인 요청 테스트 작성**

가짜 세션이 받은 URL, JSON payload, timeout을 기록하게 만들고 `login()`이 `/api/v2/bff/logged-in-user`에 `userId`, `password`, `languageCode: ko`를 전송하는지 검증한다. 성공 응답은 `userNo`와 `qsc-report`, `qsc-mission`의 `MANAGE` 권한을 반환한다.

- [ ] **Step 2: 로그인 테스트의 예상 실패 확인**

Run: `py -m pytest tests/test_fnb_client_auth.py::test_login_posts_credentials_and_sets_user_header -v`
Expected: FAIL because `FnbClient` does not exist.

- [ ] **Step 3: 최소 로그인 구현**

`FnbClient.login()`이 POST를 실행하고 JSON을 검증한 뒤 세션 헤더에 `Accept: application/json`, `Referer: https://fcdaum.com/`, `X-Logged-In-User-No`를 설정하도록 구현한다. 응답 객체나 Cookie 내용을 로그로 전달하지 않는다.

- [ ] **Step 4: Cloudflare 및 인증 오류 테스트 추가**

`403`과 `Cf-Mitigated: challenge` 조합은 `CloudflareChallengeError`여야 한다. 비정상 상태, JSON 아님, `userNo` 누락, QSC 권한 없음은 각각 비밀값이 없는 `ApiError` 또는 `AuthenticationError` 메시지를 만들어야 한다.

- [ ] **Step 5: 오류 처리 최소 구현 후 테스트 확인**

Run: `py -m pytest tests/test_fnb_client_auth.py -v`
Expected: all authentication tests pass.

### Task 3: 리포트와 문제항목 API

**Files:**
- Modify: `fnb_client.py`
- Create: `tests/test_fnb_client_reports.py`

**Interfaces:**
- Produces: `get_reports() -> dict[str, object]`
- Produces: `get_report_detail(report_no: int) -> dict[str, object]`
- Produces: `get_report_issues(report_no: int, consequence: Literal["fine", "suspension"]) -> dict[str, object]`

- [ ] **Step 1: 리포트 목록 파라미터 실패 테스트 작성**

`get_reports()`가 `currentPage=1`, `sizePerPage=10`, `sortField=visitDate`, `sortDirection=DESC`, `useYn=y`, `statuses=r,o`를 전송하는지 검증한다.

- [ ] **Step 2: 실패 확인 후 최소 목록 구현**

Run: `py -m pytest tests/test_fnb_client_reports.py::test_get_reports_uses_expected_query -v`
Expected: FAIL because method is missing. 메서드를 구현하고 같은 테스트가 PASS인지 확인한다.

- [ ] **Step 3: 상세 URL 테스트와 구현**

`report_no=789570`일 때 URL이 `/api/v2/bff/fnb-qsc-report-info/789570`으로 끝나는지 먼저 실패 테스트로 확인한 뒤 구현한다. `bool`은 정수 관리번호로 허용하지 않는다.

- [ ] **Step 4: 문제항목 필터 테스트와 구현**

과태료 호출은 `reportNos=789570`, `fineFrom=1`, 영업정지 호출은 `reportNos=789570`, `suspensionFrom=1`을 사용하고 공통으로 `sortField=reportVisitDate`, `sortDirection=DESC`를 사용하는지 각각 검증 후 구현한다. 다른 consequence 값은 `ValueError`로 거부한다.

- [ ] **Step 5: 리포트 테스트 전체 통과 확인**

Run: `py -m pytest tests/test_fnb_client_reports.py -v`
Expected: all report tests pass.

### Task 4: 품질미션 API

**Files:**
- Modify: `fnb_client.py`
- Create: `tests/test_fnb_client_missions.py`

**Interfaces:**
- Produces: `get_missions() -> dict[str, object]`

- [ ] **Step 1: 품질미션 쿼리 실패 테스트 작성**

`get_missions()`가 `currentPage=1`, `sizePerPage=10`, `sortField=regDate,missionNo`, `sortDirection=DESC`, `viewType=c`, `statuses=DOING,ACTION,REDOING,COMPLETE`를 전송하는지 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `py -m pytest tests/test_fnb_client_missions.py -v`
Expected: FAIL because `get_missions` is missing.

- [ ] **Step 3: 최소 구현 후 통과 확인**

공통 GET JSON 처리기를 재사용해 메서드를 구현한다.

Run: `py -m pytest tests/test_fnb_client_missions.py -v`
Expected: PASS.

### Task 5: 안전한 진단 실행기

**Files:**
- Modify: `crawling.py`
- Create: `tests/test_crawling.py`

**Interfaces:**
- Produces: `run_diagnostics(client: FnbClient, output: TextIO) -> int`
- Produces: `main() -> int`

- [ ] **Step 1: 전체 호출 순서 실패 테스트 작성**

가짜 클라이언트로 로그인 → 리포트 목록 → 첫 리포트 상세 → 과태료 → 영업정지 → 품질미션 순서를 검증한다. 리포트가 0건이면 상세와 문제항목을 생략하되 품질미션은 계속 호출해야 한다.

- [ ] **Step 2: 출력 보안 실패 테스트 작성**

가짜 응답에 `access_token_production`, `refresh_token_production`, `password`, `Cookie` 문자열을 넣고도 출력에는 단계명, 전체 건수, 현재 반환 건수, `reportNo`만 있으며 비밀 문자열이나 값이 없는지 검증한다.

- [ ] **Step 3: 실패 확인 후 최소 실행기 구현**

Run: `py -m pytest tests/test_crawling.py -v`
Expected: FAIL because diagnostic functions are missing. `run_diagnostics`와 예외별 종료코드를 구현한다.

- [ ] **Step 4: 진단 테스트 통과 확인**

Run: `py -m pytest tests/test_crawling.py -v`
Expected: all diagnostic tests pass.

### Task 6: Windows 설치 및 실행 문서와 최종 검증

**Files:**
- Create: `README.md`
- Modify: `.env.example`

**Interfaces:**
- Documents: Python 3.12 설치, venv, dependency installation, `.env` creation, test and diagnostic commands.

- [ ] **Step 1: README에 정확한 설치 명령 작성**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pytest -v
python crawling.py
```

PowerShell 실행 정책으로 활성화가 막힐 경우 활성화 없이 `.\.venv\Scripts\python.exe`를 사용하는 명령도 함께 작성한다.

- [ ] **Step 2: 전체 정적 보안 점검**

Run: `rg -n "access_token_production|refresh_token_production|Set-Cookie|Cookie|FNB_PASSWORD=" -g "*.py" -g ".env*"`
Expected: 토큰 및 Cookie를 출력하는 코드가 없고 `.env.example`의 `FNB_PASSWORD=`만 빈 값으로 존재한다.

- [ ] **Step 3: 전체 테스트 실행**

Run: `py -m pytest -v`
Expected: all tests pass without warnings or network access.

- [ ] **Step 4: 실제 실행 전 안전 실패 확인**

Run: `py crawling.py` with no `.env`.
Expected: missing `FNB_USER_ID` and `FNB_PASSWORD` message, no traceback, non-zero exit code, no network request.

- [ ] **Step 5: 사용자 통합 테스트 안내**

사용자가 `.env`를 입력한 뒤 `python crawling.py`를 실행하도록 안내한다. 성공 시 각 API의 상태와 건수, 실패 시 Cloudflare/인증/응답 오류 분류 결과를 전달받는다.
