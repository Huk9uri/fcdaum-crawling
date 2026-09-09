import pytest

from config import BrandAccount, Settings
from fnb_client import FnbClient


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload=None):
        self._payload = payload or {"contents": [], "totalContentsSize": 0}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def make_client():
    settings = Settings("https://fcdaum.com", (), 30, 100)
    account = BrandAccount("hanchon", "한촌설렁탕", "tester", "secret")
    session = FakeSession()
    return FnbClient(settings, account, session=session), session


def test_get_reports_uses_expected_query():
    client, session = make_client()

    client.get_reports(current_page=3, size_per_page=100)

    url, kwargs = session.calls[0]
    assert url.endswith("/api/v2/bff/fnb-qsc-report-info")
    assert kwargs["params"] == {
        "currentPage": 3,
        "sizePerPage": 100,
        "sortField": "visitDate",
        "sortDirection": "DESC",
        "useYn": "y",
        "statuses": "r,o",
    }
    assert kwargs["timeout"] == 30


@pytest.mark.parametrize("sort_field", ["visitDate", "regDate", "updateDate"])
def test_get_reports_uses_requested_supported_sort_field(sort_field):
    client, session = make_client()

    client.get_reports(sort_field=sort_field)

    _, kwargs = session.calls[0]
    assert kwargs["params"]["sortField"] == sort_field


def test_get_reports_rejects_unknown_sort_field():
    client, _ = make_client()

    with pytest.raises(ValueError, match="sortField"):
        client.get_reports(sort_field="unknown")


def test_get_report_detail_uses_report_number_in_url():
    client, session = make_client()

    client.get_report_detail(789570)

    url, _ = session.calls[0]
    assert url.endswith("/api/v2/bff/fnb-qsc-report-info/789570")


@pytest.mark.parametrize("invalid", [True, 0, -1, "789570"])
def test_get_report_detail_rejects_invalid_report_number(invalid):
    client, _ = make_client()

    with pytest.raises(ValueError):
        client.get_report_detail(invalid)


@pytest.mark.parametrize(
    ("consequence", "expected_filter"),
    [("fine", "fineFrom"), ("suspension", "suspensionFrom")],
)
def test_get_report_issues_uses_expected_consequence_filter(
    consequence, expected_filter
):
    client, session = make_client()

    client.get_report_issues(
        789570, consequence, current_page=2, size_per_page=100
    )

    url, kwargs = session.calls[0]
    assert url.endswith("/api/v2/bff/fnb-qsc-report-answer")
    assert kwargs["params"] == {
        "currentPage": 2,
        "sizePerPage": 100,
        "sortField": "reportVisitDate",
        "sortDirection": "DESC",
        "reportNos": 789570,
        expected_filter: 1,
    }


def test_get_report_issues_rejects_unknown_consequence():
    client, _ = make_client()

    with pytest.raises(ValueError, match="fine.*suspension"):
        client.get_report_issues(789570, "unknown")
