"""Patch existing worksheet cells inside an OOXML .xlsx package."""

from __future__ import annotations

import posixpath
import re
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from xml.parsers import expat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"main": SPREADSHEET_NS, "rel": OFFICE_REL_NS}
WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
CELL_RE = re.compile(r"^[A-Z]+[1-9][0-9]*$")
ROW_HIDDEN_RE = re.compile(rb'\s+hidden=(["\'])(?:(?!\1).)*\1')
ROW_HT_RE = re.compile(rb'\s+ht=(["\'])(?:(?!\1).)*\1')
ROW_CUSTOM_HEIGHT_RE = re.compile(rb'\s+customHeight=(["\'])(?:(?!\1).)*\1')
type CellValue = str | int | None

ElementTree.register_namespace("", SPREADSHEET_NS)
ElementTree.register_namespace("r", OFFICE_REL_NS)


class OoxmlCellPatcherError(Exception):
    """Expected fail-closed OOXML patching error."""


@dataclass(frozen=True)
class CellRange:
    coordinate: str
    start: int
    end: int
    xml: bytes


@dataclass(frozen=True)
class RowStartTagRange:
    row_number: int
    start: int
    end: int
    xml: bytes


def fail(message: str) -> None:
    raise OoxmlCellPatcherError(message)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_paths(template: Path, output: Path) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_path = resolved(output)
    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if template_path == output_path:
        fail("output matches template")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    return template_path, output_path


def validate_cell_coordinate(coordinate: str) -> str:
    normalized = coordinate.upper()
    if not CELL_RE.fullmatch(normalized):
        fail(f"invalid cell coordinate: {coordinate}")
    return normalized


def validate_cell_value(value: object, coordinate: str) -> CellValue:
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        and value is not None
    ):
        fail(f"unsupported value type for {coordinate}: {type(value).__name__}")
    return value


def validate_updates(updates: Mapping[str, object]) -> dict[str, CellValue]:
    normalized_updates: dict[str, CellValue] = {}
    for coordinate, raw_value in updates.items():
        normalized = validate_cell_coordinate(coordinate)
        if normalized in normalized_updates:
            fail(f"duplicate normalized cell coordinate: {normalized}")
        normalized_updates[normalized] = validate_cell_value(raw_value, normalized)
    return normalized_updates


def validate_row_number(row_number: object) -> int:
    if isinstance(row_number, bool) or not isinstance(row_number, int):
        fail(f"invalid row number: {row_number}")
    if row_number < 1:
        fail(f"invalid row number: {row_number}")
    return row_number


def validate_row_hidden_updates(
    row_hidden_updates: Mapping[int, bool] | None,
) -> dict[int, bool]:
    if row_hidden_updates is None:
        return {}
    checked: dict[int, bool] = {}
    for raw_row_number, hidden in row_hidden_updates.items():
        row_number = validate_row_number(raw_row_number)
        if not isinstance(hidden, bool):
            fail(
                "invalid row hidden value for " f"{row_number}: {type(hidden).__name__}"
            )
        checked[row_number] = hidden
    return checked


def height_text(value: int | float | str | Decimal) -> str:
    try:
        decimal = Decimal(str(value))
    except InvalidOperation:
        fail(f"invalid row height: {value}")
    if not decimal.is_finite() or decimal <= 0:
        fail(f"invalid row height: {value}")
    return format(decimal.normalize(), "f")


def validate_row_height_updates(
    row_height_updates: Mapping[int, int | float | str] | None,
) -> dict[int, str]:
    if row_height_updates is None:
        return {}
    checked: dict[int, str] = {}
    for raw_row_number, raw_height in row_height_updates.items():
        row_number = validate_row_number(raw_row_number)
        if isinstance(raw_height, bool) or not isinstance(
            raw_height,
            (int, float, str),
        ):
            fail(
                "invalid row height value for "
                f"{row_number}: {type(raw_height).__name__}"
            )
        checked[row_number] = height_text(raw_height)
    return checked


def normalize_workbook_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def read_xml_part(archive: zipfile.ZipFile, part_name: str) -> ElementTree.Element:
    try:
        raw_xml = archive.read(part_name)
    except KeyError:
        fail(f"required OOXML part is missing: {part_name}")
    try:
        return ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid XML part {part_name}: {error}")


def worksheet_part_for_sheet(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = read_xml_part(archive, WORKBOOK_PART)
    relationships = read_xml_part(archive, WORKBOOK_RELS_PART)
    targets = {
        relationship.get("Id"): normalize_workbook_target(
            relationship.get("Target", "")
        )
        for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }

    for sheet in workbook.findall("main:sheets/main:sheet", NS):
        if sheet.get("name") != sheet_name:
            continue
        relationship_id = sheet.get(f"{{{OFFICE_REL_NS}}}id")
        target = targets.get(relationship_id)
        if target is None:
            fail(f"worksheet relationship is missing: {sheet_name}")
        return target
    fail(f"worksheet not found: {sheet_name}")


def find_markup_end(xml: bytes, start: int) -> int:
    end = xml.find(b">", start)
    if end == -1:
        fail("invalid worksheet XML: cell element is not closed")
    return end + 1


def namespaced_name(uri: str, local_name: str) -> str:
    return f"{uri} {local_name}"


def is_worksheet_cell(name: str) -> bool:
    return name == namespaced_name(SPREADSHEET_NS, "c")


def is_worksheet_row(name: str) -> bool:
    return name == namespaced_name(SPREADSHEET_NS, "row")


def attribute_value(attrs: list[str], name: str) -> str | None:
    for index in range(0, len(attrs), 2):
        if attrs[index] == name:
            return attrs[index + 1]
    return None


def positive_int_attribute(attrs: list[str], name: str) -> int | None:
    value = attribute_value(attrs, name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        fail(f"invalid row number: {value}")
    if parsed < 1:
        fail(f"invalid row number: {value}")
    return parsed


def cell_ranges(worksheet_xml: bytes) -> dict[str, list[CellRange]]:
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.ordered_attributes = True
    open_cells: list[tuple[str, int]] = []
    ranges: dict[str, list[CellRange]] = {}

    def start_element(name: str, attrs: list[str]) -> None:
        if not is_worksheet_cell(name):
            return
        coordinate = attribute_value(attrs, "r")
        if coordinate is None:
            return
        open_cells.append((coordinate.upper(), parser.CurrentByteIndex))

    def end_element(name: str) -> None:
        if not is_worksheet_cell(name):
            return
        if not open_cells:
            fail("invalid worksheet XML: unexpected cell close")
        coordinate, start = open_cells.pop()
        end = parser.CurrentByteIndex
        if worksheet_xml[end : end + 2] == b"</":
            end = find_markup_end(worksheet_xml, end)
        ranges.setdefault(coordinate, []).append(
            CellRange(
                coordinate=coordinate,
                start=start,
                end=end,
                xml=worksheet_xml[start:end],
            )
        )

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(worksheet_xml, True)
    except expat.ExpatError as error:
        fail(f"invalid worksheet XML: {error}")
    if open_cells:
        fail("invalid worksheet XML: unclosed cell element")
    return ranges


def row_start_tag_ranges(worksheet_xml: bytes) -> dict[int, list[RowStartTagRange]]:
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.ordered_attributes = True
    ranges: dict[int, list[RowStartTagRange]] = {}

    def start_element(name: str, attrs: list[str]) -> None:
        if not is_worksheet_row(name):
            return
        row_number = positive_int_attribute(attrs, "r")
        if row_number is None:
            return
        start = parser.CurrentByteIndex
        end = find_markup_end(worksheet_xml, start)
        ranges.setdefault(row_number, []).append(
            RowStartTagRange(
                row_number=row_number,
                start=start,
                end=end,
                xml=worksheet_xml[start:end],
            )
        )

    parser.StartElementHandler = start_element
    try:
        parser.Parse(worksheet_xml, True)
    except expat.ExpatError as error:
        fail(f"invalid worksheet XML: {error}")
    return ranges


def remove_cell_value_nodes(cell: ElementTree.Element) -> None:
    removable_tags = {
        "f",
        "v",
        "is",
        f"{{{SPREADSHEET_NS}}}f",
        f"{{{SPREADSHEET_NS}}}v",
        f"{{{SPREADSHEET_NS}}}is",
    }
    for child in list(cell):
        if child.tag in removable_tags:
            cell.remove(child)


def child_tag(cell: ElementTree.Element, local_name: str) -> str:
    if cell.tag.startswith("{"):
        return f"{{{SPREADSHEET_NS}}}{local_name}"
    return local_name


def patch_string_cell(cell: ElementTree.Element, value: str) -> None:
    cell.set("t", "inlineStr")
    inline_string = ElementTree.SubElement(cell, child_tag(cell, "is"))
    text = ElementTree.SubElement(inline_string, child_tag(cell, "t"))
    text.set(f"{{{XML_NS}}}space", "preserve")
    text.text = value


def patch_int_cell(cell: ElementTree.Element, value: int) -> None:
    cell.attrib.pop("t", None)
    value_node = ElementTree.SubElement(cell, child_tag(cell, "v"))
    value_node.text = str(value)


def patch_empty_cell(cell: ElementTree.Element) -> None:
    cell.attrib.pop("t", None)


def patch_cell(cell: ElementTree.Element, value: CellValue) -> None:
    remove_cell_value_nodes(cell)
    if value is None:
        patch_empty_cell(cell)
    elif isinstance(value, str):
        patch_string_cell(cell, value)
    else:
        patch_int_cell(cell, value)


def patched_cell_xml(cell_xml: bytes, value: CellValue) -> bytes:
    try:
        cell = ElementTree.fromstring(cell_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid cell XML: {error}")
    patch_cell(cell, value)
    return ElementTree.tostring(cell, encoding="utf-8")


def hidden_row_start_tag_xml(row_xml: bytes, hidden: bool) -> bytes:
    if hidden:
        if ROW_HIDDEN_RE.search(row_xml):
            return ROW_HIDDEN_RE.sub(b' hidden="1"', row_xml, count=1)
        closing = b"/>" if row_xml.endswith(b"/>") else b">"
        return row_xml[: -len(closing)] + b' hidden="1"' + closing
    return ROW_HIDDEN_RE.sub(b"", row_xml, count=1)


def set_row_start_tag_attr(
    row_xml: bytes,
    pattern: re.Pattern[bytes],
    attr: str,
    value: str,
) -> bytes:
    replacement = f' {attr}="{value}"'.encode("ascii")
    if pattern.search(row_xml):
        return pattern.sub(replacement, row_xml, count=1)
    closing = b"/>" if row_xml.endswith(b"/>") else b">"
    return row_xml[: -len(closing)] + replacement + closing


def height_row_start_tag_xml(row_xml: bytes, height: str) -> bytes:
    row_xml = set_row_start_tag_attr(row_xml, ROW_HT_RE, "ht", height)
    return set_row_start_tag_attr(
        row_xml,
        ROW_CUSTOM_HEIGHT_RE,
        "customHeight",
        "1",
    )


def ensure_non_overlapping_replacements(
    replacements: Sequence[tuple[int, int, bytes]],
) -> None:
    ordered = sorted(replacements)
    previous_end = -1
    for start, end, _replacement in ordered:
        if start < previous_end:
            fail("internal patch ranges overlap")
        previous_end = end


def patched_worksheet_xml(
    worksheet_xml: bytes,
    updates: Mapping[str, object],
    row_hidden_updates: Mapping[int, bool] | None = None,
    row_height_updates: Mapping[int, int | float | str] | None = None,
) -> bytes:
    normalized_updates = validate_updates(updates)
    normalized_row_updates = validate_row_hidden_updates(row_hidden_updates)
    normalized_row_height_updates = validate_row_height_updates(row_height_updates)
    if (
        not normalized_updates
        and not normalized_row_updates
        and not normalized_row_height_updates
    ):
        fail("updates must not be empty")

    ranges = cell_ranges(worksheet_xml)
    replacements: list[tuple[int, int, bytes]] = []
    for coordinate, value in normalized_updates.items():
        matches = ranges.get(coordinate, [])
        if not matches:
            fail(f"cell does not exist: {coordinate}")
        if len(matches) > 1:
            fail(f"duplicate cell coordinate in worksheet XML: {coordinate}")
        cell_range = matches[0]
        replacements.append(
            (
                cell_range.start,
                cell_range.end,
                patched_cell_xml(cell_range.xml, value),
            )
        )

    row_ranges = row_start_tag_ranges(worksheet_xml)
    target_rows = set(normalized_row_updates) | set(normalized_row_height_updates)
    for row_number in target_rows:
        matches = row_ranges.get(row_number, [])
        if not matches:
            fail(f"row does not exist: {row_number}")
        if len(matches) > 1:
            fail(f"duplicate row number in worksheet XML: {row_number}")
        row_range = matches[0]
        row_xml = row_range.xml
        if row_number in normalized_row_updates:
            row_xml = hidden_row_start_tag_xml(
                row_xml,
                normalized_row_updates[row_number],
            )
        if row_number in normalized_row_height_updates:
            row_xml = height_row_start_tag_xml(
                row_xml,
                normalized_row_height_updates[row_number],
            )
        replacements.append(
            (
                row_range.start,
                row_range.end,
                row_xml,
            )
        )

    ensure_non_overlapping_replacements(replacements)
    patched = bytearray(worksheet_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        patched[start:end] = replacement
    return bytes(patched)


def archive_bytes(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except zipfile.BadZipFile as error:
        fail(f"invalid xlsx ZIP package: {error}")


def write_patched_package(
    template_parts: Mapping[str, bytes],
    worksheet_part: str,
    worksheet_xml: bytes,
    temporary_output: Path,
) -> None:
    with zipfile.ZipFile(temporary_output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in template_parts.items():
            archive.writestr(name, worksheet_xml if name == worksheet_part else content)


def verify_package_parts(
    template_parts: Mapping[str, bytes],
    output: Path,
    changed_part: str,
) -> None:
    output_parts = archive_bytes(output)
    if set(output_parts) != set(template_parts):
        fail("output ZIP parts differ from template")
    for name, content in template_parts.items():
        if name != changed_part and output_parts[name] != content:
            fail(f"unexpected ZIP part change: {name}")
    if output_parts[changed_part] == template_parts[changed_part]:
        fail(f"target worksheet was not changed: {changed_part}")


def patch_existing_cells(
    *,
    template: Path,
    output: Path,
    sheet_name: str,
    updates: Mapping[str, object],
    row_hidden_updates: Mapping[int, bool] | None = None,
    row_height_updates: Mapping[int, int | float | str] | None = None,
) -> Path:
    if not updates and not row_hidden_updates and not row_height_updates:
        fail("updates must not be empty")
    template_path, output_path = validate_paths(template, output)
    temporary_output = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.xlsx"
    )

    try:
        try:
            with zipfile.ZipFile(template_path) as archive:
                worksheet_part = worksheet_part_for_sheet(archive, sheet_name)
        except zipfile.BadZipFile as error:
            fail(f"invalid xlsx ZIP package: {error}")
        template_parts = archive_bytes(template_path)
        if worksheet_part not in template_parts:
            fail(f"worksheet part is missing: {worksheet_part}")
        worksheet_xml = patched_worksheet_xml(
            template_parts[worksheet_part],
            updates,
            row_hidden_updates,
            row_height_updates,
        )
        write_patched_package(
            template_parts=template_parts,
            worksheet_part=worksheet_part,
            worksheet_xml=worksheet_xml,
            temporary_output=temporary_output,
        )
        verify_package_parts(template_parts, temporary_output, worksheet_part)
        if output_path.exists():
            fail(f"output already exists: {output_path}")
        temporary_output.replace(output_path)
    except Exception:
        if temporary_output.exists():
            temporary_output.unlink()
        raise

    return output_path
