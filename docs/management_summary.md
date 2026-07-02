# Management Summary

## Project Objective

This project analyzes e-commerce transaction data and converts transaction-level sales records into SKU-level inventory and warehouse allocation decision support.

The goal is to support management in answering three practical business questions:

1. Which SKUs should receive replenishment priority?
2. Which SKUs may create stockout or overstock risk?
3. Which SKUs should be prioritized for local warehouse inventory versus external or limited-stock strategies?

## Data Foundation

The project uses the public UCI Online Retail dataset as the transaction-level sales data source.

The raw dataset was cleaned and transformed into valid product sales records by removing duplicate rows, separating cancellations and returns, excluding invalid sales records, removing records without product descriptions, and excluding non-product transaction lines such as postage, fees, discounts, bank charges, and manual adjustments.

The analysis uses `stock_code` as the normalized SKU key. Product descriptions are treated as display fields rather than SKU identifiers, which prevents the same stock code from being split into multiple SKU profiles when descriptions vary.

Inventory-related fields such as current inventory, supplier lead time, storage volume, and unit cost were simulated for portfolio demonstration purposes. No confidential company data was used.

## Key Data Outputs

After cleaning and transformation:

- Valid product sales transactions: 522,716 rows
- Returns / cancellations: 10,587 rows
- Non-product transaction rows excluded: 2,162 rows
- Monthly SKU-level sales records: 34,020 rows
- SKU master records: 3,917 SKUs
- SKU profiles classified: 3,917 SKUs

## SKU Classification Findings

The SKU classification model grouped products based on revenue contribution, sales volume, and demand volatility.

Key findings:

- High-Revenue Priority SKUs: 784 SKUs
- High-Revenue Priority SKUs contributed approximately 78.8% of total revenue and 66.1% of total units sold
- Regular SKUs: 1,684 SKUs
- High-Turnover Stable SKUs: 208 SKUs
- High-Turnover Volatile SKUs: 69 SKUs
- Long-Tail SKUs: 1,172 SKUs
- Long-Tail SKUs contributed approximately 1.3% of total revenue and 0.6% of total units sold

This indicates that a relatively small group of SKUs drives most business value, while a large number of long-tail SKUs require more cautious inventory treatment.

## Inventory Risk Findings

Based on simulated inventory assumptions and reorder point logic:

- Normal inventory position: 1,561 SKUs
- Stockout Risk: 1,432 SKUs
- Overstock Risk: 924 SKUs

The model suggests that inventory planning should not treat all SKUs equally. High-revenue and high-turnover SKUs should receive closer replenishment monitoring, while long-tail and slow-moving SKUs should be controlled to reduce warehouse space usage and working capital pressure.

## Warehouse Strategy Output

The model maps SKU groups into practical warehouse strategies:

- Local Warehouse Priority: 784 SKUs
- Stable Local Warehouse Inventory: 208 SKUs
- Small-Batch Replenishment / Monitor Closely: 69 SKUs
- External or Limited Stock Strategy: 335 SKUs
- Overstock Review / Reduce Replenishment: 924 SKUs
- Standard Replenishment Review: 1,597 SKUs

## Management Implication

The key management takeaway is that inventory and warehouse resources should be allocated based on SKU contribution, demand stability, and inventory risk.

High-revenue and stable high-turnover SKUs should be prioritized for local warehouse inventory because stockouts may directly affect sales performance.

Volatile high-turnover SKUs should be replenished in smaller batches and monitored more frequently.

Long-tail and overstock-risk SKUs should be stocked more cautiously, reviewed before additional replenishment, or considered for external fulfillment or limited-stock strategies.

This workflow demonstrates how cleaned e-commerce sales data can be converted into structured decision support for replenishment planning, warehouse allocation, and inventory risk management.

## Assumptions and Limitations

The public dataset does not include actual inventory levels, supplier lead times, unit costs, storage volume, warehouse capacity, or fulfillment methods.

Inventory-related fields were simulated to demonstrate how transaction-level sales data can be extended into replenishment planning and warehouse allocation analysis.

This project is designed for portfolio demonstration and business analytics workflow design. It does not represent actual company inventory decisions or use confidential company data.
