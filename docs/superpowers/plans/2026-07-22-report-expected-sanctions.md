# 리포트 예상 처분 합계 저장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최근 수집 리포트의 문제항목 예상 과태료와 예상 영업정지 일수를 합산해 리포트 테이블에 저장한다.

**Architecture:** Collector는 문제항목 API를 조회한 리포트 번호 집합을 결과에 포함한다. Repository는 해당 리포트만 합계 포함 명세로 upsert하고, 품질미션 외래키 지원용 과거 리포트는 기본 명세로 upsert해 기존 합계를 보존한다.

**Tech Stack:** Python 3, pytest, pyodbc, MSSQL T-SQL

## Global Constraints

- 합계 키는 브랜드별 `report_no`다.
- `NULL` 과태료와 영업정지 값은 0으로 합산한다.
- 문제항목 조회가 완료된 리포트에 문제가 없으면 합계는 0이다.
- 지원용 과거 리포트의 기존 합계는 0으로 덮어쓰지 않는다.
- 리포트·문제항목·미션은 기존처럼 하나의 트랜잭션에 저장한다.
- Git 저장소가 유효하지 않아 커밋은 생략한다.

---

### Task 1: 문제항목 조회 대상 리포트 추적

**Files:**
- Modify: `collector.py`
- Modify: `tests/test_collector.py`
- Modify: `tests/test_mssql_repository.py`

- [ ] 최근 리포트 번호는 `issue_scanned_report_nos`에 포함되고 지원용 과거 리포트는 제외되는 실패 테스트를 작성한다.
- [ ] 테스트 실패를 확인한다.
- [ ] `BrandCollection`에 `issue_scanned_report_nos: frozenset[int]`를 추가한다.
- [ ] 지원용 리포트 추가 전에 최근 리포트 번호 집합을 저장한다.
- [ ] 모든 테스트 fixture를 새 필드에 맞춘다.
- [ ] Collector 테스트를 실행한다.

### Task 2: 예상 처분 합계 계산 및 리포트 분리 upsert

**Files:**
- Modify: `mssql_repository.py`
- Modify: `tests/test_mssql_mapping.py`
- Modify: `tests/test_mssql_repository.py`

- [ ] 여러 문제항목, `NULL`, 빈 문제항목의 합계를 검증하는 실패 테스트를 작성한다.
- [ ] 최근 리포트에 합계가 매핑되고 지원용 리포트는 합계 없는 명세로 저장되는 실패 테스트를 작성한다.
- [ ] 실패를 확인한다.
- [ ] `aggregate_expected_sanctions()`를 구현한다.
- [ ] `map_report()`가 선택적으로 합계를 포함하도록 구현한다.
- [ ] 합계 포함 `REPORT_SPEC`과 지원용 `REPORT_BASE_SPEC`을 정의한다.
- [ ] 두 리포트 그룹의 `BatchStats`를 합산해 기존 반환 형식을 유지한다.
- [ ] 매핑 및 Repository 테스트를 실행한다.

### Task 3: DB 마이그레이션

**Files:**
- Create: `sql/add_report_expected_sanctions.sql`

- [ ] 리포트 테이블에 두 nullable 컬럼을 조건부 추가한다.
- [ ] 기존 문제항목을 브랜드·리포트별로 합산해 기존 리포트를 갱신한다.
- [ ] 문제항목이 없는 리포트를 0으로 채운다.
- [ ] 두 컬럼을 `NOT NULL`로 변경한다.

### Task 4: 전체 검증 및 실제 적재

**Files:**
- Verify: 전체 프로젝트와 MSSQL

- [ ] 전체 pytest와 Python 문법 검사를 실행한다.
- [ ] DB 마이그레이션을 실행하고 기존 합계를 확인한다.
- [ ] 크롤러를 실행해 최근 리포트 합계 저장을 검증한다.
- [ ] 크롤러를 재실행해 전체 미변경 판정을 검증한다.
