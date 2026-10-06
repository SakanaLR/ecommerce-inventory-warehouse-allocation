"""Streamlit AppTest smoke tests for the three merchant-app pages.

These execute the real page scripts (no mocking of Streamlit itself) against
the real repository data, and check they render without exception, show the
expected historical/simulated separation, and never leak a forbidden column
into a rendered table.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from retail_analytics import dashboard_data as dd  # noqa: E402

OVERVIEW = PROJECT_ROOT / "app" / "streamlit_app.py"
SKU_ANALYZER = PROJECT_ROOT / "app" / "pages" / "1_SKU_Analyzer.py"
MODEL_NOTES = PROJECT_ROOT / "app" / "pages" / "2_Model_and_Data_Notes.py"


def _all_rendered_dataframe_columns(app_test: AppTest) -> set[str]:
    columns: set[str] = set()
    for element in app_test.dataframe:
        columns |= set(element.value.columns)
    return columns


def _all_markdown_text(app_test: AppTest) -> str:
    """Every markdown/caption/warning/info string the page rendered, joined."""
    parts: list[str] = []
    for group in (app_test.markdown, app_test.caption, app_test.warning, app_test.info):
        parts.extend(element.value for element in group)
    return "\n".join(parts)


def _write_empty_csv(path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=columns).to_csv(path, index=False)


@pytest.fixture
def empty_data_root(tmp_path: Path) -> Path:
    """A temporary project root with every app-facing CSV present but 0 rows.

    Built with real (temporary) CSV files run through the real loaders, not
    hand-built DataFrames, so the dtypes a page actually receives match what
    an empty real source file would produce. Nothing under the repo's own
    ``data/``/``outputs/`` is read or written here.
    """
    _write_empty_csv(tmp_path / "outputs" / "sku_inventory_simulation.csv", dd.REQUIRED_SKU_PROFILE_COLUMNS)
    _write_empty_csv(tmp_path / "data" / "processed" / "sku_month_demand.csv", dd.REQUIRED_SKU_MONTH_DEMAND_COLUMNS)
    _write_empty_csv(tmp_path / "data" / "processed" / "month_coverage.csv", dd.REQUIRED_MONTH_COVERAGE_COLUMNS)
    _write_empty_csv(tmp_path / "data" / "processed" / "data_quality_summary.csv", dd.REQUIRED_DATA_QUALITY_COLUMNS)
    _write_empty_csv(tmp_path / "outputs" / "working_capital_summary.csv", dd.REQUIRED_METRIC_VALUE_COLUMNS)
    return tmp_path


# ---------------------------------------------------------------------------
# Page 1: Overview
# ---------------------------------------------------------------------------

def test_overview_page_runs_without_exception():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert not at.exception


def test_overview_page_title_and_historical_vs_simulated_sections():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert any("Merchant Inventory Overview" in t.value for t in at.title)
    headers = [h.value for h in at.header]
    assert any("Historical" in h for h in headers)
    assert any("Simulated" in h for h in headers)


def test_overview_page_shows_known_headline_numbers():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    metric_values = [m.value for m in at.metric]
    assert "£9,818,872.18" in metric_values
    assert "3,790" in metric_values
    assert "£1,805,589.48" in metric_values


def test_overview_page_never_renders_a_forbidden_column():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert not (_all_rendered_dataframe_columns(at) & dd.FORBIDDEN_COLUMNS)


def test_overview_page_risk_metrics_all_carry_a_simulated_data_hint():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    metrics_by_label = {m.label: m for m in at.metric}
    for label in ("Normal", "Stockout Risk", "Overstock Risk"):
        help_text = (metrics_by_label[label].help or "").lower()
        assert "simulated" in help_text, f"{label} metric is missing a simulated-data hint"


def test_overview_page_explains_what_sku_means():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    metrics_by_label = {m.label: m for m in at.metric}
    help_text = (metrics_by_label["Active SKUs"].help or "").lower()
    assert "stock-keeping unit" in help_text


def test_overview_page_handles_a_fully_empty_data_root_without_exception(empty_data_root, monkeypatch):
    empty_profile = dd.load_sku_profile(project_root=empty_data_root)
    empty_working_capital = dd.load_working_capital_summary(project_root=empty_data_root)
    monkeypatch.setattr(dd, "load_sku_profile", lambda *a, **k: empty_profile)
    monkeypatch.setattr(dd, "load_working_capital_summary", lambda *a, **k: empty_working_capital)

    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert not at.exception
    metric_values = [m.value for m in at.metric]
    assert "0" in metric_values


# ---------------------------------------------------------------------------
# Page 2: SKU Analyzer
# ---------------------------------------------------------------------------

def test_sku_analyzer_runs_without_exception():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    assert not at.exception


def test_sku_analyzer_search_narrows_results_and_shows_detail():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    at.sidebar.text_input(key="sku_search").set_value("heart").run()
    assert not at.exception
    assert any("Matching SKUs" in s.value for s in at.subheader)
    assert at.selectbox  # a SKU can be selected for detail
    assert at.sidebar.multiselect(key="sku_class_filter")
    assert at.sidebar.multiselect(key="inventory_risk_filter")
    assert at.sidebar.multiselect(key="warehouse_strategy_filter")
    assert at.selectbox(key="sku_detail_selector")


def test_sku_analyzer_empty_filter_shows_info_message_not_an_error():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    at.sidebar.text_input(key="sku_search").set_value("no_such_sku_matches_this_zzz").run()
    assert not at.exception
    assert not at.error
    assert any("No SKUs match" in i.value for i in at.info)


def test_sku_analyzer_shows_short_history_warning_for_a_flagged_sku():
    profile = dd.load_sku_profile()
    short_history_code = profile.loc[profile["short_history"], "stock_code"].iloc[0]

    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    at.sidebar.text_input(key="sku_search").set_value(short_history_code).run()
    at.selectbox[0].set_value(short_history_code).run()
    assert not at.exception
    assert any("fewer than the 3-month threshold" in w.value for w in at.warning)


def test_sku_analyzer_never_renders_a_forbidden_column():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    assert not (_all_rendered_dataframe_columns(at) & dd.FORBIDDEN_COLUMNS)


def test_sku_analyzer_sidebar_shows_first_use_guidance_with_all_skus_as_default():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    sidebar_captions = "\n".join(c.value for c in at.sidebar.caption)
    assert "Showing all SKUs by default" in sidebar_captions
    # Confirms P1-2's explicit requirement: guidance text only, no SKUs hidden by default.
    assert any("Matching SKUs (3,790 of 3,790)" in s.value for s in at.subheader)


def test_sku_analyzer_detail_selector_shows_code_and_description():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    at.sidebar.text_input(key="sku_search").set_value("heart").run()
    selector = at.selectbox(key="sku_detail_selector")
    assert selector.options
    assert all(" — " in option for option in selector.options)
    assert any("heart" in option.lower() for option in selector.options)


def test_sku_analyzer_demand_cv_is_rendered_as_a_plain_decimal_not_a_percent():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    [results_df] = [el.value for el in at.dataframe if "Demand CV (monthly sales)" in el.value.columns]
    cv_values = results_df["Demand CV (monthly sales)"].dropna().astype(str)
    assert not cv_values.str.contains("%").any()
    assert (cv_values.str.match(r"^-?\d+\.\d{2}$") | (cv_values == "Not available")).all()


def test_sku_analyzer_detail_metrics_all_carry_plain_language_help():
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    at.sidebar.text_input(key="sku_search").set_value("heart").run()
    metrics_by_label = {m.label: m for m in at.metric}
    expected_labels = [
        "Current inventory (simulated units)", "Safety stock (simulated units)",
        "Reorder point (simulated units)", "EOQ (simulated order units)",
        "Recommended replenishment (simulated units)", "Inventory coverage (simulated days)",
    ]
    for label in expected_labels:
        assert label in metrics_by_label, f"missing detail metric: {label}"
        assert (metrics_by_label[label].help or "").strip(), f"{label} has no help text"


def test_sku_analyzer_handles_a_fully_empty_data_root_without_exception(empty_data_root, monkeypatch):
    empty_profile = dd.load_sku_profile(project_root=empty_data_root)
    empty_month_demand = dd.load_sku_month_demand(project_root=empty_data_root)
    monkeypatch.setattr(dd, "load_sku_profile", lambda *a, **k: empty_profile)
    monkeypatch.setattr(dd, "load_sku_month_demand", lambda *a, **k: empty_month_demand)

    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    assert not at.exception
    assert not at.error
    assert any("No SKUs match" in i.value for i in at.info)


def test_sku_analyzer_handles_a_missing_short_history_flag_without_exception(monkeypatch):
    profile = dd.load_sku_profile().head(1).copy()
    profile.loc[profile.index[0], "short_history"] = pd.NA
    month_demand = dd.load_sku_month_demand()
    monkeypatch.setattr(dd, "load_sku_profile", lambda *a, **k: profile)
    monkeypatch.setattr(dd, "load_sku_month_demand", lambda *a, **k: month_demand)

    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    assert not at.exception
    [results_df] = [el.value for el in at.dataframe if "Short history" in el.value.columns]
    assert results_df["Short history"].iloc[0] == "Not available"


def test_project_disables_streamlit_usage_statistics():
    with (PROJECT_ROOT / ".streamlit" / "config.toml").open("rb") as config_file:
        config = tomllib.load(config_file)
    assert config["browser"]["gatherUsageStats"] is False


# ---------------------------------------------------------------------------
# Page 3: Model & Data Notes
# ---------------------------------------------------------------------------

def test_model_and_data_notes_runs_without_exception():
    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    assert not at.exception


def test_model_and_data_notes_covers_privacy_and_calibration_status():
    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    headers = [h.value.lower() for h in at.header]
    assert any("privacy" in h for h in headers)
    assert any("calibration" in h or "demonstration" in h for h in headers)


def test_model_and_data_notes_never_calls_a_file_timestamp_the_data_generation_time():
    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    text = _all_markdown_text(at).lower()
    assert "data generation time" not in text
    assert "generation time" not in text
    # The real headline signal is the dataset's own transaction coverage, framed
    # as a shipped public snapshot -- not a deploy/checkout timestamp.
    assert "public demonstration snapshot" in text
    if "last modified" in text:
        assert "deployed" in text or "this copy" in text


def test_model_and_data_notes_never_leaks_a_local_absolute_path():
    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    text = _all_markdown_text(at)
    assert str(PROJECT_ROOT) not in text
    assert "/Users/" not in text


def test_model_and_data_notes_links_repo_paths_to_a_stable_github_blob_url():
    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    text = _all_markdown_text(at)
    assert "https://github.com/SakanaLR/ecommerce-inventory-warehouse-allocation/blob/main/docs/runbook.md" in text
    assert "https://github.com/SakanaLR/ecommerce-inventory-warehouse-allocation/blob/main/README.md" in text


def test_model_and_data_notes_handles_empty_coverage_and_quality_tables_without_exception(
    empty_data_root, monkeypatch
):
    empty_coverage = dd.load_month_coverage(project_root=empty_data_root)
    empty_quality = dd.load_data_quality_summary(project_root=empty_data_root)
    monkeypatch.setattr(dd, "load_month_coverage", lambda *a, **k: empty_coverage)
    monkeypatch.setattr(dd, "load_data_quality_summary", lambda *a, **k: empty_quality)

    at = AppTest.from_file(str(MODEL_NOTES), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("No full (non-truncated) months" in w.value for w in at.warning)


# ---------------------------------------------------------------------------
# Path independence: the app must resolve its project root correctly when
# launched (or, for AppTest, executed) from outside the repository directory.
# ---------------------------------------------------------------------------

def test_overview_page_resolves_paths_correctly_from_an_unrelated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert not at.exception
    assert "£9,818,872.18" in [m.value for m in at.metric]


def test_sku_analyzer_resolves_paths_correctly_from_an_unrelated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(SKU_ANALYZER), default_timeout=60)
    at.run()
    assert not at.exception
