from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import validate_input_data  # noqa: E402


CURRENT_MAPPING_PATH = PROJECT_ROOT / "config" / "schema_mapping_template.csv"
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "validate_input_data.py"


def valid_raw_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "InvoiceNo": ["000001"],
            "StockCode": ["SKU-001"],
            "Description": ["Example product"],
            "Quantity": [2],
            "InvoiceDate": ["2024-01-15 10:30:00"],
            "UnitPrice": [4.5],
            "CustomerID": ["CUST-001"],
            "Country": ["United Kingdom"],
        }
    )


def current_mapping() -> pd.DataFrame:
    return validate_input_data.load_mapping(CURRENT_MAPPING_PATH)


def check_status(report: pd.DataFrame, check: str) -> str:
    rows = report.loc[report["check"] == check, "status"]
    assert len(rows) == 1, f"Expected exactly one result for {check!r}"
    return str(rows.iloc[0])


def write_cli_inputs(
    tmp_path: Path,
    mapping: pd.DataFrame,
) -> tuple[Path, Path, Path]:
    input_path = tmp_path / "sales.csv"
    mapping_path = tmp_path / "mapping.csv"
    output_path = tmp_path / "validation_report.csv"

    valid_raw_data().to_csv(input_path, index=False)
    mapping.to_csv(mapping_path, index=False)
    return input_path, mapping_path, output_path


def run_validator_cli(
    input_path: Path,
    mapping_path: Path,
    output_path: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            "--input",
            str(input_path),
            "--mapping",
            str(mapping_path),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_current_valid_mapping_passes() -> None:
    report = validate_input_data.validate(valid_raw_data(), current_mapping())

    assert not report["status"].eq("fail").any()
    assert check_status(report, "required_standard_fields_mapped") == "pass"
    assert check_status(report, "required_source_fields_exist") == "pass"


def test_canonical_required_field_cannot_be_bypassed_with_required_no() -> None:
    mapping = current_mapping()
    mapping.loc[mapping["standard_field"] == "quantity", "required"] = "no"
    raw_data = valid_raw_data().drop(columns="Quantity")

    report = validate_input_data.validate(raw_data, mapping)

    assert check_status(report, "required_source_fields_exist") == "fail"


def test_missing_canonical_source_field_produces_failure() -> None:
    raw_data = valid_raw_data().drop(columns="UnitPrice")

    report = validate_input_data.validate(raw_data, current_mapping())

    assert check_status(report, "required_source_fields_exist") == "fail"


def test_blank_required_source_mapping_produces_failure() -> None:
    mapping = current_mapping()
    mapping.loc[mapping["standard_field"] == "invoice_no", "source_field"] = ""

    report = validate_input_data.validate(valid_raw_data(), mapping)

    assert check_status(report, "required_source_fields_non_blank") == "fail"


def test_duplicate_standard_field_produces_failure() -> None:
    mapping = current_mapping()
    duplicate = mapping.loc[mapping["standard_field"] == "invoice_no"].copy()
    duplicate["source_field"] = "AlternateInvoiceNo"
    mapping = pd.concat([mapping, duplicate], ignore_index=True)
    raw_data = valid_raw_data().assign(AlternateInvoiceNo="ALT-001")

    report = validate_input_data.validate(raw_data, mapping)

    assert check_status(report, "duplicate_standard_fields") == "fail"


def test_duplicate_non_blank_source_field_produces_failure() -> None:
    mapping = current_mapping()
    mapping.loc[mapping["standard_field"] == "description", "source_field"] = (
        "InvoiceNo"
    )

    report = validate_input_data.validate(valid_raw_data(), mapping)

    assert check_status(report, "duplicate_source_fields") == "fail"


def test_cli_returns_zero_for_valid_input(tmp_path: Path) -> None:
    input_path, mapping_path, output_path = write_cli_inputs(
        tmp_path,
        current_mapping(),
    )

    result = run_validator_cli(input_path, mapping_path, output_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert output_path.exists()


def test_cli_returns_one_when_validation_fails(tmp_path: Path) -> None:
    mapping = current_mapping()
    mapping.loc[mapping["standard_field"] == "stock_code", "source_field"] = ""
    input_path, mapping_path, output_path = write_cli_inputs(tmp_path, mapping)

    result = run_validator_cli(input_path, mapping_path, output_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert output_path.exists()
    report = pd.read_csv(output_path)
    assert report["status"].eq("fail").any()
