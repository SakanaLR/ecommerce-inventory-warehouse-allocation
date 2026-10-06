"""Merchant Inventory Overview -- the app's landing page.

Read-only. Reads already-generated CSVs via
``retail_analytics.dashboard_data``; never re-runs the cleaning/demand/
simulation pipeline and never writes anything. See
``docs/app_product_spec.md`` for the product spec this implements.
"""
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from retail_analytics import dashboard_data as dd

st.set_page_config(page_title="Merchant Inventory Overview", page_icon="📊", layout="wide")

st.title("📊 Merchant Inventory Overview")
st.caption(
    "Demonstration analytics on a public dataset. This is not a calibrated operational "
    "system -- see the **Model & Data Notes** page for what is real history and what is "
    "simulated, and which parameters are still pending business calibration."
)

try:
    profile = dd.load_sku_profile(PROJECT_ROOT)
    working_capital = dd.load_working_capital_summary(PROJECT_ROOT)
except dd.DashboardDataError as exc:
    st.error(str(exc))
    st.stop()

st.header("📈 Historical sales — real, cleaned transaction data")

historical = dd.historical_overview_metrics(profile)
col1, col2 = st.columns(2)
col1.metric("Total cleaned revenue", dd.format_gbp(historical["total_revenue_gbp"]))
col2.metric(
    "Active SKUs", f"{historical['sku_count']:,}",
    help="SKU = Stock-Keeping Unit, i.e. one distinct product.",
)

st.subheader("SKU classification")
st.caption("Based on real historical revenue and unit volume.")
class_counts = historical["sku_class_counts"]
class_df = pd.DataFrame(
    {"SKU class": list(class_counts.keys()), "SKU count": list(class_counts.values())}
).sort_values("SKU count", ascending=False)
st.caption("Chart unit: SKU count. Historical classification of cleaned sales.")
st.bar_chart(class_df.set_index("SKU class"))
st.dataframe(class_df, hide_index=True, width="stretch")

st.divider()

st.header("🧪 Simulated inventory position — demonstration assumptions, not real inventory")
st.caption(
    "The figures below come from a simulated inventory layer built on demonstration "
    "assumptions (lead times, ordering costs, service levels) that have not been "
    "calibrated against real purchasing or warehouse data. See Model & Data Notes."
)

risk_counts = dd.simulated_risk_counts(profile)
rc1, rc2, rc3 = st.columns(3)
rc1.metric("Normal", f"{risk_counts.get('Normal', 0):,}",
           help=dd.normal_risk_disclaimer())
rc2.metric("Stockout Risk", f"{risk_counts.get('Stockout Risk', 0):,}",
           help=dd.simulated_metric_hint())
rc3.metric("Overstock Risk", f"{risk_counts.get('Overstock Risk', 0):,}",
           help=dd.simulated_metric_hint())

wc1, wc2 = st.columns(2)
wc1.metric(
    "Simulated inventory value",
    # .get(), not [...]: an empty (0-row) working_capital_summary.csv is a valid
    # "no data yet" state per docs/app_product_spec.md §6, not a page crash --
    # format_gbp(None) already renders that as "Not available".
    dd.format_gbp(working_capital.get("total_estimated_inventory_value")),
    help="Simulated stock x simulated unit cost. Not a real accounting figure.",
)
wc2.metric(
    "Stockout revenue exposure",
    dd.format_gbp(working_capital.get("stockout_revenue_exposure")),
    help="Upper-bound indicator of sales at risk, not a forecast of lost revenue.",
)
wc3, _ = st.columns(2)
wc3.metric(
    "Overstock capital exposure",
    dd.format_gbp(working_capital.get("overstock_capital_exposure")),
    help="Simulated inventory value held above the effective overstock threshold.",
)

st.subheader("Simulated warehouse strategy distribution")
warehouse_counts = dd.simulated_warehouse_strategy_counts(profile)
warehouse_df = pd.DataFrame(
    {"Warehouse strategy": list(warehouse_counts.keys()), "SKU count": list(warehouse_counts.values())}
).sort_values("SKU count", ascending=False)
st.caption("Chart unit: SKU count. Simulated strategy assignment under demonstration assumptions.")
st.bar_chart(warehouse_df.set_index("Warehouse strategy"))
st.dataframe(warehouse_df, hide_index=True, width="stretch")
