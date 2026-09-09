-- 신규 컬럼을 먼저 생성해 다음 배치에서 정상적으로 인식되도록 합니다.
IF COL_LENGTH('dbo.fc_daum_qsc_report', 'expected_fine_amount') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report
    ADD expected_fine_amount DECIMAL(18, 2) NULL;

IF COL_LENGTH('dbo.fc_daum_qsc_report', 'expected_suspension_days') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report
    ADD expected_suspension_days INT NULL;
GO

SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE r
    SET
        expected_fine_amount = COALESCE(a.expected_fine_amount, 0),
        expected_suspension_days = COALESCE(a.expected_suspension_days, 0)
    FROM dbo.fc_daum_qsc_report AS r
    OUTER APPLY (
        SELECT
            SUM(COALESCE(i.fine_amount, 0)) AS expected_fine_amount,
            SUM(COALESCE(i.suspension_days, 0)) AS expected_suspension_days
        FROM dbo.fc_daum_qsc_report_issue AS i
        WHERE i.brand_code = r.brand_code
          AND i.report_no = r.report_no
    ) AS a;

    ALTER TABLE dbo.fc_daum_qsc_report
    ALTER COLUMN expected_fine_amount DECIMAL(18, 2) NOT NULL;

    ALTER TABLE dbo.fc_daum_qsc_report
    ALTER COLUMN expected_suspension_days INT NOT NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
