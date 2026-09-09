from datetime import date, datetime
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

from audit import (
    AuditAttempt,
    AuditError,
    AuditRepository,
    connect_audit_repository,
    determine_run_status,
    sanitize_error_category,
)
from fnb_client import ApiError
from db_config import DatabaseSettings
from mssql_repository import DatabaseError


RUN_ID = UUID("12345678-1234-5678-1234-567812345678")
STARTED_AT = datetime(2026, 9, 8, 1, 2, 3)
FINISHED_AT = datetime(2026, 9, 8, 1, 3, 4)


class FakeCursor:
    def __init__(self, fail=False, close_fail=False):
        self.fail = fail
        self.close_fail = close_fail
        self.executed = []
        self.close_count = 0

    def execute(self, sql, *parameters):
        if self.fail:
            raise RuntimeError("DB 원문 secret-token")
        self.executed.append((sql, parameters))
        return self

    def close(self):
        self.close_count += 1
        if self.close_fail:
            raise RuntimeError("cursor close secret")


class FakeConnection:
    def __init__(self, fail=False, close_fail=False):
        self.cursor_instance = FakeCursor(fail, close_fail)
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


def successful_attempt(**overrides):
    values = {
        "run_id": RUN_ID,
        "brand_code": "hanchon",
        "brand_name": "한촌설렁탕",
        "attempt_no": 1,
        "started_at": STARTED_AT,
        "finished_at": FINISHED_AT,
        "attempt_status": "SUCCESS",
        "api_count": 6,
        "report_inserted_count": 1,
        "report_changed_count": 2,
        "report_unchanged_count": 3,
        "issue_inserted_count": 4,
        "issue_changed_count": 5,
        "issue_unchanged_count": 6,
        "mission_inserted_count": 7,
        "mission_changed_count": 8,
        "mission_unchanged_count": 9,
        "db_committed": True,
        "error_category": None,
    }
    values.update(overrides)
    return AuditAttempt(**values)


def test_repository_commits_each_run_and_attempt_write():
    connection = FakeConnection()
    repository = AuditRepository(connection)

    repository.start_run(RUN_ID, date(2026, 9, 8), STARTED_AT)
    repository.record_attempt(successful_attempt())
    repository.finish_run(RUN_ID, FINISHED_AT, "SUCCESS", 2, 0)

    assert connection.commit_count == 3
    assert connection.rollback_count == 0
    assert connection.cursor_instance.close_count == 3
    assert len(connection.cursor_instance.executed) == 3
    attempt_sql, attempt_parameters = connection.cursor_instance.executed[1]
    assert "FC_DAUM_COLLECTION_ATTEMPT" in attempt_sql
    assert attempt_parameters == (
        RUN_ID,
        "hanchon",
        "한촌설렁탕",
        1,
        STARTED_AT,
        FINISHED_AT,
        "SUCCESS",
        6,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        True,
        None,
    )


def test_repository_rolls_back_and_never_exposes_raw_database_error():
    connection = FakeConnection(fail=True, close_fail=True)
    repository = AuditRepository(connection)

    with pytest.raises(AuditError) as caught:
        repository.start_run(RUN_ID, date(2026, 9, 8), STARTED_AT)

    assert connection.commit_count == 0
    assert connection.rollback_count == 1
    assert connection.cursor_instance.close_count == 1
    assert "secret-token" not in str(caught.value)
    assert "DB 원문 secret-token" in str(caught.value.__cause__)


def test_cursor_close_failure_does_not_override_successful_commit():
    connection = FakeConnection(close_fail=True)
    repository = AuditRepository(connection)

    repository.start_run(RUN_ID, date(2026, 9, 8), STARTED_AT)

    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.cursor_instance.close_count == 1


def test_repository_replaces_untrusted_error_category_before_insert():
    connection = FakeConnection()
    repository = AuditRepository(connection)

    repository.record_attempt(
        successful_attempt(
            attempt_status="FAILED",
            db_committed=False,
            error_category="Bearer secret-token",
        )
    )

    _, parameters = connection.cursor_instance.executed[0]
    assert parameters[-1] == "UNEXPECTED_ERROR"
    assert "secret-token" not in repr(parameters)


def test_connect_audit_repository_targets_adapter_dbo_schema(monkeypatch):
    connection = FakeConnection()
    pyodbc = SimpleNamespace(
        drivers=lambda: ["ODBC Driver 17 for SQL Server"],
        connect=lambda *args, **kwargs: connection,
        Error=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "pyodbc", pyodbc)
    settings = DatabaseSettings(
        server="db.example",
        port=1433,
        database="monitoring",
        user="collector",
        password="secret",
        schema="custom",
    )

    repository = connect_audit_repository(settings)

    assert repository.connection is connection
    assert repository.schema == "dbo"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiError("Bearer secret-token"), "API_ERROR"),
        (DatabaseError("PWD=secret-password"), "DATABASE_ERROR"),
        (ValueError("response body secret"), "INVALID_DATA"),
        (RuntimeError("raw exception"), "UNEXPECTED_ERROR"),
    ],
)
def test_sanitize_error_category_uses_exception_type_only(error, expected):
    category = sanitize_error_category(error)

    assert category == expected
    assert "secret" not in category.lower()
    assert str(error) not in category


@pytest.mark.parametrize(
    ("successful", "failed", "retried", "api_count", "initialization_failed", "expected"),
    [
        (1, 1, False, 10, False, "PARTIAL_FAILED"),
        (0, 2, False, 0, False, "FAILED"),
        (2, 0, True, 10, False, "WARNING"),
        (2, 0, False, 10, False, "SUCCESS"),
        (2, 0, False, 0, False, "SUCCESS_EMPTY"),
        (0, 0, False, 0, True, "FAILED"),
    ],
)
def test_determine_run_status_obeys_monitoring_precedence(
    successful, failed, retried, api_count, initialization_failed, expected
):
    assert determine_run_status(
        successful_brands=successful,
        failed_brands=failed,
        had_retry=retried,
        api_count=api_count,
        initialization_failed=initialization_failed,
    ) == expected
