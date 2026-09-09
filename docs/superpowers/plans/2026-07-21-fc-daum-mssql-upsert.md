# FC Daum MSSQL Upsert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 두 브랜드의 최근 1개월 수집 결과를 `naverDB.dbo`의 리포트·문제항목·품질미션 테이블에 신규·변경 행만 안전하게 적재한다.

**Architecture:** `db_config.py`가 MSSQL 환경변수를 검증하고 `mssql_repository.py`가 pyodbc 연결, 필드 변환, 기존 행 비교, INSERT/UPDATE를 담당한다. 브랜드별 API 수집과 DB 적재를 한 실행 단위로 묶어 오류 시 롤백하고 실패 브랜드만 한 번 재시도한다.

**Tech Stack:** Python 3.12, pyodbc, requests, python-dotenv, python-dateutil, pytest, Microsoft SQL Server

## Global Constraints

- 대상 DB는 `naverDB`, 기본 스키마는 `dbo`이다.
- 테이블은 사용자가 이미 생성했으며 프로그램이 DDL을 실행하지 않는다.
- 부모 리포트를 문제항목과 품질미션보다 먼저 적재한다.
- 동일한 업무 값은 UPDATE하지 않으며 `updated_at`을 유지한다.
- 신규 INSERT는 DB 기본값으로 `collected_at`, `updated_at`을 설정한다.
- 변경 UPDATE만 `updated_at = SYSUTCDATETIME()`을 실행한다.
- 브랜드별 DB 트랜잭션을 사용하고 오류 시 전체 롤백한다.
- 연결 문자열, 비밀번호, Cookie, token을 출력하지 않는다.

---

### Task 1: MSSQL 환경설정과 연결 팩토리

**Files:** `db_config.py`, `.env`, `.env.example`, `requirements.txt`, `tests/test_db_config.py`

- [ ] MSSQL 필수 환경변수와 포트 검증 실패 테스트를 작성한다.
- [ ] 비밀번호를 노출하지 않는 `DatabaseSettings` 생성 테스트를 작성한다.
- [ ] 테스트 실패를 확인한 뒤 최소 설정 로더를 구현한다.
- [ ] `pyodbc` 의존성을 추가하고 드라이버 부재를 비밀값 없는 오류로 변환하는 연결 팩토리를 작성한다.

### Task 2: API 필드 매핑과 날짜 변환

**Files:** `mssql_repository.py`, `tests/test_mssql_mapping.py`

- [ ] Epoch 밀리초를 UTC naive `datetime`으로 바꾸는 테스트를 작성한다.
- [ ] 리포트 최소 컬럼 매핑 테스트를 작성한다.
- [ ] 문제항목 과태료·영업정지 및 카테고리 매핑 테스트를 작성한다.
- [ ] 품질미션 전송·마감·수행·완료 컬럼 매핑 테스트를 작성한다.
- [ ] 누락 필드는 `None`으로 처리하는 최소 매핑을 구현한다.

### Task 3: 신규·변경 감지와 UPSERT

**Files:** `mssql_repository.py`, `tests/test_mssql_repository.py`

- [ ] 현재 배치 키를 묶어서 기존 행을 조회하는 테스트를 작성한다.
- [ ] 신규 행은 INSERT, 동일 행은 무처리, 변경 행은 UPDATE로 분리하는 테스트를 작성한다.
- [ ] INSERT SQL이 감사 컬럼을 직접 지정하지 않는지 검증한다.
- [ ] UPDATE SQL이 `collected_at`을 변경하지 않고 `updated_at = SYSUTCDATETIME()`을 포함하는지 검증한다.
- [ ] 리포트→문제항목→품질미션 순서와 commit/rollback 테스트를 작성한다.
- [ ] 최소 repository 구현 후 테스트를 통과시킨다.

### Task 4: 기간 밖 부모 리포트 보완과 실행기 통합

**Files:** `collector.py`, `crawling.py`, `tests/test_collector.py`, `tests/test_crawling.py`

- [ ] 품질미션의 `reportNo`가 최근 리포트에 없으면 상세 API로 부모를 보완하는 실패 테스트를 작성한다.
- [ ] 브랜드 수집 성공 후 repository 적재를 호출하는 실패 테스트를 작성한다.
- [ ] DB 오류 시 롤백 후 다른 브랜드를 처리하고 실패 브랜드만 재시도하는 테스트를 작성한다.
- [ ] 수집·신규·변경·동일 건수만 안전하게 출력하도록 구현한다.

### Task 5: 문서 및 실제 초기 적재 검증

**Files:** `README.md`

- [ ] MSSQL 환경변수와 ODBC Driver 18 설치 안내를 추가한다.
- [ ] 전체 테스트와 compileall을 실행한다.
- [ ] DB 연결 및 대상 테이블 존재 여부를 읽기 전용으로 확인한다.
- [ ] 실제 두 브랜드 초기 적재를 실행한다.
- [ ] 각 테이블의 브랜드별 건수와 `collected_at`, `updated_at`을 조회한다.
- [ ] 즉시 한 번 재실행하여 동일 데이터의 `updated_at`이 바뀌지 않는지 확인한다.
