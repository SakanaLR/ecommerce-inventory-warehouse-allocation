"""Demand -> classification -> simulation interface tests (T1).

These tests build small, deterministic monthly-sales fixtures and run them
through the real ``full_months`` / ``build_demand_panel`` / ``build_sku_profile``
/ ``classify_skus`` / ``simulation.simulate`` pipeline — nothing here hand-writes
a simulate()-ready row to skip an intermediate step. The goal is to lock the
0/1/2/3-month observation boundary as it actually flows end to end, since
tests/test_demand.py and tests/test_simulation.py each cover their own module
in isolation but nothing previously connected them for these specific cases
(see docs/model_assumptions_review.md §7 / docs/model_assumptions_plan.md §4).
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pandas as pd
import pytest

from retail_analytics import demand, simulation

PROJECT_ROOT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "simulation_assumptions.json"

# Synthetic boundary fixture: 11 full months and one truncated month.
# The real dataset has 12 full months.
MONTH_COVERAGE = pd.DataFrame({
    "invoice_month": [f"2020-{m:02d}" for m in range(1, 13)],
    "is_truncated_month": [False] * 11 + [True],
})


def monthly_rows(rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["stock_code", "invoice_month", "monthly_units", "monthly_revenue"])
    frame["order_count"] = 1
    frame["avg_unit_price"] = frame["monthly_revenue"] / frame["monthly_units"]
    return frame


def sku_master(codes) -> pd.DataFrame:
    return pd.DataFrame({"stock_code": codes, "description": [f"ITEM {c}" for c in codes]})


@pytest.fixture(scope="module")
def real_assumptions() -> dict:
    return simulation.load_assumptions(PROJECT_ROOT_CONFIG)


def test_full_months_excludes_only_the_truncated_boundary_month():
    assert demand.full_months(MONTH_COVERAGE) == [f"2020-{m:02d}" for m in range(1, 12)]


@pytest.fixture(scope="module")
def boundary_profile() -> pd.DataFrame:
    """A small population with 0/1/2/3 full-month observation SKUs among some
    'filler' SKUs, so classify_skus has a real distribution to take percentiles
    over rather than a single-SKU degenerate case."""
    rows = []
    filler_codes = []
    for i in range(10):
        code = f"FILL{i:02d}"
        filler_codes.append(code)
        for m in range(1, 12):
            rows.append((code, f"2020-{m:02d}", 20, 20 * 2.0))

    # ONLY_TRUNC: sales only in the truncated December month -> no full-month rows at all.
    rows.append(("ONLY_TRUNC", "2020-12", 7, 7.0))

    # ONE_MONTH: a single real, full month of sales (the window's last month) ->
    # months_in_window=1. Deliberately the highest-revenue SKU in this population,
    # to test that revenue rank still wins High-Revenue Priority classification
    # even with short_history=True, via the real pipeline (not a hand-built profile).
    rows.append(("ONE_MONTH", "2020-11", 900, 900 * 5.0))

    # TWO_MONTHS: exactly 2 full months -> months_in_window=2, short_history=True.
    rows.append(("TWO_MONTHS", "2020-10", 100, 100 * 2.0))
    rows.append(("TWO_MONTHS", "2020-11", 140, 140 * 2.0))

    # THREE_MONTHS: exactly 3 full months -> months_in_window=3. The flag is
    # strictly "< 3", so this must NOT be short_history (the exact boundary
    # docs/model_assumptions_review.md §4 corrected).
    rows.append(("THREE_MONTHS", "2020-09", 80, 80 * 2.0))
    rows.append(("THREE_MONTHS", "2020-10", 95, 95 * 2.0))
    rows.append(("THREE_MONTHS", "2020-11", 110, 110 * 2.0))

    monthly_sales = monthly_rows(rows)
    codes = filler_codes + ["ONLY_TRUNC", "ONE_MONTH", "TWO_MONTHS", "THREE_MONTHS"]
    months = demand.full_months(MONTH_COVERAGE)
    return demand.build_sku_profile(monthly_sales, sku_master(codes), months)


def test_no_full_month_sales_sku_gets_zero_demand_stats_but_keeps_real_totals(boundary_profile):
    row = boundary_profile.set_index("stock_code").loc["ONLY_TRUNC"]
    assert row["no_full_month_sales"]
    assert row["months_in_window"] == 0
    assert row["avg_monthly_units"] == 0
    assert row["std_monthly_units"] == 0
    assert row["demand_cv"] == 0
    assert row["total_units"] == 7  # truncated-month sales still count toward totals
    assert pd.isna(row["zero_month_share"])  # no window months to compute a share over


def test_single_month_observation_gets_short_history_and_zero_spread(boundary_profile):
    row = boundary_profile.set_index("stock_code").loc["ONE_MONTH"]
    assert not row["no_full_month_sales"]
    assert row["months_in_window"] == 1
    assert row["short_history"]
    # A single observation has no spread, by contract -- this is an engineering
    # convention, not evidence the demand is actually stable (see docs/runbook.md's
    # "What demand_cv actually measures" note).
    assert row["std_monthly_units"] == 0
    assert row["demand_cv"] == 0


def test_two_month_observation_is_short_history_with_a_real_sample_std(boundary_profile):
    row = boundary_profile.set_index("stock_code").loc["TWO_MONTHS"]
    assert row["months_in_window"] == 2
    assert row["short_history"]
    mean, std = 120.0, math.sqrt(800.0)
    assert row["avg_monthly_units"] == pytest.approx(mean)
    assert row["std_monthly_units"] == pytest.approx(std)
    assert row["demand_cv"] == pytest.approx(std / mean)


def test_three_month_observation_is_the_exact_boundary_and_is_not_short_history(boundary_profile):
    """months_in_window == 3 must NOT be flagged short_history (the flag is `< 3`).

    This is the exact case docs/model_assumptions_review.md §4 found mislabeled
    in an earlier internal diagnosis draft (two 3-month sample SKUs were
    mis-stated as High-Revenue Priority when they were actually Regular) --
    lock the boundary itself here with hand-calculated, non-degenerate data.
    """
    row = boundary_profile.set_index("stock_code").loc["THREE_MONTHS"]
    assert row["months_in_window"] == 3
    assert not row["short_history"]
    mean, std = 95.0, 15.0
    assert row["avg_monthly_units"] == pytest.approx(mean)
    assert row["std_monthly_units"] == pytest.approx(std)
    assert row["demand_cv"] == pytest.approx(std / mean)


def test_high_revenue_short_history_sku_is_still_priority_through_the_real_pipeline(boundary_profile):
    """Revenue rank wins Priority classification even with short_history=True,
    exercised through the real classify_skus (not a hand-built profile dict).
    This locks the existing, user-confirmed D1 behavior; it does not change it.
    """
    classified, _thresholds = demand.classify_skus(boundary_profile)
    row = classified.set_index("stock_code").loc["ONE_MONTH"]
    assert row["short_history"]
    assert row["sku_class"] == demand.PRIORITY_CLASS


def test_boundary_profile_flows_into_simulate_without_hand_built_inputs(boundary_profile, real_assumptions):
    """The exact output of classify_skus (unmodified) is valid simulate() input --
    proves the interface connects, it does not re-derive simulation.py's math."""
    classified, _ = demand.classify_skus(boundary_profile)
    sim = simulation.simulate(classified, real_assumptions)
    sim_by_code = sim.set_index("stock_code")

    # No full-month sales -> zero demand statistics -> zero safety stock/reorder point.
    assert sim_by_code.loc["ONLY_TRUNC", "safety_stock"] == 0
    assert sim_by_code.loc["ONLY_TRUNC", "reorder_point"] == 0
    assert sim_by_code.loc["ONLY_TRUNC", "economic_order_qty"] == 0


def test_zero_demand_sku_inventory_zero_is_normal_and_positive_is_overstock(boundary_profile, real_assumptions):
    """Uses a temporary config COPY (never the live config) to pin the
    hash-drawn no_demand_units range deterministically, isolating exactly the
    current_inventory=0 vs >0 comparison for a genuine zero-demand SKU."""
    classified, _ = demand.classify_skus(boundary_profile)

    zero_inventory_config = copy.deepcopy(real_assumptions)
    zero_inventory_config["policy_band"] = dict(zero_inventory_config["policy_band"])
    zero_inventory_config["policy_band"]["no_demand_units"] = [0, 0]
    sim_zero = simulation.simulate(classified, zero_inventory_config)
    row_zero = sim_zero.set_index("stock_code").loc["ONLY_TRUNC"]
    assert row_zero["current_inventory"] == 0
    assert row_zero["inventory_risk"] == "Normal"

    positive_inventory_config = copy.deepcopy(real_assumptions)
    positive_inventory_config["policy_band"] = dict(positive_inventory_config["policy_band"])
    positive_inventory_config["policy_band"]["no_demand_units"] = [5, 5]
    sim_positive = simulation.simulate(classified, positive_inventory_config)
    row_positive = sim_positive.set_index("stock_code").loc["ONLY_TRUNC"]
    assert row_positive["current_inventory"] == 5
    assert row_positive["inventory_risk"] == "Overstock Risk"


def test_observed_spread_reaches_service_level_safety_stock(boundary_profile, real_assumptions):
    classified, _ = demand.classify_skus(boundary_profile)
    config = copy.deepcopy(real_assumptions)
    config["supplier_lead_time_days"] = {"values": [30], "probabilities": [1.0]}
    # z(0.8413447460685429) = 1, so independently known mean/std
    # give SS=ceil(std), ROP=ceil(mean + ceil(std)).
    config["safety_stock"]["service_level_by_class"] = {
        key: 0.8413447460685429 for key in simulation.SKU_CLASSES}
    result = simulation.simulate(classified, config).set_index("stock_code")
    for code, expected_ss, expected_rop in [
        ("ONE_MONTH", 0, 900), ("TWO_MONTHS", 29, 149), ("THREE_MONTHS", 15, 110)]:
        assert result.loc[code, "safety_stock"] == expected_ss
        assert result.loc[code, "reorder_point"] == expected_rop
