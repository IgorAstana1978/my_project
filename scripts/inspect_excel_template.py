"""Read-only inspector for Excel templates stored as OOXML workbooks."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, ParseError, fromstring
from zipfile import BadZipFile, ZipFile

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": SPREADSHEET_NS, "rel": RELATIONSHIP_NS}

WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
SHARED_STRINGS_PART = "xl/sharedStrings.xml"
MAX_PREVIEW_CELLS = 10
CELL_RE = re.compile(r"^\$?([A-Z]+)\$?(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class CellPreview:
    address: str
    value: str


@dataclass(frozen=True)
class WorksheetInspection:
    name: str
    rows: int
    columns: int
    merged_cells: tuple[str, ...]
    formula_cells: tuple[CellPreview, ...]
    preview_cells: tuple[CellPreview, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an Excel template without modifying it."
    )
    parser.add_argument("excel_file", type=Path, help="Path to an Excel workbook.")
    return parser.parse_args(argv)


def read_xml_part(archive: ZipFile, part_name: str) -> Element:
    return fromstring(archive.read(part_name))


def column_number(column: str) -> int:
    result = 0
    for letter in column.upper():
        result = result * 26 + ord(letter) - ord("A") + 1
    return result


def cell_position(address: str) -> tuple[int, int] | None:
    match = CELL_RE.match(address)
    if match is None:
        return None
    return int(match.group(2)), column_number(match.group(1))


def range_size(reference: str) -> tuple[int, int] | None:
    cells = reference.split(":")
    start = cell_position(cells[0])
    end = cell_position(cells[-1])
    if start is None or end is None:
        return None
    rows = max(start[0], end[0])
    columns = max(start[1], end[1])
    return rows, columns


def normalize_workbook_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def load_shared_strings(archive: ZipFile) -> tuple[str, ...]:
    try:
        root = read_xml_part(archive, SHARED_STRINGS_PART)
    except KeyError:
        return ()

    strings: list[str] = []
    for item in root.findall("main:si", NS):
        strings.append(
            "".join(node.text or "" for node in item.findall(".//main:t", NS))
        )
    return tuple(strings)


def workbook_sheets(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = read_xml_part(archive, WORKBOOK_PART)
    relationships = read_xml_part(archive, WORKBOOK_RELS_PART)
    targets = {
        relationship.get("Id"): normalize_workbook_target(
            relationship.get("Target", "")
        )
        for relationship in relationships.findall(
            f"{{{PACKAGE_RELATIONSHIP_NS}}}Relationship"
        )
    }

    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        relationship_id = sheet.get(f"{{{RELATIONSHIP_NS}}}id")
        target = targets.get(relationship_id)
        if target is None:
            continue
        sheets.append((sheet.get("name", "<unnamed>"), target))
    return sheets


def formula_text(cell: Element) -> str | None:
    formula = cell.find("main:f", NS)
    if formula is None:
        return None
    if formula.text:
        return f"={formula.text}"
    return "=<formula>"


def inline_string(cell: Element) -> str | None:
    nodes = cell.findall("main:is//main:t", NS)
    if not nodes:
        return None
    return "".join(node.text or "" for node in nodes)


def cell_value(cell: Element, shared_strings: Sequence[str]) -> str | None:
    formula = formula_text(cell)
    if formula is not None:
        return formula

    if cell.get("t") == "inlineStr":
        return inline_string(cell)

    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        return None

    raw_value = value.text
    if cell.get("t") == "s":
        try:
            return shared_strings[int(raw_value)]
        except IndexError, ValueError:
            return raw_value
    if cell.get("t") == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    return raw_value


def worksheet_size(
    worksheet: Element, cell_addresses: Sequence[str]
) -> tuple[int, int]:
    dimension = worksheet.find("main:dimension", NS)
    if dimension is not None:
        reference = dimension.get("ref")
        if reference is not None:
            size = range_size(reference)
            if size is not None:
                return size

    rows = 0
    columns = 0
    for address in cell_addresses:
        position = cell_position(address)
        if position is None:
            continue
        rows = max(rows, position[0])
        columns = max(columns, position[1])
    return rows, columns


def inspect_worksheet(
    archive: ZipFile,
    name: str,
    part_name: str,
    shared_strings: Sequence[str],
) -> WorksheetInspection:
    worksheet = read_xml_part(archive, part_name)
    cells = worksheet.findall(".//main:c", NS)
    addresses = [cell.get("r", "") for cell in cells]
    merged_cells = tuple(
        merge_cell.get("ref", "")
        for merge_cell in worksheet.findall(".//main:mergeCell", NS)
        if merge_cell.get("ref")
    )

    formula_cells: list[CellPreview] = []
    preview_cells: list[CellPreview] = []
    for cell in cells:
        address = cell.get("r")
        if address is None:
            continue

        formula = formula_text(cell)
        if formula is not None:
            formula_cells.append(CellPreview(address, formula))

        value = cell_value(cell, shared_strings)
        if value and len(preview_cells) < MAX_PREVIEW_CELLS:
            preview_cells.append(CellPreview(address, value))

    rows, columns = worksheet_size(worksheet, addresses)
    return WorksheetInspection(
        name=name,
        rows=rows,
        columns=columns,
        merged_cells=merged_cells,
        formula_cells=tuple(formula_cells),
        preview_cells=tuple(preview_cells),
    )


def inspect_xlsx(path: Path) -> list[WorksheetInspection]:
    with ZipFile(path, "r") as archive:
        shared_strings = load_shared_strings(archive)
        return [
            inspect_worksheet(archive, name, part_name, shared_strings)
            for name, part_name in workbook_sheets(archive)
        ]


def print_previews(title: str, previews: Sequence[CellPreview]) -> None:
    print(f"  {title}:")
    if not previews:
        print("    - <none>")
        return
    for preview in previews:
        print(f"    - {preview.address} = {preview.value}")


def print_inspection(path: Path, worksheets: Sequence[WorksheetInspection]) -> None:
    print(f"Workbook: {path}")
    print("Sheets:")
    if not worksheets:
        print("- <none>")
    for worksheet in worksheets:
        print(f"- {worksheet.name}")

    for worksheet in worksheets:
        print()
        print(f"Sheet: {worksheet.name}")
        print(f"  Size: {worksheet.rows} rows x {worksheet.columns} columns")
        print("  Merged cells:")
        if not worksheet.merged_cells:
            print("    - <none>")
        for merged_cell in worksheet.merged_cells:
            print(f"    - {merged_cell}")
        print_previews("Formula cells", worksheet.formula_cells)
        print_previews("First non-empty cells", worksheet.preview_cells)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    path: Path = args.excel_file

    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    if path.suffix.lower() == ".xls":
        print(
            "Warning: .xls is an old Excel format. "
            "Convert it to .xlsx before inspection."
        )
        return 0

    try:
        worksheets = inspect_xlsx(path)
    except (BadZipFile, KeyError, ParseError) as error:
        print(f"Error: could not inspect {path}: {error}", file=sys.stderr)
        return 1

    print_inspection(path, worksheets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
