# 품질미션 한글 상태 및 실시간 마감 조회 설계

## 목적

FC다움 API의 영문 품질미션 상태를 업무용 한글 상태로 저장하고, 미제출 미션의 마감 여부는 조회 시점에 실시간으로 계산한다.

## 저장 상태 변환

`dbo.fc_daum_mission.mission_status`에는 다음 한글 상태를 저장한다.

- `DOING` -> `수행 전`
- `ACTION` -> `제출 완료`
- `COMPLETE` -> `완료됨`
- `REDOING` -> `재수행 요청`
- 정의되지 않은 값 -> 원본값 유지
- `NULL` -> `NULL`

`마감됨`은 테이블에 저장하지 않는다.

## 실시간 마감 상태

`dbo.vw_fc_daum_mission` View에 `display_status`를 추가한다.

```sql
CASE
    WHEN owner_submitted_at IS NULL
     AND due_date < SYSUTCDATETIME()
        THEN N'마감됨'
    ELSE mission_status
END AS display_status
```

API 날짜는 UTC `datetime2`로 저장되므로 현재 시각도 `SYSUTCDATETIME()`으로 비교한다. `due_date`가 현재 시각과 같은 경우에는 마감된 것으로 처리하지 않는다.

## DB 변경

한글 상태 저장을 위해 `mission_status`를 `NVARCHAR(30)`으로 변경한다. View는 현재 품질미션 테이블의 14개 컬럼과 계산된 `display_status`를 제공한다.

```sql
ALTER TABLE dbo.fc_daum_mission
ALTER COLUMN mission_status NVARCHAR(30) NULL;
```

## 조회 방식

전체 조회:

```sql
SELECT *
FROM dbo.vw_fc_daum_mission
ORDER BY due_date DESC;
```

마감된 미수행 미션 조회:

```sql
SELECT *
FROM dbo.vw_fc_daum_mission
WHERE display_status = N'마감됨'
ORDER BY due_date DESC;
```

## 테스트

- 네 가지 API 상태의 한글 변환을 검증한다.
- 알 수 없는 상태와 `NULL` 상태의 보존을 검증한다.
- View SQL이 `owner_submitted_at IS NULL`, `due_date < SYSUTCDATETIME()` 조건으로 `마감됨`을 계산하는지 검토한다.
- 전체 회귀 테스트를 실행한다.
- DB 변경 후 실제 수집을 재실행하고 상태값 갱신을 확인한다.
