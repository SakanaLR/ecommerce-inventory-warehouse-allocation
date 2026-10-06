from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from retail_analytics import simulation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = PROJECT_ROOT / "config" / "simulation_assumptions.json"
PHASE_3A_SNAPSHOT = PROJECT_ROOT / "reports" / "baseline_end_phase3a" / "outputs" / "sku_inventory_simulation.csv"
PHASE_3A_CONFIG_SNAPSHOT = PROJECT_ROOT / "reports" / "baseline_end_phase3a" / "simulation_assumptions_phase3a.json"
FIELDS = simulation.SIMULATED_FIELDS + simulation.DERIVED_FIELDS
CLASSES = simulation.SKU_CLASSES


@pytest.fixture
def assumptions() -> dict:
    return simulation.load_assumptions(ASSUMPTIONS_PATH)


@pytest.fixture
def phase_3a(assumptions) -> dict:
    return simulation.with_methods(assumptions, **simulation.PHASE_3A_METHODS)


@pytest.fixture
def profile() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 3000
    avg = rng.uniform(0, 500, size=n)
    avg[:30] = 0.0  # some SKUs without demand
    cv = rng.uniform(0, 3, size=n)
    return pd.DataFrame({
        "stock_code": [f"SKU{i:05d}" for i in range(n)],
        "sku_class": rng.choice(CLASSES, size=n),
        "avg_unit_price": rng.uniform(0.5, 20, size=n).round(2),
        "avg_monthly_units": avg,
        "std_monthly_units": avg * cv,
        "demand_cv": cv,
    })


# ---------------------------------------------------------------------------
# Stability and determinism (both models)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", ["current", "phase_3a"])
def test_same_inputs_give_identical_results(profile, assumptions, phase_3a, model):
    config = assumptions if model == "current" else phase_3a
    pd.testing.assert_frame_equal(simulation.simulate(profile, config), simulation.simulate(profile, config))


@pytest.mark.parametrize("model", ["current", "phase_3a"])
def test_removing_or_reordering_skus_does_not_change_other_skus(profile, assumptions, phase_3a, model):
    config = assumptions if model == "current" else phase_3a
    full = simulation.simulate(profile, config).set_index("stock_code")
    reduced = simulation.simulate(profile.drop(index=[0, 17, 1500]), config).set_index("stock_code")
    shuffled = simulation.simulate(profile.sample(frac=1, random_state=7), config).set_index("stock_code")
    pd.testing.assert_frame_equal(full.loc[reduced.index, FIELDS], reduced[FIELDS])
    pd.testing.assert_frame_equal(full[FIELDS], shuffled.loc[full.index, FIELDS])


def test_changing_the_seed_changes_draws(profile, assumptions):
    other = dict(assumptions, seed=assumptions["seed"] + 1)
    a = simulation.simulate(profile, assumptions)
    b = simulation.simulate(profile, other)
    assert (a["policy_position"] != b["policy_position"]).mean() > 0.9


def test_draws_respect_configured_ranges_and_probabilities(profile, phase_3a):
    sim = simulation.simulate_inventory_fields(profile, phase_3a)
    inv = phase_3a["current_inventory"]
    priority = sim["sku_class"].isin(inv["priority_classes"])
    assert sim.loc[priority, "current_inventory"].between(inv["priority_min"], inv["priority_max"]).all()
    assert sim.loc[~priority, "current_inventory"].between(inv["other_min"], inv["other_max"]).all()
    assert sim["storage_volume_per_unit"].between(0.1, 3.0).all()
    ratio = sim["unit_cost"] / sim["avg_unit_price"]
    assert ratio.between(0.35 - 0.01, 0.65 + 0.01).all()

    lead = phase_3a["supplier_lead_time_days"]
    shares = sim["supplier_lead_time_days"].value_counts(normalize=True)
    for value, probability in zip(lead["values"], lead["probabilities"]):
        assert shares.get(value, 0) == pytest.approx(probability, abs=0.02)


# ---------------------------------------------------------------------------
# Phase 3B-1 formulas
# ---------------------------------------------------------------------------

def test_service_level_safety_stock_matches_hand_calculation():
    # z(0.95) = 1.644854; 1.644854 * 100 * sqrt(30 / 30) = 164.49 -> 165
    assert simulation.service_level_safety_stock([100.0], [30], [0.95])[0] == 165
    # z(0.98) = 2.053749; 2.053749 * 60 * sqrt(15 / 30) = 87.13 -> 88
    assert simulation.service_level_safety_stock([60.0], [15], [0.98])[0] == 88
    assert simulation.service_level_safety_stock([0.0], [30], [0.98])[0] == 0


def test_safety_stock_never_falls_when_service_level_rises():
    levels = np.array([0.80, 0.85, 0.90, 0.95, 0.98, 0.99])
    stock = simulation.service_level_safety_stock(np.full(6, 250.0), np.full(6, 21), levels)
    assert np.all(np.diff(stock) >= 0)


def test_economic_order_quantity_matches_hand_calculation():
    # sqrt(2 * 1200 * 25 / (2.00 * 0.25)) = sqrt(120000) = 346.41 -> 347
    assert simulation.economic_order_quantity([1200.0], 25.0, [2.0], 0.25)[0] == 347
    assert simulation.economic_order_quantity([0.0], 25.0, [2.0], 0.25)[0] == 0
    assert simulation.economic_order_quantity([100.0], 25.0, [0.0], 0.25)[0] == 0


def one_sku(assumptions, **overrides):
    row = {
        "stock_code": "A", "sku_class": "Regular", "avg_unit_price": 4.0,
        "avg_monthly_units": 30.0, "std_monthly_units": 15.0, "demand_cv": 0.5,
        "supplier_lead_time_days": 30, "unit_cost": 2.0, "policy_position": 0.5,
    }
    row.update(overrides)
    return simulation.apply_replenishment_rules(pd.DataFrame([row]), assumptions).iloc[0]


def test_reorder_point_eoq_cap_and_policy_band_inventory(assumptions):
    # Regular: service level 0.90, z = 1.281552
    # SS = ceil(1.281552 * 15 * 1) = 20; ROP = ceil(30 + 20) = 50
    # EOQ = ceil(sqrt(2 * 360 * 25 / 0.5)) = ceil(189.74) = 190; cap = 180 days * 1/day = 180
    row = one_sku(assumptions)
    assert row["safety_stock"] == 20
    assert row["reorder_point"] == 50
    assert row["economic_order_qty"] == 180
    assert row["eoq_capped"]
    assert row["max_stock_level"] == 230
    # inventory = round(50 + 0.5 * 180) = 140 -> between ROP and max stock
    assert row["current_inventory"] == 140
    assert row["inventory_risk"] == "Normal"
    assert row["recommended_replenishment_qty"] == 0


def test_below_reorder_point_orders_at_least_the_eoq(assumptions):
    row = one_sku(assumptions, policy_position=-0.2)  # 50 - 36 = 14 units
    assert row["current_inventory"] == 14
    assert row["inventory_risk"] == "Stockout Risk"
    assert row["recommended_replenishment_qty"] == 180  # max(EOQ 180, shortfall 36)


def test_overstock_needs_both_excess_and_long_coverage(assumptions):
    # p = 2.0 -> 50 + 360 = 410 units = 410 days of cover; threshold max(230, 180) = 230
    row = one_sku(assumptions, policy_position=2.0)
    assert row["inventory_risk"] == "Overstock Risk"
    assert row["excess_units"] == 180
    # p = 1.1 -> 248 units: above max stock (230) and 248 days of cover -> overstock
    assert one_sku(assumptions, policy_position=1.1)["inventory_risk"] == "Overstock Risk"
    # High demand: 3,000/month -> EOQ well below 180 days; p = 1.2 is above max stock
    # but covers fewer than 180 days, so it is not overstock.
    busy = one_sku(assumptions, avg_monthly_units=3000.0, std_monthly_units=900.0, unit_cost=5.0, policy_position=1.2)
    assert busy["current_inventory"] > busy["max_stock_level"]
    assert busy["inventory_coverage_days"] < 180
    assert busy["inventory_risk"] == "Normal"


def test_policy_band_positions_and_inventory_follow_config(profile, assumptions):
    sim = simulation.simulate(profile, assumptions)
    bands = assumptions["policy_band"]["position_by_class"]
    low = sim["sku_class"].map(lambda c: bands[c][0])
    high = sim["sku_class"].map(lambda c: bands[c][1])
    assert sim["policy_position"].between(low, high).all()

    has_demand = sim["avg_daily_demand"] > 0
    expected = np.floor(np.clip(sim["reorder_point"] + sim["policy_position"] * sim["economic_order_qty"], 0, None) + 0.5)
    assert (sim.loc[has_demand, "current_inventory"] == expected[has_demand]).all()
    no_low, no_high = assumptions["policy_band"]["no_demand_units"]
    assert sim.loc[~has_demand, "current_inventory"].between(no_low, no_high).all()
    cap = np.ceil(sim["avg_daily_demand"] * 180)
    assert (sim.loc[has_demand, "economic_order_qty"] <= np.maximum(cap[has_demand], 1)).all()


def test_zero_demand_sku_is_handled(assumptions):
    row = one_sku(assumptions, avg_monthly_units=0.0, std_monthly_units=0.0, demand_cv=0.0)
    assert row["safety_stock"] == 0
    assert row["reorder_point"] == 0
    assert row["economic_order_qty"] == 0
    assert np.isinf(row["inventory_coverage_days"])
    assert row["inventory_risk"] in {"Normal", "Overstock Risk"}


# ---------------------------------------------------------------------------
# EOQ/threshold boundaries and stability invariants (T2)
#
# These check properties that must hold for ANY legal parameter choice, not
# just the current live config's specific numbers (current capped-SKU counts
# or overstock totals are diagnostic snapshots, not a general contract -- see
# docs/model_assumptions_review.md §7 / docs/model_assumptions_plan.md §5).
# ---------------------------------------------------------------------------

def test_eoq_capped_boundary_exactly_at_the_cap_is_not_capped(assumptions):
    # daily demand = 1 (avg_monthly_units=30) -> cap = ceil(1*180) = 180.
    # unit_cost chosen so uncapped EOQ == 180 exactly: sqrt(2*360*25/(c*0.25)) = 180
    # => c = 72000/32400 = 20/9.
    row = one_sku(assumptions, avg_monthly_units=30.0, std_monthly_units=0.0, unit_cost=20 / 9)
    assert row["economic_order_qty"] == 180
    assert not row["eoq_capped"]


def test_eoq_capped_boundary_just_over_the_cap_is_capped(assumptions):
    # Same demand, slightly lower unit cost -> uncapped EOQ pushes just past 180.
    row = one_sku(assumptions, avg_monthly_units=30.0, std_monthly_units=0.0, unit_cost=2.0)
    assert row["economic_order_qty"] == 180  # capped down to the coverage limit
    assert row["eoq_capped"]


def test_eoq_order_quantity_never_negative_for_tiny_positive_demand(assumptions):
    # Regression guard for the cap's `max(..., 1.0)` floor: a technically-positive
    # but tiny demand must not produce a zero or negative capped order quantity.
    row = one_sku(assumptions, avg_monthly_units=1e-9, std_monthly_units=0.0, unit_cost=50.0)
    assert row["economic_order_qty"] >= 1


def test_eoq_does_not_decrease_when_ordering_cost_increases():
    low = simulation.economic_order_quantity([1200.0], 10.0, [2.0], 0.25)[0]
    high = simulation.economic_order_quantity([1200.0], 100.0, [2.0], 0.25)[0]
    assert high >= low


def test_eoq_does_not_increase_with_holding_rate_or_unit_cost():
    base = simulation.economic_order_quantity([1200.0], 25.0, [2.0], 0.25)[0]
    higher_rate = simulation.economic_order_quantity([1200.0], 25.0, [2.0], 0.50)[0]
    higher_cost = simulation.economic_order_quantity([1200.0], 25.0, [4.0], 0.25)[0]
    assert higher_rate <= base
    assert higher_cost <= base


def test_looser_cap_does_not_decrease_the_final_order_quantity(assumptions):
    tight = copy.deepcopy(assumptions)
    tight["order_quantity"] = dict(tight["order_quantity"], max_order_coverage_days=90)
    loose = copy.deepcopy(assumptions)
    loose["order_quantity"] = dict(loose["order_quantity"], max_order_coverage_days=365)

    row_tight = one_sku(tight, avg_monthly_units=30.0, std_monthly_units=0.0, unit_cost=2.0)
    row_loose = one_sku(loose, avg_monthly_units=30.0, std_monthly_units=0.0, unit_cost=2.0)
    assert row_tight["economic_order_qty"] == 90
    assert row_loose["economic_order_qty"] == 190


def test_current_inventory_equal_to_reorder_point_is_not_stockout(assumptions):
    # policy_position=0.0 -> current_inventory = round(ROP + 0*EOQ) = ROP exactly.
    row = one_sku(assumptions, policy_position=0.0)
    assert row["current_inventory"] == row["reorder_point"]
    assert row["inventory_risk"] != "Stockout Risk"


def test_current_inventory_equal_to_max_stock_level_is_not_overstock(assumptions):
    # From test_reorder_point_eoq_cap_and_policy_band_inventory: ROP=50, EOQ=180.
    # p=1.0 -> current_inventory = round(50 + 1.0*180) = 230 = max_stock_level exactly.
    row = one_sku(assumptions, policy_position=1.0)
    assert row["current_inventory"] == row["max_stock_level"]
    assert row["inventory_risk"] != "Overstock Risk"


def test_current_inventory_one_unit_over_max_stock_level_is_overstock(assumptions):
    row = one_sku(assumptions, policy_position=1 + 1 / 180)
    assert row["current_inventory"] == row["max_stock_level"] + 1
    assert row["inventory_risk"] == "Overstock Risk"


def test_recommended_replenishment_uses_shortfall_when_it_exceeds_the_capped_eoq(assumptions):
    # Large observed spread raises ROP; the EOQ really is capped at 180.
    row = one_sku(
        assumptions, avg_monthly_units=30.0, std_monthly_units=1000.0,
        unit_cost=2.0, supplier_lead_time_days=30, policy_position=-100.0,
    )
    assert row["eoq_capped"]
    assert row["economic_order_qty"] == 180
    shortfall = row["reorder_point"] - row["current_inventory"]
    assert shortfall > row["economic_order_qty"]
    assert row["recommended_replenishment_qty"] == shortfall


def test_fixed_inventory_experiment_keeps_rop_safety_stock_and_inventory_fixed(assumptions):
    """Mirrors the 'Experiment A' methodology in docs/model_assumptions_review.md
    §5: setting methods.inventory="fixed_range" makes apply_replenishment_rules
    skip its policy_band inventory-regeneration branch, so a given
    current_inventory passes through unchanged while thresholds/recommendations
    still respond to the changed order-quantity config. This must hold for any
    legal cap choice, not just the specific 180-day live value."""
    row_kwargs = dict(
        stock_code="A", sku_class="Regular", avg_unit_price=4.0,
        avg_monthly_units=30.0, std_monthly_units=15.0, demand_cv=0.5,
        supplier_lead_time_days=30, unit_cost=2.0, current_inventory=200,
    )

    def fixed_inventory_config(cap_days):
        adapted = copy.deepcopy(assumptions)
        adapted["methods"] = dict(adapted["methods"])
        adapted["methods"]["inventory"] = "fixed_range"  # skip inventory regeneration
        adapted["order_quantity"] = dict(adapted["order_quantity"], max_order_coverage_days=cap_days)
        return adapted

    tight = simulation.apply_replenishment_rules(pd.DataFrame([row_kwargs]), fixed_inventory_config(30)).iloc[0]
    loose = simulation.apply_replenishment_rules(pd.DataFrame([row_kwargs]), fixed_inventory_config(365)).iloc[0]

    assert tight["reorder_point"] == loose["reorder_point"]
    assert tight["safety_stock"] == loose["safety_stock"]
    assert tight["current_inventory"] == loose["current_inventory"] == 200
    assert loose["economic_order_qty"] >= tight["economic_order_qty"]
    assert loose["max_stock_level"] >= tight["max_stock_level"]
    # A tight enough cap can flag the same fixed inventory as overstock while a
    # looser cap does not -- the point of Experiment A: a fixed snapshot judged
    # against two different thresholds, not a new inventory-generation defect.
    assert tight["inventory_risk"] == "Overstock Risk"
    assert loose["inventory_risk"] == "Normal"


def test_full_regeneration_changes_inventory_but_not_policy_position_or_rop(assumptions):
    """Mirrors 'Experiment B' in docs/model_assumptions_review.md §5: unlike the
    fixed-inventory experiment above, letting inventory stay policy_band means
    current_inventory legitimately changes when the order-quantity cap changes
    (because it is defined as reorder_point + p*EOQ), while the hashed
    policy_position draw and the reorder point/safety stock (independent of
    the cap) do not."""
    small_profile = pd.DataFrame({
        "stock_code": ["X1", "X2", "X3"],
        "sku_class": ["Regular", "Regular", "Regular"],
        "avg_unit_price": [4.0, 4.0, 4.0],
        "avg_monthly_units": [30.0, 60.0, 90.0],
        "std_monthly_units": [15.0, 30.0, 45.0],
        "demand_cv": [0.5, 0.5, 0.5],
    })
    tight = copy.deepcopy(assumptions)
    tight["order_quantity"] = dict(tight["order_quantity"], max_order_coverage_days=30)
    loose = copy.deepcopy(assumptions)
    loose["order_quantity"] = dict(loose["order_quantity"], max_order_coverage_days=365)

    sim_tight = simulation.simulate(small_profile, tight).set_index("stock_code")
    sim_loose = simulation.simulate(small_profile, loose).set_index("stock_code")

    pd.testing.assert_series_equal(sim_tight["policy_position"], sim_loose["policy_position"])
    pd.testing.assert_series_equal(sim_tight["reorder_point"], sim_loose["reorder_point"])
    pd.testing.assert_series_equal(sim_tight["safety_stock"], sim_loose["safety_stock"])
    # Unlike Experiment A, current_inventory is free to change here because it
    # is regenerated from the (now different) EOQ each time.
    assert (sim_tight["current_inventory"] != sim_loose["current_inventory"]).any()


# ---------------------------------------------------------------------------
# Phase 3A model is still reproducible
# ---------------------------------------------------------------------------

def test_phase_3a_formulas(phase_3a):
    sim = pd.DataFrame({
        "stock_code": ["A", "B", "C"],
        "sku_class": ["Regular", "Long-Tail", "High-Revenue Priority"],
        "avg_monthly_units": [300.0, 1.5, 0.0],
        "std_monthly_units": [300.0, 0.0, 0.0],
        "demand_cv": [1.0, 0.0, 0.0],
        "current_inventory": [50, 100, 10],
        "supplier_lead_time_days": [14, 7, 7],
        "unit_cost": [1.0, 1.0, 1.0],
        "policy_position": [np.nan] * 3,
    })
    out = simulation.apply_replenishment_rules(sim, phase_3a).set_index("stock_code")
    assert out.loc["A", "safety_stock"] == 70
    assert out.loc["A", "reorder_point"] == 210
    assert out.loc["A", "recommended_replenishment_qty"] == 160
    assert out.loc["A", "inventory_risk"] == "Stockout Risk"
    assert out.loc["B", "inventory_risk"] == "Overstock Risk"
    assert np.isinf(out.loc["C", "inventory_coverage_days"])
    assert out.loc["C", "inventory_risk"] == "Normal"


@pytest.mark.skipif(not PHASE_3A_SNAPSHOT.exists(), reason="Phase 3A snapshot not available")
def test_phase_3a_methods_reproduce_the_phase_3a_snapshot(phase_3a):
    snapshot = pd.read_csv(PHASE_3A_SNAPSHOT, dtype={"stock_code": "string", "description": "string"})
    phase_3a_fields = [
        "current_inventory", "supplier_lead_time_days", "storage_volume_per_unit", "unit_cost",
        "avg_daily_demand", "safety_stock", "reorder_point", "recommended_replenishment_qty",
        "inventory_coverage_days", "inventory_risk", "warehouse_strategy",
    ]
    rerun = simulation.simulate(snapshot.drop(columns=phase_3a_fields), phase_3a)
    pd.testing.assert_frame_equal(
        snapshot[phase_3a_fields].reset_index(drop=True),
        rerun[phase_3a_fields].reset_index(drop=True),
        check_dtype=False,
    )


# ---------------------------------------------------------------------------
# A legitimate top_up config with no order_quantity section must keep working
# ---------------------------------------------------------------------------

def test_top_up_runs_without_an_order_quantity_section(phase_3a):
    # ``order_quantity`` is only meaningful for the eoq method; a top_up config
    # that omits the section entirely is still valid and must not KeyError.
    minimal = copy.deepcopy(phase_3a)
    del minimal["order_quantity"]
    # fixed_range (Phase 3A) does not derive current_inventory in
    # apply_replenishment_rules, so it must be supplied like test_phase_3a_formulas does.
    row = one_sku(minimal, current_inventory=50)
    assert np.isnan(row["annual_demand_units"])
    assert np.isnan(row["economic_order_qty"])
    assert not row["eoq_capped"]
    assert np.isnan(row["max_stock_level"])


@pytest.mark.skipif(not PHASE_3A_CONFIG_SNAPSHOT.exists(), reason="Phase 3A config snapshot not available")
def test_legacy_top_up_config_without_order_quantity_section_loads_and_simulates(profile):
    legacy = simulation.load_assumptions(PHASE_3A_CONFIG_SNAPSHOT)
    assert "order_quantity" not in legacy
    sim = simulation.simulate(profile, legacy)
    assert sim["annual_demand_units"].isna().all()
    assert sim["economic_order_qty"].isna().all()
    assert (~sim["eoq_capped"]).all()
    assert sim["max_stock_level"].isna().all()


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------

def write_config(tmp_path, config) -> Path:
    path = tmp_path / "assumptions.json"
    path.write_text(json.dumps(config))
    return path


def test_invalid_probabilities_are_rejected(tmp_path, assumptions):
    bad = json.loads(json.dumps(assumptions))
    bad["supplier_lead_time_days"] = {"values": [7, 14], "probabilities": [0.5, 0.4]}
    with pytest.raises(ValueError, match="sum to 1"):
        simulation.load_assumptions(write_config(tmp_path, bad))


def test_policy_band_requires_eoq(assumptions):
    with pytest.raises(ValueError, match="needs methods.order_quantity = eoq"):
        simulation.with_methods(assumptions, order_quantity="top_up")


def test_max_stock_requires_eoq(assumptions):
    # Without eoq, max_stock_level is all-NaN and apply_replenishment_rules would
    # silently fall back to a weaker (EOQ-less) overstock threshold.
    phase_3a = simulation.with_methods(assumptions, **simulation.PHASE_3A_METHODS)
    with pytest.raises(ValueError, match="methods.overstock = max_stock needs methods.order_quantity = eoq"):
        simulation.with_methods(phase_3a, overstock="max_stock")


def test_service_level_must_be_below_one(tmp_path, assumptions):
    bad = json.loads(json.dumps(assumptions))
    bad["safety_stock"]["service_level_by_class"]["Regular"] = 1.0
    with pytest.raises(ValueError, match="Service level"):
        simulation.load_assumptions(write_config(tmp_path, bad))


def test_unknown_method_is_rejected(assumptions):
    with pytest.raises(ValueError, match="methods.inventory"):
        simulation.with_methods(assumptions, inventory="coverage_days")


@pytest.mark.parametrize('inventory,safety_stock,order_quantity,overstock', [
    (inventory, safety, order, over)
    for inventory in ['fixed_range', 'policy_band']
    for safety in ['volatility_factor', 'service_level']
    for order in ['top_up', 'eoq']
    for over in ['coverage_only', 'max_stock']
    if order == 'eoq' or (inventory == 'fixed_range' and over == 'coverage_only')
])
def test_all_legal_method_combinations(profile, assumptions, inventory, safety_stock, order_quantity, overstock):
    config = simulation.with_methods(
        assumptions, inventory=inventory, safety_stock=safety_stock,
        order_quantity=order_quantity, overstock=overstock,
    )
    if order_quantity == 'top_up':
        del config['order_quantity']
    simulation.validate_assumptions(config)
    result = simulation.simulate(profile, config)
    assert result['inventory_risk'].isin(['Normal', 'Stockout Risk', 'Overstock Risk']).all()
    assert result['recommended_replenishment_qty'].notna().all()


def test_coverage_threshold_dominates_max_stock_at_strict_boundary(assumptions):
    # daily=1, ROP=50, Q=ceil(sqrt(72))=9; coverage threshold=180 > ROP+Q.
    at = one_sku(assumptions, unit_cost=1000.0, policy_position=130 / 9)
    above = one_sku(assumptions, unit_cost=1000.0, policy_position=131 / 9)
    assert at['economic_order_qty'] == 9
    assert at['max_stock_level'] == 59
    assert at['current_inventory'] == 180
    assert at['inventory_risk'] == 'Normal'
    assert above['current_inventory'] == 181
    assert above['inventory_risk'] == 'Overstock Risk'
    assert above['excess_units'] == 1


def test_noninteger_coverage_cap_rounds_up_and_none_removes_cap(assumptions):
    # .33 / 30 * 180 = 1.98 -> 2 units; uncapped EOQ=ceil(sqrt(396))=20.
    capped = one_sku(assumptions, avg_monthly_units=.33, std_monthly_units=0., unit_cost=2.)
    config = copy.deepcopy(assumptions)
    config['order_quantity']['max_order_coverage_days'] = None
    uncapped = one_sku(config, avg_monthly_units=.33, std_monthly_units=0., unit_cost=2.)
    assert capped['economic_order_qty'] == 2
    assert capped['eoq_capped']
    assert uncapped['economic_order_qty'] == 20
    assert not uncapped['eoq_capped']
