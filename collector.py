from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from dateutil.relativedelta import relativedelta

from fnb_client import ApiError, FnbClient


KST = timezone(timedelta(hours=9), name="Asia/Seoul")


@dataclass(frozen=True)
class BrandCollection:
    reports: list[dict[str, object]]
    report_details: dict[int, dict[str, object]]
    issues: dict[int, dict[str, object]]
    missions: list[dict[str, object]]
    cutoff_ms: int
    issue_scanned_report_nos: frozenset[int] = frozenset()
    skipped_report_nos: tuple[int, ...] = ()


def calendar_month_cutoff_ms(executed_at: datetime) -> int:
    if executed_at.tzinfo is None:
        raise ValueError("executed_at은 시간대 정보가 필요합니다.")
    cutoff = executed_at.astimezone(KST) - relativedelta(months=1)
    return int(cutoff.timestamp() * 1000)


class MonthlyCollector:
    def __init__(self, client: FnbClient, page_size: int = 100):
        if page_size <= 0:
            raise ValueError("page_size는 양의 정수여야 합니다.")
        self.client = client
        self.page_size = page_size

    def collect(
        self,
        executed_at: datetime,
        *,
        collection_start: datetime | None = None,
        collection_end: datetime | None = None,
    ) -> BrandCollection:
        if collection_start is None:
            cutoff_ms = calendar_month_cutoff_ms(executed_at)
        else:
            if collection_start.tzinfo is None:
                raise ValueError("collection_start에는 시간대 정보가 필요합니다.")
            if collection_start > executed_at:
                raise ValueError("collection_start는 실행 시각보다 늦을 수 없습니다.")
            cutoff_ms = int(collection_start.timestamp() * 1000)
        end_ms = None
        if collection_end is not None:
            if collection_end.tzinfo is None:
                raise ValueError("collection_end에는 시간대 정보가 필요합니다.")
            if collection_start is None:
                raise ValueError("collection_end에는 collection_start가 필요합니다.")
            if collection_end <= collection_start:
                raise ValueError("collection_end는 collection_start보다 늦어야 합니다.")
            end_ms = int(collection_end.timestamp() * 1000)
        self.client.login()

        report_date_fields = (
            ("visitDate",)
            if collection_start is not None
            else ("visitDate", "regDate", "updateDate")
        )
        reports_by_no: dict[int, dict[str, object]] = {}
        for date_field in report_date_fields:
            recent_reports = self._collect_recent_pages(
                fetch_page=lambda page, field=date_field: self.client.get_reports(
                    current_page=page,
                    size_per_page=self.page_size,
                    sort_field=field,
                ),
                date_field=date_field,
                cutoff_ms=cutoff_ms,
                end_ms=end_ms,
                operation="리포트 목록",
            )
            for report in recent_reports:
                report_no = report.get("reportNo")
                if isinstance(report_no, bool) or not isinstance(report_no, int):
                    raise ApiError("리포트 목록에 유효한 reportNo가 없습니다.")
                reports_by_no.setdefault(report_no, report)
        reports = list(reports_by_no.values())
        missions = self._collect_recent_pages(
            fetch_page=lambda page: self.client.get_missions(
                current_page=page, size_per_page=self.page_size
            ),
            date_field="regDate",
            cutoff_ms=cutoff_ms,
            end_ms=end_ms,
            operation="품질미션 목록",
        )

        details: dict[int, dict[str, object]] = {}
        issues: dict[int, dict[str, object]] = {}
        issue_scanned_report_nos: set[int] = set()
        skipped_report_nos: set[int] = set()
        available_reports: list[dict[str, object]] = []
        for report in reports:
            report_no = report.get("reportNo")
            if isinstance(report_no, bool) or not isinstance(report_no, int):
                raise ApiError("리포트 목록에 유효한 reportNo가 없습니다.")
            try:
                details[report_no] = self.client.get_report_detail(report_no)
            except ApiError as exc:
                if exc.status_code != 404:
                    raise
                skipped_report_nos.add(report_no)
                continue
            available_reports.append(report)
            issue_scanned_report_nos.add(report_no)
            for consequence in ("fine", "suspension"):
                for issue in self._collect_issue_pages(report_no, consequence):
                    answer_no = issue.get("answerNo")
                    if isinstance(answer_no, bool) or not isinstance(answer_no, int):
                        raise ApiError("문제항목에 유효한 answerNo가 없습니다.")
                    existing = issues.setdefault(answer_no, {})
                    existing.update(issue)

        reports = available_reports
        known_report_nos = set(details)
        available_missions: list[dict[str, object]] = []
        for mission in missions:
            report_no = mission.get("reportNo")
            if isinstance(report_no, bool) or not isinstance(report_no, int):
                raise ApiError("품질미션에 유효한 reportNo가 없습니다.")
            if report_no in skipped_report_nos:
                continue
            if report_no in known_report_nos:
                available_missions.append(mission)
                continue
            try:
                parent_report = self.client.get_report_detail(report_no)
            except ApiError as exc:
                if exc.status_code != 404:
                    raise
                skipped_report_nos.add(report_no)
                continue
            reports.append(parent_report)
            details[report_no] = parent_report
            known_report_nos.add(report_no)
            available_missions.append(mission)

        missions = available_missions

        return BrandCollection(
            reports=reports,
            report_details=details,
            issues=issues,
            missions=missions,
            cutoff_ms=cutoff_ms,
            issue_scanned_report_nos=frozenset(issue_scanned_report_nos),
            skipped_report_nos=tuple(sorted(skipped_report_nos)),
        )

    def _collect_recent_pages(
        self,
        *,
        fetch_page: Callable[[int], dict[str, object]],
        date_field: str,
        cutoff_ms: int,
        end_ms: int | None = None,
        operation: str,
    ) -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        page = 1
        while True:
            payload = fetch_page(page)
            contents = self._validated_contents(payload, operation)
            if not contents:
                break

            crossed_cutoff = False
            for item in contents:
                value = item.get(date_field)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ApiError(f"{operation} 항목에 유효한 {date_field}가 없습니다.")
                if value < cutoff_ms:
                    crossed_cutoff = True
                elif end_ms is None or value < end_ms:
                    collected.append(item)

            if crossed_cutoff or self._reached_total(payload, page, len(contents)):
                break
            page += 1
        return collected

    def _collect_issue_pages(
        self, report_no: int, consequence: str
    ) -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        page = 1
        while True:
            payload = self.client.get_report_issues(
                report_no,
                consequence,
                current_page=page,
                size_per_page=self.page_size,
            )
            contents = self._validated_contents(payload, "리포트 문제항목")
            if not contents:
                break
            collected.extend(contents)
            if self._reached_total(payload, page, len(contents)):
                break
            page += 1
        return collected

    @staticmethod
    def _validated_contents(
        payload: dict[str, object], operation: str
    ) -> list[dict[str, object]]:
        contents = payload.get("contents")
        if not isinstance(contents, list):
            raise ApiError(f"{operation} 응답에 contents 배열이 없습니다.")
        if any(not isinstance(item, dict) for item in contents):
            raise ApiError(f"{operation} contents 항목이 JSON 객체가 아닙니다.")
        return contents

    def _reached_total(
        self, payload: dict[str, object], page: int, returned_count: int
    ) -> bool:
        total = payload.get("totalContentsSize")
        if isinstance(total, int) and not isinstance(total, bool):
            return page * self.page_size >= total
        return returned_count < self.page_size
