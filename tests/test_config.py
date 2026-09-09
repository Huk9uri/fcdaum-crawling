import pytest

from config import ConfigError, load_settings


VALID_ENV = {
    "HANCHON_USER_ID": "hanchon-id",
    "HANCHON_PASSWORD": "hanchon-secret",
    "YUKSUDANG_USER_ID": "yuksudang-id",
    "YUKSUDANG_PASSWORD": "yuksudang-secret",
}


def test_load_settings_rejects_missing_brand_credentials():
    with pytest.raises(ConfigError) as exc_info:
        load_settings({})

    message = str(exc_info.value)
    for name in VALID_ENV:
        assert name in message


def test_load_settings_builds_brand_accounts_in_fixed_order():
    settings = load_settings(VALID_ENV)

    assert settings.base_url == "https://fcdaum.com"
    assert settings.timeout_seconds == 30
    assert settings.page_size == 100
    assert [(a.code, a.name) for a in settings.accounts] == [
        ("hanchon", "한촌설렁탕"),
        ("yuksudang", "육수당"),
    ]
    assert settings.accounts[0].user_id == "hanchon-id"
    assert settings.accounts[1].password == "yuksudang-secret"


def test_load_settings_rejects_one_blank_brand_credential():
    environ = {**VALID_ENV, "YUKSUDANG_PASSWORD": "  "}

    with pytest.raises(ConfigError, match="YUKSUDANG_PASSWORD"):
        load_settings(environ)
