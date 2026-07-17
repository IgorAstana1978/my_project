"""Create a reconciled multi-item client XLSX from an approved internal draft."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import uuid
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OOXML_PATCHER = PROJECT_ROOT / "scripts" / "ooxml_cell_patcher.py"
SHEET_NAME = "Счёт-КП шаблон"
SCHEMA_VERSION = "checked_clientization_approval.v0.2"
ITEM_START_ROW = 17
ITEM_END_ROW = 116
TOTAL_ROW = 117
VAT_RATE_CELL = "A131"
VAT_LABEL_CELL = "H118"
VAT_AMOUNT_CELL = "I118"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"main": SPREADSHEET_NS}
SHARED_STRINGS_PART = "xl/sharedStrings.xml"
REPORT_START = "CHECKED_CLIENTIZATION_REPORT_START"
REPORT_END = "CHECKED_CLIENTIZATION_REPORT_END"
MODE = "multi-item client XLSX candidate only"
NEXT_ACTION = "manual Igor review; separate sending approval remains required"
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
MONEY_RE = re.compile(r"[0-9]+\.[0-9]{2}\Z")

ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "approval_id",
        "approved_by",
        "approved_at",
        "internal_draft_xlsx_sha256",
        "invoice_number",
        "invoice_date",
        "payer_name",
        "apparatus_manufacturer",
        "vat_rate_percent",
        "vat_amount_kzt",
        "commercial_total_kzt",
        "payment_terms",
        "delivery_terms",
        "manufacturing_lead_time",
        "manufacturing_lead_time_approved_by",
        "manufacturing_lead_time_approved_at",
        "manufacturing_lead_time_approval_role",
        "validity_period",
        "amount_words_text",
        "commercial_price_approved",
        "clientization_approved",
        "sending_approved",
        "items",
    }
)
ITEM_FIELDS = frozenset(
    {
        "row",
        "source_name",
        "client_name",
        "unit",
        "quantity",
        "instruments_and_devices",
        "cabinet_type_dimensions_material",
        "unit_price_kzt",
        "source_note",
        "client_note",
    }
)
GUARD_CELLS = (
    "B13",
    "G9",
    "G10",
    "G11",
    "G12",
    "G13",
    "C124",
    "C125",
    "B129",
)
FORBIDDEN_TOKENS = (
    "черновик",
    "внимание!",
    "клиенту не отправлять",
    "перед отправкой проверить",
    "закупку и цех",
    "внутренним черновиком",
    "спецификация и условия подлежат проверке",
    "дата проверки:",
)
VAT_LABEL_FORMULA = (
    'IF(NOT(ISNUMBER($A$131)),"","В том числе НДС "' '&TEXT($A$131,"0")&"%")'
)
VAT_AMOUNT_FORMULA = (
    'IF(OR(NOT(ISNUMBER(I117)),NOT(ISNUMBER($A$131))),"",' "I117*$A$131/(100+$A$131))"
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


class ClientizationError(Exception):
    """Expected fail-closed clientization error."""


@dataclass(frozen=True)
class ApprovedItem:
    row: int
    source_name: str
    client_name: str
    unit: str
    quantity: int
    instruments_and_devices: str
    cabinet_type_dimensions_material: str
    unit_price_kzt: int
    source_note: str | None
    client_note: str | None

    @property
    def line_total_kzt(self) -> int:
        return self.quantity * self.unit_price_kzt


@dataclass(frozen=True)
class Approval:
    approval_id: str
    approved_by: str
    approved_at: datetime
    internal_draft_sha256: str
    invoice_number: str
    invoice_date: date
    payer_name: str
    apparatus_manufacturer: str
    vat_rate_percent: int
    vat_amount_kzt: Decimal
    commercial_total_kzt: int
    payment_terms: str
    delivery_terms: str
    manufacturing_lead_time: str
    manufacturing_lead_time_approved_by: str
    manufacturing_lead_time_approved_at: datetime
    manufacturing_lead_time_approval_role: str
    validity_period: str | None
    amount_words_text: str
    items: tuple[ApprovedItem, ...]


@dataclass(frozen=True)
class CellData:
    value: str | int | None
    formula: str | None


@dataclass(frozen=True)
class WorkbookSnapshot:
    parts: Mapping[str, bytes]
    worksheet_part: str
    cells: Mapping[str, CellData]


@dataclass
class ClientizationResult:
    internal_draft: Path
    approval_json: Path
    output_xlsx: Path
    status: str = "FAIL"
    item_count: int = 0
    approval_id: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    manufacturing_lead_time_approved_by: str | None = None
    manufacturing_lead_time_approved_at: str | None = None
    manufacturing_lead_time_approval_role: str | None = None
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "path policy": "fail",
            "approval schema": "fail",
            "source SHA-256": "fail",
            "source reconciliation": "fail",
            "candidate generation": "fail",
            "guard sanitation": "fail",
            "candidate reconciliation": "fail",
            "input immutability": "fail",
            "atomic publish": "fail",
            "safety boundaries": "fail",
        }
    )
    failures: list[str] = field(default_factory=list)


def fail(message: str) -> NoReturn:
    raise ClientizationError(message)


def load_sibling_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        fail(f"required helper could not be loaded: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ooxml_patcher = cast(
    Any,
    load_sibling_module("ooxml_cell_patcher_for_checked_clientization", OOXML_PATCHER),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a checked multi-item client XLSX candidate."
    )
    parser.add_argument("--internal-draft-xlsx", required=True, type=Path)
    parser.add_argument("--approval-json", required=True, type=Path)
    parser.add_argument("--output-xlsx", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_string(data: Mapping[str, Any], field_name: str, label: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        fail(f"{label} field must be a non-empty string: {field_name}")
    return value


def positive_int(data: Mapping[str, Any], field_name: str, label: str) -> int:
    value = data.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        fail(f"{label} field must be a positive integer: {field_name}")
    return value


def parse_timezone_datetime(value: str, label: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        fail(f"{label} is not valid ISO 8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{label} must include a timezone")
    return parsed


def nullable_note(data: Mapping[str, Any], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        fail(f"approval item {field_name} must be null or a non-empty string")
    return value


def parse_item(raw: object) -> ApprovedItem:
    if not isinstance(raw, Mapping):
        fail("approval item must be an object")
    item = cast(Mapping[str, Any], raw)
    if set(item) != ITEM_FIELDS:
        fail("approval item fields do not match the strict schema")
    source_note = nullable_note(item, "source_note")
    client_note = nullable_note(item, "client_note")
    if (source_note is None) != (client_note is None):
        fail("approval item source_note and client_note must both be null or strings")
    if client_note is not None and contains_forbidden(client_note):
        fail("approval item client_note contains an internal forbidden token")
    return ApprovedItem(
        row=positive_int(item, "row", "approval item"),
        source_name=required_string(item, "source_name", "approval item"),
        client_name=required_string(item, "client_name", "approval item"),
        unit=required_string(item, "unit", "approval item"),
        quantity=positive_int(item, "quantity", "approval item"),
        instruments_and_devices=required_string(
            item, "instruments_and_devices", "approval item"
        ),
        cabinet_type_dimensions_material=required_string(
            item, "cabinet_type_dimensions_material", "approval item"
        ),
        unit_price_kzt=positive_int(item, "unit_price_kzt", "approval item"),
        source_note=source_note,
        client_note=client_note,
    )


def parse_approval(path: Path) -> Approval:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):  # fmt: skip
        fail("approval JSON could not be read as strict UTF-8 JSON")
    if not isinstance(raw, Mapping):
        fail("approval JSON root must be an object")
    data = cast(Mapping[str, Any], raw)
    if set(data) != ROOT_FIELDS:
        fail("approval fields do not match the strict schema")
    if data.get("schema_version") != SCHEMA_VERSION:
        fail("approval schema_version is unsupported")
    approval_id = required_string(data, "approval_id", "approval")
    approved_by = required_string(data, "approved_by", "approval")
    approved_at = parse_timezone_datetime(
        required_string(data, "approved_at", "approval"),
        "approval approved_at",
    )
    lead_time_approved_by = required_string(
        data, "manufacturing_lead_time_approved_by", "approval"
    )
    lead_time_approved_at = parse_timezone_datetime(
        required_string(data, "manufacturing_lead_time_approved_at", "approval"),
        "approval manufacturing_lead_time_approved_at",
    )
    lead_time_approval_role = required_string(
        data, "manufacturing_lead_time_approval_role", "approval"
    )
    if lead_time_approval_role != "pto_engineer":
        fail("approval manufacturing_lead_time_approval_role must be pto_engineer")
    source_hash = required_string(data, "internal_draft_xlsx_sha256", "approval")
    if HASH_RE.fullmatch(source_hash) is None:
        fail("approval internal draft SHA-256 must be lowercase hexadecimal")
    if data.get("commercial_price_approved") != "yes":
        fail("approval commercial_price_approved must be exact yes")
    if data.get("clientization_approved") != "yes":
        fail("approval clientization_approved must be exact yes")
    if data.get("sending_approved") != "no":
        fail("approval sending_approved must remain exact no")
    try:
        invoice_date = date.fromisoformat(
            required_string(data, "invoice_date", "approval")
        )
    except ValueError:
        fail("approval invoice_date must be YYYY-MM-DD")
    vat_text = required_string(data, "vat_amount_kzt", "approval")
    if MONEY_RE.fullmatch(vat_text) is None:
        fail("approval vat_amount_kzt must use digits and two decimals")
    try:
        vat_amount = Decimal(vat_text)
    except InvalidOperation:
        fail("approval vat_amount_kzt is invalid")
    raw_validity = data.get("validity_period")
    if raw_validity is not None and (
        not isinstance(raw_validity, str) or raw_validity.strip() == ""
    ):
        fail("approval validity_period must be null or a non-empty string")
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        fail("approval items must be a non-empty array")
    items = tuple(parse_item(item) for item in raw_items)
    rows = [item.row for item in items]
    if rows != list(range(ITEM_START_ROW, ITEM_START_ROW + len(items))):
        fail("approval item rows must be contiguous from row 17")
    if rows[-1] > ITEM_END_ROW:
        fail("approval item rows exceed the certified capacity")
    total = positive_int(data, "commercial_total_kzt", "approval")
    if sum(item.line_total_kzt for item in items) != total:
        fail("approval item arithmetic does not match commercial_total_kzt")
    vat_rate = positive_int(data, "vat_rate_percent", "approval")
    calculated_vat = (
        Decimal(total) * Decimal(vat_rate) / Decimal(100 + vat_rate)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if calculated_vat != vat_amount:
        fail("approval VAT arithmetic does not match vat_amount_kzt")
    return Approval(
        approval_id=approval_id,
        approved_by=approved_by,
        approved_at=approved_at,
        internal_draft_sha256=source_hash,
        invoice_number=required_string(data, "invoice_number", "approval"),
        invoice_date=invoice_date,
        payer_name=required_string(data, "payer_name", "approval"),
        apparatus_manufacturer=required_string(
            data, "apparatus_manufacturer", "approval"
        ),
        vat_rate_percent=vat_rate,
        vat_amount_kzt=vat_amount,
        commercial_total_kzt=total,
        payment_terms=required_string(data, "payment_terms", "approval"),
        delivery_terms=required_string(data, "delivery_terms", "approval"),
        manufacturing_lead_time=required_string(
            data, "manufacturing_lead_time", "approval"
        ),
        manufacturing_lead_time_approved_by=lead_time_approved_by,
        manufacturing_lead_time_approved_at=lead_time_approved_at,
        manufacturing_lead_time_approval_role=lead_time_approval_role,
        validity_period=cast(str | None, raw_validity),
        amount_words_text=required_string(data, "amount_words_text", "approval"),
        items=items,
    )


def workbook_sheet_names(parts: Mapping[str, bytes]) -> list[str]:
    try:
        workbook = ElementTree.fromstring(parts["xl/workbook.xml"])
    except (KeyError, ElementTree.ParseError):  # fmt: skip
        fail("internal draft workbook metadata is missing or invalid")
    return [
        sheet.get("name", "")
        for sheet in workbook.findall("main:sheets/main:sheet", NS)
    ]


def rich_text(element: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{SPREADSHEET_NS}}}t"))


def worksheet_cells(
    worksheet_xml: bytes,
    shared_strings: Sequence[str],
) -> dict[str, CellData]:
    try:
        worksheet = ElementTree.fromstring(worksheet_xml)
    except ElementTree.ParseError:
        fail("internal draft worksheet XML is invalid")
    cells: dict[str, CellData] = {}
    for cell in worksheet.findall(".//main:sheetData/main:row/main:c", NS):
        coordinate = cell.get("r", "").upper()
        if coordinate == "" or coordinate in cells:
            fail("internal draft contains an invalid or duplicate cell")
        value_node = cell.find("main:v", NS)
        formula_node = cell.find("main:f", NS)
        raw_value = None if value_node is None else value_node.text
        cell_type = cell.get("t")
        value: str | int | None = raw_value
        if cell_type == "s" and raw_value is not None:
            try:
                value = shared_strings[int(raw_value)]
            except (IndexError, ValueError):  # fmt: skip
                fail(f"internal draft shared string index is invalid: {coordinate}")
        elif cell_type == "inlineStr":
            inline = cell.find("main:is", NS)
            value = None if inline is None else rich_text(inline)
        elif (
            cell_type in (None, "n")
            and raw_value is not None
            and re.fullmatch(r"-?[0-9]+", raw_value)
        ):
            value = int(raw_value)
        cells[coordinate] = CellData(
            value=value,
            formula=None if formula_node is None else formula_node.text,
        )
    return cells


def load_snapshot(path: Path) -> WorkbookSnapshot:
    try:
        parts = ooxml_patcher.archive_bytes(path)
        with zipfile.ZipFile(path) as archive:
            worksheet_part = ooxml_patcher.worksheet_part_for_sheet(archive, SHEET_NAME)
    # fmt: off
    except (
        OSError,
        zipfile.BadZipFile,
        ooxml_patcher.OoxmlCellPatcherError,
    ):
        # fmt: on
        fail("internal draft could not be opened as a valid XLSX")
    shared_strings: list[str] = []
    if SHARED_STRINGS_PART in parts:
        try:
            shared_root = ElementTree.fromstring(parts[SHARED_STRINGS_PART])
        except ElementTree.ParseError:
            fail("internal draft shared strings XML is invalid")
        shared_strings = [
            rich_text(item) for item in shared_root.findall("main:si", NS)
        ]
    if worksheet_part not in parts:
        fail("internal draft worksheet part is missing")
    return WorkbookSnapshot(
        parts=parts,
        worksheet_part=worksheet_part,
        cells=worksheet_cells(parts[worksheet_part], shared_strings),
    )


def cell(snapshot: WorkbookSnapshot, coordinate: str) -> CellData:
    value = snapshot.cells.get(coordinate)
    if value is None:
        fail(f"certified cell is missing: {coordinate}")
    return value


def item_formula(row: int) -> str:
    return f'IF(OR(E{row}="",H{row}=""),"",' f'IFERROR(E{row}*H{row},"нужно уточнить"))'


def russian_date(value: date) -> str:
    return f"«{value.day:02d}» {RUSSIAN_MONTHS[value.month]} {value.year} года"


def expected_internal_title(approval: Approval) -> str:
    return (
        f"Черновик счёта-КП № {approval.invoice_number} от "
        f"{russian_date(approval.invoice_date)}"
    )


def expected_client_title(approval: Approval) -> str:
    return (
        f"Счёт-КП № {approval.invoice_number} от "
        f"{russian_date(approval.invoice_date)}"
    )


def reconcile_source(snapshot: WorkbookSnapshot, approval: Approval) -> None:
    if workbook_sheet_names(snapshot.parts) != [SHEET_NAME]:
        fail("internal draft must contain exactly the certified worksheet")
    forbidden_parts = [
        name
        for name in snapshot.parts
        if any(
            token in name.casefold()
            for token in ("vba", "externallink", "activex", "oleobject", "embedding")
        )
    ]
    if forbidden_parts:
        fail("internal draft contains a forbidden active or external OOXML part")
    if cell(snapshot, "B9").value != expected_internal_title(approval):
        fail("internal draft invoice title does not match approval")
    if cell(snapshot, "B10").value != f"Плательщик: {approval.payer_name}":
        fail("internal draft payer does not match approval")
    apparatus_header = cell(snapshot, "F15").value
    if not isinstance(apparatus_header, str) or (
        approval.apparatus_manufacturer.casefold() not in apparatus_header.casefold()
    ):
        fail("internal draft apparatus manufacturer does not match approval")
    for item in approval.items:
        row = item.row
        expected_values: dict[str, object] = {
            f"B{row}": row - ITEM_START_ROW + 1,
            f"C{row}": item.source_name,
            f"D{row}": item.unit,
            f"E{row}": item.quantity,
            f"F{row}": item.instruments_and_devices,
            f"G{row}": item.cabinet_type_dimensions_material,
            f"H{row}": item.unit_price_kzt,
        }
        for coordinate, expected in expected_values.items():
            if cell(snapshot, coordinate).value != expected:
                fail(f"internal draft item mismatch: {coordinate}")
        if cell(snapshot, f"I{row}").formula != item_formula(row):
            fail(f"internal draft item formula mismatch: I{row}")
        source_note = cell(snapshot, f"J{row}")
        if item.source_note is None:
            if source_note.formula != '""' or source_note.value not in (None, ""):
                fail(f"internal draft source note must use empty formula: J{row}")
        elif source_note.value != item.source_note or source_note.formula is not None:
            fail(f"internal draft source note mismatch: J{row}")
    last_approved_row = approval.items[-1].row
    for row in range(ITEM_START_ROW, ITEM_END_ROW + 1):
        if cell(snapshot, f"B{row}").value != row - ITEM_START_ROW + 1:
            fail(f"internal draft certified row number mismatch: B{row}")
        if cell(snapshot, f"I{row}").formula != item_formula(row):
            fail(f"internal draft certified item formula mismatch: I{row}")
    for row in range(last_approved_row + 1, ITEM_END_ROW + 1):
        note = cell(snapshot, f"J{row}")
        if note.formula != '""' or note.value not in (None, ""):
            fail(f"internal draft trailing note mismatch: J{row}")
        for column in "CDEFGH":
            extra = cell(snapshot, f"{column}{row}")
            if extra.value not in (None, "") or extra.formula is not None:
                fail(f"internal draft contains an unapproved item field: {column}{row}")
    if cell(snapshot, f"I{TOTAL_ROW}").formula != (
        'IF(COUNT(I17:I116)=0,"нужно уточнить",SUM(I17:I116))'
    ):
        fail("internal draft total formula is unexpected")
    if cell(snapshot, VAT_RATE_CELL).value != approval.vat_rate_percent:
        fail("internal draft VAT rate does not match approval")
    if cell(snapshot, VAT_LABEL_CELL).formula != VAT_LABEL_FORMULA:
        fail("internal draft VAT label formula is unexpected")
    if cell(snapshot, VAT_AMOUNT_CELL).formula != VAT_AMOUNT_FORMULA:
        fail("internal draft VAT amount formula is unexpected")
    if cell(snapshot, "C119").value != approval.amount_words_text:
        fail("internal draft amount words do not match approval")
    if cell(snapshot, "C121").value != approval.validity_period:
        fail("internal draft validity period does not match approval")
    expected_terms = (
        f"Условия оплаты: {approval.payment_terms}. "
        f"Условия поставки: {approval.delivery_terms}."
    )
    if cell(snapshot, "C122").value != expected_terms:
        fail("internal draft payment or delivery terms do not match approval")
    expected_lead_time = (
        f"Ориентировочный срок изготовления: " f"{approval.manufacturing_lead_time}."
    )
    if cell(snapshot, "C123").value != expected_lead_time:
        fail("internal draft manufacturing lead time does not match approval")
    for coordinate in GUARD_CELLS:
        guard_value = cell(snapshot, coordinate).value
        internal_guard = isinstance(guard_value, str) and contains_forbidden(
            guard_value
        )
        if not internal_guard:
            fail(f"certified guard cell is missing or unexpected: {coordinate}")


def build_updates(approval: Approval) -> dict[str, object]:
    updates: dict[str, object] = {
        "B9": expected_client_title(approval),
        **{coordinate: None for coordinate in GUARD_CELLS},
        **{f"J{row}": None for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)},
    }
    for item in approval.items:
        updates[f"C{item.row}"] = item.client_name
        if item.client_note is not None:
            updates[f"J{item.row}"] = item.client_note
    return updates


def contains_forbidden(text: str) -> bool:
    folded = text.casefold()
    return any(token in folded for token in FORBIDDEN_TOKENS)


def contains_sanitizable_source_text(
    text: str,
    source_notes: frozenset[str],
) -> bool:
    return contains_forbidden(text) or text in source_notes


def shared_string_references(worksheet_xml: bytes) -> dict[int, set[str]]:
    try:
        worksheet = ElementTree.fromstring(worksheet_xml)
    except ElementTree.ParseError:
        fail("candidate worksheet XML is invalid")
    references: dict[int, set[str]] = {}
    for cell_node in worksheet.findall(".//main:c[@t='s']", NS):
        value = cell_node.find("main:v", NS)
        try:
            index = int(cast(ElementTree.Element, value).text or "")
        except (AttributeError, TypeError, ValueError):  # fmt: skip
            fail("candidate contains an invalid shared string reference")
        coordinate = cell_node.get("r", "").upper()
        if coordinate == "":
            fail("candidate contains an invalid shared string cell")
        references.setdefault(index, set()).add(coordinate)
    return references


def referenced_shared_string_indexes(worksheet_xml: bytes) -> set[int]:
    return set(shared_string_references(worksheet_xml))


def rewrite_candidate_part(path: Path, part_name: str, content: bytes) -> None:
    parts = ooxml_patcher.archive_bytes(path)
    if part_name not in parts:
        fail(f"candidate OOXML part is missing: {part_name}")
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.sanitize.tmp.xlsx")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, original in parts.items():
                archive.writestr(name, content if name == part_name else original)
        temporary.replace(path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def sanitize_unreferenced_shared_strings(
    path: Path,
    worksheet_part: str,
    approval: Approval,
) -> None:
    parts = ooxml_patcher.archive_bytes(path)
    if SHARED_STRINGS_PART not in parts:
        return
    try:
        root = ElementTree.fromstring(parts[SHARED_STRINGS_PART])
    except ElementTree.ParseError:
        fail("candidate shared strings XML is invalid")
    references = shared_string_references(parts[worksheet_part])
    source_notes = frozenset(
        item.source_note for item in approval.items if item.source_note is not None
    )
    approved_client_notes = {
        f"J{item.row}": item.client_note
        for item in approval.items
        if item.client_note is not None
    }
    changed = False
    for index, item in enumerate(root.findall("main:si", NS)):
        text = rich_text(item)
        if not contains_sanitizable_source_text(text, source_notes):
            continue
        item_references = references.get(index, set())
        allowed_as_client_note = bool(item_references) and all(
            approved_client_notes.get(coordinate) == text
            for coordinate in item_references
        )
        if text in source_notes and allowed_as_client_note:
            continue
        if item_references:
            fail("candidate still references a forbidden or source-note string")
        item.clear()
        ElementTree.SubElement(item, f"{{{SPREADSHEET_NS}}}t")
        changed = True
    if changed:
        ElementTree.register_namespace("", SPREADSHEET_NS)
        rewrite_candidate_part(
            path,
            SHARED_STRINGS_PART,
            ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
        )


def package_forbidden_hits(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                try:
                    text = archive.read(name).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                folded = text.casefold()
                for token in FORBIDDEN_TOKENS:
                    if token in folded and token not in hits:
                        hits.append(token)
    except (OSError, zipfile.BadZipFile):  # fmt: skip
        fail("candidate package could not be scanned safely")
    return hits


def package_part_contains_text(content: bytes, expected: str) -> bool:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        try:
            return expected in content.decode("utf-8")
        except UnicodeDecodeError:
            return False
    return expected in "".join(root.itertext())


def canonical_element(element: ElementTree.Element) -> tuple[object, ...]:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        element.text or "",
        tuple(canonical_element(child) for child in element),
    )


def worksheet_root(content: bytes, label: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError:
        fail(f"{label} worksheet XML is invalid")


def row_elements(root: ElementTree.Element, label: str) -> list[ElementTree.Element]:
    rows = root.findall("main:sheetData/main:row", NS)
    identifiers = [row.get("r", "") for row in rows]
    if "" in identifiers or len(set(identifiers)) != len(identifiers):
        fail(f"{label} worksheet contains invalid or duplicate rows")
    return rows


def cell_elements(
    rows: Sequence[ElementTree.Element], label: str
) -> dict[str, ElementTree.Element]:
    cells: dict[str, ElementTree.Element] = {}
    for row in rows:
        for node in row.findall("main:c", NS):
            coordinate = node.get("r", "").upper()
            if coordinate == "" or coordinate in cells:
                fail(f"{label} worksheet contains invalid or duplicate cells")
            cells[coordinate] = node
    return cells


def allowed_cell_changes(approval: Approval) -> set[str]:
    return {
        "B9",
        *GUARD_CELLS,
        *(f"J{row}" for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)),
        *(f"C{item.row}" for item in approval.items),
    }


def non_value_cell_structure(element: ElementTree.Element) -> tuple[object, ...]:
    value_tags = {
        f"{{{SPREADSHEET_NS}}}f",
        f"{{{SPREADSHEET_NS}}}v",
        f"{{{SPREADSHEET_NS}}}is",
    }
    return (
        element.tag,
        tuple(
            sorted((key, value) for key, value in element.attrib.items() if key != "t")
        ),
        tuple(
            canonical_element(child) for child in element if child.tag not in value_tags
        ),
    )


def reconcile_worksheet_structure(
    source_xml: bytes,
    candidate_xml: bytes,
    approval: Approval,
) -> None:
    source_root = worksheet_root(source_xml, "source")
    candidate_root = worksheet_root(candidate_xml, "candidate")
    sheet_data_tag = f"{{{SPREADSHEET_NS}}}sheetData"
    source_layout = tuple(
        canonical_element(child) for child in source_root if child.tag != sheet_data_tag
    )
    candidate_layout = tuple(
        canonical_element(child)
        for child in candidate_root
        if child.tag != sheet_data_tag
    )
    if source_layout != candidate_layout:
        fail("candidate worksheet layout or print settings changed")

    source_rows = row_elements(source_root, "source")
    candidate_rows = row_elements(candidate_root, "candidate")
    if [row.get("r") for row in source_rows] != [
        row.get("r") for row in candidate_rows
    ]:
        fail("candidate worksheet row structure changed")
    cell_tag = f"{{{SPREADSHEET_NS}}}c"
    for source_row, candidate_row in zip(source_rows, candidate_rows, strict=True):
        if source_row.attrib != candidate_row.attrib:
            fail(f"candidate worksheet row attributes changed: {source_row.get('r')}")
        source_non_cells = tuple(
            canonical_element(child) for child in source_row if child.tag != cell_tag
        )
        candidate_non_cells = tuple(
            canonical_element(child) for child in candidate_row if child.tag != cell_tag
        )
        if source_non_cells != candidate_non_cells:
            fail(f"candidate worksheet row layout changed: {source_row.get('r')}")

    source_cells = cell_elements(source_rows, "source")
    candidate_cells = cell_elements(candidate_rows, "candidate")
    if list(source_cells) != list(candidate_cells):
        fail("candidate worksheet cell structure changed")
    allowed = allowed_cell_changes(approval)
    for coordinate, source_cell in source_cells.items():
        candidate_cell = candidate_cells[coordinate]
        if coordinate in allowed:
            if non_value_cell_structure(source_cell) != non_value_cell_structure(
                candidate_cell
            ):
                fail(f"candidate changed protected cell structure: {coordinate}")
        elif canonical_element(source_cell) != canonical_element(candidate_cell):
            fail(f"candidate changed a non-allowed worksheet cell: {coordinate}")


def reconcile_shared_strings(
    source: WorkbookSnapshot,
    candidate: WorkbookSnapshot,
    approval: Approval,
) -> None:
    if SHARED_STRINGS_PART not in source.parts:
        return
    try:
        source_root = ElementTree.fromstring(source.parts[SHARED_STRINGS_PART])
        candidate_root = ElementTree.fromstring(candidate.parts[SHARED_STRINGS_PART])
    except ElementTree.ParseError:
        fail("source or candidate shared strings XML is invalid")
    if source_root.attrib != candidate_root.attrib:
        fail("candidate shared strings metadata changed")
    source_items = source_root.findall("main:si", NS)
    candidate_items = candidate_root.findall("main:si", NS)
    if len(source_items) != len(candidate_items):
        fail("candidate shared strings structure changed")
    referenced = referenced_shared_string_indexes(
        candidate.parts[candidate.worksheet_part]
    )
    source_notes = frozenset(
        item.source_note for item in approval.items if item.source_note is not None
    )
    for index, (source_item, candidate_item) in enumerate(
        zip(source_items, candidate_items, strict=True)
    ):
        if canonical_element(source_item) == canonical_element(candidate_item):
            continue
        if (
            index in referenced
            or not contains_sanitizable_source_text(
                rich_text(source_item), source_notes
            )
            or rich_text(candidate_item) != ""
        ):
            fail("candidate changed a non-permitted shared string")


def reconcile_candidate_note_locations(
    candidate: WorkbookSnapshot,
    approval: Approval,
) -> None:
    approved_client_notes = {
        f"J{item.row}": item.client_note
        for item in approval.items
        if item.client_note is not None
    }
    note_texts = {
        note
        for item in approval.items
        for note in (item.source_note, item.client_note)
        if note is not None
    }
    for coordinate, value in candidate.cells.items():
        if not isinstance(value.value, str):
            continue
        expected = approved_client_notes.get(coordinate)
        if expected == value.value and value.formula is None:
            continue
        if any(note in value.value for note in note_texts):
            fail("candidate note text exists outside its exact approved J location")

    for item in approval.items:
        if item.client_note is None:
            continue
        coordinate = f"J{item.row}"
        approved_cell = candidate.cells.get(coordinate)
        if (
            approved_cell is None
            or approved_cell.value != item.client_note
            or approved_cell.formula is not None
        ):
            fail("candidate approved J cell does not contain its exact client_note")

    shared_references = shared_string_references(
        candidate.parts[candidate.worksheet_part]
    )
    shared_items: list[ElementTree.Element] = []
    if SHARED_STRINGS_PART in candidate.parts:
        try:
            shared_root = ElementTree.fromstring(candidate.parts[SHARED_STRINGS_PART])
        except ElementTree.ParseError:
            fail("candidate shared strings XML is invalid")
        shared_items = shared_root.findall("main:si", NS)

    for index, shared_item in enumerate(shared_items):
        text = rich_text(shared_item)
        if not any(note in text for note in note_texts):
            continue
        references = shared_references.get(index, set())
        allowed = bool(references) and all(
            approved_client_notes.get(coordinate) == text for coordinate in references
        )
        if not allowed:
            fail("candidate note text has an unapproved shared-string location")

    for name, content in candidate.parts.items():
        if name in (candidate.worksheet_part, SHARED_STRINGS_PART):
            continue
        if any(package_part_contains_text(content, note) for note in note_texts):
            fail("candidate note text exists in an unapproved OOXML part")


def reconcile_candidate(
    source: WorkbookSnapshot,
    candidate_path: Path,
    approval: Approval,
) -> None:
    candidate = load_snapshot(candidate_path)
    if set(candidate.parts) != set(source.parts):
        fail("candidate OOXML parts differ from the internal draft")
    allowed_changed_parts = {source.worksheet_part, SHARED_STRINGS_PART}
    for name, content in source.parts.items():
        if name not in allowed_changed_parts and candidate.parts[name] != content:
            fail(f"candidate unexpectedly changed OOXML part: {name}")
    reconcile_worksheet_structure(
        source.parts[source.worksheet_part],
        candidate.parts[candidate.worksheet_part],
        approval,
    )
    reconcile_shared_strings(source, candidate, approval)
    if candidate.parts[source.worksheet_part] == source.parts[source.worksheet_part]:
        fail("candidate worksheet was not changed")
    if package_forbidden_hits(candidate_path):
        fail("candidate still contains an internal guard token")
    title = cell(candidate, "B9")
    if title.value != expected_client_title(approval):
        fail("candidate invoice title mismatch")
    if title.formula is not None:
        fail("candidate invoice title must not contain a formula: B9")
    for coordinate in GUARD_CELLS:
        guard = cell(candidate, coordinate)
        if guard.value not in (None, ""):
            fail(f"candidate guard cell was not cleared: {coordinate}")
        if guard.formula is not None:
            fail(f"candidate guard cell must not contain a formula: {coordinate}")
    expected_notes = {
        item.row: item.client_note
        for item in approval.items
        if item.client_note is not None
    }
    reconcile_candidate_note_locations(candidate, approval)
    for row in range(ITEM_START_ROW, ITEM_END_ROW + 1):
        coordinate = f"J{row}"
        item_note = cell(candidate, coordinate)
        expected_note = expected_notes.get(row)
        if expected_note is None and item_note.value not in (None, ""):
            fail(f"candidate item note was not cleared: {coordinate}")
        if expected_note is not None and item_note.value != expected_note:
            fail(f"candidate client technical note mismatch: {coordinate}")
        if item_note.formula is not None:
            fail(f"candidate item note must not contain a formula: {coordinate}")
    for item in approval.items:
        row = item.row
        name_coordinate = f"C{row}"
        client_name = cell(candidate, name_coordinate)
        if client_name.value != item.client_name:
            fail(f"candidate client item name mismatch: {name_coordinate}")
        if client_name.formula is not None:
            fail(f"candidate item name contains a formula: {name_coordinate}")
        preserved_values = {
            f"D{row}": item.unit,
            f"E{row}": item.quantity,
            f"F{row}": item.instruments_and_devices,
            f"G{row}": item.cabinet_type_dimensions_material,
            f"H{row}": item.unit_price_kzt,
        }
        for coordinate, expected in preserved_values.items():
            if cell(candidate, coordinate).value != expected:
                fail(f"candidate technical value mismatch: {coordinate}")
        if cell(candidate, f"I{row}").formula != item_formula(row):
            fail(f"candidate item formula mismatch: I{row}")
    calculated_total = sum(item.line_total_kzt for item in approval.items)
    if calculated_total != approval.commercial_total_kzt:
        fail("candidate independent total reconciliation failed")
    calculated_vat = (
        Decimal(calculated_total)
        * Decimal(approval.vat_rate_percent)
        / Decimal(100 + approval.vat_rate_percent)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if calculated_vat != approval.vat_amount_kzt:
        fail("candidate independent VAT reconciliation failed")
    if (
        cell(candidate, f"I{TOTAL_ROW}").formula
        != cell(source, f"I{TOTAL_ROW}").formula
    ):
        fail("candidate total formula changed")
    if cell(candidate, VAT_LABEL_CELL).formula != VAT_LABEL_FORMULA:
        fail("candidate VAT label formula changed")
    if cell(candidate, VAT_AMOUNT_CELL).formula != VAT_AMOUNT_FORMULA:
        fail("candidate VAT amount formula changed")
    if cell(candidate, "C119").value != approval.amount_words_text:
        fail("candidate amount words changed")


def candidate_path_for(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid.uuid4().hex}.candidate.xlsx")


def validate_paths(
    internal_draft: Path,
    approval_json: Path,
    output_xlsx: Path,
) -> tuple[Path, Path, Path]:
    source = resolved(internal_draft)
    approval = resolved(approval_json)
    output = resolved(output_xlsx)
    for label, path, suffix in (
        ("internal draft", source, ".xlsx"),
        ("approval JSON", approval, ".json"),
    ):
        if not path.is_file():
            fail(f"{label} does not exist")
        if path.suffix.casefold() != suffix:
            fail(f"{label} suffix must be {suffix}")
        if is_inside_project(path):
            fail(f"{label} must be outside Git")
    if output.suffix.casefold() != ".xlsx":
        fail("output suffix must be .xlsx")
    if output.exists():
        fail("output XLSX already exists")
    if not output.parent.is_dir():
        fail("output parent directory does not exist")
    if is_inside_project(output):
        fail("output XLSX must be outside Git")
    if output in {source, approval}:
        fail("output XLSX must not match an input")
    return source, approval, output


def remove_candidate(path: Path) -> None:
    if path.exists():
        path.unlink()


def run_clientization(
    internal_draft: Path,
    approval_json: Path,
    output_xlsx: Path,
) -> ClientizationResult:
    result = ClientizationResult(
        resolved(internal_draft), resolved(approval_json), resolved(output_xlsx)
    )
    candidate: Path | None = None
    published = False
    try:
        source_path, approval_path, output_path = validate_paths(
            internal_draft, approval_json, output_xlsx
        )
        result.internal_draft = source_path
        result.approval_json = approval_path
        result.output_xlsx = output_path
        result.checks["path policy"] = "pass"

        approval = parse_approval(approval_path)
        result.item_count = len(approval.items)
        result.approval_id = approval.approval_id
        result.approved_by = approval.approved_by
        result.approved_at = approval.approved_at.isoformat()
        result.manufacturing_lead_time_approved_by = (
            approval.manufacturing_lead_time_approved_by
        )
        result.manufacturing_lead_time_approved_at = (
            approval.manufacturing_lead_time_approved_at.isoformat()
        )
        result.manufacturing_lead_time_approval_role = (
            approval.manufacturing_lead_time_approval_role
        )
        result.checks["approval schema"] = "pass"
        source_hash = sha256_file(source_path)
        approval_hash = sha256_file(approval_path)
        if source_hash != approval.internal_draft_sha256:
            fail("internal draft SHA-256 does not match approval")
        result.checks["source SHA-256"] = "pass"

        source = load_snapshot(source_path)
        reconcile_source(source, approval)
        result.checks["source reconciliation"] = "pass"

        candidate = candidate_path_for(output_path)
        ooxml_patcher.patch_existing_cells(
            template=source_path,
            output=candidate,
            sheet_name=SHEET_NAME,
            updates=build_updates(approval),
        )
        result.checks["candidate generation"] = "pass"

        sanitize_unreferenced_shared_strings(candidate, source.worksheet_part, approval)
        result.checks["guard sanitation"] = "pass"
        reconcile_candidate(source, candidate, approval)
        result.checks["candidate reconciliation"] = "pass"

        if (
            sha256_file(source_path) != source_hash
            or sha256_file(approval_path) != approval_hash
        ):
            fail("an input changed during clientization")
        result.checks["input immutability"] = "pass"
        if output_path.exists():
            fail("output appeared before atomic publish")
        candidate.rename(output_path)
        candidate = None
        published = True
        result.checks["atomic publish"] = "pass"
        result.checks["safety boundaries"] = "pass"
        result.status = "PASS"
    except (ClientizationError, ooxml_patcher.OoxmlCellPatcherError) as error:
        result.failures.append(str(error))
        result.checks["safety boundaries"] = "pass"
    except Exception:
        result.failures.append("unexpected internal clientization failure")
        result.checks["safety boundaries"] = "pass"
    finally:
        if not published and candidate is not None:
            try:
                remove_candidate(candidate)
            except OSError:
                result.failures.append("temporary candidate could not be removed")
    return result


def format_report(result: ClientizationResult) -> str:
    failures = result.failures if result.failures else ["none"]
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        MODE,
        "",
        "Item count:",
        str(result.item_count),
        "",
        "Approval ID:",
        result.approval_id or "not parsed",
        "",
        "Approved by:",
        result.approved_by or "not parsed",
        "",
        "Approved at:",
        result.approved_at or "not parsed",
        "",
        "Manufacturing lead time approved by:",
        result.manufacturing_lead_time_approved_by or "not parsed",
        "",
        "Manufacturing lead time approved at:",
        result.manufacturing_lead_time_approved_at or "not parsed",
        "",
        "Manufacturing lead time approval role:",
        result.manufacturing_lead_time_approval_role or "not parsed",
        "",
        "Output XLSX:",
        str(result.output_xlsx),
        "",
        "Checks:",
        *(f"{name}: {status}" for name, status in result.checks.items()),
        "",
        "Failures:",
        *failures,
        "",
        "Sending status:",
        "not approved; transformer has no sending action",
        "",
        "Next action:",
        NEXT_ACTION,
        "",
        REPORT_END,
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_clientization(
        args.internal_draft_xlsx,
        args.approval_json,
        args.output_xlsx,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
