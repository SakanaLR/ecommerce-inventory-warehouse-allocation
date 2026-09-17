"""End-to-end regression test for the cleaning pipeline against the real raw data.

This is deliberately not a comparison against a saved CSV snapshot: it runs the
actual standardize + clean code (``scripts/standardize_raw_sales.py`` and
``src/retail_analytics/cleaning.py``) starting from ``data/raw/Online Retail.xlsx``,
writing intermediate output only to pytest's ``tmp_path`` so the real
``data/interim/`` and ``data/processed/`` outputs are never touched. Comparing
already-generated CSVs would not catch a code change that regenerates them
identically-but-wrongly, or a config change that nobody reruns the notebooks for.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from retail_analytics import cleaning
from scripts import standardize_raw_sales

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
MAPPING_PATH = PROJECT_ROOT / "config" / "schema_mapping_template.csv"
NON_PRODUCT_RULES_PATH = PROJECT_ROOT / "config" / "non_product_stock_codes.csv"
MANUAL_REVERSALS_PATH = PROJECT_ROOT / "config" / "manual_reversals.csv"

EXPECTED_FINAL_ROWS = 519_627
EXPECTED_REVENUE = 9_818_872.18
EXPECTED_SAME_PRICE_MATCHES = 2_722
EXPECTED_PRICE_MISMATCH_MATCHES = 93
EXPECTED_REVIEWED_MANUAL_CREDITS = 1

pytestmark = pytest.mark.skipif(
    not RAW_DATA_PATH.exists(),
    reason=f"Raw source data not available: {RAW_DATA_PATH} is missing in this environment.",
)


@pytest.fixture(scope="module")
def standardized_sales_csv(tmp_path_factory) -> Path:
    """Run the real standardize step against the real raw file, into a temp file."""
    raw = standardize_raw_sales.load_raw_data(RAW_DATA_PATH)
    mapping = standardize_raw_sales.load_mapping(MAPPING_PATH)
    standardized, _diagnostics = standardize_raw_sales.standardize_sales(raw, mapping)

    out_dir = tmp_path_factory.mktemp("cleaning_pipeline_regression")
    out_path = out_dir / "standardized_sales.csv"
    standardized.to_csv(out_path, index=False)
    return out_path


@pytest.fixture(scope="module")
def cleaning_result(standardized_sales_csv) -> cleaning.CleaningResult:
    """Run the real cleaning step (config/*.csv, never modified) on that output."""
    sales = cleaning.load_standardized_sales(standardized_sales_csv)
    non_product_rules = cleaning.load_non_product_rules(NON_PRODUCT_RULES_PATH)
    manual_reversals = cleaning.load_manual_reversals(MANUAL_REVERSALS_PATH)
    return cleaning.clean_transactions(sales, non_product_rules, manual_reversals)


def test_final_row_count_and_revenue_match_expected(cleaning_result):
    assert cleaning_result.step_counts["valid_product_sales_final"] == EXPECTED_FINAL_ROWS
    assert len(cleaning_result.sales) == EXPECTED_FINAL_ROWS
    assert cleaning_result.sales["revenue"].sum() == pytest.approx(EXPECTED_REVENUE, rel=0, abs=0.01)


def test_cancellation_and_manual_credit_match_counts(cleaning_result):
    reversed_sales = cleaning_result.reversed_sales
    full_cancellations = reversed_sales[reversed_sales["reversal_type"] == "full_cancellation"]
    manual_credits = reversed_sales[reversed_sales["reversal_type"] == "manual_credit"]

    assert (full_cancellations["match_quality"] == "same_price").sum() == EXPECTED_SAME_PRICE_MATCHES
    assert (full_cancellations["match_quality"] == "price_mismatch").sum() == EXPECTED_PRICE_MISMATCH_MATCHES
    assert len(manual_credits) == EXPECTED_REVIEWED_MANUAL_CREDITS


def test_pipeline_is_actually_sensitive_to_non_product_rule_changes(standardized_sales_csv):
    """Prove the assertions above would catch drift, without touching the real config.

    Removes one exact-match rule from an in-memory COPY of the rules table
    (config/non_product_stock_codes.csv on disk is never written to) and
    confirms the final row count actually changes.
    """
    sales = cleaning.load_standardized_sales(standardized_sales_csv)
    non_product_rules = cleaning.load_non_product_rules(NON_PRODUCT_RULES_PATH)
    manual_reversals = cleaning.load_manual_reversals(MANUAL_REVERSALS_PATH)

    exact_rules = non_product_rules[non_product_rules["match_type"] == "exact"]
    assert not exact_rules.empty, "expected at least one exact-match non-product rule to test with"
    removed_code = exact_rules.iloc[0]["stock_code"]
    affected_rows = (sales["stock_code"].astype("string").str.strip().str.upper() == removed_code).sum()
    assert affected_rows > 0, f"test rule {removed_code!r} does not affect any row; pick a different one"

    rules_without_one_rule = non_product_rules[non_product_rules["stock_code"] != removed_code].reset_index(drop=True)

    baseline = cleaning.clean_transactions(sales, non_product_rules, manual_reversals)
    changed = cleaning.clean_transactions(sales, rules_without_one_rule, manual_reversals)

    assert changed.step_counts["valid_product_sales_final"] != baseline.step_counts["valid_product_sales_final"]
