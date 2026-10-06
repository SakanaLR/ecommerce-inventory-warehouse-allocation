"""SKU Analyzer -- search, filter, and drill into a single SKU.

Read-only. See ``docs/app_product_spec.md`` §2 for the page spec.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from retail_analytics import dashboard_data as dd

st.set_page_config(page_title="SKU Analyzer", page_icon="🔍", layout="wide")

st.title("🔍 SKU Analyzer")
st.caption("Demonstration analytics on a public dataset. Not a calibrated operational system.")

try:
    profile = dd.load_sku_profile(PROJECT_ROOT)
    month_demand = dd.load_sku_month_demand(PROJECT_ROOT)
except dd.DashboardDataError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.header("Filters")
    st.caption(
        "Showing all SKUs by default. Search by code/description, or combine the "
        "filters below (all must match) — for example, pick a risk status to "
        "focus on SKUs that may need attention."
    )
    query = st.text_input("Search stock code or description", key="sku_search")
    sku_classes = st.multiselect(
        "SKU class", sorted(profile["sku_class"].dropna().unique()), key="sku_class_filter"
    )
    risks = st.multiselect(
        "Inventory risk (simulated)", sorted(profile["inventory_risk"].dropna().unique()),
        key="inventory_risk_filter",
    )
    strategies = st.multiselect(
        "Warehouse strategy (simulated)", sorted(profile["warehouse_strategy"].dropna().unique()),
        key="warehouse_strategy_filter",
    )

filtered = dd.filter_sku_profile(
    profile,
    query=query,
    sku_classes=sku_classes or None,
    risks=risks or None,
    strategies=strategies or None,
)

st.subheader(f"Matching SKUs ({len(filtered):,} of {len(profile):,})")

if filtered.empty:
    active_filters = {
        "search": query or "(none)",
        "SKU class": sku_classes or "(none)",
        "inventory risk": risks or "(none)",
        "warehouse strategy": strategies or "(none)",
    }
    st.info(f"No SKUs match the current filters: {active_filters}")
else:
    display_columns = [
        "stock_code", "description", "sku_class", "total_revenue", "total_units",
        "months_in_window", "short_history", "demand_cv", "inventory_risk", "warehouse_strategy",
    ]
    display = filtered.loc[:, display_columns].copy()
    display["total_revenue"] = display["total_revenue"].map(dd.format_gbp)
    display["total_units"] = display["total_units"].map(dd.format_units)
    display["short_history"] = display["short_history"].map(
        lambda value: "Not available" if pd.isna(value) else "Yes" if bool(value) else "No"
    )
    display["demand_cv"] = display["demand_cv"].map(dd.format_ratio)
    display = display.rename(columns={
        "stock_code": "SKU", "description": "Description", "sku_class": "SKU class",
        "total_revenue": "Historical revenue (GBP)", "total_units": "Historical units",
        "months_in_window": "Months in window", "short_history": "Short history",
        "demand_cv": "Demand CV (monthly sales)", "inventory_risk": "Inventory risk (simulated)",
        "warehouse_strategy": "Warehouse strategy (simulated)",
    })
    st.dataframe(display, hide_index=True, width="stretch")

    st.divider()
    code_to_description = dict(zip(filtered["stock_code"], filtered["description"]))
    selected_code = st.selectbox(
        "Select a SKU for detail", filtered["stock_code"].tolist(),
        format_func=lambda code: f"{code} — {code_to_description.get(code, '')}",
        key="sku_detail_selector",
    )

    if selected_code:
        row = filtered.loc[filtered["stock_code"] == selected_code].iloc[0]
        st.markdown(f"### {selected_code} — {row['description']}")

        notice = dd.short_history_notice(row)
        if notice:
            st.warning(notice)

        st.subheader("📈 Historical monthly sales")
        trend = dd.sku_month_trend(month_demand, selected_code)
        if trend.empty:
            st.info("No monthly demand history is available for this SKU.")
        else:
            chart_data = trend.set_index("invoice_month")[["monthly_units"]]
            st.caption("Chart unit: historical units sold per month. Zero-filled months are marked below.")
            st.line_chart(chart_data)
            zero_filled_months = trend.loc[trend["is_zero_filled"], "invoice_month"].tolist()
            if zero_filled_months:
                st.caption(
                    f"Zero-filled months (no recorded sales, not missing data): "
                    f"{', '.join(zero_filled_months)}"
                )

        st.subheader("🧪 Simulated inventory position")
        st.caption("Demonstration simulation on assumed cost/lead-time/service-level parameters, not real inventory records.")

        sim1, sim2 = st.columns(2)
        sim1.metric("Current inventory (simulated units)", dd.format_units(row["current_inventory"]),
                    help=dd.SKU_DETAIL_METRIC_HELP["current_inventory"])
        sim2.metric("Safety stock (simulated units)", dd.format_units(row["safety_stock"]),
                    help=dd.SKU_DETAIL_METRIC_HELP["safety_stock"])
        sim3, sim4 = st.columns(2)
        sim3.metric("Reorder point (simulated units)", dd.format_units(row["reorder_point"]),
                    help=dd.SKU_DETAIL_METRIC_HELP["reorder_point"])
        sim4.metric("EOQ (simulated order units)", dd.format_units(row["economic_order_qty"]),
                    help=dd.SKU_DETAIL_METRIC_HELP["economic_order_qty"])

        sim5, sim6 = st.columns(2)
        sim5.metric(
            "Recommended replenishment (simulated units)",
            dd.format_units(row["recommended_replenishment_qty"]),
            help=dd.SKU_DETAIL_METRIC_HELP["recommended_replenishment_qty"],
        )
        coverage = row["inventory_coverage_days"]
        coverage_display = (
            "∞ (no demand)" if pd.notna(coverage) and coverage == float("inf")
            else dd.format_units(coverage)
        )
        sim6.metric("Inventory coverage (simulated days)", coverage_display,
                    help=dd.SKU_DETAIL_METRIC_HELP["inventory_coverage_days"])

        st.markdown(f"**Inventory risk (simulated):** {row['inventory_risk']}")
        if row["inventory_risk"] == "Normal":
            st.caption(dd.normal_risk_disclaimer())
