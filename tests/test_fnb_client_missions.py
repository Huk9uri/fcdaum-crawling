from config import BrandAccount, Settings
from fnb_client import FnbClient


class FakeResponse:
    status_code = 200
    headers = {}

    def json(self):
        return {"contents": [], "totalContentsSize": 0}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse()


def test_get_missions_uses_expected_query():
    settings = Settings("https://fcdaum.com", (), 30, 100)
    account = BrandAccount("hanchon", "한촌설렁탕", "tester", "secret")
    session = FakeSession()
    client = FnbClient(settings, account, session=session)

    client.get_missions(current_page=4, size_per_page=100)

    url, kwargs = session.calls[0]
    assert url.endswith("/api/v2/bff/fnb-mission-info")
    assert kwargs["params"] == {
        "currentPage": 4,
        "sizePerPage": 100,
        "sortField": "regDate,missionNo",
        "sortDirection": "DESC",
        "viewType": "c",
        "statuses": "DOING,ACTION,REDOING,COMPLETE",
    }
    assert kwargs["timeout"] == 30
