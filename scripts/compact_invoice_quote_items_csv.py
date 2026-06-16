"""Create a compact strict items CSV for invoice quote drafts."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DELIMITER = ";"
REQUIRED_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
TEXT_COLUMNS = tuple(column for column in REQUIRED_COLUMNS if column != "quantity")
FORBIDDEN_COMMERCIAL_COLUMNS = {
    "amount",
    "currency",
    "discount",
    "price",
    "price_confirmed_by_igor",
    "price_kzt",
    "sum",
    "term",
    "total",
    "unit_price",
    "vat",
    "валюта",
    "итого",
    "ндс",
    "скидка",
    "срок",
    "стоимость",
    "сумма",
    "цена",
}
WHITESPACE_RE = re.compile(r"[ \t\r\n\f\v]+")


class CompactCsvError(Exception):
    """Expected CSV compaction preflight or validation error."""


def fail(message: str) -> None:
    raise CompactCsvError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compact a strict semicolon-delimited invoice quote items CSV."
    )
    parser.add_argument(
        "--input-csv",
        required=True,
        type=Path,
        help="Path to strict input items CSV",
    )
    parser.add_argument(
        "--output-csv",
        required=True,
        type=Path,
        help="Path for compact output CSV outside the Git project",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_output_path(path: Path) -> Path:
    output_path = resolved(path)
    if output_path.exists():
        fail(f"output CSV already exists: {output_path}")
    if is_inside_project(output_path):
        fail(f"output CSV must be outside the Git project: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output CSV parent directory does not exist: {output_path.parent}")
    return output_path


def validate_header(header: Sequence[str]) -> None:
    if not header:
        fail("items CSV must contain a header row")
    for column in header:
        if column == "":
            fail("items CSV contains an empty column name")

    seen: set[str] = set()
    duplicates: list[str] = []
    for column in header:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        fail(f"items CSV contains duplicate columns: {', '.join(duplicates)}")

    forbidden = [column for column in header if column in FORBIDDEN_COMMERCIAL_COLUMNS]
    if forbidden:
        fail(f"items CSV contains forbidden commercial columns: {', '.join(forbidden)}")

    required_set = set(REQUIRED_COLUMNS)
    unknown = [column for column in header if column not in required_set]
    if unknown:
        fail(f"items CSV contains unknown columns: {', '.join(unknown)}")

    if tuple(header) != REQUIRED_COLUMNS:
        fail("items CSV header must exactly match the required columns")


def compact_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()


def required_value(row: Mapping[str, str], column: str, row_number: int) -> str:
    value = row[column]
    if value.strip() == "":
        fail(f"items CSV row {row_number}.{column} is required")
    return value


def compact_required_text(
    row: Mapping[str, str],
    column: str,
    row_number: int,
) -> str:
    value = compact_text(required_value(row, column, row_number))
    if value == "":
        fail(f"items CSV row {row_number}.{column} is required")
    return value


def compact_quantity(row: Mapping[str, str], row_number: int) -> str:
    value = required_value(row, "quantity", row_number).strip()
    try:
        int(value, 10)
    except ValueError:
        fail(f"items CSV row {row_number}.quantity must be an integer")
    return value


def compact_row(row: Mapping[str, str], row_number: int) -> dict[str, str]:
    compacted = {
        column: compact_required_text(row, column, row_number)
        for column in TEXT_COLUMNS
    }
    compacted["quantity"] = compact_quantity(row, row_number)
    return {column: compacted[column] for column in REQUIRED_COLUMNS}


def load_compact_rows(path: Path) -> list[dict[str, str]]:
    input_path = resolved(path)
    if not input_path.is_file():
        fail(f"input CSV does not exist: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=CSV_DELIMITER, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                fail("items CSV must not be empty")

            validate_header(header)
            rows: list[dict[str, str]] = []
            for row_number, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    fail(
                        "items CSV row "
                        f"{row_number} has {len(values)} fields; expected {len(header)}"
                    )
                row = dict(zip(header, values, strict=True))
                rows.append(compact_row(row, row_number))
    except UnicodeDecodeError as error:
        fail(f"items CSV is not valid UTF-8: {error.reason}")
    except csv.Error as error:
        fail(f"items CSV is invalid: {error}")

    if not rows:
        fail("items CSV must contain at least one item")
    return rows


def write_compact_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=REQUIRED_COLUMNS,
            delimiter=CSV_DELIMITER,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def compact_csv(input_csv: Path, output_csv: Path) -> Path:
    output_path = validate_output_path(output_csv)
    rows = load_compact_rows(input_csv)
    write_compact_csv(output_path, rows)
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = compact_csv(args.input_csv, args.output_csv)
    except CompactCsvError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"CREATED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
