# 품질미션 컬럼 매핑 변경 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 변경 완료된 `dbo.fc_daum_mission` 스키마에 맞춰 API 응답 매핑과 MSSQL INSERT/UPDATE 컬럼을 수정한다.

**Architecture:** `map_mission()`이 FC다움 API 필드를 DB 컬럼 이름의 딕셔너리로 변환하고, `MISSION_SPEC`이 동일한 컬럼 집합으로 조회·비교·INSERT·UPDATE를 수행한다. 삭제된 필드는 변환 결과와 SQL 대상 모두에서 제외한다.

**Tech Stack:** Python 3, pytest, pyodbc, MSSQL

## Global Constraints

- `title`은 API의 `title`을 저장한다.
- `description`은 API의 `description`을 저장한다.
- `sv_name`은 API의 `startUserNm`을 저장한다.
- `owner_submitted_at`은 API의 `actionDate`를 UTC `datetime2` 값으로 저장한다.
- `sv_completed_at`은 API의 `completeDate`를 UTC `datetime2` 값으로 저장한다.
- `actionUserNm`, `actionComment`, `completeUserNm`은 저장하지 않는다.
- 리포트와 리포트 문제항목 적재 동작은 변경하지 않는다.
- 저장소의 Git 메타데이터가 유효하지 않으므로 커밋은 생략한다.

---

### Task 1: 품질미션 API-DB 매핑 변경

**Files:**
- Modify: `tests/test_mssql_mapping.py`
- Modify: `mssql_repository.py`

**Interfaces:**
- Consumes: `map_mission(brand_code: str, item: dict[str, Any])`
- Produces: 변경된 DB 컬럼 이름을 키로 갖는 `dict[str, object]`

- [ ] **Step 1: 변경된 매핑을 요구하는 실패 테스트 작성**

  `test_map_mission_maps_requested_excel_columns_and_missing_values`를 실제 API 필드를 모두 포함하도록 변경하고 다음을 검증한다.

  ```python
  assert result["title"] == "미션 제목"
  assert result["description"] == "미션 설명"
  assert result["sv_name"] == "SV 이름"
  assert result["owner_submitted_at"] == datetime(1970, 1, 1, 0, 0, 2)
  assert result["sv_completed_at"] == datetime(1970, 1, 1, 0, 0, 3)
  assert "inspection_comment" not in result
  assert "sender_name" not in result
  assert "action_date" not in result
  assert "completed_date" not in result
  assert "action_user_name" not in result
  assert "action_comment" not in result
  ```

- [ ] **Step 2: 실패 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_mssql_mapping.py::test_map_mission_maps_requested_excel_columns_and_missing_values -v`

  Expected: 기존 키 `inspection_comment`, `sender_name`, `action_date`, `completed_date` 때문에 FAIL.

- [ ] **Step 3: 최소 매핑 구현**

  `map_mission()`의 관련 항목을 다음과 같이 변경한다.

  ```python
  "description": item.get("description"),
  "title": item.get("title"),
  "sv_name": item.get("startUserNm"),
  "owner_submitted_at": epoch_ms_to_utc_datetime(item.get("actionDate")),
  "sv_completed_at": epoch_ms_to_utc_datetime(item.get("completeDate")),
  ```

  `actionUserNm`, `actionComment`, `completeUserNm` 매핑은 추가하지 않는다.

- [ ] **Step 4: 단위 테스트 통과 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_mssql_mapping.py -v`

  Expected: 모든 매핑 테스트 PASS.

### Task 2: Repository 컬럼 명세 변경

**Files:**
- Modify: `tests/test_mssql_repository.py`
- Modify: `mssql_repository.py`

**Interfaces:**
- Consumes: `MISSION_SPEC: TableSpec`
- Produces: 변경된 14개 테이블 컬럼을 사용하는 SELECT/INSERT/UPDATE SQL

- [ ] **Step 1: 변경된 MISSION_SPEC 실패 테스트 작성**

  `MISSION_SPEC.columns`가 아래 값과 정확히 같은지 검증한다.

  ```python
  assert MISSION_SPEC.columns == (
      "brand_code", "mission_no", "report_no", "store_name", "sent_date",
      "due_date", "mission_status", "description", "title", "sv_name",
      "owner_submitted_at", "sv_completed_at",
  )
  ```

- [ ] **Step 2: 실패 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_mssql_repository.py::test_mission_spec_matches_current_database_schema -v`

  Expected: 기존 컬럼명이 남아 있어 FAIL.

- [ ] **Step 3: 최소 컬럼 명세 구현**

  `MISSION_SPEC.columns`를 다음과 같이 변경한다.

  ```python
  (
      "brand_code", "mission_no", "report_no", "store_name", "sent_date",
      "due_date", "mission_status", "description", "title", "sv_name",
      "owner_submitted_at", "sv_completed_at",
  )
  ```

- [ ] **Step 4: Repository 테스트 통과 확인**

  Run: `.venv\Scripts\python.exe -m pytest tests/test_mssql_repository.py -v`

  Expected: 모든 Repository 테스트 PASS.

### Task 3: 전체 회귀 및 DB 연결 검증

**Files:**
- Verify: `mssql_repository.py`
- Verify: `db_check.py`
- Verify: 전체 `tests/`

**Interfaces:**
- Consumes: 변경된 매핑 및 `MISSION_SPEC`
- Produces: 현재 MSSQL 스키마와 일치하는 수집·적재 프로그램

- [ ] **Step 1: 전체 자동화 테스트 실행**

  Run: `.venv\Scripts\python.exe -m pytest -q`

  Expected: 실패 0건.

- [ ] **Step 2: Python 문법 검사**

  Run: `.venv\Scripts\python.exe -m compileall -q . -x "[\\\\/]\\.venv[\\\\/]"`

  Expected: 종료 코드 0.

- [ ] **Step 3: MSSQL 테이블 연결 확인**

  Run: `.venv\Scripts\python.exe db_check.py`

  Expected: `fc_daum_qsc_report`, `fc_daum_qsc_report_issue`, `fc_daum_mission` 모두 존재.

- [ ] **Step 4: 변경 내용 자체 검토**

  `mssql_repository.py`와 테스트에서 삭제된 다음 이름이 품질미션 매핑 및 명세에 남아 있지 않은지 확인한다.

  ```text
  inspection_comment
  sender_name
  action_date
  completed_date
  action_user_name
  action_comment
  ```
