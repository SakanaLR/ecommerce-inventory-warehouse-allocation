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


def test_overview_page_never_renders_a_forbidden_column():
    at = AppTest.from_file(str(OVERVIEW), default_timeout=60)
    at.run()
    assert not (_all_rendered_dataframe_columns(at) & dd.FORBIDDEN_COLUMNS)


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
