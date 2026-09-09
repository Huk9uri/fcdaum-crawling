-- 신규 컬럼을 먼저 생성해 다음 배치에서 정상적으로 인식되도록 합니다.
IF COL_LENGTH('dbo.fc_daum_qsc_report', 'brand_name') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report
    ADD brand_name NVARCHAR(30) NULL;

IF COL_LENGTH('dbo.fc_daum_qsc_report_issue', 'brand_name') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report_issue
    ADD brand_name NVARCHAR(30) NULL;

IF COL_LENGTH('dbo.fc_daum_mission', 'brand_name') IS NULL
    ALTER TABLE dbo.fc_daum_mission
    ADD brand_name NVARCHAR(30) NULL;
GO

SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.fc_daum_qsc_report
    SET brand_name = CASE brand_code
        WHEN 'hanchon' THEN N'한촌'
        WHEN 'yuksudang' THEN N'육수당'
        ELSE CONVERT(NVARCHAR(30), brand_code)
    END;

    UPDATE dbo.fc_daum_qsc_report_issue
    SET brand_name = CASE brand_code
        WHEN 'hanchon' THEN N'한촌'
        WHEN 'yuksudang' THEN N'육수당'
        ELSE CONVERT(NVARCHAR(30), brand_code)
    END;

    UPDATE dbo.fc_daum_mission
    SET brand_name = CASE brand_code
        WHEN 'hanchon' THEN N'한촌'
        WHEN 'yuksudang' THEN N'육수당'
        ELSE CONVERT(NVARCHAR(30), brand_code)
    END;

    ALTER TABLE dbo.fc_daum_qsc_report
    ALTER COLUMN brand_name NVARCHAR(30) NOT NULL;

    ALTER TABLE dbo.fc_daum_qsc_report_issue
    ALTER COLUMN brand_name NVARCHAR(30) NOT NULL;

    ALTER TABLE dbo.fc_daum_mission
    ALTER COLUMN brand_name NVARCHAR(30) NOT NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
