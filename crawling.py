from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, TextIO
from uuid import UUID, uuid4

from audit import (
    AuditAttempt,
    connect_audit_repository,
    determine_run_status,
    sanitize_error_category,
)
from collector import KST, BrandCollection, MonthlyCollector
from config import BrandAccount, ConfigError, Settings, load_settings
from db_config import DatabaseConfigError, load_database_settings
from fnb_client import ApiError, FnbClient
from mssql_repository import (
    BatchStats,
    CollectionStats,
    DatabaseError,
    connect_repository,
)


class TeeOutput:
    """Write the same text to each configured stream."""

    def __init__(self, *streams: TextIO):
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def daily_log_path(executed_at: datetime, log_dir: Path) -> Path:
    if executed_at.tzinfo is None:
        raise ValueError("executed_at에는 시간대 정보가 필요합니다.")
    return log_dir / f"fcdaum_{executed_at.astimezone(KST):%Y-%m-%d}.log"


def execute_with_daily_log(
    operation: Callable[[TextIO, TextIO], int],
    *,
    executed_at: datetime,
    log_dir: Path = Path("logs"),
    console: TextIO | None = None,
    error_console: TextIO | None = None,
    elapsed_seconds: Callable[[], float] | None = None,
) -> int:
    """Run one collection operation and append its outcome to a KST daily log."""
    console = console or sys.stdout
    error_console = error_console or sys.stderr
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = daily_log_path(executed_at, log_dir)
    started_tick = perf_counter()

    def duration() -> float:
        if elapsed_seconds is not None:
            return elapsed_seconds()
        return perf_counter() - started_tick

    with log_path.open("a", encoding="utf-8", newline="") as log_file:
        output = TeeOutput(console, log_file)
        errors = TeeOutput(error_console, log_file)
        print(
            f"{executed_at.astimezone(KST):%Y-%m-%d %H:%M:%S} "
            "[START] FC다움 수집 시작",
            file=output,
        )
        try:
            exit_code = operation(output, errors)
        except Exception as exc:
            print(f"[ERROR] {type(exc).__name__}: {exc}", file=errors)
            print(f"[FAILURE] 비정상 종료 (소요 {duration():.1f}초)", file=errors)
            errors.flush()
            raise

        result = "SUCCESS" if exit_code == 0 else "FAILURE"
        print(
            f"[{result}] 종료 코드 {exit_code} (소요 {duration():.1f}초)",
            file=output if exit_code == 0 else errors,
        )
        output.flush()
        errors.flush()
        return exit_code


def parse_collection_start_date(value: str, executed_at: datetime) -> datetime:
    if executed_at.tzinfo is None:
        raise ValueError("executed_at에는 시간대 정보가 필요합니다.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--from-date는 YYYY-MM-DD 형식이어야 합니다.") from exc
    collection_start = datetime.combine(parsed, time.min, tzinfo=KST)
    if collection_start > executed_at.astimezone(KST):
        raise ValueError("--from-date는 실행일 이후일 수 없습니다.")
    return collection_start


def parse_backfill_range(
    from_value: str | None,
    to_value: str | None,
    executed_at: datetime,
    *,
    from_date: str | None = None,
) -> tuple[datetime, datetime]:
    if from_date and (from_value or to_value):
        raise ValueError("--from-date와 백필 옵션은 함께 사용할 수 없습니다.")
    if not from_value or not to_value:
        raise ValueError("--backfill-from과 --backfill-to는 함께 입력해야 합니다.")
    if executed_at.tzinfo is None:
        raise ValueError("executed_at에는 시간대 정보가 필요합니다.")

    try:
        start_date = datetime.strptime(from_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--backfill-from은 YYYY-MM-DD 형식이어야 합니다.") from exc
    try:
        end_date = datetime.strptime(to_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--backfill-to는 YYYY-MM-DD 형식이어야 합니다.") from exc

    start = datetime.combine(start_date, time.min, tzinfo=KST)
    end = datetime.combine(end_date, time.min, tzinfo=KST)
    if start > end:
        raise ValueError("백필 시작일은 종료일보다 늦을 수 없습니다.")
    if end.date() > executed_at.astimezone(KST).date():
        raise ValueError("--backfill-to는 실행일 이후일 수 없습니다.")
    return start, end


def build_monthly_ranges(
    start: datetime, end_inclusive: datetime
) -> list[tuple[datetime, datetime]]:
    if start.tzinfo is None or end_inclusive.tzinfo is None:
        raise ValueError("백필 시작일과 종료일에는 시간대 정보가 필요합니다.")
    if start > end_inclusive:
        raise ValueError("백필 시작일은 종료일보다 늦을 수 없습니다.")

    overall_end = end_inclusive + timedelta(days=1)
    ranges: list[tuple[datetime, datetime]] = []
    current = start
    while current < overall_end:
        if current.month == 12:
            next_month = datetime(current.year + 1, 1, 1, tzinfo=current.tzinfo)
        else:
            next_month = datetime(
                current.year, current.month + 1, 1, tzinfo=current.tzinfo
            )
        segment_end = min(next_month, overall_end)
        ranges.append((current, segment_end))
        current = segment_end
    return ranges


def run_monthly_backfill(
    ranges: list[tuple[datetime, datetime]],
    *,
    run_range: Callable[[datetime, datetime], int],
    output: TextIO = sys.stdout,
) -> int:
    for start, end_exclusive in ranges:
        label = f"{start:%Y-%m}"
        display_end = end_exclusive - timedelta(days=1)
        print(
            f"[백필 {label}] 시작: {start:%Y-%m-%d} ~ {display_end:%Y-%m-%d}",
            file=output,
        )
        exit_code = run_range(start, end_exclusive)
        if exit_code != 0:
            print(
                f"[백필 {label}] 실패: 이후 월 처리를 중단합니다.",
                file=output,
            )
            return 1
        print(f"[백필 {label}] 완료", file=output)

    if ranges:
        overall_start = ranges[0][0]
        overall_end = ranges[-1][1] - timedelta(days=1)
        print(
            f"[백필 완료] {len(ranges)}개월, "
            f"{overall_start:%Y-%m-%d} ~ {overall_end:%Y-%m-%d}",
            file=output,
        )
    return 0


def _print_collection(
    account: BrandAccount,
    result: BrandCollection,
    output: TextIO,
    *,
    retried: bool,
    db_stats: CollectionStats | None = None,
) -> None:
    phase = "재시도 성공" if retried else "성공"
    print(
        f"[{account.name}] 리포트 {len(result.reports)}건, "
        f"문제항목 {len(result.issues)}건, "
        f"품질미션 {len(result.missions)}건 ({phase})",
        file=output,
    )
    if result.skipped_report_nos:
        report_nos = ", ".join(str(value) for value in result.skipped_report_nos)
        print(
            f"[{account.name}] HTTP 404 상세 누락 reportNo: {report_nos} "
            "(해당 리포트만 건너뜀)",
            file=output,
        )
    if db_stats is not None:
        print(
            f"[{account.name}] DB 반영: "
            f"리포트 신규 {db_stats.reports.inserted}/변경 {db_stats.reports.updated}/동일 {db_stats.reports.unchanged}, "
            f"문제항목 신규 {db_stats.issues.inserted}/변경 {db_stats.issues.updated}/동일 {db_stats.issues.unchanged}, "
            f"품질미션 신규 {db_stats.missions.inserted}/변경 {db_stats.missions.updated}/동일 {db_stats.missions.unchanged}",
            file=output,
        )


def _collect_and_save(
    account: BrandAccount,
    settings: Settings,
    run_at: datetime,
    client_factory: Callable[[BrandAccount], object],
    collector_factory: Callable[[object, int], object],
    repository_factory: Callable[[BrandAccount], object] | None,
    collection_start: datetime | None,
    collection_end: datetime | None,
    collection_observer: Callable[[BrandCollection], None] | None = None,
) -> tuple[BrandCollection, CollectionStats | None]:
    collector = collector_factory(client_factory(account), settings.page_size)
    collection_kwargs = {}
    if collection_start is not None:
        collection_kwargs["collection_start"] = collection_start
    if collection_end is not None:
        collection_kwargs["collection_end"] = collection_end
    result = collector.collect(run_at, **collection_kwargs)
    if collection_observer is not None:
        collection_observer(result)
    if repository_factory is None:
        return result, None

    repository = repository_factory(account)
    try:
        stats = repository.save_collection(account.code, result)
    finally:
        repository.close()
    return result, stats


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _api_count(result: BrandCollection | None) -> int:
    if result is None:
        return 0
    return len(result.reports) + len(result.issues) + len(result.missions)


def _safe_audit_call(repository: object | None, method: str, *args: object) -> bool:
    """감사 장애를 업무 처리와 기존 출력 계약에서 격리한다."""
    if repository is None:
        return False
    try:
        getattr(repository, method)(*args)
    except Exception:
        return False
    return True


def _audit_attempt(
    *,
    run_id: UUID,
    account: BrandAccount,
    attempt_no: int,
    started_at: datetime,
    finished_at: datetime,
    result: BrandCollection | None,
    stats: CollectionStats | None,
    error: BaseException | None,
) -> AuditAttempt:
    empty = BatchStats()
    reports = stats.reports if stats is not None else empty
    issues = stats.issues if stats is not None else empty
    missions = stats.missions if stats is not None else empty
    api_count = _api_count(result)
    succeeded = error is None
    return AuditAttempt(
        run_id=run_id,
        brand_code=account.code,
        brand_name=account.name,
        attempt_no=attempt_no,
        started_at=started_at,
        finished_at=finished_at,
        attempt_status=(
            "SUCCESS_EMPTY" if succeeded and api_count == 0
            else "SUCCESS" if succeeded
            else "FAILED"
        ),
        api_count=api_count,
        report_inserted_count=reports.inserted,
        report_changed_count=reports.updated,
        report_unchanged_count=reports.unchanged,
        issue_inserted_count=issues.inserted,
        issue_changed_count=issues.updated,
        issue_unchanged_count=issues.unchanged,
        mission_inserted_count=missions.inserted,
        mission_changed_count=missions.updated,
        mission_unchanged_count=missions.unchanged,
        db_committed=(stats.db_committed if stats is not None else False),
        error_category=sanitize_error_category(error),
    )


def _record_initialization_failure(
    *,
    executed_at: datetime,
    audit_repository_factory: Callable[[], object],
) -> None:
    """업무 시도 전 초기화 실패를 attempt 없는 FAILED 실행으로 남긴다."""
    try:
        repository = audit_repository_factory()
    except Exception:
        return
    run_id = uuid4()
    started_at = _utc_naive_now()
    if not _safe_audit_call(
        repository,
        "start_run",
        run_id,
        executed_at.astimezone(KST).date(),
        started_at,
    ):
        _safe_audit_call(repository, "close")
        return
    _safe_audit_call(
        repository,
        "finish_run",
        run_id,
        _utc_naive_now(),
        "FAILED",
        0,
        0,
    )
    _safe_audit_call(repository, "close")


def run_all_brands(
    settings: Settings,
    *,
    client_factory: Callable[[BrandAccount], object],
    collector_factory: Callable[[object, int], object] = MonthlyCollector,
    repository_factory: Callable[[BrandAccount], object] | None = None,
    audit_repository_factory: Callable[[], object] | None = None,
    output: TextIO = sys.stdout,
    executed_at: datetime | None = None,
    collection_start: datetime | None = None,
    collection_end: datetime | None = None,
    audit_clock: Callable[[], datetime] = _utc_naive_now,
) -> int:
    run_at = executed_at or datetime.now(KST)
    run_id = uuid4()
    run_started_at = audit_clock()
    audit_repository = None
    if audit_repository_factory is not None and repository_factory is not None:
        try:
            audit_repository = audit_repository_factory()
        except Exception:
            audit_repository = None
    if audit_repository is not None and not _safe_audit_call(
        audit_repository,
        "start_run",
        run_id,
        run_at.astimezone(KST).date(),
        run_started_at,
    ):
        _safe_audit_call(audit_repository, "close")
        audit_repository = None

    failed: list[BrandAccount] = []
    attempt_numbers = {account.code: 0 for account in settings.accounts}
    successful_api_count = 0
    successful_brand_codes: set[str] = set()
    audit_attempts_complete = True

    def record_audit_attempt(attempt: AuditAttempt) -> None:
        nonlocal audit_attempts_complete
        if audit_repository is None:
            return
        if not _safe_audit_call(audit_repository, "record_attempt", attempt):
            audit_attempts_complete = False

    def execute_attempt(
        account: BrandAccount,
    ) -> tuple[BrandCollection, CollectionStats | None]:
        nonlocal audit_repository, successful_api_count
        attempt_numbers[account.code] += 1
        attempt_no = attempt_numbers[account.code]
        attempt_started_at = audit_clock()
        captured_collection: list[BrandCollection] = []
        try:
            result, db_stats = _collect_and_save(
                account,
                settings,
                run_at,
                client_factory,
                collector_factory,
                repository_factory,
                collection_start,
                collection_end,
                captured_collection.append,
            )
        except (ApiError, DatabaseError) as exc:
            record_audit_attempt(
                _audit_attempt(
                    run_id=run_id,
                    account=account,
                    attempt_no=attempt_no,
                    started_at=attempt_started_at,
                    finished_at=audit_clock(),
                    result=captured_collection[0] if captured_collection else None,
                    stats=None,
                    error=exc,
                ),
            )
            raise
        except Exception as exc:
            record_audit_attempt(
                _audit_attempt(
                    run_id=run_id,
                    account=account,
                    attempt_no=attempt_no,
                    started_at=attempt_started_at,
                    finished_at=audit_clock(),
                    result=captured_collection[0] if captured_collection else None,
                    stats=None,
                    error=exc,
                ),
            )
            completed_successes = len(successful_brand_codes)
            pending_failed_codes = {
                failed_account.code
                for failed_account in failed
                if failed_account.code not in successful_brand_codes
            }
            pending_failed_codes.add(account.code)
            failed_brands = len(pending_failed_codes)
            run_status = determine_run_status(
                successful_brands=completed_successes,
                failed_brands=failed_brands,
                had_retry=bool(failed),
                api_count=successful_api_count,
            )
            if not audit_attempts_complete:
                run_status = "ABORTED"
            _safe_audit_call(
                audit_repository,
                "finish_run",
                run_id,
                audit_clock(),
                run_status,
                completed_successes,
                failed_brands,
            )
            _safe_audit_call(audit_repository, "close")
            audit_repository = None
            raise

        successful_api_count += _api_count(result)
        successful_brand_codes.add(account.code)
        record_audit_attempt(
            _audit_attempt(
                run_id=run_id,
                account=account,
                attempt_no=attempt_no,
                started_at=attempt_started_at,
                finished_at=audit_clock(),
                result=result,
                stats=db_stats,
                error=None,
            ),
        )
        return result, db_stats

    for account in settings.accounts:
        try:
            result, db_stats = execute_attempt(account)
        except (ApiError, DatabaseError) as exc:
            failed.append(account)
            print(
                f"[{account.name}] 1차 실패: "
                f"{type(exc).__name__}: {exc} "
                "다른 브랜드 처리 후 재시도합니다.",
                file=output,
            )
            continue
        _print_collection(
            account, result, output, retried=False, db_stats=db_stats
        )

    final_failed: list[BrandAccount] = []
    for account in failed:
        try:
            result, db_stats = execute_attempt(account)
        except (ApiError, DatabaseError) as exc:
            final_failed.append(account)
            print(
                f"[{account.name}] 재시도 실패: "
                f"{type(exc).__name__}: {exc}",
                file=output,
            )
            continue
        _print_collection(
            account, result, output, retried=True, db_stats=db_stats
        )

    successful_brands = len(settings.accounts) - len(final_failed)
    failed_brands = len(final_failed)
    run_status = determine_run_status(
        successful_brands=successful_brands,
        failed_brands=failed_brands,
        had_retry=bool(failed),
        api_count=successful_api_count,
    )
    if not audit_attempts_complete:
        run_status = "ABORTED"
    _safe_audit_call(
        audit_repository,
        "finish_run",
        run_id,
        audit_clock(),
        run_status,
        successful_brands,
        failed_brands,
    )
    _safe_audit_call(audit_repository, "close")

    if final_failed:
        names = ", ".join(account.name for account in final_failed)
        print(f"[최종 실패] {names}", file=output)
        return 1

    if collection_start is not None and collection_end is not None:
        display_end = collection_end.astimezone(KST) - timedelta(days=1)
        scope = (
            f"{collection_start.astimezone(KST):%Y-%m-%d} ~ "
            f"{display_end:%Y-%m-%d}"
        )
    elif collection_start is not None:
        scope = f"{collection_start.astimezone(KST):%Y-%m-%d} 이후"
    else:
        scope = "최근 1개월"
    print(f"[완료] 모든 브랜드의 {scope} 수집 검증이 성공했습니다.", file=output)
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-date",
        help="이번 실행의 수집 시작일(KST, YYYY-MM-DD)",
    )
    parser.add_argument(
        "--backfill-from",
        help="월별 백필 시작일(KST, YYYY-MM-DD)",
    )
    parser.add_argument(
        "--backfill-to",
        help="월별 백필 종료일(KST, YYYY-MM-DD, 해당 날짜 포함)",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    run_at = datetime.now(KST)

    def run(output: TextIO, error_output: TextIO) -> int:
        try:
            backfill_range = None
            collection_start = None
            if args.backfill_from or args.backfill_to:
                backfill_range = parse_backfill_range(
                    args.backfill_from,
                    args.backfill_to,
                    run_at,
                    from_date=args.from_date,
                )
            elif args.from_date:
                collection_start = parse_collection_start_date(
                    args.from_date, run_at
                )
            settings = load_settings()
            database_settings = load_database_settings()
        except (ConfigError, DatabaseConfigError, ValueError) as exc:
            if not isinstance(exc, DatabaseConfigError):
                try:
                    initialization_database_settings = load_database_settings()
                except DatabaseConfigError:
                    pass
                else:
                    _record_initialization_failure(
                        executed_at=run_at,
                        audit_repository_factory=lambda: connect_audit_repository(
                            initialization_database_settings
                        ),
                    )
            print(f"[설정 오류] {exc}", file=error_output)
            return 2

        if backfill_range is not None:
            start, end_inclusive = backfill_range
            ranges = build_monthly_ranges(start, end_inclusive)

            def run_range(
                range_start: datetime, range_end: datetime
            ) -> int:
                return run_all_brands(
                    settings,
                    client_factory=lambda account: FnbClient(settings, account),
                    repository_factory=lambda account: connect_repository(
                        database_settings
                    ),
                    audit_repository_factory=lambda: connect_audit_repository(
                        database_settings
                    ),
                    output=output,
                    executed_at=run_at,
                    collection_start=range_start,
                    collection_end=range_end,
                )

            return run_monthly_backfill(
                ranges, run_range=run_range, output=output
            )

        return run_all_brands(
            settings,
            client_factory=lambda account: FnbClient(settings, account),
            repository_factory=lambda account: connect_repository(database_settings),
            audit_repository_factory=lambda: connect_audit_repository(
                database_settings
            ),
            output=output,
            executed_at=run_at,
            collection_start=collection_start,
        )

    return execute_with_daily_log(run, executed_at=run_at)


if __name__ == "__main__":
    raise SystemExit(main())
