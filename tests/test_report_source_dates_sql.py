from pathlib import Path


def test_report_source_dates_migration_adds_nullable_datetime_columns():
    sql_path = Path(__file__).parents[1] / "sql" / "add_report_source_dates.sql"

    sql = sql_path.read_text(encoding="utf-8")

    assert "COL_LENGTH('dbo.fc_daum_qsc_report', 'reg_date')" in sql
    assert "ADD reg_date DATETIME2(3) NULL" in sql
    assert "COL_LENGTH('dbo.fc_daum_qsc_report', 'source_updated_at')" in sql
    assert "ADD source_updated_at DATETIME2(3) NULL" in sql
