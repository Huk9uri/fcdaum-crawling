# FCdaum Monthly Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 입력한 KST 날짜 범위를 월별 독립 구간으로 나눠 FC다움 데이터를 순차 수집·커밋하고 실패 월에서 안전하게 중단하는 백필 기능을 추가한다.

**Architecture:** `MonthlyCollector`는 선택적 종료 상한을 받아 `[start, end_exclusive)` 범위만 수집한다. `crawling.py`는 입력 날짜 검증, 월 구간 생성, 월별 `run_all_brands()` 호출과 로그를 담당하며 기존 정기 실행과 `--from-date` 경로를 그대로 유지한다.

**Tech Stack:** Python 3.12, argparse, datetime, pytest

## Global Constraints

- 백필 CLI는 `--backfill-from YYYY-MM-DD --backfill-to YYYY-MM-DD`이다.
- 두 백필 옵션은 함께 입력해야 한다.
- 백필 옵션과 `--from-date`는 상호 배타적이다.
- 날짜는 KST 기준이고 종료일을 포함한다.
- 내부 수집 범위는 `[start, end_exclusive)`이다.
- 월은 오래된 순서로 처리한다.
- 실패 월 이후 월은 실행하지 않는다.
- 월별·브랜드별 기존 트랜잭션 경계를 유지한다.
- 별도 체크포인트 파일을 만들지 않는다.
- 기존 정기 실행과 `--from-date` 동작을 변경하지 않는다.
- 민감정보를 로그에 출력하지 않는다.

---

### Task 1: 종료 상한 범위 수집

**Files:**
- Modify: `collector.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Consumes: `collection_start: datetime | None`, `collection_end: datetime | None`
- Produces: `MonthlyCollector.collect(..., collection_end=...)`가 `[start, end)`에 속한 리포트와 품질미션만 반환

- [ ] **Step 1: 종료 상한 필터 회귀 테스트 작성**

  다음 동작을 검증한다.

  - 종료 상한보다 최신인 첫 페이지 항목은 제외하지만 다음 페이지 조회를 계속한다.
  - 시작일과 같은 항목은 포함한다.
  - 종료 상한과 같은 항목은 제외한다.
  - 시작일보다 오래된 항목을 만나면 중단한다.
  - 품질미션도 `regDate`에 같은 범위를 적용한다.
  - `collection_end <= collection_start`를 거부한다.

- [ ] **Step 2: 테스트가 현재 코드에서 실패하는지 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_collector.py -v`

  Expected: `collection_end` 인자를 지원하지 않아 FAIL.

- [ ] **Step 3: 수집기에 최소 구현 추가**

  `collect()`와 `_collect_recent_pages()`에 종료 상한을 전달하고 다음 포함 조건을 적용한다.

  ```python
  cutoff_ms <= value < end_ms
  ```

  상한보다 최신인 데이터는 건너뛰되 페이지 조회를 중단하지 않는다.

- [ ] **Step 4: 수집기 테스트 통과 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_collector.py -v`

  Expected: 모든 collector 테스트 PASS.

### Task 2: 날짜 검증과 월 구간 생성

**Files:**
- Modify: `crawling.py`
- Test: `tests/test_crawling.py`

**Interfaces:**
- Produces: `parse_kst_date(value: str, option_name: str) -> datetime`
- Produces: `build_monthly_ranges(start: datetime, end_inclusive: datetime) -> list[tuple[datetime, datetime]]`

- [ ] **Step 1: 날짜와 월 구간 테스트 작성**

  다음 결과를 literal datetime으로 검증한다.

  - 2024-01-15~2024-03-10의 3개 반개구간
  - 2024년 윤년 2월
  - 2024-12~2025-01 연도 경계
  - 시작일과 종료일이 같은 하루
  - 시작일이 종료일보다 늦은 경우
  - 미래 종료일

- [ ] **Step 2: 테스트 실패 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py -v`

  Expected: 새 함수가 없어 수집 단계에서 FAIL.

- [ ] **Step 3: 날짜 파싱과 월 구간 생성 구현**

  각 구간의 종료값은 다음 달 1일 또는 사용자 종료일 다음 날 중 빠른 값으로 만든다.

- [ ] **Step 4: 날짜 테스트 통과 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py -v`

  Expected: 날짜·구간 테스트 PASS.

### Task 3: 월별 백필 실행기

**Files:**
- Modify: `crawling.py`
- Test: `tests/test_crawling.py`

**Interfaces:**
- Produces: `run_monthly_backfill(...) -> int`
- Consumes: `run_all_brands(..., collection_start, collection_end)`

- [ ] **Step 1: 월별 실행 순서와 중단 테스트 작성**

  fake 월 실행 함수를 사용해 다음을 검증한다.

  - 오래된 월부터 실행
  - 월별 시작·완료 로그
  - 모든 월 성공 시 0
  - 두 번째 월 실패 시 세 번째 월 미실행
  - 실패 시 1

- [ ] **Step 2: 실패 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py -v`

  Expected: 월별 실행기가 없어 FAIL.

- [ ] **Step 3: 월별 실행기 구현**

  각 월에 `run_all_brands()`를 호출하고 0이 아니면 즉시 중단한다. 표시 종료일은 `end_exclusive - 1 day`를 사용한다.

- [ ] **Step 4: 실행기 테스트 통과 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py -v`

  Expected: 월별 실행 테스트 PASS.

### Task 4: CLI 통합과 기존 동작 보존

**Files:**
- Modify: `crawling.py`
- Modify: `README.md`
- Test: `tests/test_crawling.py`

**Interfaces:**
- Consumes: argparse의 `--from-date`, `--backfill-from`, `--backfill-to`
- Produces: 일반 실행, 단일 시작일 실행, 월별 백필 실행 중 정확히 하나의 경로

- [ ] **Step 1: CLI 검증 가능한 함수 테스트 작성**

  백필 옵션 한쪽만 입력, `--from-date` 동시 입력, 미래 종료일, 역전 범위를 차단하는 테스트를 작성한다.

- [ ] **Step 2: 실패 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py -v`

  Expected: 백필 CLI가 없어 FAIL.

- [ ] **Step 3: argparse와 main 실행 경로 구현**

  백필이면 월별 실행기를 호출하고, 아니면 기존 `run_all_brands()` 경로를 사용한다.

- [ ] **Step 4: README 사용법 추가**

  다음 명령과 실패 후 동일 명령 재실행이 안전하다는 설명을 추가한다.

  ```powershell
  .\.venv\Scripts\python.exe crawling.py --backfill-from 2024-01-01 --backfill-to 2025-12-31
  ```

- [ ] **Step 5: 관련 테스트 통과 확인**

  Run: `\.venv\Scripts\python.exe -m pytest tests/test_crawling.py tests/test_collector.py -v`

  Expected: 모든 관련 테스트 PASS.

### Task 5: 전체 회귀 검증

**Files:**
- Verify: `collector.py`
- Verify: `crawling.py`
- Verify: `README.md`
- Verify: `tests/test_collector.py`
- Verify: `tests/test_crawling.py`

**Interfaces:**
- Produces: 기존 기능과 신규 월별 백필이 함께 통과하는 검증 결과

- [ ] **Step 1: 전체 자동화 테스트 실행**

  Run: `\.venv\Scripts\python.exe -m pytest -q`

  Expected: 0 failures.

- [ ] **Step 2: Python 구문 컴파일 검사**

  Run: `\.venv\Scripts\python.exe -m py_compile crawling.py collector.py`

  Expected: exit code 0.

- [ ] **Step 3: CLI 도움말 확인**

  Run: `\.venv\Scripts\python.exe crawling.py --help`

  Expected: `--from-date`, `--backfill-from`, `--backfill-to`가 표시됨.

- [ ] **Step 4: 변경 파일과 민감정보 점검**

  변경 파일에 계정 ID, 비밀번호, 토큰 또는 DB 비밀번호가 추가되지 않았는지 확인한다.
