from datetime import datetime
from decimal import Decimal

import pytest

from mssql_repository import (
    aggregate_expected_sanctions,
    epoch_ms_to_utc_datetime,
    map_issue,
    map_mission,
    map_report,
    normalize_store_name,
    translate_brand_name,
    translate_mission_status,
)


@pytest.mark.parametrize(
    ("brand_code", "store_name", "expected"),
    [
        ("hanchon", " 한촌설렁탕 부천까치울점 ", "부천까치울점"),
        ("hanchon", "인천삼산점(양수)", "인천삼산점"),
        ("hanchon", "천안두정점 (양수)", "천안두정점"),
        ("hanchon", "인천영종도", "인천영종도점"),
        ("yuksudang", "안양비즈타워점", "육수당 안양비즈타워점"),
        ("yuksudang", "육수당  가산이앤시타워점", "육수당 가산이앤시타워점"),
        ("yuksudang", "육수당 인천영종도", "육수당 인천영종도점"),
        ("hanchon", None, None),
        ("hanchon", "   ", ""),
        ("another_brand", " 원본 매장 ", "원본 매장"),
    ],
)
def test_normalize_store_name(brand_code, store_name, expected):
    assert normalize_store_name(brand_code, store_name) == expected


@pytest.mark.parametrize(
    ("brand_code", "expected"),
    [
        ("hanchon", "한촌"),
        ("yuksudang", "육수당"),
        ("another_brand", "another_brand"),
    ],
)
def test_translate_brand_name(brand_code, expected):
    assert translate_brand_name(brand_code) == expected


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("DOING", "수행 전"),
        ("ACTION", "제출 완료"),
        ("COMPLETE", "완료됨"),
        ("REDOING", "재수행 요청"),
        ("UNKNOWN", "UNKNOWN"),
        (None, None),
    ],
)
def test_translate_mission_status_to_korean(raw_status, expected):
    assert translate_mission_status(raw_status) == expected


def test_epoch_ms_to_utc_datetime_returns_naive_utc_datetime():
    result = epoch_ms_to_utc_datetime(0)

    assert result == datetime(1970, 1, 1, 0, 0, 0)
    assert result.tzinfo is None
    assert epoch_ms_to_utc_datetime(None) is None


def test_map_report_uses_minimal_table_columns():
    result = map_report(
        "hanchon",
        {
            "reportNo": 789570,
            "storeNm": "부천까치울점",
            "visitDate": 0,
            "regDate": 1000,
            "updateDate": 2000,
            "grade": "A",
            "percentageScore": 92.09,
            "userNm": "점검자",
        },
    )

    assert result == {
        "brand_code": "hanchon",
        "brand_name": "한촌",
        "report_no": 789570,
        "store_name": "부천까치울점",
        "visit_date": datetime(1970, 1, 1),
        "reg_date": datetime(1970, 1, 1, 0, 0, 1),
        "source_updated_at": datetime(1970, 1, 1, 0, 0, 2),
        "grade": "A",
        "percentage_score": Decimal("92.09"),
        "inspector_name": "점검자",
    }


def test_aggregate_expected_sanctions_groups_by_report_and_treats_null_as_zero():
    totals = aggregate_expected_sanctions(
        [
            {"reportNo": 1, "fine": 500, "suspension": None},
            {"reportNo": 1, "fine": None, "suspension": 30},
            {"reportNo": 1, "fine": 250.5, "suspension": 15},
            {"reportNo": 2, "fine": 100, "suspension": 0},
        ]
    )

    assert totals[1] == (Decimal("750.5"), 45)
    assert totals[2] == (Decimal("100"), 0)


def test_map_report_includes_expected_sanctions_when_supplied():
    result = map_report(
        "hanchon",
        {"reportNo": 1},
        expected_sanctions=(Decimal("800000"), 45),
    )

    assert result["expected_fine_amount"] == Decimal("800000")
    assert result["expected_suspension_days"] == 45


def test_map_issue_maps_sanctions_and_categories():
    result = map_issue(
        "hanchon",
        {
            "answerNo": 44065963,
            "reportNo": 789570,
            "storeNm": "부천까치울점",
            "reportVisitDate": 0,
            "topCatNm": "Q(품질)",
            "catNm": "식재료 보관",
            "quesTitle": "표시사항을 보관하는가?",
            "checkedValue": "n",
            "fine": 500,
            "suspension": 30,
        },
    )

    assert result["answer_no"] == 44065963
    assert result["brand_name"] == "한촌"
    assert result["report_no"] == 789570
    assert result["fine_amount"] == Decimal("500")
    assert result["suspension_days"] == 30
    assert result["top_category_name"] == "Q(품질)"
    assert result["category_name"] == "식재료 보관"


def test_map_mission_maps_requested_excel_columns_and_missing_values():
    result = map_mission(
        "yuksudang",
        {
            "missionNo": 434872,
            "reportNo": 787783,
            "storeNm": "매장",
            "startDate": 0,
            "endDate": 1000,
            "status": "DOING",
            "title": "미션 제목",
            "description": "미션 설명",
            "startUserNm": "SV 이름",
            "actionDate": 2000,
            "completeDate": 3000,
            "actionUserNm": "저장하지 않는 제출자",
            "actionComment": "저장하지 않는 코멘트",
        },
    )

    assert result["brand_code"] == "yuksudang"
    assert result["brand_name"] == "육수당"
    assert result["mission_no"] == 434872
    assert result["report_no"] == 787783
    assert result["store_name"] == "육수당 매장점"
    assert result["sent_date"] == datetime(1970, 1, 1)
    assert result["due_date"] == datetime(1970, 1, 1, 0, 0, 1)
    assert result["title"] == "미션 제목"
    assert result["description"] == "미션 설명"
    assert result["sv_name"] == "SV 이름"
    assert result["owner_submitted_at"] == datetime(1970, 1, 1, 0, 0, 2)
    assert result["sv_completed_at"] == datetime(1970, 1, 1, 0, 0, 3)
    assert "inspection_comment" not in result
    assert "sender_name" not in result
    assert "action_date" not in result
    assert "completed_date" not in result
    assert "action_user_name" not in result
    assert "action_comment" not in result
