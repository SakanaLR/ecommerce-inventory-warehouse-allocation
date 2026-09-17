"""Guard the single-workflow layout.

Editors that still have an old notebook open can save it back to its old
path after it was moved. These checks fail loudly when that happens.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NOTEBOOKS = {
    "01_data_cleaning.ipynb",
    "02_sql_business_queries.ipynb",
    "03_sku_classification.ipynb",
    "04_replenishment_warehouse_allocation.ipynb",
    "05_working_capital_impact.ipynb",
}
RETIRED_PATHS = ("processed_standardized", "outputs_standardized")


def test_notebooks_folder_holds_only_the_five_workflow_notebooks():
    found = {p.name for p in (PROJECT_ROOT / "notebooks").glob("*.ipynb")}
    assert found == EXPECTED_NOTEBOOKS, (
        f"Unexpected notebooks: {sorted(found - EXPECTED_NOTEBOOKS)}; "
        f"missing: {sorted(EXPECTED_NOTEBOOKS - found)}. "
        "Old versions belong in archive/notebooks/ (close them in your editor first)."
    )


def test_workflow_notebooks_do_not_use_retired_folders():
    for name in EXPECTED_NOTEBOOKS:
        notebook = json.loads((PROJECT_ROOT / "notebooks" / name).read_text())
        sources = "\n".join(
            "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
            for cell in notebook["cells"]
        )
        for retired in RETIRED_PATHS:
            assert retired not in sources, f"{name} still references {retired}"


def test_archive_keeps_all_ten_previous_notebooks():
    archived = {p.name for p in (PROJECT_ROOT / "archive" / "notebooks").glob("*.ipynb")}
    assert len(archived) == 10
    assert {name.replace(".ipynb", "") for name in EXPECTED_NOTEBOOKS} <= {name.replace(".ipynb", "") for name in archived}
