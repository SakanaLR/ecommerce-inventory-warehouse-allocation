from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.attribute_model_changes import summarise  # noqa: E402


def sim_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "current_inventory": [50, 300],
        "unit_cost": [2.0, 1.0],
        "inventory_risk": ["Stockout Risk", "Overstock Risk"],
        "reorder_point": [80, 100],
        "sku_class": ["High-Revenue Priority", "Regular"],
        "avg_unit_price": [4.0, 2.0],
        "excess_units": [0.0, 50.0],
        "safety_stock": [10, 20],
        "recommended_replenishment_qty": [30, 0],
    })


def test_summarise_computes_holding_cost_when_rate_is_available():
    result = summarise(sim_frame(), holding_rate=0.25)
    # value = 50*2 + 300*1 = 400; holding cost = 400 * 0.25 = 100
    assert result["annual_holding_cost"] == 100.0


def test_summarise_leaves_holding_cost_unavailable_when_rate_is_none():
    # A legitimate top_up-only config has no annual_holding_rate configured;
    # this must be left blank (None), never defaulted to 0.
    result = summarise(sim_frame(), holding_rate=None)
    assert result["annual_holding_cost"] is None
    # Every other metric must still be computed normally.
    assert result["estimated_inventory_value"] == 400.0
    assert result["stockout_skus"] == 1
    assert result["overstock_skus"] == 1


def test_cli_accepts_minimal_historical_config(tmp_path, monkeypatch):
    import shutil
    from scripts import attribute_model_changes

    (tmp_path / 'config').mkdir()
    (tmp_path / 'outputs').mkdir()
    shutil.copyfile(
        PROJECT_ROOT / 'reports/baseline_end_phase3a/simulation_assumptions_phase3a.json',
        tmp_path / 'config/simulation_assumptions.json',
    )
    pd.DataFrame({
        'stock_code': ['A'], 'sku_class': ['Regular'], 'avg_unit_price': [4.0],
        'avg_monthly_units': [30.0], 'std_monthly_units': [15.0], 'demand_cv': [0.5],
    }).to_csv(tmp_path / 'outputs/sku_profile_classification.csv', index=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['attribute_model_changes', '--output', 'result.csv'])
    attribute_model_changes.main()
    result = pd.read_csv(tmp_path / 'result.csv')
    assert len(result) == 1
    assert result['annual_holding_cost'].isna().all()
    assert result['method_order_quantity'].tolist() == ['top_up']
