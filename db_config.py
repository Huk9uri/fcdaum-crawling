from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Mapping

from dotenv import load_dotenv


class DatabaseConfigError(ValueError):
    """Raised when MSSQL configuration is missing or invalid."""


@dataclass(frozen=True)
class DatabaseSettings:
    server: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    schema: str = "dbo"
    driver: str = "ODBC Driver 17 for SQL Server"

    def connection_string(self) -> str:
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.user};PWD={self.password};"
            "Encrypt=yes;TrustServerCertificate=yes;"
        )


def load_database_settings(
    environ: Mapping[str, str] | None = None,
) -> DatabaseSettings:
    if environ is None:
        load_dotenv()
        environ = os.environ

    required = ("MSSQL_SERVER", "MSSQL_DATABASE", "MSSQL_USER", "MSSQL_PASSWORD")
    values = {name: environ.get(name, "").strip() for name in required}
    missing = [name for name in required if not values[name]]
    if missing:
        raise DatabaseConfigError(
            "필수 DB 환경변수가 없습니다: " + ", ".join(missing)
        )

    port_text = environ.get("MSSQL_PORT", "1433").strip()
    try:
        port = int(port_text)
    except ValueError as exc:
        raise DatabaseConfigError("MSSQL_PORT는 정수여야 합니다.") from exc
    if not 1 <= port <= 65535:
        raise DatabaseConfigError("MSSQL_PORT는 1~65535 범위여야 합니다.")

    schema = environ.get("MSSQL_SCHEMA", "dbo").strip() or "dbo"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema) is None:
        raise DatabaseConfigError("MSSQL_SCHEMA 형식이 올바르지 않습니다.")

    driver = (
        environ.get("MSSQL_DRIVER", "ODBC Driver 17 for SQL Server").strip()
        or "ODBC Driver 17 for SQL Server"
    )
    return DatabaseSettings(
        server=values["MSSQL_SERVER"],
        port=port,
        database=values["MSSQL_DATABASE"],
        user=values["MSSQL_USER"],
        password=values["MSSQL_PASSWORD"],
        schema=schema,
        driver=driver,
    )
