# FC다움 브랜드명 컬럼 추가 설계

## 목적

내부 식별자인 `brand_code`는 기본키·외래키 구성에 그대로 사용하고, 업무 조회용 한글 브랜드명을 `brand_name`으로 별도 저장한다.

## 브랜드 매핑

- `hanchon` -> `한촌`
- `yuksudang` -> `육수당`
- 정의되지 않은 브랜드 코드는 데이터 유실 방지를 위해 원본 코드값을 브랜드명으로 사용한다.

## 적용 대상

다음 세 테이블에 `brand_name NVARCHAR(30) NOT NULL`을 추가한다.

- `dbo.fc_daum_qsc_report`
- `dbo.fc_daum_qsc_report_issue`
- `dbo.fc_daum_mission`

기존 행은 `brand_code`를 기준으로 브랜드명을 채운 뒤 `NOT NULL` 제약을 적용한다. `brand_code` 기본키 및 외래키 구조는 변경하지 않는다.

## 수집 및 적재

Python 매핑 계층은 리포트, 문제항목, 품질미션 모두에 `brand_name`을 포함한다. Repository의 세 `TableSpec`에도 `brand_name`을 추가하여 신규 INSERT와 변경 UPDATE 대상에 포함한다.

## View

`dbo.vw_fc_daum_mission`에는 `brand_code` 바로 다음에 `brand_name`을 표시한다. 기존 실시간 `display_status` 계산은 그대로 유지한다.

## 테스트 및 검증

- 두 브랜드의 한글 이름 변환과 미등록 코드 fallback을 검증한다.
- 세 데이터 매핑 결과에 `brand_name`이 포함되는지 검증한다.
- 세 `TableSpec`에 `brand_name`이 포함되는지 검증한다.
- 전체 자동화 테스트를 실행한다.
- DB 변경 SQL 실행 후 기존 데이터와 View 컬럼을 확인한다.
- 크롤러를 재실행하여 신규·변경·미변경 판정을 확인한다.
