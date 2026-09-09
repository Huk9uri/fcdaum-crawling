# 품질미션 컬럼 매핑 변경 설계

## 목적

`dbo.fc_daum_mission`의 컬럼 의미를 FC다움 품질미션 업무 역할에 맞게 명확히 하고, 불필요한 제출자 이름과 수행 코멘트 수집을 제거한다.

## 확정 스키마 및 API 매핑

| API 필드 | DB 컬럼 | 의미 |
|---|---|---|
| `title` | `title` | 품질미션 제목 |
| `description` | `description` | 품질미션 설명 |
| `startUserNm` | `sv_name` | 미션을 전송한 SV 이름 |
| `actionDate` | `owner_submitted_at` | 점주가 수행 결과를 제출한 시각 |
| `completeDate` | `sv_completed_at` | SV가 최종 완료 처리한 시각 |

`actionUserNm`과 `actionComment`는 수집하거나 DB에 저장하지 않는다.

## 코드 변경 범위

- 품질미션 API 응답 매핑 키를 변경된 DB 컬럼명에 맞춘다.
- 품질미션 INSERT 및 UPDATE 대상 컬럼에서 삭제된 컬럼을 제거한다.
- `completeUserNm`은 별도 저장하지 않는다. SV 이름은 미션 전송자인 `startUserNm`만 `sv_name`에 저장한다.
- 신규·변경·미변경 판정은 변경된 컬럼 집합을 사용한다.
- 기존 리포트 및 리포트 문제항목 적재 로직은 변경하지 않는다.

## 테스트

- API 원본의 `title`, `description`, `startUserNm`, `actionDate`, `completeDate`가 각각 정확한 DB 키로 변환되는지 검증한다.
- `actionUserNm`, `actionComment`가 변환 결과에 포함되지 않는지 검증한다.
- Repository가 변경된 14개 품질미션 컬럼으로 INSERT 및 UPDATE SQL을 생성하는지 검증한다.
- 전체 자동화 테스트를 실행해 기존 수집 및 적재 동작의 회귀 여부를 확인한다.

## DB 전제조건

사용자가 다음 DB 스키마 변경을 완료했다.

- `inspection_comment` -> `title`
- `sender_name` -> `sv_name`
- `action_date` -> `owner_submitted_at`
- `completed_date` -> `sv_completed_at`
- `action_user_name`, `action_comment` 삭제
