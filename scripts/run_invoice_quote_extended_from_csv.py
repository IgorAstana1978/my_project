"""Build a fixed-layout isolated extended writer job from strict items CSV."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ITEMS_BRIDGE_SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py"
)
CSV_DELIMITER = ";"
TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory

REQUIRED_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
REQUIRED_COLUMN_SET = set(REQUIRED_COLUMNS)
FORBIDDEN_COMMERCIAL_COLUMNS = {
    "amount",
    "currency",
    "discount",
    "price",
    "price_confirmed_by_igor",
    "price_kzt",
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


class CsvItemsError(Exception):
    """Expected CSV adapter preflight or validation error."""


def fail(message: str) -> None:
    raise CsvItemsError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated extended invoice-quote writer from strict items CSV."
        )
    )
    parser.add_argument(
        "--items-csv",
        required=True,
        type=Path,
        help="Path to strict semicolon-delimited items CSV",
    )
    parser.add_argument("--template", required=True, type=Path, help="Path to .xlsx")
    parser.add_argument(
        "--template-capacity",
        required=True,
        type=int,
        help="Prepared template item-row capacity",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output .xlsx path")
    return parser.parse_args(argv)


def validate_template_capacity(capacity: Any) -> int:
    if not isinstance(capacity, int) or isinstance(capacity, bool):
        fail("template_capacity must be a positive integer")
    if capacity < 1:
        fail(f"template_capacity must be positive: {capacity}")
    return capacity


def validate_header(header: Sequence[str]) -> None:
    if not header:
        fail("items CSV must contain a header row")

    seen: set[str] = set()
    duplicates: list[str] = []
    for column in header:
        if column == "":
            fail("items CSV contains an empty column name")
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        fail(f"items CSV contains duplicate columns: {', '.join(duplicates)}")

    forbidden = [column for column in header if column in FORBIDDEN_COMMERCIAL_COLUMNS]
    if forbidden:
        fail(f"items CSV contains forbidden commercial columns: {', '.join(forbidden)}")

    unknown = [column for column in header if column not in REQUIRED_COLUMN_SET]
    if unknown:
        fail(f"items CSV contains unknown columns: {', '.join(unknown)}")

    missing = [column for column in REQUIRED_COLUMNS if column not in seen]
    if missing:
        fail(f"items CSV is missing required columns: {', '.join(missing)}")


def required_value(row: Mapping[str, str], column: str, row_number: int) -> str:
    value = row[column]
    if value.strip() == "":
        fail(f"items CSV row {row_number}.{column} is required")
    return value


def parse_quantity(value: str, row_number: int) -> int:
    try:
        return int(value, 10)
    except ValueError:
        fail(f"items CSV row {row_number}.quantity must be an integer")


def item_from_row(row: Mapping[str, str], row_number: int) -> dict[str, Any]:
    return {
        "name": required_value(row, "name", row_number),
        "unit": required_value(row, "unit", row_number),
        "quantity": parse_quantity(
            required_value(row, "quantity", row_number),
            row_number,
        ),
        "instruments_and_devices": required_value(
            row,
            "instruments_and_devices",
            row_number,
        ),
        "cabinet_type_dimensions_material": required_value(
            row,
            "cabinet_type_dimensions_material",
            row_number,
        ),
        "price_kzt": None,
        "price_confirmed_by_igor": False,
    }


def load_items_csv(path: Path, capacity: int) -> dict[str, list[dict[str, Any]]]:
    csv_path = path.expanduser().resolve(strict=False)
    if not csv_path.is_file():
        fail(f"items CSV does not exist: {csv_path}")

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file, delimiter=CSV_DELIMITER, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                fail("items CSV must not be empty")

            validate_header(header)
            items: list[dict[str, Any]] = []
            for row_number, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    fail(
                        "items CSV row "
                        f"{row_number} has {len(values)} fields; expected {len(header)}"
                    )
                row = dict(zip(header, values, strict=True))
                items.append(item_from_row(row, row_number))
                if len(items) > capacity:
                    fail(
                        f"items count {len(items)} exceeds template capacity {capacity}"
                    )
    except UnicodeDecodeError as error:
        fail(f"items CSV is not valid UTF-8: {error.reason}")
    except csv.Error as error:
        fail(f"items CSV is invalid: {error}")

    if not items:
        fail("items CSV must contain at least one item")
    return {"items": items}


def write_items_json(path: Path, items_data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(items_data, ensure_ascii=False), encoding="utf-8")


def run_items_bridge(
    items_json: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ITEMS_BRIDGE_SCRIPT),
            "--items-json",
            str(items_json),
            "--template",
            str(template),
            "--template-capacity",
            str(capacity),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def forward_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        capacity = validate_template_capacity(args.template_capacity)
        items_data = load_items_csv(args.items_csv, capacity)
    except CsvItemsError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    with TEMPORARY_DIRECTORY(prefix="invoice_quote_extended_csv_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        items_json = temp_dir / "items.json"
        write_items_json(items_json, items_data)
        result = run_items_bridge(
            items_json=items_json,
            template=args.template,
            capacity=capacity,
            output=args.output,
        )

    forward_output(result)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
