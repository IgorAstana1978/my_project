"""Extract strict invoice quote items CSV from a legacy .xls workbook."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DELIMITER = ";"
MAX_ITEM_ROWS = 100
OUTPUT_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
TEXT_COLUMNS = tuple(column for column in OUTPUT_COLUMNS if column != "quantity")
WHITESPACE_RE = re.compile(r"[ \t\r\n\f\v]+")
NON_WORD_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)

HEADER_ALIASES: Mapping[str, frozenset[str]] = {
    "name": frozenset(
        {
            "name",
            "item",
            "description",
            "наименование",
            "наименование позиции",
            "наименование товара",
            "наименование товаров",
            "наименование работ",
            "наименование услуг",
            "товар",
            "товары работы услуги",
            "номенклатура",
            "описание",
        }
    ),
    "unit": frozenset(
        {
            "unit",
            "uom",
            "ед",
            "ед изм",
            "единица измерения",
            "единицы измерения",
        }
    ),
    "quantity": frozenset(
        {
            "quantity",
            "qty",
            "количество",
            "кол во",
            "количество шт",
        }
    ),
    "instruments_and_devices": frozenset(
        {
            "instruments and devices",
            "instruments devices",
            "instruments_and_devices",
            "приборы и аппараты",
            "приборы аппараты",
            "приборы",
            "аппараты",
            "комплектующие",
            "приборы и аппараты комплектующие",
        }
    ),
    "cabinet_type_dimensions_material": frozenset(
        {
            "cabinet type dimensions material",
            "cabinet_type_dimensions_material",
            "тип шкафа габариты материал",
            "тип шкафа",
            "габариты",
            "материал",
            "шкаф",
            "тип габариты материал",
        }
    ),
}

COMMERCIAL_HEADER_TOKENS = frozenset(
    {
        "amount",
        "bank",
        "currency",
        "discount",
        "nds",
        "payment",
        "price",
        "sum",
        "term",
        "total",
        "vat",
        "валюта",
        "всего",
        "договор",
        "итого",
        "комментарий",
        "ндс",
        "оплата",
        "поставка",
        "примечание",
        "прописью",
        "реквизиты",
        "скидка",
        "срок",
        "стоимость",
        "сумма",
        "условия",
        "цена",
    }
)

COMMERCIAL_ROW_TOKENS = COMMERCIAL_HEADER_TOKENS | frozenset(
    {
        "бик",
        "бин",
        "ибан",
        "кбе",
        "р/с",
        "расчетный счет",
    }
)


class LegacyXlsExtractionError(Exception):
    """Expected legacy .xls extraction preflight or validation error."""


@dataclass(frozen=True)
class SheetMatrix:
    name: str
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class HeaderCandidate:
    sheet_name: str
    row_index: int
    columns: Mapping[str, int]


def fail(message: str) -> None:
    raise LegacyXlsExtractionError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract strict invoice quote items CSV from a legacy .xls file."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to source legacy .xls invoice/quote file",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path for strict output items CSV outside the Git project",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_input_path(path: Path) -> Path:
    input_path = resolved(path)
    if input_path.suffix.casefold() != ".xls":
        fail(f"input file must be a legacy .xls file: {input_path}")
    if not input_path.is_file():
        fail(f"input .xls does not exist: {input_path}")
    return input_path


def validate_output_path(path: Path, input_path: Path) -> Path:
    output_path = resolved(path)
    if output_path.suffix.casefold() != ".csv":
        fail(f"output file must be a CSV file: {output_path}")
    if output_path.exists():
        fail(f"output CSV already exists: {output_path}")
    if is_inside_project(output_path):
        fail(f"output CSV must be outside the Git project: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output CSV parent directory does not exist: {output_path.parent}")
    if output_path == input_path:
        fail("output CSV must not overwrite the source .xls")
    return output_path


def compact_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return WHITESPACE_RE.sub(" ", str(value)).strip()


def normalize_header(value: object) -> str:
    text = compact_text(value).casefold().replace("ё", "е")
    text = NON_WORD_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def has_commercial_token(normalized: str) -> bool:
    padded = f" {normalized} "
    return any(f" {token} " in padded for token in COMMERCIAL_HEADER_TOKENS)


def has_commercial_text(row: Sequence[str]) -> bool:
    normalized = normalize_header(" ".join(row))
    padded = f" {normalized} "
    return any(f" {token} " in padded for token in COMMERCIAL_ROW_TOKENS)


def output_column_for_header(value: object) -> str | None:
    normalized = normalize_header(value)
    if not normalized:
        return None
    if has_commercial_token(normalized):
        return None

    for column, aliases in HEADER_ALIASES.items():
        if normalized in aliases:
            return column
    return None


def row_value(row: Sequence[str], index: int) -> str:
    if index >= len(row):
        return ""
    return compact_text(row[index])


def find_header_candidates(sheets: Sequence[SheetMatrix]) -> list[HeaderCandidate]:
    candidates: list[HeaderCandidate] = []
    for sheet in sheets:
        for row_index, row in enumerate(sheet.rows):
            columns: dict[str, int] = {}
            duplicates: list[str] = []
            for column_index, value in enumerate(row):
                output_column = output_column_for_header(value)
                if output_column is None:
                    continue
                if output_column in columns and output_column not in duplicates:
                    duplicates.append(output_column)
                columns[output_column] = column_index

            if duplicates:
                fail(
                    "ambiguous layout: duplicate item headers in "
                    f"{sheet.name} row {row_index + 1}: {', '.join(duplicates)}"
                )
            if all(column in columns for column in OUTPUT_COLUMNS):
                candidates.append(
                    HeaderCandidate(
                        sheet_name=sheet.name,
                        row_index=row_index,
                        columns=columns,
                    )
                )
    return candidates


def best_missing_headers(sheets: Sequence[SheetMatrix]) -> list[str]:
    best: set[str] = set()
    for sheet in sheets:
        for row in sheet.rows:
            found = {
                output_column
                for value in row
                if (output_column := output_column_for_header(value)) is not None
            }
            if len(found) > len(best):
                best = found
    return [column for column in OUTPUT_COLUMNS if column not in best]


def select_item_table(
    sheets: Sequence[SheetMatrix],
) -> tuple[SheetMatrix, HeaderCandidate]:
    candidates = find_header_candidates(sheets)
    if not candidates:
        missing = best_missing_headers(sheets)
        if missing:
            fail(f"missing required headers: {', '.join(missing)}")
        fail("missing required headers")
    if len(candidates) > 1:
        locations = [
            f"{candidate.sheet_name} row {candidate.row_index + 1}"
            for candidate in candidates
        ]
        fail(f"multiple plausible item tables detected: {', '.join(locations)}")

    candidate = candidates[0]
    for sheet in sheets:
        if sheet.name == candidate.sheet_name:
            return sheet, candidate
    fail("internal error: selected sheet not found")


def parse_quantity(value: str, row_number: int) -> str:
    try:
        int(value, 10)
    except ValueError:
        fail(f"row {row_number}.quantity must be an integer")
    return value


def item_from_row(
    row: Sequence[str],
    columns: Mapping[str, int],
    row_number: int,
) -> dict[str, str] | None:
    values = {column: row_value(row, columns[column]) for column in OUTPUT_COLUMNS}
    if all(value == "" for value in values.values()):
        return None
    if has_commercial_text(row) and values["name"] == "":
        return None

    for column in TEXT_COLUMNS:
        if values[column] == "":
            fail(
                "shifted layout or incomplete item row "
                f"{row_number}: {column} is required"
            )
    if values["quantity"] == "":
        fail(
            "shifted layout or incomplete item row "
            f"{row_number}: quantity is required"
        )
    values["quantity"] = parse_quantity(values["quantity"], row_number)
    return {column: values[column] for column in OUTPUT_COLUMNS}


def extract_items_from_matrices(
    sheets: Sequence[SheetMatrix],
) -> list[dict[str, str]]:
    if not sheets:
        fail("workbook contains no sheets")

    sheet, header = select_item_table(sheets)
    items: list[dict[str, str]] = []
    item_rows = sheet.rows[header.row_index + 1 :]
    for row_index, row in enumerate(item_rows, start=header.row_index + 2):
        if has_commercial_text(row) and row_value(row, header.columns["name"]):
            break
        item = item_from_row(row, header.columns, row_index)
        if item is None:
            continue
        items.append(item)
        if len(items) > MAX_ITEM_ROWS:
            fail(f"item row count exceeds {MAX_ITEM_ROWS}")

    if not items:
        fail("no item rows found")
    return items


def read_legacy_xls_matrices(path: Path) -> list[SheetMatrix]:
    try:
        import xlrd  # type: ignore[import-not-found]
    except ImportError:
        fail("xlrd>=2.0,<3 is required to read legacy .xls files")

    try:
        workbook = xlrd.open_workbook(str(path), on_demand=True)
    except Exception as error:  # pragma: no cover - xlrd error types vary.
        fail(f"failed to read legacy .xls file: {error}")

    sheets: list[SheetMatrix] = []
    try:
        for sheet in workbook.sheets():
            rows = tuple(
                tuple(
                    compact_text(sheet.cell_value(row_index, column_index))
                    for column_index in range(sheet.ncols)
                )
                for row_index in range(sheet.nrows)
            )
            sheets.append(SheetMatrix(name=sheet.name, rows=rows))
    finally:
        workbook.release_resources()
    return sheets


def write_strict_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            encoding="utf-8",
            newline="",
            prefix=f"{path.name}.",
            suffix=".tmp",
        ) as csv_file:
            temp_name = csv_file.name
            writer = csv.DictWriter(
                csv_file,
                fieldnames=OUTPUT_COLUMNS,
                delimiter=CSV_DELIMITER,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        Path(temp_name).replace(path)
    except Exception:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def extract_legacy_xls_items_to_csv(input_xls: Path, output_csv: Path) -> Path:
    input_path = validate_input_path(input_xls)
    output_path = validate_output_path(output_csv, input_path)
    sheets = read_legacy_xls_matrices(input_path)
    rows = extract_items_from_matrices(sheets)
    write_strict_csv(output_path, rows)
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = extract_legacy_xls_items_to_csv(args.input, args.output)
    except LegacyXlsExtractionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"CREATED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
