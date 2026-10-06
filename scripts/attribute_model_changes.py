"""Step-by-step attribution of the Phase 3B-1 inventory model changes.

Starting from the Phase 3A model, one method is switched at a time, so the
change at each step belongs to that method alone. The profile (demand basis
and SKU classes) is held fixed at the live outputs.

Usage (from the project root):
    python scripts/attribute_model_changes.py --output reports/phase3b1_attribution.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from retail_analytics import simulation  # noqa: E402

STEPS = [
    ("0. Phase 3A model", {}),
    ("1. + service-level safety stock", {"safety_stock": "service_level"}),
    ("2. + EOQ order quantity (180-day cap)", {"order_quantity": "eoq"}),
    ("3. + max-stock overstock rule", {"overstock": "max_stock"}),
    ("4. + policy-band inventory (Phase 3B-1)", {"inventory": "policy_band"}),
]


def summarise(sim: pd.DataFrame, holding_rate: float | None) -> dict:
    value = (sim["current_inventory"] * sim["unit_cost"]).round(2)
    stockout = sim["inventory_risk"] == "Stockout Risk"
    shortfall = np.where(stockout, (sim["reorder_point"] - sim["current_inventory"]).clip(lower=0), 0)
    priority = sim["sku_class"] == "High-Revenue Priority"
    # No order_quantity.annual_holding_rate in the config (a legitimate top_up-only
    # config) means holding cost is not available; leave it blank, not 0.
    annual_holding_cost = round((value * holding_rate).round(2).sum(), 2) if holding_rate is not None else None
    return {
        "stockout_skus": int(stockout.sum()),
        "overstock_skus": int((sim["inventory_risk"] == "Overstock Risk").sum()),
        "normal_skus": int((sim["inventory_risk"] == "Normal").sum()),
        "high_revenue_priority_stockout_skus": int((stockout & priority).sum()),
        "estimated_inventory_value": round(value.sum(), 2),
        "annual_holding_cost": annual_holding_cost,
        "stockout_revenue_exposure": round((shortfall * sim["avg_unit_price"]).round(2).sum(), 2),
        "overstock_capital_exposure": round((sim["excess_units"] * sim["unit_cost"]).round(2).sum(), 2),
        "median_safety_stock_units": float(sim["safety_stock"].median()),
        "median_reorder_point_units": float(sim["reorder_point"].median()),
        "recommended_order_units": float(sim["recommended_replenishment_qty"].sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="reports/model_change_attribution.csv")
    args = parser.parse_args()

    current = simulation.load_assumptions("config/simulation_assumptions.json")
    holding_rate = current.get("order_quantity", {}).get("annual_holding_rate")
    profile = pd.read_csv("outputs/sku_profile_classification.csv", dtype={"stock_code": "string"})

    methods = dict(simulation.PHASE_3A_METHODS)
    rows = []
    for label, change in STEPS:
        # Only enable methods requested by this configuration. Historical top_up
        # configs have no EOQ parameters and must never enter the EOQ steps.
        if change and any(current["methods"][key] != value for key, value in change.items()):
            continue
        methods.update(change)
        config = simulation.with_methods(current, **methods)
        rows.append({"step": label, **{f"method_{k}": v for k, v in methods.items()},
                     **summarise(simulation.simulate(profile, config), holding_rate)})

    table = pd.DataFrame(rows)
    if table.iloc[-1][[f"method_{k}" for k in methods]].to_dict() != {f"method_{k}": v for k, v in current["methods"].items()}:
        raise SystemExit("The last step does not match the configured model; update STEPS.")
    table.to_csv(args.output, index=False)
    print(table.drop(columns=[c for c in table.columns if c.startswith("method_")]).to_string(index=False))


if __name__ == "__main__":
    main()
