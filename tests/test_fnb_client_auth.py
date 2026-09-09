import pytest

from config import BrandAccount, Settings
from fnb_client import (
    ApiError,
    AuthenticationError,
    CloudflareChallengeError,
    FnbClient,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.response


def make_settings():
    return Settings(
        base_url="https://fcdaum.com",
        accounts=(),
        timeout_seconds=30,
    )


def make_account():
    return BrandAccount("hanchon", "한촌설렁탕", "tester", "secret")


def valid_login_payload():
    return {
        "userNo": 6143,
        "functions": {
            "qsc-report": "MANAGE",
            "qsc-mission": "MANAGE",
        },
    }


def test_login_posts_credentials_and_sets_user_header():
    session = FakeSession(FakeResponse(payload=valid_login_payload()))
    client = FnbClient(make_settings(), make_account(), session=session)

    result = client.login()

    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "https://fcdaum.com/api/v2/bff/logged-in-user"
    assert kwargs["json"] == {
        "userId": "tester",
        "password": "secret",
        "languageCode": "ko",
    }
    assert kwargs["timeout"] == 30
    assert session.headers["X-Logged-In-User-No"] == "6143"
    assert session.headers["Accept"] == "application/json"
    assert session.headers["User-Agent"].startswith("Mozilla/5.0 (Windows NT 10.0")
    assert "Chrome/" in session.headers["User-Agent"]
    assert result["userNo"] == 6143


def test_login_detects_cloudflare_challenge():
    session = FakeSession(
        FakeResponse(
            status_code=403,
            headers={"Cf-Mitigated": "challenge"},
        )
    )

    with pytest.raises(CloudflareChallengeError, match="Cloudflare"):
        FnbClient(make_settings(), make_account(), session=session).login()


@pytest.mark.parametrize(
    "payload",
    [
        {"functions": {"qsc-report": "MANAGE", "qsc-mission": "MANAGE"}},
        {"userNo": 6143, "functions": {"qsc-report": "NONE", "qsc-mission": "MANAGE"}},
        {"userNo": 6143, "functions": {"qsc-report": "MANAGE", "qsc-mission": "NONE"}},
    ],
)
def test_login_rejects_missing_identity_or_permissions(payload):
    session = FakeSession(FakeResponse(payload=payload))

    with pytest.raises(AuthenticationError):
        FnbClient(make_settings(), make_account(), session=session).login()


def test_login_rejects_non_json_response_without_leaking_password():
    session = FakeSession(
        FakeResponse(payload=None, json_error=ValueError("not json"))
    )

    with pytest.raises(ApiError) as exc_info:
        FnbClient(make_settings(), make_account(), session=session).login()

    assert "secret" not in str(exc_info.value)
