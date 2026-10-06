"""Compare two versions of the pipeline outputs.

Usage (from the project root):

    # Phase 1 report: original baseline vs end of Phase 1 (both snapshots)
    python scripts/compare_to_baseline.py \
        --baseline reports/baseline_before_phase1 \
        --current reports/baseline_end_phase1 --prefix phase1

    # Phase 3A report: end of Phase 1 vs end of Phase 3A (both snapshots)
    python scripts/compare_to_baseline.py \
        --baseline reports/baseline_end_phase1 \
        --current reports/baseline_end_phase3a --prefix phase3a

    # Phase 3B-1 report: end of Phase 3A vs the live outputs
    python scripts/compare_to_baseline.py \
        --baseline reports/baseline_end_phase3a --current live --prefix phase3b1

A snapshot directory holds ``baseline_metrics.csv``, ``outputs/`` and, when
available, ``data_processed/``. ``live`` means the project's current
``outputs/`` and ``data/processed/``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPORTS = Path("reports")


class Source:
    def __init__(self, spec: str):
        self.live = spec == "live"
        self.root = Path(".") if self.live else Path(spec)
        self.outputs = self.root / "outputs"
        self.processed = Path("data/processed") if self.live else self.root / "data_processed"

    def core_metrics(self) -> dict[str, float]:
        if not self.live:
            return kv(self.root / "baseline_metrics.csv")
        sales = pd.read_csv("data/processed/clean_sales.csv",
                            usecols=["invoice_no", "stock_code", "quantity", "revenue"])
        return {
            "valid_product_sales_rows": len(sales),
            "total_revenue": round(sales["revenue"].sum(), 2),
            "total_units": int(sales["quantity"].sum()),
            "order_count": sales["invoice_no"].nunique(),
            "sku_count": sales["stock_code"].nunique(),
        }


def kv(path: Path) -> dict[str, float]:
    table = pd.read_csv(path)
    return dict(zip(table.iloc[:, 0], pd.to_numeric(table.iloc[:, 1], errors="coerce")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", default="reports/baseline_before_phase1")
    parser.add_argument("--current", default="reports/baseline_end_phase1")
    parser.add_argument("--prefix", default="phase1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    before, after = Source(args.baseline), Source(args.current)

    before_core, after_core = before.core_metrics(), after.core_metrics()
    before_wc, after_wc = kv(before.outputs / "working_capital_summary.csv"), kv(after.outputs / "working_capital_summary.csv")
    before_kpi, after_kpi = kv(before.outputs / "management_kpi_summary.csv"), kv(after.outputs / "management_kpi_summary.csv")
    before_cls = pd.read_csv(before.outputs / "sku_classification_summary.csv").set_index("sku_class")
    after_cls = pd.read_csv(after.outputs / "sku_classification_summary.csv").set_index("sku_class")
    profile_cols = ["stock_code", "description", "total_revenue", "avg_monthly_units", "demand_cv"]
    before_profile = pd.read_csv(before.outputs / "sku_profile_classification.csv", dtype={"stock_code": str}, usecols=profile_cols)
    after_profile = pd.read_csv(after.outputs / "sku_profile_classification.csv", dtype={"stock_code": str}, usecols=profile_cols)

    rows = []
    for metric, value in after_core.items():
        rows.append(("sales", metric, before_core[metric], value))
    rows.append(("sales", "non_product_rows_excluded", before_kpi["non_product_rows_excluded"], after_kpi["non_product_rows_excluded"]))
    for column in ["avg_monthly_units", "demand_cv"]:
        rows.append(("demand", f"median {column}",
                     round(before_profile[column].median(), 4), round(after_profile[column].median(), 4)))
    for sku_class in after_cls.index:
        b_count = before_cls["sku_count"].get(sku_class, 0)
        b_share = before_cls["revenue_share"].get(sku_class, 0.0)
        rows.append(("sku_class", f"{sku_class} | sku_count", b_count, after_cls.loc[sku_class, "sku_count"]))
        rows.append(("sku_class", f"{sku_class} | revenue_share", round(b_share, 4), round(after_cls.loc[sku_class, "revenue_share"], 4)))
    for metric in ["stockout_risk_sku_count", "overstock_risk_sku_count", "replenishment_recommendation_count"]:
        rows.append(("simulated_inventory", metric, before_kpi[metric], after_kpi[metric]))
    for metric in ["total_estimated_inventory_value", "stockout_revenue_exposure", "overstock_capital_exposure"]:
        rows.append(("simulated_working_capital_gbp", metric, before_wc[metric], after_wc[metric]))
    # Metrics introduced in later phases are reported only when the newer side has them.
    for metric in ["annual_holding_cost", "eoq_capped_skus"]:
        if metric in after_wc:
            rows.append(("simulated_working_capital_gbp", metric, before_wc.get(metric, float("nan")), after_wc[metric]))

    def reversal_totals(source: Source) -> dict[str, float]:
        path = source.processed / "reversed_sales.csv"
        if not path.exists():
            return {}
        table = pd.read_csv(path, usecols=["reversal_type", "revenue"])
        return table.groupby("reversal_type")["revenue"].sum().round(2).to_dict()

    before_rev, after_rev = reversal_totals(before), reversal_totals(after)
    for reversal_type in sorted(set(before_rev) | set(after_rev)):
        rows.append(("reversals", f"revenue_removed | {reversal_type}",
                     before_rev.get(reversal_type, 0.0), after_rev.get(reversal_type, 0.0)))

    comparison = pd.DataFrame(rows, columns=["area", "metric", "before", "after"])
    comparison["change"] = comparison["after"] - comparison["before"]
    comparison["change_pct"] = (comparison["change"] / comparison["before"].where(comparison["before"] != 0)).round(4)
    comparison.insert(0, "comparison", f"{args.baseline} -> {args.current}")
    comparison.to_csv(REPORTS / f"{args.prefix}_before_after.csv", index=False)

    # Top-20 on the same basis: both sides ranked from sku_profile_classification.csv,
    # which aggregates by stock_code only.
    before_top = before_profile.nlargest(20, "total_revenue").reset_index(drop=True)
    after_top = after_profile.nlargest(20, "total_revenue").reset_index(drop=True)
    before_top["rank_before"] = before_top.index + 1
    after_top["rank_after"] = after_top.index + 1
    names = pd.concat([after_profile, before_profile]).drop_duplicates("stock_code").set_index("stock_code")["description"]
    top = before_top[["stock_code", "total_revenue", "rank_before"]].merge(
        after_top[["stock_code", "total_revenue", "rank_after"]],
        on="stock_code", how="outer", suffixes=("_before", "_after"),
    )
    top.insert(1, "description", top["stock_code"].map(names))
    after_all = after_profile.set_index("stock_code")["total_revenue"]
    top["total_revenue_after"] = top["total_revenue_after"].fillna(top["stock_code"].map(after_all))
    top["basis"] = "stock_code only (sku_profile_classification.csv, before and after)"
    top = top.sort_values(["rank_after", "rank_before"], na_position="last")
    top.to_csv(REPORTS / f"{args.prefix}_top20_revenue_rank_changes.csv", index=False)

    print(comparison.drop(columns="comparison").to_string(index=False))
    moved = top[top["rank_before"].isna() | top["rank_after"].isna()]
    print("\nTop-20 revenue SKUs (stock_code basis) that entered or left the list:")
    print(moved.drop(columns="basis").to_string(index=False) if len(moved) else "none")


if __name__ == "__main__":
    main()
