# Sales Data Analytics Pipeline Runbook

## Project Purpose

This project demonstrates a reusable sales-data analytics workflow for e-commerce inventory, SKU classification, warehouse allocation, and finance-facing working-capital analysis.

The portfolio version uses the public UCI Online Retail dataset. A different sales dataset can be used by mapping its column names into the standard schema before running the pipeline.

No confidential company data is required. Inventory and cost fields are simulated for demonstration.

## Workflow

```text
raw sales file
-> scripts/validate_input_data.py        (schema and data-quality precheck)
-> scripts/standardize_raw_sales.py      (rename columns, fix types)
-> notebooks/01_data_cleaning.ipynb      (cleaning rules from src/retail_analytics/cleaning.py)
-> notebooks/02_sql_business_queries.ipynb
-> notebooks/03_sku_classification.ipynb      (demand panel from src/retail_analytics/demand.py)
-> notebooks/04_replenishment_warehouse_allocation.ipynb  (simulation from src/retail_analytics/simulation.py)
-> notebooks/05_working_capital_impact.ipynb
```

Earlier notebook versions (the original UCI-input track and the `b` standardized-input track) are kept for reference in `archive/notebooks/`. They are no longer part of the workflow.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Raw Data Placement

Place the raw sales file in `data/raw/`. The current project expects `data/raw/Online Retail.xlsx`.

For a different dataset, keep the raw file in `data/raw/` and update `config/schema_mapping_template.csv` so that each standard field points to the matching source column.

## Expected Standard Schema

| Standard field | Required | Description |
| --- | --- | --- |
| `invoice_no` | Yes | Transaction or invoice identifier. Cancellations start with `C`. |
| `stock_code` | Yes | Product or SKU identifier. |
| `description` | No | Product description used as a display field. |
| `quantity` | Yes | Quantity on the transaction line. |
| `invoice_date` | Yes | Transaction timestamp. |
| `unit_price` | Yes | Unit selling price. |
| `customer_id` | No | Customer identifier when available. |
| `country` | No | Customer country or region when available. |

The validator always treats the five required fields as required, even if the mapping file marks one of them as optional.

## Step 1: Validate

```bash
python scripts/validate_input_data.py \
  --input "data/raw/Online Retail.xlsx" \
  --mapping "config/schema_mapping_template.csv" \
  --output "outputs/data_quality_precheck.csv"
```

Add `--sheet-name "Sales"` for a specific Excel sheet.

The script exits with code 1 when a schema check fails. Warnings are expected for this dataset:

- 10,624 lines with non-positive quantity (returns and cancellations)
- 2,517 lines with non-positive price
- 5,268 exact duplicate rows

Notebook 01 handles all three.

## Step 2: Standardize

```bash
python scripts/standardize_raw_sales.py \
  --input "data/raw/Online Retail.xlsx" \
  --mapping "config/schema_mapping_template.csv" \
  --output "data/interim/standardized_sales.csv"
```

The script:

- renames the mapped columns;
- keeps `invoice_no`, `stock_code`, and `customer_id` as strings so leading zeros survive;
- converts `quantity`, `unit_price`, and `invoice_date`;
- reports how many values failed to parse.

## Step 3: Run the Notebooks

Run the notebooks in order, either interactively or from the command line:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/0*.ipynb
```

Each notebook checks that its inputs exist and names the notebook to run first if they are missing.

## Cleaning Rules (Notebook 01)

The rules are implemented in `src/retail_analytics/cleaning.py` and covered by `tests/test_cleaning.py`.

1. Trim and upper-case `stock_code`. The source contains 112 codes that differ from another code only by case.
2. Remove exact duplicate rows.
3. Save cancellation invoices and negative-quantity lines to `returns_cancellations.csv`.
4. Keep sales lines with positive quantity and price and a usable stock code, description, and date. Missing customer IDs are kept.
5. Exclude the non-product lines listed in `config/non_product_stock_codes.csv`, and save them to `non_product_lines.csv` with their category.
6. Remove the sale lines listed in `config/manual_reversals.csv`. These are keying errors that were reversed with a manual credit (stock code `M`) rather than a cancellation of the same stock code.
7. Remove fully reversed sales:
   - **Candidates.** A cancellation line can reverse a sale with the same customer, the same stock code, and the same quantity, dated on or before the cancellation.
   - **Order.** Cancellations are processed in time order.
   - **Choice.** Each cancellation takes an unused candidate at the same unit price if there is one (the most recent of those), and otherwise the most recent unused candidate.
   - **Limits.** Each sale line can be removed by only one cancellation. Lines without a customer ID are never matched. Partial returns are not netted.
8. Save every removed line from steps 6–7 to `reversed_sales.csv`, with these columns:
   - `reversal_type`: `manual_credit` or `full_cancellation`;
   - `cancel_invoice_no`, `cancel_date`, `days_to_cancel`;
   - `cancel_unit_price` and `price_delta` (cancellation price minus sale price);
   - `match_quality`: `same_price`, `price_mismatch`, or `reviewed_manual_credit`.
9. Build `sku_master.csv` (display description = most frequent description) and `monthly_sku_sales.csv`.
10. Write `month_coverage.csv`. `is_truncated_month` is true only for the first or last month when the data starts after the first day or ends before the last day of that month. Here that is December 2011, which ends on the 9th. Gaps inside a month are not detected.
11. Write two review lists; nothing on them is removed:
    - `manual_credit_candidates.csv`: manual credits whose value equals a same-customer sale line from the previous day. `reviewed_in_config` shows whether the credit is already in `config/manual_reversals.csv`.
    - `price_anomalies.csv`: lines priced at least 10 times the median price of SKUs with 3 or more lines.

### Maintaining the rule files

**`config/non_product_stock_codes.csv`** has these columns:

| Column | Meaning |
| --- | --- |
| `stock_code` | The code to match. |
| `match_type` | `exact` or `prefix`. |
| `category` | `shipping`, `fee`, `adjustment`, or `non_merchandise`. |
| `reason` | Why the code is excluded. |

The loader rejects:
- blank values (a blank prefix would match every code);
- duplicate rules;
- a rule already covered by a prefix rule.

To extend the list for a new dataset, look for non-standard codes and descriptions containing words such as POSTAGE, CARRIAGE, CHARGE, FEE, DISCOUNT, ADJUST, SAMPLE, or VOUCHER. Notebook 02 reads the same file to confirm that no matching code remains in the clean data.

**`config/manual_reversals.csv`** has these columns:

| Column | Meaning |
| --- | --- |
| `invoice_no`, `stock_code`, `quantity`, `unit_price` | Identify the sale line to remove. |
| `credit_invoice_no` | The manual credit that reversed it. |
| `reason` | Why the reversal was accepted. |

To add an entry:
1. Review `manual_credit_candidates.csv`.
2. Confirm the story from the customer's invoices, for example an error followed by a corrected invoice.
3. Add the row.

Cleaning stops with an error if a listed sale does not match exactly one line, or if its credit invoice has no same-customer credit of equal value. This keeps the list in sync with the data. The file is dataset-specific; for a new dataset, start with only the header row.

## Demand Basis and Classification (Notebook 03)

The logic is in `src/retail_analytics/demand.py` and is covered by `tests/test_demand.py`.

1. Take the months where `month_coverage.csv` has `is_truncated_month = False`. For this dataset that is December 2010 to November 2011, 12 months.
2. Build `data/processed/sku_month_demand.csv`: one row per SKU and month, from the SKU's first sale month to the last full month. Months without sales are filled with zero (`is_zero_filled`).
3. Build the SKU profile:
   - `total_units`, `total_revenue`, `total_orders`, `active_months`: all months, including December 2011, so they reconcile to clean sales.
   - `avg_monthly_units`, `std_monthly_units` (sample standard deviation; 0 when there is only one month), `demand_cv`: from the panel.
   - `avg_monthly_units_active`: the old basis (months with sales only), kept for comparison.
   - `months_in_window`, `zero_months_in_window`, `zero_month_share`.
   - `short_history`: fewer than 3 months in the window.
   - `no_full_month_sales`: the SKU sold only in truncated months. Its demand statistics are 0.
4. Classify each SKU; the first matching rule wins:
   1. **High-Revenue Priority:** total revenue at or above the 80th percentile.
   2. **High-Turnover Volatile:** total units at or above the 80th percentile, and demand CV above 1.0 or `short_history`.
   3. **High-Turnover Stable:** other SKUs at or above the 80th percentile of units.
   4. **Long-Tail:** total units at or below the 30th percentile.
   5. **Regular:** everything else.

The volatility cut-off is set by `VOLATILITY_CV` in notebook 03.

Notebook 03 prints a reconciliation of units: panel plus truncated months must equal the total.

**What `demand_cv` actually measures.** It is `sample_std(X, ddof=1) / mean(X)` over the zero-filled monthly panel `X` (first sale month through the last full month) — this is the *relative volatility of monthly sales including zero-sale months*, not a measure of single-order size, and not simply an "intermittency" indicator on its own. For a window of length `n` with zero-month share `z` and non-zero-month population CV `CV₊`, `CV_sample² = n/(n−1) × (CV₊² + z)/(1 − z)`: the observed CV is a mix of positive-month sales-volume variation, how often the SKU has any sales at all in its window, and a small-sample correction. Across the current dataset, `demand_cv` correlates with `zero_month_share` at Pearson r ≈ 0.84 (3,789 of 3,790 SKUs have both values defined) — but that correlation describes this dataset's current mix, not which term dominates for a given SKU, and it does not establish that CV "actually measures intermittency" as a general claim. See [`docs/model_assumptions_review.md`](model_assumptions_review.md) §3 for the full derivation and worked examples.

**`months_in_window == 3` is not the same as `short_history`.** The flag is strictly "fewer than 3 months" (`< 3`), so a SKU with exactly 3 months of observed history is *not* flagged `short_history`, even though 3 months is still a short observation window in a statistical sense. A SKU with only 3 months of data can still be classified High-Revenue Priority or Regular with a low `demand_cv` — that low CV is estimated from limited observations, not a verified stable demand pattern; the resulting `inventory_risk` label (e.g. "Normal") describes what the simulated policy computes under current assumptions, not a confirmed real-world outcome. See [`docs/model_assumptions_review.md`](model_assumptions_review.md) §4 for concrete examples and the corrected SKU-class table (an earlier internal diagnosis draft had mis-stated two of the example SKUs' classes; the review corrects this).

## Simulated Inventory Layer (Notebooks 04–05)

The logic is in `src/retail_analytics/simulation.py` and is covered by `tests/test_simulation.py`. `config/simulation_assumptions.json`'s `methods` block selects the model per field; the current configuration is `inventory=policy_band`, `safety_stock=service_level`, `order_quantity=eoq`, `overstock=max_stock`. A simpler model (`fixed_range`/`volatility_factor`/`top_up`/`coverage_only`, matching `PHASE_3A_METHODS` in `simulation.py`) is also supported and used for before/after comparison — a config using it does not need an `order_quantity` section at all, since that section is only read on the `eoq` path.

| Setting | Meaning |
| --- | --- |
| `seed` | Base seed for all draws. |
| `methods` | Per-field model choice: `inventory` (`fixed_range` or `policy_band`), `safety_stock` (`volatility_factor` or `service_level`), `order_quantity` (`top_up` or `eoq`), `overstock` (`coverage_only` or `max_stock`). `policy_band` and `max_stock` each require `order_quantity=eoq`; this is enforced at load time. |
| `current_inventory` | Used when `methods.inventory=fixed_range`: integer ranges for priority classes (High-Revenue Priority, High-Turnover Stable) and for all other classes. |
| `policy_band` | Used when `methods.inventory=policy_band`: current inventory = reorder point + p × EOQ, with p drawn per SKU from a class-dependent range (`position_by_class`). |
| `supplier_lead_time_days` | Values and probabilities. The probabilities must sum to 1. |
| `storage_volume_per_unit`, `unit_cost_ratio` | Uniform ranges. |
| `safety_stock` | `volatility_factor`: lead-time demand × (`base_factor` + `cv_factor` × min(CV, `cv_cap`)). `service_level`: z(service level) × monthly demand std × √(lead time ÷ days per month), with a per-class service level (`service_level_by_class`). |
| `order_quantity` | Used only when `methods.order_quantity=eoq`: EOQ = √(2 × annual demand × ordering cost ÷ (unit cost × annual holding rate)), capped at `max_order_coverage_days` of demand. `annual_holding_rate` is also used by notebook 05 to compute `annual_holding_cost`, which is only available under this method — left blank, not defaulted to 0, under `top_up`. |
| `overstock` | `coverage_only`: coverage-day limit, for the listed classes only. `max_stock`: inventory above max(reorder point + EOQ, coverage-day limit), for all classes. |

**How draws are made.** Each draw is `SHA-256(seed | field | stock_code)`, mapped to [0, 1). A SKU keeps its values when other SKUs are added, removed, or re-ordered. Changing the seed re-draws every SKU.

**How the notebooks share it.** Notebook 04 saves the full layer to `outputs/sku_inventory_simulation.csv`. Notebook 05 reads that file and asserts that a fresh simulation reproduces it.

`scripts/check_simulation_stability.py` compares the legacy row-position method with the hashed method on the real SKU list, and writes `reports/phase3a_simulation_stability.csv`. `scripts/attribute_model_changes.py` isolates the effect of each Phase 3A → Phase 3B-1 method change one at a time and writes `reports/phase3b1_attribution.csv`; read it end to end, since an intermediate step can temporarily look worse than either endpoint (see `docs/management_summary.md`).

**Parameter calibration status.** `ordering_cost_gbp`, `annual_holding_rate`, `max_order_coverage_days`, `overstock.coverage_days`, `supplier_lead_time_days`, and `safety_stock.service_level_by_class` are demonstration assumptions for this portfolio project, not values calibrated against real purchasing, warehousing, or supplier data — this dataset has no such data to calibrate against. `ordering_cost_gbp=25` is applied by the code as a fixed cost per SKU per replenishment event (see `economic_order_quantity()` in `simulation.py`); the model does not represent multi-SKU purchase orders or any cost-sharing across a supplier consolidation, so £25 should not be read as "per purchase order." Source status: demonstration / pending calibration. Owner and calibration date: not yet assigned. A meaningfully high fraction of SKUs currently hit the `max_order_coverage_days` cap and a majority of current "Overstock Risk" flags are sensitive to it — see [`docs/model_assumptions_review.md`](model_assumptions_review.md) §5–6 and [`docs/model_assumptions_plan.md`](model_assumptions_plan.md) §7 for the analysis and what real business input would be needed before treating any of these parameters as calibrated. `scripts/model_assumptions_diagnostics.py` (see Tests and Comparisons below) reproduces the fixed-inventory/full-regeneration comparison and the single-factor sensitivity scenarios from that review on demand, against a compatible policy_band/service_level/eoq/max_stock config copy, without touching the live config or outputs.

## Generated Outputs

Processed data (`data/processed/`):

- `clean_sales.csv` (about 70 MB; not committed, regenerate it locally)
- `returns_cancellations.csv`
- `non_product_lines.csv`
- `reversed_sales.csv`
- `sku_master.csv`
- `sku_description_check.csv`
- `monthly_sku_sales.csv`
- `sku_month_demand.csv`
- `month_coverage.csv`
- `manual_credit_candidates.csv`
- `price_anomalies.csv`
- `data_quality_summary.csv`

Business outputs (`outputs/`):

- `data_quality_precheck.csv`
- `top_sku_revenue_contribution.csv`
- `top_sku_unit_contribution.csv`
- `long_tail_skus.csv`
- `country_demand_summary.csv`
- `monthly_sales_trend.csv`
- `sku_profile_classification.csv`
- `sku_classification_summary.csv`
- `sku_inventory_simulation.csv`
- `replenishment_recommendations.csv`
- `overstock_risk_list.csv`
- `warehouse_allocation_summary.csv`
- `management_kpi_summary.csv`
- `working_capital_summary.csv`
- `top_overstock_capital_exposure.csv`
- `top_stockout_revenue_exposure.csv`
- `inventory_value_by_sku_class.csv`
- `inventory_value_by_warehouse_strategy.csv`

## Metric Definitions

- `warehouse_strategy_count`: the number of unique warehouse strategies (currently 6).
- `warehouse_allocation_segment_count`: the number of SKU class × strategy rows in `warehouse_allocation_summary.csv` (currently 7).
- `stockout_revenue_exposure`: for Stockout Risk SKUs, the shortfall to the reorder point valued at average selling price. It is an upper-bound indicator, not a lost-revenue forecast.
- `overstock_capital_exposure`: for Overstock Risk SKUs, `current_inventory` above the *effective* overstock threshold, valued at simulated unit cost. The threshold depends on `methods.overstock`: under `max_stock` (the live method) it is `max(reorder point + EOQ, daily demand × overstock.coverage_days)` — **not simply `daily demand × coverage_days`** — so a SKU's own reorder point and order quantity can raise its threshold above the flat coverage-day line; under the legacy `coverage_only` method the threshold is exactly `daily demand × coverage_days`. See the `overstock` row in the Simulated Inventory Layer table above, and [`docs/model_assumptions_review.md`](model_assumptions_review.md) §9 for the correction history of this definition.

All monetary values are in GBP.

## Simulated Fields

These fields are simulated:

- `current_inventory`
- `supplier_lead_time_days`
- `storage_volume_per_unit`
- `unit_cost`

These fields are derived from the simulated layer and historical demand:

- `safety_stock`
- `reorder_point`
- `recommended_replenishment_qty`
- `inventory_coverage_days`
- `inventory_risk`
- `warehouse_strategy`
- `estimated_inventory_value`
- `stockout_revenue_exposure`
- `overstock_capital_exposure`

The four simulated fields are drawn per SKU (see "Simulated Inventory Layer"). A change to the SKU list does not re-draw the values of other SKUs.

## Tests and Comparisons

```bash
python -m pytest -W error
python scripts/compare_to_baseline.py --baseline reports/baseline_before_phase1 --current reports/baseline_end_phase1 --prefix phase1
python scripts/compare_to_baseline.py --baseline reports/baseline_end_phase1 --current reports/baseline_end_phase3a --prefix phase3a
python scripts/check_simulation_stability.py
```

`compare_to_baseline.py` compares two versions of the outputs. Each report states its own basis:

| Prefix | Before | After | Report |
| --- | --- | --- | --- |
| `phase1` | Original pipeline (`reports/baseline_before_phase1/`) | End of Phase 1 (`reports/baseline_end_phase1/`) | `reports/phase1_data_correctness.md` |
| `phase3a` | End of Phase 1 (`reports/baseline_end_phase1/`) | End of Phase 3A (`reports/baseline_end_phase3a/`) | `reports/phase3a_demand_and_simulation.md` |
| `phase3b1` | End of Phase 3A (`reports/baseline_end_phase3a/`) | Current outputs (`live`) | `reports/phase3b1_before_after.csv`, `reports/phase3b1_attribution.csv` (step-by-step effect of each model change; no written report yet) |

The `phase3a` command compares two frozen snapshots; `phase3b1` compares the Phase 3A snapshot with `live`. The prefix names output files only and does not select either comparison source.

A snapshot directory holds `baseline_metrics.csv`, `outputs/`, and `data_processed/`. Revisions made within Phase 1 are not snapshots; `reports/phase1_data_correctness.md` describes them separately.

`scripts/verify_pipeline.sh` runs the full chain in the project `.venv`: validation, standardization, notebooks 01–05, both comparisons, the stability check, and the tests. Run it from the project root with `mkdir -p tmp && bash scripts/verify_pipeline.sh > tmp/verify_pipeline.log 2>&1`.

`scripts/model_assumptions_diagnostics.py` reproduces the model-assumptions experiments from [`docs/model_assumptions_review.md`](model_assumptions_review.md) on demand: the fixed-inventory experiment (`A`), the full-regeneration experiment (`B`), and the nine single-factor sensitivity scenarios (`1a`/`1b`/`2a`/`2b`/`3a`/`3b`/`4a`/`4b`/`5`). It takes an explicit `--profile`, `--config`, and `--output-dir`, refuses to write into any official `config/`/`outputs/`/`data/`/`notebooks/`/`reports/` path, and reports risk counts, shortfall units, and monetary exposure together (never counts alone) alongside a full metadata record (code commit, working-tree dirty status, input file hashes, dependency versions, seed, and the actual — not nominal — parameter values applied). It does not search for or write back a "best" parameter set; it only reports what each named scenario produces. Example:

```bash
python scripts/model_assumptions_diagnostics.py \
  --profile outputs/sku_inventory_simulation.csv \
  --config config/simulation_assumptions.json \
  --output-dir /tmp/model_assumptions_diag \
  --scenarios all
```

The destination must be a **new, nonexistent directory outside the repository**. Relative paths and symlink aliases are resolved; existing directories (including old reports) are rejected. No report is published unless all scenarios, validation and output writes succeed. Invalid/duplicate scenario names, incomplete saved simulations, duplicate SKU keys and nonfinite demand inputs fail explicitly. A raw SKU profile or a complete saved simulation is accepted; the latter is checked against its original config before any `--seed` override regenerates a common baseline. A/B and each sensitivity case independently derive from that baseline. The CLI currently supports the four live methods only, not legacy top_up configurations.

Metadata records the effective config, actual per-scenario parameters, input/source hashes, HEAD, staged and unstaged diff hashes, untracked content hashes and dependency versions. Discrete/rounded simulated fields compare exactly; unrounded floating intermediates use rtol=1e-12 and atol=1e-9 (CSV round-trip precision, substantially below one inventory unit or penny). Monetary comparisons use per-SKU pennies then aggregate pennies. Summary CSV includes baseline-relative absolute and percentage changes (zero denominators have unavailable percentages), field changes include the effective overstock threshold, and risk transition CSVs expose movement between categories. Repeating a run compares business results, not environment metadata. Named scenarios 2a–4b use the documented absolute values (e.g. £12.5/£50), so for a different baseline their percentage changes must be read from the recorded before/after values.

## Known Limitations

- Current inventory position scales with each SKU's own reorder point and EOQ, and safety stock uses a per-class service-level formula. A simpler fixed-range/volatility-factor model is still supported (see `config/simulation_assumptions.json`'s `methods` block and `PHASE_3A_METHODS` in `src/retail_analytics/simulation.py`) and used for before/after comparisons.
- Demand statistics cover the 12 full months only. A SKU's revenue rank takes priority over its `short_history` flag when assigning it to High-Revenue Priority, so treat that class's demand-volatility statistic as unreliable for the 27 SKUs (as of the current data) with under 3 months of history; see `docs/management_summary.md`'s Assumptions and Limitations section for detail.
- Partial returns are not netted against sales.
- Cancellations with no same-price sale are matched at a different price (93 cases); check `match_quality` in `reversed_sales.csv`.
- `annual_holding_cost` (in `outputs/working_capital_summary.csv` and related outputs) is only computed when `methods.order_quantity = "eoq"`; under the simpler `"top_up"` model it is left blank, not defaulted to 0.
