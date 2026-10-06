"""Measure how stable the simulated inventory layer is on the real SKU list.

For both the legacy method (NumPy draws assigned by row position) and the
current per-SKU hashed method, the script
1. removes one SKU and re-simulates, and
2. shuffles the row order and re-simulates,
then reports the share of the other SKUs whose simulated fields or risk flag
changed. Writes the table to --output (default reports/simulation_stability.csv).

Usage (from the project root):
    python scripts/check_simulation_stability.py --output reports/phase3b1_simulation_stability.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retail_analytics import simulation  # noqa: E402

FIELDS = ["current_inventory", "supplier_lead_time_days", "storage_volume_per_unit", "unit_cost",
          "safety_stock", "reorder_point", "recommended_replenishment_qty"]


def legacy_simulate(profile: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """The pre-Phase 3A method: one global seed, draws taken in row order.

    Uses the Phase 3A replenishment rules so that only the draw method differs.
    """
    assumptions = simulation.with_methods(assumptions, **simulation.PHASE_3A_METHODS)
    out = profile.copy()
    np.random.seed(assumptions["seed"])
    n = len(out)
    out["current_inventory"] = np.where(
        out["sku_class"].isin(["High-Revenue Priority", "High-Turnover Stable"]),
        np.random.randint(20, 300, size=n),
        np.random.randint(0, 120, size=n),
    )
    lead = assumptions["supplier_lead_time_days"]
    out["supplier_lead_time_days"] = np.random.choice(lead["values"], size=n, p=lead["probabilities"])
    out["storage_volume_per_unit"] = np.random.uniform(0.1, 3.0, size=n).round(2)
    out["unit_cost"] = (out["avg_unit_price"] * np.random.uniform(0.35, 0.65, size=n)).round(2)
    out["policy_position"] = np.nan
    return simulation.apply_replenishment_rules(out, assumptions)


def changed_share(base: pd.DataFrame, other: pd.DataFrame) -> tuple[float, float]:
    base = base.set_index("stock_code")
    other = other.set_index("stock_code")
    common = other.index
    fields_changed = (base.loc[common, FIELDS] != other.loc[common, FIELDS]).any(axis=1).mean()
    risk_changed = (base.loc[common, "inventory_risk"] != other.loc[common, "inventory_risk"]).mean()
    return float(fields_changed), float(risk_changed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check simulated-layer stability on the real SKU list.")
    parser.add_argument("--output", default="reports/simulation_stability.csv")
    args = parser.parse_args()
    assumptions = simulation.load_assumptions("config/simulation_assumptions.json")
    profile = pd.read_csv("outputs/sku_profile_classification.csv", dtype={"stock_code": "string"})
    scenarios = {
        "remove first SKU": profile.iloc[1:],
        "remove middle SKU": profile.drop(index=len(profile) // 2),
        "shuffle row order": profile.sample(frac=1, random_state=0),
    }
    methods = {
        "legacy row-position draws": lambda p: legacy_simulate(p, assumptions),
        "per-SKU hashed draws, Phase 3A rules": lambda p: simulation.simulate(
            p, simulation.with_methods(assumptions, **simulation.PHASE_3A_METHODS)
        ),
        "per-SKU hashed draws, current model": lambda p: simulation.simulate(p, assumptions),
    }
    rows = []
    for method_name, run in methods.items():
        base = run(profile)
        for scenario_name, variant in scenarios.items():
            fields, risk = changed_share(base, run(variant))
            rows.append((method_name, scenario_name, len(profile), round(fields, 4), round(risk, 4)))
    report = pd.DataFrame(rows, columns=[
        "method", "scenario", "sku_count", "share_of_other_skus_with_changed_simulated_fields",
        "share_of_other_skus_with_changed_risk_flag",
    ])
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
