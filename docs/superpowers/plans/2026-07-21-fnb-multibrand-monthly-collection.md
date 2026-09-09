# F&B Multi-Brand Monthly Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 한촌설렁탕과 육수당 계정으로 각각 로그인하여 실행 시각 기준 최근 1개월의 리포트·문제항목·품질미션을 모든 페이지에서 수집하고, 실패 브랜드만 한 번 일괄 재시도한다.

**Architecture:** 설정은 두 `BrandAccount`를 만들고 각 브랜드 실행마다 독립 `FnbClient` 세션을 생성한다. `collector.py`가 한국 시간 기준 한 달 전 cutoff를 Epoch 밀리초로 계산하고 최신순 페이지를 경계까지 순회하며, `crawling.py`가 브랜드 1차 실행과 실패 브랜드 2차 실행을 조정한다.

**Tech Stack:** Python 3.12, requests, python-dotenv, python-dateutil, pytest

## Global Constraints

- 리포트 범위 필드는 `visitDate`, 품질미션 범위 필드는 `regDate`이다.
- 날짜 값은 13자리 Epoch 밀리초 정수로 비교한다.
- 기준 시각은 `Asia/Seoul` 실행 시각에서 달력 기준 1개월을 뺀 시각이다.
- 기간 경계를 만날 때까지 모든 페이지를 조회하며 10건 또는 첫 페이지로 제한하지 않는다.
- 브랜드별 HTTP 세션과 인증 Cookie는 공유하지 않는다.
- 비밀번호, Cookie, token은 출력하거나 저장하지 않는다.
- MSSQL 적재는 이 변경 범위에 포함하지 않는다.

---

### Task 1: 다중 브랜드 환경설정

**Files:** `config.py`, `.env`, `.env.example`, `tests/test_config.py`

- [ ] `BrandAccount(code, name, user_id, password)`와 `Settings(accounts, page_size)`를 기대하는 실패 테스트를 작성한다.
- [ ] `HANCHON_USER_ID`, `HANCHON_PASSWORD`, `YUKSUDANG_USER_ID`, `YUKSUDANG_PASSWORD` 중 하나라도 누락되면 모든 이름을 포함한 `ConfigError`가 발생하는지 확인한다.
- [ ] 테스트가 기존 단일 계정 구조 때문에 실패하는지 실행해 확인한다.
- [ ] 두 브랜드를 고정 순서로 반환하고 기본 페이지 크기 100을 제공하도록 최소 구현한다.
- [ ] `.env`와 `.env.example`에서 기존 `FNB_*`를 제거하고 네 값을 추가한다.
- [ ] 설정 테스트 전체 통과를 확인한다.

### Task 2: 페이지 지정 가능한 API 클라이언트

**Files:** `fnb_client.py`, `tests/test_fnb_client_auth.py`, `tests/test_fnb_client_reports.py`, `tests/test_fnb_client_missions.py`

- [ ] 클라이언트가 `BrandAccount`의 자격증명으로 로그인하는 실패 테스트를 작성한다.
- [ ] 리포트·문제항목·품질미션 메서드가 `current_page`, `size_per_page`를 받아 쿼리에 넣는 실패 테스트를 작성한다.
- [ ] 기존 고정 1페이지·10건 구현 때문에 실패하는지 확인한다.
- [ ] 클라이언트 생성자와 각 API 메서드를 최소 수정한다.
- [ ] 인증과 API 파라미터 테스트 전체 통과를 확인한다.

### Task 3: 최근 1개월 전체 페이지 수집기

**Files:** `collector.py`, `tests/test_collector.py`, `requirements.txt`

- [ ] 3월 31일 기준 한 달 전이 2월 말일로 보정되는 cutoff 실패 테스트를 작성한다.
- [ ] 최신순 리포트 페이지에서 cutoff 이상만 포함하고 오래된 항목을 만난 페이지 뒤에는 추가 요청하지 않는 실패 테스트를 작성한다.
- [ ] 품질미션도 `regDate` 기준으로 같은 동작을 하는 실패 테스트를 작성한다.
- [ ] 기간 내 각 리포트의 상세를 호출하고 과태료·영업정지 문제항목을 모든 페이지에서 읽어 `answerNo` 기준 병합하는 실패 테스트를 작성한다.
- [ ] `python-dateutil` 의존성과 `MonthlyCollector`, `BrandCollection`을 최소 구현한다.
- [ ] 빈 페이지, 정확한 cutoff 경계, 중복 answerNo 테스트를 통과시킨다.

### Task 4: 브랜드 실패 일괄 재시도 실행기

**Files:** `crawling.py`, `tests/test_crawling.py`

- [ ] 한촌 실패 후 육수당이 계속 실행되는 실패 테스트를 작성한다.
- [ ] 1차 실패 브랜드만 새 클라이언트로 한 번 재시도하는 실패 테스트를 작성한다.
- [ ] 재시도 성공 시 종료코드 0, 최종 실패가 남으면 종료코드 1과 브랜드명만 출력하는 실패 테스트를 작성한다.
- [ ] 출력에 브랜드별 리포트·문제항목·품질미션 건수만 포함되고 비밀값은 없는지 검증한다.
- [ ] 실행기를 최소 구현하고 테스트 전체를 통과시킨다.

### Task 5: 문서와 최종 검증

**Files:** `README.md`

- [ ] README의 환경변수와 수집 범위를 두 브랜드·최근 1개월 전체 페이지로 수정한다.
- [ ] `python -m pytest -v`로 전체 테스트를 실행한다.
- [ ] `python -m compileall -q config.py fnb_client.py collector.py crawling.py`를 실행한다.
- [ ] 소스에서 비밀값 출력과 기존 `FNB_USER_ID`, `FNB_PASSWORD` 참조가 없는지 검색한다.
- [ ] 실제 `.env`로 통합 실행하여 브랜드별 성공 또는 비민감 오류만 확인한다.
