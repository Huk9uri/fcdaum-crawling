# FC다움 매장명 표준화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세 FC다움 테이블의 매장명을 브랜드별 표준 형식으로 저장한다.

**Architecture:** 순수 함수 `normalize_store_name()`이 브랜드 코드와 API 매장명을 받아 표준값을 반환한다. 리포트, 문제항목, 품질미션 매핑이 모두 이 함수를 사용하고 기존 upsert 변경 감지가 DB를 갱신한다.

**Tech Stack:** Python 3, pytest, MSSQL

## Global Constraints

- 한촌은 지점명만 저장하고 `점`으로 끝낸다.
- 육수당은 `육수당 {지점명}` 형식으로 저장하고 `점`으로 끝낸다.
- `NULL`과 빈 문자열을 임의 값으로 바꾸지 않는다.
- Git 저장소가 유효하지 않아 커밋은 생략한다.

---

### Task 1: 공통 매장명 정규화 함수

**Files:**
- Modify: `tests/test_mssql_mapping.py`
- Modify: `mssql_repository.py`

- [ ] 브랜드별 정상·예외 입력의 실패 테스트를 작성한다.
- [ ] 테스트 실패를 확인한다.
- [ ] 정규식 기반 `normalize_store_name()`을 최소 구현한다.
- [ ] 세 매핑의 `store_name`에 공통 함수를 적용한다.
- [ ] 매핑 테스트를 실행한다.

### Task 2: 전체 검증 및 실제 데이터 갱신

**Files:**
- Verify: 전체 프로젝트와 MSSQL

- [ ] 전체 pytest와 Python 문법 검사를 실행한다.
- [ ] 크롤러를 실제 실행한다.
- [ ] 세 테이블의 고유 매장명을 조회해 표준 위반값이 없는지 확인한다.
- [ ] 크롤러를 다시 실행해 전체 미변경 판정을 확인한다.
