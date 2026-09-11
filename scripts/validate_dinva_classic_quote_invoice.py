"""Independently validate a rendered DINVA classic quote/invoice XLSX."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import textwrap
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from math import ceil, floor, isfinite
from pathlib import Path
from typing import Any, NoReturn, cast
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.cell.cell import Cell  # type: ignore[import-untyped]
from openpyxl.styles import Border  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FAMILY = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1"
TEST_MODE_ENV = "DINVA_RENDERER_TEST_MODE"
PROFILE_SCHEMA_VERSION = "dinva_classic_presentation_profile.v0.2"
DOCUMENT_SCHEMA_VERSION = "dinva_quote_invoice_document.v0.2"
PROFILE_ID = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_2"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CUSTOM_PROPS_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
)
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {
    "rel": PACKAGE_REL_NS,
    "ct": CONTENT_TYPES_NS,
    "cp": CUSTOM_PROPS_NS,
    "xdr": DRAWING_NS,
    "main": SPREADSHEET_NS,
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
}
EXPECTED_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "docProps/app.xml",
    "docProps/core.xml",
    "docProps/custom.xml",
    "xl/_rels/workbook.xml.rels",
    "xl/drawings/_rels/drawing1.xml.rels",
    "xl/drawings/drawing1.xml",
    "xl/media/image1.png",
    "xl/styles.xml",
    "xl/theme/theme1.xml",
    "xl/workbook.xml",
    "xl/worksheets/_rels/sheet1.xml.rels",
    "xl/worksheets/sheet1.xml",
}


class ValidationError(ValueError):
    """The workbook does not match its governed inputs."""


def fail(message: str) -> NoReturn:
    raise ValidationError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def integer(value: Any, label: str) -> int:
    require(type(value) is int, f"{label} must be an integer")
    return cast(int, value)


def exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    require(set(value) == expected, f"{label} fields mismatch")


def text(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    require(
        isinstance(value, str) and bool(value.strip()),
        f"{label} must be non-empty text",
    )
    return cast(str, value)


def nonnegative_integer(value: Any, label: str, *, minimum: int = 0) -> int:
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


def validate_document_contract(
    document: Mapping[str, Any], *, allow_test_profile: bool
) -> None:
    expected_document_keys = {
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
    exact_keys(document, expected_document_keys, "document")
    require(
        document.get("schema_version") == DOCUMENT_SCHEMA_VERSION,
        "document schema mismatch",
    )
    require(document.get("document_family") == FAMILY, "document family mismatch")
    require(
        document.get("document_type") in {"QUOTE", "INVOICE", "QUOTE_INVOICE"},
        "document type mismatch",
    )
    for field in ("document_id", "document_number", "payer", "apparatus_heading"):
        text(document.get(field), field)
    try:
        date.fromisoformat(cast(str, document.get("document_date")))
    except (TypeError, ValueError) as exc:
        raise ValidationError("document date must be ISO date") from exc
    require(document.get("currency") == "KZT", "document currency mismatch")
    require(
        document.get("document_fingerprint") == document_fingerprint(document),
        "document fingerprint mismatch",
    )
    text(document.get("object_name"), "object_name", nullable=True)
    text(document.get("basis"), "basis", nullable=True)
    items = document.get("items")
    sections = document.get("sections")
    require(isinstance(items, list) and bool(items), "document items must be non-empty")
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
        first = nonnegative_integer(
            section.get("first_position"), "section first position", minimum=1
        )
        last = nonnegative_integer(
            section.get("last_position"), "section last position", minimum=1
        )
        require(
            first == next_position and last >= first,
            "section ranges must be ordered and contiguous",
        )
        next_position = last + 1
    require(
        next_position == len(cast(list[Any], items)) + 1,
        "sections must cover every item exactly once",
    )
    item_keys = {
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
        exact_keys(item, item_keys, f"item {expected_position}")
        require(
            nonnegative_integer(item.get("position"), "item position", minimum=1)
            == expected_position,
            "item positions must be contiguous",
        )
        for field in ("name", "unit", "detailed_technical_composition", "enclosure"):
            text(item.get(field), f"item {expected_position}.{field}")
        apparatus = mapping(
            item.get("apparatus"), f"item {expected_position}.apparatus"
        )
        exact_keys(
            apparatus,
            {"text", "source_role", "source_sha256", "source_locator"},
            "apparatus",
        )
        apparatus_text = cast(str, text(apparatus.get("text"), "apparatus text"))
        require(
            apparatus.get("source_role") == "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
            "apparatus source role mismatch",
        )
        sha256_text(apparatus.get("source_sha256"), "apparatus source SHA-256")
        text(apparatus.get("source_locator"), "apparatus source locator")
        require(
            apparatus_text in cast(str, item["detailed_technical_composition"]),
            "apparatus is not represented in detailed composition",
        )
        reference = mapping(item.get("approval_reference"), "approval reference")
        exact_keys(
            reference, {"pricing", "technical", "enclosure"}, "approval reference"
        )
        text(reference.get("pricing"), "pricing approval reference")
        text(reference.get("technical"), "technical approval reference")
        text(reference.get("enclosure"), "enclosure approval reference", nullable=True)
        quantity = nonnegative_integer(item.get("quantity"), "quantity", minimum=1)
        unit_price = nonnegative_integer(
            item.get("approved_unit_price_kzt"), "unit price"
        )
        line_total = nonnegative_integer(
            item.get("approved_line_total_kzt"), "line total"
        )
        require(
            quantity * unit_price == line_total, "approved item arithmetic mismatch"
        )
        total += line_total
    require(
        nonnegative_integer(document.get("approved_grand_total_kzt"), "grand total")
        == total,
        "approved grand total mismatch",
    )
    amount_words = mapping(document.get("amount_words"), "amount words")
    exact_keys(amount_words, {"amount_kzt", "approved_text"}, "amount words")
    require(
        nonnegative_integer(amount_words.get("amount_kzt"), "amount words amount")
        == total,
        "amount words amount mismatch",
    )
    text(amount_words.get("approved_text"), "amount words text")
    vat = mapping(document.get("vat"), "VAT")
    exact_keys(
        vat, {"rate_percent", "included", "approved_amount_kzt", "approved_text"}, "VAT"
    )
    rate = nonnegative_integer(vat.get("rate_percent"), "VAT rate")
    require(rate <= 100 and type(vat.get("included")) is bool, "VAT contract mismatch")
    divisor = Decimal(100 + rate) if vat["included"] else Decimal(100)
    expected_vat = int(
        (Decimal(total) * Decimal(rate) / divisor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    require(
        nonnegative_integer(vat.get("approved_amount_kzt"), "VAT amount")
        == expected_vat,
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
    lines = terms.get("commercial_lines")
    require(isinstance(lines, list) and bool(lines), "commercial terms lines missing")
    for index, raw_line in enumerate(cast(list[Any], lines), start=1):
        line = mapping(raw_line, f"commercial line {index}")
        exact_keys(
            line,
            {"source_order", "text", "source_sha256", "source_locator"},
            f"commercial line {index}",
        )
        require(
            nonnegative_integer(
                line.get("source_order"), "commercial source order", minimum=1
            )
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
    lead_source_order = nonnegative_integer(
        lead_provenance.get("source_order"), "lead-time source order", minimum=1
    )
    require(
        lead_source_order <= len(cast(list[Any], lines)),
        "lead-time source order is out of range",
    )
    lead_source = mapping(
        cast(list[Any], lines)[lead_source_order - 1],
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
    signature_keys = {
        "director_title",
        "director_name",
        "executor_label",
        "executor_title",
        "executor_name",
        "executor_full_text",
    }
    exact_keys(signatures, signature_keys, "signatures")
    for field in signature_keys:
        text(signatures.get(field), f"signatures.{field}")
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
    approval_keys = {
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
    }
    exact_keys(approval, approval_keys, "document approval")
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
    roles: set[str] = set()
    bound_shas: list[str] = []
    for raw_binding in cast(list[Any], bindings):
        binding = mapping(raw_binding, "source binding")
        exact_keys(binding, {"role", "path", "sha256"}, "source binding")
        role = cast(str, text(binding.get("role"), "source binding role"))
        require(role not in roles, "duplicate source binding role")
        roles.add(role)
        text(binding.get("path"), "source binding path")
        bound_shas.append(sha256_text(binding.get("sha256"), "source binding SHA-256"))
    source_shas = approval.get("source_sha256s")
    require(
        isinstance(source_shas, list)
        and [sha256_text(value, "document source hash") for value in source_shas]
        == bound_shas,
        "document source hashes do not match bindings",
    )
    require(approval.get("rendering_authorized") is True, "rendering is not authorized")
    require(
        approval.get("client_send_authorized") is False, "client-send boundary is open"
    )


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_mode(requested: bool) -> bool:
    return requested and os.environ.get(TEST_MODE_ENV) == "1"


def color_spec(color: Any) -> dict[str, object] | None:
    if color is None or color.type is None:
        return None
    value: str | int
    if color.type == "rgb":
        value = str(color.rgb)
    elif color.type == "indexed":
        value = int(color.indexed)
    elif color.type == "theme":
        value = int(color.theme)
    else:
        fail(f"unsupported workbook color type: {color.type}")
    return {"type": color.type, "value": value, "tint": float(color.tint or 0)}


def style_spec(cell: Cell) -> dict[str, Any]:
    return {
        "font": {
            "name": cell.font.name,
            "size": float(cell.font.sz or 0),
            "bold": bool(cell.font.b),
            "italic": bool(cell.font.i),
            "underline": cell.font.u,
            "color": color_spec(cell.font.color),
        },
        "fill": {
            "type": cell.fill.fill_type,
            "foreground": color_spec(cell.fill.fgColor),
        },
        "border": {
            "left": cell.border.left.style,
            "right": cell.border.right.style,
            "top": cell.border.top.style,
            "bottom": cell.border.bottom.style,
        },
        "alignment": {
            "horizontal": cell.alignment.horizontal,
            "vertical": cell.alignment.vertical,
            "wrap_text": bool(cell.alignment.wrap_text),
            "shrink_to_fit": bool(cell.alignment.shrink_to_fit),
        },
        "number_format": cell.number_format,
    }


def independent_percentile_90(values: Sequence[int]) -> int:
    ordered = sorted(values)
    require(bool(ordered), "content distribution is empty")
    return ordered[max(0, ceil(len(ordered) * 0.9) - 1)]


def independent_content_lengths(document: Mapping[str, Any], column: str) -> list[int]:
    field_by_column = {
        "C": "name",
        "F": "detailed_technical_composition",
        "G": "enclosure",
    }
    items = cast(list[Mapping[str, Any]], document["items"])
    if column in field_by_column:
        field = field_by_column[column]
        return [
            max(len(part) for part in cast(str, item[field]).split("\n"))
            for item in items
        ]
    if column == "I":
        values = [
            cast(int, document["approved_grand_total_kzt"]),
            *[cast(int, item["approved_line_total_kzt"]) for item in items],
        ]
        return [len(format(value, ",")) for value in values]
    return [1]


def independent_widths(
    contract: Mapping[str, Any], document: Mapping[str, Any]
) -> dict[str, float]:
    layout = mapping(contract["layout"], "layout")
    rules = mapping(layout["column_width_rules"], "column width rules")
    result: dict[str, float] = {}
    lower: dict[str, float] = {}
    for column in "BCDEFGHI":
        rule = mapping(rules[column], f"column {column} rule")
        minimum = float(rule["minimum"])
        preferred = float(rule["preferred"])
        maximum = float(rule["maximum"])
        lower[column] = minimum
        if not cast(bool, rule["adaptive"]):
            result[column] = preferred
            continue
        score = independent_percentile_90(independent_content_lengths(document, column))
        preferred_chars = integer(rule["preferred_chars"], "preferred chars")
        maximum_chars = integer(rule["maximum_chars"], "maximum chars")
        require(maximum_chars > preferred_chars, "column content thresholds invalid")
        if score <= preferred_chars:
            calculated = minimum + (preferred - minimum) * score / preferred_chars
        else:
            ratio = min(
                1.0,
                (score - preferred_chars) / (maximum_chars - preferred_chars),
            )
            calculated = preferred + (maximum - preferred) * ratio
        result[column] = round(calculated * 4) / 4
    limit = float(layout["maximum_printable_width"])
    excess = sum(result.values()) - limit
    for column in ("C", "G", "F", "I"):
        if excess <= 1e-9:
            break
        result[column] = (
            round(
                (
                    result[column]
                    - min(result[column] - lower[column], ceil(excess * 4 - 1e-9) / 4)
                )
                * 4
            )
            / 4
        )
        excess = sum(result.values()) - limit
    require(excess <= 1e-9, "column width bounds exceed printable width")
    return result


def independent_wrapped_lines(value: str, width: float, font_size: float) -> int:
    capacity = max(1, int(width * 11.0 / font_size * 0.94))
    return sum(max(1, ceil(len(part) / capacity)) for part in value.split("\n"))


def independent_item_height(
    item: Mapping[str, Any],
    widths: Mapping[str, float],
    rule: Mapping[str, Any],
    styles: Mapping[str, Any],
) -> float:
    definitions = (
        ("C", "name", "item_name"),
        ("F", "detailed_technical_composition", "technical_composition"),
        ("G", "enclosure", "enclosure"),
    )
    line_counts = []
    for column, field, role in definitions:
        font = mapping(mapping(styles[role], role)["font"], f"{role} font")
        line_counts.append(
            independent_wrapped_lines(
                cast(str, item[field]), widths[column], float(font["size"])
            )
        )
    required = max(line_counts) * float(rule["line_height_points"]) + float(
        rule["vertical_padding_points"]
    )
    require(
        required <= float(rule["maximum_height"]),
        "item content exceeds safe Excel row height",
    )
    return round(max(float(rule["minimum_height"]), required) * 4) / 4


def independent_header_height(
    contract: Mapping[str, Any],
    document: Mapping[str, Any],
    widths: Mapping[str, float],
) -> float:
    fixed = mapping(contract["fixed_blocks"], "fixed blocks")
    headers = dict(mapping(fixed["table_headers"], "table headers"))
    headers["F"] = document["apparatus_heading"]
    styles = mapping(contract["styles"], "styles")
    header_font = mapping(
        mapping(styles["table_header"], "header style")["font"], "header font"
    )
    line_count = max(
        independent_wrapped_lines(
            cast(str, headers[column]), widths[column], float(header_font["size"])
        )
        for column in "BCDEFGHI"
    )
    rule = mapping(
        mapping(contract["layout"], "layout")["row_height_rule"], "height rule"
    )
    return (
        round(
            max(
                float(rule["header_minimum_height"]),
                line_count * float(rule["header_line_height_points"])
                + float(rule["vertical_padding_points"]),
            )
            * 4
        )
        / 4
    )


def independent_object_height(
    contract: Mapping[str, Any],
    document: Mapping[str, Any],
    widths: Mapping[str, float],
) -> float:
    layout = mapping(contract["layout"], "layout")
    baseline = float(mapping(layout["top_row_heights"], "top heights")["13"])
    if "top_block_rules" not in layout or document["object_name"] is None:
        return baseline
    if contract.get("contract_version") in {
        "dinva_classic_presentation_contract.v0.4",
        "dinva_classic_presentation_contract.v0.5",
    }:
        rule = mapping(
            mapping(layout["top_block_rules"], "top rules")["object_presentation"],
            "object presentation",
        )
        require(
            rule.get("model") == "NATIVE_EXCEL_SINGLE_LINE_SPILL_V1"
            and rule.get("cell") == "C13"
            and rule.get("row_height_pt") == baseline == 26.1
            and rule.get("line_break_display") == "ZERO_ADVANCE_SINGLE_LINE"
            and rule.get("spill_columns") == list("CDEFGH")
            and rule.get("required_empty_cells") == ["D13", "E13", "F13", "G13", "H13"]
            and rule.get("maximum_digit_width_px") == 7
            and rule.get("horizontal_padding_px") == 5
            and rule.get("stored_alignment")
            == {
                "horizontal": None,
                "vertical": None,
                "wrap_text": False,
                "shrink_to_fit": False,
            }
            and rule.get("effective_alignment")
            == {"horizontal": "general", "vertical": "bottom"},
            "canonical object spill contract mismatch",
        )
        font = mapping(
            mapping(mapping(contract["styles"], "styles")["object"], "object style")[
                "font"
            ],
            "object font",
        )
        canonical_font = {
            "name": "Times New Roman",
            "size": 14,
            "bold": True,
            "italic": True,
            "color_indexed": 8,
        }
        require(
            rule.get("font") == canonical_font
            and all(
                font.get(k) == v
                for k, v in canonical_font.items()
                if k != "color_indexed"
            )
            and font.get("color") == {"type": "indexed", "value": 8, "tint": 0.0},
            "canonical object font mismatch",
        )
        style = mapping(
            mapping(mapping(contract["styles"], "styles")["object"], "object style"),
            "object style",
        )
        require(
            mapping(style["alignment"], "object alignment") == rule["stored_alignment"],
            "canonical object alignment mismatch",
        )
        advances = mapping(rule["glyph_upper_advances_pt"], "glyph advances")
        require(
            bool(advances)
            and all(
                type(v) in (int, float) and isfinite(v) and 0 < v < 100
                for v in advances.values()
            ),
            "canonical glyph advance invalid",
        )
        available = (
            sum(
                floor((256 * float(widths[column]) + floor(128 / 7)) / 256 * 7) * 0.75
                for column in "CDEFGH"
            )
            - 5 * 0.75
        )
        require(available > 0, "canonical object spill corridor invalid")
        visible = str(document["object_name"]).replace("\r", "").replace("\n", "")
        require(
            all(str(ord(character)) in advances for character in visible),
            "unmeasured object glyph",
        )
        required = sum(float(advances[str(ord(character))]) for character in visible)
        require(
            required <= available,
            "object content exceeds canonical C13:H13 spill corridor",
        )
        return baseline
    rule = mapping(
        mapping(layout["top_block_rules"], "top rules")["object_height"], "object rule"
    )
    require(
        dict(rule)
        == {
            "cell": "C13",
            "glyph_width_em": 1.1,
            "line_height_em": 1.5,
            "padding_points": 6.0,
            "maximum_height": 408.0,
        },
        "unsupported object height rule",
    )
    styles = mapping(contract["styles"], "styles")
    font = mapping(mapping(styles["object"], "object style")["font"], "object font")
    size = float(font["size"])
    usable_points = (float(widths["C"]) * 7 + 5) * 3 / 4 - 6
    chars = max(1, int(usable_points / (size * 1.1)))
    line_count = 0
    for paragraph in str(document["object_name"]).split("\n"):
        line_count += max(
            1,
            len(
                textwrap.wrap(
                    paragraph,
                    width=chars,
                    replace_whitespace=False,
                    drop_whitespace=False,
                )
            ),
        )
    required = max(baseline, ceil((line_count * size * 1.5 + 6) * 4) / 4)
    require(required <= 408, "object content exceeds safe Excel row height")
    return required


def independent_layout_plan(
    contract: Mapping[str, Any], document: Mapping[str, Any]
) -> dict[str, Any]:
    layout = mapping(contract["layout"], "layout")
    styles = mapping(contract["styles"], "styles")
    widths = independent_widths(contract, document)
    rule = mapping(layout["row_height_rule"], "row height rule")
    row = integer(layout["first_content_row"], "first content row")
    rows: list[dict[str, Any]] = []
    items = cast(list[Mapping[str, Any]], document["items"])
    indexed = {cast(int, item["position"]): item for item in items}
    for section in cast(list[Mapping[str, Any]], document["sections"]):
        rows.append(
            {"row": row, "kind": "section", "height": float(rule["section_height"])}
        )
        row += 1
        first = cast(int, section["first_position"])
        last = cast(int, section["last_position"])
        for position in range(first, last + 1):
            item = indexed[position]
            rows.append(
                {
                    "row": row,
                    "kind": "item",
                    "position": position,
                    "height": independent_item_height(item, widths, rule, styles),
                }
            )
            row += 1
    last_data_row = row - 1
    total_row = row
    bottom = mapping(layout["bottom_layout"], "bottom layout")
    amount_row = total_row + integer(bottom["amount_words_offset"], "amount offset")
    commercial_start = amount_row + 1
    line_count = len(
        cast(list[Any], mapping(document["terms"], "terms")["commercial_lines"])
    )
    director_row = (
        commercial_start
        + line_count
        + integer(bottom["signature_spacer_rows"], "signature spacer")
    )
    executor_row = director_row + 1
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
                for offset in range(line_count)
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
        limit = float(pagination["first_page_body_height_points"])
        limit -= independent_object_height(contract, document, widths) - float(
            mapping(layout["top_row_heights"], "top heights")["13"]
        )
        next_limit = float(pagination["following_page_body_height_points"])
        groups: list[list[dict[str, Any]]] = []
        index = 0
        while index < len(rows):
            entry = rows[index]
            if (
                entry["kind"] == "section"
                and index + 1 < len(rows)
                and rows[index + 1]["kind"] == "item"
            ):
                groups.append(rows[index : index + 2])
                index += 2
            elif entry["kind"] == "total":
                groups.append(rows[index:])
                break
            else:
                groups.append([entry])
                index += 1
        used = 0.0
        previous: int | None = None
        for group in groups:
            group_height = sum(float(entry["height"]) for entry in group)
            require(group_height <= next_limit, "layout group exceeds page height")
            if previous is not None and used > 0 and used + group_height > limit:
                breaks.append(previous)
                used = 0.0
                limit = next_limit
            used += group_height
            previous = cast(int, group[-1]["row"])
    return {
        "widths": widths,
        "rows": rows,
        "last_data_row": last_data_row,
        "total_row": total_row,
        "amount_row": amount_row,
        "commercial_start": commercial_start,
        "director_row": director_row,
        "executor_row": executor_row,
        "final_row": executor_row,
        "page_breaks": breaks,
        "header_height": independent_header_height(contract, document, widths),
    }


def independent_display_date(value: str) -> str:
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


def validate_governance(
    profile: Mapping[str, Any],
    profile_sha256: str,
    document: Mapping[str, Any],
    document_sha256: str,
    *,
    allow_test_profile: bool,
) -> Mapping[str, Any]:
    sha256_text(profile_sha256, "profile binding SHA-256")
    sha256_text(document_sha256, "document binding SHA-256")
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
    require(profile.get("document_family") == FAMILY, "profile family mismatch")
    require(
        document.get("schema_version") == DOCUMENT_SCHEMA_VERSION,
        "document schema mismatch",
    )
    require(document.get("document_family") == FAMILY, "document family mismatch")
    validate_document_contract(document, allow_test_profile=allow_test_profile)
    contract = mapping(profile.get("presentation_contract"), "presentation contract")
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
    fingerprint = sha256_bytes(canonical_json(contract))
    if visual:
        require(
            "top_block_rules" in mapping(contract["layout"], "layout"),
            "visual top block contract missing",
        )
    require(
        profile.get("presentation_contract_fingerprint") == fingerprint,
        "profile fingerprint mismatch",
    )
    approval = mapping(profile.get("approval_provenance"), "profile approval")
    if test_mode(allow_test_profile):
        require(
            approval.get("status") in {"DRAFT_UNAPPROVED", "APPROVED"},
            "test profile status invalid",
        )
    else:
        require(
            profile.get("artifact_status") == "IMMUTABLE_APPROVED_PROFILE",
            "profile is not immutable",
        )
        require(approval.get("status") == "APPROVED", "profile is not approved")
        require(
            approval.get("authority") == "IGOR_DIRECT_HUMAN_APPROVAL",
            "profile authority mismatch",
        )
        require(
            approval.get("approved_contract_fingerprint") == fingerprint,
            "profile approval binding mismatch",
        )
    document_approval = mapping(
        document.get("approval_provenance"), "document approval"
    )
    require(document_approval.get("status") == "APPROVED", "document is not approved")
    require(
        document_approval.get("rendering_authorized") is True,
        "rendering is not authorized",
    )
    require(
        document_approval.get("client_send_authorized") is False,
        "client-send boundary is open",
    )
    return contract


def expected_cells(
    contract: Mapping[str, Any], document: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, str], dict[int, float], dict[str, Any]]:
    layout = mapping(contract["layout"], "layout")
    fixed = mapping(contract["fixed_blocks"], "fixed blocks")
    plan = independent_layout_plan(contract, document)
    cells: dict[str, Any] = dict(mapping(fixed["company"], "company block"))
    terms = mapping(document["terms"], "terms")
    title_by_type = {
        "QUOTE": "Коммерческое предложение",
        "INVOICE": "Счёт",
        "QUOTE_INVOICE": "Счёт-КП",
    }
    cells.update(
        {
            "C9": (
                f"{title_by_type[cast(str, document['document_type'])]} № "
                f"{document['document_number']} от "
                f"{independent_display_date(cast(str, document['document_date']))}"
            ),
            "C10": f"Плательщик: {document['payer']}",
            "G9": mapping(fixed["warning"], "warning block")["G9"],
            "G10": f"Срок изготовления {terms['manufacturing_lead_time']}",
        }
    )
    if document["object_name"] is not None:
        cells["C13"] = document["object_name"]
    styles: dict[str, str] = {}
    for coordinate in mapping(fixed["company"], "company block"):
        styles[coordinate] = (
            "company_title"
            if coordinate == "C2"
            else (
                "country"
                if coordinate == "C3"
                else (
                    "bank_title"
                    if coordinate in {"I2", "I3"}
                    else "bank_info" if coordinate.startswith("I") else "company_info"
                )
            )
        )
    styles.update(
        {"C9": "document_title", "C10": "payer", "G9": "warning", "G10": "lead_time"}
    )
    if "C13" in cells:
        styles["C13"] = "object"
    header_row = integer(layout["table_header_row"], "header row")
    headers = dict(mapping(fixed["table_headers"], "table headers"))
    headers["F"] = document["apparatus_heading"]
    for column in "BCDEFGHI":
        cells[f"{column}{header_row}"] = headers[column]
        styles[f"{column}{header_row}"] = (
            "table_header_left"
            if column == "B"
            else "table_header_right" if column == "I" else "table_header"
        )
    sections = cast(list[Mapping[str, Any]], document["sections"])
    row_heights: dict[int, float] = {}
    style_names = {
        "B": "position",
        "C": "item_name",
        "D": "unit",
        "E": "quantity",
        "F": "technical_composition",
        "G": "enclosure",
        "H": "money",
        "I": "line_total",
    }
    items = cast(list[Mapping[str, Any]], document["items"])
    item_by_position = {cast(int, item["position"]): item for item in items}
    line_template = cast(
        str, mapping(contract["formulas"], "formulas")["line_total_template"]
    )
    section_iter = iter(sections)
    current_section = next(section_iter)
    next_section = next(section_iter, None)
    for entry in cast(list[dict[str, Any]], plan["rows"]):
        row = cast(int, entry["row"])
        row_heights[row] = float(entry["height"])
        if entry["kind"] == "section":
            cells[f"C{row}"] = current_section["label"]
            for column in "BCDEFGHI":
                styles[f"{column}{row}"] = "section"
            current_section = (
                next_section if next_section is not None else current_section
            )
            next_section = next(section_iter, None)
            continue
        if entry["kind"] != "item":
            continue
        item = item_by_position[cast(int, entry["position"])]
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
            cells[f"{column}{row}"] = value
            styles[f"{column}{row}"] = style_names[column]
    total_row = cast(int, plan["total_row"])
    cells[f"C{total_row}"] = fixed["total_label"]
    grand_template = cast(
        str, mapping(contract["formulas"], "formulas")["grand_total_template"]
    )
    cells[f"I{total_row}"] = grand_template.format(
        start=integer(layout["first_content_row"], "first content row"),
        end=cast(int, plan["last_data_row"]),
    )
    styles[f"C{total_row}"] = "total_label"
    styles[f"I{total_row}"] = "total_amount"
    vat = mapping(document["vat"], "VAT")
    amount_row = cast(int, plan["amount_row"])
    approved_words = mapping(document["amount_words"], "amount words")["approved_text"]
    cells[f"C{amount_row}"] = f"ВСЕГО: {approved_words}, {vat['approved_text']}."
    styles[f"C{amount_row}"] = "amount_words"
    for offset, raw_line in enumerate(
        cast(list[Mapping[str, Any]], terms["commercial_lines"])
    ):
        row = cast(int, plan["commercial_start"]) + offset
        cells[f"C{row}"] = raw_line["text"]
        styles[f"C{row}"] = "commercial_line"
    signatures = mapping(document["signatures"], "signatures")
    director_row = cast(int, plan["director_row"])
    executor_row = cast(int, plan["executor_row"])
    cells.update(
        {
            f"C{director_row}": signatures["director_title"],
            f"F{director_row}": signatures["director_name"],
            f"H{director_row}": signatures["executor_label"],
            f"E{executor_row}": "=C9",
            f"H{executor_row}": signatures["executor_full_text"],
        }
    )
    styles[f"C{director_row}"] = "director"
    styles[f"F{director_row}"] = "director_name"
    for coordinate in (f"H{director_row}", f"E{executor_row}", f"H{executor_row}"):
        styles[coordinate] = "executor"
    row_heights[integer(layout["table_header_row"], "header row")] = float(
        plan["header_height"]
    )
    for raw_row, raw_height in mapping(
        layout["top_row_heights"], "top heights"
    ).items():
        row_heights[int(raw_row)] = float(raw_height)
    row_heights[13] = independent_object_height(contract, document, plan["widths"])
    return cells, styles, row_heights, plan


def validate_workbook(
    path: Path, contract: Mapping[str, Any], document: Mapping[str, Any]
) -> None:
    try:
        workbook = load_workbook(
            path, data_only=False, read_only=False, keep_links=True
        )
    except (OSError, ValueError, BadZipFile) as exc:
        raise ValidationError(f"XLSX cannot be reopened: {exc}") from exc
    try:
        sheet_contracts = cast(
            list[Mapping[str, Any]], mapping(contract["workbook"], "workbook")["sheets"]
        )
        expected_names = [cast(str, item["name"]) for item in sheet_contracts]
        require(workbook.sheetnames == expected_names, "sheet set/order drift")
        worksheet = workbook[expected_names[0]]
        cells, style_names, row_heights, plan = expected_cells(contract, document)
        final_row = cast(int, plan["final_row"])
        for coordinate, expected in cells.items():
            require(
                worksheet[coordinate].value == expected,
                f"business cell drift: {coordinate}",
            )
        allowed = set(cells)
        for row in worksheet.iter_rows(
            min_row=1, max_row=max(worksheet.max_row, final_row), min_col=2, max_col=9
        ):
            for cell in row:
                if cell.value is not None:
                    require(
                        cell.coordinate in allowed,
                        f"unexpected business cell: {cell.coordinate}",
                    )
        profile_styles = mapping(contract["styles"], "styles")
        top_rules = mapping(
            mapping(contract["layout"], "layout").get("top_block_rules", {}),
            "top rules",
        )
        top_borders = mapping(top_rules.get("border_xml_by_cell", {}), "top borders")
        if top_rules:
            require(
                set(top_borders)
                == {f"{c}{r}" for r in range(2, 15) for c in "BCDEFGHI"},
                "top border map mismatch",
            )
            for coordinate, raw_border in top_borders.items():
                expected_border = Border.from_tree(
                    ElementTree.fromstring(str(raw_border))
                )
                require(
                    worksheet[coordinate].border == expected_border,
                    f"top border drift: {coordinate}",
                )
        for coordinate, style_name in style_names.items():
            actual_style = style_spec(worksheet[coordinate])
            if coordinate in top_borders:
                # Exact full border checked above, independently of role styles.
                actual_style["border"] = mapping(profile_styles[style_name], "style")[
                    "border"
                ]
            require(
                actual_style == profile_styles[style_name],
                f"style drift: {coordinate}",
            )
            require(
                worksheet[coordinate].font.name == "Times New Roman",
                f"font drift: {coordinate}",
            )
        layout = mapping(contract["layout"], "layout")
        for column, expected in cast(dict[str, float], plan["widths"]).items():
            actual = worksheet.column_dimensions[column].width
            require(
                actual is not None and abs(float(actual) - float(expected)) < 1e-9,
                f"width drift: {column}",
            )
        for row, expected in row_heights.items():
            actual = worksheet.row_dimensions[row].height
            require(
                actual is not None and abs(float(actual) - expected) < 1e-9,
                f"height drift: {row}",
            )
        expected_merges = set(
            cast(list[str], mapping(layout["merged_cells"], "merges")["ranges"])
        )
        require(
            {str(value) for value in worksheet.merged_cells.ranges} == expected_merges,
            "merged-cell drift",
        )
        require(
            worksheet.sheet_view.showGridLines is True,
            "gridline visibility drift",
        )
        print_contract = mapping(contract["print"], "print contract")
        require(
            str(worksheet.page_setup.paperSize) == str(print_contract["paper_size"]),
            "paper-size drift",
        )
        require(
            worksheet.page_setup.orientation == print_contract["orientation"],
            "orientation drift",
        )
        require(
            worksheet.page_setup.scale == print_contract["scale"], "print scale drift"
        )
        require(
            worksheet.page_setup.fitToHeight == print_contract["fit_to_height"],
            "fit-height drift",
        )
        require(
            worksheet.page_setup.fitToWidth == print_contract["fit_to_width"],
            "fit-width drift",
        )
        require(
            bool(worksheet.sheet_properties.pageSetUpPr.fitToPage)
            == bool(print_contract["fit_to_page"]),
            "fit-to-page drift",
        )
        for name, expected in mapping(print_contract["margins"], "margins").items():
            require(
                abs(float(getattr(worksheet.page_margins, name)) - float(expected))
                < 1e-9,
                f"margin drift: {name}",
            )
        if (
            contract.get("contract_version")
            == "dinva_classic_presentation_contract.v0.5"
        ):
            require(
                not worksheet.print_area
                and not worksheet.print_title_rows
                and not worksheet.print_title_cols,
                "noncanonical print names",
            )
            require(
                not worksheet.row_breaks.brk and not worksheet.col_breaks.brk,
                "noncanonical print breaks",
            )
        else:
            expected_area = f"'{expected_names[0]}'!$B$1:$I${final_row}"
            require(str(worksheet.print_area) == expected_area, "print-area drift")
            pagination = mapping(layout["pagination"], "pagination")
            require(
                str(worksheet.print_title_rows).replace("$", "")
                == cast(str, pagination["repeat_rows"]),
                "repeating header rows drift",
            )
            actual_breaks = [cast(int, item.id) for item in worksheet.row_breaks.brk]
            require(actual_breaks == plan["page_breaks"], "pagination row-break drift")
    finally:
        workbook.close()


def relationship_nodes(parts: Mapping[str, bytes]) -> list[ElementTree.Element]:
    nodes: list[ElementTree.Element] = []
    for name, raw in parts.items():
        if name.endswith(".rels"):
            try:
                root = ElementTree.fromstring(raw)
            except ElementTree.ParseError as exc:
                raise ValidationError(f"invalid relationship part: {name}") from exc
            nodes.extend(root.findall("rel:Relationship", NS))
    return nodes


def validate_calc_chain(
    parts: Mapping[str, bytes], formula_coordinates: set[str]
) -> None:
    nodes = relationship_nodes(parts)
    calc_rels = [
        node
        for node in nodes
        if "calcChain" in cast(str, node.get("Type", ""))
        or "calcChain" in cast(str, node.get("Target", ""))
    ]
    content_types = ElementTree.fromstring(parts["[Content_Types].xml"])
    calc_types = [
        node
        for node in content_types
        if "calcChain" in cast(str, node.get("PartName", ""))
        or "calcChain" in cast(str, node.get("ContentType", ""))
    ]
    if "xl/calcChain.xml" not in parts:
        require(not calc_rels and not calc_types, "calcChain residue without part")
        return
    require(
        len(calc_rels) == 1 and len(calc_types) == 1,
        "calcChain package binding invalid",
    )
    try:
        root = ElementTree.fromstring(parts["xl/calcChain.xml"])
    except ElementTree.ParseError as exc:
        raise ValidationError("calcChain XML invalid") from exc
    refs = [node.get("r") for node in root.findall("main:c", NS)]
    require(all(isinstance(ref, str) and ref for ref in refs), "calcChain ref invalid")
    require(len(refs) == len(set(refs)), "calcChain duplicate ref")
    require(
        set(cast(list[str], refs)) == formula_coordinates,
        "calcChain stale/orphan/missing ref",
    )


def validate_package(
    path: Path,
    contract: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_sha256: str,
    document_sha256: str,
) -> None:
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), "duplicate OOXML part")
            parts = {name: archive.read(name) for name in names}
    except (OSError, BadZipFile) as exc:
        raise ValidationError(f"invalid OOXML package: {exc}") from exc
    actual_parts = set(parts)
    require(
        actual_parts == EXPECTED_PARTS
        or actual_parts == EXPECTED_PARTS | {"xl/calcChain.xml"},
        "unexpected/missing OOXML part",
    )
    package = mapping(contract["package"], "package contract")
    for name in parts:
        require(
            not any(
                name.startswith(prefix)
                for prefix in cast(list[str], package["forbidden_part_prefixes"])
            ),
            f"forbidden part: {name}",
        )
        require(
            not any(
                name.endswith(suffix)
                for suffix in cast(list[str], package["forbidden_part_suffixes"])
            ),
            f"forbidden part: {name}",
        )
    relationships = relationship_nodes(parts)
    require(
        not any(node.get("TargetMode") == "External" for node in relationships),
        "external relationship found",
    )
    expected_custom = {
        "DINVA_PROFILE_ID": cast(str, profile["profile_id"]),
        "DINVA_DOCUMENT_FAMILY": FAMILY,
        "DINVA_PROFILE_SHA256": profile_sha256,
        "DINVA_PRESENTATION_FINGERPRINT": cast(
            str, profile["presentation_contract_fingerprint"]
        ),
        "DINVA_DOCUMENT_SHA256": document_sha256,
    }
    custom_root = ElementTree.fromstring(parts["docProps/custom.xml"])
    custom: dict[str, str] = {}
    for node in custom_root.findall("cp:property", NS):
        require(node.get("name") not in custom, "duplicate custom property")
        value_node = next(iter(node), None)
        require(
            value_node is not None and value_node.text is not None,
            "empty custom property",
        )
        custom[cast(str, node.get("name"))] = cast(
            str, cast(ElementTree.Element, value_node).text
        )
    require(custom == expected_custom, "profile/document package binding drift")
    asset = mapping(cast(list[Any], contract["assets"])[0], "logo asset")
    logo = parts["xl/media/image1.png"]
    require(sha256_bytes(logo) == asset["sha256"], "logo hash drift")
    require(
        logo == base64.b64decode(cast(str, asset["data_base64"]), validate=True),
        "logo bytes drift",
    )
    drawing = ElementTree.fromstring(parts["xl/drawings/drawing1.xml"])
    anchors = drawing.findall("xdr:twoCellAnchor", NS)
    require(len(anchors) == 1, "logo anchor count drift")
    placement = mapping(asset["placement"], "logo placement")
    if contract.get("contract_version") in {
        "dinva_classic_presentation_contract.v0.3",
        "dinva_classic_presentation_contract.v0.4",
        "dinva_classic_presentation_contract.v0.5",
    }:
        validate_logo_drawing(drawing, asset, profile, logo)
    if contract.get("contract_version") in {
        "dinva_classic_presentation_contract.v0.4",
        "dinva_classic_presentation_contract.v0.5",
    }:
        validate_object_presentation(parts, profile)
        validate_country_rich_text(parts, profile)
    if contract.get("contract_version") == "dinva_classic_presentation_contract.v0.5":
        validate_native_print(parts, profile)
    require(
        placement.get("anchor_type") == "TWO_CELL"
        and placement.get("relative_to") == "COMPANY_HEADER_BLOCK"
        and placement.get("base_cell") == "B2",
        "logo anchor type drift",
    )
    for marker_name in ("from", "to"):
        anchor_node = anchors[0].find(f"xdr:{marker_name}", NS)
        require(anchor_node is not None, f"logo {marker_name} anchor missing")
        expected = mapping(placement[marker_name], f"logo {marker_name}")
        expected_values = {
            "col": 1 + integer(expected["column_delta"], "logo column delta"),
            "colOff": integer(expected["column_offset"], "logo column offset"),
            "row": 1 + integer(expected["row_delta"], "logo row delta"),
            "rowOff": integer(expected["row_offset"], "logo row offset"),
        }
        for xml_name, expected_value in expected_values.items():
            child = cast(ElementTree.Element, anchor_node).find(f"xdr:{xml_name}", NS)
            require(
                child is not None and child.text == str(expected_value),
                f"logo anchor drift: {marker_name}.{xml_name}",
            )
    require(
        integer(mapping(placement["to"], "logo to")["row_delta"], "logo end row")
        < integer(placement["protected_first_row"], "protected first row") - 1,
        "logo overlaps protected company content",
    )
    drawing_rels = ElementTree.fromstring(parts["xl/drawings/_rels/drawing1.xml.rels"])
    image_rels = [
        node
        for node in drawing_rels.findall("rel:Relationship", NS)
        if node.get("Type") == f"{OFFICE_REL_NS}/image"
    ]
    require(
        len(image_rels) == 1 and image_rels[0].get("Target") == "../media/image1.png",
        "logo relationship drift",
    )
    sheet_rels = ElementTree.fromstring(parts["xl/worksheets/_rels/sheet1.xml.rels"])
    drawing_references = [
        node
        for node in sheet_rels.findall("rel:Relationship", NS)
        if node.get("Type") == f"{OFFICE_REL_NS}/drawing"
    ]
    require(
        len(drawing_references) == 1
        and drawing_references[0].get("Target") == "../drawings/drawing1.xml",
        "drawing relationship drift",
    )
    sheet_xml = ElementTree.fromstring(parts["xl/worksheets/sheet1.xml"])
    formulas = {
        cast(str, cell.get("r"))
        for cell in sheet_xml.findall(".//main:c", NS)
        if cell.find("main:f", NS) is not None
    }
    validate_calc_chain(parts, formulas)


def validate_logo_drawing(
    drawing: ElementTree.Element,
    asset: Mapping[str, Any],
    profile: Mapping[str, Any],
    logo: bytes,
) -> None:
    """Check full picture semantics independently, not via renderer helpers."""
    semantics = mapping(asset.get("drawing_semantics"), "logo drawing semantics")
    try:
        expected = ElementTree.fromstring(cast(str, semantics["picture_xml"]))
    except (KeyError, TypeError, ElementTree.ParseError) as exc:
        raise ValidationError("logo governed picture XML invalid") from exc
    require(
        len(drawing) == 1
        and semantics.get("edit_as") == "absolute"
        and drawing[0].attrib == {"editAs": "absolute"},
        "logo DrawingML anchor semantics drift",
    )
    for path in (
        "xdr:spPr/a:xfrm/a:off",
        "xdr:spPr/a:xfrm/a:ext",
        "xdr:blipFill/a:srcRect",
        "xdr:blipFill/a:stretch/a:fillRect",
        "xdr:blipFill/a:blip/a:extLst/a:ext/a14:useLocalDpi",
    ):
        require(expected.find(path, NS) is not None, "logo governed geometry missing")
    require(
        semantics.get("source_sha256s")
        == sorted(
            b["actual_sha256"]
            for b in cast(list[dict[str, Any]], profile["reference_provenance"])
            if b["role"] == "CLASSIC_FAMILY_EVIDENCE"
        )
        and semantics.get("source_locator")
        == "xl/drawings/drawing1.xml;xl/media/image1.png"
        and semantics.get("normalization")
        == "cNvPr/@id=1 (package-local identity only)",
        "logo drawing source binding drift",
    )
    require(
        logo[:8] == b"\x89PNG\r\n\x1a\n"
        and logo[12:16] == b"IHDR"
        and semantics.get("native_width_px") == int.from_bytes(logo[16:20], "big")
        and semantics.get("native_height_px") == int.from_bytes(logo[20:24], "big"),
        "logo native dimensions drift",
    )

    def signature(node: ElementTree.Element) -> tuple[Any, ...]:
        return (
            node.tag,
            sorted(node.attrib.items()),
            (node.text or "").strip(),
            tuple(signature(child) for child in node),
        )

    pictures = drawing[0].findall("xdr:pic", NS)
    require(
        expected.tag == f"{{{DRAWING_NS}}}pic"
        and len(pictures) == 1
        and signature(pictures[0]) == signature(expected),
        "logo DrawingML picture geometry drift",
    )
    require(
        [node.tag for node in drawing[0]]
        == [f"{{{DRAWING_NS}}}{name}" for name in ("from", "to", "pic", "clientData")]
        and not drawing[0][-1].attrib
        and len(drawing[0][-1]) == 0,
        "logo DrawingML children drift",
    )


def validate_object_presentation(
    parts: Mapping[str, bytes], profile: Mapping[str, Any]
) -> None:
    """Verify source binding and the fixed native C13 spill geometry."""

    contract = profile["presentation_contract"]
    rule = contract["layout"]["top_block_rules"]["object_presentation"]
    bindings = profile["reference_provenance"]
    require(
        rule.get("source_sha256s")
        == sorted(
            binding["actual_sha256"]
            for binding in bindings
            if binding["role"] == "CLASSIC_FAMILY_EVIDENCE"
        ),
        "object family source binding drift",
    )
    measurement_sources = [
        binding
        for binding in bindings
        if binding["role"] == "NATIVE_C13_BOLD_ITALIC_WIDTH_MEASUREMENTS"
    ]
    font_sources = [
        binding
        for binding in bindings
        if binding["role"] == "NATIVE_OBJECT_BOLD_ITALIC_FONT_SOURCE"
    ]
    require(
        len(measurement_sources) == 1
        and measurement_sources[0]["expected_sha256"]
        == measurement_sources[0]["actual_sha256"]
        == rule.get("measurement_source_sha256"),
        "object measurement source binding drift",
    )
    require(
        len(font_sources) == 1
        and font_sources[0]["expected_sha256"]
        == font_sources[0]["actual_sha256"]
        == rule.get("font_source_sha256"),
        "object font source binding drift",
    )
    sheet = ElementTree.fromstring(parts["xl/worksheets/sheet1.xml"])
    row = sheet.find(f".//{{{SPREADSHEET_NS}}}row[@r='13']")
    require(
        row is not None
        and abs(float(row.get("ht", "0")) - 26.1) < 1e-9
        and row.get("customHeight") == "1",
        "canonical row 13 geometry drift",
    )
    for coordinate in rule["required_empty_cells"]:
        cell = sheet.find(f".//{{{SPREADSHEET_NS}}}c[@r='{coordinate}']")
        require(
            cell is None
            or (
                cell.find(f"{{{SPREADSHEET_NS}}}v") is None
                and cell.find(f"{{{SPREADSHEET_NS}}}is") is None
                and cell.find(f"{{{SPREADSHEET_NS}}}f") is None
            ),
            f"canonical spill cell occupied: {coordinate}",
        )


def validate_country_rich_text(
    parts: Mapping[str, bytes], profile: Mapping[str, Any]
) -> dict[str, float]:
    """Verify actual inline runs and physical bounds, independently of renderer."""
    styles_root = ElementTree.fromstring(parts["xl/styles.xml"])
    normal = styles_root.find(
        f"{{{SPREADSHEET_NS}}}cellStyles/{{{SPREADSHEET_NS}}}cellStyle[@name='Normal']"
    )
    style_xfs = styles_root.find(f"{{{SPREADSHEET_NS}}}cellStyleXfs")
    fonts = styles_root.find(f"{{{SPREADSHEET_NS}}}fonts")
    require(
        normal is not None and style_xfs is not None and fonts is not None,
        "native physical font metadata missing",
    )
    assert normal is not None and style_xfs is not None and fonts is not None
    xf_index = int(normal.get("xfId", "-1"))
    require(0 <= xf_index < len(style_xfs), "native Normal style index invalid")
    font_index = int(style_xfs[xf_index].get("fontId", "-1"))
    require(0 <= font_index < len(fonts), "native Normal font index invalid")
    normal_font = fonts[font_index]
    name_node = normal_font.find(f"{{{SPREADSHEET_NS}}}name")
    size_node = normal_font.find(f"{{{SPREADSHEET_NS}}}sz")
    require(
        name_node is not None
        and name_node.get("val") == "Calibri"
        and size_node is not None
        and size_node.get("val") == "11"
        and normal_font.find(f"{{{SPREADSHEET_NS}}}b") is None
        and normal_font.find(f"{{{SPREADSHEET_NS}}}i") is None,
        "native physical Normal font differs from measured MDW",
    )
    contract = profile["presentation_contract"]
    rule = contract["layout"]["top_block_rules"]["country_rich_text"]
    require(
        rule.get("cell") == "C3"
        and rule.get("source_locator") == "Лист1!C3"
        and rule.get("space_advance_em") == 0.25,
        "country text geometry rule mismatch",
    )
    bindings = profile["reference_provenance"]
    require(
        rule.get("source_sha256s")
        == sorted(
            b["actual_sha256"]
            for b in bindings
            if b["role"] == "CLASSIC_FAMILY_EVIDENCE"
        ),
        "country text source binding drift",
    )
    font_sources = [
        b for b in bindings if b["role"] == "NATIVE_COUNTRY_BOLD_FONT_SOURCE"
    ]
    require(
        len(font_sources) == 1
        and font_sources[0]["actual_sha256"]
        == font_sources[0]["expected_sha256"]
        == rule.get("font_source_sha256"),
        "country font source binding drift",
    )
    sheet = ElementTree.fromstring(parts["xl/worksheets/sheet1.xml"])
    cell = sheet.find(f".//{{{SPREADSHEET_NS}}}c[@r='C3']")
    require(
        cell is not None and cell.get("t") == "inlineStr",
        "country canonical rich text missing",
    )
    assert cell is not None
    nodes = cell.findall(f"{{{SPREADSHEET_NS}}}is/{{{SPREADSHEET_NS}}}r")
    require(len(nodes) == 2 and len(rule["runs"]) == 2, "country run count drift")
    actual_text = []
    for node, expected in zip(nodes, rule["runs"], strict=True):
        props = node.find(f"{{{SPREADSHEET_NS}}}rPr")
        require(props is not None, "country run font missing")
        assert props is not None
        actual = {
            child.tag.removeprefix(f"{{{SPREADSHEET_NS}}}"): child.attrib
            for child in props
        }
        font = expected["font"]
        wanted = {
            "rFont": {"val": font["name"]},
            "sz": {"val": str(int(font["size"]))},
            "b": {"val": "1"},
            "family": {"val": str(font["family"])},
            "charset": {"val": str(font["charset"])},
            "color": {"indexed": str(font["color_indexed"])},
        }
        if actual.get("b") == {}:
            actual["b"] = {"val": "1"}
        require(
            len(props) == 6 and actual == wanted, "country canonical run font drift"
        )
        text_nodes = node.findall(f"{{{SPREADSHEET_NS}}}t")
        require(len(text_nodes) == 1, "country run text node count drift")
        text_node = text_nodes[0]
        actual_value = text_node.text or ""
        if actual_value and actual_value != actual_value.strip():
            require(
                text_node.get("{http://www.w3.org/XML/1998/namespace}space")
                == "preserve",
                "country whitespace requires xml:space preserve",
            )
        require(actual_value == expected["text"], "country run text drift")
        actual_text.append(actual_value)
    require(
        "".join(actual_text) == contract["fixed_blocks"]["company"]["C3"],
        "country plain text drift",
    )
    first, second = rule["runs"]
    require(
        bool(first["text"])
        and set(first["text"]) == {" "}
        and not second["text"].startswith(" ")
        and first["font"]
        == {
            "name": "Times New Roman",
            "size": 20,
            "bold": True,
            "family": 1,
            "charset": 204,
            "color_indexed": 8,
        }
        and second["font"]
        == {
            "name": "Times New Roman",
            "size": 16,
            "bold": True,
            "family": 1,
            "charset": 1,
            "color_indexed": 8,
        },
        "canonical country separation runs mismatch",
    )
    # C3-relative bounds remove irrelevant global grid translation (column A).
    columns = [
        n
        for n in sheet.findall(f"{{{SPREADSHEET_NS}}}cols/{{{SPREADSHEET_NS}}}col")
        if int(n.get("min", "0")) <= 2 <= int(n.get("max", "0"))
    ]
    require(len(columns) == 1, "country physical column B width missing")
    b_width = (
        floor((256 * float(columns[0].get("width", "0")) + floor(128 / 7)) / 256 * 7)
        * 0.75
    )
    drawing = ElementTree.fromstring(parts["xl/drawings/drawing1.xml"])
    anchor = drawing.find("xdr:twoCellAnchor", NS)
    require(anchor is not None, "country logo anchor missing")
    assert anchor is not None
    require(
        anchor.findtext("xdr:from/xdr:col", namespaces=NS) == "1"
        and anchor.findtext("xdr:to/xdr:col", namespaces=NS) == "2",
        "country logo relative columns mismatch",
    )
    left = -b_width + int(anchor.findtext("xdr:from/xdr:colOff", "0", NS)) / 12700
    ext = anchor.find("xdr:pic/xdr:spPr/a:xfrm/a:ext", NS)
    require(ext is not None, "country logo transform missing")
    assert ext is not None
    right = left + int(ext.attrib["cx"]) / 12700
    marker_right = int(anchor.findtext("xdr:to/xdr:colOff", "0", NS)) / 12700
    require(
        abs(right - marker_right) < 0.001,
        "country logo physical marker/transform mismatch",
    )
    start = len(first["text"]) * first["font"]["size"] * rule["space_advance_em"]
    require(start > right, "logo overlaps visible country text")
    return {
        "logo_left_relative_c3_pt": left,
        "logo_right_relative_c3_pt": right,
        "text_start_minimum_relative_c3_pt": start,
        "minimum_gap_pt": start - right,
    }


def validate_native_print(
    parts: Mapping[str, bytes], profile: Mapping[str, Any]
) -> float:
    """Raw package gate and independent reference-capacity recomputation."""
    contract = profile["presentation_contract"]
    rule = contract["layout"]["pagination"]
    require(
        set(rule)
        == {
            "mode",
            "print_area",
            "repeat_rows",
            "manual_breaks",
            "source_sha256s",
            "source_locator",
            "capacity",
        },
        "native pagination fields drift",
    )
    require(
        rule["mode"] == "NATIVE_EXCEL_AUTO"
        and rule["print_area"] is None
        and rule["repeat_rows"] is None
        and rule["manual_breaks"] == [],
        "native pagination policy drift",
    )
    family = [
        b
        for b in profile["reference_provenance"]
        if b["role"] == "CLASSIC_FAMILY_EVIDENCE"
    ]
    require(
        len(family) == 3
        and all(b["actual_sha256"] == b["expected_sha256"] for b in family)
        and rule["source_sha256s"] == sorted(b["actual_sha256"] for b in family),
        "native print source binding drift",
    )
    require(
        rule["source_locator"]
        == (
            "xl/worksheets/sheet1.xml:pageSetUpPr,pageSetup,pageMargins,rowBreaks,colBreaks;"
            "xl/workbook.xml:definedNames"
        ),
        "native print locator drift",
    )
    p = contract["print"]
    require(
        set(p)
        == {
            "paper_size",
            "orientation",
            "scale",
            "fit_to_height",
            "fit_to_width",
            "fit_to_page",
            "margins",
        },
        "native print contract fields drift",
    )
    require(
        p["paper_size"] == "9"
        and p["orientation"] == "portrait"
        and p["scale"] == 54
        and p["fit_to_page"] is True
        and p["fit_to_height"] == 0
        and p["fit_to_width"] is None,
        "native print contract drift",
    )
    capacity = (
        (
            297 * 72 / 25.4
            - (float(p["margins"]["top"]) + float(p["margins"]["bottom"])) * 72
        )
        * 100
        / p["scale"]
    )
    expected = {
        "method": "A4_PORTRAIT_MINUS_MARGINS_AT_STORED_SCALE",
        "paper_height_mm": 297,
        "paper_geometry_source": "OOXML paperSize=9;ISO216:A4=210x297mm",
        "usage": "REFERENCE_ONLY_NATIVE_FIT_TO_WIDTH_CONTROLS_PAGINATION",
    }
    require(
        set(rule["capacity"]) == set(expected) | {"nominal_unscaled_height_pt"}
        and all(rule["capacity"].get(k) == v for k, v in expected.items()),
        "native capacity method drift",
    )
    require(
        isfinite(capacity)
        and capacity > 0
        and abs(capacity - rule["capacity"]["nominal_unscaled_height_pt"]) < 1e-9,
        "native capacity value drift",
    )
    sheet = ElementTree.fromstring(parts["xl/worksheets/sheet1.xml"])
    setup = sheet.find(f"{{{SPREADSHEET_NS}}}pageSetup")
    props = sheet.find(f"{{{SPREADSHEET_NS}}}sheetPr/{{{SPREADSHEET_NS}}}pageSetUpPr")
    require(setup is not None and props is not None, "native print XML missing")
    assert setup is not None and props is not None
    require(
        setup.get("paperSize") == "9"
        and setup.get("orientation") == "portrait"
        and setup.get("scale") == "54"
        and setup.get("fitToHeight") == "0"
        and setup.get("fitToWidth") is None
        and props.get("fitToPage") in {"1", "true"},
        "native print XML drift",
    )
    require(
        all(
            sheet.find(f"{{{SPREADSHEET_NS}}}{tag}") is None
            for tag in ("rowBreaks", "colBreaks")
        ),
        "noncanonical print breaks XML",
    )
    book = ElementTree.fromstring(parts["xl/workbook.xml"])
    require(
        not any(
            n.get("name") in {"_xlnm.Print_Area", "_xlnm.Print_Titles"}
            for n in book.findall(
                f"{{{SPREADSHEET_NS}}}definedNames/{{{SPREADSHEET_NS}}}definedName"
            )
        ),
        "noncanonical print names XML",
    )
    return float(capacity)


def validate_or_raise(
    workbook_path: Path,
    profile: Mapping[str, Any],
    profile_sha256: str,
    document: Mapping[str, Any],
    document_sha256: str,
    *,
    allow_test_profile: bool = False,
) -> None:
    path = workbook_path.resolve(strict=True)
    require(path.suffix.casefold() == ".xlsx", "candidate suffix is not .xlsx")
    contract = validate_governance(
        profile,
        profile_sha256,
        document,
        document_sha256,
        allow_test_profile=allow_test_profile,
    )
    validate_workbook(path, contract, document)
    validate_package(path, contract, profile, profile_sha256, document_sha256)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.resolve(strict=True).read_bytes()
    require(sha256_bytes(raw) == expected_sha256, f"input SHA mismatch: {path}")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path}") from exc
    require(isinstance(value, Mapping), f"JSON root is not an object: {path}")
    return dict(value)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--document-sha256", required=True)
    parser.add_argument(
        "--test-only-allow-unapproved-profile",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        profile = load_json(cast(Path, args.profile), cast(str, args.profile_sha256))
        document = load_json(cast(Path, args.document), cast(str, args.document_sha256))
        validate_or_raise(
            cast(Path, args.workbook),
            profile,
            cast(str, args.profile_sha256),
            document,
            cast(str, args.document_sha256),
            allow_test_profile=bool(args.test_only_allow_unapproved_profile),
        )
    except (OSError, ValidationError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_VALIDATION=PASS_CANDIDATE_ONLY")
    print("CLIENT_SEND=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
