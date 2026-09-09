# FC다움 날짜별 실행 로그 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** 수집 실행 여부와 결과를 `updated_at` 변경과 무관하게 날짜별 파일로 확인할 수 있게 한다.

**Architecture:** `crawling.py`에 콘솔과 파일을 함께 쓰는 작은 출력 어댑터와 실행 로깅 진입점을 추가한다. 기존 수집 함수는 전달받은 `TextIO`에 계속 출력하므로 수집 로직과 저장소 로직은 변경하지 않는다.

**Tech Stack:** Python 3, 표준 라이브러리 `pathlib`, `contextlib`, `time`, pytest

## Global Constraints

- 로그 날짜와 표시 시각은 KST를 사용한다.
- 로그는 `logs/fcdaum_YYYY-MM-DD.log`에 추가 모드로 저장한다.
- 민감정보와 API 응답 원문은 기록하지 않는다.
- 기존 콘솔 출력을 유지한다.

---

### Task 1: 날짜별 로그 출력 구현

**Files:**
- Modify: `crawling.py`
- Modify: `tests/test_crawling.py`

**Interfaces:**
- Produces: `daily_log_path(run_at: datetime, log_dir: Path) -> Path`
- Produces: `TeeOutput(*streams: TextIO)`
- Produces: `run_with_logging(..., log_dir: Path = Path("logs")) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

  고정 KST 시각으로 `fcdaum_2026-07-23.log`가 생성되고, 시작·완료·브랜드별 DB 통계가 콘솔과 파일 양쪽에 기록되는 테스트를 작성한다. 같은 날짜에 두 번 실행했을 때 기존 로그가 유지되며 두 번째 실행 내용이 추가되는 테스트도 작성한다.

- [ ] **Step 2: 실패 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests\test_crawling.py -q`

  Expected: 새 로깅 인터페이스를 가져올 수 없어 실패한다.

- [ ] **Step 3: 최소 구현**

  `logs` 디렉터리를 생성하고 UTF-8 추가 모드로 파일을 연다. 시작 시각, 기존 `run_all_brands` 출력, 종료 코드와 소요 시간을 콘솔과 파일에 동시에 기록한다. 설정 오류와 예상하지 못한 예외도 종료 결과와 함께 기록한다.

- [ ] **Step 4: 대상 테스트 통과 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests\test_crawling.py -q`

  Expected: 모든 `test_crawling.py` 테스트가 통과한다.

- [ ] **Step 5: 전체 회귀 테스트**

  Run: `.venv\Scripts\python.exe -m pytest -q`

  Expected: 전체 테스트가 실패 없이 통과한다.

- [ ] **Step 6: 실제 진입점 점검**

  Run: `.venv\Scripts\python.exe crawling.py --help`

  Expected: 종료 코드 0이며 기존 `--from-date` 도움말이 표시된다.
