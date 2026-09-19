# Changelog

## Unreleased — Delivery baseline closure: CI, dependency floors, and licensing

Housekeeping only; no business model, parameter, notebook, `data/processed/`, `outputs/`, or historical baseline report was touched. See `docs/pr_delivery.md` for the full write-up.

### Added

- `.github/workflows/tests.yml`: Python 3.11, pip-cached install of `requirements-dev.txt` from a fresh checkout, `python -m pytest -W error -ra --junitxml=pytest-results.xml`, then a machine-readable JUnit XML check that fails the build if any test is skipped (a fresh checkout must never silently skip a test for missing data).
- `CITATION.cff`: records the repository URL and cites the UCI "Online Retail" dataset (citation text taken from the UCI page); it uses the non-personal placeholder "Repository maintainers" until a maintainer confirms the preferred attribution.
- README: a "License" section stating plainly that the repository's own code currently has **no license file** (default: all rights reserved) and that choosing one is left to the repository owner; a "Dataset license and citation" note under "Data Source" — the dataset is CC BY 4.0 (verified by fetching the UCI page directly, not from memory), which is why it can be committed to the repo at all.

### Changed

- `requirements.txt` / `requirements-dev.txt`: added minimum-version floors (no upper bound) instead of leaving every package unpinned. `pandas>=2.2.3`, `numpy>=1.26.0`, `openpyxl>=3.1.0`, and `pytest>=8.0.0` were verified by installing exactly those floor versions into a clean virtualenv and running `pytest -W error -ra` end to end (127 passed, 0 skipped) — not chosen by guesswork, and not a full `pip freeze` lock file. `jupyter`/`ipykernel`/`nbconvert` floors are set by convention (they're only used to execute notebooks, not exercised by the test suite) and are explicitly flagged in the file as not independently verified the same way.
- Removed `matplotlib` from `requirements.txt`: grepped the entire codebase (`src/`, `scripts/`, `notebooks/`) and found no import or usage anywhere; it was dead weight.

### Fixed

- `tests/test_model_assumptions_diagnostics.py::test_cli_scenarios_are_independent_deterministic_and_described` asserted `metadata['code']['untracked_file_sha256']` was truthy — but that field is legitimately `{}` whenever the working tree has no untracked files, which is **always true on a fresh CI checkout**. This test would have failed on every CI run as written. Changed the assertion to check the field's type (a dict) instead of its truthiness; the diagnostics script itself is unchanged.

## Unreleased — Model assumptions audit: diagnosis, independent review, and reproducible tooling (R1/T1/T2/E1)

Follows `docs/model_assumptions_audit.md` (diagnosis: short-history demand statistics, EOQ capping, parameter sensitivity), `docs/model_assumptions_review.md` (Codex's independent review — several findings downgraded from "confirmed" to "partially correct" or "insufficient evidence," most notably that the audit's headline "699/1,008 SKUs" figure only holds under one specific experiment methodology, not as a general false-positive rate), and `docs/model_assumptions_plan.md` (the resulting plan). Implements that plan's R1, T1, T2, and E1 only; B1 (business parameter calibration) and B2/D1 (reopening the short-window policy decision) remain open, pending user decisions.

### Fixed (documentation)

- `docs/runbook.md`'s `overstock_capital_exposure` definition was simply wrong ("units above 180 days of demand") for the live `max_stock` method; corrected to the actual effective threshold, `max(reorder_point + EOQ, daily_demand × overstock.coverage_days)`, with the legacy `coverage_only` method's simpler definition kept separate.
- Added an accurate definition of what `demand_cv` measures (relative monthly-sales volatility including zero-sale months, with the exact Pearson r=0.840224 relationship to zero-month share) in place of the earlier draft's overreaching "mainly measures intermittency" claim.
- Clarified that `months_in_window == 3` is not the same as `short_history` (the flag is strictly `< 3`).
- `ordering_cost_gbp`, `annual_holding_rate`, `max_order_coverage_days`, `overstock.coverage_days`, `supplier_lead_time_days`, and the service-level table are now explicitly labeled demonstration/pending-calibration parameters with owner and calibration date stated as "not yet assigned" — not invented.
- `docs/model_assumptions_audit.md` (the original diagnosis) is kept as historical material with a prominent banner pointing to the review and plan, rather than being silently rewritten.

### Added (tests)

- `tests/test_demand_simulation_interface.py` (T1, 8 tests): 0/1/2/3-month demand observations run through the real `full_months` → `build_sku_profile` → `classify_skus` → `simulate` pipeline end to end, including the exact `short_history` boundary and zero-demand inventory Normal/Overstock cases.
- `tests/test_simulation.py` (T2, 12 tests): EOQ integer-cap equality/boundary cases, monotonicity invariants (ordering cost, holding rate, cap looseness), current-inventory-equals-threshold boundaries, the `max(Q, shortfall)` replenishment rule, and a direct fixed-inventory-vs-full-regeneration contract comparison. All assert invariants that must hold for any legal configuration, not today's specific diagnostic snapshot numbers.
- `scripts/model_assumptions_diagnostics.py` (E1): reproduces the review's fixed-inventory (A) and full-regeneration (B) experiments plus the nine sensitivity scenarios, against any `--profile`/`--config`, writing only to an explicit `--output-dir` that must not be, or be inside, any official repository directory. Reports risk counts, shortfall units, and monetary exposure together; never searches for or writes back a "best" parameter set.
- `tests/test_model_assumptions_diagnostics.py` (added independently by Codex's acceptance pass): CLI safety, atomicity (no partial output on a mid-write failure), determinism, and config-compatibility tests for the diagnostics script.

### Codex acceptance corrections (`bfdc558`)

- E1 hardened: rejects unknown/duplicate scenario names and incompatible configs, refuses an already-existing output directory or a symlink alias for one, publishes results atomically via a temp directory, and detects if an input file changes mid-run. Metadata now also records the staged diff, untracked file contents, source file hashes, and the exact comparison tolerances used.
- R1/T1/T2 doc and test gaps closed: linked the review's corrections next to the original MA-04 text in the audit report, README, and management summary (699/1,008 is now clearly scoped to the fixed-inventory experiment, not a false-positive rate); added previously-missing boundary fixtures (needs-statistics-derived assertions from demand through safety stock to reorder point, strict coverage-threshold boundaries, non-integer EOQ-cap boundaries).
- Test count: **127 passed, 0 skipped** (`python -m pytest -W error -ra` in the project `.venv`).

### Not changed

- No business formulas, live parameters, or historical baseline reports were touched. `config/simulation_assumptions.json`, `outputs/`, `data/processed/`, and every notebook are byte-identical to before this round; 138 official file hashes were checked before and after.

## Unreleased — Post-3B-1 remediation: legacy config compatibility, validation gap, and documentation catch-up

Follows the independent review in `docs/issue_review.md` and the plan in `docs/remediation_plan.md`.

### Fixed

- **`methods.order_quantity = "top_up"` no longer requires an `order_quantity` config section.** Previously, `apply_replenishment_rules` (`src/retail_analytics/simulation.py`) read `assumptions["order_quantity"]` unconditionally before checking which method was selected, so a legitimate minimal top_up config (such as `reports/baseline_end_phase3a/simulation_assumptions_phase3a.json`) crashed with `KeyError`. Fixed in three places: `simulation.py`, `scripts/attribute_model_changes.py`, and `notebooks/05_working_capital_impact.ipynb`. EOQ-only parameters are now read only on the `eoq` path.
- **Notebook 05 leaves `annual_holding_cost` unavailable (blank), not defaulted to 0, when `methods.order_quantity != "eoq"`.** Notebook 05 checks the selected method; the attribution script leaves it unavailable when the holding-rate parameter is absent (with the live rate present, it applies that same rate to all comparison steps), including in the grouped summary tables (pandas' default `sum()` would otherwise turn an all-missing column into a fake 0).
- **`methods.overstock = "max_stock"` now requires `methods.order_quantity = "eoq"`**, enforced in `validate_assumptions` — previously this combination passed validation but silently used a weaker overstock threshold (missing the EOQ term) with no error.

### Documentation

- `docs/management_summary.md`, `README.md`, and `docs/runbook.md` now describe the actual live model (service-level safety stock, EOQ, policy-band inventory, max-stock overstock) instead of the retired Phase 3A description; warehouse-strategy and working-capital figures were refreshed to match current output, and `annual_holding_cost` is documented.
- Noted that a SKU's revenue rank takes priority over its `short_history` flag when assigning High-Revenue Priority (by design, unchanged this round); this affects 27 current SKUs and is now called out as a known, accepted limitation rather than left undocumented.

### Added

- `tests/test_attribute_model_changes.py` (2 tests) and `tests/test_cleaning_pipeline_regression.py` (3 tests) — the latter runs the actual cleaning code against the real raw file into a temporary directory and checks the headline aggregates, rather than only comparing pre-generated CSVs.
- `tests/test_simulation.py`: 3 more tests, for the legacy top_up config path and the new overstock/order_quantity validation.
- `tests/test_demand.py`: extended the classification-precedence test to cover a high-revenue, short-history SKU explicitly.
- Current test count: 78 (`python -m pytest -W error` from the project `.venv`).

### Codex final acceptance corrections

- The attribution CLI now stops at the configured methods, so a minimal historical config never enters an EOQ step. Added a CLI regression test and coverage of all 10 legal method combinations.
- Cleaning revenue regression uses `rel=0, abs=0.01`; pytest's default relative tolerance previously allowed nearly £10 of drift.
- Pipeline verification propagates pipeline failures and exits with its accumulated status; notebook warnings remain visible.
- README/runbook Phase 3A comparison commands use the frozen Phase 3A snapshot, matching the verification script.
- Refreshed the three intermediate attribution exposures from £1,296,241.70 to the independently rerun £1,296,241.69. This is a one-penny change in a rounded monetary result, not accepted as generic floating-point noise; the historical cause is unproven. Current-model endpoints, classifications, risk flags and ranked outputs are unchanged.

### Not changed

- No business result changes under the current, valid live configuration: re-running notebooks 04–05 after these fixes reproduces `outputs/working_capital_summary.csv`, `outputs/inventory_value_by_sku_class.csv`, and `outputs/inventory_value_by_warehouse_strategy.csv` byte-for-byte. Per-SKU floating-point values in `outputs/sku_inventory_simulation.csv` differ by up to 7×10⁻¹² (small floating-point differences; their historical cause has not been established), which does not change any reported figure.

## Unreleased — Phase 3B-1: service-level safety stock, EOQ, and policy-band inventory

All figures in this entry are measured against the **end of Phase 3A** (`reports/baseline_end_phase3a/`), not against Phase 1 or the original baseline.

### Changed

- **Simulation model is now configurable per field**, via a new `methods` block in `config/simulation_assumptions.json` (`src/retail_analytics/simulation.py`). The live configuration is:
  - `inventory = policy_band`: current inventory = reorder point + p × EOQ, with p drawn per SKU from a class-dependent range.
  - `safety_stock = service_level`: z(service level) × monthly demand std × √(lead time ÷ days per month), with a per-class service level.
  - `order_quantity = eoq`: EOQ = √(2 × annual demand × ordering cost ÷ (unit cost × annual holding rate)), capped at 180 days of coverage.
  - `overstock = max_stock`: inventory above max(reorder point + EOQ, coverage-day limit), for all classes.
  - The previous Phase 3A model (`fixed_range`/`volatility_factor`/`top_up`/`coverage_only`) is still fully supported and used for comparison.
- **Simulated results:**
  - Stockout 1,326 → 536; Overstock 1,086 → 1,008; Normal 1,378 → 2,246.
  - Inventory value £637,918.62 → £1,805,589.48.
  - Stockout exposure £563,830.24 → £84,414.16.
  - Overstock exposure £135,218.48 → £53,315.26.
  - New metrics: `annual_holding_cost` (£451,397.56) and `eoq_capped_skus` (2,242).
  - `reports/phase3b1_attribution.csv` isolates the effect of each method change one at a time; read it end to end, since an intermediate step (service-level safety stock alone, before the inventory model switches to policy_band) temporarily raises stockout risk to 1,855 as an artifact of isolating one variable, not a regression.

### Added

- `tests/test_simulation.py`: 13 new tests for the service-level safety stock, EOQ, policy-band inventory, and overstock formulas, plus configuration-validation tests.
- `scripts/attribute_model_changes.py` and `reports/phase3b1_attribution.csv`.
- `reports/baseline_end_phase3a/` snapshot, plus `reports/phase3b1_before_after.csv`, `reports/phase3b1_top20_revenue_rank_changes.csv`, and `reports/phase3b1_simulation_stability.csv`.

### Unchanged

- Cleaning rules, demand basis, and SKU classification: revenue £9,818,872.18, 519,627 lines, 3,790 SKUs, and the same SKU class counts and top-20 revenue list as Phase 3A.

## Unreleased — Phase 3A: demand basis and stable simulation

All figures in this entry are measured against the **end of Phase 1** (`reports/baseline_end_phase1/`), not against the original baseline.

### Changed

- **Demand statistics** (`avg_monthly_units`, `std_monthly_units`, `demand_cv`) now come from a SKU × month panel over the 12 full months, zero-filled from each SKU's first sale month.
  - Median monthly units: 45.2 → 38.0. Median CV: 0.77 → 1.01.
  - The old active-month average is kept as `avg_monthly_units_active`.
- **Volatility rule:** a high-turnover SKU is volatile when its CV is above 1.0 or its history is short, instead of when its CV is above the 75th percentile.
  - High-Turnover Stable: 201 → 182. High-Turnover Volatile: 67 → 86. Other classes are unchanged.
- **Simulated fields** are drawn per SKU from SHA-256(seed | field | stock_code) instead of by row position. Distributions are unchanged.
  - Removing a SKU or shuffling rows now changes no other SKU's values. Before, every SKU's simulated fields and about 32% of risk flags changed.
- **Notebook 05** reads the simulated layer saved by notebook 04 instead of simulating again.
- **Simulated results:**
  - Stockout 1,439 → 1,326; Overstock 842 → 1,086; Normal 1,509 → 1,378.
  - Inventory value £663,706.48 → £637,918.62.
  - Stockout exposure £549,965.11 → £563,830.24.
  - Overstock exposure £110,907.87 → £135,218.48.
  - `reports/phase3a_attribution.csv` separates the effect of the demand basis from the effect of the new draws.
- **Comparison script:** `scripts/compare_to_baseline.py` takes `--baseline`, `--current`, and `--prefix`. The Phase 1 report files are regenerated from the two snapshots with identical values, plus two new demand rows and a `comparison` column.

### Added

- `src/retail_analytics/demand.py` and `tests/test_demand.py` (6 tests).
- `src/retail_analytics/simulation.py`, `tests/test_simulation.py` (7 tests), and `config/simulation_assumptions.json`.
- `data/processed/sku_month_demand.csv` and `outputs/sku_inventory_simulation.csv`.
- New profile fields: `months_in_window`, `zero_months_in_window`, `zero_month_share`, `short_history` (160 SKUs), and `no_full_month_sales` (1 SKU).
- `scripts/check_simulation_stability.py` and `scripts/verify_pipeline.sh`.
- The `reports/baseline_end_phase1/` snapshot.
- `reports/phase3a_before_after.csv`, `reports/phase3a_top20_revenue_rank_changes.csv`, `reports/phase3a_attribution.csv`, `reports/phase3a_simulation_stability.csv`, and `reports/phase3a_demand_and_simulation.md`.

### Unchanged

- Cleaning rules and every sales figure: revenue £9,818,872.18, 519,627 lines, 3,790 SKUs, and the same top-20 revenue list.

## Unreleased — Phase 1: data correctness and single workflow

All figures in this entry are measured against the original (pre-Phase 1) baseline unless stated otherwise.

### Fixed

**Reversed sales**
- Sales that the same customer later cancelled in full are now removed: 2,815 lines, £387,988.81. This includes the 80,995-unit order of `23843` and the 74,215-unit order of `23166`.
- Cancellation matching prefers a sale at the same unit price. Before this change, `C556448` (60 × £4.95) was paired with `556444` (60 × £649.50) only because `556444` was more recent.
- Keying errors reversed by a manual credit note are now removed through a reviewed list: `556444`, £38,970, reversed by `C556445`.

**Non-product lines and codes**
- The non-product list now also excludes these codes, which removes 273 more lines (£20,250.25):
  - `B` (bad debt)
  - `C2` and `23444` (carriage)
  - `23574` (packing charge)
  - gift vouchers (`GIFT_*`, `22016`)
  - `S` (samples)
  - `PADS`
- Stock codes are upper-cased, which merges 112 case-only duplicate codes. This also moves lowercase `m` manual adjustments under the `M` rule.

**Notebooks and documentation**
- The SKU display description is the most frequent description instead of the first one seen.
- Notebook 04 builds its KPI table from the data-quality summary instead of hardcoded numbers.
- Notebook 02 takes descriptions from the SKU master instead of `MIN(description)`.
- The runbook now describes the matching direction correctly: each cancellation takes a sale.

### Added

**Cleaning module, rules, and tests**
- `src/retail_analytics/cleaning.py`: tested cleaning functions used by notebook 01.
- `config/non_product_stock_codes.csv`: 15 rules. The loader rejects blank, duplicate, and overlapping rules.
- `config/manual_reversals.csv`: reviewed manual-credit reversals. Each entry is checked against the data.
- `tests/test_cleaning.py` (22 tests, including a regression test for customer 15098 on 10 June 2011), `tests/conftest.py`, and `pytest.ini`.

**Processed outputs**
- `reversed_sales.csv`, with `reversal_type`, `cancel_unit_price`, `price_delta`, and `match_quality`.
- `month_coverage.csv`, with `is_truncated_month`. The monthly trend carries the same flag; December 2011 ends on the 9th.
- `manual_credit_candidates.csv` and `price_anomalies.csv` (review lists only).

**Comparison and reporting**
- `scripts/compare_to_baseline.py`, which compares top-20 revenue on the same `stock_code` basis before and after.
- The `reports/baseline_before_phase1/` snapshot.
- `reports/phase1_before_after.csv`, `reports/phase1_top20_revenue_rank_changes.csv`, and `reports/phase1_data_correctness.md`.
- GBP labels on monetary outputs, and a clearer definition of stockout revenue exposure.

### Changed

- The two notebook tracks are merged into one set, `notebooks/01`–`05`, based on the standardized-input version. It reads `data/interim/standardized_sales.csv` and writes to `data/processed/` and `outputs/`.
- The previous notebooks moved to `archive/notebooks/`.
- `data/processed/` and `outputs/` were regenerated. Revenue is now £9,818,872.18, down £447,211.61 (4.4%) from the baseline.
- README, `docs/runbook.md`, and `docs/management_summary.md` were updated with the new figures and rules.
- `.gitignore` now ignores `data/processed/clean_sales.csv` and `.pytest_cache/`. The file was removed from the index with `git rm --cached`; the local copy is kept.
- `requirements-dev.txt` now includes `nbconvert`. The pytest pin is widened from `<9` to `<10`, to match the pytest 9.1.1 already in the project environment.

### Revised within Phase 1 (vs the first Phase 1 pass)

- Cancellation matching now prefers a sale at the same unit price, and a reviewed manual-credit rule was added.
- Compared with the first pass:
  - revenue is £1,192.60 lower (£9,820,064.78 → £9,818,872.18);
  - revenue removed by full cancellations fell by £37,777.40;
  - £38,970.00 is now removed through the manual-credit rule.
- SKU class counts, inventory risk counts, and warehouse strategy counts are the same as in the first pass. They still differ from the original baseline.
- The top-20 before/after comparison now uses the same `stock_code` basis on both sides.
