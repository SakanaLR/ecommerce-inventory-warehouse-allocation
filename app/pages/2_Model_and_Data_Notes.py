"""Model & Data Notes -- data coverage, cleaning rules, model explanations,
parameter calibration status, privacy notes, and links to fuller docs.

Read-only. See ``docs/app_product_spec.md`` §2 for the page spec.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import streamlit as st

from retail_analytics import dashboard_data as dd

# Stable links into the public repo for this page's "further reading" references.
# The repository is public on GitHub at this URL; these point at specific files
# on `main` so a reader (merchant or portfolio visitor) can actually open them
# instead of seeing an inert file path they have no way to follow.
REPO_BLOB_BASE = "https://github.com/SakanaLR/ecommerce-inventory-warehouse-allocation/blob/main/"


def repo_link(path: str) -> str:
    return f"[`{path}`]({REPO_BLOB_BASE}{path})"


st.set_page_config(page_title="Model & Data Notes", page_icon="📚", layout="wide")

st.title("📚 Model & Data Notes")
st.caption(
    "This app runs on a public demonstration dataset (UCI Online Retail). "
    "Nothing on this page or elsewhere in the app is a calibrated, production operational system."
)
st.caption(
    "This is a public demonstration snapshot of that dataset, shipped with this "
    "repository — not a live feed and not connected to any merchant's real systems."
)

try:
    month_coverage = dd.load_month_coverage(PROJECT_ROOT)
    quality = dd.load_data_quality_summary(PROJECT_ROOT)
except dd.DashboardDataError as exc:
    st.error(str(exc))
    st.stop()

st.header("Data coverage")
full_months = month_coverage[~month_coverage["is_truncated_month"]]
truncated_months = month_coverage[month_coverage["is_truncated_month"]]
if not full_months.empty:
    st.write(
        f"**{len(full_months)} full months** of data used for demand statistics: "
        f"{full_months['invoice_month'].min()} to {full_months['invoice_month'].max()}."
    )
else:
    st.warning("No full (non-truncated) months were found in month_coverage.csv.")
if not truncated_months.empty:
    st.write("Truncated (partial) months — excluded from demand statistics, but their sales still count toward SKU totals:")
    st.dataframe(
        truncated_months[["invoice_month", "first_date", "last_date"]], hide_index=True, width="stretch"
    )

freshness = dd.data_freshness_notes(PROJECT_ROOT)
if freshness["row_count_warning"]:
    st.warning(freshness["row_count_warning"])

if freshness["files"]:
    with st.expander("Deployed copy's file details (not the data's generation time)"):
        st.caption(
            "These are file-system modification timestamps for this deployed/cloned "
            "copy of the repository — they shift on every checkout or deploy and do "
            "not indicate when the underlying demonstration data was produced."
        )
        for rel_path, mtime in sorted(freshness["files"].items()):
            stamp = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            st.caption(f"`{rel_path}` — this copy's file last modified: {stamp}")

st.header("Cleaning rules (summary)")
st.markdown(
    "- Duplicate transaction rows are removed.\n"
    "- Non-product lines (postage, carriage, fees, discounts, samples, gift vouchers, etc.) are "
    f"excluded — see {repo_link('config/non_product_stock_codes.csv')}.\n"
    f"- Sales reversed by a reviewed manual credit are removed — see {repo_link('config/manual_reversals.csv')}.\n"
    "- Sales that the same customer later cancelled in full are removed, preferring a match at the "
    "same unit price.\n"
    f"- Full detail: {repo_link('docs/runbook.md')}'s \"Cleaning Rules\" section."
)
st.dataframe(quality, hide_index=True, width="stretch")

st.header("How the simulated inventory model works")
st.markdown(
    "- **Safety stock (service level):** extra stock held to cover demand swings during the "
    "supplier lead time, sized so a target share of lead-time demand is covered. "
    "*Formula:* z(service level) × monthly demand std × √(lead time ÷ days per month).\n"
    "- **EOQ (economic order quantity):** the order size that balances ordering cost against "
    "holding cost, capped at 180 days of coverage. "
    "*Formula:* √(2 × annual demand × ordering cost ÷ (unit cost × annual holding rate)).\n"
    "- **Overstock threshold:** a SKU is only flagged Overstock Risk when its simulated stock "
    "exceeds *both* its own reorder-point-plus-EOQ level *and* a flat coverage-day limit. "
    "*Formula:* max(reorder point + EOQ, daily demand × coverage days)."
)

st.header("⚠️ Parameters: demonstration only, pending business calibration")
st.warning(
    "The ordering cost (£25 per replenishment event), annual holding rate (25%), the 180-day "
    "order-quantity cap, the 180-day overstock coverage limit, the supplier lead-time distribution "
    "(7–45 days), and the per-class service levels are **all demonstration assumptions** — none are "
    "calibrated against real purchasing, warehousing, or supplier data, because this public dataset "
    f"has none. Owner and calibration date: not yet assigned. See {repo_link('docs/runbook.md')}'s "
    f"\"Parameter calibration status\" section and {repo_link('docs/model_assumptions_review.md')} "
    "for the full analysis."
)

st.header("🔒 Data privacy")
st.markdown(
    "- This app rejects any input whose original header declares `customer_id`, `invoice_no`, "
    "`invoice_date`, or other row-level order identifiers; those fields never reach a page.\n"
    "- It only reads pre-aggregated, SKU-level (or coarser) summary files — never the raw transaction file.\n"
    "- It does not offer a raw-data download button, makes no outbound network requests, and "
    "disables Streamlit usage-stat collection in this project's `.streamlit/config.toml`."
)

st.header("Known model limitations")
st.markdown(
    "- A SKU's revenue rank overrides its `short_history` flag when assigning High-Revenue Priority "
    "(by design) — treat that class's demand-volatility statistic as unreliable for short-history SKUs.\n"
    "- Removing the EOQ coverage cap means different things depending on method: holding inventory "
    "fixed, 699 of 1,008 baseline overstock flags become Normal (69.3%); fully regenerating inventory, "
    "overstock counts instead *rise* to 1,043 with none of the original 1,008 leaving that category. "
    "**69.3% is a fixed-snapshot sensitivity result, not a false-positive rate.**\n"
    "- `demand_cv` measures relative monthly-sales volatility including zero-sale months — it is not "
    "a measure of individual order-size variation.\n"
    f"- Full detail: {repo_link('docs/model_assumptions_review.md')} and {repo_link('README.md')}'s "
    "\"Assumptions and Limitations\"."
)

st.header("Further reading in this repository")
st.markdown(
    f"- {repo_link('docs/runbook.md')} — full pipeline and model documentation.\n"
    f"- {repo_link('docs/management_summary.md')} — management-facing summary.\n"
    f"- {repo_link('docs/model_assumptions_review.md')} — independent review of the simulation "
    "model's assumptions."
)
