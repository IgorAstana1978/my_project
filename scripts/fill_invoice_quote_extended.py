"""Minimal isolated extended invoice-quote writer.

This module intentionally has no CLI and is not connected to the v0.2 separate
layer. It writes only to an explicitly provided test/extended layout.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHEET_NAME = "Счёт-КП шаблон"
NEEDS_CLARIFICATION = "нужно уточнить"


class ExtendedFillError(Exception):
    """Expected validation, preflight, or generation error."""


@dataclass(frozen=True)
class ExtendedLayout:
    item_start_row: int
    item_end_row: int
    capacity: int
    total_row: int
    signature_range: str
    header_ranges: tuple[str, ...]
    formula_cells: tuple[str, ...]


@dataclass(frozen=True)
class WorkbookSnapshot:
    formulas: dict[str, Any]
    signature_values: dict[str, Any]
    header_values: dict[str, Any]
    merged_ranges: tuple[str, ...]


def fail(message: str) -> None:
    raise ExtendedFillError(message)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_layout(layout: ExtendedLayout) -> None:
    if layout.capacity < 1:
        fail(f"layout capacity must be positive: {layout.capacity}")
    if layout.item_end_row < layout.item_start_row:
        fail("layout item_end_row must be greater than or equal to item_start_row")
    actual_capacity = layout.item_end_row - layout.item_start_row + 1
    if layout.capacity != actual_capacity:
        fail(
            "layout capacity must equal item_end_row - item_start_row + 1: "
            f"{layout.capacity} != {actual_capacity}"
        )
    if layout.total_row in range(layout.item_start_row, layout.item_end_row + 1):
        fail("layout total_row must be outside item rows")
    if not layout.signature_range:
        fail("layout signature_range must be set")
    if not layout.header_ranges:
        fail("layout header_ranges must be set")
    if not layout.formula_cells:
        fail("layout formula_cells must be set")


def require_items(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        fail("payload items must be a list")

    checked_items: list[Mapping[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping) or not item:
            fail(f"payload items[{index}] must be a non-empty object")
        for key in ("name", "unit", "quantity"):
            if key not in item or item[key] in (None, ""):
                fail(f"payload items[{index}].{key} is required")
        checked_items.append(cast(Mapping[str, Any], item))
    if not checked_items:
        fail("payload items must not be empty")
    return tuple(checked_items)


def validate_capacity(
    items: Sequence[Mapping[str, Any]], layout: ExtendedLayout
) -> None:
    if len(items) > layout.capacity:
        fail(f"items count {len(items)} exceeds layout capacity {layout.capacity}")


def validate_template_and_output(template: Path, output: Path) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_path = resolved(output)

    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    if template_path == output_path:
        fail("output matches template")
    return template_path, output_path


def value_map(worksheet: Worksheet, ranges: Sequence[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for cell_range in ranges:
        min_column, min_row, max_column, max_row = range_boundaries(cell_range)
        for row in range(min_row, max_row + 1):
            for column in range(min_column, max_column + 1):
                cell = worksheet.cell(row=row, column=column)
                values[cell.coordinate] = cell.value
    return values


def snapshot_workbook(worksheet: Worksheet, layout: ExtendedLayout) -> WorkbookSnapshot:
    return WorkbookSnapshot(
        formulas={cell: worksheet[cell].value for cell in layout.formula_cells},
        signature_values=value_map(worksheet, (layout.signature_range,)),
        header_values=value_map(worksheet, layout.header_ranges),
        merged_ranges=tuple(str(item) for item in worksheet.merged_cells.ranges),
    )


def load_template_workbook(template: Path) -> Workbook:
    workbook = load_workbook(template, data_only=False)
    if SHEET_NAME not in workbook.sheetnames:
        fail(f'worksheet "{SHEET_NAME}" not found')
    return cast(Workbook, workbook)


def optional_text(value: Any) -> str:
    if value is None or value == "":
        return NEEDS_CLARIFICATION
    return str(value)


def fill_item_rows(
    worksheet: Worksheet,
    items: Sequence[Mapping[str, Any]],
    layout: ExtendedLayout,
) -> None:
    for offset, item in enumerate(items):
        row = layout.item_start_row + offset
        worksheet[f"C{row}"] = item["name"]
        worksheet[f"D{row}"] = item["unit"]
        worksheet[f"E{row}"] = item["quantity"]
        worksheet[f"F{row}"] = optional_text(item.get("instruments_and_devices"))
        worksheet[f"G{row}"] = optional_text(
            item.get("cabinet_type_dimensions_material")
        )
        worksheet[f"H{row}"] = NEEDS_CLARIFICATION

    for row in range(layout.item_start_row + len(items), layout.item_end_row + 1):
        worksheet[f"C{row}"] = NEEDS_CLARIFICATION
        worksheet[f"D{row}"] = "шт"
        worksheet[f"E{row}"] = 1
        worksheet[f"F{row}"] = NEEDS_CLARIFICATION
        worksheet[f"G{row}"] = NEEDS_CLARIFICATION
        worksheet[f"H{row}"] = NEEDS_CLARIFICATION


def verify_output(
    output: Path, layout: ExtendedLayout, before: WorkbookSnapshot
) -> None:
    workbook = load_template_workbook(output)
    worksheet = workbook[SHEET_NAME]
    after = snapshot_workbook(worksheet, layout)

    if after.formulas != before.formulas:
        fail("formula cells changed")
    if after.signature_values != before.signature_values:
        fail("signature range changed")
    if after.header_values != before.header_values:
        fail("header ranges changed")
    if after.merged_ranges != before.merged_ranges:
        fail("merged ranges changed")


def generate_extended_workbook(
    template: Path,
    output: Path,
    payload: Mapping[str, Any],
    layout: ExtendedLayout,
) -> Path:
    validate_layout(layout)
    items = require_items(payload)
    validate_capacity(items, layout)
    template_path, output_path = validate_template_and_output(template, output)

    workbook = load_template_workbook(template_path)
    worksheet = workbook[SHEET_NAME]
    before = snapshot_workbook(worksheet, layout)
    fill_item_rows(worksheet, items, layout)

    temporary_output = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.xlsx"
    )
    try:
        workbook.save(temporary_output)
        verify_output(temporary_output, layout, before)
        if output_path.exists():
            fail(f"output already exists: {output_path}")
        temporary_output.replace(output_path)
    except Exception:
        if temporary_output.exists():
            temporary_output.unlink()
        raise

    return output_path
