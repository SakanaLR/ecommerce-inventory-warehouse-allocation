from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT_PATH = Path("data/raw/Online Retail.xlsx")
DEFAULT_MAPPING_PATH = Path("config/schema_mapping_template.csv")
DEFAULT_OUTPUT_PATH = Path("outputs/data_quality_precheck.csv")
REQUIRED_STANDARD_FIELDS = {
    "invoice_no",
    "stock_code",
    "quantity",
    "invoice_date",
    "unit_price",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate raw sales data against the standard schema mapping."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_PATH),
        help="Path to raw sales data file (.csv, .xlsx, or .xls).",
    )
    parser.add_argument(
        "--mapping",
        default=str(DEFAULT_MAPPING_PATH),
        help="Path to schema mapping CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path for validation summary CSV.",
    )
    parser.add_argument(
        "--sheet-name",
        default=None,
        help="Optional Excel sheet name. Defaults to the first sheet.",
    )
    return parser.parse_args()


def load_raw_data(path: Path, sheet_name: str | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        if sheet_name:
            return pd.read_excel(path, sheet_name=sheet_name)
        return pd.read_excel(path)

    raise ValueError(f"Unsupported file type: {suffix}. Use .csv, .xlsx, or .xls.")


def load_mapping(path: Path) -> pd.DataFrame:
    mapping = pd.read_csv(path)
    required_columns = {"standard_field", "source_field", "required", "data_type", "description"}
    missing_columns = required_columns - set(mapping.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Schema mapping is missing required columns: {missing}")

    for column in required_columns:
        mapping[column] = mapping[column].fillna("").astype(str).str.strip()

    mapping["standard_field"] = mapping["standard_field"].str.lower()
    mapping["required"] = mapping["required"].str.lower()
    mapping["data_type"] = mapping["data_type"].str.lower()
    return mapping


def add_result(results: list[dict], check: str, status: str, detail: str, row_count: int | None = None) -> None:
    results.append(
        {
            "check": check,
            "status": status,
            "detail": detail,
            "row_count": "" if row_count is None else row_count,
        }
    )


def validate_mapping_quality(mapping: pd.DataFrame, results: list[dict]) -> None:
    standard_fields = set(mapping["standard_field"])
    missing_required_fields = sorted(REQUIRED_STANDARD_FIELDS - standard_fields)

    if missing_required_fields:
        add_result(
            results,
            "required_standard_fields_mapped",
            "fail",
            "Required standard fields missing from mapping file: "
            + ", ".join(missing_required_fields),
            len(missing_required_fields),
        )
    else:
        add_result(
            results,
            "required_standard_fields_mapped",
            "pass",
            "All required standard fields are present in the mapping file.",
            0,
        )

    required_rows = mapping[mapping["standard_field"].isin(REQUIRED_STANDARD_FIELDS)]
    blank_required_mappings = sorted(
        required_rows.loc[required_rows["source_field"] == "", "standard_field"].tolist()
    )

    if blank_required_mappings:
        add_result(
            results,
            "required_source_fields_non_blank",
            "fail",
            "Required standard fields with blank source_field: "
            + ", ".join(blank_required_mappings),
            len(blank_required_mappings),
        )
    else:
        add_result(
            results,
            "required_source_fields_non_blank",
            "pass",
            "All required standard fields have non-blank source_field mappings.",
            0,
        )

    duplicate_standard_fields = sorted(
        mapping.loc[
            mapping["standard_field"].ne("")
            & mapping["standard_field"].duplicated(keep=False),
            "standard_field",
        ].unique()
    )

    if duplicate_standard_fields:
        add_result(
            results,
            "duplicate_standard_fields",
            "fail",
            "Duplicate standard_field values in mapping file: "
            + ", ".join(duplicate_standard_fields),
            len(duplicate_standard_fields),
        )
    else:
        add_result(
            results,
            "duplicate_standard_fields",
            "pass",
            "No duplicate standard_field values detected.",
            0,
        )

    duplicate_source_fields = sorted(
        mapping.loc[
            mapping["source_field"].ne("")
            & mapping["source_field"].duplicated(keep=False),
            "source_field",
        ].unique()
    )

    if duplicate_source_fields:
        add_result(
            results,
            "duplicate_source_fields",
            "warn",
            "Duplicate non-blank source_field values in mapping file: "
            + ", ".join(duplicate_source_fields),
            len(duplicate_source_fields),
        )
    else:
        add_result(
            results,
            "duplicate_source_fields",
            "pass",
            "No duplicate non-blank source_field values detected.",
            0,
        )


def validate(df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    results: list[dict] = []
    original_columns = list(df.columns)
    stripped_columns = [str(column).strip() for column in original_columns]
    whitespace_columns = [
        str(column)
        for column, stripped in zip(original_columns, stripped_columns)
        if str(column) != stripped
    ]

    if whitespace_columns:
        df = df.copy()
        df.columns = stripped_columns
        add_result(
            results,
            "raw_column_whitespace_stripped",
            "warn",
            "Raw column names had leading/trailing whitespace and were stripped: "
            + ", ".join(whitespace_columns),
            len(whitespace_columns),
        )
    else:
        add_result(
            results,
            "raw_column_whitespace_stripped",
            "pass",
            "No leading/trailing whitespace detected in raw column names.",
            0,
        )

    available_columns = set(df.columns)
    validate_mapping_quality(mapping, results)

    mapped = mapping[mapping["source_field"].notna() & (mapping["source_field"] != "")]
    required_mapped = mapped[mapped["required"].isin({"yes", "true", "1", "y"})]

    missing_required = [
        row.source_field
        for row in required_mapped.itertuples(index=False)
        if row.source_field not in available_columns
    ]

    if missing_required:
        add_result(
            results,
            "required_source_fields_exist",
            "fail",
            "Missing required source fields: " + ", ".join(missing_required),
            len(missing_required),
        )
    else:
        add_result(
            results,
            "required_source_fields_exist",
            "pass",
            "All required source fields are present.",
            0,
        )

    mapped_existing = mapped[mapped["source_field"].isin(available_columns)]

    for row in mapped_existing.itertuples(index=False):
        source_field = row.source_field
        standard_field = row.standard_field
        expected_type = row.data_type
        is_required = row.required in {"yes", "true", "1", "y"}

        if is_required:
            required_values = df[source_field].replace(r"^\s*$", pd.NA, regex=True)
            missing_count = int(required_values.isna().sum())
            status = "pass" if missing_count == 0 else "warn"
            add_result(
                results,
                f"missing_required_values:{standard_field}",
                status,
                f"Missing values in {source_field}.",
                missing_count,
            )

        if expected_type == "numeric":
            parsed = pd.to_numeric(df[source_field], errors="coerce")
            invalid_count = int(parsed.isna().sum() - df[source_field].isna().sum())
            status = "pass" if invalid_count == 0 else "warn"
            add_result(
                results,
                f"numeric_parseability:{standard_field}",
                status,
                f"Values in {source_field} that cannot be parsed as numeric.",
                invalid_count,
            )

        elif expected_type == "datetime":
            parsed = pd.to_datetime(df[source_field], errors="coerce")
            invalid_count = int(parsed.isna().sum() - df[source_field].isna().sum())
            status = "pass" if invalid_count == 0 else "warn"
            add_result(
                results,
                f"date_parseability:{standard_field}",
                status,
                f"Values in {source_field} that cannot be parsed as dates.",
                invalid_count,
            )

    field_lookup = dict(zip(mapping["standard_field"], mapping["source_field"]))

    quantity_field = field_lookup.get("quantity")
    if quantity_field in available_columns:
        quantity = pd.to_numeric(df[quantity_field], errors="coerce")
        invalid_quantity_count = int((quantity <= 0).sum())
        status = "pass" if invalid_quantity_count == 0 else "warn"
        add_result(
            results,
            "non_positive_quantity_records",
            status,
            f"Rows where {quantity_field} is less than or equal to zero.",
            invalid_quantity_count,
        )

    unit_price_field = field_lookup.get("unit_price")
    if unit_price_field in available_columns:
        unit_price = pd.to_numeric(df[unit_price_field], errors="coerce")
        invalid_price_count = int((unit_price <= 0).sum())
        status = "pass" if invalid_price_count == 0 else "warn"
        add_result(
            results,
            "non_positive_unit_price_records",
            status,
            f"Rows where {unit_price_field} is less than or equal to zero.",
            invalid_price_count,
        )

    duplicate_count = int(df.duplicated().sum())
    status = "pass" if duplicate_count == 0 else "warn"
    add_result(
        results,
        "duplicate_rows",
        status,
        "Exact duplicate rows in the raw file.",
        duplicate_count,
    )

    add_result(
        results,
        "raw_row_count",
        "info",
        "Total rows loaded from the raw file.",
        len(df),
    )

    add_result(
        results,
        "raw_column_count",
        "info",
        "Total columns loaded from the raw file.",
        len(df.columns),
    )

    return pd.DataFrame(results)


def print_summary(report: pd.DataFrame, output_path: Path) -> None:
    status_counts = report["status"].value_counts().to_dict()
    fail_count = status_counts.get("fail", 0)
    warn_count = status_counts.get("warn", 0)

    print("\n===== Sales Data Validation Summary =====")
    print(f"Output report: {output_path}")
    print(f"Checks passed: {status_counts.get('pass', 0)}")
    print(f"Warnings: {warn_count}")
    print(f"Failures: {fail_count}")

    attention = report[report["status"].isin(["fail", "warn"])]
    if not attention.empty:
        print("\nItems to review:")
        for row in attention.itertuples(index=False):
            print(f"- [{row.status.upper()}] {row.check}: {row.row_count} ({row.detail})")
    else:
        print("\nNo failures or warnings detected.")

    if fail_count > 0:
        print("\nValidation result: FAIL. Resolve required schema issues before running the notebooks.")
    elif warn_count > 0:
        print("\nValidation result: PASS WITH WARNINGS. Review data quality issues before running the notebooks.")
    else:
        print("\nValidation result: PASS.")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    mapping_path = Path(args.mapping)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not mapping_path.exists():
        raise FileNotFoundError(f"Schema mapping file not found: {mapping_path}")

    df = load_raw_data(input_path, args.sheet_name)
    mapping = load_mapping(mapping_path)
    report = validate(df, mapping)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)
    print_summary(report, output_path)


if __name__ == "__main__":
    main()
