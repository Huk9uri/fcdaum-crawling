from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from typing import Any

from collector import BrandCollection
from db_config import DatabaseSettings


class DatabaseError(RuntimeError):
    """Raised for MSSQL connection or transactional write failures."""


def connect_repository(settings: DatabaseSettings) -> "MssqlRepository":
    try:
        import pyodbc
    except ImportError as exc:
        raise DatabaseError("pyodbc가 설치되어 있지 않습니다.") from exc

    installed = pyodbc.drivers()
    if settings.driver not in installed:
        available = ", ".join(installed) if installed else "없음"
        raise DatabaseError(
            f"MSSQL ODBC 드라이버를 찾지 못했습니다. 설치된 드라이버: {available}"
        )
    try:
        connection = pyodbc.connect(
            settings.connection_string(), autocommit=False, timeout=10
        )
    except pyodbc.Error as exc:
        raise DatabaseError("MSSQL 서버에 연결하지 못했습니다.") from exc
    return MssqlRepository(connection, schema=settings.schema)


def epoch_ms_to_utc_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Epoch 밀리초 값은 숫자여야 합니다.")
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


MISSION_STATUS_NAMES = {
    "DOING": "수행 전",
    "ACTION": "제출 완료",
    "COMPLETE": "완료됨",
    "REDOING": "재수행 요청",
}

BRAND_NAMES = {
    "hanchon": "한촌",
    "yuksudang": "육수당",
}


def translate_brand_name(brand_code: str) -> str:
    return BRAND_NAMES.get(brand_code, brand_code)


def normalize_store_name(
    brand_code: str, store_name: str | None
) -> str | None:
    if store_name is None:
        return None
    normalized = store_name.strip()
    if not normalized:
        return ""

    if brand_code == "hanchon":
        normalized = re.sub(r"^한촌설렁탕\s*", "", normalized)
        normalized = re.sub(r"\s*\([^()]*\)\s*$", "", normalized).strip()
        if normalized and not normalized.endswith("점"):
            normalized += "점"
        return normalized

    if brand_code == "yuksudang":
        normalized = re.sub(r"^육수당\s*", "", normalized).strip()
        if not normalized:
            return ""
        if not normalized.endswith("점"):
            normalized += "점"
        return f"육수당 {normalized}"

    return normalized


def translate_mission_status(value: object) -> object:
    if value is None:
        return None
    return MISSION_STATUS_NAMES.get(value, value)


def aggregate_expected_sanctions(
    issues: list[dict[str, Any]],
) -> dict[int, tuple[Decimal, int]]:
    totals: dict[int, tuple[Decimal, int]] = {}
    for issue in issues:
        report_no = issue.get("reportNo")
        if isinstance(report_no, bool) or not isinstance(report_no, int):
            raise ValueError("문제항목에 유효한 reportNo가 없습니다.")
        fine_total, suspension_total = totals.get(
            report_no, (Decimal("0"), 0)
        )
        fine_amount = _decimal(issue.get("fine")) or Decimal("0")
        suspension_days = issue.get("suspension")
        totals[report_no] = (
            fine_total + fine_amount,
            suspension_total + (int(suspension_days) if suspension_days else 0),
        )
    return totals


def map_report(
    brand_code: str,
    item: dict[str, Any],
    *,
    expected_sanctions: tuple[Decimal, int] | None = None,
) -> dict[str, object]:
    mapped = {
        "brand_code": brand_code,
        "brand_name": translate_brand_name(brand_code),
        "report_no": item.get("reportNo"),
        "store_name": normalize_store_name(brand_code, item.get("storeNm")),
        "visit_date": epoch_ms_to_utc_datetime(item.get("visitDate")),
        "reg_date": epoch_ms_to_utc_datetime(item.get("regDate")),
        "source_updated_at": epoch_ms_to_utc_datetime(item.get("updateDate")),
        "grade": item.get("grade"),
        "percentage_score": _decimal(item.get("percentageScore")),
        "inspector_name": item.get("userNm"),
    }
    if expected_sanctions is not None:
        mapped["expected_fine_amount"] = expected_sanctions[0]
        mapped["expected_suspension_days"] = expected_sanctions[1]
    return mapped


def map_issue(brand_code: str, item: dict[str, Any]) -> dict[str, object]:
    return {
        "brand_code": brand_code,
        "brand_name": translate_brand_name(brand_code),
        "answer_no": item.get("answerNo"),
        "report_no": item.get("reportNo"),
        "store_name": normalize_store_name(brand_code, item.get("storeNm")),
        "visit_date": epoch_ms_to_utc_datetime(item.get("reportVisitDate")),
        "top_category_name": item.get("topCatNm"),
        "category_name": item.get("catNm"),
        "question_title": item.get("quesTitle"),
        "checked_value": item.get("checkedValue"),
        "fine_amount": _decimal(item.get("fine")),
        "suspension_days": item.get("suspension"),
    }


def map_mission(brand_code: str, item: dict[str, Any]) -> dict[str, object]:
    return {
        "brand_code": brand_code,
        "brand_name": translate_brand_name(brand_code),
        "mission_no": item.get("missionNo"),
        "report_no": item.get("reportNo"),
        "store_name": normalize_store_name(brand_code, item.get("storeNm")),
        "sent_date": epoch_ms_to_utc_datetime(item.get("startDate")),
        "due_date": epoch_ms_to_utc_datetime(item.get("endDate")),
        "mission_status": translate_mission_status(item.get("status")),
        "description": item.get("description"),
        "title": item.get("title"),
        "sv_name": item.get("startUserNm"),
        "owner_submitted_at": epoch_ms_to_utc_datetime(item.get("actionDate")),
        "sv_completed_at": epoch_ms_to_utc_datetime(item.get("completeDate")),
    }


@dataclass(frozen=True)
class TableSpec:
    table: str
    key_column: str
    columns: tuple[str, ...]

    @property
    def compared_columns(self) -> tuple[str, ...]:
        return tuple(
            column
            for column in self.columns
            if column not in ("brand_code", self.key_column)
        )


@dataclass(frozen=True)
class BatchStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def combine_batch_stats(*stats: BatchStats) -> BatchStats:
    return BatchStats(
        inserted=sum(item.inserted for item in stats),
        updated=sum(item.updated for item in stats),
        unchanged=sum(item.unchanged for item in stats),
    )


@dataclass(frozen=True)
class CollectionStats:
    reports: BatchStats
    issues: BatchStats
    missions: BatchStats
    db_committed: bool = True


REPORT_BASE_SPEC = TableSpec(
    "fc_daum_qsc_report",
    "report_no",
    (
        "brand_code", "brand_name", "report_no", "store_name", "visit_date",
        "reg_date", "source_updated_at", "grade",
        "percentage_score", "inspector_name",
    ),
)
REPORT_SPEC = TableSpec(
    "fc_daum_qsc_report",
    "report_no",
    REPORT_BASE_SPEC.columns
    + ("expected_fine_amount", "expected_suspension_days"),
)
ISSUE_SPEC = TableSpec(
    "fc_daum_qsc_report_issue",
    "answer_no",
    (
        "brand_code", "brand_name", "answer_no", "report_no", "store_name", "visit_date",
        "top_category_name", "category_name", "question_title", "checked_value",
        "fine_amount", "suspension_days",
    ),
)
MISSION_SPEC = TableSpec(
    "fc_daum_mission",
    "mission_no",
    (
        "brand_code", "brand_name", "mission_no", "report_no", "store_name", "sent_date",
        "due_date", "mission_status", "description", "title", "sv_name",
        "owner_submitted_at", "sv_completed_at",
    ),
)


def _qualified(schema: str, table: str) -> str:
    return f"[{schema}].[{table}]"


def build_insert_sql(schema: str, spec: TableSpec) -> str:
    columns = ", ".join(f"[{column}]" for column in spec.columns)
    placeholders = ", ".join("?" for _ in spec.columns)
    return f"INSERT INTO {_qualified(schema, spec.table)} ({columns}) VALUES ({placeholders})"


def build_update_sql(schema: str, spec: TableSpec) -> str:
    assignments = ", ".join(
        f"[{column}] = ?" for column in spec.compared_columns
    )
    return (
        f"UPDATE {_qualified(schema, spec.table)} SET {assignments}, "
        "[updated_at] = SYSUTCDATETIME() "
        f"WHERE [brand_code] = ? AND [{spec.key_column}] = ?"
    )


def partition_rows(
    rows: list[dict[str, object]],
    existing: dict[object, dict[str, object]],
    spec: TableSpec,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    new_rows: list[dict[str, object]] = []
    changed_rows: list[dict[str, object]] = []
    unchanged_count = 0
    for row in rows:
        key = row[spec.key_column]
        current = existing.get(key)
        if current is None:
            new_rows.append(row)
        elif any(row[column] != current[column] for column in spec.compared_columns):
            changed_rows.append(row)
        else:
            unchanged_count += 1
    return new_rows, changed_rows, unchanged_count


class MssqlRepository:
    def __init__(self, connection: Any, schema: str = "dbo"):
        self.connection = connection
        self.schema = schema

    def save_collection(
        self, brand_code: str, collection: BrandCollection
    ) -> CollectionStats:
        cursor = self.connection.cursor()
        try:
            issue_items = list(collection.issues.values())
            expected_sanctions = aggregate_expected_sanctions(issue_items)
            scanned_reports = []
            support_reports = []
            for item in collection.reports:
                report_no = item.get("reportNo")
                if report_no in collection.issue_scanned_report_nos:
                    scanned_reports.append(
                        map_report(
                            brand_code,
                            item,
                            expected_sanctions=expected_sanctions.get(
                                report_no, (Decimal("0"), 0)
                            ),
                        )
                    )
                else:
                    support_reports.append(map_report(brand_code, item))

            report_stats = combine_batch_stats(
                self._upsert(cursor, REPORT_SPEC, scanned_reports),
                self._upsert_support_reports(cursor, support_reports),
            )
            issue_stats = self._upsert(
                cursor, ISSUE_SPEC,
                [map_issue(brand_code, item) for item in issue_items],
            )
            mission_stats = self._upsert(
                cursor, MISSION_SPEC,
                [map_mission(brand_code, item) for item in collection.missions],
            )
            self.connection.commit()
        except Exception as exc:
            self.connection.rollback()
            raise DatabaseError("MSSQL 트랜잭션 적재에 실패했습니다.") from exc
        return CollectionStats(
            report_stats,
            issue_stats,
            mission_stats,
            db_committed=True,
        )

    def close(self) -> None:
        self.connection.close()

    def _upsert(
        self, cursor: Any, spec: TableSpec, rows: list[dict[str, object]]
    ) -> BatchStats:
        if not rows:
            return BatchStats()
        existing = self._fetch_existing(cursor, spec, rows)
        new_rows, changed_rows, unchanged_count = partition_rows(rows, existing, spec)
        if new_rows:
            cursor.executemany(
                build_insert_sql(self.schema, spec),
                [tuple(row[column] for column in spec.columns) for row in new_rows],
            )
        if changed_rows:
            cursor.executemany(
                build_update_sql(self.schema, spec),
                [
                    tuple(row[column] for column in spec.compared_columns)
                    + (row["brand_code"], row[spec.key_column])
                    for row in changed_rows
                ],
            )
        return BatchStats(len(new_rows), len(changed_rows), unchanged_count)

    def _upsert_support_reports(
        self, cursor: Any, rows: list[dict[str, object]]
    ) -> BatchStats:
        if not rows:
            return BatchStats()
        existing = self._fetch_existing(cursor, REPORT_BASE_SPEC, rows)
        new_rows, changed_rows, unchanged_count = partition_rows(
            rows, existing, REPORT_BASE_SPEC
        )
        if new_rows:
            insert_rows = [
                {
                    **row,
                    "expected_fine_amount": Decimal("0"),
                    "expected_suspension_days": 0,
                }
                for row in new_rows
            ]
            cursor.executemany(
                build_insert_sql(self.schema, REPORT_SPEC),
                [
                    tuple(row[column] for column in REPORT_SPEC.columns)
                    for row in insert_rows
                ],
            )
        if changed_rows:
            cursor.executemany(
                build_update_sql(self.schema, REPORT_BASE_SPEC),
                [
                    tuple(row[column] for column in REPORT_BASE_SPEC.compared_columns)
                    + (row["brand_code"], row[REPORT_BASE_SPEC.key_column])
                    for row in changed_rows
                ],
            )
        return BatchStats(len(new_rows), len(changed_rows), unchanged_count)

    def _fetch_existing(
        self, cursor: Any, spec: TableSpec, rows: list[dict[str, object]]
    ) -> dict[object, dict[str, object]]:
        existing: dict[object, dict[str, object]] = {}
        keys = list(dict.fromkeys(row[spec.key_column] for row in rows))
        brand_code = rows[0]["brand_code"]
        selected = ", ".join(f"[{column}]" for column in spec.columns)
        for offset in range(0, len(keys), 500):
            chunk = keys[offset : offset + 500]
            placeholders = ", ".join("?" for _ in chunk)
            sql = (
                f"SELECT {selected} FROM {_qualified(self.schema, spec.table)} "
                f"WHERE [brand_code] = ? AND [{spec.key_column}] IN ({placeholders})"
            )
            result = cursor.execute(sql, brand_code, *chunk)
            names = [description[0] for description in result.description]
            for db_row in result.fetchall():
                mapped = dict(zip(names, db_row))
                existing[mapped[spec.key_column]] = mapped
        return existing
