-- 080_create_collection_audit_tables.sql 적용 후 실행하는 읽기 전용 확인 쿼리입니다.
-- 아래 쿼리는 스키마와 최근 감사 집계만 조회하며 데이터를 변경하지 않습니다.

SELECT
    schemas.[name] AS [SchemaName],
    tables.[name] AS [TableName]
FROM sys.tables AS tables
INNER JOIN sys.schemas AS schemas
    ON schemas.[schema_id] = tables.[schema_id]
WHERE schemas.[name] = N'dbo'
  AND tables.[name] IN (
      N'FC_DAUM_COLLECTION_RUN',
      N'FC_DAUM_COLLECTION_ATTEMPT'
  )
ORDER BY tables.[name];

SELECT
    tables.[name] AS [TableName],
    columns.[column_id] AS [ColumnOrder],
    columns.[name] AS [ColumnName],
    types.[name] AS [DataType],
    columns.[max_length] AS [MaxLength],
    columns.[is_nullable] AS [IsNullable]
FROM sys.tables AS tables
INNER JOIN sys.schemas AS schemas
    ON schemas.[schema_id] = tables.[schema_id]
INNER JOIN sys.columns AS columns
    ON columns.[object_id] = tables.[object_id]
INNER JOIN sys.types AS types
    ON types.[user_type_id] = columns.[user_type_id]
WHERE schemas.[name] = N'dbo'
  AND tables.[name] IN (
      N'FC_DAUM_COLLECTION_RUN',
      N'FC_DAUM_COLLECTION_ATTEMPT'
  )
ORDER BY tables.[name], columns.[column_id];

SELECT
    tables.[name] AS [TableName],
    indexes.[name] AS [IndexName],
    indexes.[is_primary_key] AS [IsPrimaryKey],
    indexes.[is_unique] AS [IsUnique]
FROM sys.tables AS tables
INNER JOIN sys.schemas AS schemas
    ON schemas.[schema_id] = tables.[schema_id]
INNER JOIN sys.indexes AS indexes
    ON indexes.[object_id] = tables.[object_id]
WHERE schemas.[name] = N'dbo'
  AND tables.[name] IN (
      N'FC_DAUM_COLLECTION_RUN',
      N'FC_DAUM_COLLECTION_ATTEMPT'
  )
  AND indexes.[index_id] > 0
ORDER BY tables.[name], indexes.[name];

SELECT
    tables.[name] AS [TableName],
    checks.[name] AS [ConstraintName],
    checks.[definition] AS [ConstraintDefinition]
FROM sys.tables AS tables
INNER JOIN sys.schemas AS schemas
    ON schemas.[schema_id] = tables.[schema_id]
INNER JOIN sys.check_constraints AS checks
    ON checks.[parent_object_id] = tables.[object_id]
WHERE schemas.[name] = N'dbo'
  AND tables.[name] IN (
      N'FC_DAUM_COLLECTION_RUN',
      N'FC_DAUM_COLLECTION_ATTEMPT'
  )
ORDER BY tables.[name], checks.[name];

SELECT
    foreign_keys.[name] AS [ForeignKeyName],
    parent_table.[name] AS [ParentTable],
    referenced_table.[name] AS [ReferencedTable]
FROM sys.foreign_keys AS foreign_keys
INNER JOIN sys.tables AS parent_table
    ON parent_table.[object_id] = foreign_keys.[parent_object_id]
INNER JOIN sys.tables AS referenced_table
    ON referenced_table.[object_id] = foreign_keys.[referenced_object_id]
WHERE foreign_keys.[name] = N'FK_FC_DAUM_COLLECTION_ATTEMPT_RUN';

SELECT TOP (20)
    [RunId],
    [ScheduledDate],
    [StartedAt],
    [FinishedAt],
    [RunStatus],
    [SuccessfulBrands],
    [FailedBrands]
FROM [dbo].[FC_DAUM_COLLECTION_RUN]
ORDER BY [StartedAt] DESC, CONVERT(CHAR(36), [RunId]) DESC;

SELECT TOP (100)
    [RunId],
    [BrandCode],
    [BrandName],
    [AttemptNo],
    [StartedAt],
    [FinishedAt],
    [AttemptStatus],
    [ApiCount],
    [ReportInsertedCount],
    [ReportChangedCount],
    [ReportUnchangedCount],
    [IssueInsertedCount],
    [IssueChangedCount],
    [IssueUnchangedCount],
    [MissionInsertedCount],
    [MissionChangedCount],
    [MissionUnchangedCount],
    [DbCommitted],
    [ErrorCategory]
FROM [dbo].[FC_DAUM_COLLECTION_ATTEMPT]
ORDER BY [FinishedAt] DESC, [RunId], [BrandCode], [AttemptNo];
