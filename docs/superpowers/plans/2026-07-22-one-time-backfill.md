# FC다움 일회성 시작일 백필 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 명시한 KST 날짜부터 현재까지 한 번 수집할 수 있는 CLI 옵션을 추가하고 2026-01-01 백필을 실행한다.

**Architecture:** CLI 계층이 `--from-date`를 KST datetime으로 변환해 수집기에 전달한다. 수집기는 명시 시작일이 없을 때만 기존 최근 1개월 계산을 사용한다.

**Tech Stack:** Python 3, argparse, pytest, MSSQL

## Global Constraints

- 기본 실행 범위는 최근 1개월로 유지한다.
- 명시 날짜는 KST 00:00이며 시작 경계를 포함한다.
- 잘못된 날짜와 미래 날짜는 수집 전에 거부한다.
- Git 저장소가 유효하지 않아 커밋은 생략한다.

---

### Task 1: 명시 시작일 수집 지원

**Files:**
- Modify: `tests/test_collector.py`
- Modify: `collector.py`
- Modify: `tests/test_crawling.py`
- Modify: `crawling.py`

- [ ] 시작일 변환과 명시 cutoff 사용 실패 테스트를 작성한다.
- [ ] 실패를 확인한다.
- [ ] 수집기에 선택적 시작 시각을 추가한다.
- [ ] CLI의 `--from-date` 파싱과 검증을 구현한다.
- [ ] 관련 테스트를 실행한다.

### Task 2: 전체 검증 및 백필

**Files:**
- Verify: 전체 프로젝트와 MSSQL

- [ ] 전체 pytest와 문법 검사를 실행한다.
- [ ] `--from-date 2026-01-01`로 실제 백필을 실행한다.
- [ ] 브랜드별 적재 결과와 DB 건수를 확인한다.
- [ ] 옵션 없는 기본값이 최근 1개월로 유지되는지 확인한다.
