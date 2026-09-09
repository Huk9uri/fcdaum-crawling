from __future__ import annotations

from typing import Any

import requests

from config import BrandAccount, Settings


class ApiError(RuntimeError):
    """Raised when the remote API returns an unusable response."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CloudflareChallengeError(ApiError):
    """Raised when Cloudflare blocks the non-browser HTTP client."""


class AuthenticationError(ApiError):
    """Raised when login succeeds incompletely or lacks required access."""


class FnbClient:
    def __init__(
        self,
        settings: Settings,
        account: BrandAccount,
        session: Any | None = None,
    ):
        self.settings = settings
        self.account = account
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Referer": f"{settings.base_url}/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/150.0.0.0 Safari/537.36"
                ),
            }
        )

    def login(self) -> dict[str, object]:
        url = f"{self.settings.base_url}/api/v2/bff/logged-in-user"
        try:
            response = self.session.post(
                url,
                json={
                    "userId": self.account.user_id,
                    "password": self.account.password,
                    "languageCode": "ko",
                },
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ApiError("로그인 서버에 연결하지 못했습니다.") from exc

        payload = self._json_payload(response, "로그인")
        user_no = payload.get("userNo")
        functions = payload.get("functions")

        if not isinstance(user_no, int) or isinstance(user_no, bool):
            raise AuthenticationError("로그인 응답에 사용자 번호가 없습니다.")
        if not isinstance(functions, dict):
            raise AuthenticationError("로그인 응답에 권한 정보가 없습니다.")

        required = ("qsc-report", "qsc-mission")
        if any(functions.get(name) != "MANAGE" for name in required):
            raise AuthenticationError("리포트 또는 품질미션 조회 권한이 없습니다.")

        self.session.headers["X-Logged-In-User-No"] = str(user_no)
        return payload

    def get_reports(
        self,
        *,
        current_page: int = 1,
        size_per_page: int | None = None,
        sort_field: str = "visitDate",
    ) -> dict[str, object]:
        if sort_field not in ("visitDate", "regDate", "updateDate"):
            raise ValueError(
                "sortField는 visitDate, regDate 또는 updateDate여야 합니다."
            )
        return self._get_json(
            "/api/v2/bff/fnb-qsc-report-info",
            params={
                "currentPage": current_page,
                "sizePerPage": size_per_page or self.settings.page_size,
                "sortField": sort_field,
                "sortDirection": "DESC",
                "useYn": "y",
                "statuses": "r,o",
            },
            operation="리포트 목록",
        )

    def get_report_detail(self, report_no: int) -> dict[str, object]:
        self._validate_positive_id(report_no, "reportNo")
        return self._get_json(
            f"/api/v2/bff/fnb-qsc-report-info/{report_no}",
            operation="리포트 상세",
        )

    def get_report_issues(
        self,
        report_no: int,
        consequence: str,
        *,
        current_page: int = 1,
        size_per_page: int | None = None,
    ) -> dict[str, object]:
        self._validate_positive_id(report_no, "reportNo")
        filters = {
            "fine": "fineFrom",
            "suspension": "suspensionFrom",
        }
        if consequence not in filters:
            raise ValueError("consequence는 fine 또는 suspension이어야 합니다.")

        params = {
            "currentPage": current_page,
            "sizePerPage": size_per_page or self.settings.page_size,
            "sortField": "reportVisitDate",
            "sortDirection": "DESC",
            "reportNos": report_no,
            filters[consequence]: 1,
        }
        return self._get_json(
            "/api/v2/bff/fnb-qsc-report-answer",
            params=params,
            operation="리포트 문제항목",
        )

    def get_missions(
        self, *, current_page: int = 1, size_per_page: int | None = None
    ) -> dict[str, object]:
        return self._get_json(
            "/api/v2/bff/fnb-mission-info",
            params={
                "currentPage": current_page,
                "sizePerPage": size_per_page or self.settings.page_size,
                "sortField": "regDate,missionNo",
                "sortDirection": "DESC",
                "viewType": "c",
                "statuses": "DOING,ACTION,REDOING,COMPLETE",
            },
            operation="품질미션 목록",
        )

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, object] | None = None,
        operation: str,
    ) -> dict[str, object]:
        try:
            response = self.session.get(
                f"{self.settings.base_url}{path}",
                params=params,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ApiError(f"{operation} 서버에 연결하지 못했습니다.") from exc
        return self._json_payload(response, operation)

    @staticmethod
    def _validate_positive_id(value: object, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name}는 양의 정수여야 합니다.")

    def _json_payload(self, response: Any, operation: str) -> dict[str, object]:
        mitigated = str(response.headers.get("Cf-Mitigated", "")).lower()
        if response.status_code == 403 and mitigated == "challenge":
            raise CloudflareChallengeError(
                "Cloudflare가 API 요청을 차단했습니다. 브라우저 자동화가 필요합니다."
            )
        if not 200 <= response.status_code < 300:
            raise ApiError(
                f"{operation} 요청이 HTTP {response.status_code}로 실패했습니다.",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ApiError(f"{operation} 응답이 JSON 형식이 아닙니다.") from exc
        if not isinstance(payload, dict):
            raise ApiError(f"{operation} 응답이 JSON 객체가 아닙니다.")
        return payload
