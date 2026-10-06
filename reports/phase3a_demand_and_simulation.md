# Phase 3A: Demand Basis and Stable Simulation

**Comparison basis.** Every *Before* figure in this note is the **end of Phase 1** (snapshot in `reports/baseline_end_phase1/`). Nothing here is compared with the original pre-Phase 1 baseline; see `reports/phase1_data_correctness.md` for that comparison.

The figures come from these files:
- `reports/phase3a_before_after.csv` (`scripts/compare_to_baseline.py --baseline reports/baseline_end_phase1 --current live --prefix phase3a`);
- `reports/phase3a_attribution.csv`;
- `reports/phase3a_simulation_stability.csv` (`scripts/check_simulation_stability.py`).

Cleaning was not touched in this phase: revenue is still £9,818,872.18 and the top-20 revenue list is unchanged.

## Problem 1: demand statistics ignored months without sales

**Before.** Average monthly units, their standard deviation, and CV were computed only over the months in which a SKU sold. The average also included December 2011, which covers only 9 days.

**Effect.**
- For 827 SKUs, the active-month average is at least twice the zero-filled average; for 1,420 SKUs it is at least 25% higher.
- Median demand CV was 0.77 on active months and is 1.01 once zero months count.
- Intermittent sellers therefore looked steadier and larger than they are, which fed straight into reorder points and the stable/volatile split.

**Fix.** `src/retail_analytics/demand.py` builds a SKU × month panel, saved as `data/processed/sku_month_demand.csv` (39,708 rows):
- **Window:** full months only, December 2010 to November 2011 (12 months). The truncated December 2011 is excluded.
- **Zero-fill:** each SKU starts at its first sale month, and months without sales count as zero (8,778 zero-filled rows).
- **Profile fields:**
  - `avg_monthly_units`, `std_monthly_units`, and `demand_cv` now come from this panel;
  - `avg_monthly_units_active` keeps the old average for comparison;
  - new fields: `months_in_window`, `zero_months_in_window`, and `zero_month_share`;
  - `short_history` flags SKUs with fewer than 3 months in the window (160 SKUs);
  - `no_full_month_sales` marks the one SKU that sold only in December 2011 (`90214U`).
- **Reconciliation:** panel units (5,106,054) plus December 2011 units (231,104) equal clean-sales units (5,337,158). All 3,790 SKUs keep a profile.

**Classification change.** The volatility rule is now a fixed cut-off: a high-turnover SKU is volatile when its CV is above 1.0 or its history is short. It used to be the 75th percentile of CV, which moves with the SKU mix. Revenue, volume, and long-tail thresholds are unchanged.

| SKU class | End of Phase 1 | Phase 3A | Change |
| --- | ---: | ---: | ---: |
| High-Revenue Priority | 758 | 758 | 0 |
| High-Turnover Stable | 201 | 182 | -19 |
| High-Turnover Volatile | 67 | 86 | +19 |
| Long-Tail | 1,133 | 1,133 | 0 |
| Regular | 1,631 | 1,631 | 0 |

Among high-turnover SKUs, 21 moved from Stable to Volatile and 2 moved the other way. None of them has a short history.

## Problem 2: simulated values depended on row position

**Before.** Notebook 04 drew all simulated values from one NumPy seed in row order. Notebook 05 repeated the same simulation.

**Effect.** Adding, removing, or re-ordering any SKU re-drew the values of every SKU after it. On the real SKU list:

| Method | Scenario | Other SKUs with changed simulated fields | Other SKUs with changed risk flag |
| --- | --- | ---: | ---: |
| Legacy row-position draws | Remove first SKU | 100% | 32.8% |
| Legacy row-position draws | Remove middle SKU | 100% | 31.1% |
| Legacy row-position draws | Shuffle row order | 100% | 31.7% |
| Per-SKU hashed draws | Any of the three | **0%** | **0%** |

**Fix.** `src/retail_analytics/simulation.py` derives each draw from SHA-256(`seed | field | stock_code`):
- The distributions are unchanged and now live in `config/simulation_assumptions.json`.
- Notebook 04 writes the full simulated layer to `outputs/sku_inventory_simulation.csv`.
- Notebook 05 reads that file instead of simulating again, and checks that a fresh run reproduces it exactly.

## Effect on simulated outputs, and what caused it

The two fixes change the simulated outputs for different reasons, so each combination was run separately:

| Demand basis | Draw method | Stockout | Overstock | Normal | Inventory value | Stockout exposure | Overstock exposure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Active months (end of Phase 1) | Legacy | 1,439 | 842 | 1,509 | 663,706.48 | 549,965.11 | 110,907.87 |
| Active months | Hashed | 1,383 | 855 | 1,552 | 638,683.04 | 546,950.76 | 104,660.78 |
| Zero-filled | Legacy | 1,371 | 1,070 | 1,349 | 663,432.29 | 568,636.63 | 139,328.92 |
| **Zero-filled (Phase 3A)** | **Hashed** | **1,326** | **1,086** | **1,378** | **637,918.62** | **563,830.24** | **135,218.48** |

Reading the table:
- **Overstock Risk rises by about 230 SKUs because of the demand basis.** Lower zero-filled demand means longer inventory coverage, so more Long-Tail and Regular SKUs pass 180 days. Overstock capital exposure rises for the same reason.
- **Estimated inventory value falls by about £25k because of the draw method.** This is not a systematic change: the distributions are identical, and the new draws are simply a different sample. Future phases will not see this kind of shift when the SKU list changes.
- **Warehouse strategies:** External or Limited Stock falls from 364 to 177 SKUs, because more Long-Tail SKUs now fall under Overstock Review (956). Standard Replenishment Review falls from 1,558 to 1,501.

## Acceptance checks

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Zero-filled mean and standard deviation are correct, the window starts at the first sale month, and truncated months are excluded | `tests/test_demand.py` (6 tests) |
| 2 | Units reconcile (panel + truncated = 5,337,158); all 3,790 SKUs kept; the December-only SKU is flagged | Printed in notebook 03 |
| 3 | Removing a SKU or shuffling rows changes no other SKU's simulated fields | 0% on real data; `tests/test_simulation.py` |
| 4 | Identical reruns; a new seed changes the draws; lead-time shares within ±2 pt of the configured probabilities | `tests/test_simulation.py`; the share table in notebook 04 |
| 5 | Notebook 05 uses exactly the values saved by notebook 04 | Assertion in notebook 05 |
| 6 | 01–05 run cleanly, `pytest -W error` passes, revenue is £9,818,872.18 | 43 tests pass (Python 3.11.16, pandas 3.0.3, numpy 2.4.6) |
| 7 | This report compares only with the end of Phase 1 and says so | This note |

## Still open (Phase 3B)

- Simulated stock does not scale with each SKU's demand: 466 of 758 High-Revenue Priority SKUs are flagged as stockout risks.
- Safety stock uses an ad hoc volatility factor rather than z·σ·√LT at a stated service level. There is no order-quantity (EOQ) logic.
- Long-Tail coverage is extreme: the average for the Overstock Review segment is about 3,060 days. Long-Tail stock is drawn from 0–119 units regardless of demand.
