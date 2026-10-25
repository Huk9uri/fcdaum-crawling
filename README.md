# FC다움 API 호출 수집기

문서 갱신일: 2026-09-14. 

한촌설렁탕과 육수당 계정으로 각각 로그인하여 실행 시각 기준 최근 1개월의 리포트, 문제항목, 품질미션을 전체 페이지에서 수집하고 MSSQL에 신규, 변경 데이터만 적재하는 프로그램입니다.

## 1. Python 및 라이브러리 설치

Windows에 Python 3.12 64비트를 설치하고 프로젝트 폴더에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. 환경변수 입력

프로젝트 루트의 `.env` 파일에 두 브랜드 계정을 입력합니다.

```dotenv
HANCHON_USER_ID=한촌계정아이디
HANCHON_PASSWORD=한촌계정비밀번호
YUKSUDANG_USER_ID=육수당계정아이디
YUKSUDANG_PASSWORD=육수당계정비밀번호
```

MSSQL 설정도 같은 `.env`에 입력합니다.

```dotenv
MSSQL_SERVER=서버주소
MSSQL_PORT=1433
MSSQL_DATABASE=naverDB
MSSQL_USER=적재계정
MSSQL_PASSWORD=DB비밀번호
MSSQL_SCHEMA=dbo
MSSQL_DRIVER=ODBC Driver 17 for SQL Server
```

### 감사 이력 SQL 적용 및 확인

모니터링 플랫폼이 FC다움 실행 상태를 읽으려면 업무 테이블과 같은 DB에 감사
테이블을 한 번 생성해야 합니다. 적용 전 대상 DB와 스키마가 `dbo`인지 확인한
후 다음 순서로 진행합니다.

1. 기존 업무 테이블과 필요한 컬럼 변경 SQL을 먼저 적용합니다.
2. `sql/080_create_collection_audit_tables.sql`을 적용해
   `dbo.FC_DAUM_COLLECTION_RUN`과
   `dbo.FC_DAUM_COLLECTION_ATTEMPT`를 생성합니다.
3. `sql/085_verify_collection_audit_tables.sql`을 실행해 테이블, 컬럼, 인덱스와
   최근 감사 이력을 확인합니다.

업무 테이블은 `fc_daum_qsc_report`, `fc_daum_qsc_report_issue`, `fc_daum_mission`입니다. 기존 스키마와 `sql/add_brand_name.sql`, `sql/add_report_expected_sanctions.sql`, `sql/add_report_source_dates.sql` 적용 여부를 대조하고, 미션 조회 View는 `sql/fc_daum_mission_view.sql`을 확인합니다. 감사 테이블 생성 SQL만으로 업무 테이블이 생성되지는 않습니다. 

`085_verify_collection_audit_tables.sql`은 `SELECT`만 사용하는 읽기 전용 확인
쿼리입니다. 실행 결과에서 두 감사 테이블과 각 PK·인덱스가 조회되는지,
컬럼명이 모니터링 API 계약과 일치하는지 확인합니다. 실제 수집을 실행하거나
업무·감사 데이터를 변경하지 않습니다.

감사 이력은 업무 적재와 별도 DB 연결 및 트랜잭션으로 기록됩니다. 브랜드 업무
트랜잭션이 커밋된 뒤 성공 시도를 기록하고, 업무 rollback 시에는
`DbCommitted=0`인 실패 시도를 기록합니다. 감사 DB 기록이 실패해도 이미
커밋된 업무 데이터는 되돌리지 않으며 수집기의 기존 출력과 종료코드는
유지됩니다. 

## 3. 수집 범위

- 실행 시각은 한국 시간 UTC+9를 사용합니다.
- 실행 시각에서 달력 기준 1개월 전을 뺀 시각부터 수집합니다.
- 정기 수집 리포트는 `visitDate`, `regDate`, `updateDate` 중 하나라도 최근 1개월이면 수집합니다.
- 명시적 시작일 및 월별 백필 리포트는 지정 기간의 `visitDate`를 기준으로 수집합니다.
- 품질미션은 `regDate` Epoch 밀리초 값을 기준으로 판정합니다.
- 최신순으로 페이지 번호를 증가시키며 기간 경계를 만날 때까지 전부 조회합니다.
- 기간 내 모든 리포트의 상세, 과태료 문제항목, 영업정지 문제항목을 조회합니다.
- 여러 날짜 기준에 중복된 리포트는 `reportNo`로 병합해 상세 API를 한 번만 조회합니다.
- 리포트의 API 등록·수정 시각은 각각 `reg_date`, `source_updated_at`으로 저장합니다.
- 문제항목은 `answerNo` 기준으로 병합해 중복을 제거합니다.
- 상위 리포트를 문제항목과 품질미션보다 먼저 적재합니다.
- 품질미션이 기간 밖 리포트를 참조하면 부모 리포트를 상세 API로 보완합니다.
- 신규 행은 `collected_at`, `updated_at`이 자동 설정됩니다.
- 기존 업무 값이 실제로 달라질 때만 `updated_at`이 변경됩니다.

리포트 상세가 HTTP 404이면 해당 리포트와 연결 문제항목·품질미션을 제외하고 번호를 로그에 남깁니다. 404 이외의 오류는 실패 처리합니다. 과거 상위 리포트를 보조 수집할 때 신규 행의 예상 처분 과태료의 합계는 0으로 저장하고 기존 행의 합계는 유지합니다. 보조 리포트의 0은 문제항목 전체를 조회한 결과가 아닐 수 있습니다.

한 브랜드가 실패하면 다른 브랜드를 먼저 처리한 뒤 실패 브랜드만 새 로그인 세션으로 한 번 재시도합니다. 재시도 후에도 실패하면 종료코드 1을 반환합니다.

### 월별 기간 분할 백필

과거 데이터를 월별로 나눠 수집하려면 시작일과 종료일을 함께 지정합니다.

```powershell
.\.venv\Scripts\python.exe crawling.py `
  --backfill-from 2024-01-01 `
  --backfill-to 2025-12-31
```

- 입력 날짜는 KST 기준이며 시작일과 종료일을 모두 포함합니다.
- 최초·최종 월이 월 중간 날짜이면 입력한 날짜까지만 처리합니다.
- 오래된 월부터 순서대로 처리합니다.
- DB는 월별·브랜드별로 독립 커밋됩니다.
- 최종 실패 브랜드가 발생한 월에서 이후 월 처리를 중단합니다.
- 완료된 이전 월의 데이터는 유지됩니다.
- 별도 체크포인트 파일은 사용하지 않습니다.
- 실패 후 같은 명령을 다시 실행해도 UPSERT가 기존 데이터를 신규·변경·미변경으로 판정하므로 중복 행이 생성되지 않습니다.
- `--backfill-from`과 `--backfill-to`는 반드시 함께 사용해야 하며 기존 `--from-date`와 동시에 사용할 수 없습니다.

일반 정기 실행은 기존과 같이 최근 1개월을 수집합니다. 시작일만 지정하는 기존 일회성 수집도 그대로 사용할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe crawling.py --from-date 2026-01-01
```

## 4. 자동 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## 5. 실제 수집 검증

먼저 DB 연결과 대상 테이블을 확인합니다.

```powershell
.\.venv\Scripts\python.exe db_check.py
```

수집 및 적재를 실행합니다.

```powershell
.\.venv\Scripts\python.exe crawling.py
```

출력 예시:

```text
[한촌설렁탕] 리포트 120건, 문제항목 15건, 품질미션 45건 (성공)
[한촌설렁탕] DB 반영: 리포트 신규 120/변경 0/동일 0, 문제항목 신규 15/변경 0/동일 0, 품질미션 신규 45/변경 0/동일 0
[육수당] 리포트 80건, 문제항목 9건, 품질미션 32건 (성공)
[육수당] DB 반영: 리포트 신규 80/변경 0/동일 0, 문제항목 신규 9/변경 0/동일 0, 품질미션 신규 32/변경 0/동일 0
[완료] 모든 브랜드의 최근 1개월 수집 검증이 성공했습니다.
```

실제 건수는 실행일과 계정별 데이터에 따라 달라집니다.

브랜드별 DB 건수와 최대 수집·변경 시각은 다음 명령으로 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe db_stats.py
```

| 종료 코드 | 의미 | 확인 사항 |
|---|---|---|
| `0` | 모든 브랜드 성공 | 404 제외 목록과 감사 이력도 확인 |
| `1` | 재시도 후 최종 실패 | 실패 브랜드의 API·DB 오류 확인 후 재실행 |
| `2` | 처리된 설정·날짜 입력 오류 | 환경변수와 실행 인수 확인 |

처리되지 않은 예외는 별도 비정상 종료로 기록되므로 로그의 예외 유형·메시지를 확인합니다. 브랜드별 DB 저장 실패는 해당 트랜잭션을 롤백하며 이미 성공한 다른 브랜드는 유지됩니다.

재시도 후 성공은 감사 상태 `WARNING`이면서 종료 코드 `0`일 수 있습니다. 감사 DB 장애는 업무 성공 여부와 종료 코드를 변경하지 않으므로, 로그·업무 DB·감사 이력을 함께 대조합니다. 월별 백필은 월마다 별도 실행 이력이 생성됩니다.

## 7. 문서와 검증 이력

- DB 컬럼·조회 SQL: [FC다움 API 수집 DB 정의서 및 조회 가이드](FC다움_API_수집_DB_정의서_및_조회가이드.md)
- 운영·장애·인계 체크리스트: [FC다움 API 호출 수집기 인수인계서](FC다움_API_호출_수집기_인수인계서.md)
- 설계·구현 자료: `docs/superpowers/specs/`, `docs/superpowers/plans/`
