# FC다움 브랜드명 컬럼 추가 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세 FC다움 테이블과 품질미션 View에 한글 `brand_name`을 추가하고 수집 시 자동 저장한다.

**Architecture:** Python 공통 변환 함수가 내부 `brand_code`를 한글 브랜드명으로 변환한다. 세 데이터 매핑과 `TableSpec`이 `brand_name`을 공통으로 사용하며, MSSQL 마이그레이션은 기존 행을 채운 후 `NOT NULL`을 적용한다.

**Tech Stack:** Python 3, pytest, pyodbc, MSSQL T-SQL

## Global Constraints

- `brand_code` 키와 외래키는 변경하지 않는다.
- `hanchon`은 `한촌`, `yuksudang`은 `육수당`으로 저장한다.
- 미등록 코드는 원본 코드값을 브랜드명으로 사용한다.
- 세 테이블의 `brand_name`은 `NVARCHAR(30) NOT NULL`이다.
- Git 저장소가 유효하지 않아 커밋은 생략한다.

---

### Task 1: 브랜드명 매핑 및 Repository 명세

**Files:**
- Modify: `tests/test_mssql_mapping.py`
- Modify: `tests/test_mssql_repository.py`
- Modify: `mssql_repository.py`

- [ ] 브랜드명 변환 및 세 매핑 결과를 검증하는 실패 테스트를 작성한다.
- [ ] 세 `TableSpec`에 `brand_name`을 요구하는 실패 테스트를 작성한다.
- [ ] 실패 원인이 신규 컬럼 미구현인지 확인한다.
- [ ] 공통 변환 함수와 세 매핑, 세 `TableSpec`을 최소 수정한다.
- [ ] 관련 테스트를 다시 실행한다.

### Task 2: DB 마이그레이션 및 View 갱신

**Files:**
- Create: `sql/add_brand_name.sql`
- Modify: `sql/fc_daum_mission_view.sql`

- [ ] 세 테이블에 nullable `brand_name`을 조건부 추가한다.
- [ ] 기존 행을 코드별 한글명으로 갱신하고 미등록 코드는 원본 코드로 채운다.
- [ ] 세 컬럼을 `NVARCHAR(30) NOT NULL`로 변경한다.
- [ ] View에서 `brand_code` 다음에 `brand_name`을 표시한다.

### Task 3: 검증 및 실제 적재

**Files:**
- Verify: 전체 프로젝트와 MSSQL

- [ ] 전체 pytest와 Python 문법 검사를 실행한다.
- [ ] 마이그레이션 SQL과 View SQL을 실제 DB에 적용한다.
- [ ] 세 테이블의 `brand_name` 값과 View 컬럼 순서를 확인한다.
- [ ] 크롤러를 재실행한다.
- [ ] 재실행 결과와 브랜드별 저장값을 확인한다.
