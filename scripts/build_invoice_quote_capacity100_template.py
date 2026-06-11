"""Build the one-off capacity 100 invoice quote template at ZIP/OOXML level."""

from __future__ import annotations

import argparse
import hashlib
import os
import posixpath
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from xml.parsers import expat

PROJECT_ROOT = Path(
    os.environ.get(
        "CAPACITY100_BUILDER_PROJECT_ROOT",
        str(Path(__file__).resolve().parents[1]),
    )
)
SHEET_NAME = "Счёт-КП шаблон"
WORKBOOK_PART = "xl/workbook.xml"
WORKBOOK_RELS_PART = "xl/_rels/workbook.xml.rels"
WORKSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
MAIN = {"main": WORKSHEET_NS}
REL = {"rel": PACKAGE_REL_NS}
BOOK = {"main": WORKSHEET_NS, "r": OFFICE_REL_NS}

SOURCE_DIMENSION = "A1:I36"
TARGET_DIMENSION = "A1:I131"
SOURCE_ITEM_ROWS = range(17, 22)
TARGET_ITEM_ROWS = range(17, 117)
SOURCE_TOTAL_ROW = 22
TARGET_TOTAL_ROW = 117
SAMPLE_ROW = 19
SHIFT = 95
CHANGED_PART = "xl/worksheets/sheet1.xml"
CONTENT_TYPES_PART = "[Content_Types].xml"
STYLES_PART = "xl/styles.xml"
CALC_CHAIN_PART = "xl/calcChain.xml"
CALC_CHAIN_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain"
)
CALC_CHAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml"
)
EXPECTED_SOURCE_FORMULA_REFS = {f"I{row}" for row in range(17, 23)}
DEFAULT_UNIT = "шт."
TARGET_ITEM_ROW_HEIGHT = "24"
ALLOWED_CHANGED_PARTS = {
    CHANGED_PART,
    CONTENT_TYPES_PART,
    STYLES_PART,
    WORKBOOK_RELS_PART,
    CALC_CHAIN_PART,
}
EXPECTED_LOWER_MERGES = {
    "C24:I24",
    "C26:I26",
    "C27:I27",
    "C28:I28",
    "C29:I29",
    "C30:I30",
    "B32:E32",
    "F32:I32",
    "B33:E33",
    "F33:I33",
    "B34:I34",
}
EXPECTED_TARGET_MERGES = {
    "C119:I119",
    "C121:I121",
    "C122:I122",
    "C123:I123",
    "C124:I124",
    "C125:I125",
    "B127:E127",
    "F127:I127",
    "B128:E128",
    "F128:I128",
    "B129:I129",
}
UNSUPPORTED_PART_PREFIXES = (
    "xl/tables/",
    "xl/externalLinks/",
    "xl/printerSettings/",
)
UNSUPPORTED_PART_SUFFIXES = (".vml",)


class CapacityTemplateBuilderError(Exception):
    """Expected fail-closed builder error."""


@dataclass(frozen=True)
class ElementRange:
    tag: str
    attrs: dict[str, str]
    start: int
    start_end: int
    end: int
    xml: bytes


def fail(message: str) -> None:
    raise CapacityTemplateBuilderError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_paths(source: Path, output: Path, expected_sha: str) -> tuple[Path, Path]:
    source_path = resolved(source)
    output_path = resolved(output)
    if not source_path.is_file():
        fail(f"source does not exist: {source_path}")
    if source_path == output_path:
        fail("output matches source")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    actual_sha = sha256_file(source_path)
    if actual_sha.casefold() != expected_sha.casefold():
        fail(f"source SHA-256 mismatch: {actual_sha}")
    return source_path, output_path


def archive_bytes(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except zipfile.BadZipFile as error:
        fail(f"invalid xlsx ZIP package: {error}")


def read_xml(parts: dict[str, bytes], part: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(parts[part])
    except KeyError:
        fail(f"required OOXML part is missing: {part}")
    except ElementTree.ParseError as error:
        fail(f"invalid XML part {part}: {error}")


def normalize_workbook_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def worksheet_part_for_sheet(parts: dict[str, bytes]) -> str:
    workbook = read_xml(parts, WORKBOOK_PART)
    relationships = read_xml(parts, WORKBOOK_RELS_PART)
    targets = {
        relationship.get("Id"): normalize_workbook_target(
            relationship.get("Target", "")
        )
        for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    sheets = workbook.findall("main:sheets/main:sheet", BOOK)
    if len(sheets) != 1:
        fail("workbook must contain exactly one sheet")
    sheet = sheets[0]
    if sheet.get("name") != SHEET_NAME:
        fail(f"worksheet not found: {SHEET_NAME}")
    relationship_id = sheet.get(f"{{{OFFICE_REL_NS}}}id")
    target = targets.get(relationship_id)
    if target != CHANGED_PART:
        fail(f"unexpected worksheet part: {target}")
    return target


def local_name(name: str) -> str:
    return name.split(" ", 1)[1] if " " in name else name


def attr_dict(attrs: list[str]) -> dict[str, str]:
    return {attrs[index]: attrs[index + 1] for index in range(0, len(attrs), 2)}


def markup_end(xml: bytes, start: int) -> int:
    end = xml.find(b">", start)
    if end == -1:
        fail("invalid worksheet XML: start tag is not closed")
    return end + 1


def element_ranges(xml: bytes) -> list[ElementRange]:
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.ordered_attributes = True
    stack: list[tuple[str, dict[str, str], int, int]] = []
    ranges: list[ElementRange] = []

    def start_element(name: str, attrs: list[str]) -> None:
        start = parser.CurrentByteIndex
        stack.append(
            (local_name(name), attr_dict(attrs), start, markup_end(xml, start))
        )

    def end_element(name: str) -> None:
        if not stack:
            fail("invalid worksheet XML: unexpected close tag")
        tag, attrs, start, start_end = stack.pop()
        if tag != local_name(name):
            fail("invalid worksheet XML: mismatched close tag")
        end = parser.CurrentByteIndex
        if xml[start_end - 2 : start_end] == b"/>":
            end = start_end
        elif end < start_end:
            end = start_end
        elif xml[end : end + 2] == b"</":
            end = markup_end(xml, end)
        ranges.append(ElementRange(tag, attrs, start, start_end, end, xml[start:end]))

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(xml, True)
    except expat.ExpatError as error:
        fail(f"invalid worksheet XML: {error}")
    if stack:
        fail("invalid worksheet XML: unclosed element")
    return ranges


def single_range(ranges: list[ElementRange], tag: str) -> ElementRange:
    matches = [item for item in ranges if item.tag == tag]
    if len(matches) != 1:
        fail(f"expected one {tag} element, found {len(matches)}")
    return matches[0]


def rows_by_number(ranges: list[ElementRange]) -> dict[int, ElementRange]:
    rows: dict[int, ElementRange] = {}
    for item in ranges:
        if item.tag != "row":
            continue
        raw = item.attrs.get("r")
        if raw is None:
            fail("row is missing r attribute")
        row_number = int(raw)
        if row_number in rows:
            fail(f"duplicate row number: {row_number}")
        rows[row_number] = item
    return rows


def cell_refs(row: ElementRange) -> dict[str, ElementRange]:
    refs: dict[str, ElementRange] = {}
    for item in element_ranges(row.xml):
        if item.tag != "c":
            continue
        ref = item.attrs.get("r")
        if ref is None:
            fail("cell is missing r attribute")
        refs[ref] = item
    return refs


def cell_text(cell_xml: bytes, tag: str) -> str | None:
    try:
        cell = ElementTree.fromstring(cell_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid cell XML: {error}")
    child = cell.find(f"main:{tag}", MAIN)
    if child is None:
        child = cell.find(tag)
    return None if child is None else child.text


def cell_has_value(cell_xml: bytes) -> bool:
    return (
        cell_text(cell_xml, "v") is not None
        or cell_text(cell_xml, "t") is not None
        or b"<is" in cell_xml
    )


def formula_for_row(row: int) -> str:
    return f'IF(OR(E{row}="",H{row}=""),"",IFERROR(E{row}*H{row},"нужно уточнить"))'


def total_formula() -> str:
    return 'IF(COUNT(I17:I116)=0,"нужно уточнить",SUM(I17:I116))'


def expected_source_total_formula() -> str:
    return 'IF(COUNT(I17:I21)=0,"нужно уточнить",SUM(I17:I21))'


def validate_source_rows(rows: dict[int, ElementRange]) -> None:
    for row_number in SOURCE_ITEM_ROWS:
        row = rows.get(row_number)
        if row is None:
            fail(f"source item row is missing: {row_number}")
        if row.attrs.get("ht") != "54" or row.attrs.get("customHeight") != "1":
            fail(f"source item row has unexpected height: {row_number}")
        cells = cell_refs(row)
        for column in "BCDEFGHI":
            coordinate = f"{column}{row_number}"
            if coordinate not in cells:
                fail(f"expected cell is missing: {coordinate}")
        b_value = cell_text(cells[f"B{row_number}"].xml, "v")
        if b_value != str(row_number - 16):
            fail(f"unexpected item number in B{row_number}")
        formula = cell_text(cells[f"I{row_number}"].xml, "f")
        if formula != formula_for_row(row_number):
            fail(f"unexpected item formula in I{row_number}")
    sample = rows.get(SAMPLE_ROW)
    if sample is None:
        fail(f"sample row is missing: {SAMPLE_ROW}")
    total_row = rows.get(SOURCE_TOTAL_ROW)
    if total_row is None:
        fail("source total row is missing")
    total_cells = cell_refs(total_row)
    missing_cell = ElementRange("", {}, 0, 0, 0, b"")
    formula = cell_text(total_cells.get("I22", missing_cell).xml, "f")
    if formula != expected_source_total_formula():
        fail("unexpected source total formula in I22")


def range_rows(reference: str) -> tuple[int, int]:
    rows = [int(match) for match in re.findall(r"[A-Z]+([0-9]+)", reference)]
    if not rows:
        fail(f"invalid merge range: {reference}")
    return min(rows), max(rows)


def shift_cell_ref(match: re.Match[str]) -> str:
    column, row_text = match.groups()
    row = int(row_text)
    if row >= SOURCE_TOTAL_ROW:
        row += SHIFT
    return f"{column}{row}"


def shift_row_references(text: str) -> str:
    return re.sub(r"([A-Z]{1,3})([0-9]+)", shift_cell_ref, text)


def shift_merge(reference: str) -> str:
    start, end = range_rows(reference)
    if end <= 21:
        return reference
    if start >= SOURCE_TOTAL_ROW:
        return shift_row_references(reference)
    fail(f"merge range crosses insertion boundary: {reference}")


def validate_merges(root: ElementTree.Element) -> None:
    merge_cells = root.find("main:mergeCells", MAIN)
    if merge_cells is None:
        fail("mergeCells element is missing")
    lower_merges: set[str] = set()
    for merge_cell in merge_cells.findall("main:mergeCell", MAIN):
        reference = merge_cell.get("ref")
        if reference is None:
            fail("mergeCell is missing ref")
        start, end = range_rows(reference)
        if start <= 21 < end:
            fail(f"merge range crosses insertion boundary: {reference}")
        if start >= SOURCE_TOTAL_ROW:
            lower_merges.add(reference)
    if lower_merges != EXPECTED_LOWER_MERGES:
        fail("unexpected lower merged ranges")


def has_children(root: ElementTree.Element, tag: str) -> bool:
    return root.find(f"main:{tag}", MAIN) is not None


def validate_unsupported_features(
    parts: dict[str, bytes],
    root: ElementTree.Element,
) -> None:
    unsupported_tags = (
        "tableParts",
        "conditionalFormatting",
        "dataValidations",
        "hyperlinks",
        "extLst",
    )
    for tag in unsupported_tags:
        if has_children(root, tag):
            fail(f"unsupported worksheet feature: {tag}")
    if any("comments" in name for name in parts):
        fail("unsupported workbook feature: comments")
    workbook = read_xml(parts, WORKBOOK_PART)
    if workbook.find("main:definedNames", MAIN) is not None:
        fail("unsupported workbook feature: defined names")
    for name in parts:
        if name.startswith(UNSUPPORTED_PART_PREFIXES) or name.endswith(
            UNSUPPORTED_PART_SUFFIXES
        ):
            fail(f"unsupported OOXML part: {name}")


def calc_chain_overrides(parts: dict[str, bytes]) -> list[ElementTree.Element]:
    content_types = read_xml(parts, CONTENT_TYPES_PART)
    return [
        item
        for item in content_types.findall(f"{{{CONTENT_TYPES_NS}}}Override")
        if item.get("PartName") == "/xl/calcChain.xml"
        or item.get("ContentType") == CALC_CHAIN_CONTENT_TYPE
    ]


def calc_chain_relationships(parts: dict[str, bytes]) -> list[ElementTree.Element]:
    relationships = read_xml(parts, WORKBOOK_RELS_PART)
    return [
        item
        for item in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        if item.get("Type") == CALC_CHAIN_REL_TYPE
        or "calcChain" in item.get("Target", "")
    ]


def validate_calc_chain(parts: dict[str, bytes]) -> None:
    has_part = CALC_CHAIN_PART in parts
    overrides = calc_chain_overrides(parts)
    relationships = calc_chain_relationships(parts)
    if not has_part and not overrides and not relationships:
        return
    if not has_part:
        fail("calcChain relationship exists but calcChain part is missing")
    if len(overrides) != 1:
        fail("calcChain content type override is missing or ambiguous")
    override = overrides[0]
    if override.get("ContentType") != CALC_CHAIN_CONTENT_TYPE:
        fail("calcChain content type override is unexpected")
    if len(relationships) != 1:
        fail("calcChain relationship is missing or ambiguous")
    relationship = relationships[0]
    if relationship.get("Type") != CALC_CHAIN_REL_TYPE:
        fail("calcChain relationship type is unexpected")
    if relationship.get("Target") != "calcChain.xml":
        fail("calcChain relationship target is unexpected")
    try:
        root = ElementTree.fromstring(parts[CALC_CHAIN_PART])
    except ElementTree.ParseError as error:
        fail(f"invalid calcChain XML: {error}")
    if root.tag != f"{{{WORKSHEET_NS}}}calcChain" or root.attrib:
        fail("calcChain structure is unsupported")
    refs: set[str] = set()
    for child in list(root):
        if child.tag != f"{{{WORKSHEET_NS}}}c":
            fail("calcChain structure is unsupported")
        reference = child.get("r")
        if reference is None:
            fail("calcChain cell reference is missing")
        unexpected_attrs = set(child.attrib) - {"r", "i", "s", "l", "t"}
        if unexpected_attrs:
            fail("calcChain structure is unsupported")
        refs.add(reference)
    if refs != EXPECTED_SOURCE_FORMULA_REFS:
        fail("calcChain references are unexpected")


def drawing_target(parts: dict[str, bytes], worksheet_part: str) -> str:
    rels_part = "xl/worksheets/_rels/sheet1.xml.rels"
    relationships = read_xml(parts, rels_part)
    targets: dict[str, str] = {}
    for relationship in relationships.findall("rel:Relationship", REL):
        targets[relationship.get("Id", "")] = relationship.get("Target", "")
    root = read_xml(parts, worksheet_part)
    drawing = root.find("main:drawing", MAIN)
    if drawing is None:
        fail("worksheet drawing reference is missing")
    relationship_id = drawing.get(f"{{{OFFICE_REL_NS}}}id")
    target = targets.get(relationship_id or "")
    if target is None:
        fail("worksheet drawing relationship is missing")
    return posixpath.normpath(posixpath.join("xl/worksheets", target))


def validate_drawing(parts: dict[str, bytes], worksheet_part: str) -> None:
    target = drawing_target(parts, worksheet_part)
    if target != "xl/drawings/drawing1.xml":
        fail(f"unexpected drawing part: {target}")
    drawing = read_xml(parts, target)
    anchors = [
        item
        for item in drawing
        if item.tag.endswith("oneCellAnchor") or item.tag.endswith("twoCellAnchor")
    ]
    if not anchors:
        fail("drawing anchor is missing")
    for anchor in anchors:
        row_node = anchor.find(f".//{{{DRAWING_NS}}}from/{{{DRAWING_NS}}}row")
        if row_node is None or row_node.text is None:
            fail("drawing anchor row is missing")
        if int(row_node.text) >= 21:
            fail("drawing anchor is in the shifted area")
    if "xl/media/image1.png" not in parts:
        fail("drawing media image is missing")
    if "xl/drawings/_rels/drawing1.xml.rels" not in parts:
        fail("drawing relationships are missing")


def validate_source_contract(parts: dict[str, bytes], worksheet_part: str) -> None:
    root = read_xml(parts, worksheet_part)
    dimension = root.find("main:dimension", MAIN)
    if dimension is None or dimension.get("ref") != SOURCE_DIMENSION:
        fail("unexpected source dimension")
    ranges = element_ranges(parts[worksheet_part])
    rows = rows_by_number(ranges)
    validate_source_rows(rows)
    validate_merges(root)
    validate_unsupported_features(parts, root)
    validate_calc_chain(parts)
    validate_drawing(parts, worksheet_part)


def replace_attr(tag_xml: bytes, attr: str, value: str) -> bytes:
    start_end = markup_end(tag_xml, 0)
    start_tag = tag_xml[:start_end]
    rest = tag_xml[start_end:]
    pattern = rb"(\s+" + attr.encode("ascii") + rb'=)(["\'])(?:(?!\2).)*\2'

    def replacement(match: re.Match[bytes]) -> bytes:
        quote = match.group(2)
        return match.group(1) + quote + value.encode("utf-8") + quote

    if re.search(pattern, start_tag) is None:
        closing = b"/>" if start_tag.endswith(b"/>") else b">"
        patched_start = (
            start_tag[: -len(closing)]
            + b" "
            + attr.encode("ascii")
            + b'="'
            + value.encode("utf-8")
            + b'"'
            + closing
        )
    else:
        patched_start = re.sub(pattern, replacement, start_tag, count=1)
    return patched_start + rest


def replace_cell_ref(cell_xml: bytes, coordinate: str) -> bytes:
    return replace_attr(cell_xml, "r", coordinate)


def remove_children(cell_xml: bytes) -> bytes:
    start_end = markup_end(cell_xml, 0)
    if cell_xml[start_end - 2 : start_end] == b"/>":
        return cell_xml
    end_start = cell_xml.rfind(b"</")
    if end_start == -1:
        fail("invalid cell XML: close tag is missing")
    return cell_xml[:start_end] + cell_xml[end_start:]


def int_cell(cell_xml: bytes, coordinate: str, value: int) -> bytes:
    cell_xml = replace_cell_ref(cell_xml, coordinate)
    cell_xml = re.sub(rb'\s+t=(["\'])(?:(?!\1).)*\1', b"", cell_xml, count=1)
    cell_xml = remove_children(cell_xml)
    start_end = markup_end(cell_xml, 0)
    end_start = cell_xml.rfind(b"</")
    return (
        cell_xml[:start_end] + f"<v>{value}</v>".encode("ascii") + cell_xml[end_start:]
    )


def empty_cell(cell_xml: bytes, coordinate: str) -> bytes:
    cell_xml = replace_cell_ref(cell_xml, coordinate)
    cell_xml = re.sub(rb'\s+t=(["\'])(?:(?!\1).)*\1', b"", cell_xml, count=1)
    return remove_children(cell_xml)


def formula_cell(cell_xml: bytes, coordinate: str, formula: str) -> bytes:
    cell_xml = replace_cell_ref(cell_xml, coordinate)
    cell_xml = replace_attr(cell_xml, "t", "str")
    cell_xml = remove_children(cell_xml)
    start_end = markup_end(cell_xml, 0)
    end_start = cell_xml.rfind(b"</")
    formula_xml = f"<f>{formula}</f>".encode()
    return cell_xml[:start_end] + formula_xml + cell_xml[end_start:]


def text_cell_from_template(cell_xml: bytes, coordinate: str) -> bytes:
    return replace_cell_ref(cell_xml, coordinate)


def shifted_cell(cell_xml: bytes, old_coordinate: str) -> bytes:
    new_coordinate = shift_row_references(old_coordinate)
    shifted = replace_cell_ref(cell_xml, new_coordinate)
    shifted = re.sub(
        rb"<f>(.*?)</f>",
        lambda match: b"<f>"
        + shift_row_references(match.group(1).decode("utf-8")).encode("utf-8")
        + b"</f>",
        shifted,
        flags=re.DOTALL,
    )
    return shifted


def row_start_with_number(row_xml: bytes, row_number: int) -> bytes:
    start_end = markup_end(row_xml, 0)
    return replace_attr(row_xml[:start_end], "r", str(row_number)) + row_xml[start_end:]


def row_start_with_height(row_xml: bytes, height: str) -> bytes:
    start_end = markup_end(row_xml, 0)
    start_tag = replace_attr(row_xml[:start_end], "ht", height)
    start_tag = replace_attr(start_tag, "customHeight", "1")
    return start_tag + row_xml[start_end:]


def tune_item_row_xml(row_xml: bytes, row_number: int) -> bytes:
    row_xml = row_start_with_number(row_xml, row_number)
    return row_start_with_height(row_xml, TARGET_ITEM_ROW_HEIGHT)


def build_position_row(sample_row: ElementRange, row_number: int) -> bytes:
    row_xml = tune_item_row_xml(sample_row.xml, row_number)
    cells = cell_refs(ElementRange("row", {}, 0, 0, len(row_xml), row_xml))
    replacements: list[tuple[int, int, bytes]] = []
    for column in "BCDEFGHI":
        old_coordinate = f"{column}{SAMPLE_ROW}"
        cell = cells[old_coordinate]
        new_coordinate = f"{column}{row_number}"
        if column == "B":
            replacement = int_cell(cell.xml, new_coordinate, row_number - 16)
        elif column == "D":
            replacement = text_cell_from_template(cell.xml, new_coordinate)
        elif column == "I":
            replacement = formula_cell(
                cell.xml,
                new_coordinate,
                formula_for_row(row_number),
            )
        else:
            replacement = empty_cell(cell.xml, new_coordinate)
        replacements.append((cell.start, cell.end, replacement))
    data = bytearray(row_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        data[start:end] = replacement
    return bytes(data)


def tune_existing_position_row(row: ElementRange) -> bytes:
    row_number = int(row.attrs["r"])
    row_xml = tune_item_row_xml(row.xml, row_number)
    cells = cell_refs(ElementRange("row", {}, 0, 0, len(row_xml), row_xml))
    cell = cells.get(f"D{row_number}")
    if cell is None:
        fail(f"expected unit cell is missing: D{row_number}")
    replacement = text_cell_from_template(cell.xml, f"D{row_number}")
    data = bytearray(row_xml)
    data[cell.start : cell.end] = replacement
    return bytes(data)


def shift_lower_row(row: ElementRange) -> bytes:
    old_row = int(row.attrs["r"])
    new_row = old_row + SHIFT
    row_xml = row_start_with_number(row.xml, new_row)
    cells = cell_refs(ElementRange("row", {}, 0, 0, len(row_xml), row_xml))
    replacements: list[tuple[int, int, bytes]] = []
    for coordinate, cell in cells.items():
        if coordinate == "I22":
            replacement = formula_cell(cell.xml, "I117", total_formula())
        else:
            replacement = shifted_cell(cell.xml, coordinate)
        replacements.append((cell.start, cell.end, replacement))
    data = bytearray(row_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        data[start:end] = replacement
    return bytes(data)


def build_sheet_data(sheet_data: ElementRange, rows: dict[int, ElementRange]) -> bytes:
    row_ranges = sorted(
        (row for row in rows.values() if 17 <= int(row.attrs["r"]) <= 36),
        key=lambda item: int(item.attrs["r"]),
    )
    if len(row_ranges) != 20:
        fail("unexpected source row set in table/lower block")
    output_rows = [rows[row].xml for row in range(1, 17) if row in rows]
    for row in range(17, 22):
        output_rows.append(tune_existing_position_row(rows[row]))
    for row in range(22, 117):
        output_rows.append(build_position_row(rows[SAMPLE_ROW], row))
    for row in range(22, 37):
        output_rows.append(shift_lower_row(rows[row]))
    start_tag = sheet_data.xml[: sheet_data.start_end - sheet_data.start]
    return start_tag + b"".join(output_rows) + b"</sheetData>"


def build_merge_cells(merge_cells: ElementRange) -> bytes:
    try:
        root = ElementTree.fromstring(merge_cells.xml)
    except ElementTree.ParseError as error:
        fail(f"invalid mergeCells XML: {error}")
    refs: list[str] = []
    merge_cell_elements = root.findall("main:mergeCell", MAIN) or root.findall(
        "mergeCell"
    )
    for merge_cell in merge_cell_elements:
        reference = merge_cell.get("ref")
        if reference is None:
            fail("mergeCell is missing ref")
        refs.append(shift_merge(reference))
    target_lower = {ref for ref in refs if range_rows(ref)[0] >= TARGET_TOTAL_ROW}
    if target_lower != EXPECTED_TARGET_MERGES:
        fail("target merged ranges are unexpected")
    cells_xml = b"".join(f'<mergeCell ref="{ref}"/>'.encode("ascii") for ref in refs)
    return (
        f'<mergeCells count="{len(refs)}">'.encode("ascii")
        + cells_xml
        + b"</mergeCells>"
    )


def patch_dimension(dimension: ElementRange) -> bytes:
    return replace_attr(dimension.xml, "ref", TARGET_DIMENSION)


def patch_worksheet_xml(worksheet_xml: bytes) -> bytes:
    ranges = element_ranges(worksheet_xml)
    rows = rows_by_number(ranges)
    dimension = single_range(ranges, "dimension")
    sheet_data = single_range(ranges, "sheetData")
    merge_cells = single_range(ranges, "mergeCells")
    replacements = [
        (dimension.start, dimension.end, patch_dimension(dimension)),
        (sheet_data.start, sheet_data.end, build_sheet_data(sheet_data, rows)),
        (merge_cells.start, merge_cells.end, build_merge_cells(merge_cells)),
    ]
    data = bytearray(worksheet_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        data[start:end] = replacement
    return bytes(data)


def without_calc_chain_override(content_types_xml: bytes) -> bytes:
    try:
        root = ElementTree.fromstring(content_types_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid content types XML: {error}")
    removed = False
    for child in list(root):
        if (
            child.tag == f"{{{CONTENT_TYPES_NS}}}Override"
            and child.get("PartName") == "/xl/calcChain.xml"
        ):
            root.remove(child)
            removed = True
    if not removed:
        fail("calcChain content type override was not removed")
    ElementTree.register_namespace("", CONTENT_TYPES_NS)
    result = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    if b"calcChain" in result:
        fail("content types still contain calcChain")
    return result


def without_calc_chain_relationship(workbook_rels_xml: bytes) -> bytes:
    try:
        root = ElementTree.fromstring(workbook_rels_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid workbook relationships XML: {error}")
    removed = False
    for child in list(root):
        if (
            child.tag == f"{{{PACKAGE_REL_NS}}}Relationship"
            and child.get("Type") == CALC_CHAIN_REL_TYPE
        ):
            root.remove(child)
            removed = True
    if not removed:
        fail("calcChain relationship was not removed")
    ElementTree.register_namespace("", PACKAGE_REL_NS)
    result = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    if b"calcChain" in result:
        fail("workbook relationships still contain calcChain")
    return result


def tuned_styles_xml(styles_xml: bytes) -> bytes:
    try:
        root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError as error:
        fail(f"invalid styles XML: {error}")
    fonts = root.find(f"{{{WORKSHEET_NS}}}fonts")
    if fonts is None:
        fail("styles fonts element is missing")
    changed = False
    for font in fonts.findall(f"{{{WORKSHEET_NS}}}font"):
        size = font.find(f"{{{WORKSHEET_NS}}}sz")
        if size is None:
            continue
        if set(size.attrib) != {"val"}:
            fail("font size structure is unsupported")
        if size.get("val") in {"10", "11"}:
            changed = True
    if not changed:
        fail("font sizes 10/11 were not found")

    def replace_size(match: re.Match[bytes]) -> bytes:
        return match.group(1) + match.group(2) + b"12" + match.group(2)

    tuned = re.sub(
        rb"(<(?:\w+:)?sz\b[^>]*\bval=)([\"'])(?:10|11)\2",
        replace_size,
        styles_xml,
    )
    try:
        tuned_root = ElementTree.fromstring(tuned)
    except ElementTree.ParseError as error:
        fail(f"invalid tuned styles XML: {error}")
    tuned_fonts = tuned_root.find(f"{{{WORKSHEET_NS}}}fonts")
    if tuned_fonts is None:
        fail("tuned styles fonts element is missing")
    remaining = [
        size.get("val")
        for font in tuned_fonts.findall(f"{{{WORKSHEET_NS}}}font")
        for size in [font.find(f"{{{WORKSHEET_NS}}}sz")]
        if size is not None and size.get("val") in {"10", "11"}
    ]
    if remaining:
        fail("font sizes 10/11 remain in tuned styles")
    return tuned


def output_parts_for_source(
    source_parts: dict[str, bytes],
    worksheet_xml: bytes,
) -> dict[str, bytes]:
    if CALC_CHAIN_PART not in source_parts:
        fail("calcChain part is missing")
    if STYLES_PART not in source_parts:
        fail("styles part is missing")
    output_parts = dict(source_parts)
    output_parts[CHANGED_PART] = worksheet_xml
    output_parts[STYLES_PART] = tuned_styles_xml(source_parts[STYLES_PART])
    output_parts[CONTENT_TYPES_PART] = without_calc_chain_override(
        source_parts[CONTENT_TYPES_PART]
    )
    output_parts[WORKBOOK_RELS_PART] = without_calc_chain_relationship(
        source_parts[WORKBOOK_RELS_PART]
    )
    del output_parts[CALC_CHAIN_PART]
    return output_parts


def write_package(output_parts: dict[str, bytes], temporary_output: Path) -> None:
    with zipfile.ZipFile(temporary_output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in output_parts.items():
            archive.writestr(name, content)


def verify_non_target_parts(source_parts: dict[str, bytes], output: Path) -> None:
    output_parts = archive_bytes(output)
    expected_parts = set(source_parts) - {CALC_CHAIN_PART}
    if set(output_parts) != expected_parts:
        fail("output ZIP parts differ from source")
    for name, content in source_parts.items():
        if name in ALLOWED_CHANGED_PARTS:
            continue
        if output_parts[name] != content:
            fail(f"unexpected ZIP part change: {name}")
    if output_parts[CHANGED_PART] == source_parts[CHANGED_PART]:
        fail("target worksheet was not changed")
    if CALC_CHAIN_PART in output_parts:
        fail("calcChain part is present in output")
    if b"calcChain" in output_parts[CONTENT_TYPES_PART]:
        fail("content types still contain calcChain")
    if b"calcChain" in output_parts[WORKBOOK_RELS_PART]:
        fail("workbook relationships still contain calcChain")
    if (
        b'val="10"' in output_parts[STYLES_PART]
        or b'val="11"' in output_parts[STYLES_PART]
    ):
        fail("font sizes 10/11 remain in output styles")


def verify_output_contract(output: Path) -> None:
    parts = archive_bytes(output)
    if CALC_CHAIN_PART in parts:
        fail("output calcChain verification failed")
    if b"calcChain" in parts[CONTENT_TYPES_PART]:
        fail("output content types calcChain verification failed")
    if b"calcChain" in parts[WORKBOOK_RELS_PART]:
        fail("output workbook relationships calcChain verification failed")
    if b'val="10"' in parts[STYLES_PART] or b'val="11"' in parts[STYLES_PART]:
        fail("output styles font size verification failed")
    root = read_xml(parts, CHANGED_PART)
    dimension = root.find("main:dimension", MAIN)
    if dimension is None or dimension.get("ref") != TARGET_DIMENSION:
        fail("output dimension verification failed")
    ranges = element_ranges(parts[CHANGED_PART])
    rows = rows_by_number(ranges)
    for row_number in TARGET_ITEM_ROWS:
        if row_number not in rows:
            fail(f"output item row is missing: {row_number}")
        if rows[row_number].attrs.get("ht") != TARGET_ITEM_ROW_HEIGHT:
            fail(f"output item row height is invalid: {row_number}")
        if rows[row_number].attrs.get("customHeight") != "1":
            fail(f"output item row customHeight is invalid: {row_number}")
        cells = cell_refs(rows[row_number])
        if cell_text(cells[f"B{row_number}"].xml, "v") != str(row_number - 16):
            fail(f"output item number is invalid: {row_number}")
        if not cell_has_value(cells[f"D{row_number}"].xml):
            fail(f"output item unit is invalid: {row_number}")
        if cell_text(cells[f"I{row_number}"].xml, "f") != formula_for_row(row_number):
            fail(f"output item formula is invalid: {row_number}")
    total_cells = cell_refs(rows[TARGET_TOTAL_ROW])
    if cell_text(total_cells["I117"].xml, "f") != total_formula():
        fail("output total formula verification failed")
    validate_drawing(parts, CHANGED_PART)


def build_capacity100_template(
    *,
    source: Path,
    output: Path,
    expected_source_sha256: str,
) -> Path:
    source_path, output_path = validate_paths(source, output, expected_source_sha256)
    temporary_output = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp.xlsx"
    )
    try:
        source_parts = archive_bytes(source_path)
        worksheet_part = worksheet_part_for_sheet(source_parts)
        validate_source_contract(source_parts, worksheet_part)
        worksheet_xml = patch_worksheet_xml(source_parts[worksheet_part])
        output_parts = output_parts_for_source(source_parts, worksheet_xml)
        write_package(output_parts, temporary_output)
        verify_non_target_parts(source_parts, temporary_output)
        verify_output_contract(temporary_output)
        if output_path.exists():
            fail(f"output already exists: {output_path}")
        temporary_output.replace(output_path)
    except Exception:
        if temporary_output.exists():
            temporary_output.unlink()
        if output_path.exists() and output_path.name.startswith("."):
            output_path.unlink()
        raise
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the one-off capacity 100 invoice quote template.",
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = build_capacity100_template(
            source=args.source,
            output=args.output,
            expected_source_sha256=args.expected_source_sha256,
        )
    except CapacityTemplateBuilderError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"CREATED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
