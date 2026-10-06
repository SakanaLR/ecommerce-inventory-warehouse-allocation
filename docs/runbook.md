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
- `overstock_capital_exposure`: for Overstock Risk SKUs, the units above 180 days of demand valued at simulated unit cost.

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

## Known Limitations

- Current inventory position scales with each SKU's own reorder point and EOQ, and safety stock uses a per-class service-level formula. A simpler fixed-range/volatility-factor model is still supported (see `config/simulation_assumptions.json`'s `methods` block and `PHASE_3A_METHODS` in `src/retail_analytics/simulation.py`) and used for before/after comparisons.
- Demand statistics cover the 12 full months only. A SKU's revenue rank takes priority over its `short_history` flag when assigning it to High-Revenue Priority, so treat that class's demand-volatility statistic as unreliable for the 27 SKUs (as of the current data) with under 3 months of history; see `docs/management_summary.md`'s Assumptions and Limitations section for detail.
- Partial returns are not netted against sales.
- Cancellations with no same-price sale are matched at a different price (93 cases); check `match_quality` in `reversed_sales.csv`.
- `annual_holding_cost` (in `outputs/working_capital_summary.csv` and related outputs) is only computed when `methods.order_quantity = "eoq"`; under the simpler `"top_up"` model it is left blank, not defaulted to 0.
