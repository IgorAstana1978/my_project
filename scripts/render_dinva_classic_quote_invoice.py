"""Render a new DINVA classic quote/invoice XLSX from approved inputs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import textwrap
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast
from xml.etree import ElementTree
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.cell.cell import Cell  # type: ignore[import-untyped]
from openpyxl.cell.rich_text import (  # type: ignore[import-untyped]
    CellRichText,
    TextBlock,
)
from openpyxl.cell.text import InlineFont  # type: ignore[import-untyped]
from openpyxl.styles import (  # type: ignore[import-untyped]
    Alignment,
    Border,
    Color,
    Font,
    PatternFill,
    Side,
)
from openpyxl.worksheet.pagebreak import Break  # type: ignore[import-untyped]

try:
    from dinva_native_text import canonical_spill_fit
except ModuleNotFoundError:
    # The CLI puts scripts/ on sys.path; import-by-path test consumers put the
    # repository root there instead. Both resolve the same stateless helper.
    canonical_spill_fit = importlib.import_module(
        "scripts.dinva_native_text"
    ).canonical_spill_fit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_dinva_classic_quote_invoice.py")
PROFILE_SCHEMA_VERSION = "dinva_classic_presentation_profile.v0.2"
DOCUMENT_SCHEMA_VERSION = "dinva_quote_invoice_document.v0.2"
FAMILY = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1"
PROFILE_ID = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_2"
TEST_MODE_ENV = "DINVA_RENDERER_TEST_MODE"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CUSTOM_PROPS_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
DRAWING_MAIN_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
CUSTOM_PROPERTY_FORMAT_ID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"
PROFILE_KEYS = {
    "schema_version",
    "profile_id",
    "document_family",
    "artifact_status",
    "reference_provenance",
    "presentation_contract",
    "presentation_contract_fingerprint",
    "approval_provenance",
}
DOCUMENT_KEYS = {
    "schema_version",
    "document_family",
    "document_type",
    "document_id",
    "document_number",
    "document_date",
    "currency",
    "payer",
    "object_name",
    "basis",
    "apparatus_heading",
    "sections",
    "items",
    "document_fingerprint",
    "approved_grand_total_kzt",
    "vat",
    "amount_words",
    "terms",
    "signatures",
    "approval_provenance",
}


class RendererError(ValueError):
    """A clean render would violate the approved contract."""


def fail(message: str) -> NoReturn:
    raise RendererError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(resolved(PROJECT_ROOT))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_bound_json(
    path: Path, expected_sha256: str, label: str
) -> tuple[Path, bytes, dict[str, Any]]:
    actual = path.resolve(strict=True)
    require(not is_inside_project(actual), f"real {label} must be outside Git")
    raw = actual.read_bytes()
    require(sha256_bytes(raw) == expected_sha256, f"{label} SHA-256 mismatch")
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RendererError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    require(isinstance(payload, Mapping), f"{label} root must be an object")
    return actual, raw, dict(payload)


def exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    require(set(value) == expected, f"{label} fields mismatch")


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    require(
        isinstance(value, str) and bool(value.strip()),
        f"{label} must be non-empty text",
    )
    return cast(str, value)


def integer(value: Any, label: str, *, minimum: int = 0) -> int:
    require(
        type(value) is int and value >= minimum,
        f"{label} must be an integer >= {minimum}",
    )
    return cast(int, value)


def sha256_text(value: Any, label: str) -> str:
    require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} must be a lowercase SHA-256",
    )
    return cast(str, value)


def document_fingerprint(document: Mapping[str, Any]) -> str:
    governed = {
        key: value
        for key, value in document.items()
        if key not in {"approval_provenance", "document_fingerprint"}
    }
    return sha256_bytes(canonical_json(governed))


def test_mode(requested: bool) -> bool:
    return requested and os.environ.get(TEST_MODE_ENV) == "1"


def validate_profile(
    profile: Mapping[str, Any], *, allow_test_profile: bool
) -> Mapping[str, Any]:
    exact_keys(profile, PROFILE_KEYS, "profile")
    require(
        profile.get("schema_version")
        in {
            PROFILE_SCHEMA_VERSION,
            "dinva_classic_presentation_profile.v0.3",
            "dinva_classic_presentation_profile.v0.4",
            "dinva_classic_presentation_profile.v0.5",
        },
        "profile schema mismatch",
    )
    v05 = profile.get("schema_version") == "dinva_classic_presentation_profile.v0.5"
    v04 = (
        v05
        or profile.get("schema_version") == "dinva_classic_presentation_profile.v0.4"
    )
    visual = (
        v04
        or profile.get("schema_version") == "dinva_classic_presentation_profile.v0.3"
    )
    require(
        profile.get("profile_id")
        == (
            (
                "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_5"
                if v05
                else "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_4"
            )
            if v04
            else (
                "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_3"
                if visual
                else PROFILE_ID
            )
        ),
        "profile id mismatch",
    )
    require(
        profile.get("document_family") == FAMILY, "unknown/unsupported profile family"
    )
    contract = mapping(profile.get("presentation_contract"), "presentation contract")
    fingerprint = sha256_bytes(canonical_json(contract))
    require(
        profile.get("presentation_contract_fingerprint") == fingerprint,
        "profile contract fingerprint mismatch",
    )
    approval = mapping(
        profile.get("approval_provenance"), "profile approval provenance"
    )
    if test_mode(allow_test_profile):
        require(
            approval.get("status") in {"DRAFT_UNAPPROVED", "APPROVED"},
            "test profile status invalid",
        )
    else:
        require(
            profile.get("artifact_status") == "IMMUTABLE_APPROVED_PROFILE",
            "profile is not immutable/approved",
        )
        require(approval.get("status") == "APPROVED", "profile is DRAFT/unapproved")
        require(
            approval.get("authority") == "IGOR_DIRECT_HUMAN_APPROVAL",
            "profile approval authority mismatch",
        )
        require(
            approval.get("approved_contract_fingerprint") == fingerprint,
            "profile approval fingerprint mismatch",
        )
    exact_keys(
        contract,
        {
            "contract_version",
            "workbook",
            "fixed_blocks",
            "layout",
            "styles",
            "formulas",
            "assets",
            "package",
            "print",
            "optional_elements",
            "variable_elements",
        },
        "presentation contract",
    )
    require(
        contract.get("contract_version")
        == (
            (
                "dinva_classic_presentation_contract.v0.5"
                if v05
                else "dinva_classic_presentation_contract.v0.4"
            )
            if v04
            else (
                "dinva_classic_presentation_contract.v0.3"
                if visual
                else "dinva_classic_presentation_contract.v0.2"
            )
        ),
        "presentation contract version mismatch",
    )
    workbook = mapping(contract.get("workbook"), "workbook contract")
    sheets = workbook.get("sheets")
    require(
        isinstance(sheets, list)
        and len(sheets) == 1
        and mapping(cast(list[Any], sheets)[0], "primary sheet").get("role")
        == "PRIMARY_DOCUMENT"
        and isinstance(cast(list[Any], sheets)[0].get("name"), str),
        "sheet contract mismatch",
    )
    require(
        workbook.get("extra_sheets_allowed") is False, "extra sheets must be closed"
    )
    layout = mapping(contract.get("layout"), "layout contract")
    exact_keys(
        layout,
        {
            "table_header_row",
            "first_content_row",
            "table_columns",
            "column_width_rules",
            "maximum_printable_width",
            "row_height_rule",
            "bottom_layout",
            "pagination",
            "gridlines_visible",
            "merged_cells",
            "top_row_heights",
        }
        | ({"top_block_rules"} if visual else set()),
        "layout contract",
    )
    require(
        layout.get("table_header_row") == 15 and layout.get("first_content_row") == 16,
        "classic structural anchors mismatch",
    )
    width_rules = mapping(layout.get("column_width_rules"), "column width rules")
    require(set(width_rules) == set("BCDEFGHI"), "semantic column rules mismatch")
    for column, raw_rule in width_rules.items():
        rule = mapping(raw_rule, f"column {column} rule")
        exact_keys(
            rule,
            {
                "minimum",
                "preferred",
                "maximum",
                "adaptive",
                "preferred_chars",
                "maximum_chars",
            },
            f"column {column} rule",
        )
        minimum = float(rule["minimum"])
        preferred = float(rule["preferred"])
        maximum = float(rule["maximum"])
        require(0 < minimum <= preferred <= maximum, f"column {column} bounds invalid")
        require(
            type(rule["adaptive"]) is bool, f"column {column} adaptive flag invalid"
        )
        if not cast(bool, rule["adaptive"]):
            require(
                minimum == preferred == maximum,
                f"fixed column {column} must have one width",
            )
        integer(rule["preferred_chars"], f"column {column} preferred chars", minimum=1)
        integer(rule["maximum_chars"], f"column {column} maximum chars", minimum=1)
    require(
        layout.get("gridlines_visible") is True,
        "DINVA classic gridlines must remain visible",
    )
    merges = mapping(layout.get("merged_cells"), "merged cells")
    require(
        merges.get("mode") == "NONE" and merges.get("ranges") == [],
        "DINVA classic successor must not merge cells",
    )
    assets = contract.get("assets")
    require(
        isinstance(assets, list) and len(assets) == 1,
        "asset contract must contain one logo",
    )
    asset = mapping(cast(list[Any], assets)[0], "logo asset")
    try:
        logo = base64.b64decode(cast(str, asset.get("data_base64")), validate=True)
    except (ValueError, TypeError) as exc:
        raise RendererError("logo asset base64 is invalid") from exc
    require(sha256_bytes(logo) == asset.get("sha256"), "logo asset SHA-256 mismatch")
    placement = mapping(asset.get("placement"), "logo placement")
    require(
        placement.get("anchor_type") == "TWO_CELL"
        and placement.get("relative_to") == "COMPANY_HEADER_BLOCK"
        and placement.get("base_cell") == "B2",
        "logo placement rule mismatch",
    )
    if visual:
        semantics = mapping(asset.get("drawing_semantics"), "logo drawing semantics")
        require(semantics.get("edit_as") == "absolute", "logo editAs mismatch")
        try:
            picture = ElementTree.fromstring(
                cast(str, text(semantics.get("picture_xml"), "logo picture XML"))
            )
        except ElementTree.ParseError as exc:
            raise RendererError("logo governed picture XML invalid") from exc
        require(
            picture.tag == f"{{{DRAWING_NS}}}pic"
            and picture.find(
                f"{{{DRAWING_NS}}}spPr/{{{DRAWING_MAIN_NS}}}xfrm/{{{DRAWING_MAIN_NS}}}off"
            )
            is not None
            and picture.find(
                f"{{{DRAWING_NS}}}spPr/{{{DRAWING_MAIN_NS}}}xfrm/{{{DRAWING_MAIN_NS}}}ext"
            )
            is not None,
            "logo explicit transform missing",
        )
    return contract


def validate_document(document: Mapping[str, Any], *, allow_test_profile: bool) -> None:
    exact_keys(document, DOCUMENT_KEYS, "document")
    require(
        document.get("schema_version") == DOCUMENT_SCHEMA_VERSION,
        "document schema mismatch",
    )
    require(
        document.get("document_family") == FAMILY, "unknown/unsupported document family"
    )
    require(
        document.get("document_type") in {"QUOTE", "INVOICE", "QUOTE_INVOICE"},
        "document type mismatch",
    )
    for field in ("document_id", "document_number", "payer", "apparatus_heading"):
        text(document.get(field), field)
    try:
        date.fromisoformat(cast(str, document.get("document_date")))
    except (TypeError, ValueError) as exc:
        raise RendererError("document date must be ISO date") from exc
    require(document.get("currency") == "KZT", "document currency mismatch")
    require(
        document.get("document_fingerprint") == document_fingerprint(document),
        "document fingerprint mismatch",
    )
    text(document.get("object_name"), "object_name", nullable=True)
    text(document.get("basis"), "basis", nullable=True)
    items = document.get("items")
    require(isinstance(items, list) and bool(items), "document items must be non-empty")
    sections = document.get("sections")
    require(
        isinstance(sections, list) and bool(sections),
        "document sections must be non-empty",
    )
    next_position = 1
    for index, raw_section in enumerate(cast(list[Any], sections), start=1):
        section = mapping(raw_section, f"section {index}")
        exact_keys(
            section, {"label", "first_position", "last_position"}, f"section {index}"
        )
        text(section.get("label"), f"section {index}.label")
        first = integer(
            section.get("first_position"), "section first position", minimum=1
        )
        last = integer(section.get("last_position"), "section last position", minimum=1)
        require(
            first == next_position and last >= first,
            "section ranges must be ordered and contiguous",
        )
        next_position = last + 1
    require(
        next_position == len(cast(list[Any], items)) + 1,
        "sections must cover every item exactly once",
    )
    expected_item_keys = {
        "position",
        "name",
        "unit",
        "quantity",
        "detailed_technical_composition",
        "apparatus",
        "enclosure",
        "approved_unit_price_kzt",
        "approved_line_total_kzt",
        "approval_reference",
    }
    total = 0
    for expected_position, raw_item in enumerate(cast(list[Any], items), start=1):
        item = mapping(raw_item, f"item {expected_position}")
        exact_keys(item, expected_item_keys, f"item {expected_position}")
        require(
            integer(item.get("position"), "item position", minimum=1)
            == expected_position,
            "item positions must be contiguous",
        )
        for field in ("name", "unit", "detailed_technical_composition", "enclosure"):
            text(item.get(field), f"item {expected_position}.{field}")
        composition = cast(str, item["detailed_technical_composition"])
        apparatus = mapping(
            item.get("apparatus"), f"item {expected_position}.apparatus"
        )
        exact_keys(
            apparatus,
            {"text", "source_role", "source_sha256", "source_locator"},
            f"item {expected_position}.apparatus",
        )
        apparatus_text = cast(str, text(apparatus.get("text"), "apparatus text"))
        require(
            apparatus.get("source_role") == "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
            "apparatus source role mismatch",
        )
        sha256_text(apparatus.get("source_sha256"), "apparatus source SHA-256")
        text(apparatus.get("source_locator"), "apparatus source locator")
        require(
            apparatus_text in composition,
            f"item {expected_position} apparatus is not exactly represented "
            "in detailed composition",
        )
        reference = mapping(
            item.get("approval_reference"),
            f"item {expected_position}.approval reference",
        )
        exact_keys(
            reference, {"pricing", "technical", "enclosure"}, "approval reference"
        )
        text(reference.get("pricing"), "pricing approval reference")
        text(reference.get("technical"), "technical approval reference")
        text(reference.get("enclosure"), "enclosure approval reference", nullable=True)
        quantity = integer(item.get("quantity"), "quantity", minimum=1)
        unit_price = integer(item.get("approved_unit_price_kzt"), "unit price")
        line_total = integer(item.get("approved_line_total_kzt"), "line total")
        require(
            quantity * unit_price == line_total,
            f"item {expected_position} approved arithmetic mismatch",
        )
        total += line_total
    require(
        integer(document.get("approved_grand_total_kzt"), "grand total") == total,
        "approved grand total mismatch",
    )
    amount_words = mapping(document.get("amount_words"), "amount words")
    exact_keys(amount_words, {"amount_kzt", "approved_text"}, "amount words")
    require(
        integer(amount_words.get("amount_kzt"), "amount words amount") == total,
        "amount words amount mismatch",
    )
    text(amount_words.get("approved_text"), "amount words text")
    vat = mapping(document.get("vat"), "VAT")
    exact_keys(
        vat, {"rate_percent", "included", "approved_amount_kzt", "approved_text"}, "VAT"
    )
    rate = integer(vat.get("rate_percent"), "VAT rate")
    require(rate <= 100, "VAT rate exceeds 100")
    require(type(vat.get("included")) is bool, "VAT included must be boolean")
    divisor = Decimal(100 + rate) if vat["included"] else Decimal(100)
    expected_vat = int(
        (Decimal(total) * Decimal(rate) / divisor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    require(
        integer(vat.get("approved_amount_kzt"), "VAT amount") == expected_vat,
        "approved VAT arithmetic mismatch",
    )
    text(vat.get("approved_text"), "VAT text")
    terms = mapping(document.get("terms"), "terms")
    exact_keys(
        terms,
        {
            "payment",
            "delivery",
            "manufacturing_lead_time",
            "manufacturing_lead_time_provenance",
            "validity",
            "commercial_lines",
        },
        "terms",
    )
    text(terms.get("payment"), "terms.payment", nullable=True)
    if (
        document.get("document_number") == "519"
        or mapping(document.get("approval_provenance"), "document approval").get(
            "approval_scope"
        )
        == "INVOICE519_DOCUMENT_MODEL_ONLY"
    ):
        require(
            terms.get("payment") is None,
            "Invoice519 payment lacks governed provenance",
        )
    for field in ("delivery", "manufacturing_lead_time"):
        text(terms.get(field), f"terms.{field}")
    text(terms.get("validity"), "terms.validity", nullable=True)
    commercial_lines = terms.get("commercial_lines")
    require(
        isinstance(commercial_lines, list) and bool(commercial_lines),
        "commercial terms lines missing",
    )
    for index, raw_line in enumerate(cast(list[Any], commercial_lines), start=1):
        line = mapping(raw_line, f"commercial line {index}")
        exact_keys(
            line,
            {"source_order", "text", "source_sha256", "source_locator"},
            f"commercial line {index}",
        )
        require(
            integer(line.get("source_order"), "commercial source order", minimum=1)
            == index,
            "commercial source order must be contiguous",
        )
        text(line.get("text"), f"commercial line {index}.text")
        sha256_text(line.get("source_sha256"), "commercial line source SHA-256")
        text(line.get("source_locator"), "commercial line source locator")
    lead_provenance = mapping(
        terms.get("manufacturing_lead_time_provenance"),
        "manufacturing lead-time provenance",
    )
    exact_keys(
        lead_provenance,
        {
            "source_order",
            "source_text",
            "normalized_text",
            "source_sha256",
            "source_locator",
            "normalization_rule",
            "approval_reference",
        },
        "manufacturing lead-time provenance",
    )
    lead_source_order = integer(
        lead_provenance.get("source_order"), "lead-time source order", minimum=1
    )
    require(
        lead_source_order <= len(cast(list[Any], commercial_lines)),
        "lead-time source order is out of range",
    )
    lead_source = mapping(
        cast(list[Any], commercial_lines)[lead_source_order - 1],
        "lead-time commercial source",
    )
    require(
        lead_provenance.get("source_text") == lead_source.get("text")
        and lead_provenance.get("source_sha256") == lead_source.get("source_sha256")
        and lead_provenance.get("source_locator") == lead_source.get("source_locator")
        and lead_provenance.get("normalized_text")
        == terms.get("manufacturing_lead_time"),
        "manufacturing lead-time provenance mismatch",
    )
    text(lead_provenance.get("normalization_rule"), "lead-time normalization rule")
    text(lead_provenance.get("approval_reference"), "lead-time approval reference")
    signatures = mapping(document.get("signatures"), "signatures")
    exact_keys(
        signatures,
        {
            "director_title",
            "director_name",
            "executor_label",
            "executor_title",
            "executor_name",
            "executor_full_text",
        },
        "signatures",
    )
    for field in signatures:
        text(signatures[field], f"signatures.{field}")
    require(
        cast(str, signatures["executor_title"])
        in cast(str, signatures["executor_full_text"]),
        "executor title is not represented in full text",
    )
    require(
        cast(str, signatures["executor_name"])
        in cast(str, signatures["executor_full_text"]),
        "executor name is not represented in full text",
    )
    approval = mapping(document.get("approval_provenance"), "document approval")
    exact_keys(
        approval,
        {
            "status",
            "authority",
            "approval_id",
            "approved_at",
            "approval_scope",
            "approved_document_fingerprint",
            "source_bindings",
            "source_sha256s",
            "rendering_authorized",
            "client_send_authorized",
        },
        "document approval",
    )
    require(approval.get("status") == "APPROVED", "document is not approved")
    if not test_mode(allow_test_profile):
        require(
            approval.get("authority") == "IGOR_DIRECT_HUMAN_APPROVAL",
            "document approval authority mismatch",
        )
    text(approval.get("authority"), "approval authority")
    text(approval.get("approval_id"), "approval id")
    text(approval.get("approved_at"), "approved_at")
    approval_scope = text(approval.get("approval_scope"), "document approval scope")
    if approval_scope == "INVOICE519_DOCUMENT_MODEL_ONLY":
        require(document.get("basis") == "2024/086", "Invoice519 basis mismatch")
    require(
        approval.get("approved_document_fingerprint") == document_fingerprint(document),
        "document approval fingerprint mismatch",
    )
    bindings = approval.get("source_bindings")
    require(
        isinstance(bindings, list) and bool(bindings),
        "document source bindings missing",
    )
    bound_shas: list[str] = []
    roles: set[str] = set()
    for index, raw_binding in enumerate(cast(list[Any], bindings), start=1):
        binding = mapping(raw_binding, f"source binding {index}")
        exact_keys(binding, {"role", "path", "sha256"}, f"source binding {index}")
        role = cast(str, text(binding.get("role"), "source binding role"))
        require(role not in roles, "duplicate source binding role")
        roles.add(role)
        text(binding.get("path"), "source binding path")
        bound_shas.append(sha256_text(binding.get("sha256"), "source binding SHA-256"))
    source_shas = approval.get("source_sha256s")
    require(
        isinstance(source_shas, list) and bool(source_shas),
        "document source hashes missing",
    )
    require(
        all(isinstance(item, str) for item in cast(list[Any], source_shas))
        and [
            sha256_text(item, "document source hash")
            for item in cast(list[Any], source_shas)
        ]
        == bound_shas,
        "document source hash invalid",
    )
    require(
        approval.get("rendering_authorized") is True,
        "document rendering is not authorized",
    )
    require(
        approval.get("client_send_authorized") is False,
        "renderer cannot consume sending authorization",
    )


def color_from_spec(spec: Mapping[str, Any] | None) -> Color | None:
    if spec is None:
        return None
    kind = spec.get("type")
    value = spec.get("value")
    tint = float(spec.get("tint", 0))
    if kind == "rgb":
        return Color(rgb=cast(str, value), tint=tint)
    if kind == "indexed":
        return Color(indexed=int(cast(int, value)), tint=tint)
    if kind == "theme":
        return Color(theme=int(cast(int, value)), tint=tint)
    fail("unsupported profile color")


def apply_style(cell: Cell, raw_style: Mapping[str, Any]) -> None:
    font = mapping(raw_style.get("font"), "style font")
    fill = mapping(raw_style.get("fill"), "style fill")
    border = mapping(raw_style.get("border"), "style border")
    alignment = mapping(raw_style.get("alignment"), "style alignment")
    cell.font = Font(
        name=cast(str, font["name"]),
        size=float(cast(float, font["size"])),
        bold=bool(font["bold"]),
        italic=bool(font["italic"]),
        underline=cast(str | None, font["underline"]),
        color=color_from_spec(cast(Mapping[str, Any] | None, font["color"])),
    )
    cell.fill = PatternFill(
        fill_type=cast(str | None, fill["type"]),
        fgColor=color_from_spec(cast(Mapping[str, Any] | None, fill["foreground"])),
    )
    cell.border = Border(
        left=Side(style=cast(str | None, border["left"]), color="FF000000"),
        right=Side(style=cast(str | None, border["right"]), color="FF000000"),
        top=Side(style=cast(str | None, border["top"]), color="FF000000"),
        bottom=Side(style=cast(str | None, border["bottom"]), color="FF000000"),
    )
    cell.alignment = Alignment(
        horizontal=cast(str | None, alignment["horizontal"]),
        vertical=cast(str | None, alignment["vertical"]),
        wrap_text=bool(alignment["wrap_text"]),
        shrink_to_fit=bool(alignment["shrink_to_fit"]),
    )
    cell.number_format = cast(str, raw_style["number_format"])


def percentile_90(values: Sequence[int]) -> int:
    ordered = sorted(values)
    require(bool(ordered), "content distribution is empty")
    return ordered[max(0, ceil(len(ordered) * 0.9) - 1)]


def content_lengths(document: Mapping[str, Any], column: str) -> list[int]:
    fields = {"C": "name", "F": "detailed_technical_composition", "G": "enclosure"}
    items = cast(list[Mapping[str, Any]], document["items"])
    if column in fields:
        return [
            max(len(part) for part in cast(str, item[fields[column]]).split("\n"))
            for item in items
        ]
    if column == "I":
        values = [
            cast(int, document["approved_grand_total_kzt"]),
            *[cast(int, item["approved_line_total_kzt"]) for item in items],
        ]
        return [len(f"{value:,}") for value in values]
    return [1]


def adaptive_column_widths(
    contract: Mapping[str, Any], document: Mapping[str, Any]
) -> dict[str, float]:
    layout = mapping(contract["layout"], "layout")
    rules = mapping(layout["column_width_rules"], "column width rules")
    widths: dict[str, float] = {}
    minimums: dict[str, float] = {}
    for column in "BCDEFGHI":
        rule = mapping(rules[column], f"column {column} rule")
        minimum = float(rule["minimum"])
        preferred = float(rule["preferred"])
        maximum = float(rule["maximum"])
        minimums[column] = minimum
        if not cast(bool, rule["adaptive"]):
            widths[column] = preferred
            continue
        score = percentile_90(content_lengths(document, column))
        preferred_chars = integer(
            rule["preferred_chars"], f"column {column} preferred chars", minimum=1
        )
        maximum_chars = integer(
            rule["maximum_chars"], f"column {column} maximum chars", minimum=1
        )
        require(
            maximum_chars > preferred_chars,
            f"column {column} content thresholds invalid",
        )
        if score <= preferred_chars:
            fraction = score / preferred_chars
            width = minimum + (preferred - minimum) * fraction
        else:
            fraction = min(
                1.0, (score - preferred_chars) / (maximum_chars - preferred_chars)
            )
            width = preferred + (maximum - preferred) * fraction
        widths[column] = round(width * 4) / 4
    maximum_total = float(layout["maximum_printable_width"])
    excess = sum(widths.values()) - maximum_total
    for column in ("C", "G", "F", "I"):
        if excess <= 1e-9:
            break
        available = widths[column] - minimums[column]
        reduction = min(available, ceil(excess * 4 - 1e-9) / 4)
        widths[column] = round((widths[column] - reduction) * 4) / 4
        excess = sum(widths.values()) - maximum_total
    require(excess <= 1e-9, "column width bounds exceed printable width")
    return widths


def wrapped_line_count(text_value: str, width: float, font_size: float) -> int:
    capacity = max(1, int(width * 11.0 / font_size * 0.94))
    return sum(max(1, ceil(len(part) / capacity)) for part in text_value.split("\n"))


def content_row_height(
    item: Mapping[str, Any],
    widths: Mapping[str, float],
    rule: Mapping[str, Any],
    styles: Mapping[str, Any],
) -> float:
    roles = {
        "C": ("name", "item_name"),
        "F": ("detailed_technical_composition", "technical_composition"),
        "G": ("enclosure", "enclosure"),
    }
    lines = []
    for column, (field, style_name) in roles.items():
        style = mapping(styles[style_name], f"{style_name} style")
        font = mapping(style["font"], f"{style_name} font")
        lines.append(
            wrapped_line_count(
                cast(str, item[field]), float(widths[column]), float(font["size"])
            )
        )
    line_height = float(rule["line_height_points"])
    padding = float(rule["vertical_padding_points"])
    required = max(lines) * line_height + padding
    maximum = float(rule["maximum_height"])
    require(required <= maximum, "item content exceeds safe Excel row height")
    return round(max(float(rule["minimum_height"]), required) * 4) / 4


def table_header_height(
    contract: Mapping[str, Any],
    document: Mapping[str, Any],
    widths: Mapping[str, float],
) -> float:
    fixed = mapping(contract["fixed_blocks"], "fixed blocks")
    headers = dict(mapping(fixed["table_headers"], "table headers"))
    headers["F"] = document["apparatus_heading"]
    style = mapping(
        mapping(contract["styles"], "styles")["table_header"], "header style"
    )
    font_size = float(mapping(style["font"], "header font")["size"])
    lines = max(
        wrapped_line_count(cast(str, headers[column]), widths[column], font_size)
        for column in "BCDEFGHI"
    )
    rule = mapping(
        mapping(contract["layout"], "layout")["row_height_rule"], "height rule"
    )
    return (
        round(
            max(
                float(rule["header_minimum_height"]),
                lines * float(rule["header_line_height_points"])
                + float(rule["vertical_padding_points"]),
            )
            * 4
        )
        / 4
    )


def object_block_height(
    contract: Mapping[str, Any],
    document: Mapping[str, Any],
    widths: Mapping[str, float],
) -> float:
    layout = mapping(contract["layout"], "layout")
    minimum = float(mapping(layout["top_row_heights"], "top heights")["13"])
    if "top_block_rules" not in layout or document["object_name"] is None:
        return minimum
    if contract.get("contract_version") in {
        "dinva_classic_presentation_contract.v0.4",
        "dinva_classic_presentation_contract.v0.5",
    }:
        rule = mapping(
            mapping(layout["top_block_rules"], "top rules")["object_presentation"],
            "object presentation",
        )
        font = mapping(
            mapping(mapping(contract["styles"], "styles")["object"], "object style")[
                "font"
            ],
            "object font",
        )
        require(
            all(
                font.get(key) == value
                for key, value in mapping(rule["font"], "canonical font").items()
                if key != "color_indexed"
            ),
            "object font differs from canonical font",
        )
        require(
            font.get("color") == {"type": "indexed", "value": 8, "tint": 0.0}
            and mapping(
                mapping(
                    mapping(contract["styles"], "styles")["object"], "object style"
                )["alignment"],
                "object alignment",
            )
            == rule["stored_alignment"],
            "object style differs from canonical C13 presentation",
        )
        try:
            canonical_spill_fit(rule, str(document["object_name"]), widths)
        except ValueError as exc:
            raise RendererError(str(exc)) from exc
        return minimum
    rule = mapping(
        mapping(layout["top_block_rules"], "top rules")["object_height"],
        "object height",
    )
    require(
        rule
        == {
            "cell": "C13",
            "glyph_width_em": 1.1,
            "line_height_em": 1.5,
            "padding_points": 6.0,
            "maximum_height": 408.0,
        },
        "unsupported object height rule",
    )
    font = mapping(
        mapping(mapping(contract["styles"], "styles")["object"], "object style")[
            "font"
        ],
        "object font",
    )
    size = float(font["size"])
    # Conservative one-em glyph bound plus word-wrap and explicit line breaks.
    capacity = max(1, int(((widths["C"] * 7 + 5) * 0.75 - 6) / (size * 1.1)))
    lines = sum(
        max(
            1,
            len(
                textwrap.wrap(
                    part, capacity, replace_whitespace=False, drop_whitespace=False
                )
            ),
        )
        for part in str(document["object_name"]).split("\n")
    )
    height = max(minimum, ceil((lines * size * 1.5 + 6) * 4) / 4)
    require(height <= 408, "object content exceeds safe Excel row height")
    return height


def dynamic_layout_plan(
    contract: Mapping[str, Any], document: Mapping[str, Any]
) -> dict[str, Any]:
    layout = mapping(contract["layout"], "layout")
    styles = mapping(contract["styles"], "styles")
    widths = adaptive_column_widths(contract, document)
    rule = mapping(layout["row_height_rule"], "row height rule")
    row = integer(layout["first_content_row"], "first content row", minimum=1)
    rows: list[dict[str, Any]] = []
    items = cast(list[Mapping[str, Any]], document["items"])
    by_position = {cast(int, item["position"]): item for item in items}
    for section in cast(list[Mapping[str, Any]], document["sections"]):
        rows.append(
            {
                "row": row,
                "kind": "section",
                "height": float(rule["section_height"]),
                "value": section["label"],
            }
        )
        row += 1
        for position in range(
            cast(int, section["first_position"]),
            cast(int, section["last_position"]) + 1,
        ):
            item = by_position[position]
            rows.append(
                {
                    "row": row,
                    "kind": "item",
                    "height": content_row_height(item, widths, rule, styles),
                    "item": item,
                }
            )
            row += 1
    last_data_row = row - 1
    bottom = mapping(layout["bottom_layout"], "bottom layout")
    total_row = row
    amount_row = total_row + integer(
        bottom["amount_words_offset"], "amount words offset", minimum=1
    )
    commercial_start = amount_row + 1
    commercial_count = len(
        cast(list[Any], mapping(document["terms"], "terms")["commercial_lines"])
    )
    director_row = (
        commercial_start
        + commercial_count
        + integer(bottom["signature_spacer_rows"], "signature spacer rows", minimum=0)
    )
    executor_row = director_row + 1
    final_row = executor_row
    rows.extend(
        [
            {"row": total_row, "kind": "total", "height": float(rule["total_height"])},
            {
                "row": amount_row,
                "kind": "amount",
                "height": float(rule["amount_height"]),
            },
            *[
                {
                    "row": commercial_start + offset,
                    "kind": "commercial",
                    "height": float(rule["commercial_height"]),
                }
                for offset in range(commercial_count)
            ],
            {
                "row": director_row,
                "kind": "signature",
                "height": float(rule["signature_height"]),
            },
            {
                "row": executor_row,
                "kind": "executor",
                "height": float(rule["signature_height"]),
            },
        ]
    )
    pagination = mapping(layout["pagination"], "pagination")
    breaks: list[int] = []
    if contract.get("contract_version") == "dinva_classic_presentation_contract.v0.5":
        breaks = []
    else:
        first_limit = float(pagination["first_page_body_height_points"])
        first_limit -= object_block_height(contract, document, widths) - float(
            mapping(layout["top_row_heights"], "top heights")["13"]
        )
        following_limit = float(pagination["following_page_body_height_points"])
        groups: list[list[dict[str, Any]]] = []
        index = 0
        while index < len(rows):
            current = rows[index]
            if (
                current["kind"] == "section"
                and index + 1 < len(rows)
                and rows[index + 1]["kind"] == "item"
            ):
                groups.append([current, rows[index + 1]])
                index += 2
            elif current["kind"] == "total":
                groups.append(rows[index:])
                break
            else:
                groups.append([current])
                index += 1
        used = 0.0
        limit = first_limit
        previous_row: int | None = None
        for group in groups:
            height = sum(float(entry["height"]) for entry in group)
            require(
                height <= following_limit,
                "layout group is taller than one printable page",
            )
            if previous_row is not None and used > 0 and used + height > limit:
                breaks.append(previous_row)
                used = 0.0
                limit = following_limit
            used += height
            previous_row = cast(int, group[-1]["row"])
    return {
        "widths": widths,
        "rows": rows,
        "last_data_row": last_data_row,
        "total_row": total_row,
        "amount_row": amount_row,
        "commercial_start": commercial_start,
        "director_row": director_row,
        "executor_row": executor_row,
        "final_row": final_row,
        "page_breaks": breaks,
        "header_height": table_header_height(contract, document, widths),
    }


def display_document_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    months = (
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
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year} года"


def render_clean_workbook(
    profile: Mapping[str, Any],
    profile_sha256: str,
    document: Mapping[str, Any],
    document_sha256: str,
    output: Path,
) -> None:
    contract = mapping(profile["presentation_contract"], "presentation contract")
    layout = mapping(contract["layout"], "layout")
    styles = mapping(contract["styles"], "styles")
    fixed = mapping(contract["fixed_blocks"], "fixed blocks")
    plan = dynamic_layout_plan(contract, document)
    workbook = Workbook()
    worksheet = workbook.active
    sheet_contract = cast(
        list[Mapping[str, Any]], mapping(contract["workbook"], "workbook")["sheets"]
    )[0]
    worksheet.title = cast(str, sheet_contract["name"])
    workbook.properties.creator = "DINVA deterministic renderer"
    fixed_time = datetime(2000, 1, 1, tzinfo=UTC)
    workbook.properties.created = fixed_time
    workbook.properties.modified = fixed_time
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    worksheet.sheet_view.showGridLines = True
    for column, width in cast(dict[str, float], plan["widths"]).items():
        worksheet.column_dimensions[column].width = width
    for raw_row, raw_height in mapping(
        layout["top_row_heights"], "top row heights"
    ).items():
        worksheet.row_dimensions[int(raw_row)].height = float(raw_height)
    company = mapping(fixed["company"], "company block")
    for coordinate, value in company.items():
        worksheet[coordinate] = value
        apply_style(
            worksheet[coordinate],
            mapping(
                styles[
                    (
                        "company_title"
                        if coordinate == "C2"
                        else (
                            "country"
                            if coordinate == "C3"
                            else (
                                "bank_title"
                                if coordinate in {"I2", "I3"}
                                else (
                                    "bank_info"
                                    if coordinate.startswith("I")
                                    else "company_info"
                                )
                            )
                        )
                    )
                ],
                "company style",
            ),
        )
    title_by_type = {
        "QUOTE": "Коммерческое предложение",
        "INVOICE": "Счёт",
        "QUOTE_INVOICE": "Счёт-КП",
    }
    worksheet["C9"] = (
        f"{title_by_type[cast(str, document['document_type'])]} № "
        f"{document['document_number']} от "
        f"{display_document_date(cast(str, document['document_date']))}"
    )
    worksheet["C10"] = f"Плательщик: {document['payer']}"
    if document["object_name"] is not None:
        worksheet["C13"] = document["object_name"]
        apply_style(worksheet["C13"], mapping(styles["object"], "object style"))
        worksheet.row_dimensions[13].height = object_block_height(
            contract, document, plan["widths"]
        )
    worksheet["G9"] = mapping(fixed["warning"], "warning block")["G9"]
    terms = mapping(document["terms"], "terms")
    worksheet["G10"] = f"Срок изготовления {terms['manufacturing_lead_time']}"
    apply_style(worksheet["C9"], mapping(styles["document_title"], "title style"))
    apply_style(worksheet["C10"], mapping(styles["payer"], "payer style"))
    apply_style(worksheet["G9"], mapping(styles["warning"], "warning style"))
    apply_style(worksheet["G10"], mapping(styles["lead_time"], "lead time style"))
    if "top_block_rules" in layout:
        top = mapping(layout["top_block_rules"], "top block rules")
        if contract.get("contract_version") in {
            "dinva_classic_presentation_contract.v0.4",
            "dinva_classic_presentation_contract.v0.5",
        }:
            country = mapping(top["country_rich_text"], "country rich text")
            runs = cast(list[dict[str, Any]], country["runs"])
            require(
                country.get("cell") == "C3"
                and "".join(run["text"] for run in runs) == company["C3"],
                "country rich text differs from fixed text",
            )
            worksheet["C3"] = CellRichText(
                [
                    TextBlock(
                        InlineFont(
                            rFont=run["font"]["name"],
                            sz=run["font"]["size"],
                            b=run["font"]["bold"],
                            family=run["font"]["family"],
                            charset=run["font"]["charset"],
                            color=Color(indexed=run["font"]["color_indexed"]),
                        ),
                        run["text"],
                    )
                    for run in runs
                ]
            )
        borders = mapping(top["border_xml_by_cell"], "top borders")
        require(
            set(borders) == {f"{c}{r}" for r in range(2, 15) for c in "BCDEFGHI"},
            "top border map mismatch",
        )
        for coordinate, raw_border in borders.items():
            worksheet[coordinate].border = Border.from_tree(
                ElementTree.fromstring(str(raw_border))
            )
    header_row = integer(layout["table_header_row"], "table header row", minimum=1)
    headers = dict(mapping(fixed["table_headers"], "table headers"))
    headers["F"] = document["apparatus_heading"]
    header_style_by_column = {"B": "table_header_left", "I": "table_header_right"}
    for column in "BCDEFGHI":
        coordinate = f"{column}{header_row}"
        worksheet[coordinate] = headers[column]
        apply_style(
            worksheet[coordinate],
            mapping(
                styles[header_style_by_column.get(column, "table_header")],
                "table header style",
            ),
        )
    worksheet.row_dimensions[header_row].height = float(plan["header_height"])
    style_by_column = {
        "B": "position",
        "C": "item_name",
        "D": "unit",
        "E": "quantity",
        "F": "technical_composition",
        "G": "enclosure",
        "H": "money",
        "I": "line_total",
    }
    line_template = cast(
        str, mapping(contract["formulas"], "formulas")["line_total_template"]
    )
    for entry in cast(list[dict[str, Any]], plan["rows"]):
        row = cast(int, entry["row"])
        worksheet.row_dimensions[row].height = float(entry["height"])
        if entry["kind"] == "section":
            for column in "BCDEFGHI":
                apply_style(
                    worksheet[f"{column}{row}"],
                    mapping(styles["section"], "section style"),
                )
            worksheet[f"C{row}"] = entry["value"]
            continue
        if entry["kind"] != "item":
            continue
        item = cast(Mapping[str, Any], entry["item"])
        values = {
            "B": item["position"],
            "C": item["name"],
            "D": item["unit"],
            "E": item["quantity"],
            "F": item["detailed_technical_composition"],
            "G": item["enclosure"],
            "H": item["approved_unit_price_kzt"],
            "I": line_template.format(row=row),
        }
        for column, value in values.items():
            worksheet[f"{column}{row}"] = value
            apply_style(
                worksheet[f"{column}{row}"],
                mapping(styles[style_by_column[column]], f"{column} item style"),
            )
    total_row = cast(int, plan["total_row"])
    worksheet[f"C{total_row}"] = fixed["total_label"]
    grand_template = cast(
        str, mapping(contract["formulas"], "formulas")["grand_total_template"]
    )
    worksheet[f"I{total_row}"] = grand_template.format(
        start=integer(layout["first_content_row"], "first content row"),
        end=cast(int, plan["last_data_row"]),
    )
    apply_style(
        worksheet[f"C{total_row}"], mapping(styles["total_label"], "total label style")
    )
    apply_style(
        worksheet[f"I{total_row}"],
        mapping(styles["total_amount"], "total amount style"),
    )
    vat = mapping(document["vat"], "VAT")
    amount_row = cast(int, plan["amount_row"])
    approved_words = mapping(document["amount_words"], "amount words")["approved_text"]
    worksheet[f"C{amount_row}"] = f"ВСЕГО: {approved_words}, {vat['approved_text']}."
    apply_style(
        worksheet[f"C{amount_row}"],
        mapping(styles["amount_words"], "amount words style"),
    )
    commercial_start = cast(int, plan["commercial_start"])
    for offset, raw_line in enumerate(
        cast(list[Mapping[str, Any]], terms["commercial_lines"])
    ):
        row = commercial_start + offset
        worksheet[f"C{row}"] = raw_line["text"]
        apply_style(
            worksheet[f"C{row}"],
            mapping(styles["commercial_line"], "commercial line style"),
        )
    signatures = mapping(document["signatures"], "signatures")
    director_row = cast(int, plan["director_row"])
    executor_row = cast(int, plan["executor_row"])
    worksheet[f"C{director_row}"] = signatures["director_title"]
    worksheet[f"F{director_row}"] = signatures["director_name"]
    worksheet[f"H{director_row}"] = signatures["executor_label"]
    worksheet[f"E{executor_row}"] = "=C9"
    worksheet[f"H{executor_row}"] = signatures["executor_full_text"]
    apply_style(
        worksheet[f"C{director_row}"], mapping(styles["director"], "director style")
    )
    apply_style(
        worksheet[f"F{director_row}"],
        mapping(styles["director_name"], "director name style"),
    )
    for coordinate in (f"H{director_row}", f"E{executor_row}", f"H{executor_row}"):
        apply_style(
            worksheet[coordinate], mapping(styles["executor"], "executor style")
        )
    print_contract = mapping(contract["print"], "print contract")
    worksheet.page_setup.paperSize = cast(str, print_contract["paper_size"])
    worksheet.page_setup.orientation = cast(str, print_contract["orientation"])
    worksheet.page_setup.scale = integer(
        print_contract["scale"], "page scale", minimum=1
    )
    worksheet.page_setup.fitToHeight = integer(
        print_contract["fit_to_height"], "fit height"
    )
    native_print = (
        contract.get("contract_version") == "dinva_classic_presentation_contract.v0.5"
    )
    worksheet.page_setup.fitToWidth = (
        None if native_print else integer(print_contract["fit_to_width"], "fit width")
    )
    worksheet.sheet_properties.pageSetUpPr.fitToPage = bool(
        print_contract["fit_to_page"]
    )
    margins = mapping(print_contract["margins"], "margins")
    for name in ("left", "right", "top", "bottom", "header", "footer"):
        setattr(worksheet.page_margins, name, float(cast(float, margins[name])))
    if not native_print:
        worksheet.print_title_rows = cast(
            str, mapping(layout["pagination"], "pagination")["repeat_rows"]
        )
        for break_after_row in cast(list[int], plan["page_breaks"]):
            worksheet.row_breaks.append(Break(id=break_after_row))
        final_row = cast(int, plan["final_row"])
        worksheet.print_area = f"B1:I{final_row}"
    workbook.save(output)
    workbook.close()
    asset = mapping(cast(list[Any], contract["assets"])[0], "logo asset")
    inject_governed_parts(
        output,
        base64.b64decode(cast(str, asset["data_base64"]), validate=True),
        mapping(asset["placement"], "logo placement"),
        {
            "DINVA_PROFILE_ID": cast(str, profile["profile_id"]),
            "DINVA_DOCUMENT_FAMILY": FAMILY,
            "DINVA_PROFILE_SHA256": profile_sha256,
            "DINVA_PRESENTATION_FINGERPRINT": cast(
                str, profile["presentation_contract_fingerprint"]
            ),
            "DINVA_DOCUMENT_SHA256": document_sha256,
        },
        (
            mapping(asset["drawing_semantics"], "logo drawing semantics")
            if "drawing_semantics" in asset
            else None
        ),
    )


def archive_parts(path: Path) -> dict[str, bytes]:
    try:
        with ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except BadZipFile as exc:
        raise RendererError(f"candidate is not a valid XLSX package: {exc}") from exc


def drawing_xml(
    placement: Mapping[str, Any], semantics: Mapping[str, Any] | None = None
) -> bytes:
    anchor_type = placement.get("anchor_type")
    if anchor_type == "ONE_CELL":
        start = mapping(placement["from"], "logo from anchor")
        extent = mapping(placement["extent"], "logo extent")

        def legacy_marker(name: str, value: Mapping[str, Any]) -> str:
            column = integer(value["column"], "anchor column")
            column_offset = integer(value["column_offset"], "anchor column offset")
            row = integer(value["row"], "anchor row")
            row_offset = integer(value["row_offset"], "anchor row offset")
            return (
                f"<xdr:{name}><xdr:col>{column}</xdr:col>"
                f"<xdr:colOff>{column_offset}</xdr:colOff>"
                f"<xdr:row>{row}</xdr:row>"
                f"<xdr:rowOff>{row_offset}</xdr:rowOff>"
                f"</xdr:{name}>"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<xdr:wsDr xmlns:xdr="{DRAWING_NS}" xmlns:a="{DRAWING_MAIN_NS}" '
            f'xmlns:r="{OFFICE_REL_NS}"><xdr:oneCellAnchor>'
            + legacy_marker("from", start)
            + f'<xdr:ext cx="{integer(extent["cx"], "logo extent cx")}" '
            f'cy="{integer(extent["cy"], "logo extent cy")}"/>'
            + '<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="DINVA classic logo"/>'
            '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/>'
            "</xdr:cNvPicPr></xdr:nvPicPr>"
            '<xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch>'
            '</xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            "<a:noFill/><a:ln><a:noFill/></a:ln></xdr:spPr></xdr:pic><xdr:clientData/>"
            "</xdr:oneCellAnchor></xdr:wsDr>"
        ).encode("utf-8")
    require(anchor_type == "TWO_CELL", "logo anchor type mismatch")
    require(placement.get("base_cell") == "B2", "logo base cell mismatch")
    start = mapping(placement["from"], "logo from anchor")
    end = mapping(placement["to"], "logo to anchor")

    def marker(name: str, value: Mapping[str, Any]) -> str:
        column = 1 + integer(value["column_delta"], "anchor column delta")
        column_offset = integer(value["column_offset"], "anchor column offset")
        row = 1 + integer(value["row_delta"], "anchor row delta")
        row_offset = integer(value["row_offset"], "anchor row offset")
        return (
            f"<xdr:{name}><xdr:col>{column}</xdr:col>"
            f"<xdr:colOff>{column_offset}</xdr:colOff>"
            f"<xdr:row>{row}</xdr:row>"
            f"<xdr:rowOff>{row_offset}</xdr:rowOff>"
            f"</xdr:{name}>"
        )

    if semantics is not None:
        require(semantics.get("edit_as") == "absolute", "logo editAs mismatch")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<xdr:wsDr xmlns:xdr="{DRAWING_NS}"><xdr:twoCellAnchor editAs="absolute">'
            + marker("from", start)
            + marker("to", end)
            + cast(str, semantics["picture_xml"])
            + "<xdr:clientData/></xdr:twoCellAnchor></xdr:wsDr>"
        ).encode("utf-8")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<xdr:wsDr xmlns:xdr="{DRAWING_NS}" xmlns:a="{DRAWING_MAIN_NS}" '
        f'xmlns:r="{OFFICE_REL_NS}"><xdr:twoCellAnchor editAs="absolute">'
        + marker("from", start)
        + marker("to", end)
        + '<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="DINVA classic logo"/>'
        '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
        '<xdr:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch>'
        '</xdr:blipFill><xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln></xdr:spPr></xdr:pic><xdr:clientData/>"
        "</xdr:twoCellAnchor></xdr:wsDr>"
    ).encode("utf-8")


def custom_properties_xml(values: Mapping[str, str]) -> bytes:
    properties = []
    for pid, (name, value) in enumerate(sorted(values.items()), start=2):
        properties.append(
            f'<property fmtid="{CUSTOM_PROPERTY_FORMAT_ID}" pid="{pid}" '
            f'name="{escape(name)}"><vt:lpwstr>{escape(value)}</vt:lpwstr></property>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Properties xmlns="{CUSTOM_PROPS_NS}" xmlns:vt="{VT_NS}">'
        + "".join(properties)
        + "</Properties>"
    ).encode("utf-8")


def inject_governed_parts(
    path: Path,
    logo: bytes,
    placement: Mapping[str, Any],
    custom_properties: Mapping[str, str],
    drawing_semantics: Mapping[str, Any] | None = None,
) -> None:
    parts = archive_parts(path)
    sheet_name = "xl/worksheets/sheet1.xml"
    root = ElementTree.fromstring(parts[sheet_name])
    # Rich-text serializers may omit xml:space on whitespace-only runs.
    # Preserve the governed text in the raw package, before independent validation.
    for text_node in root.findall(f".//{{{SPREADSHEET_NS}}}t"):
        value = text_node.text or ""
        if value and value != value.strip():
            text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    drawing = ElementTree.SubElement(root, f"{{{SPREADSHEET_NS}}}drawing")
    drawing.set(f"{{{OFFICE_REL_NS}}}id", "rId1")
    ElementTree.register_namespace("", SPREADSHEET_NS)
    ElementTree.register_namespace("r", OFFICE_REL_NS)
    parts[sheet_name] = ElementTree.tostring(
        root, encoding="utf-8", xml_declaration=True
    )
    parts["xl/worksheets/_rels/sheet1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rId1" '
        f'Type="{OFFICE_REL_NS}/drawing" Target="../drawings/drawing1.xml"/>'
        "</Relationships>"
    ).encode()
    parts["xl/drawings/drawing1.xml"] = drawing_xml(placement, drawing_semantics)
    parts["xl/drawings/_rels/drawing1.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}"><Relationship Id="rId1" '
        f'Type="{OFFICE_REL_NS}/image" Target="../media/image1.png"/>'
        "</Relationships>"
    ).encode()
    parts["xl/media/image1.png"] = logo
    content_types = ElementTree.fromstring(parts["[Content_Types].xml"])
    if not any(item.get("Extension") == "png" for item in content_types):
        ElementTree.SubElement(
            content_types,
            f"{{{CONTENT_TYPES_NS}}}Default",
            {"Extension": "png", "ContentType": "image/png"},
        )
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Override",
        {
            "PartName": "/xl/drawings/drawing1.xml",
            "ContentType": "application/vnd.openxmlformats-officedocument.drawing+xml",
        },
    )
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Override",
        {
            "PartName": "/docProps/custom.xml",
            "ContentType": (
                "application/vnd.openxmlformats-officedocument." "custom-properties+xml"
            ),
        },
    )
    ElementTree.register_namespace("", CONTENT_TYPES_NS)
    parts["[Content_Types].xml"] = ElementTree.tostring(
        content_types, encoding="utf-8", xml_declaration=True
    )
    package_rels = ElementTree.fromstring(parts["_rels/.rels"])
    relationship_ids = {item.get("Id") for item in package_rels}
    rid_number = 1
    while f"rId{rid_number}" in relationship_ids:
        rid_number += 1
    ElementTree.SubElement(
        package_rels,
        f"{{{PACKAGE_REL_NS}}}Relationship",
        {
            "Id": f"rId{rid_number}",
            "Type": f"{OFFICE_REL_NS}/custom-properties",
            "Target": "docProps/custom.xml",
        },
    )
    ElementTree.register_namespace("", PACKAGE_REL_NS)
    parts["_rels/.rels"] = ElementTree.tostring(
        package_rels, encoding="utf-8", xml_declaration=True
    )
    parts["docProps/custom.xml"] = custom_properties_xml(custom_properties)
    for name in list(parts):
        if name == "xl/calcChain.xml":
            fail("clean renderer unexpectedly emitted calcChain")
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.rewrite.xlsx")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for name in sorted(parts):
                archive.writestr(name, parts[name])
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dinva_classic_independent_validator", VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        fail("independent validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_output_path(output: Path) -> Path:
    path = resolved(output)
    require(path.suffix.casefold() == ".xlsx", "output suffix must be .xlsx")
    require(not is_inside_project(path), "output must be outside Git")
    require(path.parent.is_dir(), "output parent must already exist")
    require(not path.exists(), "output already exists")
    return path


def render(
    *,
    profile_path: Path,
    expected_profile_sha256: str,
    document_path: Path,
    expected_document_sha256: str,
    output: Path,
    allow_test_profile: bool = False,
) -> Path:
    profile_file, profile_raw, profile = load_bound_json(
        profile_path, expected_profile_sha256, "profile"
    )
    document_file, document_raw, document = load_bound_json(
        document_path, expected_document_sha256, "document"
    )
    validate_profile(profile, allow_test_profile=allow_test_profile)
    validate_document(document, allow_test_profile=allow_test_profile)
    output_path = validate_output_path(output)
    candidate = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.candidate.xlsx"
    )
    try:
        render_clean_workbook(
            profile,
            expected_profile_sha256,
            document,
            expected_document_sha256,
            candidate,
        )
        validator = load_validator()
        validator.validate_or_raise(
            candidate,
            profile,
            expected_profile_sha256,
            document,
            expected_document_sha256,
            allow_test_profile=allow_test_profile,
        )
        require(
            profile_file.read_bytes() == profile_raw, "profile changed during render"
        )
        require(
            document_file.read_bytes() == document_raw, "document changed during render"
        )
        require(not output_path.exists(), "output appeared before atomic publish")
        os.link(candidate, output_path)
        validator.validate_or_raise(
            output_path,
            profile,
            expected_profile_sha256,
            document,
            expected_document_sha256,
            allow_test_profile=allow_test_profile,
        )
        require(
            profile_file.read_bytes() == profile_raw, "profile changed after publish"
        )
        require(
            document_file.read_bytes() == document_raw, "document changed after publish"
        )
    except (OSError, RendererError, ValueError) as exc:
        output_path.unlink(missing_ok=True)
        if isinstance(exc, RendererError):
            raise
        raise RendererError(f"clean render failed: {exc}") from exc
    finally:
        candidate.unlink(missing_ok=True)
    return output_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--document-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--test-only-allow-unapproved-profile",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output = render(
            profile_path=cast(Path, args.profile),
            expected_profile_sha256=cast(str, args.profile_sha256),
            document_path=cast(Path, args.document),
            expected_document_sha256=cast(str, args.document_sha256),
            output=cast(Path, args.output),
            allow_test_profile=bool(args.test_only_allow_unapproved_profile),
        )
    except (OSError, RendererError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_RENDER=PASS_CANDIDATE_ONLY")
    print(f"OUTPUT={output}")
    print("CLIENT_SEND=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
