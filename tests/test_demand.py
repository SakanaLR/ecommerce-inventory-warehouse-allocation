from __future__ import annotations

import pandas as pd
import pytest

from retail_analytics import demand

MONTHS = ["2011-01", "2011-02", "2011-03", "2011-04"]


def monthly(rows):
    frame = pd.DataFrame(rows, columns=["stock_code", "invoice_month", "monthly_units", "monthly_revenue"])
    frame["order_count"] = 1
    frame["avg_unit_price"] = frame["monthly_revenue"] / frame["monthly_units"]
    return frame


def master(codes):
    return pd.DataFrame({"stock_code": codes, "description": [f"ITEM {c}" for c in codes]})


def test_full_months_drops_truncated_months():
    coverage = pd.DataFrame({
        "invoice_month": ["2010-12", "2011-01", "2011-12"],
        "is_truncated_month": [False, False, True],
    })
    assert demand.full_months(coverage) == ["2010-12", "2011-01"]


def test_panel_zero_fills_from_first_sale_month():
    data = monthly([
        ("A", "2011-02", 10, 20.0),
        ("A", "2011-04", 20, 40.0),
    ])
    panel = demand.build_demand_panel(data, MONTHS)
    assert panel["invoice_month"].tolist() == ["2011-02", "2011-03", "2011-04"]
    assert panel["monthly_units"].tolist() == [10, 0, 20]
    assert panel["is_zero_filled"].tolist() == [False, True, False]


def test_truncated_month_is_excluded_but_counts_toward_totals():
    data = monthly([
        ("A", "2011-03", 10, 10.0),
        ("A", "2011-05", 90, 90.0),  # truncated month, outside MONTHS
    ])
    profile = demand.build_sku_profile(data, master(["A"]), MONTHS)
    row = profile.iloc[0]
    assert row["total_units"] == 100
    assert row["months_in_window"] == 2
    assert row["avg_monthly_units"] == pytest.approx(5.0)  # (10 + 0) / 2
    assert row["avg_monthly_units_active"] == pytest.approx(50.0)


def test_zero_filled_mean_std_and_cv():
    data = monthly([
        ("A", "2011-01", 10, 10.0),
        ("A", "2011-04", 20, 20.0),
    ])
    row = demand.build_sku_profile(data, master(["A"]), MONTHS).iloc[0]
    series = pd.Series([10, 0, 0, 20])
    assert row["avg_monthly_units"] == pytest.approx(7.5)
    assert row["std_monthly_units"] == pytest.approx(series.std(ddof=1))
    assert row["demand_cv"] == pytest.approx(series.std(ddof=1) / 7.5)
    assert row["zero_month_share"] == pytest.approx(0.5)
    assert not row["short_history"]


def test_short_history_and_truncated_only_skus_are_flagged():
    data = monthly([
        ("NEW", "2011-04", 5, 5.0),
        ("LATE", "2011-05", 7, 7.0),  # only in a truncated month
    ])
    profile = demand.build_sku_profile(data, master(["NEW", "LATE"]), MONTHS).set_index("stock_code")
    assert profile.loc["NEW", "short_history"]
    assert profile.loc["NEW", "demand_cv"] == 0
    assert profile.loc["LATE", "no_full_month_sales"]
    assert profile.loc["LATE", "months_in_window"] == 0
    assert profile.loc["LATE", "avg_monthly_units"] == 0
    assert profile.loc["LATE", "total_units"] == 7


def test_classification_uses_absolute_cv_and_short_history():
    profile = pd.DataFrame({
        "stock_code": list("ABCDEF"),
        "total_revenue": [1000.0, 10.0, 10.0, 10.0, 1.0, 1000.0],
        "total_units": [100, 500, 500, 500, 1, 5],
        "demand_cv": [3.0, 0.4, 1.5, 0.2, 0.0, 0.0],
        "short_history": [False, False, False, True, False, True],
    })
    classified, thresholds = demand.classify_skus(
        profile, revenue_quantile=0.8, volume_quantile=0.4, long_tail_quantile=0.2, volatility_cv=1.0
    )
    assert thresholds["volatility_cv"] == 1.0
    assert classified.set_index("stock_code")["sku_class"].to_dict() == {
        "A": "High-Revenue Priority",
        "B": "High-Turnover Stable",
        "C": "High-Turnover Volatile",
        "D": "High-Turnover Volatile",   # short history is never "stable"
        "E": "Long-Tail",
        # Revenue rank wins even when short_history=True and demand_cv is
        # degenerate (0.0): this is the documented precedence in
        # classify_skus's docstring, not an accident of rule ordering. It also
        # means the short_history flag is informational only for this tier —
        # nothing downstream should assume a short-history SKU's demand_cv is
        # statistically meaningful just because it landed in Priority.
        "F": "High-Revenue Priority",
    }
    assert classified["recommended_action"].notna().all()
