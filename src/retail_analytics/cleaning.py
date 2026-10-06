"""Transaction cleaning rules for the standardized sales dataset.

The notebooks call these functions so the cleaning logic lives in one tested
place instead of being copied between notebooks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["invoice_no", "stock_code", "quantity", "invoice_date", "unit_price"]
CANONICAL_COLUMNS = [
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]
STRING_COLUMNS = ["invoice_no", "stock_code", "description", "customer_id", "country"]
OPTIONAL_DEFAULTS = {"description": "Description unavailable", "country": "Unknown"}
PRICE_DECIMALS = 4
MATCH_COLUMNS = [
    "sale_index",
    "cancel_index",
    "cancel_invoice_no",
    "cancel_date",
    "days_to_cancel",
    "cancel_unit_price",
    "price_delta",
    "match_quality",
]


# ---------------------------------------------------------------------------
# Loading and normalization
# ---------------------------------------------------------------------------

def load_standardized_sales(path: str | Path) -> pd.DataFrame:
    """Read the standardized CSV written by scripts/standardize_raw_sales.py."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            "Standardized input not found. Run scripts/standardize_raw_sales.py first. "
            f"Expected file: {path}"
        )
    header = pd.read_csv(path, nrows=0).columns
    dtypes = {column: "string" for column in STRING_COLUMNS if column in header}
    return pd.read_csv(path, dtype=dtypes)


def normalize_sales(df: pd.DataFrame) -> pd.DataFrame:
    """Return canonical columns with consistent types and normalized keys.

    ``stock_code`` is stripped and upper-cased because the source contains
    case-only variants of the same product (for example ``85123a`` and
    ``85123A``).
    """
    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError("Missing required standardized input columns: " + ", ".join(missing))

    df = df.copy()
    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default
    if "customer_id" not in df.columns:
        df["customer_id"] = pd.Series(pd.NA, index=df.index, dtype="string")

    df = df[CANONICAL_COLUMNS].copy()
    for column in STRING_COLUMNS:
        df[column] = df[column].astype("string").str.strip()
    df["stock_code"] = df["stock_code"].str.upper()
    df["description"] = df["description"].str.upper()
    df.loc[df["description"] == "", "description"] = pd.NA
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Non-product rules
# ---------------------------------------------------------------------------

def validate_non_product_rules(rules: pd.DataFrame) -> None:
    """Raise ValueError when the rule table is incomplete or ambiguous."""
    for column in ["stock_code", "match_type", "category"]:
        blank = rules[column].isna() | rules[column].eq("")
        if blank.any():
            rows = ", ".join(str(i + 2) for i in rules.index[blank])
            raise ValueError(f"Blank {column} in non-product rules (file rows {rows}).")

    bad = sorted(set(rules["match_type"]) - {"exact", "prefix"})
    if bad:
        raise ValueError("Unsupported match_type values: " + ", ".join(bad))

    duplicated = rules.duplicated(["stock_code", "match_type"], keep=False)
    if duplicated.any():
        codes = ", ".join(sorted(rules.loc[duplicated, "stock_code"].unique()))
        raise ValueError("Duplicate non-product rules: " + codes)

    prefixes = rules.loc[rules["match_type"] == "prefix", "stock_code"].tolist()
    overlaps = []
    for rule in rules.itertuples(index=False):
        for prefix in prefixes:
            if rule.stock_code == prefix and rule.match_type == "prefix":
                continue
            if rule.stock_code.startswith(prefix):
                overlaps.append(f"{rule.stock_code} ({rule.match_type}) is covered by prefix {prefix}")
    if overlaps:
        raise ValueError("Overlapping non-product rules: " + "; ".join(overlaps))


def load_non_product_rules(path: str | Path) -> pd.DataFrame:
    rules = pd.read_csv(path, dtype="string", keep_default_na=False)
    expected = {"stock_code", "match_type", "category", "reason"}
    missing = expected - set(rules.columns)
    if missing:
        raise ValueError("Non-product rule file is missing columns: " + ", ".join(sorted(missing)))
    rules["stock_code"] = rules["stock_code"].str.strip().str.upper()
    rules["match_type"] = rules["match_type"].str.strip().str.lower()
    rules["category"] = rules["category"].str.strip()
    validate_non_product_rules(rules)
    return rules


def non_product_category(stock_codes: pd.Series, rules: pd.DataFrame) -> pd.Series:
    """Return the rule category for each stock code, or <NA> for products."""
    codes = stock_codes.astype("string").str.strip().str.upper()
    result = pd.Series(pd.NA, index=codes.index, dtype="string")
    for rule in rules.itertuples(index=False):
        if rule.match_type == "exact":
            hit = codes == rule.stock_code
        else:
            hit = codes.str.startswith(rule.stock_code, na=False)
        result = result.mask(hit.fillna(False) & result.isna(), rule.category)
    return result


# ---------------------------------------------------------------------------
# Full cancellations
# ---------------------------------------------------------------------------

def match_full_cancellations(
    sales: pd.DataFrame,
    cancellations: pd.DataFrame,
) -> pd.DataFrame:
    """Pair each cancellation line with the sale line it fully reverses.

    A candidate sale has the same customer, the same stock code, a sold
    quantity equal to the cancelled quantity, and a timestamp on or before the
    cancellation. Cancellations are processed in time order. Each one takes an
    unused candidate at the same unit price when one exists (the most recent of
    those), and otherwise the most recent unused candidate. Every sale line is
    used at most once. Lines without a customer ID are never matched.

    ``match_quality`` is ``same_price`` or ``price_mismatch``.
    """
    if sales.empty or cancellations.empty:
        return pd.DataFrame(columns=MATCH_COLUMNS)

    candidates = sales.dropna(subset=["customer_id", "invoice_date"])
    buckets: dict[tuple, list[tuple]] = defaultdict(list)
    for idx, customer, code, qty, date, price in zip(
        candidates.index,
        candidates["customer_id"],
        candidates["stock_code"],
        candidates["quantity"],
        candidates["invoice_date"],
        candidates["unit_price"],
    ):
        buckets[(customer, code, float(qty))].append((date, idx, round(float(price), PRICE_DECIMALS)))
    for rows in buckets.values():
        rows.sort(key=lambda item: item[0])

    cancels = cancellations.dropna(subset=["customer_id", "invoice_date"])
    cancels = cancels[cancels["quantity"] < 0].sort_values("invoice_date", kind="stable")

    used: set = set()
    pairs = []
    for cidx, customer, code, qty, cdate, cinv, cprice in zip(
        cancels.index,
        cancels["customer_id"],
        cancels["stock_code"],
        cancels["quantity"],
        cancels["invoice_date"],
        cancels["invoice_no"],
        cancels["unit_price"],
    ):
        rows = buckets.get((customer, code, float(-qty)))
        if not rows:
            continue
        eligible = [row for row in rows if row[0] <= cdate and row[1] not in used]
        if not eligible:
            continue
        cancel_price = round(float(cprice), PRICE_DECIMALS)
        same_price = [row for row in eligible if row[2] == cancel_price]
        sale_date, sidx, sale_price = (same_price or eligible)[-1]
        used.add(sidx)
        pairs.append((
            sidx,
            cidx,
            cinv,
            cdate,
            (cdate - sale_date).days,
            cancel_price,
            round(cancel_price - sale_price, PRICE_DECIMALS),
            "same_price" if same_price else "price_mismatch",
        ))

    return pd.DataFrame(pairs, columns=MATCH_COLUMNS)


# ---------------------------------------------------------------------------
# Manual credits
# ---------------------------------------------------------------------------

MANUAL_REVERSAL_COLUMNS = [
    "invoice_no",
    "stock_code",
    "quantity",
    "unit_price",
    "credit_invoice_no",
    "reason",
]


def load_manual_reversals(path: str | Path) -> pd.DataFrame:
    """Read the reviewed list of sale lines reversed by manual credit notes."""
    table = pd.read_csv(path, dtype="string", keep_default_na=False)
    missing = set(MANUAL_REVERSAL_COLUMNS) - set(table.columns)
    if missing:
        raise ValueError("Manual reversal file is missing columns: " + ", ".join(sorted(missing)))
    table = table[MANUAL_REVERSAL_COLUMNS].apply(lambda s: s.str.strip())
    blank = table.eq("").any(axis=1)
    if blank.any():
        raise ValueError("Manual reversal file has blank values (file rows "
                         + ", ".join(str(i + 2) for i in table.index[blank]) + ").")
    table["stock_code"] = table["stock_code"].str.upper()
    table["quantity"] = pd.to_numeric(table["quantity"])
    table["unit_price"] = pd.to_numeric(table["unit_price"])
    key = ["invoice_no", "stock_code", "quantity", "unit_price"]
    if table.duplicated(key).any():
        raise ValueError("Duplicate sale lines in manual reversal file.")
    return table


def apply_manual_reversals(
    sales: pd.DataFrame,
    cancellations: pd.DataFrame,
    reversals: pd.DataFrame,
) -> pd.DataFrame:
    """Locate each reviewed manual reversal and check it against the data.

    Every listed sale line must match exactly one sales row, and its credit
    invoice must contain a credit line for the same customer whose absolute
    value equals the sale line value. Any mismatch raises ValueError so the
    reviewed list cannot silently drift from the data.
    """
    if reversals.empty:
        return pd.DataFrame(columns=MATCH_COLUMNS)

    pairs = []
    for rev in reversals.itertuples(index=False):
        hit = sales[
            (sales["invoice_no"] == rev.invoice_no)
            & (sales["stock_code"] == rev.stock_code)
            & (sales["quantity"] == rev.quantity)
            & ((sales["unit_price"] - rev.unit_price).abs() < 1e-9)
        ]
        if len(hit) != 1:
            raise ValueError(
                f"Manual reversal {rev.invoice_no}/{rev.stock_code} matched {len(hit)} sales rows; expected 1."
            )
        sale = hit.iloc[0]
        line_value = round(float(sale["quantity"] * sale["unit_price"]), 2)
        credit = cancellations[
            (cancellations["invoice_no"] == rev.credit_invoice_no)
            & (cancellations["customer_id"] == sale["customer_id"])
        ]
        credit_values = (credit["quantity"] * credit["unit_price"]).abs().round(2)
        credit = credit[credit_values == line_value]
        if len(credit) != 1:
            raise ValueError(
                f"Credit {rev.credit_invoice_no} has no single line worth {line_value} "
                f"for the customer of sale {rev.invoice_no}."
            )
        credit_row = credit.iloc[0]
        pairs.append((
            hit.index[0],
            credit.index[0],
            rev.credit_invoice_no,
            credit_row["invoice_date"],
            (credit_row["invoice_date"] - sale["invoice_date"]).days,
            round(float(credit_row["unit_price"]), PRICE_DECIMALS),
            float("nan"),
            "reviewed_manual_credit",
        ))
    return pd.DataFrame(pairs, columns=MATCH_COLUMNS)


def find_manual_credit_candidates(
    sales: pd.DataFrame,
    cancellations: pd.DataFrame,
    manual_codes: tuple[str, ...] = ("M",),
    window_days: int = 1,
) -> pd.DataFrame:
    """List manual credit lines whose value equals a recent sale line value.

    This is a review aid: nothing is removed automatically. A credit is a
    candidate when the same customer has at least one sale line in the
    ``window_days`` before it with exactly the same value.
    """
    columns = [
        "credit_invoice_no", "credit_date", "customer_id", "credit_amount",
        "candidate_count", "candidate_invoices", "candidate_stock_codes",
    ]
    credits = cancellations[
        cancellations["stock_code"].isin(manual_codes)
        & cancellations["customer_id"].notna()
        & (cancellations["quantity"] * cancellations["unit_price"] < 0)
    ]
    if credits.empty:
        return pd.DataFrame(columns=columns)

    lines = sales.dropna(subset=["customer_id"]).assign(
        line_value=lambda d: (d["quantity"] * d["unit_price"]).round(2)
    )
    rows = []
    for credit in credits.itertuples(index=False):
        amount = round(abs(credit.quantity * credit.unit_price), 2)
        hit = lines[
            (lines["customer_id"] == credit.customer_id)
            & (lines["line_value"] == amount)
            & (lines["invoice_date"] <= credit.invoice_date)
            & (lines["invoice_date"] >= credit.invoice_date - pd.Timedelta(days=window_days))
        ]
        if hit.empty:
            continue
        rows.append((
            credit.invoice_no, credit.invoice_date, credit.customer_id, amount, len(hit),
            ";".join(hit["invoice_no"]), ";".join(hit["stock_code"]),
        ))
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("credit_amount", ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Review reports
# ---------------------------------------------------------------------------

def find_price_anomalies(
    sales: pd.DataFrame,
    ratio: float = 10.0,
    min_lines: int = 3,
) -> pd.DataFrame:
    """Flag lines priced at least ``ratio`` times the SKU's median price.

    Only SKUs with at least ``min_lines`` sales lines are checked. The report
    is for review; flagged lines are not removed.
    """
    stats = sales.groupby("stock_code")["unit_price"].agg(sku_median_price="median", sku_lines="size")
    frame = sales.join(stats, on="stock_code")
    frame = frame[(frame["sku_lines"] >= min_lines) & (frame["unit_price"] >= ratio * frame["sku_median_price"])]
    frame = frame.assign(
        price_ratio=(frame["unit_price"] / frame["sku_median_price"]).round(1),
        line_value=(frame["quantity"] * frame["unit_price"]).round(2),
    )
    return frame[
        ["invoice_no", "stock_code", "description", "quantity", "unit_price",
         "sku_median_price", "price_ratio", "line_value", "invoice_date", "customer_id"]
    ].sort_values("line_value", ascending=False).reset_index(drop=True)


def month_coverage(dates: pd.Series) -> pd.DataFrame:
    """Describe each month and flag months cut off by the data's start or end.

    ``is_truncated_month`` is True only for the first or last month when the
    data starts after the first day or ends before the last day of that month.
    It does not detect gaps inside a month.
    """
    dates = pd.to_datetime(dates).dropna()
    frame = pd.DataFrame({"date": dates.dt.normalize()})
    frame["invoice_month"] = frame["date"].dt.to_period("M")
    coverage = (
        frame.groupby("invoice_month")["date"]
        .agg(first_date="min", last_date="max")
        .reset_index()
    )
    data_start = frame["date"].min()
    data_end = frame["date"].max()
    month_start = coverage["invoice_month"].dt.start_time.dt.normalize()
    month_end = coverage["invoice_month"].dt.end_time.dt.normalize()
    coverage["is_truncated_month"] = (
        ((coverage["invoice_month"] == data_start.to_period("M")) & (data_start > month_start))
        | ((coverage["invoice_month"] == data_end.to_period("M")) & (data_end < month_end))
    )
    coverage["invoice_month"] = coverage["invoice_month"].astype(str)
    coverage["first_date"] = coverage["first_date"].dt.date
    coverage["last_date"] = coverage["last_date"].dt.date
    return coverage


# ---------------------------------------------------------------------------
# Full cleaning sequence
# ---------------------------------------------------------------------------

@dataclass
class CleaningResult:
    sales: pd.DataFrame
    returns_cancellations: pd.DataFrame
    non_product_lines: pd.DataFrame
    reversed_sales: pd.DataFrame
    manual_credit_candidates: pd.DataFrame
    step_counts: dict[str, int] = field(default_factory=dict)


def _reversed_lines(sales: pd.DataFrame, pairs: pd.DataFrame, reversal_type: str) -> pd.DataFrame:
    lines = sales.loc[pairs["sale_index"]].copy()
    lines["reversal_type"] = reversal_type
    for column in MATCH_COLUMNS[2:]:
        lines[column] = pairs[column].to_numpy()
    lines["price_delta"] = pd.to_numeric(lines["price_delta"], errors="coerce").astype(float)
    lines["revenue"] = lines["quantity"] * lines["unit_price"]
    return lines


def clean_transactions(
    raw: pd.DataFrame,
    non_product_rules: pd.DataFrame,
    manual_reversals: pd.DataFrame | None = None,
) -> CleaningResult:
    """Apply the full cleaning sequence and return every output table.

    Order: normalize, de-duplicate, separate returns and cancellations, keep
    valid sales, exclude non-product lines, remove reviewed manual reversals,
    then remove sales fully reversed by a cancellation line.
    """
    counts: dict[str, int] = {"standardized_input": len(raw)}

    df = normalize_sales(raw)
    df = df.drop_duplicates().copy()
    counts["after_duplicate_removal"] = len(df)

    is_cancel_invoice = df["invoice_no"].str.startswith("C", na=False)
    returns_cancellations = df[is_cancel_invoice | (df["quantity"] < 0)].copy()
    counts["returns_cancellations_separated"] = len(returns_cancellations)

    valid = (
        ~is_cancel_invoice
        & (df["quantity"] > 0)
        & (df["unit_price"] > 0)
        & df["stock_code"].notna()
        & df["description"].notna()
        & df["invoice_date"].notna()
    )
    sales = df[valid].copy()
    counts["valid_sales_before_exclusions"] = len(sales)

    category = non_product_category(sales["stock_code"], non_product_rules)
    non_product_lines = sales[category.notna()].assign(non_product_category=category[category.notna()])
    sales = sales[category.isna()].copy()
    counts["non_product_lines_excluded"] = len(non_product_lines)

    candidates = find_manual_credit_candidates(sales, returns_cancellations)

    if manual_reversals is None:
        manual_reversals = pd.DataFrame(columns=MANUAL_REVERSAL_COLUMNS)
    manual_pairs = apply_manual_reversals(sales, returns_cancellations, manual_reversals)
    manual_lines = _reversed_lines(sales, manual_pairs, "manual_credit")
    sales = sales.drop(index=manual_pairs["sale_index"])
    counts["manual_credit_reversals_removed"] = len(manual_lines)

    pairs = match_full_cancellations(sales, returns_cancellations)
    cancelled_lines = _reversed_lines(sales, pairs, "full_cancellation")
    sales = sales.drop(index=pairs["sale_index"])
    counts["fully_reversed_sales_removed"] = len(cancelled_lines)

    parts = [frame for frame in (manual_lines, cancelled_lines) if not frame.empty]
    reversed_sales = pd.concat(parts) if len(parts) > 1 else (parts[0] if parts else cancelled_lines)

    candidates["reviewed_in_config"] = candidates["credit_invoice_no"].isin(manual_reversals["credit_invoice_no"])

    sales["invoice_date_only"] = sales["invoice_date"].dt.date
    sales["invoice_month"] = sales["invoice_date"].dt.to_period("M").astype(str)
    sales["invoice_week"] = sales["invoice_date"].dt.to_period("W").astype(str)
    sales["revenue"] = sales["quantity"] * sales["unit_price"]
    counts["valid_product_sales_final"] = len(sales)

    return CleaningResult(
        sales=sales.reset_index(drop=True),
        returns_cancellations=returns_cancellations.reset_index(drop=True),
        non_product_lines=non_product_lines.reset_index(drop=True),
        reversed_sales=reversed_sales.reset_index(drop=True),
        manual_credit_candidates=candidates,
        step_counts=counts,
    )


# ---------------------------------------------------------------------------
# SKU tables
# ---------------------------------------------------------------------------

def build_sku_master(sales: pd.DataFrame) -> pd.DataFrame:
    """One row per stock_code; description is the most frequent (latest on ties)."""
    description = (
        sales.groupby(["stock_code", "description"])
        .agg(lines=("invoice_no", "size"), last_seen=("invoice_date", "max"))
        .reset_index()
        .sort_values(["stock_code", "lines", "last_seen"], ascending=[True, False, False])
        .drop_duplicates("stock_code")[["stock_code", "description"]]
    )
    stats = sales.groupby("stock_code", as_index=False).agg(
        first_sale_date=("invoice_date", "min"),
        last_sale_date=("invoice_date", "max"),
        total_units=("quantity", "sum"),
        total_revenue=("revenue", "sum"),
        avg_unit_price=("unit_price", "mean"),
        description_count=("description", "nunique"),
    )
    master = description.merge(stats, on="stock_code", how="right", validate="one_to_one")
    return master[
        [
            "stock_code",
            "description",
            "first_sale_date",
            "last_sale_date",
            "total_units",
            "total_revenue",
            "avg_unit_price",
            "description_count",
        ]
    ]


def build_monthly_sku_sales(sales: pd.DataFrame, sku_master: pd.DataFrame) -> pd.DataFrame:
    monthly = sales.groupby(["stock_code", "invoice_month"], as_index=False).agg(
        monthly_units=("quantity", "sum"),
        monthly_revenue=("revenue", "sum"),
        order_count=("invoice_no", "nunique"),
        avg_unit_price=("unit_price", "mean"),
    )
    monthly = monthly.merge(
        sku_master[["stock_code", "description"]], on="stock_code", how="left", validate="many_to_one"
    )
    return monthly[
        [
            "stock_code",
            "description",
            "invoice_month",
            "monthly_units",
            "monthly_revenue",
            "order_count",
            "avg_unit_price",
        ]
    ]
