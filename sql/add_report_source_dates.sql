-- FC다움 원본 리포트의 등록·수정 시각을 보존합니다.
IF COL_LENGTH('dbo.fc_daum_qsc_report', 'reg_date') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report
    ADD reg_date DATETIME2(3) NULL;

IF COL_LENGTH('dbo.fc_daum_qsc_report', 'source_updated_at') IS NULL
    ALTER TABLE dbo.fc_daum_qsc_report
    ADD source_updated_at DATETIME2(3) NULL;
