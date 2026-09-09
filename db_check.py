from __future__ import annotations

from db_config import DatabaseConfigError, load_database_settings
from mssql_repository import DatabaseError, connect_repository


EXPECTED_TABLES = (
    "fc_daum_qsc_report",
    "fc_daum_qsc_report_issue",
    "fc_daum_mission",
)


def main() -> int:
    try:
        settings = load_database_settings()
        repository = connect_repository(settings)
        try:
            placeholders = ", ".join("?" for _ in EXPECTED_TABLES)
            rows = repository.connection.cursor().execute(
                "SELECT t.name "
                "FROM sys.tables AS t "
                "INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id "
                f"WHERE s.name = ? AND t.name IN ({placeholders}) "
                "ORDER BY t.name",
                settings.schema,
                *EXPECTED_TABLES,
            ).fetchall()
        finally:
            repository.close()
    except (DatabaseConfigError, DatabaseError) as exc:
        print(f"[DB 확인 실패] {exc}")
        return 1

    found = {row[0] for row in rows}
    missing = [name for name in EXPECTED_TABLES if name not in found]
    if missing:
        print("[DB 확인 실패] 없는 테이블: " + ", ".join(missing))
        return 1
    print("[DB 확인 성공] 대상 테이블 3개가 모두 존재합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
