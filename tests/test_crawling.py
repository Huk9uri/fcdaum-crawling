from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pytest

from collector import BrandCollection
from config import BrandAccount, Settings
from audit import AuditError
from crawling import (
    _record_initialization_failure,
    build_monthly_ranges,
    build_argument_parser,
    execute_with_daily_log,
    parse_backfill_range,
    parse_collection_start_date,
    run_all_brands,
    run_monthly_backfill,
)
from fnb_client import ApiError
from mssql_repository import BatchStats, CollectionStats, DatabaseError


KST = timezone(timedelta(hours=9))
EXECUTED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=KST)


def test_parse_collection_start_date_as_kst_midnight():
    assert parse_collection_start_date("2026-01-01", EXECUTED_AT) == datetime(
        2026, 1, 1, 0, 0, tzinfo=KST
    )


@pytest.mark.parametrize("value", ["2026/01/01", "not-a-date", "2026-07-22"])
def test_parse_collection_start_date_rejects_invalid_or_future_date(value):
    with pytest.raises(ValueError):
        parse_collection_start_date(value, EXECUTED_AT)


def test_build_monthly_ranges_respects_partial_first_and_last_months():
    start = datetime(2024, 1, 15, tzinfo=KST)
    end = datetime(2024, 3, 10, tzinfo=KST)

    assert build_monthly_ranges(start, end) == [
        (
            datetime(2024, 1, 15, tzinfo=KST),
            datetime(2024, 2, 1, tzinfo=KST),
        ),
        (
            datetime(2024, 2, 1, tzinfo=KST),
            datetime(2024, 3, 1, tzinfo=KST),
        ),
        (
            datetime(2024, 3, 1, tzinfo=KST),
            datetime(2024, 3, 11, tzinfo=KST),
        ),
    ]


def test_build_monthly_ranges_handles_leap_year_and_year_boundary():
    assert build_monthly_ranges(
        datetime(2024, 2, 1, tzinfo=KST),
        datetime(2025, 1, 2, tzinfo=KST),
    )[-2:] == [
        (
            datetime(2024, 12, 1, tzinfo=KST),
            datetime(2025, 1, 1, tzinfo=KST),
        ),
        (
            datetime(2025, 1, 1, tzinfo=KST),
            datetime(2025, 1, 3, tzinfo=KST),
        ),
    ]

    february = build_monthly_ranges(
        datetime(2024, 2, 1, tzinfo=KST),
        datetime(2024, 2, 29, tzinfo=KST),
    )
    assert february == [
        (
            datetime(2024, 2, 1, tzinfo=KST),
            datetime(2024, 3, 1, tzinfo=KST),
        )
    ]


def test_build_monthly_ranges_supports_single_day_and_rejects_reverse_range():
    day = datetime(2024, 5, 7, tzinfo=KST)
    assert build_monthly_ranges(day, day) == [
        (day, datetime(2024, 5, 8, tzinfo=KST))
    ]

    with pytest.raises(ValueError, match="시작일"):
        build_monthly_ranges(
            datetime(2024, 5, 8, tzinfo=KST),
            datetime(2024, 5, 7, tzinfo=KST),
        )


def test_parse_backfill_range_returns_kst_midnights():
    assert parse_backfill_range(
        "2024-01-01", "2025-12-31", EXECUTED_AT
    ) == (
        datetime(2024, 1, 1, tzinfo=KST),
        datetime(2025, 12, 31, tzinfo=KST),
    )


@pytest.mark.parametrize(
    ("from_value", "to_value"),
    [("2024-01-01", None), (None, "2024-01-31")],
)
def test_parse_backfill_range_requires_both_options(from_value, to_value):
    with pytest.raises(ValueError, match="함께"):
        parse_backfill_range(from_value, to_value, EXECUTED_AT)


def test_parse_backfill_range_rejects_reverse_and_future_end():
    with pytest.raises(ValueError, match="시작일"):
        parse_backfill_range("2024-02-01", "2024-01-31", EXECUTED_AT)

    with pytest.raises(ValueError, match="실행일 이후"):
        parse_backfill_range("2026-01-01", "2026-07-22", EXECUTED_AT)


def test_parse_backfill_range_rejects_from_date_combination():
    with pytest.raises(ValueError, match="함께 사용할 수 없습니다"):
        parse_backfill_range(
            "2024-01-01",
            "2024-01-31",
            EXECUTED_AT,
            from_date="2026-01-01",
        )


def test_argument_parser_accepts_monthly_backfill_options():
    args = build_argument_parser().parse_args(
        ["--backfill-from", "2024-01-01", "--backfill-to", "2025-12-31"]
    )

    assert args.backfill_from == "2024-01-01"
    assert args.backfill_to == "2025-12-31"
    assert args.from_date is None


def test_run_monthly_backfill_processes_oldest_first_and_logs_completion():
    ranges = [
        (
            datetime(2024, 1, 1, tzinfo=KST),
            datetime(2024, 2, 1, tzinfo=KST),
        ),
        (
            datetime(2024, 2, 1, tzinfo=KST),
            datetime(2024, 3, 1, tzinfo=KST),
        ),
    ]
    calls = []
    output = StringIO()

    def run_range(start, end):
        calls.append((start, end))
        return 0

    exit_code = run_monthly_backfill(ranges, run_range=run_range, output=output)

    assert exit_code == 0
    assert calls == ranges
    text = output.getvalue()
    assert "[백필 2024-01] 시작: 2024-01-01 ~ 2024-01-31" in text
    assert "[백필 2024-01] 완료" in text
    assert "[백필 2024-02] 완료" in text
    assert "[백필 완료] 2개월" in text


def test_run_monthly_backfill_stops_after_failed_month():
    ranges = [
        (
            datetime(2024, month, 1, tzinfo=KST),
            datetime(2024, month + 1, 1, tzinfo=KST),
        )
        for month in (1, 2, 3)
    ]
    calls = []
    output = StringIO()

    def run_range(start, end):
        calls.append((start, end))
        return 1 if start.month == 2 else 0

    exit_code = run_monthly_backfill(ranges, run_range=run_range, output=output)

    assert exit_code == 1
    assert [start.month for start, _ in calls] == [1, 2]
    assert "[백필 2024-02] 실패: 이후 월 처리를 중단합니다." in output.getvalue()


def make_settings():
    return Settings(
        base_url="https://fcdaum.com",
        accounts=(
            BrandAccount("hanchon", "한촌설렁탕", "h-id", "h-secret"),
            BrandAccount("yuksudang", "육수당", "y-id", "y-secret"),
        ),
        page_size=100,
    )


def collection(report_count=2, issue_count=1, mission_count=3, skipped_report_nos=()):
    return BrandCollection(
        reports=[{"reportNo": index + 1} for index in range(report_count)],
        report_details={},
        issues={index + 1: {"answerNo": index + 1} for index in range(issue_count)},
        missions=[{"missionNo": index + 1} for index in range(mission_count)],
        cutoff_ms=1,
        skipped_report_nos=skipped_report_nos,
    )


class FakeCollector:
    def __init__(self, outcome):
        self.outcome = outcome

    def collect(self, executed_at):
        assert executed_at == EXECUTED_AT
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def make_factories(outcomes):
    calls = []

    def client_factory(account):
        attempt = sum(1 for code in calls if code == account.code)
        calls.append(account.code)
        return (account.code, attempt)

    def collector_factory(client, page_size):
        code, attempt = client
        assert page_size == 100
        return FakeCollector(outcomes[(code, attempt)])

    return calls, client_factory, collector_factory


def test_failed_brand_retries_after_other_brand_finishes():
    outcomes = {
        ("hanchon", 0): ApiError("temporary"),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): collection(),
    }
    calls, client_factory, collector_factory = make_factories(outcomes)

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        output=StringIO(),
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 0
    assert calls == ["hanchon", "yuksudang", "hanchon"]


def test_retry_failure_returns_one_and_names_failed_brand():
    outcomes = {
        ("hanchon", 0): ApiError("first-secret"),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): ApiError("second-secret"),
    }
    _, client_factory, collector_factory = make_factories(outcomes)
    output = StringIO()

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        output=output,
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 1
    text = output.getvalue()
    assert "최종 실패" in text
    assert "한촌설렁탕" in text
    assert "육수당" in text
    assert "ApiError: first-secret" in text
    assert "ApiError: second-secret" in text


def test_success_output_contains_only_brand_counts():
    outcomes = {
        ("hanchon", 0): collection(2, 1, 3),
        ("yuksudang", 0): collection(4, 2, 5),
    }
    _, client_factory, collector_factory = make_factories(outcomes)
    output = StringIO()

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        output=output,
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 0
    text = output.getvalue()
    assert "[한촌설렁탕] 리포트 2건, 문제항목 1건, 품질미션 3건" in text
    assert "[육수당] 리포트 4건, 문제항목 2건, 품질미션 5건" in text
    assert "h-secret" not in text
    assert "y-secret" not in text


def test_success_output_names_reports_skipped_after_detail_http_404():
    outcomes = {
        ("hanchon", 0): collection(skipped_report_nos=(408340, 408341)),
        ("yuksudang", 0): collection(),
    }
    _, client_factory, collector_factory = make_factories(outcomes)
    output = StringIO()

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        output=output,
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 0
    assert "HTTP 404 상세 누락 reportNo: 408340, 408341" in output.getvalue()


def test_explicit_collection_start_is_shown_in_completion_output():
    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
    }
    calls = []

    def client_factory(account):
        calls.append(account.code)
        return account.code

    class ExplicitStartCollector:
        def __init__(self, result):
            self.result = result

        def collect(self, executed_at, *, collection_start):
            assert collection_start == datetime(2026, 1, 1, tzinfo=KST)
            return self.result

    def collector_factory(client, page_size):
        return ExplicitStartCollector(outcomes[(client, 0)])

    output = StringIO()
    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        output=output,
        executed_at=EXECUTED_AT,
        collection_start=datetime(2026, 1, 1, tzinfo=KST),
    )

    assert exit_code == 0
    assert calls == ["hanchon", "yuksudang"]
    assert "2026-01-01 이후" in output.getvalue()


def test_explicit_collection_range_is_forwarded_to_collector():
    start = datetime(2024, 1, 1, tzinfo=KST)
    end = datetime(2024, 2, 1, tzinfo=KST)
    calls = []

    class RangeCollector:
        def collect(self, executed_at, *, collection_start, collection_end):
            calls.append((collection_start, collection_end))
            return collection()

    exit_code = run_all_brands(
        make_settings(),
        client_factory=lambda account: account.code,
        collector_factory=lambda client, page_size: RangeCollector(),
        output=StringIO(),
        executed_at=EXECUTED_AT,
        collection_start=start,
        collection_end=end,
    )

    assert exit_code == 0
    assert calls == [(start, end), (start, end)]


def test_database_failure_retries_brand_after_other_brand():
    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): collection(),
    }
    calls, client_factory, collector_factory = make_factories(outcomes)
    repository_calls = []

    class FakeRepository:
        def __init__(self, account):
            self.account = account

        def save_collection(self, brand_code, result):
            attempt = sum(1 for code in repository_calls if code == brand_code)
            repository_calls.append(brand_code)
            if brand_code == "hanchon" and attempt == 0:
                raise DatabaseError("db-secret")
            empty = BatchStats()
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        repository_factory=lambda account: FakeRepository(account),
        output=StringIO(),
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 0
    assert calls == ["hanchon", "yuksudang", "hanchon"]
    assert repository_calls == ["hanchon", "yuksudang", "hanchon"]


class FakeAuditRepository:
    def __init__(self, events=None, fail=False):
        self.events = events if events is not None else []
        self.fail = fail
        self.started = []
        self.attempts = []
        self.finished = []
        self.closed = False

    def _check(self):
        if self.fail:
            raise AuditError("감사 이력 저장에 실패했습니다.")

    def start_run(self, run_id, scheduled_date, started_at):
        self._check()
        self.started.append((run_id, scheduled_date, started_at))

    def record_attempt(self, attempt):
        self._check()
        self.events.append(f"audit_{attempt.brand_code}_{attempt.attempt_status}")
        self.attempts.append(attempt)

    def finish_run(
        self, run_id, finished_at, run_status, successful_brands, failed_brands
    ):
        self._check()
        self.finished.append(
            (run_id, finished_at, run_status, successful_brands, failed_brands)
        )

    def close(self):
        self.closed = True


def _run_with_audit(outcomes, audit_repository, repository_factory=None):
    if repository_factory is None:
        empty = BatchStats()

        class CommittedRepository:
            def save_collection(self, brand_code, result):
                return CollectionStats(empty, empty, empty)

            def close(self):
                return None

        repository_factory = lambda account: CommittedRepository()
    _, client_factory, collector_factory = make_factories(outcomes)
    output = StringIO()
    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        repository_factory=repository_factory,
        audit_repository_factory=lambda: audit_repository,
        output=output,
        executed_at=EXECUTED_AT,
    )
    return exit_code, output.getvalue()


def test_audit_records_partial_failed_when_hanchon_finally_fails():
    outcomes = {
        ("hanchon", 0): ApiError("first secret"),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): ApiError("second secret"),
    }
    audit_repository = FakeAuditRepository()

    exit_code, _ = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 1
    assert audit_repository.finished[0][2:] == ("PARTIAL_FAILED", 1, 1)
    assert [item.attempt_no for item in audit_repository.attempts] == [1, 1, 2]
    assert audit_repository.attempts[-1].error_category == "API_ERROR"
    assert "secret" not in repr(audit_repository.attempts[-1])


def test_audit_preserves_failed_exit_when_last_attempt_write_is_lost():
    class LastAttemptWriteFailureRepository(FakeAuditRepository):
        def __init__(self):
            super().__init__()
            self.record_attempt_calls = 0

        def record_attempt(self, attempt):
            self.record_attempt_calls += 1
            if attempt.brand_code == "yuksudang" and attempt.attempt_no == 2:
                raise AuditError("감사 최종 시도 저장에 실패했습니다.")
            super().record_attempt(attempt)

    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): ApiError("temporary"),
        ("yuksudang", 1): ApiError("final"),
    }
    audit_repository = LastAttemptWriteFailureRepository()

    exit_code, output = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 1
    assert "[최종 실패] 육수당" in output
    assert audit_repository.record_attempt_calls == 3
    assert [
        (attempt.brand_code, attempt.attempt_no)
        for attempt in audit_repository.attempts
    ] == [("hanchon", 1), ("yuksudang", 1)]
    assert audit_repository.finished[0][2:] == ("ABORTED", 1, 1)
    assert audit_repository.closed is True


def test_audit_records_warning_after_failed_attempt_retries_successfully():
    outcomes = {
        ("hanchon", 0): ApiError("temporary"),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): collection(),
    }
    audit_repository = FakeAuditRepository()

    exit_code, _ = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 0
    assert audit_repository.finished[0][2:] == ("WARNING", 2, 0)


def test_audit_records_failed_when_all_brands_finally_fail():
    outcomes = {
        ("hanchon", 0): ApiError("h1"),
        ("yuksudang", 0): ApiError("y1"),
        ("hanchon", 1): ApiError("h2"),
        ("yuksudang", 1): ApiError("y2"),
    }
    audit_repository = FakeAuditRepository()

    exit_code, _ = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 1
    assert audit_repository.finished[0][2:] == ("FAILED", 0, 2)


def test_success_attempt_is_recorded_only_after_business_commit_returns():
    events = []
    empty = BatchStats()

    class OrderedRepository:
        def save_collection(self, brand_code, result):
            events.append(f"business_commit_{brand_code}")
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
    }
    audit_repository = FakeAuditRepository(events=events)

    exit_code, _ = _run_with_audit(
        outcomes,
        audit_repository,
        repository_factory=lambda account: OrderedRepository(),
    )

    assert exit_code == 0
    assert events == [
        "business_commit_hanchon",
        "audit_hanchon_SUCCESS",
        "business_commit_yuksudang",
        "audit_yuksudang_SUCCESS",
    ]
    assert all(attempt.db_committed for attempt in audit_repository.attempts)


def test_failed_attempt_is_recorded_after_business_rollback():
    events = []
    empty = BatchStats()
    repository_calls = []

    class RollbackRepository:
        def save_collection(self, brand_code, result):
            attempt_no = repository_calls.count(brand_code) + 1
            repository_calls.append(brand_code)
            if brand_code == "hanchon" and attempt_no == 1:
                events.append("business_rollback_hanchon")
                raise DatabaseError("PWD=secret")
            events.append(f"business_commit_{brand_code}")
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
        ("hanchon", 1): collection(),
    }
    audit_repository = FakeAuditRepository(events=events)

    exit_code, _ = _run_with_audit(
        outcomes,
        audit_repository,
        repository_factory=lambda account: RollbackRepository(),
    )

    assert exit_code == 0
    assert events[:2] == [
        "business_rollback_hanchon",
        "audit_hanchon_FAILED",
    ]
    failed_attempt = audit_repository.attempts[0]
    assert failed_attempt.db_committed is False
    assert failed_attempt.api_count == 6
    assert failed_attempt.error_category == "DATABASE_ERROR"
    assert "secret" not in repr(failed_attempt)


def test_audit_records_success_empty_when_all_successful_api_counts_are_zero():
    outcomes = {
        ("hanchon", 0): collection(0, 0, 0),
        ("yuksudang", 0): collection(0, 0, 0),
    }
    audit_repository = FakeAuditRepository()

    exit_code, _ = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 0
    assert audit_repository.finished[0][2:] == ("SUCCESS_EMPTY", 2, 0)
    assert [attempt.attempt_status for attempt in audit_repository.attempts] == [
        "SUCCESS_EMPTY",
        "SUCCESS_EMPTY",
    ]


def test_audit_failure_preserves_existing_output_and_exit_code():
    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
    }
    expected_code, expected_output = _run_with_audit(
        outcomes, FakeAuditRepository()
    )

    actual_code, actual_output = _run_with_audit(
        outcomes, FakeAuditRepository(fail=True)
    )

    assert actual_code == expected_code == 0
    assert actual_output == expected_output


def test_audit_marks_run_aborted_when_one_attempt_write_is_lost():
    class OneAttemptWriteFailureRepository(FakeAuditRepository):
        def __init__(self):
            super().__init__()
            self.record_attempt_calls = 0

        def record_attempt(self, attempt):
            self.record_attempt_calls += 1
            if self.record_attempt_calls == 1:
                raise AuditError("감사 시도 한 건 저장에 실패했습니다.")
            super().record_attempt(attempt)

    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
    }
    audit_repository = OneAttemptWriteFailureRepository()

    exit_code, output = _run_with_audit(outcomes, audit_repository)

    assert exit_code == 0
    assert "[완료]" in output
    assert audit_repository.record_attempt_calls == 2
    assert [attempt.brand_code for attempt in audit_repository.attempts] == [
        "yuksudang"
    ]
    assert audit_repository.finished[0][2:] == ("ABORTED", 2, 0)
    assert audit_repository.closed is True


def test_audit_marks_initialization_failure_failed_and_preserves_exception():
    audit_repository = FakeAuditRepository()
    empty = BatchStats()

    class CommittedRepository:
        def save_collection(self, brand_code, result):
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    def failing_client_factory(account):
        raise RuntimeError("initialization secret")

    with pytest.raises(RuntimeError, match="initialization secret"):
        run_all_brands(
            make_settings(),
            client_factory=failing_client_factory,
            repository_factory=lambda account: CommittedRepository(),
            audit_repository_factory=lambda: audit_repository,
            output=StringIO(),
            executed_at=EXECUTED_AT,
        )

    assert audit_repository.finished[0][2:] == ("FAILED", 0, 1)
    assert audit_repository.attempts[0].error_category == "UNEXPECTED_ERROR"
    assert "secret" not in repr(audit_repository.attempts[0])
    assert audit_repository.closed is True


def test_unexpected_failure_after_success_is_partial_failed_in_audit():
    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): RuntimeError("unexpected secret"),
    }
    audit_repository = FakeAuditRepository()
    empty = BatchStats()

    class CommittedRepository:
        def save_collection(self, brand_code, result):
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    _, client_factory, collector_factory = make_factories(outcomes)
    with pytest.raises(RuntimeError, match="unexpected secret"):
        run_all_brands(
            make_settings(),
            client_factory=client_factory,
            collector_factory=collector_factory,
            repository_factory=lambda account: CommittedRepository(),
            audit_repository_factory=lambda: audit_repository,
            output=StringIO(),
            executed_at=EXECUTED_AT,
        )

    assert audit_repository.finished[0][2:] == ("PARTIAL_FAILED", 1, 1)


def test_audit_marks_unexpected_run_aborted_after_an_attempt_write_is_lost():
    class OneAttemptWriteFailureRepository(FakeAuditRepository):
        def __init__(self):
            super().__init__()
            self.record_attempt_calls = 0

        def record_attempt(self, attempt):
            self.record_attempt_calls += 1
            if self.record_attempt_calls == 1:
                raise AuditError("감사 시도 한 건 저장에 실패했습니다.")
            super().record_attempt(attempt)

    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): RuntimeError("unexpected secret"),
    }
    audit_repository = OneAttemptWriteFailureRepository()
    empty = BatchStats()

    class CommittedRepository:
        def save_collection(self, brand_code, result):
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    _, client_factory, collector_factory = make_factories(outcomes)

    with pytest.raises(RuntimeError, match="unexpected secret"):
        run_all_brands(
            make_settings(),
            client_factory=client_factory,
            collector_factory=collector_factory,
            repository_factory=lambda account: CommittedRepository(),
            audit_repository_factory=lambda: audit_repository,
            output=StringIO(),
            executed_at=EXECUTED_AT,
        )

    assert audit_repository.record_attempt_calls == 2
    assert [attempt.brand_code for attempt in audit_repository.attempts] == [
        "yuksudang"
    ]
    assert audit_repository.finished[0][2:] == ("ABORTED", 1, 1)
    assert audit_repository.closed is True


def test_unexpected_failure_includes_pending_failed_brands_in_run_counts():
    outcomes = {
        ("hanchon", 0): ApiError("temporary"),
        ("yuksudang", 0): RuntimeError("unexpected secret"),
    }
    audit_repository = FakeAuditRepository()
    empty = BatchStats()

    class CommittedRepository:
        def save_collection(self, brand_code, result):
            return CollectionStats(empty, empty, empty)

        def close(self):
            return None

    _, client_factory, collector_factory = make_factories(outcomes)
    with pytest.raises(RuntimeError, match="unexpected secret"):
        run_all_brands(
            make_settings(),
            client_factory=client_factory,
            collector_factory=collector_factory,
            repository_factory=lambda account: CommittedRepository(),
            audit_repository_factory=lambda: audit_repository,
            output=StringIO(),
            executed_at=EXECUTED_AT,
        )

    assert audit_repository.finished[0][2:] == ("FAILED", 0, 2)


def test_audit_is_not_started_without_business_repository():
    outcomes = {
        ("hanchon", 0): collection(),
        ("yuksudang", 0): collection(),
    }
    _, client_factory, collector_factory = make_factories(outcomes)
    factory_calls = []

    exit_code = run_all_brands(
        make_settings(),
        client_factory=client_factory,
        collector_factory=collector_factory,
        audit_repository_factory=lambda: factory_calls.append(True),
        output=StringIO(),
        executed_at=EXECUTED_AT,
    )

    assert exit_code == 0
    assert factory_calls == []


def test_global_initialization_failure_records_attemptless_failed_run():
    audit_repository = FakeAuditRepository()

    _record_initialization_failure(
        executed_at=EXECUTED_AT,
        audit_repository_factory=lambda: audit_repository,
    )

    assert len(audit_repository.started) == 1
    assert audit_repository.attempts == []
    assert audit_repository.finished[0][2:] == ("FAILED", 0, 0)
    assert audit_repository.closed is True


def test_execute_with_daily_log_writes_console_and_kst_dated_file(tmp_path: Path):
    console = StringIO()

    def operation(output, error):
        print("[한촌] 리포트 신규 0/변경 0/동일 172", file=output)
        return 0

    exit_code = execute_with_daily_log(
        operation,
        executed_at=datetime(2026, 7, 23, 9, 20, 55, tzinfo=KST),
        log_dir=tmp_path,
        console=console,
        error_console=StringIO(),
        elapsed_seconds=lambda: 78.0,
    )

    assert exit_code == 0
    log_path = tmp_path / "fcdaum_2026-07-23.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "2026-07-23 09:20:55 [START]" in log_text
    assert "[한촌] 리포트 신규 0/변경 0/동일 172" in log_text
    assert "[SUCCESS] 종료 코드 0 (소요 78.0초)" in log_text
    assert "[한촌] 리포트 신규 0/변경 0/동일 172" in console.getvalue()


def test_execute_with_daily_log_appends_same_day_runs(tmp_path: Path):
    run_at = datetime(2026, 7, 23, 9, 20, 55, tzinfo=KST)

    def operation(output, error):
        print("수집 실행", file=output)
        return 0

    for _ in range(2):
        execute_with_daily_log(
            operation,
            executed_at=run_at,
            log_dir=tmp_path,
            console=StringIO(),
            error_console=StringIO(),
            elapsed_seconds=lambda: 1.0,
        )

    log_text = (tmp_path / "fcdaum_2026-07-23.log").read_text(encoding="utf-8")
    assert log_text.count("[START]") == 2
    assert log_text.count("수집 실행") == 2


def test_execute_with_daily_log_records_unhandled_exception(tmp_path: Path):
    def operation(output, error):
        raise RuntimeError("unexpected failure")

    with pytest.raises(RuntimeError, match="unexpected failure"):
        execute_with_daily_log(
            operation,
            executed_at=datetime(2026, 7, 23, 9, 20, 55, tzinfo=KST),
            log_dir=tmp_path,
            console=StringIO(),
            error_console=StringIO(),
            elapsed_seconds=lambda: 2.5,
        )

    log_text = (tmp_path / "fcdaum_2026-07-23.log").read_text(encoding="utf-8")
    assert "[ERROR] RuntimeError: unexpected failure" in log_text
    assert "[FAILURE] 비정상 종료 (소요 2.5초)" in log_text
