"""Reproducible, metadata-stamped model-assumptions diagnostics (E1).

This tool reproduces, on demand, the two experiment methodologies and the nine
single-factor sensitivity scenarios described in ``docs/model_assumptions_review.md``
and ``docs/model_assumptions_plan.md``:

- **Experiment A (fixed inventory):** re-applies replenishment rules under a
  changed order-quantity/overstock configuration while *reusing* each SKU's
  already-simulated ``current_inventory`` unchanged. This answers "how would
  the same inventory snapshot be judged under a different policy threshold?"
  It is implemented by calling the real, unmodified
  ``simulation.apply_replenishment_rules`` with ``methods.inventory`` set to
  ``fixed_range`` on an input that already has ``current_inventory`` populated
  from the real policy-band simulation — that setting makes the function skip
  its inventory-generating branch entirely (see ``simulation.py``), so no
  business code is modified or reimplemented here.
- **Experiment B (full regeneration):** calls the real, unmodified
  ``simulation.simulate`` end to end under the changed configuration, with
  ``methods.inventory`` left at ``policy_band`` — current inventory is
  regenerated from the new reorder point / EOQ, exactly as the live model
  would.
- **Sensitivity scenarios 1a/1b/2a/2b/3a/3b/4a/4b/5:** each one changes a
  single parameter group from the live baseline, using Experiment B (full
  regeneration), and reports the actual (not nominal) parameter values
  applied.

Every scenario is built from a **fresh deep copy of the same baseline
configuration** — scenarios never chain off each other's mutated state.

This script never reads or writes the project's official ``config/``,
``outputs/``, ``data/``, or ``notebooks/`` paths for *output*; it refuses to
write into any of them (see ``_ensure_safe_output_dir``). It only *reads* the
profile/config paths you pass in (which may well be the real, live files —
reading them is fine; only the destination is restricted).

This tool does not search for or recommend a "best" parameter set. It reports
what each named, human-chosen scenario produces; it never optimizes.

Usage:
    python scripts/model_assumptions_diagnostics.py \\
        --profile outputs/sku_inventory_simulation.csv \\
        --config config/simulation_assumptions.json \\
        --output-dir /tmp/model_assumptions_diag_run1 \\
        [--scenarios A,B,1a,1b,2a,2b,3a,3b,4a,4b,5 | --scenarios all]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import os
import tempfile
import warnings
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from retail_analytics import simulation  # noqa: E402

# Directories this tool must never write into, however --output-dir is spelled.
_FORBIDDEN_OUTPUT_ROOTS = [
    PROJECT_ROOT / "outputs",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "notebooks",
    PROJECT_ROOT / "reports",
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT,  # also refuses the bare project root itself
]

ALL_SCENARIOS = ["A", "B", "1a", "1b", "2a", "2b", "3a", "3b", "4a", "4b", "5"]


def _ensure_safe_output_dir(raw_path: Path) -> Path:
    resolved = raw_path.resolve()
    for forbidden in _FORBIDDEN_OUTPUT_ROOTS:
        forbidden_resolved = forbidden.resolve()
        if resolved == forbidden_resolved or forbidden_resolved in resolved.parents:
            raise SystemExit(
                f"Refusing to write to {resolved}: it is, or is inside, the official "
                f"directory {forbidden_resolved}. Choose an isolated output directory "
                f"(e.g. under /tmp), never a path inside the repository's tracked folders."
            )
        if resolved in forbidden_resolved.parents:
            raise SystemExit(
                f"Refusing to write to {resolved}: it is an ancestor of the official "
                f"directory {forbidden_resolved} and could shadow or be confused with it."
            )
    if raw_path.is_symlink() or resolved.exists():
        raise ValueError("Output directory must be new and must not be a symlink: " + str(raw_path))
    return resolved


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def collect_run_metadata(profile_path: Path, config_path: Path, seed_override: int | None) -> dict:
    status = _git("status", "--porcelain")
    is_dirty = bool(status)
    diff_sha256 = hashlib.sha256(_git("diff").encode("utf-8")).hexdigest() if is_dirty else None
    staged_sha256 = hashlib.sha256(_git("diff", "--cached").encode("utf-8")).hexdigest()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=PROJECT_ROOT
    ).decode().split("\0")
    untracked_hashes = {name: _sha256_file(PROJECT_ROOT / name) for name in untracked if name}
    # HEAD plus both diffs and untracked contents identify this uncommitted run.
    source_hashes = {str(path.relative_to(PROJECT_ROOT)): _sha256_file(path)
                     for path in [Path(__file__).resolve(), *sorted((PROJECT_ROOT / "src").rglob("*.py"))]}
    return {
        "generated_by": "scripts/model_assumptions_diagnostics.py",
        "code": {
            "commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "working_tree_dirty": is_dirty,
            "uncommitted_paths": status.splitlines() if is_dirty else [],
            "uncommitted_diff_sha256": diff_sha256,
            "staged_diff_sha256": staged_sha256,
            "untracked_file_sha256": untracked_hashes,
            "source_file_sha256": source_hashes,
        },
        "dependencies": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "inputs": {
            "profile_path": str(profile_path),
            "profile_sha256": _sha256_file(profile_path),
            "config_path": str(config_path),
            "config_sha256": _sha256_file(config_path),
        },
        "seed_override": seed_override,
    }


EXPECTED_METHODS = {"inventory": "policy_band", "safety_stock": "service_level",
                    "order_quantity": "eoq", "overstock": "max_stock"}
FLOAT_RTOL, FLOAT_ATOL = 1e-12, 1e-9
EXACT_FIELDS = set(simulation.SIMULATED_FIELDS + simulation.DERIVED_FIELDS) - {
    "avg_daily_demand", "annual_demand_units", "inventory_coverage_days",
}


def validate_diagnostic_config(config: dict) -> None:
    """Validate this diagnostic's scope without changing the business model."""
    if config.get("methods") != EXPECTED_METHODS:
        raise ValueError("Diagnostics require policy_band/service_level/eoq/max_stock methods.")
    def number(value, name, minimum=0, strict=False):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if value < minimum or (strict and value == minimum):
            raise ValueError(f"{name} must be {'>' if strict else '>='} {minimum}")
    if type(config["seed"]) is not int:
        raise ValueError("seed must be an integer")
    number(config["days_per_month"], "days_per_month", strict=True)
    for key in ["ordering_cost_gbp", "annual_holding_rate", "months_per_year"]:
        number(config["order_quantity"][key], key, strict=True)
    cap = config["order_quantity"].get("max_order_coverage_days")
    if cap is not None:
        number(cap, "max_order_coverage_days", strict=True)
    number(config["overstock"]["coverage_days"], "overstock.coverage_days", strict=True)
    lead = config["supplier_lead_time_days"]
    if not lead["values"]:
        raise ValueError("supplier_lead_time_days.values must not be empty")
    for value in lead["values"]:
        number(value, "lead-time value", strict=True)
    for probability in lead["probabilities"]:
        number(probability, "lead-time probability")
    for section in ["unit_cost_ratio", "storage_volume_per_unit"]:
        bounds = config[section]
        number(bounds["min"], section + ".min")
        number(bounds["max"], section + ".max", bounds["min"])
    for bounds in config["policy_band"]["position_by_class"].values():
        if len(bounds) != 2 or not all(np.isfinite(v) for v in bounds):
            raise ValueError("policy_band ranges must contain two finite numbers")
    bounds = config["policy_band"]["no_demand_units"]
    if len(bounds) != 2 or any(type(v) is not int or v < 0 for v in bounds):
        raise ValueError("no_demand_units must contain two nonnegative integers")
    simulation.validate_assumptions(config)


def load_baseline(profile_path: Path, config_path: Path, seed_override: int | None) -> tuple[pd.DataFrame, dict]:
    assumptions = simulation.load_assumptions(config_path)
    validate_diagnostic_config(assumptions)
    saved = pd.read_csv(profile_path, dtype={"stock_code": "string", "description": "string"})
    required = {"stock_code", "sku_class", "avg_unit_price", "avg_monthly_units", "std_monthly_units", "demand_cv"}
    missing = required - set(saved)
    if missing:
        raise ValueError("Profile missing required columns: " + ", ".join(sorted(missing)))
    if saved.empty:
        raise ValueError("Profile must contain at least one SKU")
    codes = saved["stock_code"]
    if codes.isna().any() or codes.str.strip().eq("").any() or codes.str.strip().duplicated().any():
        raise ValueError("stock_code must be nonblank and unique")
    if not saved["sku_class"].isin(simulation.SKU_CLASSES).all():
        raise ValueError("Profile contains missing or unknown sku_class values")
    for name in required - {"stock_code", "sku_class"}:
        values = pd.to_numeric(saved[name], errors="raise")
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{name} must contain finite, nonnegative numbers")
        saved[name] = values
    check_fields = set(simulation.SIMULATED_FIELDS + simulation.DERIVED_FIELDS)
    present = check_fields & set(saved)
    if present and present != check_fields:
        raise ValueError("Saved simulation is incomplete; supply all simulated fields or a raw SKU profile")
    if present:
        # Check against its original seed, not a requested new experiment seed.
        verify_baseline_reproduces_saved(saved, assumptions)
    if seed_override is not None:
        assumptions["seed"] = seed_override
    baseline = simulation.simulate(saved[pre_simulation_columns(saved)], assumptions)
    return baseline, assumptions


def pre_simulation_columns(df: pd.DataFrame) -> list[str]:
    simulated_derived = set(simulation.SIMULATED_FIELDS + simulation.DERIVED_FIELDS)
    return [c for c in df.columns if c not in simulated_derived]


def verify_baseline_reproduces_saved(saved: pd.DataFrame, assumptions: dict) -> None:
    """Same input reruns must give consistent results (acceptance criterion)."""
    profile_columns = pre_simulation_columns(saved)
    recomputed = simulation.simulate(saved[profile_columns], assumptions)
    check_fields = simulation.SIMULATED_FIELDS + simulation.DERIVED_FIELDS
    for field in check_fields:
        pd.testing.assert_series_equal(
            saved[field].reset_index(drop=True), recomputed[field].reset_index(drop=True),
            check_dtype=False, check_exact=field in EXACT_FIELDS,
            rtol=FLOAT_RTOL, atol=FLOAT_ATOL,
        )


def experiment_a_fixed_inventory(saved: pd.DataFrame, new_assumptions: dict) -> pd.DataFrame:
    """Fixed-inventory experiment: reuse every simulated field unchanged, only
    re-apply replenishment rules under the new order-quantity/overstock config.

    Setting methods.inventory="fixed_range" makes apply_replenishment_rules
    skip its policy_band inventory-regeneration branch entirely, so the input
    current_inventory column (and every other already-simulated field) passes
    through unmodified. This calls the real, unmodified function — no
    business logic is duplicated or reimplemented here.
    """
    adapted = copy.deepcopy(new_assumptions)
    adapted["methods"] = dict(adapted["methods"])
    adapted["methods"]["inventory"] = "fixed_range"
    return simulation.apply_replenishment_rules(saved.copy(), adapted)


def experiment_b_full_regeneration(saved: pd.DataFrame, new_assumptions: dict) -> pd.DataFrame:
    """Full regeneration: re-run the entire simulation under the new config."""
    profile_columns = pre_simulation_columns(saved)
    return simulation.simulate(saved[profile_columns], new_assumptions)


def uncapped_variant(assumptions: dict) -> dict:
    updated = copy.deepcopy(assumptions)
    updated["order_quantity"] = dict(updated["order_quantity"])
    updated["order_quantity"]["max_order_coverage_days"] = None
    return updated


# ---------------------------------------------------------------------------
# Sensitivity scenario definitions — each one is a pure function of a fresh
# deep copy of the baseline assumptions, so scenarios never accumulate state.
# ---------------------------------------------------------------------------

def _scenario_1a(assumptions: dict) -> dict:
    updated = copy.deepcopy(assumptions)
    levels = updated["safety_stock"]["service_level_by_class"]
    updated["safety_stock"]["service_level_by_class"] = {k: min(v + 0.03, 0.995) for k, v in levels.items()}
    return updated


def _scenario_1b(assumptions: dict) -> dict:
    updated = copy.deepcopy(assumptions)
    levels = updated["safety_stock"]["service_level_by_class"]
    updated["safety_stock"]["service_level_by_class"] = {k: v - 0.03 for k, v in levels.items()}
    return updated


def _scenario_ordering_cost(assumptions: dict, new_cost: float) -> dict:
    updated = copy.deepcopy(assumptions)
    updated["order_quantity"]["ordering_cost_gbp"] = new_cost
    return updated


def _scenario_holding_rate(assumptions: dict, new_rate: float) -> dict:
    updated = copy.deepcopy(assumptions)
    updated["order_quantity"]["annual_holding_rate"] = new_rate
    return updated


def _scenario_coverage_cap(assumptions: dict, new_cap: float) -> dict:
    updated = copy.deepcopy(assumptions)
    updated["order_quantity"]["max_order_coverage_days"] = new_cap
    return updated


def _scenario_5_lead_time(assumptions: dict) -> dict:
    updated = copy.deepcopy(assumptions)
    lead = updated["supplier_lead_time_days"]
    # Python's built-in round() (round-half-to-even), applied per value, matching
    # the review's independently reproduced actual values: [10, 21, 32, 45, 68].
    updated["supplier_lead_time_days"] = {
        "values": [round(v * 1.5) for v in lead["values"]],
        "probabilities": list(lead["probabilities"]),
    }
    return updated


SCENARIO_BUILDERS = {
    "1a": _scenario_1a,
    "1b": _scenario_1b,
    "2a": lambda a: _scenario_ordering_cost(a, 12.5),
    "2b": lambda a: _scenario_ordering_cost(a, 50.0),
    "3a": lambda a: _scenario_holding_rate(a, 0.15),
    "3b": lambda a: _scenario_holding_rate(a, 0.35),
    "4a": lambda a: _scenario_coverage_cap(a, 365),
    "4b": lambda a: _scenario_coverage_cap(a, 90),
    "5": _scenario_5_lead_time,
}


def actual_parameter_change(scenario: str, baseline: dict, changed: dict) -> dict:
    if scenario in ("1a", "1b"):
        return {
            "service_level_by_class_before": baseline["safety_stock"]["service_level_by_class"],
            "service_level_by_class_after": changed["safety_stock"]["service_level_by_class"],
        }
    if scenario in ("2a", "2b"):
        return {
            "ordering_cost_gbp_before": baseline["order_quantity"]["ordering_cost_gbp"],
            "ordering_cost_gbp_after": changed["order_quantity"]["ordering_cost_gbp"],
        }
    if scenario in ("3a", "3b"):
        return {
            "annual_holding_rate_before": baseline["order_quantity"]["annual_holding_rate"],
            "annual_holding_rate_after": changed["order_quantity"]["annual_holding_rate"],
        }
    if scenario in ("4a", "4b"):
        return {
            "max_order_coverage_days_before": baseline["order_quantity"]["max_order_coverage_days"],
            "max_order_coverage_days_after": changed["order_quantity"]["max_order_coverage_days"],
        }
    if scenario == "5":
        return {
            "supplier_lead_time_days_before": baseline["supplier_lead_time_days"],
            "supplier_lead_time_days_after": changed["supplier_lead_time_days"],
        }
    return {}


# ---------------------------------------------------------------------------
# Reporting: money uses notebook 05's exact per-SKU-rounding convention.
# Every summary reports risk COUNTS, shortfall UNITS, and MONEY together.
# ---------------------------------------------------------------------------

def summarise(sim: pd.DataFrame, assumptions: dict) -> dict:
    methods = assumptions["methods"]
    holding_available = methods["order_quantity"] == "eoq"

    value = (sim["current_inventory"] * sim["unit_cost"]).round(2)
    is_stockout = sim["inventory_risk"] == "Stockout Risk"
    is_overstock = sim["inventory_risk"] == "Overstock Risk"
    shortfall_units = np.where(
        is_stockout, (sim["reorder_point"] - sim["current_inventory"]).clip(lower=0), 0
    )
    stockout_revenue_exposure = pd.Series(shortfall_units * sim["avg_unit_price"], index=sim.index).round(2)
    overstock_capital_exposure = (sim["excess_units"] * sim["unit_cost"]).round(2)
    annual_holding_cost = (
        round((value * assumptions["order_quantity"]["annual_holding_rate"]).round(2).sum(), 2)
        if holding_available else None
    )

    return {
        "sku_count": int(len(sim)),
        "stockout_skus": int(is_stockout.sum()),
        "overstock_skus": int(is_overstock.sum()),
        "normal_skus": int((sim["inventory_risk"] == "Normal").sum()),
        "stockout_shortfall_units": int(shortfall_units.sum()),
        "recommended_replenishment_qty_total": float(sim["recommended_replenishment_qty"].sum()),
        "total_inventory_value_gbp": round(value.sum(), 2),
        "annual_holding_cost_gbp": annual_holding_cost,
        "stockout_revenue_exposure_gbp": round(stockout_revenue_exposure.sum(), 2),
        "overstock_capital_exposure_gbp": round(overstock_capital_exposure.sum(), 2),
        "eoq_capped_skus": int(sim["eoq_capped"].sum()) if "eoq_capped" in sim else None,
        "warehouse_strategy_distinct": int(sim["warehouse_strategy"].nunique()),
    }


def changed_field_counts(baseline: pd.DataFrame, other: pd.DataFrame, fields: list[str]) -> dict:
    b = baseline.set_index("stock_code")
    o = other.set_index("stock_code").reindex(b.index)
    out = {}
    for field in fields:
        if field not in b.columns:
            continue
        left, right = b[field], o[field]
        if field in EXACT_FIELDS:
            changed = ~(left.eq(right) | (left.isna() & right.isna()))
        elif pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            changed = ~np.isclose(left.astype(float), right.astype(float), rtol=FLOAT_RTOL, atol=FLOAT_ATOL, equal_nan=True)
        else:
            changed = left.astype(str) != right.astype(str)
        out[f"{field}_changed_skus"] = int(np.sum(changed))
    return out


def risk_transition_matrix(baseline: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    b = baseline.set_index("stock_code")["inventory_risk"]
    o = other.set_index("stock_code")["inventory_risk"].reindex(b.index)
    matrix = pd.DataFrame({"baseline_risk": b, "scenario_risk": o})
    return matrix.groupby(["baseline_risk", "scenario_risk"], observed=True).size().rename("sku_count").reset_index()


def warehouse_strategy_changed(baseline: pd.DataFrame, other: pd.DataFrame) -> int:
    b = baseline.set_index("stock_code")["warehouse_strategy"]
    o = other.set_index("stock_code")["warehouse_strategy"].reindex(b.index)
    return int((b.astype(str) != o.astype(str)).sum())


COMPARISON_FIELDS = [
    "current_inventory", "reorder_point", "safety_stock", "economic_order_qty",
    "max_stock_level", "recommended_replenishment_qty",
]


def selected_scenarios(value: str) -> list[str]:
    scenarios = list(ALL_SCENARIOS) if value == "all" else [s.strip() for s in value.split(",")]
    if not scenarios or any(s not in ALL_SCENARIOS for s in scenarios):
        raise ValueError("Unknown or empty scenario; choose " + ",".join(ALL_SCENARIOS))
    if len(scenarios) != len(set(scenarios)):
        raise ValueError("Duplicate scenario names are not allowed")
    return scenarios


def add_effective_threshold(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    return frame.assign(effective_overstock_threshold=np.maximum(
        frame["max_stock_level"], frame["avg_daily_demand"] * config["overstock"]["coverage_days"]
    ))


def run(args: argparse.Namespace) -> None:
    scenarios = selected_scenarios(args.scenarios)
    output_dir = _ensure_safe_output_dir(Path(args.output_dir))
    profile_path, config_path = Path(args.profile).resolve(), Path(args.config).resolve()
    metadata = collect_run_metadata(profile_path, config_path, args.seed)
    saved, baseline_assumptions = load_baseline(profile_path, config_path, args.seed)
    metadata.update(baseline_methods=baseline_assumptions["methods"],
                    baseline_config=baseline_assumptions, effective_seed=baseline_assumptions["seed"],
                    numeric_comparison={"rtol": FLOAT_RTOL, "atol": FLOAT_ATOL,
                                        "exact_fields": sorted(EXACT_FIELDS)},
                    monetary_rounding="Round per SKU to GBP cents, then sum and round total to cents")
    saved = add_effective_threshold(saved, baseline_assumptions)
    baseline_summary = summarise(saved, baseline_assumptions)
    rows = [{"scenario": "baseline", "mode": "regenerated_baseline", **baseline_summary}]
    transitions, field_rows, changes, configs = {}, [], {}, {}
    for scenario in scenarios:
        changed = (uncapped_variant(baseline_assumptions) if scenario in {"A", "B"}
                   else SCENARIO_BUILDERS[scenario](baseline_assumptions))
        validate_diagnostic_config(changed)
        mode = "fixed_inventory" if scenario == "A" else "full_regeneration"
        name = {"A": "A_fixed_inventory_uncapped", "B": "B_full_regeneration_uncapped"}.get(scenario, scenario)
        frame = (experiment_a_fixed_inventory(saved, changed) if scenario == "A"
                 else experiment_b_full_regeneration(saved, changed))
        # Same seed/SKU identity implies the same hashed draws. Scenario 5 changes
        # lead-time values, not the underlying hash/probability-bin draw.
        for field in ["stock_code", "sku_class", "policy_position", "unit_cost", "storage_volume_per_unit"]:
            pd.testing.assert_series_equal(saved[field], frame[field], check_exact=True)
        if scenario != "5":
            pd.testing.assert_series_equal(saved["supplier_lead_time_days"], frame["supplier_lead_time_days"], check_exact=True)
        if scenario in {"A", "B"}:
            for field in ["reorder_point", "safety_stock"] + (["current_inventory"] if scenario == "A" else []):
                pd.testing.assert_series_equal(saved[field], frame[field], check_exact=True)
        frame = add_effective_threshold(frame, changed)
        rows.append({"scenario": name, "mode": mode, **summarise(frame, changed)})
        transitions[name] = risk_transition_matrix(saved, frame)
        field_rows.append({"scenario": name,
                           "warehouse_strategy_changed_skus": warehouse_strategy_changed(saved, frame),
                           **changed_field_counts(saved, frame, COMPARISON_FIELDS + ["effective_overstock_threshold"])})
        changes[scenario] = ({"max_order_coverage_days_before": baseline_assumptions["order_quantity"].get("max_order_coverage_days"),
                              "max_order_coverage_days_after": None} if scenario in {"A", "B"}
                             else actual_parameter_change(scenario, baseline_assumptions, changed))
        configs[scenario] = {"policy_config": changed, "mode": mode,
                             "inventory_adapter": "fixed_range (reuse baseline inventory, do not draw again)" if scenario == "A" else None}
    results = pd.DataFrame(rows)
    for metric, baseline_value in baseline_summary.items():
        if baseline_value is not None:
            results[metric + "_delta"] = (results[metric] - baseline_value).round(8)
            results[metric + "_pct"] = (100 * results[metric + "_delta"] / baseline_value
                                         if baseline_value else np.nan)
    metadata.update(parameter_changes=changes, scenario_configs=configs, scenarios_run=scenarios,
                    assertions={"same_SKU_and_hash_draws": True,
                                "experiment_A_current_inventory_unchanged": True if "A" in scenarios else None})
    # Publish only after all scenarios and all output writes succeed. Never reuse
    # an existing destination: this also prevents stale reports and child symlinks.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".model-diagnostics-", dir=output_dir.parent) as work:
        stage = Path(work) / "report"
        stage.mkdir()
        results.to_csv(stage / "scenario_summary.csv", index=False)
        pd.DataFrame(field_rows).to_csv(stage / "field_change_counts.csv", index=False)
        (stage / "risk_transitions").mkdir()
        for name, frame in transitions.items():
            frame.to_csv(stage / "risk_transitions" / f"{name}.csv", index=False)
        if _sha256_file(profile_path) != metadata["inputs"]["profile_sha256"] or _sha256_file(config_path) != metadata["inputs"]["config_sha256"]:
            raise ValueError("Input changed during diagnostics; report was not published")
        metadata["status"] = "complete"
        (stage / "run_metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False))
        _ensure_safe_output_dir(Path(args.output_dir))
        os.rename(stage, output_dir)
    print(f"Completed diagnostics in {output_dir}")
    print(results[["scenario", *baseline_summary]].to_string(index=False))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Path to a raw SKU profile or complete saved simulation CSV. Read-only.")
    parser.add_argument("--config", required=True, help="Path to a simulation_assumptions.json to read as the baseline. Read-only.")
    parser.add_argument("--output-dir", required=True, help="New, nonexistent isolated directory outside the repository; existing destinations are rejected.")
    parser.add_argument("--scenarios", default="all", help="Comma-separated scenario names (A,B,1a,1b,2a,2b,3a,3b,4a,4b,5) or 'all'.")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed override, recorded in run_metadata.json. Defaults to the config's own seed.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            run(args)
    except (ValueError, TypeError, KeyError, IndexError, AssertionError, OSError, Warning, OverflowError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Diagnostics failed; no new report published: {exc}") from None


if __name__ == "__main__":
    main()
