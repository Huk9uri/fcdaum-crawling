# Server Migration Report Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FC다움과 `review_analysis`의 서버 PC 이관 내역을 하나의 업무로 묶은 핵심 결과 중심의 2026년 7월 27일 업무 보고서를 작성한다.

**Architecture:** 공통 서버 이관 절차는 상위 항목에서 한 번만 설명하고, 두 프로젝트의 경로·실행 주기·계정·검증 결과는 비교표와 프로젝트별 짧은 하위 항목으로 구분한다. 세부 명령어와 반복 설명은 제거하되 운영 전환을 입증하는 상태값과 실행 결과는 유지한다.

**Tech Stack:** Markdown

## Global Constraints

- 두 프로젝트를 하나의 상위 업무로 묶는다.
- 프로젝트별 경로, 실행 주기, 실행 계정 및 검증 결과는 표로 비교한다.
- 공통 서버 구성과 로컬 작업 비활성화 절차는 중복 작성하지 않는다.
- FC다움의 수집 건수와 종료 코드, `review_analysis`의 실행 상태는 유지한다.
- 향후 계획에 두 프로젝트의 최초 정기 실행 확인을 포함한다.

---

### Task 1: 업무 보고 통합 편집

**Files:**
- Modify: `26.07.27_ai전략실_최혁규_업무_보고.md`
- Reference: `docs/superpowers/specs/2026-07-27-server-migration-report-integration-design.md`
- Reference: `C:\Users\user1\.codex\attachments\15be9ba6-25ad-407d-bec7-c4604647503d\pasted-text.txt`

**Interfaces:**
- Consumes: 승인된 통합 편집 설계와 두 프로젝트의 실제 이관 결과
- Produces: 중복 없이 두 프로젝트를 하나의 서버 이관 업무로 정리한 Markdown 보고서

- [ ] **Step 1: 상위 구조를 통합한다**

  기존 FC다움 단독 구조를 다음 네 개 상위 항목으로 교체한다.

  1. 자동화 프로젝트 운영 서버 이관
  2. 프로젝트별 검증 결과
  3. 최종 운영 상태
  4. 향후 확인 계획

- [ ] **Step 2: 프로젝트 비교표를 작성한다**

  비교표에 다음 값을 정확히 포함한다.

  | 프로젝트 | 서버 경로 | 실행 방식 | 실행 시각 | 실행 계정 |
  |---|---|---|---|---|
  | FC다움 API 데이터 수집 | `C:\Users\Administrator\Desktop\iyeon_RPA\fcdaum_crawling` | Windows 주간 트리거 | 매주 월요일 오전 8시 | `Administrator` |
  | `review_analysis` | `C:\Users\Administrator\Desktop\iyeon_RPA\review_analysis` | 서버 시작 시 프로세스 실행 후 내부 일일 스케줄 | 매일 오전 5시 30분 | `SYSTEM` |

- [ ] **Step 3: 공통 이관 절차를 한 번만 서술한다**

  서버 `192.168.0.175`로의 코드·설정 이관, 프로젝트별 독립 가상환경, Windows 작업 스케줄러 등록, 기존 운영 DB 유지, 로컬 작업 비활성화를 공통 수행 내용으로 요약한다.

- [ ] **Step 4: 프로젝트별 검증 결과를 유지한다**

  FC다움은 한촌설렁탕 34/38/29건, 육수당 24/29/12건, 수동 종료 코드 0, 예약 실행 종료 코드 0을 포함한다. `review_analysis`는 패키지 67개 설치, 설정 모드 `daily`, 상태 `Running`, 결과 `0x41301`을 포함하고 `0x41301`이 실행 중 대기 상태임을 설명한다.

- [ ] **Step 5: 중복과 불필요한 세부 내용을 제거한다**

  PowerShell 명령어, UTC 변환 예시, 상세 환경변수 목록, FC다움 단독 최종 결과 및 프로젝트별로 반복된 로컬 비활성화 설명을 제거한다.

- [ ] **Step 6: 문서 구조와 필수 사실을 검증한다**

  다음 PowerShell 검증을 실행한다.

  ```powershell
  $file = 'C:\workspace\fcdaum_crawling\26.07.27_ai전략실_최혁규_업무_보고.md'
  $text = Get-Content -Raw -Encoding UTF8 $file
  $required = @(
      '자동화 프로젝트 운영 서버 이관',
      'FC다움 API 데이터 수집',
      'review_analysis',
      '매주 월요일 오전 8시',
      '매일 오전 5시 30분',
      'LastTaskResult',
      '0x41301',
      '로컬 PC'
  )
  $required | ForEach-Object {
      [pscustomobject]@{ Text = $_; Present = $text.Contains($_) }
  }
  ```

  예상 결과: 모든 항목의 `Present` 값이 `True`.

  다음 중복 제목 검사를 실행한다.

  ```powershell
  Select-String -Path $file -Encoding UTF8 -Pattern '^## 1\.'
  ```

  예상 결과: `## 1.` 상위 제목이 한 번만 출력됨.
