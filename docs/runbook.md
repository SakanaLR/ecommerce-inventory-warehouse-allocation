# Sales Data Analytics Pipeline Runbook

## Project Purpose

This project demonstrates a reusable sales-data analytics workflow for e-commerce inventory, SKU classification, warehouse allocation, and finance-facing working capital analysis.

The current portfolio version uses the public UCI Online Retail dataset. The long-term goal is to make the workflow adaptable to future sales datasets by mapping company-specific column names into a standard schema before running the notebooks.

No confidential company data is required for this project. Inventory and cost fields used for replenishment, warehouse allocation, and working capital analysis are simulated for portfolio demonstration.

## Raw Data Placement

Place the raw sales file under:

```text
data/raw/
```

The current project expects the UCI file at:

```text
data/raw/Online Retail.xlsx
```

For a different dataset, keep the raw file in `data/raw/` and update `config/schema_mapping_template.csv` so each standard field points to the correct source column name.

## Expected Standard Schema

The workflow expects sales data to be mapped into these standard fields:

| Standard field | Required | Description |
| --- | --- | --- |
| `invoice_no` | Yes | Transaction or invoice identifier. |
| `stock_code` | Yes | Product or SKU identifier. |
| `description` | No | Product description used as a display field. |
| `quantity` | Yes | Quantity sold on the transaction line. |
| `invoice_date` | Yes | Transaction or invoice timestamp. |
| `unit_price` | Yes | Unit selling price. |
| `customer_id` | No | Customer identifier when available. |
| `country` | No | Customer country or region when available. |

The current mapping template uses the UCI Online Retail source fields:

```text
InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country
```

## Notebook Execution Order

Run the notebooks in order:

```text
notebooks/01_data_cleaning.ipynb
notebooks/02_sql_business_queries.ipynb
notebooks/03_sku_classification.ipynb
notebooks/04_replenishment_warehouse_allocation.ipynb
notebooks/05_working_capital_impact.ipynb
```

Notebook 05 extends the project into working capital analysis. It loads `outputs/sku_profile_classification.csv` and uses simulated inventory and cost fields. If those fields are not already present in the source file, it recreates the simulated inventory layer deterministically for reproducibility.

## Generated Outputs

Core processed data outputs:

- `data/processed/clean_sales.csv`
- `data/processed/returns_cancellations.csv`
- `data/processed/non_product_lines.csv`
- `data/processed/sku_master.csv`
- `data/processed/sku_description_check.csv`
- `data/processed/monthly_sku_sales.csv`
- `data/processed/data_quality_summary.csv`

Business analysis outputs:

- `outputs/top_sku_revenue_contribution.csv`
- `outputs/top_sku_unit_contribution.csv`
- `outputs/long_tail_skus.csv`
- `outputs/country_demand_summary.csv`
- `outputs/monthly_sales_trend.csv`
- `outputs/sku_profile_classification.csv`
- `outputs/sku_classification_summary.csv`
- `outputs/replenishment_recommendations.csv`
- `outputs/overstock_risk_list.csv`
- `outputs/warehouse_allocation_summary.csv`
- `outputs/management_kpi_summary.csv`

Working capital outputs:

- `outputs/working_capital_summary.csv`
- `outputs/top_overstock_capital_exposure.csv`
- `outputs/top_stockout_revenue_exposure.csv`
- `outputs/inventory_value_by_sku_class.csv`
- `outputs/inventory_value_by_warehouse_strategy.csv`

Pre-run validation output:

- `outputs/data_quality_precheck.csv`

## Adapting a Different Sales Dataset

To adapt a different sales dataset:

1. Place the raw file in `data/raw/`.
2. Open `config/schema_mapping_template.csv`.
3. Update the `source_field` column so each standard field points to the matching column in the new dataset.
4. Keep the required fields mapped: `invoice_no`, `stock_code`, `quantity`, `invoice_date`, and `unit_price`.
5. Run the validation script before executing the notebooks.
6. Review `outputs/data_quality_precheck.csv` for missing fields, missing values, date parsing issues, invalid quantities, invalid prices, and duplicate rows.
7. If the precheck looks acceptable, run the notebooks in order.

The notebooks may still need small path or column-loading adjustments if a future dataset has a different file format, sheet structure, or business meaning. The schema mapping template is the first step toward standardization.

The current schema mapping layer supports validation and adaptation planning. The existing notebooks do not yet automatically consume `config/schema_mapping_template.csv`, so any future source-column changes should be reviewed before running the full notebook workflow.

## Simulated Fields

The public dataset does not include real inventory or cost data. The following fields are simulated in the inventory and working capital workflow:

- `current_inventory`
- `lead_time_days`
- `storage_volume_per_unit`
- `unit_cost`

The following decision-support fields are derived from the simulated layer and historical demand:

- `safety_stock`
- `reorder_point`
- `recommended_replenishment_qty`
- `inventory_coverage_days`
- `inventory_risk`
- `warehouse_strategy`
- `estimated_inventory_value`
- `stockout_revenue_exposure`
- `overstock_capital_exposure`

These outputs are illustrative portfolio examples. They should not be interpreted as real company inventory recommendations, accounting values, or operational decisions.

## Common Data Issues

Check for these issues before running the full workflow:

- Missing required columns.
- Missing values in required fields.
- Duplicate transaction rows.
- Cancelled invoices or returns.
- Negative or zero quantities.
- Negative or zero unit prices.
- Product codes used for non-product lines such as postage, fees, discounts, or manual adjustments.
- Missing or inconsistent product descriptions.
- Invoice dates that cannot be parsed as dates.
- Mixed date formats or unexpected currency handling.

## Validate Before Running the Workflow

Run the validation script from the project root:

```bash
python scripts/validate_input_data.py --input "data/raw/Online Retail.xlsx"
```

Optional arguments:

```bash
python scripts/validate_input_data.py \
  --input "data/raw/company_sales.csv" \
  --mapping "config/schema_mapping_template.csv" \
  --output "outputs/data_quality_precheck.csv"
```

For Excel files with a specific sheet:

```bash
python scripts/validate_input_data.py \
  --input "data/raw/company_sales.xlsx" \
  --sheet-name "Sales"
```

The script writes a summary report to:

```text
outputs/data_quality_precheck.csv
```

Use the precheck as an early warning step. It does not replace detailed data cleaning in notebook 01, but it helps identify schema and quality issues before running the full workflow.

Expected warnings should be interpreted in context. Non-positive quantity records may represent returns or cancellations, non-positive unit prices may represent invalid or non-sales records, and duplicate rows may be removed during cleaning. These issues are warnings rather than automatic failures because notebook 01 handles them downstream.

## Standardize Raw Sales Data

For future reusable pipeline work, the recommended preparation flow is:

```text
raw sales file
-> scripts/validate_input_data.py
-> scripts/standardize_raw_sales.py
-> downstream cleaning and analysis
```

The standardization script reads the raw sales file and `config/schema_mapping_template.csv`, renames mapped source columns into the standard schema, preserves identifier fields as strings, converts `quantity` and `unit_price` to numeric values where possible, converts `invoice_date` to datetime where possible, and writes:

```text
data/interim/standardized_sales.csv
```

The identifier fields `invoice_no`, `stock_code`, and `customer_id` are kept as strings to avoid losing leading zeros or treating IDs as numeric measures. Because the standardized output is saved as CSV, `invoice_date` is written as a text representation and should be parsed back to datetime in downstream code when date operations are needed.

Run from the project root:

```bash
python scripts/standardize_raw_sales.py --input "data/raw/Online Retail.xlsx"
```

Optional arguments:

```bash
python scripts/standardize_raw_sales.py \
  --input "data/raw/company_sales.csv" \
  --mapping "config/schema_mapping_template.csv" \
  --output "data/interim/standardized_sales.csv"
```

For Excel files with a specific sheet:

```bash
python scripts/standardize_raw_sales.py \
  --input "data/raw/company_sales.xlsx" \
  --sheet-name "Sales"
```

This standardization layer prepares a normalized dataset for future pipeline refactoring. Notebook 01 does not yet automatically consume `data/interim/standardized_sales.csv`.

### Optional Standardized-Input Cleaning

`notebooks/01_data_cleaning.ipynb` remains the original UCI-input cleaning notebook and the current production/portfolio workflow. As an optional path, `notebooks/01b_data_cleaning_standardized_input.ipynb` consumes `data/interim/standardized_sales.csv` and writes only to `data/processed_standardized/`, so it does not overwrite the original outputs under `data/processed/`. Notebook 01b is a preparation layer for future reusable pipeline refactoring, not yet a replacement for the original workflow.
