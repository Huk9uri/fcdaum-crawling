import pytest

from db_config import DatabaseConfigError, load_database_settings


VALID_DB_ENV = {
    "MSSQL_SERVER": "db.example.internal",
    "MSSQL_PORT": "1433",
    "MSSQL_DATABASE": "naverDB",
    "MSSQL_USER": "crawler",
    "MSSQL_PASSWORD": "db-secret",
    "MSSQL_SCHEMA": "dbo",
    "MSSQL_DRIVER": "ODBC Driver 18 for SQL Server",
}


def test_load_database_settings_rejects_missing_required_values():
    with pytest.raises(DatabaseConfigError) as exc_info:
        load_database_settings({})

    message = str(exc_info.value)
    for name in ("MSSQL_SERVER", "MSSQL_DATABASE", "MSSQL_USER", "MSSQL_PASSWORD"):
        assert name in message


@pytest.mark.parametrize("port", ["zero", "0", "65536"])
def test_load_database_settings_rejects_invalid_port(port):
    with pytest.raises(DatabaseConfigError, match="MSSQL_PORT"):
        load_database_settings({**VALID_DB_ENV, "MSSQL_PORT": port})


def test_load_database_settings_rejects_unsafe_schema_name():
    with pytest.raises(DatabaseConfigError, match="MSSQL_SCHEMA"):
        load_database_settings({**VALID_DB_ENV, "MSSQL_SCHEMA": "dbo]; DROP TABLE x;--"})


def test_database_settings_do_not_expose_password_in_repr():
    settings = load_database_settings(VALID_DB_ENV)

    assert settings.server == "db.example.internal"
    assert settings.port == 1433
    assert settings.database == "naverDB"
    assert settings.schema == "dbo"
    assert settings.driver == "ODBC Driver 18 for SQL Server"
    assert "db-secret" not in repr(settings)


def test_database_settings_default_to_installed_odbc_driver_17():
    environ = {key: value for key, value in VALID_DB_ENV.items() if key != "MSSQL_DRIVER"}

    settings = load_database_settings(environ)

    assert settings.driver == "ODBC Driver 17 for SQL Server"
