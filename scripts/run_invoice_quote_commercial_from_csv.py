"""Create a reconciled internal commercial quote draft from strict CSV."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import re
import sys
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, NoReturn, cast
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMERCIAL_PREFLIGHT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py"
)
COMMERCIAL_RECONCILIATION_SCRIPT = (
    PROJECT_ROOT / "scripts" / "inspect_quote_commercial_reconciliation.py"
)
OOXML_CELL_PATCHER_SCRIPT = PROJECT_ROOT / "scripts" / "ooxml_cell_patcher.py"

SHEET_NAME = "Счёт-КП шаблон"
STYLES_PART = "xl/styles.xml"
CERTIFIED_CAPACITY = 100
ITEM_START_ROW = 17
ITEM_END_ROW = 116
TOTAL_ROW = 117
AMOUNT_WORDS_ROW = 119
QUOTE_METADATA_SCHEMA_VERSION = "quote_metadata.v0.1"
QUOTE_METADATA_SCHEMA_VERSION_V0_2 = "quote_metadata.v0.2"
QUOTE_METADATA_FIELDS = frozenset(
    {
        "schema_version",
        "document_number",
        "document_date",
        "payer_name",
        "payment_terms",
        "manufacturing_lead_time",
        "delivery_terms",
        "vat_rate_percent",
        "validity_period",
        "object_name",
        "basis_project",
        "item_notes",
    }
)
QUOTE_METADATA_V0_2_FIELDS = QUOTE_METADATA_FIELDS | {"apparatus_manufacturer"}
DOCUMENT_LINE_CELL = "B9"
PAYER_CELL = "B10"
OBJECT_CELL = "B11"
BASIS_PROJECT_CELL = "B12"
SECTION_CELL = "C16"
SECTION_ROW = 16
VALIDITY_CELL = "C121"
PAYMENT_DELIVERY_CELL = "C122"
MANUFACTURING_CELL = "C123"
VAT_RATE_CELL = "A131"
VAT_LABEL_CELL = "H118"
VAT_AMOUNT_CELL = "I118"
APPARATUS_HEADER_CELL = "F15"
APPARATUS_HEADER_PREFIX = "Применяемые приборы и аппараты\n" "согласно схемы,\n"
APPARATUS_MANUFACTURER_PREFIX = "производства "
ITEM_NOTE_COLUMN = "J"
ITEM_NOTE_WIDTH = 30
CERTIFIED_LOGO_PART = "xl/media/image1.png"
CERTIFIED_LOGO_SHA256 = (
    "18e0f9446c72f8aa80ea833df07c2e42eb830770a0186decc476c5f948987301"
)
CERTIFIED_DRAWING_PART = "xl/drawings/drawing1.xml"
CERTIFIED_DRAWING_RELS_PART = "xl/drawings/_rels/drawing1.xml.rels"
CERTIFIED_DRAWING_TARGET = "../drawings/drawing1.xml"
CERTIFIED_LOGO_TARGET = "../media/image1.png"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
DRAWING_MAIN_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
DRAWING_REL_TYPE = f"{OFFICE_REL_NS}/drawing"
IMAGE_REL_TYPE = f"{OFFICE_REL_NS}/image"
CERTIFIED_LOGO_COL = "0"
CERTIFIED_LOGO_ROW = "1"
CERTIFIED_LOGO_EXTENT = {"cx": "781050", "cy": "428625"}
PRINT_PAGE_SETUP = {
    "paperSize": "9",
    "scale": "54",
    "fitToHeight": "0",
    "orientation": "portrait",
}
PRINT_PAGE_MARGINS = {
    "left": 0.43307086614173229,
    "right": 0.23622047244094491,
    "top": 0.35433070866141736,
    "bottom": 0.74803149606299213,
    "header": 0.31496062992125984,
    "footer": 0.31496062992125984,
}
VAT_RATE_PLACEHOLDER = "QUOTE_METADATA_VAT_RATE"
VAT_LABEL_FORMULA = (
    '=IF(NOT(ISNUMBER($A$131)),"","В том числе НДС "' '&TEXT($A$131,"0")&"%")'
)
VAT_AMOUNT_FORMULA = (
    '=IF(OR(NOT(ISNUMBER(I117)),NOT(ISNUMBER($A$131))),"",' "I117*$A$131/(100+$A$131))"
)
RUSSIAN_MONTHS = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
NUMBER_FORMAT_ID = "3"
NUMBER_FORMAT_CODE = "#,##0"
BASE_ITEM_ROW_HEIGHT = 24
ITEM_ROW_VISUAL_LINE_HEIGHT = 15
ITEM_ROW_VERTICAL_PADDING = 6
MAX_ITEM_ROW_HEIGHT = 360
CELL_STYLE_RE = re.compile(rb'\s+s=(["\'])(?:(?!\1).)*\1')
COUNT_ATTR_RE = re.compile(rb'\s+count=(["\'])[0-9]+\1')
CELL_XFS_CONTAINER_RE = re.compile(
    rb"<(?P<prefix>(?:[A-Za-z_][A-Za-z0-9_.-]*:)?)cellXfs\b"
    rb"(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=prefix)cellXfs\s*>",
    re.DOTALL,
)
ROW_HEIGHT_TEXT_WIDTHS = {
    "name": 28,
    "instruments_and_devices": 35,
    "cabinet_type_dimensions_material": 24,
}
ONES_MASCULINE = (
    "",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
ONES_FEMININE = (
    "",
    "одна",
    "две",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
)
TEENS = (
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)
SCALE_FORMS = (
    ("", "", "", False),
    ("тысяча", "тысячи", "тысяч", True),
    ("миллион", "миллиона", "миллионов", False),
    ("миллиард", "миллиарда", "миллиардов", False),
    ("триллион", "триллиона", "триллионов", False),
    ("квадриллион", "квадриллиона", "квадриллионов", False),
)
PASS_NEXT = (
    "retain as an internal draft only; manual Igor check and separate Human "
    "Approval are required"
)
FAIL_NEXT = "no internal draft was published; correct the reported issue and rerun"


class CommercialWriterError(Exception):
    """Expected commercial writer validation or generation failure."""


@dataclass(frozen=True)
class ItemNote:
    item_number: int
    text: str


@dataclass(frozen=True)
class QuoteMetadata:
    schema_version: str
    document_number: str
    document_date: date
    payer_name: str
    payment_terms: str
    manufacturing_lead_time: str
    delivery_terms: str
    vat_rate_percent: int
    validity_period: str | None
    object_name: str | None
    basis_project: str | None
    item_notes: tuple[ItemNote, ...]
    apparatus_manufacturer: str | None


@dataclass
class CommercialWriterResult:
    commercial_csv: Path
    template: Path
    output: Path
    status: str = "FAIL"
    row_count: int = 0
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "commercial preflight": "fail",
            "capacity100 profile": "fail",
            "output path": "fail",
            "candidate generation": "fail",
            "presentation formatting": "fail",
            "commercial reconciliation": "fail",
            "atomic publish": "fail",
        }
    )
    reconciliation_checks: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    next_action: str = FAIL_NEXT


def fail(message: str) -> NoReturn:
    raise CommercialWriterError(message)


def load_sibling_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        fail(f"could not load required helper: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


commercial_preflight = cast(
    Any,
    load_sibling_module(
        "preflight_quote_commercial_input_for_writer",
        COMMERCIAL_PREFLIGHT_SCRIPT,
    ),
)
commercial_reconciliation = cast(
    Any,
    load_sibling_module(
        "inspect_quote_commercial_reconciliation_for_writer",
        COMMERCIAL_RECONCILIATION_SCRIPT,
    ),
)
ooxml_cell_patcher = cast(
    Any,
    load_sibling_module(
        "ooxml_cell_patcher_for_commercial_writer",
        OOXML_CELL_PATCHER_SCRIPT,
    ),
)
OoxmlCellPatcherError = ooxml_cell_patcher.OoxmlCellPatcherError
patch_existing_cells = ooxml_cell_patcher.patch_existing_cells
archive_bytes = ooxml_cell_patcher.archive_bytes
cell_ranges = ooxml_cell_patcher.cell_ranges
ensure_non_overlapping_replacements = (
    ooxml_cell_patcher.ensure_non_overlapping_replacements
)
find_markup_end = ooxml_cell_patcher.find_markup_end
worksheet_part_for_sheet = ooxml_cell_patcher.worksheet_part_for_sheet
SPREADSHEET_NS = ooxml_cell_patcher.SPREADSHEET_NS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reconciled capacity100 commercial XLSX for internal "
            "draft review only."
        )
    )
    parser.add_argument("--commercial-csv", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--template-capacity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--quote-metadata-json", type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_generation_paths(
    template: Path,
    output: Path,
    template_capacity: int,
) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_path = resolved(output)

    if template_capacity != CERTIFIED_CAPACITY:
        fail("only the certified capacity100 profile is supported")
    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if template_path.suffix.casefold() != ".xlsx":
        fail("template suffix must be .xlsx")
    if output_path.suffix.casefold() != ".xlsx":
        fail("output suffix must be .xlsx")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    if template_path == output_path:
        fail("output matches template")
    return template_path, output_path


def load_commercial_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(
                csv_file,
                delimiter=commercial_preflight.CSV_DELIMITER,
                strict=True,
            )
            rows = [dict(row) for row in reader]
    except OSError, UnicodeDecodeError, csv.Error:
        fail("validated commercial CSV could not be read safely")
    if not rows:
        fail("validated commercial CSV contains no rows")
    return rows


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("quote metadata JSON contains duplicate fields")
        result[key] = value
    return result


def required_metadata_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value.strip():
        fail(f"quote metadata field must be a non-empty string: {field_name}")
    return value


def optional_metadata_text(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload[field_name]
    if value is not None and (not isinstance(value, str) or not value.strip()):
        fail(
            "quote metadata field must be null or a non-empty string: " f"{field_name}"
        )
    return value


def load_item_notes(payload: Mapping[str, Any], row_count: int) -> tuple[ItemNote, ...]:
    raw_notes = payload["item_notes"]
    if not isinstance(raw_notes, list):
        fail("quote metadata item_notes must be a list")
    notes: list[ItemNote] = []
    seen_numbers: set[int] = set()
    for raw_note in raw_notes:
        if not isinstance(raw_note, dict) or set(raw_note) != {"item_number", "text"}:
            fail("quote metadata item note is malformed or contains unknown fields")
        item_number = raw_note["item_number"]
        if (
            isinstance(item_number, bool)
            or not isinstance(item_number, int)
            or item_number <= 0
        ):
            fail("quote metadata item note item_number must be a positive integer")
        if item_number > row_count:
            fail("quote metadata item note item_number is out of range")
        if item_number in seen_numbers:
            fail("quote metadata item note item_number is duplicated")
        note_text = raw_note["text"]
        if not isinstance(note_text, str) or not note_text.strip():
            fail("quote metadata item note text must be a non-empty string")
        seen_numbers.add(item_number)
        notes.append(ItemNote(item_number=item_number, text=note_text))
    return tuple(notes)


def load_quote_metadata(path: Path, row_count: int) -> QuoteMetadata:
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError, UnicodeDecodeError:
        fail("quote metadata JSON could not be read as strict UTF-8")
    try:
        payload = json.loads(text, object_pairs_hook=unique_json_object)
    except json.JSONDecodeError:
        fail("quote metadata JSON is malformed")
    if not isinstance(payload, dict):
        fail("quote metadata JSON root must be an object")
    schema_version = payload.get("schema_version")
    if schema_version not in (
        QUOTE_METADATA_SCHEMA_VERSION,
        QUOTE_METADATA_SCHEMA_VERSION_V0_2,
    ):
        if "schema_version" not in payload:
            fail("quote metadata JSON is missing required fields")
        fail("quote metadata schema_version is unsupported")
    expected_fields = (
        QUOTE_METADATA_V0_2_FIELDS
        if schema_version == QUOTE_METADATA_SCHEMA_VERSION_V0_2
        else QUOTE_METADATA_FIELDS
    )
    payload_fields = set(payload)
    unknown_fields = payload_fields - expected_fields
    missing_fields = expected_fields - payload_fields
    if unknown_fields:
        fail("quote metadata JSON contains unknown fields")
    if missing_fields:
        fail("quote metadata JSON is missing required fields")
    document_date_text = required_metadata_text(payload, "document_date")
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", document_date_text) is None:
        fail("quote metadata document_date must use YYYY-MM-DD")
    try:
        document_date = date.fromisoformat(document_date_text)
    except ValueError:
        fail("quote metadata document_date is invalid")

    vat_rate = payload["vat_rate_percent"]
    if isinstance(vat_rate, bool) or not isinstance(vat_rate, int):
        fail("quote metadata vat_rate_percent must be an integer")
    if not 0 <= vat_rate <= 100:
        fail("quote metadata vat_rate_percent must be between 0 and 100")

    validity_period = payload["validity_period"]
    if validity_period is not None and (
        not isinstance(validity_period, str) or not validity_period.strip()
    ):
        fail("quote metadata validity_period must be null or a non-empty string")

    return QuoteMetadata(
        schema_version=schema_version,
        document_number=required_metadata_text(payload, "document_number"),
        document_date=document_date,
        payer_name=required_metadata_text(payload, "payer_name"),
        payment_terms=required_metadata_text(payload, "payment_terms"),
        manufacturing_lead_time=required_metadata_text(
            payload, "manufacturing_lead_time"
        ),
        delivery_terms=required_metadata_text(payload, "delivery_terms"),
        vat_rate_percent=vat_rate,
        validity_period=validity_period,
        object_name=optional_metadata_text(payload, "object_name"),
        basis_project=optional_metadata_text(payload, "basis_project"),
        item_notes=load_item_notes(payload, row_count),
        apparatus_manufacturer=(
            required_metadata_text(payload, "apparatus_manufacturer")
            if schema_version == QUOTE_METADATA_SCHEMA_VERSION_V0_2
            else None
        ),
    )


def formula_for_cell(worksheet_xml: bytes, coordinate: str) -> str | None:
    matches = cell_ranges(worksheet_xml).get(coordinate, [])
    if len(matches) != 1:
        return None
    try:
        cell = ElementTree.fromstring(matches[0].xml)
    except ElementTree.ParseError:
        return None
    formula = cell.find(f"{{{SPREADSHEET_NS}}}f")
    if formula is None:
        formula = cell.find("f")
    if formula is None or formula.text is None:
        return None
    return f"={formula.text}"


def page_margins_match(element: ElementTree.Element | None) -> bool:
    if element is None:
        return False
    try:
        return all(
            element.get(name) is not None
            and abs(float(cast(str, element.get(name))) - value) <= 1e-12
            for name, value in PRINT_PAGE_MARGINS.items()
        )
    except ValueError:
        return False


def worksheet_relationships_part(worksheet_part: str) -> str:
    path = PurePosixPath(worksheet_part)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def relationship_target(
    relationships: ElementTree.Element,
    relationship_id: str | None,
    relationship_type: str,
) -> str | None:
    matches = [
        relationship
        for relationship in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        if relationship.get("Id") == relationship_id
        and relationship.get("Type") == relationship_type
    ]
    if len(matches) != 1:
        return None
    return matches[0].get("Target")


def validate_certified_logo_contract(
    archive: zipfile.ZipFile,
    worksheet_part: str,
    worksheet: ElementTree.Element,
) -> None:
    required_parts = {
        CERTIFIED_LOGO_PART,
        CERTIFIED_DRAWING_PART,
        CERTIFIED_DRAWING_RELS_PART,
        worksheet_relationships_part(worksheet_part),
    }
    if not required_parts.issubset(archive.namelist()):
        fail("quote metadata template certified logo/drawing part is missing")
    if hashlib.sha256(archive.read(CERTIFIED_LOGO_PART)).hexdigest() != (
        CERTIFIED_LOGO_SHA256
    ):
        fail("quote metadata template certified logo bytes are unexpected")
    try:
        worksheet_relationships = ElementTree.fromstring(
            archive.read(worksheet_relationships_part(worksheet_part))
        )
        drawing = ElementTree.fromstring(archive.read(CERTIFIED_DRAWING_PART))
        drawing_relationships = ElementTree.fromstring(
            archive.read(CERTIFIED_DRAWING_RELS_PART)
        )
    except ElementTree.ParseError:
        fail("quote metadata template certified logo/drawing XML is malformed")

    drawing_reference = worksheet.find(f"{{{SPREADSHEET_NS}}}drawing")
    drawing_relationship_id = (
        drawing_reference.get(f"{{{OFFICE_REL_NS}}}id")
        if drawing_reference is not None
        else None
    )
    if (
        relationship_target(
            worksheet_relationships,
            drawing_relationship_id,
            DRAWING_REL_TYPE,
        )
        != CERTIFIED_DRAWING_TARGET
    ):
        fail("quote metadata template worksheet drawing relationship is broken")

    anchors = [
        child
        for child in drawing
        if child.tag
        in {
            f"{{{DRAWING_NS}}}oneCellAnchor",
            f"{{{DRAWING_NS}}}twoCellAnchor",
        }
    ]
    if len(anchors) != 1:
        fail("quote metadata template certified logo anchor is missing or ambiguous")
    anchor = anchors[0]
    column = anchor.find(f"{{{DRAWING_NS}}}from/{{{DRAWING_NS}}}col")
    row = anchor.find(f"{{{DRAWING_NS}}}from/{{{DRAWING_NS}}}row")
    extent = anchor.find(f"{{{DRAWING_NS}}}ext")
    blip = anchor.find(f".//{{{DRAWING_MAIN_NS}}}blip")
    image_relationship_id = (
        blip.get(f"{{{OFFICE_REL_NS}}}embed") if blip is not None else None
    )
    if (
        column is None
        or column.text != CERTIFIED_LOGO_COL
        or row is None
        or row.text != CERTIFIED_LOGO_ROW
        or extent is None
        or any(
            extent.get(name) != value for name, value in CERTIFIED_LOGO_EXTENT.items()
        )
    ):
        fail("quote metadata template certified logo anchor is unexpected")
    if (
        relationship_target(
            drawing_relationships,
            image_relationship_id,
            IMAGE_REL_TYPE,
        )
        != CERTIFIED_LOGO_TARGET
    ):
        fail("quote metadata template drawing image relationship is broken")


def validate_metadata_template_contract(
    template: Path,
    *,
    require_apparatus_header: bool = False,
) -> None:
    try:
        with zipfile.ZipFile(template) as archive:
            worksheet_part = worksheet_part_for_sheet(archive, SHEET_NAME)
            worksheet_xml = archive.read(worksheet_part)
    except OoxmlCellPatcherError as error:
        fail(f"quote metadata template contract could not be checked: {error}")
    except zipfile.BadZipFile:
        fail("quote metadata template is not a valid XLSX package")
    except OSError, KeyError:
        fail("quote metadata template contract could not be read")

    required_cells = {
        DOCUMENT_LINE_CELL,
        PAYER_CELL,
        OBJECT_CELL,
        BASIS_PROJECT_CELL,
        SECTION_CELL,
        VALIDITY_CELL,
        PAYMENT_DELIVERY_CELL,
        MANUFACTURING_CELL,
        VAT_RATE_CELL,
        VAT_LABEL_CELL,
        VAT_AMOUNT_CELL,
        *(
            f"{ITEM_NOTE_COLUMN}{row}"
            for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)
        ),
    }
    if require_apparatus_header:
        required_cells.add(APPARATUS_HEADER_CELL)
    ranges = cell_ranges(worksheet_xml)
    if any(len(ranges.get(coordinate, [])) != 1 for coordinate in required_cells):
        fail("quote metadata template is missing one or more certified cells")
    if formula_for_cell(worksheet_xml, VAT_LABEL_CELL) != VAT_LABEL_FORMULA:
        fail("quote metadata template VAT label formula is missing or unexpected")
    if formula_for_cell(worksheet_xml, VAT_AMOUNT_CELL) != VAT_AMOUNT_FORMULA:
        fail("quote metadata template VAT amount formula is missing or unexpected")
    try:
        worksheet = ElementTree.fromstring(worksheet_xml)
    except ElementTree.ParseError:
        fail("quote metadata template worksheet XML is malformed")
    sheet_properties = worksheet.find(f"{{{SPREADSHEET_NS}}}sheetPr")
    page_setup_properties = (
        sheet_properties.find(f"{{{SPREADSHEET_NS}}}pageSetUpPr")
        if sheet_properties is not None
        else None
    )
    page_setup = worksheet.find(f"{{{SPREADSHEET_NS}}}pageSetup")
    page_margins = worksheet.find(f"{{{SPREADSHEET_NS}}}pageMargins")
    if (
        page_setup_properties is None
        or page_setup_properties.get("fitToPage") != "1"
        or page_setup is None
        or any(
            page_setup.get(name) != value for name, value in PRINT_PAGE_SETUP.items()
        )
        or not page_margins_match(page_margins)
    ):
        fail("quote metadata template native page setup is missing or unexpected")
    try:
        with zipfile.ZipFile(template) as archive:
            validate_certified_logo_contract(archive, worksheet_part, worksheet)
    except zipfile.BadZipFile, OSError, KeyError:
        fail(
            "quote metadata template certified logo/drawing contract could not be read"
        )


def metadata_cell_updates(metadata: QuoteMetadata) -> dict[str, str | int | None]:
    document_date = metadata.document_date
    document_line = (
        f"Черновик счёта-КП № {metadata.document_number} от "
        f"«{document_date.day:02d}» {RUSSIAN_MONTHS[document_date.month]} "
        f"{document_date.year} года"
    )
    validity = (
        None
        if metadata.validity_period is None
        else f"Срок действия: {metadata.validity_period}."
    )
    return {
        DOCUMENT_LINE_CELL: document_line,
        PAYER_CELL: f"Плательщик: {metadata.payer_name}",
        OBJECT_CELL: (
            None if metadata.object_name is None else f"Объект: {metadata.object_name}"
        ),
        BASIS_PROJECT_CELL: (
            None
            if metadata.basis_project is None
            else f"Основание / проект: {metadata.basis_project}"
        ),
        VALIDITY_CELL: validity,
        PAYMENT_DELIVERY_CELL: (
            f"Условия оплаты: {metadata.payment_terms}. "
            f"Условия поставки: {metadata.delivery_terms}."
        ),
        MANUFACTURING_CELL: (
            "Ориентировочный срок изготовления: " f"{metadata.manufacturing_lead_time}."
        ),
        VAT_RATE_CELL: metadata.vat_rate_percent,
    }


def calculate_grand_total(rows: Sequence[Mapping[str, str]]) -> int:
    try:
        return sum(int(row["quantity"]) * int(row["unit_price_kzt"]) for row in rows)
    except KeyError, TypeError, ValueError:
        fail("validated commercial values could not be calculated safely")


def scale_form(value: int, forms: Sequence[str]) -> str:
    last_two = value % 100
    if 11 <= last_two <= 14:
        return forms[2]
    last_digit = value % 10
    if last_digit == 1:
        return forms[0]
    if 2 <= last_digit <= 4:
        return forms[1]
    return forms[2]


def triad_words(value: int, feminine: bool) -> list[str]:
    words: list[str] = []
    hundreds = value // 100
    remainder = value % 100
    if hundreds:
        words.append(HUNDREDS[hundreds])
    if 10 <= remainder <= 19:
        words.append(TEENS[remainder - 10])
        return words
    tens = remainder // 10
    ones = remainder % 10
    if tens:
        words.append(TENS[tens])
    if ones:
        words.append((ONES_FEMININE if feminine else ONES_MASCULINE)[ones])
    return words


def integer_to_russian_words(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail("grand total must be a non-negative integer")
    if value == 0:
        return "ноль"

    triads: list[int] = []
    remaining = value
    while remaining:
        triads.append(remaining % 1000)
        remaining //= 1000
    if len(triads) > len(SCALE_FORMS):
        fail("grand total exceeds the supported Russian wording range")

    words: list[str] = []
    for scale_index in range(len(triads) - 1, -1, -1):
        triad = triads[scale_index]
        if triad == 0:
            continue
        singular, paucal, plural, feminine = SCALE_FORMS[scale_index]
        words.extend(triad_words(triad, feminine))
        if scale_index:
            words.append(scale_form(triad, (singular, paucal, plural)))
    return " ".join(words)


def amount_words_text(grand_total: int) -> str:
    words = integer_to_russian_words(grand_total)
    capitalized_words = words[:1].upper() + words[1:]
    return f"Всего прописью: {capitalized_words} тенге 00 тиын"


def visual_line_count(value: str, width: int) -> int:
    return sum(max(1, (len(line) + width - 1) // width) for line in value.split("\n"))


def estimate_item_row_height(
    row: Mapping[str, str], note_text: str | None = None
) -> int:
    visual_lines = max(
        visual_line_count(row[field], width)
        for field, width in ROW_HEIGHT_TEXT_WIDTHS.items()
    )
    if note_text is not None:
        visual_lines = max(visual_lines, visual_line_count(note_text, ITEM_NOTE_WIDTH))
    if visual_lines <= 1:
        return BASE_ITEM_ROW_HEIGHT
    return min(
        MAX_ITEM_ROW_HEIGHT,
        visual_lines * ITEM_ROW_VISUAL_LINE_HEIGHT + ITEM_ROW_VERTICAL_PADDING,
    )


def build_cell_updates(
    rows: Sequence[Mapping[str, str]],
    amount_text: str,
    metadata: QuoteMetadata | None = None,
) -> dict[str, str | int | None]:
    updates: dict[str, str | int | None] = {
        f"C{AMOUNT_WORDS_ROW}": amount_text,
    }
    for offset, item in enumerate(rows):
        excel_row = ITEM_START_ROW + offset
        updates[f"C{excel_row}"] = item["name"]
        updates[f"D{excel_row}"] = item["unit"]
        updates[f"E{excel_row}"] = int(item["quantity"])
        updates[f"F{excel_row}"] = item["instruments_and_devices"]
        updates[f"G{excel_row}"] = item["cabinet_type_dimensions_material"]
        updates[f"H{excel_row}"] = int(item["unit_price_kzt"])

    for excel_row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1):
        for column in "CDEFGH":
            updates[f"{column}{excel_row}"] = None
    if metadata is not None:
        updates.update(metadata_cell_updates(metadata))
        if metadata.object_name is None and metadata.basis_project is None:
            updates[SECTION_CELL] = None
        for note in metadata.item_notes:
            excel_row = ITEM_START_ROW + note.item_number - 1
            updates[f"{ITEM_NOTE_COLUMN}{excel_row}"] = note.text
    return updates


def build_row_hidden_updates(
    rows: Sequence[Mapping[str, str]], metadata: QuoteMetadata | None = None
) -> dict[int, bool]:
    first_unused_row = ITEM_START_ROW + len(rows)
    updates = {
        row: row >= first_unused_row for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)
    }
    if (
        metadata is not None
        and metadata.object_name is None
        and metadata.basis_project is None
    ):
        updates[SECTION_ROW] = True
    return updates


def build_row_height_updates(
    rows: Sequence[Mapping[str, str]], metadata: QuoteMetadata | None = None
) -> dict[int, int]:
    notes = (
        {note.item_number: note.text for note in metadata.item_notes}
        if metadata is not None
        else {}
    )
    updates = {
        ITEM_START_ROW + offset: estimate_item_row_height(item, notes.get(offset + 1))
        for offset, item in enumerate(rows)
    }
    updates.update(
        {
            row: BASE_ITEM_ROW_HEIGHT
            for row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1)
        }
    )
    return updates


def candidate_path_for(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid.uuid4().hex}.candidate.xlsx")


def generate_candidate(
    template: Path,
    candidate: Path,
    rows: Sequence[Mapping[str, str]],
    amount_text: str,
    metadata: QuoteMetadata | None = None,
) -> None:
    try:
        patch_existing_cells(
            template=template,
            output=candidate,
            sheet_name=SHEET_NAME,
            updates=build_cell_updates(rows, amount_text, metadata),
            row_hidden_updates=build_row_hidden_updates(rows, metadata),
            row_height_updates=build_row_height_updates(rows, metadata),
        )
    except OoxmlCellPatcherError as error:
        fail(f"candidate generation failed: {error}")


def number_format_coordinates() -> tuple[str, ...]:
    return tuple(
        [
            *(f"H{row}" for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)),
            *(f"I{row}" for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)),
            f"I{TOTAL_ROW}",
        ]
    )


def cell_style_id(cell_xml: bytes, coordinate: str) -> int:
    try:
        cell = ElementTree.fromstring(cell_xml)
        style_id = int(cell.get("s", "0"))
    except ElementTree.ParseError, ValueError:
        fail(f"presentation style could not be read for {coordinate}")
    if style_id < 0:
        fail(f"presentation style is invalid for {coordinate}")
    return style_id


def style_cell_xml(cell_xml: bytes, style_id: int) -> bytes:
    start_tag_end = find_markup_end(cell_xml, 0)
    start_tag = cell_xml[:start_tag_end]
    replacement = f' s="{style_id}"'.encode("ascii")
    if CELL_STYLE_RE.search(start_tag):
        styled_start_tag = CELL_STYLE_RE.sub(replacement, start_tag, count=1)
    else:
        closing = b"/>" if start_tag.endswith(b"/>") else b">"
        styled_start_tag = start_tag[: -len(closing)] + replacement + closing
    return styled_start_tag + cell_xml[start_tag_end:]


def apparatus_header_cell_xml(cell_xml: bytes, manufacturer: str) -> bytes:
    try:
        cell = ElementTree.fromstring(cell_xml)
    except ElementTree.ParseError:
        fail("apparatus manufacturer header cell XML is invalid")
    for child in list(cell):
        if child.tag in {
            "f",
            "v",
            "is",
            f"{{{SPREADSHEET_NS}}}f",
            f"{{{SPREADSHEET_NS}}}v",
            f"{{{SPREADSHEET_NS}}}is",
        }:
            cell.remove(child)
    cell.set("t", "inlineStr")
    inline_string = ElementTree.SubElement(cell, f"{{{SPREADSHEET_NS}}}is")
    heading_run = ElementTree.SubElement(inline_string, f"{{{SPREADSHEET_NS}}}r")
    heading_text = ElementTree.SubElement(
        heading_run,
        f"{{{SPREADSHEET_NS}}}t",
    )
    heading_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    heading_text.text = APPARATUS_HEADER_PREFIX
    manufacturer_run = ElementTree.SubElement(
        inline_string,
        f"{{{SPREADSHEET_NS}}}r",
    )
    run_properties = ElementTree.SubElement(
        manufacturer_run,
        f"{{{SPREADSHEET_NS}}}rPr",
    )
    ElementTree.SubElement(run_properties, f"{{{SPREADSHEET_NS}}}b")
    ElementTree.SubElement(run_properties, f"{{{SPREADSHEET_NS}}}u")
    ElementTree.SubElement(
        run_properties,
        f"{{{SPREADSHEET_NS}}}sz",
        {"val": "12"},
    )
    ElementTree.SubElement(
        run_properties,
        f"{{{SPREADSHEET_NS}}}color",
        {"indexed": "10"},
    )
    ElementTree.SubElement(
        run_properties,
        f"{{{SPREADSHEET_NS}}}rFont",
        {"val": "Times New Roman"},
    )
    ElementTree.SubElement(
        run_properties,
        f"{{{SPREADSHEET_NS}}}family",
        {"val": "1"},
    )
    ElementTree.SubElement(
        run_properties,
        f"{{{SPREADSHEET_NS}}}charset",
        {"val": "204"},
    )
    manufacturer_text = ElementTree.SubElement(
        manufacturer_run,
        f"{{{SPREADSHEET_NS}}}t",
    )
    manufacturer_text.text = APPARATUS_MANUFACTURER_PREFIX + manufacturer
    return cast(bytes, ElementTree.tostring(cell, encoding="utf-8"))


def worksheet_with_apparatus_header(
    worksheet_xml: bytes,
    manufacturer: str,
) -> bytes:
    matches = cell_ranges(worksheet_xml).get(APPARATUS_HEADER_CELL, [])
    if len(matches) != 1:
        fail("apparatus manufacturer header cell is missing or duplicated")
    cell_range = matches[0]
    replacement = apparatus_header_cell_xml(cell_range.xml, manufacturer)
    return (
        worksheet_xml[: cell_range.start]
        + replacement
        + worksheet_xml[cell_range.end :]
    )


def styles_with_number_format(
    styles_xml: bytes,
    base_style_ids: set[int],
) -> tuple[bytes, dict[int, int]]:
    try:
        root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError:
        fail("presentation styles XML is invalid")
    cell_xfs = root.find(f"{{{SPREADSHEET_NS}}}cellXfs")
    if cell_xfs is None:
        fail("presentation styles cellXfs element is missing")
    xfs = list(cell_xfs.findall(f"{{{SPREADSHEET_NS}}}xf"))
    if cell_xfs.get("count") != str(len(xfs)):
        fail("presentation styles count is inconsistent")

    style_map: dict[int, int] = {}
    cloned_xfs: list[bytes] = []
    next_style_id = len(xfs)
    ElementTree.register_namespace("", SPREADSHEET_NS)
    for base_style_id in sorted(base_style_ids):
        if base_style_id >= len(xfs):
            fail("presentation source style is out of range")
        base_xf = xfs[base_style_id]
        if base_xf.get("numFmtId") == NUMBER_FORMAT_ID:
            style_map[base_style_id] = base_style_id
            continue
        formatted_xf = copy.deepcopy(base_xf)
        formatted_xf.set("numFmtId", NUMBER_FORMAT_ID)
        formatted_xf.set("applyNumberFormat", "1")
        cloned_xfs.append(ElementTree.tostring(formatted_xf, encoding="utf-8"))
        style_map[base_style_id] = next_style_id
        next_style_id += 1

    if not cloned_xfs:
        return styles_xml, style_map

    container = CELL_XFS_CONTAINER_RE.search(styles_xml)
    if container is None:
        fail("presentation styles cellXfs bytes are unsupported")
    start_tag_end = styles_xml.find(b">", container.start()) + 1
    if start_tag_end <= 0 or start_tag_end > container.end():
        fail("presentation styles cellXfs start tag is invalid")
    start_tag = styles_xml[container.start() : start_tag_end]
    if not COUNT_ATTR_RE.search(start_tag):
        fail("presentation styles count attribute is missing")
    styled_start_tag = COUNT_ATTR_RE.sub(
        f' count="{next_style_id}"'.encode("ascii"),
        start_tag,
        count=1,
    )
    body_end = container.end("body")
    return (
        styles_xml[: container.start()]
        + styled_start_tag
        + styles_xml[start_tag_end:body_end]
        + b"".join(cloned_xfs)
        + styles_xml[body_end:]
    ), style_map


def worksheet_with_number_formats(
    worksheet_xml: bytes,
    styles_xml: bytes,
) -> tuple[bytes, bytes]:
    ranges = cell_ranges(worksheet_xml)
    selected: dict[str, Any] = {}
    base_style_ids: set[int] = set()
    for coordinate in number_format_coordinates():
        matches = ranges.get(coordinate, [])
        if len(matches) != 1:
            fail(f"presentation target cell is missing or duplicated: {coordinate}")
        cell_range = matches[0]
        base_style_id = cell_style_id(cell_range.xml, coordinate)
        selected[coordinate] = (cell_range, base_style_id)
        base_style_ids.add(base_style_id)

    styled_styles_xml, style_map = styles_with_number_format(
        styles_xml,
        base_style_ids,
    )
    replacements: list[tuple[int, int, bytes]] = []
    for cell_range, base_style_id in selected.values():
        replacements.append(
            (
                cell_range.start,
                cell_range.end,
                style_cell_xml(cell_range.xml, style_map[base_style_id]),
            )
        )
    ensure_non_overlapping_replacements(replacements)
    styled_worksheet = bytearray(worksheet_xml)
    for start, end, replacement in sorted(replacements, reverse=True):
        styled_worksheet[start:end] = replacement
    return bytes(styled_worksheet), styled_styles_xml


def verify_number_formats(worksheet_xml: bytes, styles_xml: bytes) -> None:
    try:
        styles_root = ElementTree.fromstring(styles_xml)
    except ElementTree.ParseError:
        fail("formatted styles XML is invalid")
    cell_xfs = styles_root.find(f"{{{SPREADSHEET_NS}}}cellXfs")
    if cell_xfs is None:
        fail("formatted styles cellXfs element is missing")
    xfs = list(cell_xfs.findall(f"{{{SPREADSHEET_NS}}}xf"))
    ranges = cell_ranges(worksheet_xml)
    for coordinate in number_format_coordinates():
        matches = ranges.get(coordinate, [])
        if len(matches) != 1:
            fail(f"formatted target cell is missing or duplicated: {coordinate}")
        style_id = cell_style_id(matches[0].xml, coordinate)
        if style_id >= len(xfs) or xfs[style_id].get("numFmtId") != NUMBER_FORMAT_ID:
            fail(f"number format was not applied to {coordinate}")


def write_presentation_package(
    parts: Mapping[str, bytes],
    worksheet_part: str,
    worksheet_xml: bytes,
    styles_xml: bytes,
    output: Path,
) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            if name == worksheet_part:
                content = worksheet_xml
            elif name == STYLES_PART:
                content = styles_xml
            archive.writestr(name, content)


def verify_presentation_package(
    before_parts: Mapping[str, bytes],
    output: Path,
    worksheet_part: str,
) -> None:
    after_parts = archive_bytes(output)
    if set(after_parts) != set(before_parts):
        fail("presentation XLSX parts differ from the candidate")
    allowed_changes = {worksheet_part, STYLES_PART}
    for name, content in before_parts.items():
        if name not in allowed_changes and after_parts[name] != content:
            fail(f"presentation changed an unexpected XLSX part: {name}")
    verify_number_formats(
        after_parts[worksheet_part],
        after_parts[STYLES_PART],
    )


def apply_number_formats(
    candidate: Path,
    metadata: QuoteMetadata | None = None,
) -> None:
    temporary_output = candidate.with_name(
        f".{candidate.stem}.{uuid.uuid4().hex}.presentation.tmp.xlsx"
    )
    try:
        try:
            with zipfile.ZipFile(candidate) as archive:
                worksheet_part = worksheet_part_for_sheet(archive, SHEET_NAME)
        except zipfile.BadZipFile as error:
            fail(f"presentation candidate is not a valid XLSX package: {error}")
        parts = archive_bytes(candidate)
        if worksheet_part not in parts or STYLES_PART not in parts:
            fail("presentation candidate is missing required XLSX parts")
        worksheet_xml = parts[worksheet_part]
        if metadata is not None and metadata.apparatus_manufacturer is not None:
            worksheet_xml = worksheet_with_apparatus_header(
                worksheet_xml,
                metadata.apparatus_manufacturer,
            )
        worksheet_xml, styles_xml = worksheet_with_number_formats(
            worksheet_xml,
            parts[STYLES_PART],
        )
        write_presentation_package(
            parts,
            worksheet_part,
            worksheet_xml,
            styles_xml,
            temporary_output,
        )
        verify_presentation_package(parts, temporary_output, worksheet_part)
        temporary_output.replace(candidate)
    except OoxmlCellPatcherError as error:
        fail(f"presentation formatting failed: {error}")
    except OSError:
        fail("presentation formatting could not update the candidate safely")
    finally:
        if temporary_output.exists():
            temporary_output.unlink()


def publish_candidate(candidate: Path, output: Path) -> None:
    if output.exists():
        fail(f"output already exists: {output}")
    try:
        candidate.rename(output)
    except OSError:
        fail("candidate could not be published atomically")


def remove_candidate(candidate: Path) -> None:
    if not candidate.exists():
        return
    try:
        candidate.unlink()
    except OSError:
        fail("temporary candidate could not be removed")


def safe_failures(failures: Sequence[str]) -> list[str]:
    return list(failures) if failures else ["unspecified validation failure"]


def run_commercial_writer(
    commercial_csv: Path,
    template: Path,
    template_capacity: int,
    output: Path,
    quote_metadata_json: Path | None = None,
) -> CommercialWriterResult:
    csv_path = resolved(commercial_csv)
    template_path = resolved(template)
    output_path = resolved(output)
    result = CommercialWriterResult(csv_path, template_path, output_path)

    preflight_result = commercial_preflight.preflight(csv_path)
    result.row_count = preflight_result.row_count
    if preflight_result.status != "PASS":
        result.failures.extend(safe_failures(preflight_result.failures))
        return result
    result.checks["commercial preflight"] = "pass"

    try:
        template_path, output_path = validate_generation_paths(
            template_path,
            output_path,
            template_capacity,
        )
        result.template = template_path
        result.output = output_path
        result.checks["capacity100 profile"] = "pass"
        result.checks["output path"] = "pass"
        rows = load_commercial_rows(csv_path)
        grand_total = calculate_grand_total(rows)
        amount_text = amount_words_text(grand_total)
        metadata = None
        if quote_metadata_json is not None:
            metadata = load_quote_metadata(resolved(quote_metadata_json), len(rows))
            validate_metadata_template_contract(
                template_path,
                require_apparatus_header=(metadata.apparatus_manufacturer is not None),
            )
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result

    candidate = candidate_path_for(output_path)
    published = False
    try:
        generate_candidate(template_path, candidate, rows, amount_text, metadata)
        result.checks["candidate generation"] = "pass"

        apply_number_formats(candidate, metadata)
        result.checks["presentation formatting"] = "pass"

        reconciliation_result = commercial_reconciliation.reconcile(
            csv_path,
            candidate,
            template_capacity,
        )
        result.reconciliation_checks = dict(reconciliation_result.checks)
        if reconciliation_result.status != "PASS":
            result.failures.extend(safe_failures(reconciliation_result.failures))
            return result
        result.checks["commercial reconciliation"] = "pass"

        publish_candidate(candidate, output_path)
        published = True
        result.checks["atomic publish"] = "pass"
        result.status = "PASS"
        result.next_action = PASS_NEXT
        return result
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result
    except Exception:
        result.failures.append("unexpected internal writer failure")
        return result
    finally:
        if not published and candidate.exists():
            try:
                remove_candidate(candidate)
            except CommercialWriterError as error:
                result.failures.append(str(error))


def format_report(result: CommercialWriterResult) -> str:
    lines = [
        "COMMERCIAL_QUOTE_WRITER_REPORT_START",
        "",
        "Mode:",
        "internal draft only",
        "",
        "Input CSV:",
        str(result.commercial_csv),
        "",
        "Output XLSX:",
        str(result.output),
        "",
        "Status:",
        result.status,
        "",
        "Rows:",
        str(result.row_count),
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(
        f"reconciliation {name}: {status}"
        for name, status in result.reconciliation_checks.items()
    )
    lines.extend(["", "Failures:"])
    lines.extend(result.failures if result.failures else ["none"])
    lines.extend(
        [
            "",
            "Next:",
            result.next_action,
            "",
            "Manual Igor check:",
            "required",
            "",
            "Human Approval:",
            "separate approval required",
            "",
            "COMMERCIAL_QUOTE_WRITER_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_commercial_writer(
        args.commercial_csv,
        args.template,
        args.template_capacity,
        args.output,
        args.quote_metadata_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
