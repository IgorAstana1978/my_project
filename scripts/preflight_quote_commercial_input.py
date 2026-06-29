"""Preflight a strict commercial quote CSV without creating quote outputs."""

from __future__ import annotations

import argparse
import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DELIMITER = ";"
MAX_ROWS = 100
REQUIRED_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
    "unit_price_kzt",
    "price_includes_vat",
    "price_confirmed_by_igor",
)
REQUIRED_TEXT_COLUMNS = (
    "name",
    "unit",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
POSITIVE_INTEGER_RE = re.compile(r"[1-9][0-9]*\Z")
HEADER_NORMALIZATION_RE = re.compile(r"[^0-9a-zа-я]+")
PASS_NEXT = (
    "commercial input validated for draft preparation only; XLSX generation is "
    "not implemented in this phase; manual Igor check and separate Human Approval "
    "are required before any client-ready use"
)
FAIL_NEXT = "not safe for draft preparation; correct commercial CSV and rerun preflight"


@dataclass
class CommercialPreflightResult:
    input_path: Path
    status: str = "PASS"
    row_count: int = 0
    columns_status: str = "invalid"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "input path": "fail",
            "outside Git": "fail",
            "header": "fail",
            "row count": "fail",
            "required fields": "fail",
            "quantity positive integer": "fail",
            "unit price positive integer": "fail",
            "VAT value": "fail",
            "VAT consistent": "fail",
            "price confirmation": "fail",
            "client-control columns": "fail",
        }
    )
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    next_action: str = FAIL_NEXT


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight a strict commercial quote CSV without creating XLSX output."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to strict commercial semicolon-delimited CSV outside Git",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_failure(result: CommercialPreflightResult, message: str) -> None:
    result.failures.append(message)


def normalized_header(column: str) -> str:
    return HEADER_NORMALIZATION_RE.sub("_", column.casefold()).strip("_")


def is_client_control_column(column: str) -> bool:
    normalized = normalized_header(column)
    english_client_control = any(
        audience in normalized for audience in ("client", "customer")
    ) and any(token in normalized for token in ("ready", "send", "approve"))
    russian_client_control = "клиент" in normalized and any(
        token in normalized for token in ("готов", "отправ", "одобр", "соглас")
    )
    return english_client_control or russian_client_control


def validate_header(
    header: Sequence[str],
    result: CommercialPreflightResult,
) -> bool:
    if not header:
        add_failure(result, "commercial CSV must contain a header row")
        return False

    seen: set[str] = set()
    duplicates: list[str] = []
    for column in header:
        if column == "":
            add_failure(result, "header contains an empty column name")
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)

    if duplicates:
        add_failure(
            result,
            f"header contains duplicate columns: {', '.join(duplicates)}",
        )

    missing = [column for column in REQUIRED_COLUMNS if column not in seen]
    extra = [column for column in header if column not in REQUIRED_COLUMNS]
    if missing:
        add_failure(result, f"header missing columns: {', '.join(missing)}")
    if extra:
        add_failure(result, f"header has unknown or extra columns: {', '.join(extra)}")

    client_control_columns = [
        column for column in header if is_client_control_column(column)
    ]
    if client_control_columns:
        add_failure(result, "forbidden client-control column detected")
        result.checks["client-control columns"] = "fail"
    else:
        result.checks["client-control columns"] = "pass"

    if (
        len(header) == len(REQUIRED_COLUMNS)
        and not missing
        and not extra
        and tuple(header) != REQUIRED_COLUMNS
    ):
        add_failure(result, "header order does not match strict commercial contract")

    header_ok = tuple(header) == REQUIRED_COLUMNS and not duplicates
    if header_ok:
        result.checks["header"] = "pass"
        result.columns_status = "strict 8 columns"
    return header_ok


def validate_positive_integer(value: str) -> bool:
    return POSITIVE_INTEGER_RE.fullmatch(value) is not None


def validate_rows(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    result: CommercialPreflightResult,
) -> None:
    required_ok = True
    quantity_ok = True
    price_ok = True
    vat_value_ok = True
    confirmation_ok = True
    vat_modes: set[str] = set()

    for row_number, values in enumerate(rows, start=2):
        if len(values) != len(header):
            required_ok = False
            quantity_ok = False
            price_ok = False
            vat_value_ok = False
            confirmation_ok = False
            add_failure(result, f"row {row_number}: field count mismatch")
            continue

        row = dict(zip(header, values, strict=True))
        for column in REQUIRED_TEXT_COLUMNS:
            if row[column].strip() == "":
                required_ok = False
                add_failure(result, f"row {row_number}: {column} is required")

        quantity = row["quantity"]
        if quantity == "":
            required_ok = False
            add_failure(result, f"row {row_number}: quantity is required")
        if not validate_positive_integer(quantity):
            quantity_ok = False
            add_failure(
                result,
                f"row {row_number}: quantity must be a positive integer",
            )

        price = row["unit_price_kzt"]
        if price == "":
            required_ok = False
            add_failure(result, f"row {row_number}: unit_price_kzt is required")
        if not validate_positive_integer(price):
            price_ok = False
            add_failure(
                result,
                f"row {row_number}: unit_price_kzt must be a positive integer",
            )

        vat_mode = row["price_includes_vat"]
        if vat_mode not in {"yes", "no"}:
            vat_value_ok = False
            add_failure(
                result,
                f"row {row_number}: price_includes_vat must be exact yes or no",
            )
        else:
            vat_modes.add(vat_mode)

        if row["price_confirmed_by_igor"] != "yes":
            confirmation_ok = False
            add_failure(
                result,
                f"row {row_number}: price_confirmed_by_igor must be exact yes",
            )

    result.checks["required fields"] = "pass" if required_ok else "fail"
    result.checks["quantity positive integer"] = "pass" if quantity_ok else "fail"
    result.checks["unit price positive integer"] = "pass" if price_ok else "fail"
    result.checks["VAT value"] = "pass" if vat_value_ok else "fail"
    result.checks["price confirmation"] = "pass" if confirmation_ok else "fail"

    vat_consistent = vat_value_ok and len(vat_modes) <= 1
    if len(vat_modes) > 1:
        add_failure(result, "price_includes_vat must be consistent across all rows")
    result.checks["VAT consistent"] = "pass" if vat_consistent else "fail"


def load_csv_rows(
    path: Path,
    result: CommercialPreflightResult,
) -> tuple[list[str], list[list[str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=CSV_DELIMITER, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                add_failure(result, "input CSV is empty")
                return [], []
            return header, list(reader)
    except UnicodeDecodeError as error:
        add_failure(result, f"input CSV is not valid UTF-8: {error.reason}")
    except csv.Error:
        add_failure(result, "input CSV is invalid")
    except OSError:
        add_failure(result, "input CSV could not be read")
    return [], []


def preflight(input_csv: Path) -> CommercialPreflightResult:
    input_path = resolved(input_csv)
    result = CommercialPreflightResult(input_path=input_path)

    if input_path.is_file():
        result.checks["input path"] = "pass"
    else:
        add_failure(result, f"input path does not exist: {input_path}")

    if input_path.suffix.casefold() != ".csv":
        add_failure(result, "input suffix must be .csv")

    if is_inside_project(input_path):
        add_failure(result, "input CSV must be outside the Git project")
    else:
        result.checks["outside Git"] = "pass"

    if result.checks["input path"] != "pass":
        finalize_status(result)
        return result

    header, rows = load_csv_rows(input_path, result)
    header_ok = validate_header(header, result)
    result.row_count = len(rows)

    if 1 <= result.row_count <= MAX_ROWS:
        result.checks["row count"] = "pass"
    else:
        add_failure(result, f"row count must be 1-{MAX_ROWS}")

    if header_ok:
        validate_rows(header, rows, result)

    finalize_status(result)
    return result


def finalize_status(result: CommercialPreflightResult) -> None:
    if result.failures:
        result.status = "FAIL"
        result.next_action = FAIL_NEXT
    else:
        result.status = "PASS"
        result.next_action = PASS_NEXT


def format_list(values: Sequence[str]) -> list[str]:
    if not values:
        return ["none"]
    return list(values)


def format_report(result: CommercialPreflightResult) -> str:
    lines = [
        "COMMERCIAL_QUOTE_INPUT_PREFLIGHT_REPORT_START",
        "",
        "Input:",
        str(result.input_path),
        "",
        "Status:",
        result.status,
        "",
        "Rows:",
        str(result.row_count),
        "",
        "Columns:",
        result.columns_status,
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(["", "Warnings:"])
    lines.extend(format_list(result.warnings))
    lines.extend(["", "Failures:"])
    lines.extend(format_list(result.failures))
    lines.extend(
        [
            "",
            "Next:",
            result.next_action,
            "",
            "Manual Igor check:",
            "required",
            "",
            "COMMERCIAL_QUOTE_INPUT_PREFLIGHT_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = preflight(args.input)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
