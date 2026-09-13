# E-Commerce Inventory Forecasting & Warehouse Allocation Model

## Overview

This project analyzes public e-commerce transaction data and converts transaction-level sales records into SKU-level inventory and warehouse allocation decision support.

The project demonstrates how cleaned sales data can be used to identify high-priority SKUs, long-tail products, stockout risk, overstock risk, and practical warehouse strategies.

This is a portfolio project for business analytics, inventory planning, and data-driven operations decision support.

## Business Value

The project shows how an e-commerce operator can move from raw transaction records to practical inventory review outputs.

Instead of treating all products equally, the workflow separates core revenue-driving SKUs, stable high-turnover SKUs, volatile SKUs, long-tail SKUs, stockout-risk SKUs, and overstock-risk SKUs. This supports more targeted replenishment, warehouse space allocation, and management review.

## Business Questions

This project answers three practical management questions:

1. Which SKUs should receive replenishment priority?
2. Which SKUs may create stockout or overstock risk?
3. Which SKUs should be prioritized for local warehouse inventory versus external or limited-stock strategies?

## Data Source

The project uses the public UCI Online Retail dataset as the transaction-level sales data source.

Dataset link: https://archive.ics.uci.edu/dataset/352/online+retail

The dataset includes invoice-level sales records with product code, product description, quantity, invoice date, unit price, customer ID, and country.

No confidential company data is used.

## SKU Definition

This project uses `stock_code` as the normalized SKU key.

Product descriptions are treated as display fields rather than SKU identifiers. This prevents the same stock code from being split into multiple SKU profiles when product descriptions vary across transactions.

## Project Workflow

The analysis is organized into five notebooks:

### 01 Data Cleaning

Cleans the raw transaction data and creates a valid product sales dataset.

Main steps include:

- Removing duplicate rows.
- Separating cancellations and returns.
- Removing invalid sales records.
- Excluding records without product descriptions.
- Excluding non-product transaction lines such as postage, fees, discounts, bank charges, and manual adjustments.
- Creating a SKU master table.
- Creating a SKU description consistency check.
- Creating monthly SKU-level sales records.
- Creating a data quality summary table.

Main outputs:

- `data/processed/clean_sales.csv`
- `data/processed/returns_cancellations.csv`
- `data/processed/non_product_lines.csv`
- `data/processed/sku_master.csv`
- `data/processed/sku_description_check.csv`
- `data/processed/monthly_sku_sales.csv`
- `data/processed/data_quality_summary.csv`

### 02 SQL Business Queries

Loads cleaned product sales data into SQLite and generates business summary tables using SQL.

The SQL queries are embedded in `notebooks/02_sql_business_queries.ipynb`.

Main outputs:

- `outputs/top_sku_revenue_contribution.csv`
- `outputs/top_sku_unit_contribution.csv`
- `outputs/long_tail_skus.csv`
- `outputs/country_demand_summary.csv`
- `outputs/monthly_sales_trend.csv`

### 03 SKU Classification

Builds SKU-level profiles and classifies products based on revenue contribution, sales volume, and demand volatility.

Main SKU classes include:

- High-Revenue Priority
- High-Turnover Stable
- High-Turnover Volatile
- Long-Tail
- Regular

Main outputs:

- `outputs/sku_profile_classification.csv`
- `outputs/sku_classification_summary.csv`

### 04 Replenishment and Warehouse Allocation

Extends SKU classification into replenishment and warehouse allocation recommendations.

This notebook simulates inventory-related fields because the public dataset does not include actual inventory levels, supplier lead times, unit costs, storage volume, warehouse capacity, or fulfillment method.

Main outputs:

- `outputs/replenishment_recommendations.csv`
- `outputs/overstock_risk_list.csv`
- `outputs/warehouse_allocation_summary.csv`
- `outputs/management_kpi_summary.csv`

### 05 Working Capital Impact

Extends the inventory analytics workflow into a finance-facing working capital analysis.

This notebook loads `outputs/sku_profile_classification.csv` and uses simulated inventory and cost fields to estimate inventory value, stockout revenue exposure, and overstock capital exposure. If the simulated inventory fields are not present in the source file, the notebook recreates the simulated inventory layer deterministically for reproducibility.

Main outputs:

- `outputs/working_capital_summary.csv`
- `outputs/top_overstock_capital_exposure.csv`
- `outputs/top_stockout_revenue_exposure.csv`
- `outputs/inventory_value_by_sku_class.csv`
- `outputs/inventory_value_by_warehouse_strategy.csv`

## Key Results

After cleaning and transformation:

- Valid product sales transactions: 522,716 rows
- Returns / cancellations: 10,587 rows
- Non-product transaction rows excluded: 2,162 rows
- Monthly SKU-level sales records: 34,020 rows
- SKU master records: 3,917 SKUs
- SKU profiles classified: 3,917 SKUs

SKU classification findings:

- High-Revenue Priority SKUs: 784 SKUs
- High-Revenue Priority SKUs contributed approximately 78.8% of total revenue and 66.1% of total units sold
- Regular SKUs: 1,684 SKUs
- High-Turnover Stable SKUs: 208 SKUs
- High-Turnover Volatile SKUs: 69 SKUs
- Long-Tail SKUs: 1,172 SKUs
- Long-Tail SKUs contributed approximately 1.3% of total revenue and 0.6% of total units sold

Inventory risk findings based on simulated inventory assumptions:

- Normal inventory position: 1,561 SKUs
- Stockout Risk: 1,432 SKUs
- Overstock Risk: 924 SKUs

Warehouse strategy outputs:

- `warehouse_strategy_count`: 6 unique warehouse strategies
- `warehouse_allocation_segment_count`: 7 SKU classification × warehouse strategy summary combinations

- Local Warehouse Priority: 784 SKUs
- Stable Local Warehouse Inventory: 208 SKUs
- Small-Batch Replenishment / Monitor Closely: 69 SKUs
- External or Limited Stock Strategy: 335 SKUs
- Overstock Review / Reduce Replenishment: 924 SKUs
- Standard Replenishment Review: 1,597 SKUs

Working capital impact based on simulated inventory and cost assumptions:

- Total SKUs analyzed: 3,917
- Stockout Risk SKUs: 1,432
- Overstock Risk SKUs: 924
- Estimated inventory value: 1,090,613.07
- Stockout revenue exposure: 645,275.56
- Overstock capital exposure: 124,125.96

## Main Output Files

| Output file | Purpose |
| --- | --- |
| `data/processed/clean_sales.csv` | Cleaned valid product sales transactions used as the main analytical dataset. |
| `data/processed/sku_master.csv` | Normalized SKU reference table using `stock_code` as the SKU key. |
| `data/processed/sku_description_check.csv` | Check for stock codes with multiple product descriptions. |
| `data/processed/data_quality_summary.csv` | Summary of the data cleaning process and row counts. |
| `outputs/sku_profile_classification.csv` | SKU-level classification output with revenue, demand, volatility, and recommended action fields. |
| `outputs/replenishment_recommendations.csv` | SKUs that may require replenishment based on simulated inventory and reorder point logic. |
| `outputs/overstock_risk_list.csv` | SKUs that may require overstock review or reduced replenishment. |
| `outputs/warehouse_allocation_summary.csv` | Summary of warehouse strategy groups. |
| `outputs/management_kpi_summary.csv` | Consolidated KPI summary for portfolio and management review. |
| `outputs/working_capital_summary.csv` | Finance-facing summary of simulated inventory value, stockout revenue exposure, and overstock capital exposure. |
| `outputs/top_overstock_capital_exposure.csv` | SKUs with the highest simulated overstock capital exposure. |
| `outputs/top_stockout_revenue_exposure.csv` | SKUs with the highest simulated stockout revenue exposure. |
| `outputs/inventory_value_by_sku_class.csv` | Simulated inventory value summarized by SKU class. |
| `outputs/inventory_value_by_warehouse_strategy.csv` | Simulated inventory value summarized by warehouse strategy. |

## Repository Structure

```text
ecommerce-inventory-warehouse-allocation/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── data/
│   ├── raw/
│   │   └── Online Retail.xlsx
│   └── processed/
│       ├── clean_sales.csv
│       ├── returns_cancellations.csv
│       ├── non_product_lines.csv
│       ├── sku_master.csv
│       ├── sku_description_check.csv
│       ├── monthly_sku_sales.csv
│       └── data_quality_summary.csv
│
├── database/
│   └── ecommerce_inventory.db  # generated by notebook 02, not committed
│
├── notebooks/
│   ├── 01_data_cleaning.ipynb
│   ├── 02_sql_business_queries.ipynb
│   ├── 03_sku_classification.ipynb
│   ├── 04_replenishment_warehouse_allocation.ipynb
│   └── 05_working_capital_impact.ipynb
│
├── outputs/
│   ├── top_sku_revenue_contribution.csv
│   ├── top_sku_unit_contribution.csv
│   ├── long_tail_skus.csv
│   ├── country_demand_summary.csv
│   ├── monthly_sales_trend.csv
│   ├── sku_profile_classification.csv
│   ├── sku_classification_summary.csv
│   ├── replenishment_recommendations.csv
│   ├── overstock_risk_list.csv
│   ├── warehouse_allocation_summary.csv
│   ├── management_kpi_summary.csv
│   ├── working_capital_summary.csv
│   ├── top_overstock_capital_exposure.csv
│   ├── top_stockout_revenue_exposure.csv
│   ├── inventory_value_by_sku_class.csv
│   └── inventory_value_by_warehouse_strategy.csv
│
└── docs/
    └── management_summary.md
```

## How to Run

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

For Windows:

```bash
.venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Place the raw dataset in the following path:

```text
data/raw/Online Retail.xlsx
```

4. Run the notebooks in order:

```text
notebooks/01_data_cleaning.ipynb
notebooks/02_sql_business_queries.ipynb
notebooks/03_sku_classification.ipynb
notebooks/04_replenishment_warehouse_allocation.ipynb
notebooks/05_working_capital_impact.ipynb
```

5. Review the generated outputs:

```text
data/processed/
outputs/
docs/management_summary.md
```

## Generated Files Note

The SQLite database file under `database/` is generated by `02_sql_business_queries.ipynb` and is not intended to be committed to GitHub.

The processed CSV files in `data/processed/` and final CSV outputs in `outputs/` may be included for portfolio review, but they can also be regenerated by running the notebooks in order.

The raw dataset should be placed locally under `data/raw/Online Retail.xlsx` before running the workflow.

## Assumptions and Limitations

The public dataset does not include actual inventory levels, supplier lead times, unit costs, storage volume, warehouse capacity, or fulfillment methods.

Inventory-related fields and cost fields are simulated to demonstrate how transaction-level sales data can be extended into replenishment planning, warehouse allocation analysis, and finance-facing working capital analysis.

Stockout risk, overstock risk, warehouse strategy, and working capital exposure outputs are illustrative decision-support examples. They should not be interpreted as real operational recommendations, accounting values, or actual company inventory decisions.

No confidential company data is used.

## Disclaimer

This project uses public transaction data and simulated inventory assumptions.

No confidential company data is used.

The analysis is intended to demonstrate a reproducible business analytics workflow for SKU classification, replenishment planning, inventory risk review, warehouse allocation, and simulated working capital decision support.
