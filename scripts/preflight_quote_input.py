"""Preflight a strict quote input CSV without creating quote outputs."""

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
)
OPTIONAL_COLUMNS = (
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
COMMERCIAL_TOKENS = (
    "price",
    "сумма",
    "цена",
    "ндс",
    "vat",
    "итого",
    "всего прописью",
    "payment",
    "условия оплаты",
    "условия поставки",
    "bank",
    "банковские реквизиты",
    "currency",
    "валюта",
)
WHITESPACE_RE = re.compile(r"[ \t\r\n\f\v]+")


@dataclass
class PreflightResult:
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
            "quantity integer": "fail",
            "required fields": "fail",
            "commercial data scan": "fail",
            "draft output": "skip",
        }
    )
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    next_action: str = "not safe to run"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight a strict items CSV before quote generation."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to strict semicolon-delimited items CSV outside Git",
    )
    parser.add_argument(
        "--draft-output",
        type=Path,
        help="Optional draft .xlsx path for the recommended next command",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def compact_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()


def normalized(value: str) -> str:
    return compact_text(value).casefold().replace("ё", "е")


def has_commercial_token(value: str) -> bool:
    text = normalized(value)
    return any(token in text for token in COMMERCIAL_TOKENS)


def add_failure(result: PreflightResult, message: str) -> None:
    result.failures.append(message)


def add_warning(result: PreflightResult, message: str) -> None:
    result.warnings.append(message)


def validate_header(header: Sequence[str], result: PreflightResult) -> None:
    if tuple(header) == REQUIRED_COLUMNS:
        result.checks["header"] = "pass"
        result.checks["commercial data scan"] = "pass"
        result.columns_status = "strict 5 columns"
        return

    result.checks["header"] = "fail"
    result.columns_status = "invalid"
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    extra = [column for column in header if column not in REQUIRED_COLUMNS]
    if missing:
        add_failure(result, f"header missing columns: {', '.join(missing)}")
    if extra:
        add_failure(result, f"header has extra columns: {', '.join(extra)}")
    if len(header) == len(REQUIRED_COLUMNS) and not missing and not extra:
        add_failure(result, "header order does not match strict CSV contract")
    commercial = [column for column in header if has_commercial_token(column)]
    if commercial:
        result.checks["commercial data scan"] = "fail"
        add_failure(result, "commercial column detected in header")


def validate_rows(
    header: Sequence[str],
    rows: Sequence[Sequence[str]],
    result: PreflightResult,
) -> None:
    quantity_ok = True
    required_ok = True
    commercial_ok = result.checks["commercial data scan"] != "fail"
    for row_index, row in enumerate(rows, start=2):
        if len(row) != len(header):
            required_ok = False
            add_failure(result, f"row {row_index}: field count mismatch")
            continue

        row_by_column = dict(zip(header, row, strict=True))
        for column in ("name", "unit", "quantity"):
            if compact_text(row_by_column.get(column, "")) == "":
                required_ok = False
                add_failure(result, f"row {row_index}: {column} is required")

        quantity = compact_text(row_by_column.get("quantity", ""))
        if quantity:
            try:
                int(quantity, 10)
            except ValueError:
                quantity_ok = False
                add_failure(result, f"row {row_index}: quantity must be an integer")

        for column in OPTIONAL_COLUMNS:
            if compact_text(row_by_column.get(column, "")) == "":
                add_warning(result, f"row {row_index}: {column} is empty")

        for column, value in row_by_column.items():
            if has_commercial_token(value):
                commercial_ok = False
                add_failure(
                    result,
                    f"row {row_index}: commercial token detected in {column}",
                )

    result.checks["quantity integer"] = "pass" if quantity_ok else "fail"
    result.checks["required fields"] = "pass" if required_ok else "fail"
    result.checks["commercial data scan"] = "pass" if commercial_ok else "fail"


def load_csv_rows(
    path: Path,
    result: PreflightResult,
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
    except csv.Error as error:
        add_failure(result, f"input CSV is invalid: {error}")
    return [], []


def preflight(input_csv: Path, draft_output: Path | None = None) -> PreflightResult:
    input_path = resolved(input_csv)
    result = PreflightResult(input_path=input_path)

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

    validate_draft_output(input_path, draft_output, result)

    if result.checks["input path"] != "pass":
        finalize_status(result, draft_output)
        return result

    header, rows = load_csv_rows(input_path, result)
    validate_header(header, result)
    result.row_count = len(rows)

    if 1 <= result.row_count <= MAX_ROWS:
        result.checks["row count"] = "pass"
    else:
        add_failure(result, f"row count must be 1-{MAX_ROWS}")

    if tuple(header) == REQUIRED_COLUMNS:
        validate_rows(header, rows, result)
    else:
        result.checks["quantity integer"] = "fail"
        result.checks["required fields"] = "fail"
        if result.checks["commercial data scan"] != "fail":
            result.checks["commercial data scan"] = "fail"

    finalize_status(result, draft_output)
    return result


def validate_draft_output(
    input_path: Path,
    draft_output: Path | None,
    result: PreflightResult,
) -> None:
    if draft_output is None:
        result.checks["draft output"] = "skip"
        return

    output_path = resolved(draft_output)
    output_ok = True
    if output_path.suffix.casefold() != ".xlsx":
        output_ok = False
        add_failure(result, "draft output suffix must be .xlsx")
    if is_inside_project(output_path):
        output_ok = False
        add_failure(result, "draft output must be outside the Git project")
    if not output_path.parent.is_dir():
        output_ok = False
        add_failure(result, "draft output parent directory does not exist")
    if output_path.exists():
        output_ok = False
        add_failure(result, "draft output file already exists")
    if output_path == input_path:
        output_ok = False
        add_failure(result, "draft output must not equal input CSV path")
    result.checks["draft output"] = "pass" if output_ok else "fail"


def recommended_command(input_path: Path, draft_output: Path | None) -> str:
    if draft_output is None:
        return "safe to run make_quote_capacity100.ps1"
    return (
        "safe to run make_quote_capacity100.ps1\n"
        f'.\\scripts\\make_quote_capacity100.ps1 "{input_path}" '
        f'"{resolved(draft_output)}"'
    )


def finalize_status(result: PreflightResult, draft_output: Path | None) -> None:
    if result.failures:
        result.status = "FAIL"
        result.next_action = "not safe to run"
    elif result.warnings:
        result.status = "WARN"
        result.next_action = recommended_command(result.input_path, draft_output)
    else:
        result.status = "PASS"
        result.next_action = recommended_command(result.input_path, draft_output)


def format_list(values: Sequence[str]) -> list[str]:
    if not values:
        return ["none"]
    return list(values)


def format_report(result: PreflightResult) -> str:
    lines = [
        "QUOTE_INPUT_PREFLIGHT_REPORT_START",
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
        f"input path: {result.checks['input path']}",
        f"outside Git: {result.checks['outside Git']}",
        f"header: {result.checks['header']}",
        f"row count: {result.checks['row count']}",
        f"quantity integer: {result.checks['quantity integer']}",
        f"required fields: {result.checks['required fields']}",
        f"commercial data scan: {result.checks['commercial data scan']}",
        f"draft output: {result.checks['draft output']}",
        "",
        "Warnings:",
    ]
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
            "QUOTE_INPUT_PREFLIGHT_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = preflight(args.input, args.draft_output)
    print(format_report(result))
    return 1 if result.status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
