# F&B QSC API 진단 프로그램 설계

## 목표

Windows에서 사용자가 `.env`에 한촌설렁탕·육수당 및 MSSQL 계정을 입력한 뒤 명령 하나로 각 브랜드의 실행일 기준 최근 1개월 리포트, 문제항목, 품질미션을 수집하고 `naverDB.dbo`의 세 테이블에 신규·변경 데이터만 적재한다.

## 범위

- Python 3.12 및 가상환경 사용 방법 제공
- 환경변수에서 한촌설렁탕·육수당 로그인 정보 로드 및 필수값 검증
- 로그인 API 호출과 응답 권한 검증
- 로그인 응답 쿠키를 동일한 HTTP 세션에서 자동 유지
- 로그인 응답의 `userNo`를 `X-Logged-In-User-No` 헤더에 설정
- 리포트 목록을 최신순으로 페이지 순회하여 최근 1개월 전체 조회
- 첫 리포트의 상세정보 조회
- 기간 내 리포트들의 과태료·영업정지 문제항목 조회
- 품질미션 목록을 최신순으로 페이지 순회하여 최근 1개월 전체 조회
- 상태코드, 조회 건수, 비민감 식별번호만 콘솔에 표시
- Cloudflare challenge 응답을 별도로 감지해 안내
- 브랜드마다 독립적인 HTTP 세션을 사용해 인증 쿠키 격리
- 1차 실행에서 실패한 브랜드가 있어도 나머지 브랜드 계속 실행
- 1차 실패 브랜드만 로그인부터 전체 진단을 한 번 일괄 재시도
- 재시도 후에도 실패한 브랜드를 마지막에 요약하고 비정상 종료
- 단위 테스트와 실행 안내 제공

## 제외 범위

- MSSQL 테이블 생성(DDL은 사용자가 별도로 실행)
- 전체 페이지 수집
- Windows 작업 스케줄러 등록
- 쿠키 및 토큰의 파일 저장
- Playwright 기반 브라우저 자동화

## MSSQL 적재

`pyodbc`로 `naverDB`에 연결하며 대상 테이블은 `dbo.fc_daum_qsc_report`, `dbo.fc_daum_qsc_report_issue`, `dbo.fc_daum_mission`이다. 브랜드별로 독립 트랜잭션을 열고 부모 리포트, 문제항목, 품질미션 순서로 적재한다.

각 배치의 관리번호를 묶어서 기존 행을 조회하고 Python에서 수집 대상 컬럼을 NULL 안전하게 비교한다. 키가 없으면 INSERT하고, 키가 있으며 값이 다르면 UPDATE하고, 모든 값이 같으면 SQL을 실행하지 않는다. INSERT 시 `collected_at`과 `updated_at`은 테이블 기본값 `SYSUTCDATETIME()`을 사용한다. UPDATE 시 `collected_at`은 유지하고 실제 값이 다른 경우에만 `updated_at = SYSUTCDATETIME()`을 실행한다.

기본키 및 관계는 다음과 같다.

- 리포트 PK: `(brand_code, report_no)`
- 문제항목 PK: `(brand_code, answer_no)`, 리포트 FK: `(brand_code, report_no)`
- 품질미션 PK: `(brand_code, mission_no)`, 리포트 FK: `(brand_code, report_no)`

품질미션이 최근 1개월 밖의 리포트를 참조하고 DB에 부모가 없으면 해당 `report_no` 상세 API를 추가 조회하여 부모 리포트를 먼저 보조 적재한다. DB 적재 중 오류가 발생하면 해당 브랜드 트랜잭션 전체를 롤백한다. 다른 브랜드는 계속 처리하고 실패 브랜드는 새 API 세션과 새 DB 트랜잭션으로 한 번 재시도한다.

API Epoch 밀리초는 UTC 기준 `datetime2(3)` 값으로 변환한다. JSON의 누락 필드는 SQL NULL로 저장한다. 과태료와 영업정지는 문제항목별 `fine_amount`, `suspension_days`로 저장하며 합산하지 않는다.

필수 DB 환경변수는 `MSSQL_SERVER`, `MSSQL_PORT`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD`, `MSSQL_SCHEMA`, `MSSQL_DRIVER`이다. 비밀번호를 연결 오류나 로그에 포함하지 않는다.

## 접근 방식

초기 구현은 `requests.Session`을 사용한다. 로그인 응답의 `Set-Cookie`를 세션이 자동 보관하므로 `AWSALB`, `AWSALBCORS`, `access_token_production`, `refresh_token_production` 값을 직접 읽거나 출력하지 않는다. 일반 HTTP 클라이언트가 Cloudflare에 차단되는 경우에는 이번 진단 결과를 근거로 후속 단계에서 Playwright 방식으로 전환한다.

## 구성요소

- `.env.example`: 두 브랜드 계정을 채울 환경변수 템플릿
- `.env`: 실제 계정정보 파일이며 버전 관리에서 제외
- `config.py`: 설정 로드와 필수값 검증
- `fnb_client.py`: 인증, 공통 요청 처리, 각 API 메서드
- `crawling.py`: 진단 흐름 실행 및 안전한 결과 출력
- `tests/`: 환경설정, 인증, 요청 파라미터, 오류 처리 테스트
- `requirements.txt`: 실행 및 테스트 의존성
- `README.md`: Python 설치, 가상환경, 설정, 실행 방법

## 데이터 흐름

1. `.env`에서 `HANCHON_USER_ID`, `HANCHON_PASSWORD`, `YUKSUDANG_USER_ID`, `YUKSUDANG_PASSWORD`를 읽는다.
2. 누락된 값이 있으면 네트워크 요청 전에 종료한다.
3. 한촌설렁탕 전용 세션에서 로그인부터 전체 API 진단을 실행한다.
4. 성공·실패 여부를 기록하고 육수당 전용 세션에서 같은 진단을 실행한다.
5. 1차 실패 브랜드가 있으면 해당 브랜드만 새 세션으로 로그인부터 한 번 재시도한다.
6. 모든 브랜드가 성공하면 정상 종료한다.
7. 재시도 후 실패 브랜드가 남으면 브랜드명과 비민감 오류만 요약하고 비정상 종료한다.

브랜드별 전체 API 진단은 로그인 응답의 `userNo`와 `qsc-report`, `qsc-mission` 권한을 확인하고, 세션에 `X-Logged-In-User-No`를 설정한 뒤 리포트 목록, 기간 내 리포트 상세와 과태료·영업정지 문제항목, 품질미션 목록을 순서대로 호출한다.

수집 시작 기준은 실행 시각에서 달력 기준 1개월을 뺀 시각이다. 예를 들어 7월 21일 실행이면 6월 21일부터 수집하며, 말일이 존재하지 않는 달은 해당 달의 마지막 날을 사용한다. 리포트는 `visitDate`, 품질미션은 `regDate`를 기간 판정 필드로 사용한다.

리포트는 `visitDate DESC`, 품질미션은 `regDate DESC, missionNo DESC` 정렬을 유지하고 `currentPage`를 증가시키며 모든 페이지를 순회한다. 각 페이지에서 기준 시각 이상인 항목만 결과에 포함한다. 기준 시각보다 오래된 항목을 만나는 페이지까지 처리한 뒤 다음 페이지 요청을 중단한다. 전체 건수가 0이거나 서버가 빈 페이지를 반환해도 안전하게 종료한다.

## API 요청

- 로그인: `POST /api/v2/bff/logged-in-user`
- 리포트 목록: `GET /api/v2/bff/fnb-qsc-report-info`
- 리포트 상세: `GET /api/v2/bff/fnb-qsc-report-info/{reportNo}`
- 문제항목: `GET /api/v2/bff/fnb-qsc-report-answer`
- 품질미션: `GET /api/v2/bff/fnb-mission-info`

목록 요청은 특정 페이지나 10건으로 제한하지 않는다. 설정된 페이지 크기로 `currentPage`를 증가시키며 최근 1개월 범위가 끝날 때까지 조회한다. 리포트 문제항목은 기간 내 각 `reportNo`로 과태료 및 영업정지 필터를 각각 조회하고, 같은 `answerNo`는 하나의 문제항목으로 병합한다.

## 오류 처리와 보안

- 비밀번호, 요청 Cookie, `Set-Cookie`, access/refresh token은 로그에 남기지 않는다.
- 로그인 실패는 HTTP 상태와 서버의 비민감 오류 메시지만 표시한다.
- `403`이며 `Cf-Mitigated: challenge`가 있으면 Cloudflare 차단으로 분류한다.
- JSON이 아닌 응답, 필수 응답 필드 누락, 타임아웃을 구분하여 사용자 친화적 메시지를 표시한다.
- 모든 네트워크 요청은 유한한 타임아웃을 사용한다.
- TLS 인증서 검증은 끄지 않는다.

## 테스트 전략

외부 서버를 실제 호출하지 않는 단위 테스트에서 주입된 가짜 세션을 사용한다. 다음 행위를 테스트 우선으로 구현한다.

- 필수 환경변수 누락 시 명확하게 실패
- 로그인 payload가 `userId`, `password`, `languageCode`로 구성됨
- 로그인 성공 후 `X-Logged-In-User-No` 설정
- 리포트 목록 파라미터 구성
- 최신순 목록 페이지 증가와 빈 페이지 종료
- 리포트 `visitDate` 기준 최근 1개월 필터 및 경계 페이지 종료
- 상세 URL에 `reportNo` 포함
- 과태료와 영업정지 필터가 각각 올바르게 구성됨
- 품질미션 상태 및 정렬 파라미터 구성
- 품질미션 `regDate` 기준 최근 1개월 필터 및 경계 페이지 종료
- 달력 기준 1개월 전 계산과 월말 보정
- Cloudflare challenge 감지
- 진단 결과가 토큰이나 비밀번호를 출력하지 않음
- 두 브랜드가 서로 다른 세션을 사용함
- 첫 브랜드 실패 후에도 두 번째 브랜드가 실행됨
- 1차 실패 브랜드만 정확히 한 번 재시도됨
- 재시도 성공 시 정상 종료하고 재시도 실패 시 브랜드 목록과 함께 비정상 종료함
- 신규 행의 `collected_at`, `updated_at`이 DB 기본값으로 설정됨
- 동일 행 재수집 시 UPDATE 및 `updated_at` 변경이 없음
- 업무 컬럼 변경 시에만 UPDATE되고 `collected_at`은 유지됨
- 부모 리포트가 자식보다 먼저 적재되고 브랜드별 오류 시 전체 롤백됨
- API 및 MSSQL 비밀번호가 출력되지 않음

실제 서버 통합 검증은 사용자가 `.env`를 입력한 뒤 `py crawling.py`로 수행한다.

## 완료 조건

- `py -m pytest`가 모두 통과한다.
- `.env.example`만으로 두 브랜드에 필요한 입력값을 알 수 있다.
- 실제 `.env`는 버전 관리에서 제외된다.
- `py crawling.py`가 브랜드별 최근 1개월 수집 대상 건수와 각 API의 성공 여부를 출력한다.
- 한 브랜드 실패가 다른 브랜드의 1차 실행을 막지 않는다.
- 실패 브랜드는 다른 브랜드의 1차 실행 이후 한 번만 전체 재시도된다.
- 리포트와 품질미션 모두 실행일 기준 최근 1개월 밖의 항목을 결과에서 제외한다.
- 기간 경계를 만날 때까지 필요한 모든 페이지를 조회하며 첫 페이지나 10건으로 제한하지 않는다.
- 신규·변경·동일 행을 구분해 신규와 변경만 DB에 반영한다.
- 실제 변경이 없는 재실행에서는 세 업무 테이블의 `updated_at`이 유지된다.
- 실행 결과에 인증 비밀값이 포함되지 않는다.
- Cloudflare가 차단하면 브라우저 자동화가 필요하다는 진단이 명확히 출력된다.
