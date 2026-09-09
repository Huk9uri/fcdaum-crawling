from __future__ import annotations

from db_config import load_database_settings
from mssql_repository import connect_repository


TABLES = (
    "fc_daum_qsc_report",
    "fc_daum_qsc_report_issue",
    "fc_daum_mission",
)


def main() -> int:
    settings = load_database_settings()
    repository = connect_repository(settings)
    try:
        cursor = repository.connection.cursor()
        for table in TABLES:
            rows = cursor.execute(
                f"SELECT [brand_code], COUNT_BIG(*), "
                "MAX([collected_at]), MAX([updated_at]) "
                f"FROM [{settings.schema}].[{table}] "
                "GROUP BY [brand_code] ORDER BY [brand_code]"
            ).fetchall()
            for brand_code, count, collected_at, updated_at in rows:
                print(
                    f"{table}|{brand_code}|{count}|"
                    f"{collected_at.isoformat()}|{updated_at.isoformat()}"
                )
    finally:
        repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
