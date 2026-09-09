from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class BrandAccount:
    code: str
    name: str
    user_id: str
    password: str


@dataclass(frozen=True)
class Settings:
    base_url: str
    accounts: tuple[BrandAccount, ...]
    timeout_seconds: int = 30
    page_size: int = 100


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    if environ is None:
        load_dotenv()
        environ = os.environ

    required_names = (
        "HANCHON_USER_ID",
        "HANCHON_PASSWORD",
        "YUKSUDANG_USER_ID",
        "YUKSUDANG_PASSWORD",
    )
    values = {name: environ.get(name, "").strip() for name in required_names}
    missing = [name for name in required_names if not values[name]]
    if missing:
        raise ConfigError("필수 환경변수가 없습니다: " + ", ".join(missing))

    return Settings(
        base_url="https://fcdaum.com",
        accounts=(
            BrandAccount(
                code="hanchon",
                name="한촌설렁탕",
                user_id=values["HANCHON_USER_ID"],
                password=values["HANCHON_PASSWORD"],
            ),
            BrandAccount(
                code="yuksudang",
                name="육수당",
                user_id=values["YUKSUDANG_USER_ID"],
                password=values["YUKSUDANG_PASSWORD"],
            ),
        ),
    )
