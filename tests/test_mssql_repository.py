from datetime import datetime
import re

import pytest

from collector import BrandCollection
from mssql_repository import (
    DatabaseError,
    ISSUE_SPEC,
    MISSION_SPEC,
    MssqlRepository,
    REPORT_BASE_SPEC,
    REPORT_SPEC,
    TableSpec,
    build_insert_sql,
    build_update_sql,
    partition_rows,
)


SPEC = TableSpec(
    table="sample",
    key_column="report_no",
    columns=("brand_code", "report_no", "store_name"),
)


def test_mission_spec_matches_current_database_schema():
    assert MISSION_SPEC.columns == (
        "brand_code", "brand_name", "mission_no", "report_no", "store_name",
        "sent_date",
        "due_date", "mission_status", "description", "title", "sv_name",
        "owner_submitted_at", "sv_completed_at",
    )


def test_report_and_issue_specs_include_brand_name_after_brand_code():
    assert REPORT_SPEC.columns[:2] == ("brand_code", "brand_name")
    assert ISSUE_SPEC.columns[:2] == ("brand_code", "brand_name")


def test_report_spec_includes_expected_sanctions_but_base_spec_does_not():
    assert REPORT_SPEC.columns[-2:] == (
        "expected_fine_amount",
        "expected_suspension_days",
    )
    assert "expected_fine_amount" not in REPORT_BASE_SPEC.columns
    assert "expected_suspension_days" not in REPORT_BASE_SPEC.columns


def test_report_specs_include_source_registration_and_update_dates():
    assert "reg_date" in REPORT_BASE_SPEC.columns
    assert "source_updated_at" in REPORT_BASE_SPEC.columns
    assert "reg_date" in REPORT_SPEC.columns
    assert "source_updated_at" in REPORT_SPEC.columns


def test_partition_rows_splits_new_unchanged_and_changed():
    rows = [
        {"brand_code": "h", "report_no": 1, "store_name": "new"},
        {"brand_code": "h", "report_no": 2, "store_name": "same"},
        {"brand_code": "h", "report_no": 3, "store_name": "changed"},
    ]
    existing = {
        2: {"brand_code": "h", "report_no": 2, "store_name": "same"},
        3: {"brand_code": "h", "report_no": 3, "store_name": "old"},
    }

    new_rows, changed_rows, unchanged_count = partition_rows(rows, existing, SPEC)

    assert [row["report_no"] for row in new_rows] == [1]
    assert [row["report_no"] for row in changed_rows] == [3]
    assert unchanged_count == 1


def test_insert_and_update_sql_preserve_audit_semantics():
    insert_sql = build_insert_sql("dbo", SPEC)
    update_sql = build_update_sql("dbo", SPEC)

    assert "collected_at" not in insert_sql
    assert "updated_at" not in insert_sql
    assert "[store_name] = ?" in update_sql
    assert "[collected_at]" not in update_sql
    assert "[updated_at] = SYSUTCDATETIME()" in update_sql


class FakeCursor:
    def __init__(self, fail_table=None, existing_rows=None):
        self.fail_table = fail_table
        self.existing_rows = existing_rows or {}
        self.executed = []
        self.executed_many = []
        self._rows = []
        self.description = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        self._rows = []
        self.description = []
        if sql.startswith("SELECT") and "fc_daum_qsc_report]" in sql:
            selected = sql.split(" FROM ", 1)[0]
            columns = re.findall(r"\[([^]]+)\]", selected)
            self.description = [(column,) for column in columns]
            for key in params[1:]:
                row = self.existing_rows.get(key)
                if row is not None:
                    self._rows.append(tuple(row[column] for column in columns))
        return self

    def fetchall(self):
        return self._rows

    def executemany(self, sql, params):
        if self.fail_table and self.fail_table in sql:
            raise RuntimeError("db failure")
        self.executed_many.append((sql, list(params)))
        return self


class FakeConnection:
    def __init__(self, fail_table=None, existing_rows=None):
        self.cursor_instance = FakeCursor(fail_table, existing_rows)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def sample_collection():
    return BrandCollection(
        reports=[
            {
                "reportNo": 1,
                "storeNm": "매장",
                "visitDate": 0,
                "grade": "A",
                "percentageScore": 90,
                "userNm": "점검자",
            }
        ],
        report_details={},
        issues={
            10: {
                "answerNo": 10,
                "reportNo": 1,
                "storeNm": "매장",
                "reportVisitDate": 0,
            }
        },
        missions=[
            {
                "missionNo": 20,
                "reportNo": 1,
                "storeNm": "매장",
                "startDate": 0,
            }
        ],
        cutoff_ms=0,
        issue_scanned_report_nos=frozenset({1}),
    )


def test_save_collection_inserts_parent_before_children_and_commits():
    connection = FakeConnection()
    repository = MssqlRepository(connection, schema="dbo")

    stats = repository.save_collection("hanchon", sample_collection())

    tables = [
        "fc_daum_qsc_report" if "fc_daum_qsc_report]" in sql and "issue" not in sql
        else "fc_daum_qsc_report_issue" if "fc_daum_qsc_report_issue" in sql
        else "fc_daum_mission"
        for sql, _ in connection.cursor_instance.executed_many
    ]
    assert tables == [
        "fc_daum_qsc_report",
        "fc_daum_qsc_report_issue",
        "fc_daum_mission",
    ]
    assert stats.reports.inserted == 1
    assert stats.issues.inserted == 1
    assert stats.missions.inserted == 1
    assert stats.db_committed is True
    assert connection.committed is True
    assert connection.rolled_back is False


def test_save_collection_inserts_new_support_report_with_zero_sanctions():
    collection = BrandCollection(
        reports=[
            {"reportNo": 1, "storeNm": "최근 매장", "visitDate": 0},
            {"reportNo": 2, "storeNm": "지원 매장", "visitDate": 0},
        ],
        report_details={},
        issues={
            10: {
                "answerNo": 10,
                "reportNo": 1,
                "fine": 500,
                "suspension": 30,
            }
        },
        missions=[],
        cutoff_ms=0,
        issue_scanned_report_nos=frozenset({1}),
    )
    connection = FakeConnection()
    repository = MssqlRepository(connection, schema="dbo")

    stats = repository.save_collection("hanchon", collection)

    report_inserts = [
        (sql, params)
        for sql, params in connection.cursor_instance.executed_many
        if "fc_daum_qsc_report]" in sql and "issue" not in sql
    ]
    assert len(report_inserts) == 2
    assert "[expected_fine_amount]" in report_inserts[0][0]
    assert "[expected_suspension_days]" in report_inserts[0][0]
    assert "[expected_fine_amount]" in report_inserts[1][0]
    assert "[expected_suspension_days]" in report_inserts[1][0]
    assert report_inserts[1][1][0][-2:] == (0, 0)
    assert stats.reports.inserted == 2


def test_save_collection_preserves_existing_support_report_sanctions():
    collection = BrandCollection(
        reports=[{"reportNo": 2, "storeNm": "변경 매장", "visitDate": 0}],
        report_details={},
        issues={},
        missions=[],
        cutoff_ms=0,
        issue_scanned_report_nos=frozenset(),
    )
    connection = FakeConnection(
        existing_rows={
            2: {
                "brand_code": "hanchon",
                "brand_name": "한촌",
                "report_no": 2,
                "store_name": "기존 매장",
                "visit_date": datetime(1970, 1, 1),
                "reg_date": None,
                "source_updated_at": None,
                "grade": None,
                "percentage_score": None,
                "inspector_name": None,
            }
        }
    )
    repository = MssqlRepository(connection, schema="dbo")

    stats = repository.save_collection("hanchon", collection)

    report_updates = [
        sql
        for sql, _ in connection.cursor_instance.executed_many
        if sql.startswith("UPDATE") and "fc_daum_qsc_report]" in sql
    ]
    assert len(report_updates) == 1
    assert "[store_name] = ?" in report_updates[0]
    assert "expected_fine_amount" not in report_updates[0]
    assert "expected_suspension_days" not in report_updates[0]
    assert stats.reports.updated == 1


def test_save_collection_rolls_back_when_child_insert_fails():
    connection = FakeConnection(fail_table="fc_daum_qsc_report_issue")
    repository = MssqlRepository(connection, schema="dbo")

    with pytest.raises(DatabaseError, match="MSSQL 트랜잭션"):
        repository.save_collection("hanchon", sample_collection())

    assert connection.committed is False
    assert connection.rolled_back is True
