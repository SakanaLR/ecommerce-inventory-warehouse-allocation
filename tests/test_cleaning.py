from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from retail_analytics import cleaning

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = PROJECT_ROOT / "config" / "non_product_stock_codes.csv"


def make_rows(rows: list[tuple]) -> pd.DataFrame:
    columns = ["invoice_no", "stock_code", "description", "quantity",
               "invoice_date", "unit_price", "customer_id", "country"]
    return pd.DataFrame(rows, columns=columns)


@pytest.fixture
def rules() -> pd.DataFrame:
    return cleaning.load_non_product_rules(RULES_PATH)


def test_stock_codes_are_upper_cased(rules):
    raw = make_rows([
        ("1", "85123a", "heart", 1, "2011-01-01 10:00", 2.0, "C1", "UK"),
        ("2", "85123A", "HEART", 1, "2011-01-02 10:00", 2.0, "C1", "UK"),
    ])
    result = cleaning.clean_transactions(raw, rules)
    assert result.sales["stock_code"].unique().tolist() == ["85123A"]


def test_non_product_rules_cover_exact_prefix_and_case(rules):
    codes = pd.Series(["POST", "m", "gift_0001_20", "C2", "B", "PADS", "S", "23444", "23574", "22016", "22423", "DCGSSBOY"])
    category = cleaning.non_product_category(codes, rules)
    assert category.notna().tolist() == [True] * 10 + [False, False]


def test_same_day_full_cancellation_removes_the_sale(rules):
    raw = make_rows([
        ("581483", "23843", "PAPER CRAFT", 80995, "2011-12-09 09:15", 2.08, "16446", "UK"),
        ("C581484", "23843", "PAPER CRAFT", -80995, "2011-12-09 09:27", 2.08, "16446", "UK"),
        ("581490", "22423", "CAKESTAND", 2, "2011-12-09 10:00", 12.75, "16446", "UK"),
    ])
    result = cleaning.clean_transactions(raw, rules)
    assert result.sales["stock_code"].tolist() == ["22423"]
    assert result.reversed_sales["cancel_invoice_no"].tolist() == ["C581484"]
    assert result.step_counts["fully_reversed_sales_removed"] == 1


def test_partial_return_and_other_customer_are_not_matched(rules):
    raw = make_rows([
        ("1", "A1", "X", 10, "2011-01-01 10:00", 1.0, "C1", "UK"),
        ("C2", "A1", "X", -4, "2011-01-02 10:00", 1.0, "C1", "UK"),    # partial
        ("3", "A2", "Y", 5, "2011-01-01 10:00", 1.0, "C1", "UK"),
        ("C4", "A2", "Y", -5, "2011-01-02 10:00", 1.0, "C9", "UK"),    # other customer
        ("5", "A3", "Z", 5, "2011-01-05 10:00", 1.0, "C1", "UK"),
        ("C6", "A3", "Z", -5, "2011-01-04 10:00", 1.0, "C1", "UK"),    # before sale
    ])
    result = cleaning.clean_transactions(raw, rules)
    assert result.reversed_sales.empty
    assert len(result.sales) == 3


def test_each_sale_line_is_reversed_at_most_once(rules):
    raw = make_rows([
        ("1", "A1", "X", 6, "2011-01-01 10:00", 1.0, "C1", "UK"),
        ("2", "A1", "X", 6, "2011-01-03 10:00", 1.0, "C1", "UK"),
        ("C3", "A1", "X", -6, "2011-01-04 10:00", 1.0, "C1", "UK"),
    ])
    result = cleaning.clean_transactions(raw, rules)
    # The most recent prior sale is the one reversed.
    assert result.reversed_sales["invoice_no"].tolist() == ["2"]
    assert result.sales["invoice_no"].tolist() == ["1"]


def test_missing_customer_is_never_matched(rules):
    raw = make_rows([
        ("1", "A1", "X", 6, "2011-01-01 10:00", 1.0, None, "UK"),
        ("C2", "A1", "X", -6, "2011-01-01 11:00", 1.0, None, "UK"),
    ])
    result = cleaning.clean_transactions(raw, rules)
    assert result.reversed_sales.empty


def test_invalid_rows_and_duplicates_are_removed(rules):
    raw = make_rows([
        ("1", "A1", "X", 1, "2011-01-01 10:00", 1.0, "C1", "UK"),
        ("1", "A1", "X", 1, "2011-01-01 10:00", 1.0, "C1", "UK"),  # duplicate
        ("2", "A1", "X", 1, "2011-01-01 10:00", 0.0, "C1", "UK"),  # zero price
        ("3", "A1", None, 1, "2011-01-01 10:00", 1.0, "C1", "UK"),  # no description
        ("4", "A1", "X", 1, "not a date", 1.0, "C1", "UK"),         # bad date
    ])
    result = cleaning.clean_transactions(raw, rules)
    assert result.step_counts["after_duplicate_removal"] == 4
    assert result.sales["invoice_no"].tolist() == ["1"]


def test_month_coverage_flags_truncated_boundary_months_only():
    dates = pd.Series(pd.to_datetime(["2010-12-03", "2011-01-15", "2011-12-09"]))
    coverage = cleaning.month_coverage(dates).set_index("invoice_month")
    assert coverage.loc["2010-12", "is_truncated_month"]      # data starts on the 3rd
    assert not coverage.loc["2011-01", "is_truncated_month"]  # inner month, never flagged
    assert coverage.loc["2011-12", "is_truncated_month"]      # data ends on the 9th


def test_sku_master_uses_most_frequent_description(rules):
    raw = make_rows([
        ("1", "A1", "white heart", 1, "2011-01-01 10:00", 1.0, "C1", "UK"),
        ("2", "A1", "white heart", 1, "2011-01-02 10:00", 1.0, "C1", "UK"),
        ("3", "A1", "cream heart", 1, "2011-01-03 10:00", 1.0, "C1", "UK"),
    ])
    sales = cleaning.clean_transactions(raw, rules).sales
    master = cleaning.build_sku_master(sales)
    assert master.loc[0, "description"] == "WHITE HEART"
    assert master.loc[0, "description_count"] == 2


def test_missing_required_column_raises():
    raw = make_rows([("1", "A1", "X", 1, "2011-01-01", 1.0, "C1", "UK")]).drop(columns="unit_price")
    with pytest.raises(ValueError, match="unit_price"):
        cleaning.normalize_sales(raw)


# ---------------------------------------------------------------------------
# Regression: customer 15098, 10 June 2011 (UCI Online Retail)
# ---------------------------------------------------------------------------

CUSTOMER_15098 = [
    ("556442", "22502", "PICNIC BASKET WICKER SMALL", 60, "2011-06-10 15:22", 4.95, "15098", "UK"),
    ("556444", "22502", "PICNIC BASKET WICKER 60 PIECES", 60, "2011-06-10 15:28", 649.50, "15098", "UK"),
    ("C556445", "M", "Manual", -1, "2011-06-10 15:31", 38970.0, "15098", "UK"),
    ("556446", "22502", "PICNIC BASKET WICKER 60 PIECES", 1, "2011-06-10 15:33", 649.50, "15098", "UK"),
    ("C556448", "22502", "PICNIC BASKET WICKER SMALL", -60, "2011-06-10 15:39", 4.95, "15098", "UK"),
]
MANUAL_PATH = PROJECT_ROOT / "config" / "manual_reversals.csv"


def test_cancellation_prefers_same_price_sale_over_more_recent_one(rules):
    raw = make_rows([row for row in CUSTOMER_15098 if row[0] != "C556445"])
    result = cleaning.clean_transactions(raw, rules)
    reversed_sales = result.reversed_sales
    assert reversed_sales["invoice_no"].tolist() == ["556442"]
    assert reversed_sales["match_quality"].tolist() == ["same_price"]
    assert reversed_sales["price_delta"].tolist() == [0.0]
    assert reversed_sales["cancel_unit_price"].tolist() == [4.95]


def test_customer_15098_keeps_only_the_corrected_invoice(rules):
    raw = make_rows(CUSTOMER_15098)
    result = cleaning.clean_transactions(raw, rules, cleaning.load_manual_reversals(MANUAL_PATH))
    assert result.sales["invoice_no"].tolist() == ["556446"]
    assert result.sales["revenue"].sum() == pytest.approx(649.50)
    by_type = result.reversed_sales.set_index("invoice_no")["reversal_type"].to_dict()
    assert by_type == {"556444": "manual_credit", "556442": "full_cancellation"}
    assert result.step_counts["manual_credit_reversals_removed"] == 1
    assert result.step_counts["fully_reversed_sales_removed"] == 1
    candidates = result.manual_credit_candidates
    assert candidates["credit_invoice_no"].tolist() == ["C556445"]
    assert candidates["reviewed_in_config"].tolist() == [True]


def test_price_mismatch_is_used_only_when_no_same_price_sale_exists(rules):
    raw = make_rows([
        ("1", "A1", "X", 2, "2011-01-01 10:00", 6.95, "C1", "UK"),
        ("C2", "A1", "X", -2, "2011-02-01 10:00", 5.95, "C1", "UK"),
    ])
    reversed_sales = cleaning.clean_transactions(raw, rules).reversed_sales
    assert reversed_sales["match_quality"].tolist() == ["price_mismatch"]
    assert reversed_sales["price_delta"].tolist() == [-1.0]


def test_manual_reversal_that_does_not_match_data_raises(rules):
    raw = make_rows(CUSTOMER_15098)
    reversals = cleaning.load_manual_reversals(MANUAL_PATH)
    reversals.loc[0, "credit_invoice_no"] = "C999999"
    with pytest.raises(ValueError, match="C999999"):
        cleaning.clean_transactions(raw, rules, reversals)

    reversals = cleaning.load_manual_reversals(MANUAL_PATH)
    reversals.loc[0, "unit_price"] = 1.0
    with pytest.raises(ValueError, match="matched 0 sales rows"):
        cleaning.clean_transactions(raw, rules, reversals)


def test_manual_credit_candidates_do_not_remove_anything(rules):
    raw = make_rows(CUSTOMER_15098)
    result = cleaning.clean_transactions(raw, rules)  # no reviewed list supplied
    assert "556444" in result.sales["invoice_no"].tolist()
    assert result.manual_credit_candidates["reviewed_in_config"].tolist() == [False]


def test_price_anomaly_report_flags_outlier_line():
    sales = pd.DataFrame({
        "invoice_no": ["1", "2", "3", "4"],
        "stock_code": ["A1"] * 4,
        "description": ["X"] * 4,
        "quantity": [10, 10, 10, 1],
        "unit_price": [4.95, 4.95, 5.10, 649.50],
        "invoice_date": pd.to_datetime(["2011-01-01"] * 4),
        "customer_id": ["C1"] * 4,
    })
    report = cleaning.find_price_anomalies(sales)
    assert report["invoice_no"].tolist() == ["4"]
    assert report.loc[0, "price_ratio"] > 10


# ---------------------------------------------------------------------------
# Rule-table validation
# ---------------------------------------------------------------------------

def write_rules(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rules.csv"
    path.write_text("stock_code,match_type,category,reason\n" + body)
    return path


def test_blank_prefix_rule_is_rejected(tmp_path):
    path = write_rules(tmp_path, ",prefix,fee,blank would match everything\n")
    with pytest.raises(ValueError, match="Blank stock_code"):
        cleaning.load_non_product_rules(path)


def test_duplicate_rule_is_rejected(tmp_path):
    path = write_rules(tmp_path, "POST,exact,shipping,a\npost,exact,shipping,b\n")
    with pytest.raises(ValueError, match="Duplicate"):
        cleaning.load_non_product_rules(path)


def test_overlapping_rules_are_rejected(tmp_path):
    path = write_rules(tmp_path, "GIFT_,prefix,x,a\nGIFT_0001_10,exact,x,b\n")
    with pytest.raises(ValueError, match="Overlapping"):
        cleaning.load_non_product_rules(path)


def test_unknown_match_type_is_rejected(tmp_path):
    path = write_rules(tmp_path, "POST,contains,shipping,a\n")
    with pytest.raises(ValueError, match="match_type"):
        cleaning.load_non_product_rules(path)


def test_project_config_files_are_valid():
    cleaning.load_non_product_rules(RULES_PATH)
    assert len(cleaning.load_manual_reversals(MANUAL_PATH)) >= 1


def test_header_only_manual_reversal_file_removes_nothing(tmp_path, rules):
    path = tmp_path / "manual.csv"
    path.write_text("invoice_no,stock_code,quantity,unit_price,credit_invoice_no,reason\n")
    reversals = cleaning.load_manual_reversals(path)
    result = cleaning.clean_transactions(make_rows(CUSTOMER_15098), rules, reversals)
    assert result.step_counts["manual_credit_reversals_removed"] == 0
    assert "556444" in result.sales["invoice_no"].tolist()
