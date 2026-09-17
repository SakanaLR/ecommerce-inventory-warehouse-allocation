# Phase 1: Data Correctness Review

This note explains what changed when the cleaning rules were corrected, and why. The figures come from `reports/phase1_before_after.csv` and `reports/phase1_top20_revenue_rank_changes.csv`, which `scripts/compare_to_baseline.py --baseline reports/baseline_before_phase1 --current reports/baseline_end_phase1 --prefix phase1` produces. The pre-fix outputs are kept in `reports/baseline_before_phase1/`, and the end-of-Phase 1 outputs in `reports/baseline_end_phase1/`.

Later phases change the live outputs, but not the tables in this note: they compare two fixed snapshots.

All monetary values are in GBP.

## Comparison bases used in this note

Two comparisons appear below. They answer different questions, so they are kept apart:

| Label | Compares | Where |
| --- | --- | --- |
| **vs original baseline** | Current outputs against the pipeline as it was before Phase 1 (snapshot in `reports/baseline_before_phase1/`) | "Impact" and all tables marked *Before / After* |
| **vs first Phase 1 pass** | Current outputs against the first version of the Phase 1 fixes, which matched cancellations without the same-price preference and had no manual-credit rule | "Revision within Phase 1" |

Unless a table says otherwise, *Before* means the original baseline.

## What was wrong

| Issue | Evidence | Effect before the fix |
| --- | --- | --- |
| Cancelled orders counted as sales | A sale of 80,995 units of `23843` (£168,470) was cancelled 12 minutes later by `C581484`. A sale of 74,215 units of `23166` (£77,184) was cancelled 16 minutes later by `C541433`. | `23843` ranked #2 by revenue and `23166` ranked #6. `23843` alone made up 15% of the simulated stockout exposure. |
| A keying error reversed by a manual credit | Invoice `556444` billed 60 × £649.50 = £38,970 for `22502`. Manual credit `C556445` (stock code `M`) reversed exactly £38,970, and `556446` re-billed 1 × £649.50. | £38,970 of revenue that never happened. The cancellation of the same stock code cannot detect this, because the reversal was booked under a different code. |
| Incomplete non-product list | Still treated as products: `B` "Adjust bad debt" (£11,062), carriage (`C2`, `23444`), a packing charge (`23574`), gift vouchers (`gift_0001_*`, `22016`), samples (`S`), `PADS` (priced at £0.001), and lowercase `m` manual adjustments. | The £11,062 bad-debt line was classified as a High-Revenue Priority SKU. The simulation gave it £423,604 of inventory value, which was **38.8% of the reported £1.09M total**. |
| The same product under several codes | 112 stock codes appear in both lower and upper case with the same description (for example `85123a` and `85123A`). | One product was split into two SKU profiles. |
| Incomplete last month | The data ends on 9 December 2011. | The December 2011 dip in the trend was a calendar artifact, not a drop in demand. |

## Rules applied

1. **Codes:** stock codes are trimmed and upper-cased.
2. **Non-product lines:** codes are listed in `config/non_product_stock_codes.csv` (15 rules). The loader rejects blank, duplicate, or overlapping rules.
3. **Reviewed manual reversals:** these are listed in `config/manual_reversals.csv`. Each entry must match exactly one sale line, and its credit invoice must contain a same-customer credit of equal value; otherwise cleaning stops with an error.
4. **Full cancellations:** a cancellation line removes a sale with the same customer, stock code, and quantity, dated on or before the cancellation.
   - Cancellations are processed in time order.
   - A sale at the same unit price is preferred (the most recent of those); if there is none, the most recent unused sale is taken.
   - Each sale is used at most once. Lines without a customer ID are never matched.
   - `reversed_sales.csv` records `cancel_unit_price`, `price_delta`, `match_quality`, and `reversal_type` for every removed line.
5. **Review-only reports (nothing is removed):**
   - `manual_credit_candidates.csv`: manual credits whose value equals a same-customer sale line from the previous day;
   - `price_anomalies.csv`: lines priced at least 10 times the SKU's median price.
6. **Truncated months:** `month_coverage.csv` flags months cut off by the data's start or end date (`is_truncated_month`), and the monthly trend output carries the same flag. Gaps inside a month are not detected.

### Why the same-price preference matters

Customer 15098 on 10 June 2011:

| Invoice | Line | Treatment |
| --- | --- | --- |
| 556442 | 60 × £4.95 | Removed: cancelled by `C556448` at the same price |
| 556444 | 60 × £649.50 = £38,970 | Removed: reviewed manual credit `C556445` |
| 556446 | 1 × £649.50 | Kept: the corrected invoice |

The first version of the matching used only customer, code, quantity, and time, and chose the most recent sale. It paired `C556448` with `556444`, which removed the right amount for the wrong reason and left `556442` in the data. Preferring the same price alone would have fixed that pair but kept the £38,970 error. Both rules are needed, and a regression test covers this exact case.

Match quality across all 2,815 cancellation matches: 2,722 at the same price and 93 at a different price. In the 93 mismatches, the cancellation price differs from the sale price and no same-price sale was available.

## Impact (vs original baseline)

| Metric | Before (original baseline) | After (current) | Change |
| --- | ---: | ---: | ---: |
| Product sales lines | 522,716 | 519,627 | -3,089 |
| Revenue | 10,266,083.79 | 9,818,872.18 | -447,211.61 (-4.4%) |
| Units | 5,561,566 | 5,337,158 | -224,408 (-4.0%) |
| Orders | 19,779 | 19,646 | -133 |
| SKUs | 3,917 | 3,790 | -127 |
| Non-product lines excluded | 2,162 | 2,435 | +273 |

The revenue change reconciles exactly:

| Component | Lines | Revenue removed |
| --- | ---: | ---: |
| Sales fully reversed by a cancellation line (75.4% of this value was cancelled on the same day) | 2,815 | 387,988.81 |
| Sale reversed by a reviewed manual credit (`556444`) | 1 | 38,970.00 |
| Newly excluded non-product lines | 273 | 20,250.25 |
| Lowercase `m` manual adjustment (now caught by the `M` rule) | – | 2.55 |
| **Total** | | **447,211.61** |

### Top-20 revenue ranking (vs original baseline, same aggregation basis)

Both sides are ranked from `sku_profile_classification.csv`, which aggregates by `stock_code` only.

The old notebook 02 top-20 file grouped by `stock_code` and `description`, so it is not used for this comparison; mixing the two bases would blend cleaning effects with a change in aggregation.

| Change | Stock code | Description | Revenue before | Revenue after |
| --- | --- | --- | ---: | ---: |
| Left (#2) | 23843 | PAPER CRAFT, LITTLE BIRDIE | 168,469.60 | 0 (only sale was cancelled) |
| Left (#6) | 23166 | MEDIUM CERAMIC TOP STORAGE JAR | 81,700.92 | 4,236.47 |
| Left (#11) | 22502 | PICNIC BASKET WICKER SMALL | 51,408.77 | 12,094.17 |
| Entered (#18) | 20725 | LUNCH BAG RED RETROSPOT | – | 35,246.06 |
| Entered (#19) | 22178 | VICTORIAN GLASS HANGING T-LIGHT | – | 32,950.92 |
| Entered (#20) | 22114 | HOT WATER BOTTLE TEA AND SYMPATHY | – | 32,851.84 |

`22502` fell by £39,314.60:
- £38,970.00 from the manual-credit reversal;
- £297.00 from `556442`;
- £47.60 from two smaller full cancellations.

### SKU classes and simulated outputs (vs original baseline)

Compared with the original baseline, class sizes shrink by about 3% each, and the revenue concentration pattern holds:
- **High-Revenue Priority:** 758 SKUs (baseline 784), 77.8% of revenue (baseline 78.8%).
- **Long-Tail:** 1,133 SKUs (baseline 1,172), 1.5% of revenue (baseline 1.3%).

| Simulated metric | Original baseline | Current |
| --- | ---: | ---: |
| Stockout Risk SKUs | 1,432 | 1,439 |
| Overstock Risk SKUs | 924 | 842 |
| Estimated inventory value | 1,090,613.07 | 663,706.48 |
| Stockout revenue exposure | 645,275.56 | 549,965.11 |
| Overstock capital exposure | 124,125.96 | 110,907.87 |

Most of the drop in inventory value comes from removing the bad-debt line. The rest reflects re-drawn simulated values: the random draws are assigned by row position, so a different SKU list gives each SKU different simulated stock and cost. The simulated layer is redesigned in the next phase.

## Revision within Phase 1 (vs first Phase 1 pass)

An external review found that the first pass paired `C556448` with the wrong sale (see "Why the same-price preference matters"). The fix changed the result as follows.

The first-pass figures were recorded from that run's outputs. They were not kept as a separate snapshot, because those outputs were regenerated.

| Metric | First Phase 1 pass | Current | Change |
| --- | ---: | ---: | ---: |
| Product sales lines | 519,628 | 519,627 | -1 |
| Revenue | 9,820,064.78 | 9,818,872.18 | -1,192.60 |
| Units | 5,337,218 | 5,337,158 | -60 |
| Orders | 19,646 | 19,646 | 0 |
| SKUs | 3,790 | 3,790 | 0 |
| Revenue removed by full cancellations | 425,766.21 (2,815 lines) | 387,988.81 (2,815 lines) | -37,777.40 |
| Revenue removed by reviewed manual credits | 0 | 38,970.00 (1 line) | +38,970.00 |
| Total revenue removed vs original baseline | 446,019.01 | 447,211.61 | +1,192.60 |
| High-Revenue Priority revenue share | 77.76% | 77.77% | +0.01 pt |
| SKU class counts (758 / 1,631 / 201 / 1,133 / 67) | same | same | 0 |
| Inventory risk counts (Normal 1,509 / Stockout 1,439 / Overstock 842) | same | same | 0 |
| Warehouse strategy counts | same | same | 0 |
| Estimated inventory value | 663,709.93 | 663,706.48 | -3.45 |
| Stockout revenue exposure | 549,990.79 | 549,965.11 | -25.68 |
| Overstock capital exposure | 110,907.87 | 110,907.87 | 0 |

The top-20 list published with the first pass compared files with different aggregation bases: the baseline file grouped by `stock_code + description`. On that basis, `23203` appeared to enter the list. On the same `stock_code` basis, `20725` enters instead, as shown above.

The counts marked "same" are unchanged only relative to the first pass. Relative to the original baseline, every one of them changed.

## Review lists

- **`manual_credit_candidates.csv`:** 5 candidates.
  - `C556445` is reviewed and applied.
  - The other 4 are worth £2.95–£20.16, and 3 of them match several sale lines, so they are left in place.
- **`price_anomalies.csv`:** 387 lines worth £4,963 in total.
  - 99% have no customer ID; most are "assorted" items sold at a pack price on anonymous invoices.
  - The largest is `556446` (£649.50), the legitimate re-invoice described above.

## Known limitations carried forward

- Partial returns stay in `returns_cancellations.csv` and are not netted against sales.
- The 93 price-mismatched cancellation matches are kept as matches; they are listed in `reversed_sales.csv` for review.
- Average monthly demand and demand CV use active months only. *Addressed in Phase 3A; see `reports/phase3a_demand_and_simulation.md`.*
- Simulated values are assigned by row position. *Addressed in Phase 3A.*
- Simulated stock levels do not scale with each SKU's demand. *Planned for Phase 3B.*
