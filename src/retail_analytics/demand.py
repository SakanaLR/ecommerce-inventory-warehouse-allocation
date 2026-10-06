"""Monthly demand basis and SKU classification.

Demand statistics are computed on a SKU x month panel that
- keeps only months fully covered by the data (truncated boundary months are dropped), and
- starts at each SKU's first sale month and fills months without sales with zero.

Revenue and unit totals still use every month, so they reconcile to clean sales.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRIORITY_CLASS = "High-Revenue Priority"
STABLE_CLASS = "High-Turnover Stable"
VOLATILE_CLASS = "High-Turnover Volatile"
LONG_TAIL_CLASS = "Long-Tail"
REGULAR_CLASS = "Regular"

ACTION_MAPPING = {
    PRIORITY_CLASS: "Prioritize inventory monitoring and avoid stockouts",
    STABLE_CLASS: "Keep stable local warehouse inventory",
    VOLATILE_CLASS: "Monitor closely and replenish in smaller batches",
    LONG_TAIL_CLASS: "Limit stock and avoid excessive local warehouse space",
    REGULAR_CLASS: "Maintain standard replenishment review",
}


def full_months(month_coverage: pd.DataFrame) -> list[str]:
    """Months not truncated by the data's start or end date, in order."""
    flag = month_coverage["is_truncated_month"].astype(str).str.lower().isin(["true", "1"])
    return sorted(month_coverage.loc[~flag, "invoice_month"].astype(str))


def build_demand_panel(monthly_sku_sales: pd.DataFrame, months: list[str]) -> pd.DataFrame:
    """SKU x month panel over ``months``, zero-filled from each SKU's first sale month.

    The first sale month is taken from all months, so a SKU first sold in a
    truncated opening month still starts at the first full month. SKUs whose
    sales fall only in truncated months get no rows.
    """
    months = sorted(months)
    monthly = monthly_sku_sales.assign(invoice_month=monthly_sku_sales["invoice_month"].astype(str))
    first_month = monthly.groupby("stock_code")["invoice_month"].min()
    in_window = monthly[monthly["invoice_month"].isin(months)]
    skus = sorted(in_window["stock_code"].unique())

    grid = pd.MultiIndex.from_product([skus, months], names=["stock_code", "invoice_month"]).to_frame(index=False)
    grid = grid[grid["invoice_month"] >= grid["stock_code"].map(first_month)]
    panel = grid.merge(
        in_window[["stock_code", "invoice_month", "monthly_units", "monthly_revenue"]],
        on=["stock_code", "invoice_month"],
        how="left",
        validate="one_to_one",
    )
    panel["is_zero_filled"] = panel["monthly_units"].isna()
    panel[["monthly_units", "monthly_revenue"]] = panel[["monthly_units", "monthly_revenue"]].fillna(0)
    return panel.sort_values(["stock_code", "invoice_month"]).reset_index(drop=True)


def build_sku_profile(
    monthly_sku_sales: pd.DataFrame,
    sku_master: pd.DataFrame,
    months: list[str],
    min_history_months: int = 3,
) -> pd.DataFrame:
    """One row per SKU with totals (all months) and demand statistics (panel)."""
    totals = monthly_sku_sales.groupby("stock_code", as_index=False).agg(
        total_units=("monthly_units", "sum"),
        total_revenue=("monthly_revenue", "sum"),
        active_months=("invoice_month", "nunique"),
        avg_monthly_units_active=("monthly_units", "mean"),
        avg_unit_price=("avg_unit_price", "mean"),
        total_orders=("order_count", "sum"),
    )

    panel = build_demand_panel(monthly_sku_sales, months)
    stats = panel.groupby("stock_code").agg(
        months_in_window=("invoice_month", "size"),
        zero_months_in_window=("is_zero_filled", "sum"),
        avg_monthly_units=("monthly_units", "mean"),
        std_monthly_units=("monthly_units", "std"),
    )
    profile = totals.merge(stats, on="stock_code", how="left", validate="one_to_one")

    profile["no_full_month_sales"] = profile["months_in_window"].isna()
    profile["months_in_window"] = profile["months_in_window"].fillna(0).astype(int)
    profile["zero_months_in_window"] = profile["zero_months_in_window"].fillna(0).astype(int)
    profile["avg_monthly_units"] = profile["avg_monthly_units"].fillna(0.0)
    # A single observation has no spread; treat it as zero, as before.
    profile["std_monthly_units"] = profile["std_monthly_units"].fillna(0.0)
    profile["zero_month_share"] = np.where(
        profile["months_in_window"] > 0,
        profile["zero_months_in_window"] / profile["months_in_window"].where(profile["months_in_window"] > 0, 1),
        np.nan,
    )
    profile["demand_cv"] = np.where(
        profile["avg_monthly_units"] > 0,
        profile["std_monthly_units"] / profile["avg_monthly_units"].where(profile["avg_monthly_units"] > 0, 1),
        0.0,
    )
    profile["short_history"] = profile["months_in_window"] < min_history_months

    profile = profile.merge(
        sku_master[["stock_code", "description"]], on="stock_code", how="left", validate="one_to_one"
    )
    return profile[
        [
            "stock_code", "description", "total_units", "total_revenue", "total_orders",
            "avg_unit_price", "active_months", "months_in_window", "zero_months_in_window",
            "zero_month_share", "avg_monthly_units", "avg_monthly_units_active",
            "std_monthly_units", "demand_cv", "short_history", "no_full_month_sales",
        ]
    ]


def classify_skus(
    profile: pd.DataFrame,
    revenue_quantile: float = 0.80,
    volume_quantile: float = 0.80,
    long_tail_quantile: float = 0.30,
    volatility_cv: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Assign SKU classes; the first matching rule wins.

    1. High-Revenue Priority: total revenue at or above the revenue quantile.
    2. High-Turnover: total units at or above the volume quantile.
       Volatile when demand CV is above ``volatility_cv`` or history is short;
       otherwise Stable.
    3. Long-Tail: total units at or below the long-tail quantile.
    4. Regular: everything else.
    """
    thresholds = {
        "revenue_threshold": float(profile["total_revenue"].quantile(revenue_quantile)),
        "volume_threshold": float(profile["total_units"].quantile(volume_quantile)),
        "long_tail_threshold": float(profile["total_units"].quantile(long_tail_quantile)),
        "volatility_cv": float(volatility_cv),
    }
    high_revenue = profile["total_revenue"] >= thresholds["revenue_threshold"]
    high_volume = profile["total_units"] >= thresholds["volume_threshold"]
    volatile = (profile["demand_cv"] > volatility_cv) | profile["short_history"]
    long_tail = profile["total_units"] <= thresholds["long_tail_threshold"]

    sku_class = np.select(
        [high_revenue, high_volume & volatile, high_volume, long_tail],
        [PRIORITY_CLASS, VOLATILE_CLASS, STABLE_CLASS, LONG_TAIL_CLASS],
        default=REGULAR_CLASS,
    )
    classified = profile.assign(sku_class=sku_class)
    classified["recommended_action"] = classified["sku_class"].map(ACTION_MAPPING)
    return classified, thresholds
