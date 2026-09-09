from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CREATE_SQL = ROOT / "sql" / "080_create_collection_audit_tables.sql"
VERIFY_SQL = ROOT / "sql" / "085_verify_collection_audit_tables.sql"


RUN_COLUMNS = {
    "RunId",
    "ScheduledDate",
    "StartedAt",
    "FinishedAt",
    "RunStatus",
    "SuccessfulBrands",
    "FailedBrands",
}

ATTEMPT_COLUMNS = {
    "RunId",
    "BrandCode",
    "BrandName",
    "AttemptNo",
    "StartedAt",
    "FinishedAt",
    "AttemptStatus",
    "ApiCount",
    "ReportInsertedCount",
    "ReportChangedCount",
    "ReportUnchangedCount",
    "IssueInsertedCount",
    "IssueChangedCount",
    "IssueUnchangedCount",
    "MissionInsertedCount",
    "MissionChangedCount",
    "MissionUnchangedCount",
    "DbCommitted",
    "ErrorCategory",
}


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+\[dbo\]\.\[{table}\]\s*\((.*?)\)\s*;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"{table} CREATE TABLE 문이 없습니다."
    return match.group(1)


def _declared_columns(table_body: str) -> set[str]:
    return set(
        re.findall(r"^\s*\[([A-Za-z][A-Za-z0-9]*)\]\s+", table_body, re.MULTILINE)
    )


def test_create_sql_declares_adapter_contract_columns_only():
    sql = CREATE_SQL.read_text(encoding="utf-8")

    assert _declared_columns(_table_body(sql, "FC_DAUM_COLLECTION_RUN")) == RUN_COLUMNS
    assert (
        _declared_columns(_table_body(sql, "FC_DAUM_COLLECTION_ATTEMPT"))
        == ATTEMPT_COLUMNS
    )


def test_create_sql_has_primary_foreign_check_constraints_and_indexes():
    sql = CREATE_SQL.read_text(encoding="utf-8")
    normalized = " ".join(sql.upper().split())

    assert "PRIMARY KEY ([RUNID])" in normalized
    assert "PRIMARY KEY ([RUNID], [BRANDCODE], [ATTEMPTNO])" in normalized
    assert "FOREIGN KEY ([RUNID]) REFERENCES [DBO].[FC_DAUM_COLLECTION_RUN] ([RUNID])" in normalized
    assert "CHECK ([ATTEMPTNO] > 0)" in normalized
    assert "CHECK ([APICOUNT] >= 0)" in normalized
    assert "CHECK ([DBCOMMITTED] IN (0, 1))" in normalized
    assert "[ERRORCATEGORY] IS NOT NULL" in normalized
    assert "[ERRORCATEGORY] IN (" in normalized
    for category in (
        "API_ERROR",
        "DATABASE_ERROR",
        "INITIALIZATION_ERROR",
        "INVALID_DATA",
        "UNEXPECTED_ERROR",
    ):
        assert f"'{category}'" in normalized
    assert "CK_FC_DAUM_COLLECTION_RUN_STATUS" in normalized
    assert "CK_FC_DAUM_COLLECTION_ATTEMPT_STATUS" in normalized
    assert "CREATE INDEX [IX_FC_DAUM_COLLECTION_RUN_STARTEDAT]" in normalized
    assert "CREATE INDEX [IX_FC_DAUM_COLLECTION_ATTEMPT_RUN_FINISHEDAT]" in normalized


def test_audit_schema_excludes_sensitive_and_raw_payload_columns():
    sql = CREATE_SQL.read_text(encoding="utf-8")
    declared = _declared_columns(_table_body(sql, "FC_DAUM_COLLECTION_RUN")) | _declared_columns(
        _table_body(sql, "FC_DAUM_COLLECTION_ATTEMPT")
    )
    forbidden_fragments = (
        "account",
        "userid",
        "password",
        "cookie",
        "token",
        "response",
        "payload",
        "businessdata",
        "errormessage",
        "exception",
        "sqltext",
    )

    assert not any(
        fragment in column.lower()
        for column in declared
        for fragment in forbidden_fragments
    )


def test_verify_sql_is_read_only_and_checks_both_tables():
    sql = VERIFY_SQL.read_text(encoding="utf-8")
    statements = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).upper()

    assert "FC_DAUM_COLLECTION_RUN" in statements
    assert "FC_DAUM_COLLECTION_ATTEMPT" in statements
    assert "SYS.CHECK_CONSTRAINTS" in statements
    assert "SYS.FOREIGN_KEYS" in statements
    assert "SELECT" in statements
    assert not re.search(
        r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|EXEC(?:UTE)?)\b",
        statements,
    )
