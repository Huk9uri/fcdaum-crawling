-- 한글 품질미션 상태를 안전하게 저장할 수 있도록 컬럼 형식을 변경합니다.
ALTER TABLE dbo.fc_daum_mission
ALTER COLUMN mission_status NVARCHAR(30) NULL;
GO

-- 미제출 미션의 마감 여부를 조회 시점에 실시간으로 계산합니다.
-- 원본 날짜는 UTC datetime2로 저장되므로 SYSUTCDATETIME()을 사용합니다.
CREATE OR ALTER VIEW dbo.vw_fc_daum_mission
AS
SELECT
    m.brand_code,
    m.brand_name,
    m.mission_no,
    m.report_no,
    m.store_name,
    m.sent_date,
    m.due_date,
    m.mission_status,
    CASE
        WHEN m.owner_submitted_at IS NULL
         AND m.due_date < SYSUTCDATETIME()
            THEN N'마감됨'
        ELSE m.mission_status
    END AS display_status,
    m.title,
    m.description,
    m.sv_name,
    m.owner_submitted_at,
    m.sv_completed_at,
    m.collected_at,
    m.updated_at
FROM dbo.fc_daum_mission AS m;
GO

-- 전체 품질미션 조회
-- SELECT *
-- FROM dbo.vw_fc_daum_mission
-- ORDER BY due_date DESC;

-- 마감된 미수행 품질미션만 조회
-- SELECT *
-- FROM dbo.vw_fc_daum_mission
-- WHERE display_status = N'마감됨'
-- ORDER BY due_date DESC;
