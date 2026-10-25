# FC다움 API 수집 DB 정의서 및 조회 가이드

문서 갱신일: 2026-09-14
## 1. 문서 목적

본 문서는 FC다움 품질관리 시스템의 리포트, 리포트 문제항목, 품질미션 데이터를 수집하여 MSSQL에 저장하는 방식과 저장된 데이터의 조회 방법을 설명합니다.

본 시스템은 Selenium 등의 브라우저 자동화로 화면을 조작하거나 웹페이지의 HTML을 분석하는 크롤링 방식이 아닙니다. FC다움 웹서비스에서 사용하는 기존 API를 직접 호출하여 JSON 응답을 수집하는 **API 기반 데이터 수집 방식**입니다.

업무 요청자가 다음 내용을 쉽게 확인할 수 있도록 작성했습니다.

- 어떤 데이터를 수집하는지
- 어느 기간의 데이터를 수집하는지
- 신규 및 변경 데이터가 어떻게 반영되는지
- 각 테이블의 컬럼이 무엇을 의미하는지
- 과태료와 영업정지 값이 어떻게 계산되는지
- 품질미션의 현재 상태와 마감 여부를 어떻게 확인하는지
- 업무 목적에 따라 어떤 SQL로 조회하면 되는지

## 2. 수집 대상

### 2-1. 대상 브랜드

| 브랜드 코드 | 브랜드명 | 계정 처리 방식 |
|---|---|---|
| `hanchon` | 한촌 | 한촌 전용 계정으로 로그인 |
| `yuksudang` | 육수당 | 육수당 전용 계정으로 로그인 |

두 브랜드는 각각 독립된 로그인 세션으로 수집합니다. 한 브랜드에서 오류가 발생해도 다음 브랜드 수집은 계속 진행하며, 모든 브랜드의 1차 수집이 끝난 후 실패한 브랜드만 한 번 더 재시도합니다.

업무 테이블의 `brand_name`은 `한촌`이며 실행 로그·감사 테이블의 브랜드명은 `한촌설렁탕`입니다. 조인·집계 기준은 표시명보다 `brand_code`를 사용합니다. 브랜드 계속 처리·재시도 대상은 코드에서 처리하는 API·DB 오류이며, 처리되지 않은 예외는 비정상 종료할 수 있습니다.

### 2-2. 수집 데이터

| 구분 | 수집 내용 |
|---|---|
| 리포트 | 매장 점검 결과, 등급, 백분율 점수, 점검자 |
| 리포트 문제항목 | 점검에서 문제가 된 항목, 점검 결과, 예상 과태료, 예상 영업정지 |
| 품질미션 | 매장에 전달된 개선 미션, 상태, 마감일, 제출 및 완료 시각 |

### 2-3. 수집 기간

수집 기간은 고정 30일이 아니라 **실행 시각 기준 최근 1개월**입니다.

예를 들어 2026년 7월 22일 오후 3시에 실행하면 2026년 6월 22일 오후 3시 이후의 데이터를 수집합니다. 월 길이에 따라 실제 수집 일수는 28일, 29일, 30일 또는 31일이 될 수 있습니다.

| 데이터 | 기간 판단에 사용하는 API 필드 |
|---|---|
| 정기 수집 리포트 | `visitDate`, `regDate`, `updateDate` 중 하나라도 최근 1개월 |
| 시작일 지정·월별 백필 리포트 | 지정 기간의 `visitDate` |
| 품질미션 | `regDate` |

기간 시작 시각과 정확히 같은 데이터도 수집 대상에 포함합니다.

초기 과거 데이터 적재가 필요한 경우에는 실행 옵션으로 시작일을 지정할 수 있습니다.

```powershell
python crawling.py --from-date 2026-01-01
```

위 옵션은 해당 실행에만 적용됩니다. 옵션 없이 실행하는 이후 주간 작업은 자동으로 최근 1개월을 수집합니다. 2026년 1월 1일부터의 초기 일괄 적재는 7월 22일 업무 보고에 완료된 것으로 기록돼 있으며, 모든 과거 기간의 현재 완전성을 보장하는 의미는 아닙니다.

장기간 데이터는 월별로 분할하여 백필할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe crawling.py --backfill-from 2024-01-01 --backfill-to 2025-12-31
```

KST 시작일·종료일을 모두 포함하고 내부적으로 `[시작일 00:00, 종료일 다음 날 00:00)` 범위를 사용합니다. 월 중간 경계도 입력한 날짜를 따르며 오래된 월부터 처리합니다. 두 백필 옵션은 함께 사용하고 `--from-date`와 혼용하지 않습니다. 품질미션은 해당 기간의 `regDate`를 사용하며 부모 리포트 보완으로 기간 밖 리포트가 추가될 수 있습니다.

## 3. 수집 방식

### 3-1. API 기반 수집 방식

본 수집 프로그램은 브라우저를 실행하거나 로그인 화면과 메뉴를 자동으로 클릭하지 않습니다. 브랜드별 계정으로 로그인 API를 호출한 뒤, 발급된 인증 세션을 유지하면서 리포트 및 품질미션 API를 직접 호출합니다.

| 구분 | 적용 여부 |
|---|---:|
| Selenium 등 브라우저 자동화 | 사용하지 않음 |
| 웹페이지 HTML 분석 및 화면 크롤링 | 사용하지 않음 |
| FC다움 기존 API 호출 | 사용 |
| API JSON 응답 수집 | 사용 |

따라서 본 작업의 정확한 명칭은 **FC다움 API 기반 데이터 수집 및 DB 적재**입니다.

### 3-2. 사용 API

| 용도 | HTTP 방식 | API 경로 |
|---|---|---|
| 로그인 | POST | `/api/v2/bff/logged-in-user` |
| 리포트 목록 | GET | `/api/v2/bff/fnb-qsc-report-info` |
| 리포트 상세 | GET | `/api/v2/bff/fnb-qsc-report-info/{reportNo}` |
| 리포트 문제항목 | GET | `/api/v2/bff/fnb-qsc-report-answer` |
| 품질미션 목록 | GET | `/api/v2/bff/fnb-mission-info` |

### 3-3. 로그인 및 인증

1. 브랜드별 계정으로 로그인 API를 호출합니다.
2. 로그인 응답으로 발급된 인증 쿠키를 HTTP 세션에 보관합니다.
3. 동일한 세션으로 리포트와 품질미션 API를 호출합니다.
4. 계정정보는 소스 코드가 아닌 환경변수 파일에서 관리합니다.

로그인 응답에서 `userNo`와 `qsc-report`, `qsc-mission`의 `MANAGE` 권한을 검증하고 이후 요청에 `X-Logged-In-User-No` 헤더를 설정합니다.

`HttpOnly` 인증 쿠키는 프로그램이 직접 값을 해석하지 않고 HTTP 세션이 자동으로 유지합니다.

### 3-4. 목록 페이지 수집

목록의 첫 페이지나 10건만 수집하지 않습니다.

1. 최신 데이터부터 페이지당 100건씩 요청합니다.
2. 응답의 전체 건수와 페이지 데이터를 확인합니다.
3. 수집 기준일보다 오래된 데이터가 나타날 때까지 다음 페이지를 계속 요청합니다.
4. 기준일 이상인 데이터만 최종 수집합니다.

향후 수집 기간이 확대되더라도 같은 방식으로 필요한 페이지까지 자동 조회할 수 있습니다.

정기 리포트는 세 날짜 필드별 내림차순 목록을 조회한 뒤 `reportNo`로 병합하여 고유 리포트의 상세를 한 번만 요청합니다. 백필에서는 종료 상한보다 최신인 데이터는 건너뛰고 시작 하한보다 오래된 데이터에서 조회를 중단합니다. API 정렬·응답 구조 변경 시 기간 누락 여부를 점검해야 합니다.

### 3-5. 리포트 문제항목 수집

선택한 수집 기간의 대상 리포트마다 다음 필터를 각각 호출합니다.

- 예상 과태료가 있는 문제항목
- 예상 영업정지가 있는 문제항목

동일한 문제항목이 두 필터에 모두 나타날 수 있으므로 `answerNo`를 기준으로 하나의 문제항목으로 병합합니다. 한 문제항목에 과태료와 영업정지가 모두 있으면 두 값을 모두 저장합니다.

### 3-6. 품질미션 상위 리포트 보완

최근 1개월 품질미션이 이전 기간의 리포트를 참조할 수 있습니다. 이 경우 외래키 관계를 유지하기 위해 해당 과거 리포트 상세를 추가로 조회하여 리포트 테이블에 저장합니다.

이처럼 품질미션 연결을 위해 추가된 과거 리포트는 이번 실행에서 문제항목 전체를 조회한 리포트가 아니므로, 기존 예상 과태료와 예상 영업정지 합계를 0으로 덮어쓰지 않습니다.

신규 보조 리포트는 NOT NULL 제약을 충족하도록 예상 과태료·영업정지 합계를 0으로 저장합니다. 이 0은 전체 문제항목을 조회해 확인한 합계가 아니므로 정확한 값이 필요하면 해당 점검 기간을 백필합니다.

리포트 상세 HTTP 404는 해당 리포트와 연결 문제항목·미션을 제외하고 `reportNo`를 로그에 기록합니다. 그 외 HTTP 오류는 실패 처리합니다. 제외 처리는 기존 DB 행을 삭제하는 기능이 아닙니다.

### 3-7. 브랜드별 매장명 표준화

API에서 매장명이 서로 다른 형식으로 제공되더라도 DB에는 다음 기준으로 통일해 저장합니다.

| 브랜드 | 저장 기준 | 변환 예시 |
|---|---|---|
| 한촌 | 브랜드명과 끝 괄호 표기를 제거하고 지점명만 `점`으로 끝나게 저장 | `한촌설렁탕 부천까치울점` → `부천까치울점` |
| 한촌 | 양수 등 끝 괄호 표기 제거 | `인천삼산점(양수)` → `인천삼산점` |
| 한촌 | `점`이 없으면 추가 | `인천영종도` → `인천영종도점` |
| 육수당 | `육수당 {지점명}` 형식으로 저장 | `안양비즈타워점` → `육수당 안양비즈타워점` |

같은 표준화 규칙을 리포트, 문제항목, 품질미션 세 테이블에 모두 적용합니다.

## 4. DB 반영 방식

### 4-1. 신규·변경·미변경 판정

수집한 데이터는 기존 DB값과 비교하여 다음과 같이 처리합니다.

| 구분 | 처리 방식 |
|---|---|
| 신규 | 동일한 브랜드와 관리번호가 없으면 INSERT |
| 변경 | 기존 행이 있고 수집 대상 값이 달라졌으면 UPDATE |
| 미변경 | 모든 수집 대상 값이 같으면 아무 작업도 하지 않음 |

따라서 같은 데이터를 반복 수집해도 중복 행이 생성되지 않으며, 실제 변경이 없으면 `updated_at`도 변경되지 않습니다.

### 4-2. 저장 순서와 트랜잭션

한 브랜드의 데이터는 다음 순서로 저장합니다.

1. 리포트
2. 리포트 문제항목
3. 품질미션

세 단계는 하나의 DB 트랜잭션으로 처리합니다. 중간 단계에서 오류가 발생하면 해당 브랜드의 이번 저장 작업 전체를 취소하여 일부 데이터만 저장되는 상황을 방지합니다.

월별 백필에서는 월별·브랜드별로 독립 커밋합니다. 재시도 후 최종 실패가 남은 월에서 이후 월 처리를 중단하고 이전 성공 월과 다른 성공 브랜드의 데이터는 유지합니다. 별도 체크포인트 파일 없이 같은 기간을 재실행하면 UPSERT로 신규·변경·동일을 판정합니다. 원천 삭제의 DB 자동 동기화는 구현되어 있지 않습니다.

### 4-3. 수집 이력 일시

| 컬럼 | 의미 |
|---|---|
| `collected_at` | 해당 행이 DB에 최초 등록된 UTC 시각 |
| `updated_at` | 수집 대상 값이 마지막으로 변경된 UTC 시각 |
| `reg_date` | FC다움 API의 리포트 등록 시각(`regDate`, UTC) |
| `source_updated_at` | FC다움 API의 리포트 수정 시각(`updateDate`, UTC) |

기존 행을 업데이트해도 `collected_at`은 변경하지 않습니다. 실제 데이터가 변경된 경우에만 `updated_at`을 갱신합니다.

### 4-4. 날짜 저장 기준

FC다움 API의 Epoch Millisecond 날짜값은 UTC `datetime2`로 변환하여 저장합니다. 한국 시각으로 표시해야 할 때는 조회 SQL에서 9시간을 더할 수 있습니다.

```sql
DATEADD(HOUR, 9, visit_date)
```

## 5. 테이블 관계

```text
fc_daum_qsc_report (리포트 1건)
    ├── fc_daum_qsc_report_issue (문제항목 여러 건)
    └── fc_daum_mission          (품질미션 여러 건)
```

관계 기준은 `brand_code + report_no`입니다.

| 부모 | 자식 | 관계 |
|---|---|---|
| `fc_daum_qsc_report` | `fc_daum_qsc_report_issue` | 1:N |
| `fc_daum_qsc_report` | `fc_daum_mission` | 1:N |

## 6. 테이블 정의서

### 6-1. `dbo.fc_daum_qsc_report`

매장별 리포트 수행 결과를 저장합니다. 한 리포트에 연결된 문제항목의 예상 처분 합계도 함께 저장합니다.

기본키: `brand_code + report_no`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `brand_code` | `VARCHAR(30)` | 불가 | 내부 브랜드 식별 코드 |
| `brand_name` | `NVARCHAR(30)` | 불가 | 한글 브랜드명 |
| `report_no` | `BIGINT` | 불가 | FC다움 리포트 관리번호 |
| `store_name` | `NVARCHAR(300)` | 가능 | 점검 대상 매장명 |
| `visit_date` | `DATETIME2` | 가능 | 매장 점검 시각(UTC) |
| `reg_date` | `DATETIME2(3)` | 가능 | FC다움 리포트 등록 시각(API `regDate`, UTC) |
| `source_updated_at` | `DATETIME2(3)` | 가능 | FC다움 리포트 최종 수정 시각(API `updateDate`, UTC) |
| `grade` | `NVARCHAR(30)` | 가능 | 리포트 평가 등급 |
| `percentage_score` | `DECIMAL(9,2)` | 가능 | 백분율 점수 |
| `inspector_name` | `NVARCHAR(100)` | 가능 | 점검자명 |
| `expected_fine_amount` | `DECIMAL(18,2)` | 불가 | 연결된 문제항목의 예상 과태료 합계 |
| `expected_suspension_days` | `INT` | 불가 | 연결된 문제항목의 예상 영업정지 일수 합계 |
| `collected_at` | `DATETIME2` | 불가 | 최초 수집 시각(UTC) |
| `updated_at` | `DATETIME2` | 불가 | 최종 변경 시각(UTC) |

예상 처분 합계 계산식:

```text
expected_fine_amount
= 동일한 brand_code + report_no의 fine_amount 합계

expected_suspension_days
= 동일한 brand_code + report_no의 suspension_days 합계
```

문제항목이 없으면 두 값 모두 0입니다. 합계는 API에서 수집한 숫자를 그대로 더하며 별도의 금액 단위 변환은 하지 않습니다.

### 6-2. `dbo.fc_daum_qsc_report_issue`

리포트에서 확인된 문제항목을 저장합니다. 하나의 리포트에 여러 문제항목 행이 존재할 수 있습니다.

기본키: `brand_code + answer_no`
외래키: `brand_code + report_no` → `fc_daum_qsc_report`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `brand_code` | `VARCHAR(30)` | 불가 | 내부 브랜드 식별 코드 |
| `brand_name` | `NVARCHAR(30)` | 불가 | 한글 브랜드명 |
| `answer_no` | `BIGINT` | 불가 | FC다움 문제항목 관리번호 |
| `report_no` | `BIGINT` | 불가 | 상위 리포트 관리번호 |
| `store_name` | `NVARCHAR(300)` | 가능 | 점검 대상 매장명 |
| `visit_date` | `DATETIME2` | 가능 | 리포트 점검 시각(UTC) |
| `top_category_name` | `NVARCHAR(300)` | 가능 | 상위 카테고리명 |
| `category_name` | `NVARCHAR(300)` | 가능 | 하위 카테고리명 |
| `question_title` | `NVARCHAR(1000)` | 가능 | 점검항목 질문 |
| `checked_value` | `NVARCHAR(100)` | 가능 | API의 점검 결과값 |
| `fine_amount` | `DECIMAL(18,2)` | 가능 | 해당 문제항목의 예상 과태료 |
| `suspension_days` | `INT` | 가능 | 해당 문제항목의 예상 영업정지 일수 |
| `collected_at` | `DATETIME2` | 불가 | 최초 수집 시각(UTC) |
| `updated_at` | `DATETIME2` | 불가 | 최종 변경 시각(UTC) |

### 6-3. `dbo.fc_daum_mission`

매장에 전달된 품질개선 미션을 저장합니다. 하나의 리포트에서 여러 품질미션이 만들어질 수 있습니다.

기본키: `brand_code + mission_no`
외래키: `brand_code + report_no` → `fc_daum_qsc_report`

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---:|---|
| `brand_code` | `VARCHAR(30)` | 불가 | 내부 브랜드 식별 코드 |
| `brand_name` | `NVARCHAR(30)` | 불가 | 한글 브랜드명 |
| `mission_no` | `BIGINT` | 불가 | FC다움 품질미션 관리번호 |
| `report_no` | `BIGINT` | 불가 | 상위 리포트 관리번호 |
| `store_name` | `NVARCHAR(300)` | 가능 | 미션 수행 대상 매장명 |
| `sent_date` | `DATETIME2` | 가능 | 미션 전송 시각(API `startDate`, UTC) |
| `due_date` | `DATETIME2` | 가능 | 미션 마감 시각(API `endDate`, UTC) |
| `mission_status` | `NVARCHAR(30)` | 가능 | 한글로 변환한 현재 미션 상태 |
| `title` | `NVARCHAR(MAX)` | 가능 | API의 미션 제목 |
| `description` | `NVARCHAR(MAX)` | 가능 | API의 미션 설명 |
| `sv_name` | `NVARCHAR(100)` | 가능 | 미션을 전송한 SV 이름(API `startUserNm`) |
| `owner_submitted_at` | `DATETIME2` | 가능 | 점주가 수행 결과를 제출한 시각(API `actionDate`, UTC) |
| `sv_completed_at` | `DATETIME2` | 가능 | SV가 최종 완료 처리한 시각(API `completeDate`, UTC) |
| `collected_at` | `DATETIME2` | 불가 | 최초 수집 시각(UTC) |
| `updated_at` | `DATETIME2` | 불가 | 최종 변경 시각(UTC) |

미션 상태 변환 기준:

| API 상태 | DB 저장값 |
|---|---|
| `DOING` | 수행 전 |
| `ACTION` | 제출 완료 |
| `COMPLETE` | 완료됨 |
| `REDOING` | 재수행 요청 |

정의되지 않은 상태가 추가되면 데이터 유실을 막기 위해 API 원본값을 그대로 저장합니다.

### 6-4. `dbo.FC_DAUM_COLLECTION_RUN`

실행 단위 감사 이력입니다. 기본키는 `RunId`이며 월별 백필은 각 월의 브랜드 처리마다 별도 실행 이력을 생성합니다.

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---|---|
| `RunId` | `UNIQUEIDENTIFIER` | 불가 | 실행 식별자 |
| `ScheduledDate` | `DATE` | 불가 | 실행 기준일(KST), 백필 대상 월이나 스케줄러 예정일을 뜻하지 않음 |
| `StartedAt` | `DATETIME2(3)` | 불가 | 실제 시작 시각(UTC) |
| `FinishedAt` | `DATETIME2(3)` | 가능 | 종료 시각(UTC) |
| `RunStatus` | `VARCHAR(20)` | 불가 | 실행 상태 |
| `SuccessfulBrands` | `INT` | 불가 | 최종 성공 브랜드 수, 기본값 0 |
| `FailedBrands` | `INT` | 불가 | 최종 실패 브랜드 수, 기본값 0 |

| 상태 | 의미 |
|---|---|
| `RUNNING` | 실행 시작 기록, 아직 종료 기록 없음 |
| `SUCCESS` | 전체 브랜드 성공, 수집 데이터 있음 |
| `SUCCESS_EMPTY` | 전체 브랜드 성공, 수집 건수 합계 0 |
| `WARNING` | 실패 브랜드 재시도 후 전체 성공 |
| `PARTIAL_FAILED` | 일부 브랜드 성공·일부 실패 |
| `FAILED` | 전체 실패 또는 기록 가능한 초기화 실패 |
| `ABORTED` | 브랜드 시도 감사 기록 누락을 감지한 경우 등 |
| `NOT_RUN` | SQL 제약에서 허용하는 값. 현재 수집기가 미실행 일자의 행을 자동 생성하지는 않음 |

재시도가 있었다면 데이터가 0건이어도 `WARNING`이 우선합니다. 프로세스 강제 종료·감사 종료 기록 실패 시 `RUNNING`이 남을 수 있으므로 이 상태만으로 실제 실행 중이라고 단정하지 않습니다.

### 6-5. `dbo.FC_DAUM_COLLECTION_ATTEMPT`

기본키는 `RunId + BrandCode + AttemptNo`, 외래키는 `RunId` → `FC_DAUM_COLLECTION_RUN.RunId`입니다.

| 컬럼 | 형식 | NULL | 설명 |
|---|---|---|---|
| `RunId` | `UNIQUEIDENTIFIER` | 불가 | 부모 실행 식별자 |
| `BrandCode` | `VARCHAR(50)` | 불가 | `hanchon`, `yuksudang` |
| `BrandName` | `NVARCHAR(100)` | 불가 | 실행용 브랜드명(한촌설렁탕, 육수당) |
| `AttemptNo` | `INT` | 불가 | 브랜드 시도 번호: 최초 1, 재시도 2 |
| `StartedAt` | `DATETIME2(3)` | 불가 | 시도 시작 시각(UTC) |
| `FinishedAt` | `DATETIME2(3)` | 불가 | 시도 종료 시각(UTC) |
| `AttemptStatus` | `VARCHAR(20)` | 불가 | `SUCCESS`, `SUCCESS_EMPTY`, `FAILED` |
| `ApiCount` | `INT` | 불가 | 수집 결과의 리포트·문제항목·미션 건수 합계 |
| `ReportInsertedCount` | `INT` | 불가 | 리포트 신규 건수 |
| `ReportChangedCount` | `INT` | 불가 | 리포트 변경 건수 |
| `ReportUnchangedCount` | `INT` | 불가 | 리포트 동일 건수 |
| `IssueInsertedCount` | `INT` | 불가 | 문제항목 신규 건수 |
| `IssueChangedCount` | `INT` | 불가 | 문제항목 변경 건수 |
| `IssueUnchangedCount` | `INT` | 불가 | 문제항목 동일 건수 |
| `MissionInsertedCount` | `INT` | 불가 | 미션 신규 건수 |
| `MissionChangedCount` | `INT` | 불가 | 미션 변경 건수 |
| `MissionUnchangedCount` | `INT` | 불가 | 미션 동일 건수 |
| `DbCommitted` | `BIT` | 불가 | 업무 커밋 여부: 성공 1, 실패 0 |
| `ErrorCategory` | `VARCHAR(64)` | 가능 | 성공 시 NULL, 실패 시 정규화된 오류 분류 |

오류 분류는 `API_ERROR`, `DATABASE_ERROR`, `INITIALIZATION_ERROR`, `INVALID_DATA`, `UNEXPECTED_ERROR`입니다. 초기화 실패는 시도 없이 실행 이력만 남을 수 있고 DB 설정·감사 연결 자체가 실패하면 이력이 없을 수 있습니다.

`ApiCount`는 HTTP 호출 횟수가 아닙니다. 수집 결과를 확보하기 전에 실패하면 0일 수 있으며 실패 시 적재 건수도 0으로 기록하므로 API 요청 유무와 혼동하지 않습니다. 재시도를 모두 합산하면 같은 데이터를 중복 집계할 수 있습니다.

감사는 업무 DB와 별도 연결·트랜잭션으로 기록합니다. 감사 기록 실패가 이미 커밋한 업무 데이터를 되돌리거나 기존 종료 코드를 변경하지는 않습니다. 감사 테이블에는 인증정보·응답 본문·원문 예외를 저장하지 않습니다.

정의 SQL은 `sql/080_create_collection_audit_tables.sql`입니다. 실행 시작 시각, 실행 상태·시작 시각, 시도별 실행 ID·종료 시각에 조회용 인덱스를 생성합니다. `sql/085_verify_collection_audit_tables.sql`로 테이블·컬럼·PK·인덱스·최근 이력을 읽기 전용으로 확인할 수 있습니다.

## 7. View 정의서

### 7-1. `dbo.vw_fc_daum_mission`

품질미션 테이블의 저장값과 조회 시점의 마감 상태를 함께 제공합니다.

View는 한 번 생성하면 삭제하거나 변경하기 전까지 계속 사용할 수 있습니다. 별도 데이터를 저장하지 않으며 조회할 때마다 원본 테이블과 현재 UTC 시각을 기준으로 결과를 계산합니다.

| 컬럼 | 설명 |
|---|---|
| `brand_code` | 내부 브랜드 식별 코드 |
| `brand_name` | 한글 브랜드명 |
| `mission_no` | 품질미션 관리번호 |
| `report_no` | 상위 리포트 관리번호 |
| `store_name` | 대상 매장명 |
| `sent_date` | 미션 전송 시각(UTC) |
| `due_date` | 미션 마감 시각(UTC) |
| `mission_status` | DB에 저장된 현재 미션 상태 |
| `display_status` | 조회 시점의 마감 여부를 반영한 표시 상태 |
| `title` | 미션 제목 |
| `description` | 미션 설명 |
| `sv_name` | 미션 전송 SV |
| `owner_submitted_at` | 점주 제출 시각(UTC) |
| `sv_completed_at` | SV 완료 처리 시각(UTC) |
| `collected_at` | 최초 수집 시각(UTC) |
| `updated_at` | 최종 변경 시각(UTC) |

`display_status` 계산 기준:

```sql
CASE
    WHEN owner_submitted_at IS NULL
     AND due_date < SYSUTCDATETIME()
        THEN N'마감됨'
    ELSE mission_status
END
```

즉, 점주가 제출하지 않았고 현재 시각이 마감 시각을 지난 경우에만 `마감됨`으로 표시합니다. 제출된 미션은 마감일이 지났더라도 저장된 미션 상태를 표시합니다.

## 8. 업무 목적별 조회 SQL

### 8-1. 최근 리포트 조회

```sql
SELECT
    brand_name,
    report_no,
    store_name,
    DATEADD(HOUR, 9, visit_date) AS visit_date_kst,
    grade,
    percentage_score,
    inspector_name,
    expected_fine_amount,
    expected_suspension_days
FROM dbo.fc_daum_qsc_report
ORDER BY visit_date DESC;
```

### 8-2. 특정 브랜드 리포트 조회

```sql
SELECT
    brand_name,
    report_no,
    store_name,
    DATEADD(HOUR, 9, visit_date) AS visit_date_kst,
    grade,
    percentage_score,
    expected_fine_amount,
    expected_suspension_days
FROM dbo.fc_daum_qsc_report
WHERE brand_code = 'hanchon'
ORDER BY visit_date DESC;
```

육수당은 `brand_code = 'yuksudang'`으로 변경합니다.

### 8-3. 예상 처분이 있는 리포트 조회

```sql
SELECT
    brand_name,
    report_no,
    store_name,
    DATEADD(HOUR, 9, visit_date) AS visit_date_kst,
    expected_fine_amount,
    expected_suspension_days
FROM dbo.fc_daum_qsc_report
WHERE expected_fine_amount > 0
   OR expected_suspension_days > 0
ORDER BY visit_date DESC;
```

### 8-4. 리포트별 문제항목 상세 조회

```sql
DECLARE @brand_code VARCHAR(30) = 'hanchon';
DECLARE @report_no BIGINT = 789570;

SELECT
    brand_name,
    report_no,
    answer_no,
    store_name,
    top_category_name,
    category_name,
    question_title,
    checked_value,
    fine_amount,
    suspension_days
FROM dbo.fc_daum_qsc_report_issue
WHERE brand_code = @brand_code
  AND report_no = @report_no
ORDER BY answer_no;
```

### 8-5. 리포트와 문제항목 함께 조회

리포트 1건에 문제항목이 여러 건이면 리포트 정보가 문제항목 수만큼 반복되어 표시됩니다.

```sql
SELECT
    r.brand_name,
    r.report_no,
    r.store_name,
    DATEADD(HOUR, 9, r.visit_date) AS visit_date_kst,
    r.grade,
    r.percentage_score,
    r.expected_fine_amount,
    r.expected_suspension_days,
    i.answer_no,
    i.top_category_name,
    i.category_name,
    i.question_title,
    i.checked_value,
    i.fine_amount,
    i.suspension_days
FROM dbo.fc_daum_qsc_report AS r
LEFT JOIN dbo.fc_daum_qsc_report_issue AS i
  ON i.brand_code = r.brand_code
 AND i.report_no = r.report_no
ORDER BY r.visit_date DESC, i.answer_no;
```

### 8-6. 전체 품질미션 조회

마감 여부가 반영된 `display_status`를 사용하기 위해 테이블이 아닌 View를 조회합니다.

```sql
SELECT
    brand_name,
    mission_no,
    report_no,
    store_name,
    DATEADD(HOUR, 9, sent_date) AS sent_date_kst,
    DATEADD(HOUR, 9, due_date) AS due_date_kst,
    mission_status,
    display_status,
    title,
    description,
    sv_name,
    DATEADD(HOUR, 9, owner_submitted_at) AS owner_submitted_at_kst,
    DATEADD(HOUR, 9, sv_completed_at) AS sv_completed_at_kst
FROM dbo.vw_fc_daum_mission
ORDER BY due_date DESC;
```

### 8-7. 마감됐지만 점주가 제출하지 않은 미션 조회

```sql
SELECT
    brand_name,
    mission_no,
    report_no,
    store_name,
    DATEADD(HOUR, 9, due_date) AS due_date_kst,
    display_status,
    title,
    sv_name
FROM dbo.vw_fc_daum_mission
WHERE display_status = N'마감됨'
ORDER BY due_date DESC;
```

### 8-8. 현재 상태별 품질미션 조회

```sql
DECLARE @mission_status NVARCHAR(30) = N'재수행 요청';

SELECT
    brand_name,
    mission_no,
    report_no,
    store_name,
    mission_status,
    display_status,
    DATEADD(HOUR, 9, due_date) AS due_date_kst,
    title
FROM dbo.vw_fc_daum_mission
WHERE mission_status = @mission_status
ORDER BY due_date DESC;
```

`@mission_status`에는 `수행 전`, `제출 완료`, `완료됨`, `재수행 요청`을 사용할 수 있습니다.

### 8-9. 특정 기간에 최초 수집되거나 변경된 데이터 조회

최근 7일 이내 최초 등록 또는 변경된 리포트:

```sql
SELECT *
FROM dbo.fc_daum_qsc_report
WHERE collected_at >= DATEADD(DAY, -7, SYSUTCDATETIME())
   OR updated_at >= DATEADD(DAY, -7, SYSUTCDATETIME())
ORDER BY updated_at DESC;
```

### 8-10. 브랜드별 데이터 건수 조회

```sql
SELECT
    brand_name,
    COUNT(*) AS report_count
FROM dbo.fc_daum_qsc_report
GROUP BY brand_name
ORDER BY brand_name;

SELECT
    brand_name,
    COUNT(*) AS issue_count
FROM dbo.fc_daum_qsc_report_issue
GROUP BY brand_name
ORDER BY brand_name;

SELECT
    brand_name,
    COUNT(*) AS mission_count
FROM dbo.fc_daum_mission
GROUP BY brand_name
ORDER BY brand_name;
```

### 8-11. 최근 실행 및 브랜드별 시도 조회

```sql
SELECT TOP (20)
    RunId, ScheduledDate,
    DATEADD(HOUR, 9, StartedAt) AS started_at_kst,
    DATEADD(HOUR, 9, FinishedAt) AS finished_at_kst,
    RunStatus, SuccessfulBrands, FailedBrands
FROM dbo.FC_DAUM_COLLECTION_RUN
ORDER BY StartedAt DESC, RunId;

-- 가장 최근 실행의 시도 이력: 최초 시도와 재시도를 모두 표시
SELECT a.*
FROM dbo.FC_DAUM_COLLECTION_ATTEMPT AS a
WHERE a.RunId = (
    SELECT TOP (1) RunId
    FROM dbo.FC_DAUM_COLLECTION_RUN
    ORDER BY StartedAt DESC, RunId
)
ORDER BY a.BrandCode, a.AttemptNo;
```

감사 행이 없거나 성공으로 기록돼도 업무 로그의 404 제외 번호와 실제 적재 결과를 함께 확인합니다. 월별 백필의 대상 기간은 감사 테이블에 별도 컬럼으로 저장되지 않으므로 일별 로그와 대조합니다.

### 8-12. 점검일보다 뒤늦게 등록된 리포트 확인

```sql
SELECT brand_code, report_no, store_name,
    DATEADD(HOUR, 9, visit_date) AS visit_date_kst,
    DATEADD(HOUR, 9, reg_date) AS reg_date_kst,
    DATEADD(HOUR, 9, source_updated_at) AS source_updated_at_kst,
    DATEADD(HOUR, 9, updated_at) AS db_updated_at_kst
FROM dbo.fc_daum_qsc_report
WHERE reg_date > DATEADD(MONTH, 1, visit_date)
ORDER BY reg_date DESC;
```

이 SQL은 DB에 적재된 지연 등록 사례를 찾는 용도입니다. DB에 아예 없는 리포트는 동일 브랜드·기간·필터의 원천 API 관리번호와 대조해야 찾을 수 있습니다.

## 9. 운영 방식

실행 시 브랜드별로 다음 결과를 출력합니다.

- 수집한 리포트 건수
- 수집한 문제항목 건수
- 수집한 품질미션 건수
- 테이블별 신규 등록 건수
- 테이블별 변경 업데이트 건수
- 테이블별 미변경 건수
- 실패 브랜드와 재시도 결과

일별 로그는 실행 작업 디렉터리의 `logs\fcdaum_YYYY-MM-DD.log`에 생성되며 같은 날에는 이어쓰기합니다. 스케줄러 시작 위치를 프로젝트 폴더로 지정합니다. 종료 코드 `0`은 전체 성공, `1`은 재시도 후 최종 실패, `2`는 처리된 설정·날짜 오류입니다. 처리되지 않은 예외는 비정상 종료 로그를 확인합니다. 상세 404 제외는 전체 성공과 함께 발생할 수 있습니다.

연결·업무 테이블 확인은 `db_check.py`, 브랜드별 건수·최대 수집·변경 시각 확인은 `db_stats.py`, 감사 구조·최근 이력 확인은 `sql/085_verify_collection_audit_tables.sql`을 사용합니다. 설치·실행 명령은 [README](README.md)를 참고합니다.


## 10. 구현 및 검증 현황

다음은 과거 업무 보고에 기록된 검증 결과입니다.

| 보고일 | 주요 결과 | 당시 자동화 테스트 |
|---|---|---|
| 2026-07-22 | 두 브랜드 수집·적재, 중복 방지, 상태·View·예상 처분 합계 검증 | 58건 통과 |
| 2026-08-12 | 보조 리포트 NOT NULL 오류 수정 및 서버 재실행 성공 | 78건 통과 |
| 2026-08-13 | 월별 백필, 일별 상세 로그, 상세 404 제외 구현 | 97건 통과 |
| 2026-08-27 | 누락 리포트 3건 복구, 세 날짜 기준 정기 수집·원천 날짜 컬럼 적용 | 105건 통과 |

현재 코드에는 실행·시도 감사 이력 기능도 포함됩니다. 테스트는 프로젝트 폴더에서 `.\.venv\Scripts\python.exe -m pytest -v`로 실행합니다.



운영 인계·장애 사례·미해결 과제는 [최종 인수인계서](FC다움_API_호출_수집기_인수인계서.md)를 참고합니다.
