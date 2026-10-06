"""Tests for the merchant-app data access layer (src/retail_analytics/dashboard_data.py).

No Streamlit runtime is needed for any test in this file -- these test the
pure data loading/validation/aggregation functions directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from retail_analytics import dashboard_data as dd  # noqa: E402


def _profile_row(**overrides) -> dict:
    row = {
        "stock_code": "A0001", "description": "WIDGET", "total_units": 100, "total_revenue": 200.0,
        "total_orders": 10, "avg_unit_price": 2.0, "months_in_window": 12, "zero_month_share": 0.1,
        "avg_monthly_units": 8.3, "std_monthly_units": 2.0, "demand_cv": 0.24, "short_history": False,
        "no_full_month_sales": False, "sku_class": "Regular", "recommended_action": "Maintain",
        "supplier_lead_time_days": 14, "unit_cost": 1.0, "safety_stock": 5, "reorder_point": 20,
        "economic_order_qty": 30, "eoq_capped": False, "max_stock_level": 50, "current_inventory": 25,
        "recommended_replenishment_qty": 0, "inventory_coverage_days": 30.0, "inventory_risk": "Normal",
        "excess_units": 0.0, "warehouse_strategy": "Standard Replenishment Review",
    }
    row.update(overrides)
    return row


def make_profile(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=dd.REQUIRED_SKU_PROFILE_COLUMNS)
    return pd.DataFrame(rows)


@pytest.fixture
def small_profile() -> pd.DataFrame:
    return make_profile([
        _profile_row(stock_code="A0001", description="WIDGET", total_revenue=200.0,
                     sku_class="Regular", inventory_risk="Normal",
                     warehouse_strategy="Standard Replenishment Review"),
        _profile_row(stock_code="A0002", description="GADGET", total_revenue=500.0,
                     sku_class="High-Revenue Priority", inventory_risk="Stockout Risk",
                     warehouse_strategy="Local Warehouse Priority", short_history=True,
                     months_in_window=1),
        _profile_row(stock_code="A0003", description="THINGAMAJIG", total_revenue=50.0,
                     sku_class="Long-Tail", inventory_risk="Overstock Risk",
                     warehouse_strategy="External or Limited Stock Strategy"),
    ])


# ---------------------------------------------------------------------------
# Schema validation, including the privacy denylist
# ---------------------------------------------------------------------------

def test_validate_schema_passes_for_a_complete_profile(small_profile):
    dd.validate_schema(small_profile, dd.REQUIRED_SKU_PROFILE_COLUMNS, "small_profile")


def test_validate_schema_reports_missing_columns_by_name():
    df = pd.DataFrame({"stock_code": ["A"]})
    with pytest.raises(dd.DashboardDataError, match="total_revenue"):
        dd.validate_schema(df, dd.REQUIRED_SKU_PROFILE_COLUMNS, "incomplete")


def test_validate_schema_rejects_forbidden_column_before_reporting_missing_columns():
    # The raw header must be checked before the file is narrowed to its data
    # contract or diagnosed as incomplete; otherwise a sensitive input could be
    # silently hidden by a future implementation change.
    df = pd.DataFrame({"customer_id": ["12345"]})
    with pytest.raises(dd.DashboardDataError, match="customer_id"):
        dd.validate_schema(df, dd.REQUIRED_SKU_PROFILE_COLUMNS, "unsafe_incomplete")


@pytest.mark.parametrize("forbidden_column", sorted(dd.FORBIDDEN_COLUMNS))
def test_validate_schema_rejects_every_forbidden_column_individually(small_profile, forbidden_column):
    tainted = small_profile.copy()
    tainted[forbidden_column] = "leak"
    with pytest.raises(dd.DashboardDataError, match=forbidden_column):
        dd.validate_schema(tainted, dd.REQUIRED_SKU_PROFILE_COLUMNS, "tainted")


def test_validate_schema_rejects_forbidden_column_even_when_required_columns_present(small_profile):
    tainted = small_profile.assign(customer_id="12345")
    with pytest.raises(dd.DashboardDataError):
        dd.validate_schema(tainted, dd.REQUIRED_SKU_PROFILE_COLUMNS, "tainted")


# ---------------------------------------------------------------------------
# File loading: missing file / missing column / forbidden column / empty file
# ---------------------------------------------------------------------------

def test_load_sku_profile_missing_file_raises_dashboard_data_error(tmp_path):
    with pytest.raises(dd.DashboardDataError, match="Missing data file"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_missing_column_names_it_in_the_error(tmp_path):
    (tmp_path / "outputs").mkdir()
    pd.DataFrame({"stock_code": ["A"]}).to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    with pytest.raises(dd.DashboardDataError, match="total_revenue"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_rejects_a_file_containing_a_forbidden_column(tmp_path):
    (tmp_path / "outputs").mkdir()
    df = make_profile([_profile_row()])
    df["customer_id"] = "12345"
    df.to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    with pytest.raises(dd.DashboardDataError, match="customer_id"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_rejects_a_forbidden_column_before_missing_column_error(tmp_path):
    (tmp_path / "outputs").mkdir()
    pd.DataFrame({"customer_id": ["12345"]}).to_csv(
        tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False
    )
    with pytest.raises(dd.DashboardDataError, match="customer_id"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_empty_file_loads_without_error(tmp_path):
    (tmp_path / "outputs").mkdir()
    make_profile([]).to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    profile = dd.load_sku_profile(project_root=tmp_path)
    assert profile.empty
    assert dd.simulated_risk_counts(profile) == {}
    assert dd.historical_overview_metrics(profile)["sku_count"] == 0
    assert dd.historical_overview_metrics(profile)["total_revenue_gbp"] == 0


def test_load_sku_profile_rejects_a_zero_byte_file_with_a_clear_error(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "sku_inventory_simulation.csv").write_bytes(b"")
    with pytest.raises(dd.DashboardDataError, match="Data file is empty"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_rejects_non_numeric_required_data(tmp_path):
    (tmp_path / "outputs").mkdir()
    make_profile([_profile_row(total_revenue="not-a-number")]).to_csv(
        tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False
    )
    with pytest.raises(dd.DashboardDataError, match="total_revenue"):
        dd.load_sku_profile(project_root=tmp_path)


def test_load_sku_profile_rejects_duplicate_stock_code_before_aggregation(tmp_path):
    (tmp_path / "outputs").mkdir()
    make_profile([_profile_row(), _profile_row(description="DUPLICATE")]).to_csv(
        tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False
    )
    with pytest.raises(dd.DashboardDataError, match="duplicate row key"):
        dd.load_sku_profile(project_root=tmp_path)


def test_loader_returns_only_approved_columns_and_a_new_dataframe_per_call(tmp_path):
    (tmp_path / "outputs").mkdir()
    unsafe_extra = make_profile([_profile_row()])
    unsafe_extra["merchant_private_note"] = "do not show"
    unsafe_extra.to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    first = dd.load_sku_profile(project_root=tmp_path)
    first.loc[0, "description"] = "page mutation"
    second = dd.load_sku_profile(project_root=tmp_path)
    assert list(second.columns) == dd.REQUIRED_SKU_PROFILE_COLUMNS
    assert "merchant_private_note" not in second.columns
    assert second.loc[0, "description"] == "WIDGET"


def test_load_real_sku_profile_from_repo_matches_known_totals():
    profile = dd.load_sku_profile()
    hist = dd.historical_overview_metrics(profile)
    assert hist["sku_count"] == 3790
    assert hist["total_revenue_gbp"] == pytest.approx(9_818_872.18, abs=0.01)


def test_all_real_loaders_succeed_against_the_repo():
    assert not dd.load_sku_month_demand().empty
    assert not dd.load_month_coverage().empty
    assert not dd.load_data_quality_summary().empty
    assert not dd.load_warehouse_allocation_summary().empty
    kpi = dd.load_management_kpi_summary()
    assert isinstance(kpi, dict) and kpi
    working_capital = dd.load_working_capital_summary()
    assert isinstance(working_capital, dict) and working_capital
    assert working_capital["total_estimated_inventory_value"] == pytest.approx(1_805_589.48, abs=0.01)


def test_load_sku_month_demand_rejects_duplicate_sku_month_keys(tmp_path):
    path = tmp_path / "data" / "processed"
    path.mkdir(parents=True)
    pd.DataFrame({
        "stock_code": ["A", "A"], "invoice_month": ["2011-01", "2011-01"],
        "monthly_units": [1, 2], "monthly_revenue": [1.0, 2.0],
        "is_zero_filled": [False, False],
    }).to_csv(path / "sku_month_demand.csv", index=False)
    with pytest.raises(dd.DashboardDataError, match="duplicate row key"):
        dd.load_sku_month_demand(project_root=tmp_path)


# ---------------------------------------------------------------------------
# Aggregation and formatting
# ---------------------------------------------------------------------------

def test_historical_overview_metrics(small_profile):
    hist = dd.historical_overview_metrics(small_profile)
    assert hist["sku_count"] == 3
    assert hist["total_revenue_gbp"] == pytest.approx(750.0)
    assert hist["sku_class_counts"] == {"Regular": 1, "High-Revenue Priority": 1, "Long-Tail": 1}


def test_simulated_risk_counts(small_profile):
    assert dd.simulated_risk_counts(small_profile) == {
        "Normal": 1, "Stockout Risk": 1, "Overstock Risk": 1,
    }


def test_simulated_warehouse_strategy_counts(small_profile):
    counts = dd.simulated_warehouse_strategy_counts(small_profile)
    assert counts["Standard Replenishment Review"] == 1
    assert counts["Local Warehouse Priority"] == 1


def test_format_gbp():
    assert dd.format_gbp(1234.5) == "£1,234.50"
    assert dd.format_gbp(0) == "£0.00"


def test_display_formatters_keep_missing_values_distinct_from_zero():
    assert dd.format_gbp(float("nan")) == "Not available"
    assert dd.format_units(None) == "Not available"
    assert dd.format_percent(float("nan")) == "Not available"
    assert dd.format_ratio(float("nan")) == "Not available"


def test_format_ratio_matches_the_repos_own_plain_decimal_convention():
    # README.md describes demand_cv as a plain ratio ("median CV of 1.01"), not a
    # percentage -- this keeps the app's own rendering consistent with that.
    assert dd.format_ratio(1.01) == "1.01"
    assert dd.format_ratio(0.840224) == "0.84"
    assert dd.format_ratio(None) == "Not available"


# ---------------------------------------------------------------------------
# Historical and simulated metrics must never be computed from each other's
# columns -- this is the P0 "don't mix historical facts with simulated
# numbers" requirement, checked mechanically rather than just by convention.
# ---------------------------------------------------------------------------

def test_historical_metrics_are_unaffected_by_simulated_columns(small_profile):
    before = dd.historical_overview_metrics(small_profile)
    mutated = small_profile.copy()
    mutated["inventory_risk"] = "Overstock Risk"
    mutated["current_inventory"] = 999_999
    mutated["warehouse_strategy"] = "Overstock Review / Reduce Replenishment"
    after = dd.historical_overview_metrics(mutated)
    assert before == after


def test_simulated_metrics_are_unaffected_by_historical_columns(small_profile):
    before_risk = dd.simulated_risk_counts(small_profile)
    before_strategy = dd.simulated_warehouse_strategy_counts(small_profile)
    mutated = small_profile.copy()
    mutated["total_revenue"] = 0.0
    mutated["total_units"] = 0
    mutated["sku_class"] = "Long-Tail"
    assert dd.simulated_risk_counts(mutated) == before_risk
    assert dd.simulated_warehouse_strategy_counts(mutated) == before_strategy


# ---------------------------------------------------------------------------
# Search and combined filtering
# ---------------------------------------------------------------------------

def test_filter_sku_profile_search_matches_stock_code_or_description(small_profile):
    assert set(dd.filter_sku_profile(small_profile, query="A0002")["stock_code"]) == {"A0002"}
    assert set(dd.filter_sku_profile(small_profile, query="gadget")["stock_code"]) == {"A0002"}


def test_filter_sku_profile_combines_filters_with_and_semantics(small_profile):
    result = dd.filter_sku_profile(
        small_profile, sku_classes=["Regular", "Long-Tail"], risks=["Overstock Risk"]
    )
    assert set(result["stock_code"]) == {"A0003"}


def test_filter_sku_profile_no_filters_returns_everything(small_profile):
    assert len(dd.filter_sku_profile(small_profile)) == len(small_profile)


def test_filter_sku_profile_blank_query_returns_everything(small_profile):
    assert len(dd.filter_sku_profile(small_profile, query="   ")) == len(small_profile)


def test_filter_sku_profile_no_match_returns_empty_dataframe_not_error(small_profile):
    result = dd.filter_sku_profile(small_profile, query="doesnotexist_zzz")
    assert result.empty


# ---------------------------------------------------------------------------
# short_history notice logic
# ---------------------------------------------------------------------------

def test_short_history_notice_present_and_mentions_month_count():
    row = pd.Series(_profile_row(short_history=True, months_in_window=1))
    notice = dd.short_history_notice(row)
    assert notice is not None
    assert "1 month" in notice


def test_short_history_notice_absent_for_long_history_sku():
    row = pd.Series(_profile_row(short_history=False))
    assert dd.short_history_notice(row) is None


def test_normal_risk_disclaimer_does_not_claim_confirmed_good_performance():
    text = dd.normal_risk_disclaimer().lower()
    assert "not a confirmed" in text or "not confirmed" in text


# ---------------------------------------------------------------------------
# short_history_notice boundary fixtures: required fields that are *present*
# (pass schema validation, which does not require non-null) but *empty* --
# these bypass the CSV loader entirely, the same way a page's own call to this
# pure function would if a row happened to carry a missing flag/count.
# ---------------------------------------------------------------------------

def test_short_history_notice_handles_a_missing_short_history_flag_without_crashing():
    # short_history is a nullable "boolean" column after loading; bool(pd.NA)
    # raises TypeError, so this must not reach a raw bool() cast.
    row = pd.Series(_profile_row(short_history=pd.NA, months_in_window=12))
    assert dd.short_history_notice(row) is None


def test_short_history_notice_handles_a_missing_months_in_window_without_crashing():
    # months_in_window is numeric-but-nullable; int(float("nan")) raises
    # ValueError, so this must not reach a raw int() cast either.
    row = pd.Series(_profile_row(short_history=True, months_in_window=float("nan")))
    notice = dd.short_history_notice(row)
    assert notice is not None
    assert "month count is not available" in notice
    assert "0 month" not in notice


def test_simulated_metric_hint_points_readers_to_the_model_and_data_notes_page():
    hint = dd.simulated_metric_hint().lower()
    assert "simulated" in hint
    assert "model & data notes" in hint


def test_sku_detail_metric_help_covers_every_simulated_metric_with_distinct_text():
    expected_keys = {
        "current_inventory", "safety_stock", "reorder_point",
        "economic_order_qty", "recommended_replenishment_qty", "inventory_coverage_days",
    }
    assert set(dd.SKU_DETAIL_METRIC_HELP) == expected_keys
    texts = list(dd.SKU_DETAIL_METRIC_HELP.values())
    assert all(isinstance(text, str) and text.strip() for text in texts)
    assert len(set(texts)) == len(texts)  # no copy-pasted duplicate explanations


# ---------------------------------------------------------------------------
# Monthly trend
# ---------------------------------------------------------------------------

def test_sku_month_trend_filters_to_one_sku_and_sorts_by_month():
    demand = pd.DataFrame({
        "stock_code": ["A", "A", "B"],
        "invoice_month": ["2011-02", "2011-01", "2011-01"],
        "monthly_units": [5, 3, 9],
        "monthly_revenue": [10.0, 6.0, 18.0],
        "is_zero_filled": [False, False, False],
    })
    trend = dd.sku_month_trend(demand, "A")
    assert trend["invoice_month"].tolist() == ["2011-01", "2011-02"]
    assert set(trend["stock_code"]) == {"A"}


def test_sku_month_trend_sorts_by_actual_month_not_lexical_input_order():
    demand = pd.DataFrame({
        "stock_code": ["A", "A", "A"],
        "invoice_month": ["2011-10", "2011-02", "2011-01"],
        "monthly_units": [1, 2, 3], "monthly_revenue": [1.0, 2.0, 3.0],
        "is_zero_filled": [False, False, False],
    })
    assert dd.sku_month_trend(demand, "A")["invoice_month"].tolist() == [
        "2011-01", "2011-02", "2011-10"
    ]


# ---------------------------------------------------------------------------
# Data freshness / row-count consistency notes (advisory, not blocking)
# ---------------------------------------------------------------------------

def test_data_freshness_notes_flags_a_row_count_mismatch(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "data" / "processed").mkdir(parents=True)
    pd.DataFrame({"a": [1, 2, 3]}).to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    pd.DataFrame({"a": [1, 2]}).to_csv(tmp_path / "outputs" / "sku_profile_classification.csv", index=False)
    notes = dd.data_freshness_notes(project_root=tmp_path)
    assert notes["row_count_warning"] is not None
    assert "3 rows" in notes["row_count_warning"]
    assert "2 rows" in notes["row_count_warning"]


def test_data_freshness_notes_no_warning_when_counts_match(tmp_path):
    (tmp_path / "outputs").mkdir()
    pd.DataFrame({"a": [1, 2]}).to_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", index=False)
    pd.DataFrame({"a": [1, 2]}).to_csv(tmp_path / "outputs" / "sku_profile_classification.csv", index=False)
    notes = dd.data_freshness_notes(project_root=tmp_path)
    assert notes["row_count_warning"] is None


def test_data_freshness_notes_missing_files_do_not_raise(tmp_path):
    notes = dd.data_freshness_notes(project_root=tmp_path)
    assert notes["row_count_warning"] is None
    assert notes["files"] == {}
