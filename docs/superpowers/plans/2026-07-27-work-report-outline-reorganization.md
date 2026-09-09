# Work Report Outline Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 스마트플레이스 업무와 자동화 프로젝트 서버 이관 업무를 두 개의 상위 항목으로 재구성하고 모든 하위 번호를 올바르게 정렬한 통합 업무 보고서를 만든다.

**Architecture:** 첨부 원문의 세부 내용을 업무 주제별로 묶고, `##`는 상위 업무 2개에만 사용한다. 원문의 수치·날짜·경로·상태값은 유지하면서 관련 세부 항목은 `###` 및 굵은 소제목으로 정돈한다.

**Tech Stack:** Markdown

## Global Constraints

- 대상 파일은 `26.07.27_ai전략실_최혁규_업무_보고.md`이다.
- 기존 파일을 재구성된 전체 보고서로 덮어쓴다.
- `## 1.`과 `## 2.`만 상위 제목으로 사용한다.
- 스마트플레이스 하위 번호는 `1-1`부터 `1-8`까지 사용한다.
- 서버 이관 하위 번호는 `2-1`부터 `2-6`까지 사용한다.
- 원문의 수치, 날짜, 경로, 상태 코드 및 검증 결과를 변경하지 않는다.

---

### Task 1: 통합 업무 보고 목차 재구성

**Files:**
- Modify: `26.07.27_ai전략실_최혁규_업무_보고.md`
- Reference: `C:\Users\user1\.codex\attachments\04f54313-99fe-4597-8a75-273e788dce60\pasted-text.txt`
- Reference: `docs/superpowers/specs/2026-07-27-work-report-outline-reorganization-design.md`

**Interfaces:**
- Consumes: 첨부된 전체 업무 보고 원문과 승인된 목차 설계
- Produces: 상위 업무 2개와 순차적인 하위 번호를 가진 통합 Markdown 보고서

- [ ] **Step 1: 스마트플레이스 업무를 첫 번째 상위 항목으로 묶는다**

  백필 검증, 0값 행 보정, 중복 정리, DB 중복 방지, V2.2 로직 보완, 서버 적재 검증, 테스트, 향후 계획을 `1-1`부터 `1-8`까지 배치한다.

- [ ] **Step 2: 서버 이관 업무를 두 번째 상위 항목으로 묶는다**

  추진 배경, 프로젝트별 운영 구성, 서버 환경 및 스케줄러, 검증 결과, 최종 운영 상태, 향후 계획을 `2-1`부터 `2-6`까지 배치한다.

- [ ] **Step 3: 관련 세부 항목을 합치고 원문 결과를 유지한다**

  유입 수·키워드 중복 정리는 `1-3`, 유니크 인덱스 2종은 `1-4`, V2.2 로직 3종은 `1-5`, 두 프로젝트 검증은 `2-4` 안에서 굵은 소제목으로 구분한다.

- [ ] **Step 4: 번호와 핵심 사실을 검증한다**

  다음 PowerShell 검사를 실행한다.

  ```powershell
  $file = 'C:\workspace\fcdaum_crawling\26.07.27_ai전략실_최혁규_업무_보고.md'
  $text = Get-Content -Raw -Encoding UTF8 $file
  Select-String -Path $file -Encoding UTF8 -Pattern '^## |^### '
  ```

  예상 결과:

  - `## 1.`과 `## 2.`가 각각 한 번 출력된다.
  - `### 1-1.`부터 `### 1-8.`까지 순서대로 출력된다.
  - `### 2-1.`부터 `### 2-6.`까지 순서대로 출력된다.

  다음 필수 사실 검사를 실행한다.

  ```powershell
  $required = @(
      '7,812건',
      '893건',
      '98,687건',
      '32건 통과',
      '192.168.0.175',
      '69.8초',
      '0x41301'
  )
  $required | ForEach-Object {
      [pscustomobject]@{ Text = $_; Present = $text.Contains($_) }
  }
  ```

  예상 결과: 모든 항목의 `Present` 값이 `True`.
