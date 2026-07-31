from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT_PATH = Path("data/raw/Online Retail.xlsx")
DEFAULT_MAPPING_PATH = Path("config/schema_mapping_template.csv")
DEFAULT_OUTPUT_PATH = Path("data/interim/standardized_sales.csv")

STANDARD_FIELDS = [
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]
REQUIRED_STANDARD_FIELDS = {
    "invoice_no",
    "stock_code",
    "quantity",
    "invoice_date",
    "unit_price",
}
OPTIONAL_STANDARD_FIELDS = {"description", "customer_id", "country"}
IDENTIFIER_FIELDS = {"invoice_no", "stock_code", "customer_id"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standardize raw sales data using the schema mapping template."
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
        help="Path for standardized sales CSV.",
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
        return pd.read_csv(path, dtype=object)
    if suffix in {".xlsx", ".xls"}:
        if sheet_name:
            return pd.read_excel(path, sheet_name=sheet_name, dtype=object)
        return pd.read_excel(path, dtype=object)

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


def validate_required_mapping(mapping: pd.DataFrame, raw_columns: set[str]) -> None:
    duplicate_standard_fields = sorted(
        mapping.loc[
            mapping["standard_field"].ne("")
            & mapping["standard_field"].duplicated(keep=False),
            "standard_field",
        ].unique()
    )
    if duplicate_standard_fields:
        raise ValueError(
            "Duplicate standard_field values in mapping file: "
            + ", ".join(duplicate_standard_fields)
        )

    duplicate_source_fields = sorted(
        mapping.loc[
            mapping["source_field"].ne("")
            & mapping["source_field"].duplicated(keep=False),
            "source_field",
        ].unique()
    )
    if duplicate_source_fields:
        raise ValueError(
            "Duplicate non-blank source_field values in mapping file: "
            + ", ".join(duplicate_source_fields)
        )

    standard_fields = set(mapping["standard_field"])
    missing_standard_fields = sorted(REQUIRED_STANDARD_FIELDS - standard_fields)
    if missing_standard_fields:
        raise ValueError(
            "Required standard fields missing from mapping file: "
            + ", ".join(missing_standard_fields)
        )

    required_rows = mapping[mapping["standard_field"].isin(REQUIRED_STANDARD_FIELDS)]
    blank_required = sorted(
        required_rows.loc[required_rows["source_field"] == "", "standard_field"].tolist()
    )
    if blank_required:
        raise ValueError(
            "Required standard fields with blank source_field: "
            + ", ".join(blank_required)
        )

    missing_source_fields = sorted(
        row.source_field
        for row in required_rows.itertuples(index=False)
        if row.source_field not in raw_columns
    )
    if missing_source_fields:
        raise ValueError(
            "Required source fields missing from raw data: "
            + ", ".join(missing_source_fields)
        )


def count_parse_failures(original: pd.Series, converted: pd.Series) -> int:
    original_text = original.astype("string").str.strip()
    original_non_missing = original_text.notna() & original_text.ne("")
    return int((original_non_missing & converted.isna()).sum())


def format_identifier(value: object) -> object:
    if pd.isna(value):
        return pd.NA

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def standardize_sales(raw_data: pd.DataFrame, mapping: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    raw_data = raw_data.copy()
    raw_data.columns = [str(column).strip() for column in raw_data.columns]
    raw_columns = set(raw_data.columns)

    validate_required_mapping(mapping, raw_columns)

    mapped_rows = mapping[
        mapping["standard_field"].isin(STANDARD_FIELDS)
        & mapping["source_field"].ne("")
        & mapping["source_field"].isin(raw_columns)
    ]

    rename_map = dict(zip(mapped_rows["source_field"], mapped_rows["standard_field"]))
    standardized = raw_data[list(rename_map.keys())].rename(columns=rename_map)
    ordered_columns = [field for field in STANDARD_FIELDS if field in standardized.columns]
    standardized = standardized[ordered_columns]

    for field in IDENTIFIER_FIELDS:
        if field in standardized.columns:
            standardized[field] = standardized[field].map(format_identifier).astype("string")

    conversion_diagnostics: dict[str, int] = {}

    original_quantity = standardized["quantity"].copy()
    standardized["quantity"] = pd.to_numeric(standardized["quantity"], errors="coerce")
    conversion_diagnostics["quantity_parse_failures"] = count_parse_failures(
        original_quantity,
        standardized["quantity"],
    )

    original_unit_price = standardized["unit_price"].copy()
    standardized["unit_price"] = pd.to_numeric(standardized["unit_price"], errors="coerce")
    conversion_diagnostics["unit_price_parse_failures"] = count_parse_failures(
        original_unit_price,
        standardized["unit_price"],
    )

    original_invoice_date = standardized["invoice_date"].copy()
    standardized["invoice_date"] = pd.to_datetime(
        standardized["invoice_date"],
        errors="coerce",
    )
    conversion_diagnostics["invoice_date_parse_failures"] = count_parse_failures(
        original_invoice_date,
        standardized["invoice_date"],
    )

    return standardized, conversion_diagnostics


def print_summary(
    standardized: pd.DataFrame,
    output_path: Path,
    required_included: list[str],
    optional_included: list[str],
    conversion_diagnostics: dict[str, int],
) -> None:
    print("\n===== Sales Data Standardization Summary =====")
    print(f"Rows processed: {len(standardized):,}")
    print(f"Columns standardized: {len(standardized.columns)}")
    print("Required fields included: " + ", ".join(required_included))
    if optional_included:
        print("Optional fields included: " + ", ".join(optional_included))
    else:
        print("Optional fields included: none")
    print("Conversion diagnostics:")
    for check, count in conversion_diagnostics.items():
        print(f"  - {check}: {count:,}")
    print(f"Output path: {output_path}")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    mapping_path = Path(args.mapping)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not mapping_path.exists():
        raise FileNotFoundError(f"Schema mapping file not found: {mapping_path}")

    raw_data = load_raw_data(input_path, args.sheet_name)
    mapping = load_mapping(mapping_path)
    standardized, conversion_diagnostics = standardize_sales(raw_data, mapping)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    standardized.to_csv(output_path, index=False)

    required_included = [field for field in STANDARD_FIELDS if field in REQUIRED_STANDARD_FIELDS]
    optional_included = [field for field in STANDARD_FIELDS if field in OPTIONAL_STANDARD_FIELDS and field in standardized.columns]
    print_summary(
        standardized,
        output_path,
        required_included,
        optional_included,
        conversion_diagnostics,
    )


if __name__ == "__main__":
    main()
