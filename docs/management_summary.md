# Management Summary

## Project Objective

This project converts e-commerce transaction data into SKU-level decision support for replenishment, inventory risk, warehouse allocation, and working capital. It answers three practical questions:

1. Which SKUs should receive replenishment priority?
2. Which SKUs may create stockout or overstock risk?
3. Which SKUs belong in local warehouse inventory, and which suit external or limited-stock strategies?

All monetary values are in GBP.

## Data Foundation

The analysis uses the public UCI Online Retail dataset: 541,909 transaction lines from 1 December 2010 to 9 December 2011.

The raw file was validated, standardized, and cleaned:

- duplicates removed;
- returns and cancellations separated;
- invalid lines removed;
- non-product lines excluded (postage, carriage, fees, discounts, bad-debt and manual adjustments, samples, gift vouchers);
- sales reversed by a reviewed manual credit removed;
- sales that the same customer later cancelled in full removed, matched at the same unit price where possible.

`stock_code` is the SKU key, and the most frequent description is used for display.

**Data-quality finding.** Compared with the original pipeline, the corrected cleaning lowers revenue by £447,212 (4.4%). Reversed orders and non-product lines had been counted as sales:

- Two orders of 80,995 and 74,215 units were cancelled within minutes but had been counted as sales.
- A £38,970 keying error had been reversed through a manual credit note, not a matching cancellation.
- A £11,062 bad-debt adjustment had been treated as a top-revenue product; it accounted for 38.8% of the simulated inventory value.

Details are in `reports/phase1_data_correctness.md`.

## Key Data Outputs

| Measure | Value |
| --- | ---: |
| Valid product sales lines | 519,627 |
| Revenue | £9.82M |
| Orders | 19,646 |
| SKUs | 3,790 |
| Returns and cancellations separated | 10,587 lines |
| Non-product lines excluded | 2,435 |
| Sales fully reversed by a cancellation | 2,815 lines (£387,989) |
| Sale reversed by a reviewed manual credit | 1 line (£38,970) |

The United Kingdom generates 84.7% of revenue.

## SKU Classification Findings

| SKU class | SKUs | Revenue share | Unit share |
| --- | ---: | ---: | ---: |
| High-Revenue Priority | 758 | 77.8% | 64.6% |
| Regular | 1,631 | 16.2% | 18.6% |
| High-Turnover Stable | 182 | 3.3% | 10.8% |
| Long-Tail | 1,133 | 1.5% | 0.7% |
| High-Turnover Volatile | 86 | 1.2% | 5.3% |

About one fifth of SKUs generate nearly four fifths of revenue, while almost a third contribute 1.5%. Inventory attention and warehouse space should follow that concentration.

**How demand is measured.** Monthly demand counts months without sales as zero, from each product's first sale, over the 12 full months of data. Counting only months with sales would overstate demand at least twofold for 827 products and make intermittent sellers look steady. A high-turnover product is treated as volatile when its monthly demand typically swings by more than its own average (coefficient of variation above 1.0).

## Inventory Risk Findings (Simulated)

- Normal: 2,246 SKUs
- Stockout Risk: 536 SKUs
- Overstock Risk: 1,008 SKUs

Most overstock flags sit in the Long-Tail (507) and Regular (467) classes, where realistic monthly demand is small relative to the simulated stock.

High-revenue and high-turnover SKUs need closer replenishment monitoring. Long-tail and slow-moving SKUs should be controlled to limit warehouse space and working capital.

## Warehouse Strategy Output (Simulated)

| Strategy | SKUs |
| --- | ---: |
| Standard Replenishment Review | 1,164 |
| Overstock Review / Reduce Replenishment | 1,008 |
| Local Warehouse Priority | 748 |
| External or Limited Stock Strategy | 626 |
| Stable Local Warehouse Inventory | 171 |
| Small-Batch Replenishment / Monitor Closely | 73 |

## Working Capital View (Simulated)

| Metric | Value |
| --- | ---: |
| Estimated inventory value | £1,805,589 |
| Annual holding cost | £451,398 |
| Stockout revenue exposure (upper-bound indicator) | £84,414 |
| Overstock capital exposure | £53,315 |

The simulated values are drawn per product, so adding or removing products does not change the figures for the others. Annual holding cost is only available under the current inventory model (order quantities sized by EOQ); it is not defaulted to zero if a simpler model without EOQ is configured.

## Management Implications

- Prioritize local inventory for high-revenue and stable high-turnover SKUs, where stockouts directly affect sales.
- Replenish volatile high-turnover SKUs in smaller batches and review them more often.
- Stock long-tail and overstock-risk SKUs cautiously, review them before reordering, or move them to external or limited-stock fulfilment.
- Validate transactions before analysis. Cancelled orders, manual credits, and non-product lines can materially distort both revenue rankings and inventory-value estimates.

## Assumptions and Limitations

- Inventory levels, lead times, unit costs, storage volumes, and fulfilment methods are simulated. Risk counts, strategies, and monetary exposures illustrate the workflow and are not real company decisions or accounting values.
- Current inventory position follows a reorder-point-plus-EOQ policy band per SKU class. Safety stock uses a per-class service-level target (z-score × monthly demand volatility × √lead time), and order quantities use an EOQ formula capped at 180 days of coverage. This replaced an earlier, coarser model (a fixed random inventory range, a volatility-factor safety stock, and a fixed reorder quantity). `reports/phase3b1_attribution.csv` isolates the effect of each change one at a time; read it end to end rather than only its first and last rows — turning on the service-level safety stock alone (before the inventory model also switches to the reorder-point-based policy band) temporarily raises the stockout-risk count above both the old and new model, because the old fixed random inventory draw does not yet track the new, higher reorder points. That intermediate row is an artifact of isolating one variable at a time, not a regression in either model.
- Demand statistics cover the 12 full months only; products with under 3 months of history are flagged (`short_history`). By design, a SKU's revenue rank still determines its classification even when it has short history (see `src/retail_analytics/demand.py`), so a short-history SKU's demand volatility statistic should be treated as unreliable rather than assumed accurate. In practice this affects 27 High-Revenue Priority SKUs; only one of them currently has a resulting zero safety stock, and the rest show no systematic difference in simulated safety stock or stockout incidence from SKUs with full history.
- Partial returns are not netted against sales.
