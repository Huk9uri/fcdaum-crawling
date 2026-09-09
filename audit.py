"""FC다움 수집 실행의 비민감 감사 이력을 독립 트랜잭션으로 저장한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from config import ConfigError
from db_config import DatabaseConfigError, DatabaseSettings
from fnb_client import ApiError
from mssql_repository import DatabaseError


class AuditError(RuntimeError):
    """감사 DB 연결 또는 쓰기 실패를 원문 없이 나타낸다."""


ERROR_CATEGORIES = frozenset(
    {
        "API_ERROR",
        "DATABASE_ERROR",
        "INITIALIZATION_ERROR",
        "INVALID_DATA",
        "UNEXPECTED_ERROR",
    }
)


def sanitize_error_category(error: BaseException | str | None) -> str | None:
    """오류 메시지 대신 제한된 분류만 반환한다."""
    if error is None:
        return None
    if isinstance(error, str):
        return error if error in ERROR_CATEGORIES else "UNEXPECTED_ERROR"
    if isinstance(error, ApiError):
        return "API_ERROR"
    if isinstance(error, DatabaseError):
        return "DATABASE_ERROR"
    if isinstance(error, (ConfigError, DatabaseConfigError)):
        return "INITIALIZATION_ERROR"
    if isinstance(error, ValueError):
        return "INVALID_DATA"
    return "UNEXPECTED_ERROR"


def determine_run_status(
    *,
    successful_brands: int,
    failed_brands: int,
    had_retry: bool,
    api_count: int,
    initialization_failed: bool = False,
) -> str:
    """최종 브랜드 결과를 모니터링 공통 상태 우선순위로 집계한다."""
    if initialization_failed or (failed_brands > 0 and successful_brands == 0):
        return "FAILED"
    if failed_brands > 0:
        return "PARTIAL_FAILED"
    if had_retry:
        return "WARNING"
    if api_count == 0:
        return "SUCCESS_EMPTY"
    return "SUCCESS"


@dataclass(frozen=True)
class AuditAttempt:
    run_id: UUID
    brand_code: str
    brand_name: str
    attempt_no: int
    started_at: datetime
    finished_at: datetime
    attempt_status: str
    api_count: int
    report_inserted_count: int
    report_changed_count: int
    report_unchanged_count: int
    issue_inserted_count: int
    issue_changed_count: int
    issue_unchanged_count: int
    mission_inserted_count: int
    mission_changed_count: int
    mission_unchanged_count: int
    db_committed: bool
    error_category: str | None


def connect_audit_repository(settings: DatabaseSettings) -> "AuditRepository":
    """업무 적재 연결과 분리된 감사 전용 연결을 생성한다."""
    try:
        import pyodbc
    except ImportError as exc:
        raise AuditError("감사 DB 드라이버를 사용할 수 없습니다.") from exc

    if settings.driver not in pyodbc.drivers():
        raise AuditError("감사 DB 드라이버를 사용할 수 없습니다.")
    try:
        connection = pyodbc.connect(
            settings.connection_string(), autocommit=False, timeout=10
        )
    except pyodbc.Error as exc:
        raise AuditError("감사 DB에 연결하지 못했습니다.") from exc
    # 모니터링 adapter와 배포 SQL이 고정 조회하는 감사 스키마입니다.
    return AuditRepository(connection, schema="dbo")


class AuditRepository:
    """각 감사 쓰기를 즉시 독립 커밋하는 MSSQL 저장소."""

    def __init__(self, connection: Any, schema: str = "dbo"):
        self.connection = connection
        self.schema = schema

    def _table(self, name: str) -> str:
        return f"[{self.schema}].[{name}]"

    def _write(self, sql: str, parameters: tuple[object, ...]) -> None:
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql, *parameters)
            self.connection.commit()
        except Exception as exc:
            self.connection.rollback()
            raise AuditError("감사 이력 저장에 실패했습니다.") from exc
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def start_run(
        self, run_id: UUID, scheduled_date: date, started_at: datetime
    ) -> None:
        sql = f"""INSERT INTO {self._table('FC_DAUM_COLLECTION_RUN')} (
            [RunId], [ScheduledDate], [StartedAt], [FinishedAt], [RunStatus],
            [SuccessfulBrands], [FailedBrands]
        ) VALUES (?, ?, ?, NULL, 'RUNNING', 0, 0)"""
        self._write(sql, (run_id, scheduled_date, started_at))

    def record_attempt(self, attempt: AuditAttempt) -> None:
        error_category = sanitize_error_category(attempt.error_category)
        sql = f"""INSERT INTO {self._table('FC_DAUM_COLLECTION_ATTEMPT')} (
            [RunId], [BrandCode], [BrandName], [AttemptNo], [StartedAt],
            [FinishedAt], [AttemptStatus], [ApiCount],
            [ReportInsertedCount], [ReportChangedCount], [ReportUnchangedCount],
            [IssueInsertedCount], [IssueChangedCount], [IssueUnchangedCount],
            [MissionInsertedCount], [MissionChangedCount], [MissionUnchangedCount],
            [DbCommitted], [ErrorCategory]
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        self._write(
            sql,
            (
                attempt.run_id,
                attempt.brand_code,
                attempt.brand_name,
                attempt.attempt_no,
                attempt.started_at,
                attempt.finished_at,
                attempt.attempt_status,
                attempt.api_count,
                attempt.report_inserted_count,
                attempt.report_changed_count,
                attempt.report_unchanged_count,
                attempt.issue_inserted_count,
                attempt.issue_changed_count,
                attempt.issue_unchanged_count,
                attempt.mission_inserted_count,
                attempt.mission_changed_count,
                attempt.mission_unchanged_count,
                attempt.db_committed,
                error_category,
            ),
        )

    def finish_run(
        self,
        run_id: UUID,
        finished_at: datetime,
        run_status: str,
        successful_brands: int,
        failed_brands: int,
    ) -> None:
        sql = f"""UPDATE {self._table('FC_DAUM_COLLECTION_RUN')}
        SET [FinishedAt] = ?, [RunStatus] = ?,
            [SuccessfulBrands] = ?, [FailedBrands] = ?
        WHERE [RunId] = ?"""
        self._write(
            sql,
            (
                finished_at,
                run_status,
                successful_brands,
                failed_brands,
                run_id,
            ),
        )

    def close(self) -> None:
        self.connection.close()
