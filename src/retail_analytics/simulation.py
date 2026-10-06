"""Deterministic, per-SKU simulated inventory layer.

The public dataset has no inventory, lead-time, cost, or storage data, so these
fields are simulated. Each random draw is derived from a SHA-256 hash of
``seed | field | stock_code``, so a SKU keeps the same draws no matter which
other SKUs are present or how the rows are ordered.

The model is chosen in ``assumptions["methods"]``:

- ``inventory``: ``fixed_range`` (Phase 3A) or ``policy_band`` (reorder point + p x EOQ)
- ``safety_stock``: ``volatility_factor`` (Phase 3A) or ``service_level``
- ``order_quantity``: ``top_up`` (Phase 3A) or ``eoq``
- ``overstock``: ``coverage_only`` (Phase 3A) or ``max_stock``
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

SIMULATED_FIELDS = [
    "policy_position",
    "supplier_lead_time_days",
    "storage_volume_per_unit",
    "unit_cost",
]
DERIVED_FIELDS = [
    "current_inventory",
    "avg_daily_demand",
    "service_level",
    "safety_stock_z",
    "safety_stock",
    "reorder_point",
    "annual_demand_units",
    "economic_order_qty",
    "eoq_capped",
    "max_stock_level",
    "recommended_replenishment_qty",
    "inventory_coverage_days",
    "inventory_risk",
    "excess_units",
    "warehouse_strategy",
]
VALID_METHODS = {
    "inventory": {"fixed_range", "policy_band"},
    "safety_stock": {"volatility_factor", "service_level"},
    "order_quantity": {"top_up", "eoq"},
    "overstock": {"coverage_only", "max_stock"},
}
PHASE_3A_METHODS = {
    "inventory": "fixed_range",
    "safety_stock": "volatility_factor",
    "order_quantity": "top_up",
    "overstock": "coverage_only",
}
SKU_CLASSES = [
    "High-Revenue Priority",
    "High-Turnover Stable",
    "High-Turnover Volatile",
    "Regular",
    "Long-Tail",
]


def validate_assumptions(assumptions: dict) -> None:
    methods = assumptions.get("methods", PHASE_3A_METHODS)
    for key, allowed in VALID_METHODS.items():
        if methods.get(key) not in allowed:
            raise ValueError(f"methods.{key} must be one of {sorted(allowed)}")

    lead = assumptions["supplier_lead_time_days"]
    if len(lead["values"]) != len(lead["probabilities"]):
        raise ValueError("Lead-time values and probabilities must have the same length.")
    if not np.isclose(sum(lead["probabilities"]), 1.0):
        raise ValueError("Lead-time probabilities must sum to 1.")

    inv = assumptions["current_inventory"]
    if inv["priority_min"] > inv["priority_max"] or inv["other_min"] > inv["other_max"]:
        raise ValueError("Inventory ranges must have min <= max.")

    if methods["inventory"] == "policy_band":
        if methods["order_quantity"] != "eoq":
            raise ValueError("methods.inventory = policy_band needs methods.order_quantity = eoq.")
        band = assumptions["policy_band"]
        missing = sorted(set(SKU_CLASSES) - set(band["position_by_class"]))
        if missing:
            raise ValueError("policy_band.position_by_class is missing: " + ", ".join(missing))
        for name, (low, high) in band["position_by_class"].items():
            if not low <= high:
                raise ValueError(f"policy_band range for {name} must satisfy min <= max.")
        low, high = band["no_demand_units"]
        if not 0 <= low <= high:
            raise ValueError("policy_band.no_demand_units must satisfy 0 <= min <= max.")

    if methods["safety_stock"] == "service_level":
        levels = assumptions["safety_stock"]["service_level_by_class"]
        missing = sorted(set(SKU_CLASSES) - set(levels))
        if missing:
            raise ValueError("service_level_by_class is missing: " + ", ".join(missing))
        for name, level in levels.items():
            if not 0.5 <= level < 1:
                raise ValueError(f"Service level for {name} must be in [0.5, 1).")

    if methods["order_quantity"] == "eoq":
        oq = assumptions["order_quantity"]
        if oq["ordering_cost_gbp"] <= 0 or oq["annual_holding_rate"] <= 0:
            raise ValueError("Ordering cost and holding rate must be positive.")
        if oq.get("max_order_coverage_days") is not None and oq["max_order_coverage_days"] <= 0:
            raise ValueError("max_order_coverage_days must be positive when set.")

    if methods["overstock"] == "max_stock" and methods["order_quantity"] != "eoq":
        raise ValueError("methods.overstock = max_stock needs methods.order_quantity = eoq.")


def load_assumptions(path: str | Path) -> dict:
    assumptions = json.loads(Path(path).read_text())
    assumptions.setdefault("methods", dict(PHASE_3A_METHODS))
    validate_assumptions(assumptions)
    return assumptions


def with_methods(assumptions: dict, **methods: str) -> dict:
    """Copy of ``assumptions`` with some model methods replaced."""
    updated = copy.deepcopy(assumptions)
    updated["methods"].update(methods)
    validate_assumptions(updated)
    return updated


def sku_uniform(stock_codes: pd.Series, field: str, seed: int) -> np.ndarray:
    """Uniform [0, 1) draw per stock code, independent of row order."""
    values = []
    for code in stock_codes.astype(str):
        digest = hashlib.sha256(f"{seed}|{field}|{code}".encode("utf-8")).digest()
        values.append(int.from_bytes(digest[:8], "big") / 2**64)
    return np.asarray(values, dtype=float)


def _uniform_int(u: np.ndarray, low, high) -> np.ndarray:
    """Integer in [low, high] inclusive (element-wise bounds allowed)."""
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    return (low + np.floor(u * (high - low + 1))).astype(int)


def _round_half_up(values) -> np.ndarray:
    return np.floor(np.asarray(values, dtype=float) + 0.5)


def simulate_inventory_fields(profile: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Add the per-SKU random draws to a SKU profile.

    Needs ``stock_code``, ``sku_class`` and ``avg_unit_price``. With the
    ``fixed_range`` method the current inventory is drawn here; with
    ``policy_band`` only the position ``p`` is drawn here, and the inventory
    is set in :func:`apply_replenishment_rules` once the reorder point and
    EOQ are known.
    """
    seed = assumptions["seed"]
    methods = assumptions["methods"]
    codes = profile["stock_code"]
    out = profile.copy()

    if methods["inventory"] == "fixed_range":
        inv = assumptions["current_inventory"]
        u_inv = sku_uniform(codes, "current_inventory", seed)
        priority = out["sku_class"].isin(inv["priority_classes"]).to_numpy()
        out["current_inventory"] = np.where(
            priority,
            _uniform_int(u_inv, inv["priority_min"], inv["priority_max"]),
            _uniform_int(u_inv, inv["other_min"], inv["other_max"]),
        )
        out["policy_position"] = np.nan
    else:
        bounds = out["sku_class"].map(assumptions["policy_band"]["position_by_class"])
        if bounds.isna().any():
            raise ValueError("No policy_band range for classes: " + ", ".join(sorted(out.loc[bounds.isna(), "sku_class"].unique())))
        low = bounds.str[0].to_numpy(dtype=float)
        high = bounds.str[1].to_numpy(dtype=float)
        u_pos = sku_uniform(codes, "policy_position", seed)
        out["policy_position"] = np.round(low + u_pos * (high - low), 4)

    lead = assumptions["supplier_lead_time_days"]
    cumulative = np.cumsum(lead["probabilities"])
    cumulative[-1] = 1.0
    u_lead = sku_uniform(codes, "supplier_lead_time_days", seed)
    out["supplier_lead_time_days"] = np.asarray(lead["values"])[np.searchsorted(cumulative, u_lead, side="right")]

    vol = assumptions["storage_volume_per_unit"]
    u_vol = sku_uniform(codes, "storage_volume_per_unit", seed)
    out["storage_volume_per_unit"] = (vol["min"] + u_vol * (vol["max"] - vol["min"])).round(vol["decimals"])

    ratio = assumptions["unit_cost_ratio"]
    u_cost = sku_uniform(codes, "unit_cost_ratio", seed)
    cost_ratio = ratio["min"] + u_cost * (ratio["max"] - ratio["min"])
    out["unit_cost"] = (out["avg_unit_price"] * cost_ratio).round(2)
    return out


def z_score(service_level: float) -> float:
    return NormalDist().inv_cdf(service_level)


def service_level_safety_stock(std_monthly_units, lead_time_days, service_level, days_per_month=30) -> np.ndarray:
    """z x monthly demand std x sqrt(lead time in months), rounded up to whole units."""
    z = np.vectorize(z_score)(np.asarray(service_level, dtype=float))
    raw = z * np.asarray(std_monthly_units, dtype=float) * np.sqrt(np.asarray(lead_time_days, dtype=float) / days_per_month)
    return np.ceil(np.round(raw, 9))


def economic_order_quantity(annual_demand_units, ordering_cost, unit_cost, holding_rate) -> np.ndarray:
    """sqrt(2 D S / (c h)), rounded up; 0 when there is no demand or no cost.

    Uncapped; :func:`apply_replenishment_rules` applies the coverage cap.
    """
    demand = np.asarray(annual_demand_units, dtype=float)
    cost = np.asarray(unit_cost, dtype=float)
    holding = cost * holding_rate
    with np.errstate(divide="ignore", invalid="ignore"):
        eoq = np.sqrt(2 * demand * ordering_cost / holding)
    eoq = np.where((demand > 0) & (holding > 0), np.ceil(np.round(eoq, 9)), 0.0)
    return eoq


def apply_replenishment_rules(sim: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Safety stock, reorder point, order quantity, coverage, risk, excess, strategy."""
    out = sim.copy()
    methods = assumptions["methods"]
    days_per_month = assumptions["days_per_month"]
    ss_cfg = assumptions["safety_stock"]

    out["avg_daily_demand"] = out["avg_monthly_units"] / days_per_month
    lead_time_demand = out["avg_daily_demand"] * out["supplier_lead_time_days"]

    if methods["safety_stock"] == "volatility_factor":
        volatility_factor = ss_cfg["base_factor"] + out["demand_cv"].clip(0, ss_cfg["cv_cap"]) * ss_cfg["cv_factor"]
        out["service_level"] = np.nan
        out["safety_stock_z"] = np.nan
        out["safety_stock"] = (lead_time_demand * volatility_factor).round(0)
        out["reorder_point"] = (lead_time_demand + out["safety_stock"]).round(0)
    else:
        levels = out["sku_class"].map(ss_cfg["service_level_by_class"]).astype(float)
        out["service_level"] = levels
        out["safety_stock_z"] = levels.map(z_score).round(4)
        out["safety_stock"] = service_level_safety_stock(
            out["std_monthly_units"], out["supplier_lead_time_days"], levels, days_per_month
        )
        out["reorder_point"] = np.ceil(np.round(lead_time_demand + out["safety_stock"], 9))

    daily = out["avg_daily_demand"]
    if methods["order_quantity"] == "top_up":
        # EOQ-only config (``order_quantity`` section) is never read on this path,
        # so a legitimate top_up config without that section stays valid.
        out["annual_demand_units"] = np.nan
        out["economic_order_qty"] = np.nan
        out["eoq_capped"] = False
        out["max_stock_level"] = np.nan
    else:
        oq = assumptions["order_quantity"]
        out["annual_demand_units"] = out["avg_monthly_units"] * oq["months_per_year"]
        eoq = economic_order_quantity(
            out["annual_demand_units"], oq["ordering_cost_gbp"], out["unit_cost"], oq["annual_holding_rate"]
        )
        cap_days = oq.get("max_order_coverage_days")
        if cap_days is None:
            cap = np.full(len(out), np.inf)
        else:
            cap = np.where(daily > 0, np.maximum(np.ceil(np.round(daily * cap_days, 9)), 1.0), 0.0)
        out["eoq_capped"] = eoq > cap
        out["economic_order_qty"] = np.minimum(eoq, cap)
        out["max_stock_level"] = out["reorder_point"] + out["economic_order_qty"]

    if methods["inventory"] == "policy_band":
        band = assumptions["policy_band"]
        position_units = out["reorder_point"] + out["policy_position"] * out["economic_order_qty"]
        no_low, no_high = band["no_demand_units"]
        no_demand_units = _uniform_int(sku_uniform(out["stock_code"], "no_demand_units", assumptions["seed"]), no_low, no_high)
        out["current_inventory"] = np.where(
            daily > 0, _round_half_up(np.clip(position_units, 0, None)), no_demand_units
        ).astype(int)

    shortfall = (out["reorder_point"] - out["current_inventory"]).clip(lower=0)
    if methods["order_quantity"] == "top_up":
        out["recommended_replenishment_qty"] = shortfall.round(0)
    else:
        needs_order = out["current_inventory"] < out["reorder_point"]
        out["recommended_replenishment_qty"] = np.where(
            needs_order, np.maximum(out["economic_order_qty"], shortfall), 0.0
        )

    out["inventory_coverage_days"] = np.where(
        daily > 0, out["current_inventory"] / daily.where(daily > 0, 1), np.inf
    )

    over = assumptions["overstock"]
    coverage_limit_units = daily * over["coverage_days"]
    stockout = out["current_inventory"] < out["reorder_point"]
    if methods["overstock"] == "coverage_only":
        overstock = (out["inventory_coverage_days"] > over["coverage_days"]) & out["sku_class"].isin(over["classes"])
        excess_threshold = coverage_limit_units
    else:
        excess_threshold = np.maximum(out["max_stock_level"].fillna(out["reorder_point"]), coverage_limit_units)
        overstock = (out["current_inventory"] > excess_threshold) & (out["inventory_coverage_days"] > over["coverage_days"])
    out["inventory_risk"] = np.select([stockout, overstock], ["Stockout Risk", "Overstock Risk"], default="Normal")
    out["excess_units"] = np.where(
        out["inventory_risk"] == "Overstock Risk",
        (out["current_inventory"] - excess_threshold).clip(lower=0),
        0.0,
    ).round(2)

    out["warehouse_strategy"] = np.select(
        [
            out["inventory_risk"] == "Overstock Risk",
            out["sku_class"] == "High-Revenue Priority",
            out["sku_class"] == "High-Turnover Stable",
            out["sku_class"] == "High-Turnover Volatile",
            out["sku_class"] == "Long-Tail",
        ],
        [
            "Overstock Review / Reduce Replenishment",
            "Local Warehouse Priority",
            "Stable Local Warehouse Inventory",
            "Small-Batch Replenishment / Monitor Closely",
            "External or Limited Stock Strategy",
        ],
        default="Standard Replenishment Review",
    )
    return out


def simulate(profile: pd.DataFrame, assumptions: dict) -> pd.DataFrame:
    """Simulated fields plus replenishment rules in one call."""
    return apply_replenishment_rules(simulate_inventory_fields(profile, assumptions), assumptions)
