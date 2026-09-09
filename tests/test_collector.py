from datetime import datetime, timedelta, timezone

from collector import MonthlyCollector, calendar_month_cutoff_ms
from fnb_client import ApiError


KST = timezone(timedelta(hours=9), name="Asia/Seoul")


class FakeClient:
    def __init__(
        self,
        report_pages,
        mission_pages,
        issue_pages=None,
        report_pages_by_sort=None,
    ):
        self.report_pages = report_pages
        self.report_pages_by_sort = report_pages_by_sort or {}
        self.mission_pages = mission_pages
        self.issue_pages = issue_pages or {}
        self.calls = []

    def login(self):
        self.calls.append("login")
        return {"userNo": 1}

    def get_reports(
        self, *, current_page, size_per_page, sort_field="visitDate"
    ):
        if sort_field == "visitDate":
            self.calls.append(("reports", current_page, size_per_page))
            pages = self.report_pages
        else:
            self.calls.append(
                ("reports", sort_field, current_page, size_per_page)
            )
            pages = self.report_pages_by_sort.get(sort_field, {})
        return pages.get(
            current_page, {"totalContentsSize": 0, "contents": []}
        )

    def get_report_detail(self, report_no):
        self.calls.append(("detail", report_no))
        return {"reportNo": report_no, "detail": True}

    def get_report_issues(
        self, report_no, consequence, *, current_page, size_per_page
    ):
        self.calls.append(
            ("issues", report_no, consequence, current_page, size_per_page)
        )
        return self.issue_pages.get(
            (report_no, consequence, current_page),
            {"totalContentsSize": 0, "contents": []},
        )

    def get_missions(self, *, current_page, size_per_page):
        self.calls.append(("missions", current_page, size_per_page))
        return self.mission_pages.get(
            current_page, {"totalContentsSize": 0, "contents": []}
        )


def test_calendar_month_cutoff_adjusts_to_previous_month_end():
    executed_at = datetime(2025, 3, 31, 15, 30, tzinfo=KST)

    cutoff_ms = calendar_month_cutoff_ms(executed_at)
    cutoff = datetime.fromtimestamp(cutoff_ms / 1000, tz=KST)

    assert cutoff == datetime(2025, 2, 28, 15, 30, tzinfo=KST)


def test_collect_uses_explicit_kst_start_instead_of_previous_month():
    executed_at = datetime(2026, 7, 22, 12, 0, tzinfo=KST)
    collection_start = datetime(2026, 1, 1, 0, 0, tzinfo=KST)
    start_ms = int(collection_start.timestamp() * 1000)
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 2,
                "contents": [
                    {"reportNo": 2, "visitDate": start_ms},
                    {"reportNo": 1, "visitDate": start_ms - 1},
                ],
            }
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client).collect(
        executed_at, collection_start=collection_start
    )

    assert result.cutoff_ms == start_ms
    assert [item["reportNo"] for item in result.reports] == [2]


def test_collect_filters_reports_to_half_open_date_range_and_keeps_paging():
    executed_at = datetime(2026, 7, 22, 12, 0, tzinfo=KST)
    collection_start = datetime(2024, 1, 15, 0, 0, tzinfo=KST)
    collection_end = datetime(2024, 2, 1, 0, 0, tzinfo=KST)
    start_ms = int(collection_start.timestamp() * 1000)
    end_ms = int(collection_end.timestamp() * 1000)
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 6,
                "contents": [
                    {"reportNo": 6, "visitDate": end_ms + 1},
                    {"reportNo": 5, "visitDate": end_ms},
                ],
            },
            2: {
                "totalContentsSize": 6,
                "contents": [
                    {"reportNo": 4, "visitDate": end_ms - 1},
                    {"reportNo": 3, "visitDate": start_ms},
                ],
            },
            3: {
                "totalContentsSize": 6,
                "contents": [
                    {"reportNo": 2, "visitDate": start_ms - 1},
                    {"reportNo": 1, "visitDate": start_ms - 2},
                ],
            },
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client, page_size=2).collect(
        executed_at,
        collection_start=collection_start,
        collection_end=collection_end,
    )

    assert [item["reportNo"] for item in result.reports] == [4, 3]
    assert ("reports", 2, 2) in client.calls
    assert ("reports", 3, 2) in client.calls
    assert not any(
        call[:2] == ("reports", 4)
        for call in client.calls
        if isinstance(call, tuple)
    )


def test_collect_filters_missions_by_reg_date_end_boundary():
    executed_at = datetime(2026, 7, 22, 12, 0, tzinfo=KST)
    collection_start = datetime(2024, 2, 1, 0, 0, tzinfo=KST)
    collection_end = datetime(2024, 3, 1, 0, 0, tzinfo=KST)
    start_ms = int(collection_start.timestamp() * 1000)
    end_ms = int(collection_end.timestamp() * 1000)
    client = FakeClient(
        report_pages={1: {"totalContentsSize": 0, "contents": []}},
        mission_pages={
            1: {
                "totalContentsSize": 4,
                "contents": [
                    {"missionNo": 4, "reportNo": 904, "regDate": end_ms},
                    {"missionNo": 3, "reportNo": 903, "regDate": end_ms - 1},
                    {"missionNo": 2, "reportNo": 902, "regDate": start_ms},
                    {"missionNo": 1, "reportNo": 901, "regDate": start_ms - 1},
                ],
            }
        },
    )

    result = MonthlyCollector(client).collect(
        executed_at,
        collection_start=collection_start,
        collection_end=collection_end,
    )

    assert [item["missionNo"] for item in result.missions] == [3, 2]


def test_collect_rejects_end_not_after_start():
    executed_at = datetime(2026, 7, 22, 12, 0, tzinfo=KST)
    boundary = datetime(2024, 2, 1, 0, 0, tzinfo=KST)
    client = FakeClient({}, {})

    try:
        MonthlyCollector(client).collect(
            executed_at,
            collection_start=boundary,
            collection_end=boundary,
        )
    except ValueError as exc:
        assert "collection_end" in str(exc)
    else:
        raise AssertionError("collection_end <= collection_start must fail")


def test_collect_skips_only_report_detail_that_returns_http_404():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)

    class MissingDetailClient(FakeClient):
        def get_report_detail(self, report_no):
            self.calls.append(("detail", report_no))
            if report_no == 404:
                raise ApiError("missing detail", status_code=404)
            return {"reportNo": report_no, "detail": True}

    client = MissingDetailClient(
        report_pages={
            1: {
                "totalContentsSize": 2,
                "contents": [
                    {"reportNo": 404, "visitDate": cutoff + 2},
                    {"reportNo": 200, "visitDate": cutoff + 1},
                ],
            }
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client).collect(executed_at)

    assert [item["reportNo"] for item in result.reports] == [200]
    assert set(result.report_details) == {200}
    assert result.skipped_report_nos == (404,)


def test_collect_does_not_skip_non_404_report_detail_error():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)

    class BrokenDetailClient(FakeClient):
        def get_report_detail(self, report_no):
            raise ApiError("server error", status_code=500)

    client = BrokenDetailClient(
        report_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [{"reportNo": 500, "visitDate": cutoff + 1}],
            }
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    try:
        MonthlyCollector(client).collect(executed_at)
    except ApiError as exc:
        assert exc.status_code == 500
    else:
        raise AssertionError("non-404 detail failure must not be skipped")


def test_collect_skips_mission_when_its_parent_report_detail_returns_404():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)

    class MissingParentClient(FakeClient):
        def get_report_detail(self, report_no):
            raise ApiError("missing parent", status_code=404)

    client = MissingParentClient(
        report_pages={1: {"totalContentsSize": 0, "contents": []}},
        mission_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [
                    {"missionNo": 1, "reportNo": 404, "regDate": cutoff + 1}
                ],
            }
        },
    )

    result = MonthlyCollector(client).collect(executed_at)

    assert result.missions == []
    assert result.skipped_report_nos == (404,)


def test_collects_report_pages_until_visit_date_crosses_cutoff():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 5,
                "contents": [
                    {"reportNo": 11, "visitDate": cutoff + 1000},
                    {"reportNo": 10, "visitDate": cutoff},
                ],
            },
            2: {
                "totalContentsSize": 5,
                "contents": [
                    {"reportNo": 9, "visitDate": cutoff - 1},
                    {"reportNo": 8, "visitDate": cutoff - 1000},
                ],
            },
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client, page_size=2).collect(executed_at)

    assert [item["reportNo"] for item in result.reports] == [11, 10]
    assert ("reports", 1, 2) in client.calls
    assert ("reports", 2, 2) in client.calls
    assert not any(call[:2] == ("reports", 3) for call in client.calls if isinstance(call, tuple))


def test_regular_collection_includes_late_registered_and_updated_old_reports_once():
    executed_at = datetime(2026, 8, 24, 8, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)
    old_visit_date = cutoff - 10_000
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [
                    {
                        "reportNo": 10,
                        "visitDate": cutoff + 1,
                        "regDate": cutoff + 1,
                        "updateDate": cutoff + 1,
                    }
                ],
            }
        },
        report_pages_by_sort={
            "regDate": {
                1: {
                    "totalContentsSize": 2,
                    "contents": [
                        {
                            "reportNo": 11,
                            "visitDate": old_visit_date,
                            "regDate": cutoff + 2,
                            "updateDate": cutoff + 3,
                        },
                        {
                            "reportNo": 10,
                            "visitDate": cutoff + 1,
                            "regDate": cutoff + 1,
                            "updateDate": cutoff + 1,
                        },
                    ],
                }
            },
            "updateDate": {
                1: {
                    "totalContentsSize": 2,
                    "contents": [
                        {
                            "reportNo": 12,
                            "visitDate": old_visit_date,
                            "regDate": old_visit_date,
                            "updateDate": cutoff + 4,
                        },
                        {
                            "reportNo": 11,
                            "visitDate": old_visit_date,
                            "regDate": cutoff + 2,
                            "updateDate": cutoff + 3,
                        },
                    ],
                }
            },
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client).collect(executed_at)

    assert [item["reportNo"] for item in result.reports] == [10, 11, 12]
    assert [call for call in client.calls if call == ("detail", 11)] == [
        ("detail", 11)
    ]
    assert [call for call in client.calls if call == ("detail", 12)] == [
        ("detail", 12)
    ]


def test_explicit_backfill_keeps_visit_date_only_report_scope():
    executed_at = datetime(2026, 8, 24, 8, 0, tzinfo=KST)
    collection_start = datetime(2026, 6, 1, tzinfo=KST)
    start_ms = int(collection_start.timestamp() * 1000)
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [{"reportNo": 20, "visitDate": start_ms}],
            }
        },
        report_pages_by_sort={
            "regDate": {
                1: {
                    "totalContentsSize": 1,
                    "contents": [
                        {
                            "reportNo": 21,
                            "visitDate": start_ms - 1,
                            "regDate": start_ms + 1,
                        }
                    ],
                }
            }
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
    )

    result = MonthlyCollector(client).collect(
        executed_at, collection_start=collection_start
    )

    assert [item["reportNo"] for item in result.reports] == [20]
    assert not any(
        call[:2] == ("reports", "regDate")
        for call in client.calls
        if isinstance(call, tuple)
    )


def test_collects_mission_pages_by_reg_date_until_cutoff():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)
    client = FakeClient(
        report_pages={1: {"totalContentsSize": 0, "contents": []}},
        mission_pages={
            1: {
                "totalContentsSize": 3,
                "contents": [
                    {"missionNo": 21, "reportNo": 901, "regDate": cutoff + 1},
                    {"missionNo": 20, "reportNo": 902, "regDate": cutoff},
                ],
            },
            2: {
                "totalContentsSize": 3,
                "contents": [
                    {"missionNo": 19, "reportNo": 903, "regDate": cutoff - 1}
                ],
            },
        },
    )

    result = MonthlyCollector(client, page_size=2).collect(executed_at)

    assert [item["missionNo"] for item in result.missions] == [21, 20]
    assert ("missions", 2, 2) in client.calls


def test_collects_details_and_merges_paginated_issues_by_answer_number():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)
    client = FakeClient(
        report_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [{"reportNo": 11, "visitDate": cutoff + 1}],
            }
        },
        mission_pages={1: {"totalContentsSize": 0, "contents": []}},
        issue_pages={
            (11, "fine", 1): {
                "totalContentsSize": 2,
                "contents": [
                    {"answerNo": 101, "fine": 500},
                    {"answerNo": 103, "fine": 1000},
                ],
            },
            (11, "suspension", 1): {
                "totalContentsSize": 2,
                "contents": [
                    {"answerNo": 102, "suspension": 30},
                    {"answerNo": 103, "suspension": 60},
                ],
            },
        },
    )

    result = MonthlyCollector(client, page_size=100).collect(executed_at)

    assert result.report_details[11]["detail"] is True
    assert set(result.issues) == {101, 102, 103}
    assert result.issues[103]["fine"] == 1000
    assert result.issues[103]["suspension"] == 60
    assert result.issue_scanned_report_nos == frozenset({11})


def test_adds_parent_report_when_recent_mission_references_older_report():
    executed_at = datetime(2026, 7, 21, 12, 0, tzinfo=KST)
    cutoff = calendar_month_cutoff_ms(executed_at)
    client = FakeClient(
        report_pages={1: {"totalContentsSize": 0, "contents": []}},
        mission_pages={
            1: {
                "totalContentsSize": 1,
                "contents": [
                    {
                        "missionNo": 21,
                        "reportNo": 999,
                        "regDate": cutoff + 1,
                    }
                ],
            }
        },
    )

    result = MonthlyCollector(client, page_size=100).collect(executed_at)

    assert [report["reportNo"] for report in result.reports] == [999]
    assert result.report_details[999] == {"reportNo": 999, "detail": True}
    assert result.issue_scanned_report_nos == frozenset()
    assert ("detail", 999) in client.calls
