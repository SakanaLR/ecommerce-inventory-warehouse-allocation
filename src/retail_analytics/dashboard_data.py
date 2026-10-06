"""Read-only data access layer for the merchant analytics Streamlit app.

Every function here reads an already-generated CSV under ``data/processed/``
or ``outputs/`` — nothing here re-runs cleaning, demand, or simulation logic
(see ``cleaning.py``/``demand.py``/``simulation.py`` for that), and nothing
here writes any file. This module is deliberately separate from the Streamlit
page scripts under ``app/``: page scripts only call functions here and render
the result, so the data/aggregation logic can be unit-tested without a
Streamlit runtime.

Privacy contract (see ``docs/app_product_spec.md`` §5): every loader validates
its DataFrame against :data:`FORBIDDEN_COLUMNS`, a denylist of row-level
identifiers (customer/invoice identifiers) that must never reach the app, even
if a future change to an upstream output file were to introduce one. This is
defense in depth — none of the current source files contain these columns —
not a claim that today's files are unsafe.

Any future merchant-provided local aggregation file can be used as a
drop-in replacement for :func:`load_sku_profile` as long as it satisfies
:data:`REQUIRED_SKU_PROFILE_COLUMNS` and contains none of
:data:`FORBIDDEN_COLUMNS` — that column contract *is* the data contract.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# src/retail_analytics/dashboard_data.py -> parents[2] is the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DashboardDataError(RuntimeError):
    """A data source is missing, malformed, or violates the privacy contract.

    Raised instead of letting pandas/IO exceptions bubble up, so page code can
    catch this one type and show a clear message instead of a traceback.
    """


# Row-level identifiers that must never appear in data handed to the app.
# These are the actual column names used elsewhere in this codebase for
# customer/invoice identifiers (see cleaning.py's CANONICAL_COLUMNS and
# MATCH_COLUMNS) -- not a guess at what "sounds sensitive".
FORBIDDEN_COLUMNS = {
    "customer_id",
    "invoice_no",
    "invoice_date",
    "cancel_invoice_no",
    "credit_invoice_no",
}

REQUIRED_SKU_PROFILE_COLUMNS = [
    "stock_code", "description", "total_units", "total_revenue", "total_orders",
    "avg_unit_price", "months_in_window", "zero_month_share", "avg_monthly_units",
    "std_monthly_units", "demand_cv", "short_history", "no_full_month_sales",
    "sku_class", "recommended_action",
    "supplier_lead_time_days", "unit_cost", "safety_stock", "reorder_point",
    "economic_order_qty", "eoq_capped", "max_stock_level", "current_inventory",
    "recommended_replenishment_qty", "inventory_coverage_days", "inventory_risk",
    "excess_units", "warehouse_strategy",
]
REQUIRED_SKU_MONTH_DEMAND_COLUMNS = [
    "stock_code", "invoice_month", "monthly_units", "monthly_revenue", "is_zero_filled",
]
REQUIRED_MONTH_COVERAGE_COLUMNS = ["invoice_month", "first_date", "last_date", "is_truncated_month"]
REQUIRED_DATA_QUALITY_COLUMNS = ["step", "row_count", "note"]
REQUIRED_METRIC_VALUE_COLUMNS = ["metric", "value"]
REQUIRED_WAREHOUSE_ALLOCATION_COLUMNS = [
    "sku_class", "warehouse_strategy", "sku_count", "total_revenue", "total_units",
    "avg_inventory_coverage_days",
]

# Only these aggregated fields may leave the data-access layer.  The forbidden
# column check below remains important (it rejects unsafe source files), while
# this allowlist prevents an unrelated future column from being accidentally
# passed to a page simply because a renderer changes.
NUMERIC_COLUMNS = {
    "sku_profile": [
        "total_units", "total_revenue", "total_orders", "avg_unit_price",
        "months_in_window", "zero_month_share", "avg_monthly_units",
        "std_monthly_units", "demand_cv", "supplier_lead_time_days",
        "unit_cost", "safety_stock", "reorder_point", "economic_order_qty",
        "max_stock_level", "current_inventory", "recommended_replenishment_qty",
        "inventory_coverage_days", "excess_units",
    ],
    "sku_month_demand": ["monthly_units", "monthly_revenue"],
    "data_quality": ["row_count"],
    "warehouse": ["sku_count", "total_revenue", "total_units", "avg_inventory_coverage_days"],
    "metric_value": ["value"],
}
BOOLEAN_COLUMNS = {
    "sku_profile": ["short_history", "no_full_month_sales", "eoq_capped"],
    "sku_month_demand": ["is_zero_filled"],
    "month_coverage": ["is_truncated_month"],
}


def validate_schema(df: pd.DataFrame, required_columns: list[str], source_name: str) -> None:
    """Raise :class:`DashboardDataError` if ``df`` is missing a required column
    or contains a forbidden one. Usable directly on a DataFrame (no file
    needed), so a future merchant-provided file can be checked before use.
    """
    # This must happen before any column selection or missing-column handling:
    # a source that declares a customer/order field is unsafe even if it is
    # otherwise malformed, and the page must never make it past this boundary.
    forbidden_present = sorted(FORBIDDEN_COLUMNS & set(df.columns))
    if forbidden_present:
        raise DashboardDataError(
            f"{source_name} contains column(s) that must never reach the app: "
            f"{', '.join(forbidden_present)}. Refusing to load it."
        )
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise DashboardDataError(
            f"{source_name} is missing required column(s): {', '.join(missing)}."
        )


def _display_path(path: Path, project_root: Path) -> Path:
    try:
        return path.relative_to(project_root)
    except ValueError:
        return path


def _coerce_numeric_columns(df: pd.DataFrame, columns: list[str], source_name: str) -> None:
    for column in columns:
        converted = pd.to_numeric(df[column], errors="coerce")
        invalid = df[column].notna() & converted.isna()
        if invalid.any():
            raise DashboardDataError(
                f"{source_name} has non-numeric value(s) in required numeric column: {column}."
            )
        df[column] = converted


def _coerce_boolean_columns(df: pd.DataFrame, columns: list[str], source_name: str) -> None:
    true_values = {True, "true", "1", 1}
    false_values = {False, "false", "0", 0}
    for column in columns:
        normalised = df[column].map(
            lambda value: value.strip().lower() if isinstance(value, str) else value
        )
        invalid = normalised.notna() & ~normalised.isin(true_values | false_values)
        if invalid.any():
            raise DashboardDataError(
                f"{source_name} has non-boolean value(s) in required boolean column: {column}."
            )
        df[column] = normalised.map(
            lambda value: True if value in true_values else False if value in false_values else pd.NA
        ).astype("boolean")


def _validate_key_columns(df: pd.DataFrame, key_columns: list[str], source_name: str) -> None:
    if not key_columns:
        return
    for column in key_columns:
        empty = df[column].isna() | df[column].astype("string").str.strip().eq("")
        if empty.any():
            raise DashboardDataError(f"{source_name} has a blank key value in: {column}.")
    if df.duplicated(key_columns).any():
        key_description = ", ".join(key_columns)
        raise DashboardDataError(
            f"{source_name} has duplicate row key(s): {key_description}. Refusing ambiguous aggregation."
        )


def _validate_year_month(df: pd.DataFrame, source_name: str) -> None:
    if "invoice_month" not in df.columns:
        return
    parsed = pd.to_datetime(df["invoice_month"], format="%Y-%m", errors="coerce")
    if (df["invoice_month"].notna() & parsed.isna()).any():
        raise DashboardDataError(
            f"{source_name} has invalid invoice_month values; expected YYYY-MM."
        )
    df["invoice_month"] = parsed.dt.strftime("%Y-%m").astype("string")


def _read_csv_with_schema(
    path: Path,
    required_columns: list[str],
    project_root: Path,
    *,
    dtype: dict | None = None,
    numeric_columns: list[str] | None = None,
    boolean_columns: list[str] | None = None,
    key_columns: list[str] | None = None,
) -> pd.DataFrame:
    display_path = _display_path(path, project_root)
    if not path.is_file():
        raise DashboardDataError(
            f"Missing data file: {display_path}. Run the notebooks (notebooks/01-05) "
            "or scripts/verify_pipeline.sh to generate it before using the app."
        )
    try:
        df = pd.read_csv(path, dtype=dtype)
    except pd.errors.EmptyDataError as exc:
        raise DashboardDataError(f"Data file is empty: {display_path}.") from exc
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise DashboardDataError(f"Could not read data file: {display_path}. {exc}") from exc
    validate_schema(df, required_columns, str(display_path))
    # Select the approved data contract only after the original header was
    # checked for forbidden fields.  Return a new object for every call so
    # Streamlit renderers cannot mutate a shared cached DataFrame.
    result = df.loc[:, required_columns].copy()
    _coerce_numeric_columns(result, numeric_columns or [], str(display_path))
    _coerce_boolean_columns(result, boolean_columns or [], str(display_path))
    _validate_year_month(result, str(display_path))
    _validate_key_columns(result, key_columns or [], str(display_path))
    return result


def load_sku_profile(project_root: Path | None = None) -> pd.DataFrame:
    """The per-SKU table backing the Overview and SKU Analyzer pages.

    Historical columns (``total_revenue``, ``total_units``, ``demand_cv``, ...)
    and simulated columns (``current_inventory``, ``inventory_risk``, ...) live
    side by side in this file; callers must keep presenting them as distinct
    categories (see docs/app_product_spec.md §4), this loader does not.
    """
    root = project_root or PROJECT_ROOT
    path = root / "outputs" / "sku_inventory_simulation.csv"
    return _read_csv_with_schema(
        path, REQUIRED_SKU_PROFILE_COLUMNS, root,
        dtype={"stock_code": "string", "description": "string", "sku_class": "string",
               "inventory_risk": "string", "warehouse_strategy": "string"},
        numeric_columns=NUMERIC_COLUMNS["sku_profile"],
        boolean_columns=BOOLEAN_COLUMNS["sku_profile"],
        key_columns=["stock_code"],
    )


def load_sku_month_demand(project_root: Path | None = None) -> pd.DataFrame:
    """Zero-filled SKU x month historical demand panel (for trend charts)."""
    root = project_root or PROJECT_ROOT
    path = root / "data" / "processed" / "sku_month_demand.csv"
    return _read_csv_with_schema(
        path, REQUIRED_SKU_MONTH_DEMAND_COLUMNS, root, dtype={"stock_code": "string"},
        numeric_columns=NUMERIC_COLUMNS["sku_month_demand"],
        boolean_columns=BOOLEAN_COLUMNS["sku_month_demand"],
        key_columns=["stock_code", "invoice_month"],
    )


def load_month_coverage(project_root: Path | None = None) -> pd.DataFrame:
    root = project_root or PROJECT_ROOT
    path = root / "data" / "processed" / "month_coverage.csv"
    return _read_csv_with_schema(
        path, REQUIRED_MONTH_COVERAGE_COLUMNS, root,
        boolean_columns=BOOLEAN_COLUMNS["month_coverage"], key_columns=["invoice_month"],
    )


def load_data_quality_summary(project_root: Path | None = None) -> pd.DataFrame:
    root = project_root or PROJECT_ROOT
    path = root / "data" / "processed" / "data_quality_summary.csv"
    return _read_csv_with_schema(
        path, REQUIRED_DATA_QUALITY_COLUMNS, root,
        numeric_columns=NUMERIC_COLUMNS["data_quality"], key_columns=["step"],
    )


def load_warehouse_allocation_summary(project_root: Path | None = None) -> pd.DataFrame:
    root = project_root or PROJECT_ROOT
    path = root / "outputs" / "warehouse_allocation_summary.csv"
    return _read_csv_with_schema(
        path, REQUIRED_WAREHOUSE_ALLOCATION_COLUMNS, root,
        numeric_columns=NUMERIC_COLUMNS["warehouse"],
        key_columns=["sku_class", "warehouse_strategy"],
    )


def _load_metric_value_csv(path: Path, project_root: Path) -> dict[str, float | str]:
    df = _read_csv_with_schema(
        path, REQUIRED_METRIC_VALUE_COLUMNS, project_root,
        numeric_columns=NUMERIC_COLUMNS["metric_value"], key_columns=["metric"],
    )
    return dict(zip(df["metric"], df["value"]))


def load_management_kpi_summary(project_root: Path | None = None) -> dict[str, float | str]:
    root = project_root or PROJECT_ROOT
    return _load_metric_value_csv(root / "outputs" / "management_kpi_summary.csv", root)


def load_working_capital_summary(project_root: Path | None = None) -> dict[str, float | str]:
    root = project_root or PROJECT_ROOT
    return _load_metric_value_csv(root / "outputs" / "working_capital_summary.csv", root)


# ---------------------------------------------------------------------------
# Aggregation / formatting (pure functions over already-loaded DataFrames --
# no file I/O below this line, so these are testable without touching disk).
# ---------------------------------------------------------------------------

def historical_overview_metrics(sku_profile: pd.DataFrame) -> dict:
    """Historical-fact metrics for the Overview page. See docs/app_product_spec.md §4."""
    return {
        "total_revenue_gbp": float(sku_profile["total_revenue"].sum()),
        "sku_count": int(len(sku_profile)),
        "sku_class_counts": sku_profile["sku_class"].value_counts().to_dict(),
    }


def simulated_risk_counts(sku_profile: pd.DataFrame) -> dict[str, int]:
    """Simulated inventory_risk counts. Not a historical/real-world measurement."""
    return {k: int(v) for k, v in sku_profile["inventory_risk"].value_counts().items()}


def simulated_warehouse_strategy_counts(sku_profile: pd.DataFrame) -> dict[str, int]:
    return {k: int(v) for k, v in sku_profile["warehouse_strategy"].value_counts().items()}


def filter_sku_profile(
    sku_profile: pd.DataFrame,
    *,
    query: str | None = None,
    sku_classes: list[str] | None = None,
    risks: list[str] | None = None,
    strategies: list[str] | None = None,
) -> pd.DataFrame:
    """Apply the SKU Analyzer's filters (AND semantics across filter groups)."""
    df = sku_profile
    if query:
        needle = query.strip().lower()
        if needle:
            code_hit = df["stock_code"].str.lower().str.contains(needle, na=False, regex=False)
            desc_hit = df["description"].str.lower().str.contains(needle, na=False, regex=False)
            df = df[code_hit | desc_hit]
    if sku_classes:
        df = df[df["sku_class"].isin(sku_classes)]
    if risks:
        df = df[df["inventory_risk"].isin(risks)]
    if strategies:
        df = df[df["warehouse_strategy"].isin(strategies)]
    return df.copy()


def sku_month_trend(sku_month_demand: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """A single SKU's monthly demand history, in month order."""
    trend = sku_month_demand[sku_month_demand["stock_code"] == stock_code].copy()
    month_order = pd.to_datetime(trend["invoice_month"], format="%Y-%m", errors="coerce")
    if (trend["invoice_month"].notna() & month_order.isna()).any():
        raise DashboardDataError("Monthly demand contains invalid invoice_month values; expected YYYY-MM.")
    return trend.assign(_month_order=month_order).sort_values("_month_order").drop(
        columns="_month_order"
    ).reset_index(drop=True)


def short_history_notice(row: pd.Series) -> str | None:
    """Uncertainty notice for a short-history SKU, or None if not applicable.

    Wording intentionally mirrors docs/model_assumptions_review.md's discipline:
    a low demand_cv from few observations is not evidence of stable demand.

    ``short_history``/``months_in_window`` are schema-validated as boolean/numeric
    on load but are not required to be *non-null* (see ``validate_schema``), so a
    caller that builds a row directly (tests, or a future merchant-provided file)
    can legitimately hand this a missing flag (``pd.NA``) or a missing month count
    (``NaN``); both are treated as "no notice to show" / "unknown month count"
    rather than raising, since ``bool(pd.NA)`` and ``int(float("nan"))`` both raise.
    """
    flag = row.get("short_history", False)
    if pd.isna(flag) or not bool(flag):
        return None
    months_value = row.get("months_in_window", 0)
    if pd.isna(months_value):
        return (
            "This SKU is flagged as short-history, but its month count is not available. "
            "Its demand statistics, especially demand_cv, should not be read as a verified "
            "stable demand pattern."
        )
    months = int(months_value)
    return (
        f"This SKU has only {months} month(s) of sales history (fewer than the 3-month "
        "threshold). Its demand statistics, especially demand_cv, are estimated from very "
        "few observations and should not be read as a verified stable demand pattern."
    )


def normal_risk_disclaimer() -> str:
    """Standard disclaimer for an inventory_risk == 'Normal' SKU."""
    return (
        "\"Normal\" means the simulated policy, under today's demonstration assumptions, "
        "does not currently flag this SKU as at risk. It is not a confirmed measurement of "
        "real-world service performance."
    )


def simulated_metric_hint() -> str:
    """Generic ℹ️ hint for a simulated-layer metric (docs/app_product_spec.md §2, page 1)."""
    return (
        "Simulated under today's demonstration assumptions (lead times, ordering costs, "
        "service levels) — not a real inventory measurement. See the Model & Data Notes "
        "page for the full model and its calibration status."
    )


# One-line, plain-language ``help=`` text for each simulated inventory metric shown
# on the SKU Analyzer detail view. Kept short on purpose: the full formulas live on
# the Model & Data Notes page (app/pages/2_Model_and_Data_Notes.py); these summarise
# the same definitions so the two pages never say materially different things about
# the same metric.
SKU_DETAIL_METRIC_HELP: dict[str, str] = {
    "current_inventory": (
        "Simulated stock level under the demonstration inventory policy — not a real, "
        "counted inventory balance."
    ),
    "safety_stock": (
        "Extra simulated stock held to cover demand swings during the supplier lead "
        "time. z(service level) x monthly demand std-dev x sqrt(lead time / days per "
        "month). See Model & Data Notes for the full formula."
    ),
    "reorder_point": (
        "Simulated stock level at which the demonstration policy would trigger a new "
        "order."
    ),
    "economic_order_qty": (
        "Simulated order size balancing ordering cost against holding cost (EOQ), "
        "capped at 180 days of coverage. See Model & Data Notes for the full formula."
    ),
    "recommended_replenishment_qty": (
        "Simulated suggested order quantity to bring stock back to the policy level "
        "— not a business recommendation to act on."
    ),
    "inventory_coverage_days": (
        "Simulated number of days the current simulated stock would last at this "
        "SKU's average demand."
    ),
}


def format_gbp(value: float | None) -> str:
    if value is None or pd.isna(value) or value in (float("inf"), float("-inf")):
        return "Not available"
    return f"£{value:,.2f}"


def format_units(value: float | None) -> str:
    if value is None or pd.isna(value) or value in (float("inf"), float("-inf")):
        return "Not available"
    return f"{value:,.0f}"


def format_percent(value: float | None) -> str:
    if value is None or pd.isna(value) or value in (float("inf"), float("-inf")):
        return "Not available"
    return f"{value:.1%}"


def format_ratio(value: float | None, decimals: int = 2) -> str:
    """Format a unitless ratio (e.g. demand_cv) as a plain decimal, not a percent.

    README.md and the rest of the repo's own documentation describe demand_cv as
    a plain ratio (e.g. "median CV of 1.01"), not a percentage; this keeps the
    app's own rendering consistent with that convention instead of showing the
    same number as e.g. "101.0%", which reads as alarming/out-of-range for a
    reader expecting a 0-100% figure.
    """
    if value is None or pd.isna(value) or value in (float("inf"), float("-inf")):
        return "Not available"
    return f"{value:.{decimals}f}"


def data_freshness_notes(project_root: Path | None = None) -> dict:
    """Lightweight, advisory freshness/consistency info for the Model & Data page.

    This is informational only (docs/app_product_spec.md §6) -- it does not
    block any page from rendering, it only surfaces a note when the sku
    profile and classification outputs disagree on row count, or reports each
    file's last-modified time.
    """
    root = project_root or PROJECT_ROOT
    notes: dict = {"files": {}, "row_count_warning": None}
    watched = [
        root / "outputs" / "sku_inventory_simulation.csv",
        root / "outputs" / "sku_profile_classification.csv",
        root / "data" / "processed" / "sku_month_demand.csv",
    ]
    row_counts = {}
    for path in watched:
        if not path.exists():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        mtime = path.stat().st_mtime
        notes["files"][str(rel)] = mtime
        try:
            with path.open() as handle:
                row_counts[str(rel)] = sum(1 for _ in handle) - 1
        except OSError:
            pass

    sim_key = "outputs/sku_inventory_simulation.csv"
    cls_key = "outputs/sku_profile_classification.csv"
    if sim_key in row_counts and cls_key in row_counts and row_counts[sim_key] != row_counts[cls_key]:
        notes["row_count_warning"] = (
            f"{sim_key} has {row_counts[sim_key]} rows but {cls_key} has "
            f"{row_counts[cls_key]} rows -- these are usually regenerated together. "
            "Figures on this page may be based on outputs from different pipeline runs."
        )
    return notes
