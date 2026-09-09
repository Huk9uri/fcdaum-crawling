# 품질미션 한글 상태 및 실시간 마감 View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API 영문 미션 상태를 한글로 저장하고, 조회 시 미제출·마감 미션을 `마감됨`으로 표시하는 MSSQL View를 제공한다.

**Architecture:** Python 매핑 계층에서 API 상태를 한글로 변환한다. MSSQL View는 원본 테이블의 저장 상태를 유지하면서 `owner_submitted_at`, `due_date`, UTC 현재 시각으로 `display_status`를 계산한다.

**Tech Stack:** Python 3, pytest, MSSQL T-SQL

## Global Constraints

- `DOING`, `ACTION`, `COMPLETE`, `REDOING`만 정의된 한글 상태로 변환한다.
- 알 수 없는 상태는 원본값을 유지하고 `NULL`은 `NULL`로 유지한다.
- `마감됨`은 테이블에 저장하지 않는다.
- UTC 저장값은 `SYSUTCDATETIME()`과 비교한다.
- Git 저장소가 유효하지 않아 커밋은 생략한다.

---

### Task 1: 상태 변환 구현

**Files:**
- Modify: `tests/test_mssql_mapping.py`
- Modify: `mssql_repository.py`

- [ ] 네 가지 상태, 미등록 상태, `NULL`을 검증하는 실패 테스트를 작성한다.
- [ ] 해당 테스트가 기존 원본 상태 저장 때문에 실패하는지 확인한다.
- [ ] `translate_mission_status()`를 추가하고 `map_mission()`에서 사용한다.
- [ ] 매핑 테스트를 다시 실행해 통과를 확인한다.

### Task 2: MSSQL View SQL 제공

**Files:**
- Create: `sql/fc_daum_mission_view.sql`

- [ ] `mission_status`를 `NVARCHAR(30)`으로 변경하는 SQL을 작성한다.
- [ ] `dbo.vw_fc_daum_mission`을 `CREATE OR ALTER VIEW`로 작성한다.
- [ ] View의 `display_status`가 미제출·기한 경과 시 `마감됨`을 반환하도록 작성한다.
- [ ] 전체 조회와 마감 미션 조회 예시를 주석으로 제공한다.

### Task 3: 전체 검증

**Files:**
- Verify: `mssql_repository.py`
- Verify: `sql/fc_daum_mission_view.sql`
- Verify: `tests/`

- [ ] 전체 pytest를 실행한다.
- [ ] Python 문법 검사를 실행한다.
- [ ] SQL 전문을 검토해 UTC 비교와 컬럼명이 실제 스키마와 일치하는지 확인한다.
