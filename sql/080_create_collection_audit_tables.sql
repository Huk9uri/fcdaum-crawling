-- FC다움 수집기의 실행·브랜드별 시도 감사 이력을 생성합니다.
-- 감사 테이블에는 집계값과 정규화 오류 분류만 저장합니다.
-- 계정, 인증정보, 응답 본문, 업무 데이터, 원문 예외는 저장하지 않습니다.
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'[dbo].[FC_DAUM_COLLECTION_RUN]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[FC_DAUM_COLLECTION_RUN] (
        [RunId] UNIQUEIDENTIFIER NOT NULL,
        [ScheduledDate] DATE NOT NULL,
        [StartedAt] DATETIME2(3) NOT NULL,
        [FinishedAt] DATETIME2(3) NULL,
        [RunStatus] VARCHAR(20) NOT NULL,
        [SuccessfulBrands] INT NOT NULL CONSTRAINT [DF_FC_DAUM_COLLECTION_RUN_SUCCESSFUL] DEFAULT (0),
        [FailedBrands] INT NOT NULL CONSTRAINT [DF_FC_DAUM_COLLECTION_RUN_FAILED] DEFAULT (0),
        CONSTRAINT [PK_FC_DAUM_COLLECTION_RUN] PRIMARY KEY ([RunId]),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_RUN_STATUS] CHECK ([RunStatus] IN (
            'SUCCESS', 'SUCCESS_EMPTY', 'WARNING', 'PARTIAL_FAILED',
            'FAILED', 'RUNNING', 'ABORTED', 'NOT_RUN'
        )),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_RUN_COUNTS] CHECK (
            [SuccessfulBrands] >= 0 AND [FailedBrands] >= 0
        ),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_RUN_TIME] CHECK (
            [FinishedAt] IS NULL OR [FinishedAt] >= [StartedAt]
        )
    );
END;
GO

IF OBJECT_ID(N'[dbo].[FC_DAUM_COLLECTION_ATTEMPT]', N'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[FC_DAUM_COLLECTION_ATTEMPT] (
        [RunId] UNIQUEIDENTIFIER NOT NULL,
        [BrandCode] VARCHAR(50) NOT NULL,
        [BrandName] NVARCHAR(100) NOT NULL,
        [AttemptNo] INT NOT NULL,
        [StartedAt] DATETIME2(3) NOT NULL,
        [FinishedAt] DATETIME2(3) NOT NULL,
        [AttemptStatus] VARCHAR(20) NOT NULL,
        [ApiCount] INT NOT NULL,
        [ReportInsertedCount] INT NOT NULL,
        [ReportChangedCount] INT NOT NULL,
        [ReportUnchangedCount] INT NOT NULL,
        [IssueInsertedCount] INT NOT NULL,
        [IssueChangedCount] INT NOT NULL,
        [IssueUnchangedCount] INT NOT NULL,
        [MissionInsertedCount] INT NOT NULL,
        [MissionChangedCount] INT NOT NULL,
        [MissionUnchangedCount] INT NOT NULL,
        [DbCommitted] BIT NOT NULL,
        [ErrorCategory] VARCHAR(64) NULL,
        CONSTRAINT [PK_FC_DAUM_COLLECTION_ATTEMPT]
            PRIMARY KEY ([RunId], [BrandCode], [AttemptNo]),
        CONSTRAINT [FK_FC_DAUM_COLLECTION_ATTEMPT_RUN]
            FOREIGN KEY ([RunId]) REFERENCES [dbo].[FC_DAUM_COLLECTION_RUN] ([RunId]),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_NO]
            CHECK ([AttemptNo] > 0),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_STATUS]
            CHECK ([AttemptStatus] IN ('SUCCESS', 'SUCCESS_EMPTY', 'FAILED')),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_API_COUNT]
            CHECK ([ApiCount] >= 0),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_REPORT_COUNTS] CHECK (
            [ReportInsertedCount] >= 0
            AND [ReportChangedCount] >= 0
            AND [ReportUnchangedCount] >= 0
        ),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_ISSUE_COUNTS] CHECK (
            [IssueInsertedCount] >= 0
            AND [IssueChangedCount] >= 0
            AND [IssueUnchangedCount] >= 0
        ),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_MISSION_COUNTS] CHECK (
            [MissionInsertedCount] >= 0
            AND [MissionChangedCount] >= 0
            AND [MissionUnchangedCount] >= 0
        ),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_COMMITTED]
            CHECK ([DbCommitted] IN (0, 1)),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_ERROR] CHECK (
            ([AttemptStatus] IN ('SUCCESS', 'SUCCESS_EMPTY')
                AND [DbCommitted] = 1 AND [ErrorCategory] IS NULL)
            OR ([AttemptStatus] = 'FAILED'
                AND [DbCommitted] = 0
                AND [ErrorCategory] IS NOT NULL
                AND [ErrorCategory] IN (
                    'API_ERROR', 'DATABASE_ERROR', 'INITIALIZATION_ERROR',
                    'INVALID_DATA', 'UNEXPECTED_ERROR'
                ))
        ),
        CONSTRAINT [CK_FC_DAUM_COLLECTION_ATTEMPT_TIME]
            CHECK ([FinishedAt] >= [StartedAt])
    );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE [object_id] = OBJECT_ID(N'[dbo].[FC_DAUM_COLLECTION_RUN]')
      AND [name] = N'IX_FC_DAUM_COLLECTION_RUN_STARTEDAT'
)
    CREATE INDEX [IX_FC_DAUM_COLLECTION_RUN_STARTEDAT]
        ON [dbo].[FC_DAUM_COLLECTION_RUN] ([StartedAt] DESC, [RunId]);
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE [object_id] = OBJECT_ID(N'[dbo].[FC_DAUM_COLLECTION_RUN]')
      AND [name] = N'IX_FC_DAUM_COLLECTION_RUN_STATUS'
)
    CREATE INDEX [IX_FC_DAUM_COLLECTION_RUN_STATUS]
        ON [dbo].[FC_DAUM_COLLECTION_RUN] ([RunStatus], [StartedAt] DESC);
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE [object_id] = OBJECT_ID(N'[dbo].[FC_DAUM_COLLECTION_ATTEMPT]')
      AND [name] = N'IX_FC_DAUM_COLLECTION_ATTEMPT_RUN_FINISHEDAT'
)
    CREATE INDEX [IX_FC_DAUM_COLLECTION_ATTEMPT_RUN_FINISHEDAT]
        ON [dbo].[FC_DAUM_COLLECTION_ATTEMPT] ([RunId], [FinishedAt] DESC)
        INCLUDE ([BrandCode], [AttemptNo], [AttemptStatus], [DbCommitted]);
GO
