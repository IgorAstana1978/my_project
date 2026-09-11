from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from zipfile import ZipFile

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical_file(path: Path, value: object) -> str:
    raw = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def refresh_document_fingerprint(document: dict[str, Any]) -> None:
    governed = {
        key: value
        for key, value in document.items()
        if key not in {"approval_provenance", "document_fingerprint"}
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            governed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    document["document_fingerprint"] = fingerprint
    document["approval_provenance"]["approved_document_fingerprint"] = fingerprint


def approved_document() -> dict[str, Any]:
    composition = "QF1 — автомат 16 А; KM1 — контактор 25 А\nБез сокращений"
    document: dict[str, Any] = {
        "schema_version": "dinva_quote_invoice_document.v0.2",
        "document_family": "DINVA_CLASSIC_QUOTE_INVOICE_V0_1",
        "document_type": "QUOTE_INVOICE",
        "document_id": "SYNTHETIC-001",
        "document_number": "TEST-001",
        "document_date": "2026-09-01",
        "currency": "KZT",
        "payer": "Synthetic Customer",
        "object_name": "Synthetic Object",
        "basis": "2024/086",
        "apparatus_heading": "Применяемые приборы и аппараты согласно схемы",
        "sections": [{"label": "Секция 9", "first_position": 1, "last_position": 1}],
        "items": [
            {
                "position": 1,
                "name": "Шкаф управления",
                "unit": "шт.",
                "quantity": 2,
                "detailed_technical_composition": composition,
                "apparatus": {
                    "text": "QF1 — автомат 16 А",
                    "source_role": "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
                    "source_sha256": "1" * 64,
                    "source_locator": "Synthetic!F17",
                },
                "enclosure": "IP54, 600×400×250, металл",
                "approved_unit_price_kzt": 100000,
                "approved_line_total_kzt": 200000,
                "approval_reference": {
                    "pricing": "SYNTHETIC-PRICE-APPROVAL-1",
                    "technical": "Synthetic!F17",
                    "enclosure": None,
                },
            }
        ],
        "approved_grand_total_kzt": 200000,
        "vat": {
            "rate_percent": 12,
            "included": True,
            "approved_amount_kzt": 21429,
            "approved_text": "В том числе НДС 12%",
        },
        "amount_words": {
            "amount_kzt": 200000,
            "approved_text": "Двести тысяч тенге 00 тиын",
        },
        "terms": {
            "payment": None,
            "delivery": "Самовывоз",
            "manufacturing_lead_time": "20 рабочих дней",
            "manufacturing_lead_time_provenance": {
                "source_order": 1,
                "source_text": "Срок действия: 10 календарных дней",
                "normalized_text": "20 рабочих дней",
                "source_sha256": "1" * 64,
                "source_locator": "Synthetic!C21",
                "normalization_rule": "SYNTHETIC_APPROVED_NORMALIZATION",
                "approval_reference": "SYNTHETIC-LEAD-TIME-APPROVAL",
            },
            "validity": "10 календарных дней",
            "commercial_lines": [
                {
                    "source_order": 1,
                    "text": "Срок действия: 10 календарных дней",
                    "source_sha256": "1" * 64,
                    "source_locator": "Synthetic!C21",
                },
                {
                    "source_order": 2,
                    "text": "Условия оплаты: 50% предоплата.",
                    "source_sha256": "1" * 64,
                    "source_locator": "Synthetic!C22",
                },
                {
                    "source_order": 3,
                    "text": "Условия поставки: Самовывоз.",
                    "source_sha256": "1" * 64,
                    "source_locator": "Synthetic!C23",
                },
            ],
        },
        "signatures": {
            "director_title": "Директор",
            "director_name": "Тестовый Директор",
            "executor_label": "Исполнитель:",
            "executor_title": "Исполнитель",
            "executor_name": "Тестовый Исполнитель",
            "executor_full_text": "Исполнитель Тестовый Исполнитель",
        },
        "approval_provenance": {
            "status": "APPROVED",
            "authority": "SYNTHETIC_TEST_AUTHORITY",
            "approval_id": "SYNTHETIC-ONLY",
            "approved_at": "2026-09-01T00:00:00Z",
            "approval_scope": "INVOICE519_DOCUMENT_MODEL_ONLY",
            "approved_document_fingerprint": "",
            "source_bindings": [
                {"role": "synthetic", "path": "Synthetic!A1", "sha256": "1" * 64}
            ],
            "source_sha256s": ["1" * 64],
            "rendering_authorized": True,
            "client_send_authorized": False,
        },
    }
    refresh_document_fingerprint(document)
    return document


@pytest.mark.parametrize("payment", ["после внесения предоплаты", "100% предоплата"])
def test_invoice519_rejects_unsupported_payment(payment: str) -> None:
    document = approved_document()
    document["terms"]["payment"] = payment
    refresh_document_fingerprint(document)
    renderer = load_file(
        "payment_renderer", ROOT / "scripts" / "render_dinva_classic_quote_invoice.py"
    )
    validator = load_file(
        "payment_validator",
        ROOT / "scripts" / "validate_dinva_classic_quote_invoice.py",
    )
    with pytest.raises(
        renderer.RendererError, match="payment lacks governed provenance"
    ):
        renderer.validate_document(document, allow_test_profile=True)
    with pytest.raises(
        validator.ValidationError, match="payment lacks governed provenance"
    ):
        validator.validate_document_contract(document, allow_test_profile=True)


def style(
    size: float,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: str | None = None,
    horizontal: str | None = None,
    vertical: str | None = None,
    wrap: bool = False,
    number_format: str = "General",
    left: str | None = None,
    right: str | None = None,
    top: str | None = None,
    bottom: str | None = None,
    fill: str | None = None,
    color: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "font": {
            "name": "Times New Roman",
            "size": size,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "color": color,
        },
        "fill": {
            "type": "solid" if fill else None,
            "foreground": (
                {"type": "rgb", "value": fill, "tint": 0.0}
                if fill
                else {"type": "rgb", "value": "00000000", "tint": 0.0}
            ),
        },
        "border": {"left": left, "right": right, "top": top, "bottom": bottom},
        "alignment": {
            "horizontal": horizontal,
            "vertical": vertical,
            "wrap_text": wrap,
            "shrink_to_fit": False,
        },
        "number_format": number_format,
    }


def dynamic_profile() -> dict[str, Any]:
    logo = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    body: dict[str, Any] = {
        "vertical": "center",
        "wrap": True,
        "top": "thin",
        "bottom": "thin",
    }
    styles = {
        "company_title": style(20, bold=True, horizontal="left", top="medium"),
        "country": style(16, bold=True, horizontal="left"),
        "company_info": style(14, bold=True, horizontal="left"),
        "bank_title": style(
            20, bold=True, horizontal="right", right="medium", top="medium"
        ),
        "bank_info": style(14, bold=True, horizontal="right", right="medium"),
        "document_title": style(20, bold=True, top="medium"),
        "payer": style(20, bold=True, horizontal="left"),
        "warning": style(
            14, color={"type": "rgb", "value": "FFFF0000", "tint": 0.0}, top="medium"
        ),
        "lead_time": style(
            14,
            bold=True,
            underline="single",
            color={"type": "rgb", "value": "FFFF0000", "tint": 0.0},
        ),
        "object": style(14, bold=True, horizontal="left", vertical="center", wrap=True),
        "table_header": style(
            16,
            bold=True,
            horizontal="center",
            vertical="center",
            wrap=True,
            left="thin",
            right="thin",
            top="medium",
            bottom="medium",
            fill="FFBFBFBF",
        ),
        "table_header_left": style(
            16,
            bold=True,
            horizontal="center",
            vertical="center",
            wrap=True,
            left="medium",
            right="thin",
            top="medium",
            bottom="medium",
            fill="FFBFBFBF",
        ),
        "table_header_right": style(
            16,
            bold=True,
            horizontal="center",
            vertical="center",
            wrap=True,
            left="thin",
            right="medium",
            top="medium",
            bottom="medium",
            fill="FFBFBFBF",
        ),
        "section": style(
            14,
            bold=True,
            horizontal="left",
            vertical="center",
            left="thin",
            right="thin",
            top="medium",
            bottom="medium",
            fill="FFD9D9D9",
        ),
        "position": style(14, horizontal="center", left="medium", right="thin", **body),
        "item_name": style(14, horizontal="left", left="thin", right="thin", **body),
        "unit": style(14, horizontal="center", left="thin", right="thin", **body),
        "quantity": style(14, horizontal="center", left="thin", right="thin", **body),
        "technical_composition": style(
            14,
            horizontal="left",
            vertical="top",
            wrap=True,
            left="thin",
            right="thin",
            top="thin",
            bottom="thin",
        ),
        "enclosure": style(14, horizontal="center", left="thin", right="thin", **body),
        "money": style(
            14,
            horizontal="center",
            number_format="#,##0",
            left="thin",
            right="thin",
            **body,
        ),
        "line_total": style(
            14,
            horizontal="center",
            number_format="#,##0",
            left="thin",
            right="medium",
            **body,
        ),
        "total_label": style(16, bold=True),
        "total_amount": style(14, bold=True, number_format="#,##0_);(#,##0)"),
        "amount_words": style(16, bold=True, horizontal="left"),
        "commercial_line": style(16, bold=True, horizontal="left"),
        "director": style(16, horizontal="right"),
        "director_name": style(16, horizontal="center", vertical="center"),
        "executor": style(8, horizontal="left"),
    }
    contract = {
        "contract_version": "dinva_classic_presentation_contract.v0.2",
        "workbook": {
            "active_sheet_index": 0,
            "extra_sheets_allowed": False,
            "sheets": [{"name": "Счёт-КП", "role": "PRIMARY_DOCUMENT"}],
        },
        "fixed_blocks": {
            "company": {
                "C2": "                     ТОО «ДиН ВА-КЭС»",
                "C3": "                     Республика Казахстан",
                "B4": "г.Астана, ул. Шара Жиенкулова, зд. 11/4",
                "B5": "Тел: +7-777-142-7219",
                "B6": "info@dinva.kz, www.dinva.kz",
                "I2": "БИН 190 940 021 963",
                "I3": "АО «Народный Банк Казахстан»",
                "I4": "IBAN (ИИК) KZ66601A871006276891",
                "I5": "BIK (БИК) HSBKKZKX",
                "I6": "КБЕ: 17, КБК: 710",
            },
            "warning": {"G9": "ВНИМАНИЕ!"},
            "table_headers": {
                "B": "№\nп/п",
                "C": "Наименование",
                "D": "Ед.",
                "E": "Кол-\nво",
                "F": "Применяемые приборы и аппараты согласно схемы",
                "G": "Тип шкафа, габариты ВхШхГ, материал",
                "H": "Цена",
                "I": "Сумма",
            },
            "total_label": "ИТОГО",
        },
        "layout": {
            "table_header_row": 15,
            "first_content_row": 16,
            "table_columns": {
                "position": "B",
                "name": "C",
                "unit": "D",
                "quantity": "E",
                "technical_composition": "F",
                "enclosure": "G",
                "unit_price": "H",
                "line_total": "I",
            },
            "column_width_rules": {
                "B": {
                    "minimum": 5.42578125,
                    "preferred": 5.42578125,
                    "maximum": 5.42578125,
                    "adaptive": False,
                    "preferred_chars": 1,
                    "maximum_chars": 1,
                },
                "C": {
                    "minimum": 36.0,
                    "preferred": 42.0,
                    "maximum": 44.0,
                    "adaptive": True,
                    "preferred_chars": 24,
                    "maximum_chars": 60,
                },
                "D": {
                    "minimum": 8.140625,
                    "preferred": 8.140625,
                    "maximum": 8.140625,
                    "adaptive": False,
                    "preferred_chars": 1,
                    "maximum_chars": 1,
                },
                "E": {
                    "minimum": 12.5703125,
                    "preferred": 12.5703125,
                    "maximum": 12.5703125,
                    "adaptive": False,
                    "preferred_chars": 1,
                    "maximum_chars": 1,
                },
                "F": {
                    "minimum": 48.0,
                    "preferred": 56.140625,
                    "maximum": 58.0,
                    "adaptive": True,
                    "preferred_chars": 90,
                    "maximum_chars": 260,
                },
                "G": {
                    "minimum": 18.0,
                    "preferred": 19.85546875,
                    "maximum": 22.0,
                    "adaptive": True,
                    "preferred_chars": 26,
                    "maximum_chars": 55,
                },
                "H": {
                    "minimum": 14.42578125,
                    "preferred": 14.42578125,
                    "maximum": 14.42578125,
                    "adaptive": False,
                    "preferred_chars": 1,
                    "maximum_chars": 1,
                },
                "I": {
                    "minimum": 15.5703125,
                    "preferred": 18.0,
                    "maximum": 22.140625,
                    "adaptive": True,
                    "preferred_chars": 7,
                    "maximum_chars": 12,
                },
            },
            "maximum_printable_width": 180.75,
            "row_height_rule": {
                "minimum_height": 37.5,
                "line_height_points": 18.0,
                "vertical_padding_points": 3.0,
                "maximum_height": 408.0,
                "header_minimum_height": 82.0,
                "header_line_height_points": 20.0,
                "section_height": 19.5,
                "total_height": 20.25,
                "amount_height": 20.25,
                "commercial_height": 20.25,
                "signature_height": 20.25,
            },
            "bottom_layout": {"amount_words_offset": 2, "signature_spacer_rows": 1},
            "pagination": {
                "first_page_body_height_points": 900.0,
                "following_page_body_height_points": 1100.0,
                "repeat_rows": "15:15",
                "keep_section_with_first_item": True,
            },
            "gridlines_visible": True,
            "merged_cells": {"mode": "NONE", "ranges": []},
            "top_row_heights": {
                "2": 25.5,
                "3": 25.5,
                "9": 25.5,
                "10": 25.5,
                "13": 63.75,
            },
        },
        "styles": styles,
        "formulas": {
            "calc_chain_policy": "OPTIONAL_BUT_MUST_BE_CONSISTENT",
            "line_total_template": (
                '=IF(OR(E{row}="",H{row}=""),"",'
                'IFERROR(E{row}*H{row},"нужно уточнить"))'
            ),
            "grand_total_template": (
                '=IF(COUNT(I{start}:I{end})=0,"нужно уточнить",' "SUM(I{start}:I{end}))"
            ),
        },
        "assets": [
            {
                "asset_id": "DINVA_CLASSIC_LOGO_V0_1",
                "media_type": "image/png",
                "sha256": hashlib.sha256(logo).hexdigest(),
                "data_base64": base64.b64encode(logo).decode(),
                "source_reference_sha256s": ["1" * 64, "2" * 64, "3" * 64],
                "placement": {
                    "anchor_type": "TWO_CELL",
                    "relative_to": "COMPANY_HEADER_BLOCK",
                    "base_cell": "B2",
                    "from": {
                        "column_delta": 0,
                        "column_offset": 57150,
                        "row_delta": 0,
                        "row_offset": 76200,
                    },
                    "to": {
                        "column_delta": 1,
                        "column_offset": 1200150,
                        "row_delta": 1,
                        "row_offset": 266700,
                    },
                    "protected_first_row": 4,
                },
            }
        ],
        "package": {
            "external_relationships_allowed": False,
            "forbidden_part_prefixes": [
                "xl/externalLinks/",
                "xl/activeX/",
                "xl/embeddings/",
                "xl/connections",
                "customXml/",
            ],
            "forbidden_part_suffixes": ["vbaProject.bin", ".vml"],
        },
        "print": {
            "fit_to_height": 0,
            "fit_to_width": 0,
            "fit_to_page": False,
            "margins": {
                "bottom": 0.7480314960629921,
                "footer": 0.31496062992125984,
                "header": 0.31496062992125984,
                "left": 0.4330708661417323,
                "right": 0.2362204724409449,
                "top": 0.35433070866141736,
            },
            "orientation": "portrait",
            "paper_size": "9",
            "print_area_columns": "B:I",
            "scale": 54,
        },
        "optional_elements": ["object", "basis", "validity"],
        "variable_elements": [
            "item count/order",
            "sections",
            "content",
            "commercial lines",
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return {
        "schema_version": "dinva_classic_presentation_profile.v0.2",
        "profile_id": "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_2",
        "document_family": "DINVA_CLASSIC_QUOTE_INVOICE_V0_1",
        "artifact_status": "DRAFT_PROFILE_CANDIDATE",
        "reference_provenance": [],
        "presentation_contract": contract,
        "presentation_contract_fingerprint": fingerprint,
        "approval_provenance": {
            "status": "DRAFT_UNAPPROVED",
            "authority": None,
            "approval_id": None,
            "approved_at": None,
            "approved_contract_fingerprint": None,
        },
    }


def make_case(tmp_path: Path) -> dict[str, Any]:
    renderer = load_file(
        "dinva_renderer_for_tests",
        ROOT / "scripts" / "render_dinva_classic_quote_invoice.py",
    )
    synthetic_root = tmp_path / "synthetic-repo"
    synthetic_root.mkdir(exist_ok=True)
    renderer.__dict__["PROJECT_ROOT"] = synthetic_root
    profile = dynamic_profile()
    document = approved_document()
    profile_path = tmp_path / "profile.json"
    document_path = tmp_path / "document.json"
    return {
        "renderer": renderer,
        "profile": profile,
        "document": document,
        "profile_path": profile_path,
        "document_path": document_path,
        "profile_sha": canonical_file(profile_path, profile),
        "document_sha": canonical_file(document_path, document),
    }


def render_case(case: dict[str, Any], output: Path) -> Path:
    renderer = case["renderer"]
    return cast(
        Path,
        renderer.render(
            profile_path=case["profile_path"],
            expected_profile_sha256=case["profile_sha"],
            document_path=case["document_path"],
            expected_document_sha256=case["document_sha"],
            output=output,
            allow_test_profile=True,
        ),
    )


def reshape_case(
    case: dict[str, Any],
    section_sizes: list[int],
    *,
    long_text: bool = False,
    commercial_line_count: int = 3,
) -> None:
    document = case["document"]
    template = document["items"][0]
    items = []
    total_items = sum(section_sizes)
    for position in range(1, total_items + 1):
        item = copy.deepcopy(template)
        item.update(
            position=position,
            name=("Очень длинное наименование шкафа " * 3 if long_text else "Шкаф")
            + f" {position}",
            quantity=1,
            approved_unit_price_kzt=1000,
            approved_line_total_kzt=1000,
            enclosure=(
                "Напольный 1700×1000×500 металл 1,2мм " * 4 if long_text else "КРН-24"
            ),
        )
        apparatus_text = f"QF{position} — автомат 16 А"
        composition = (
            (apparatus_text + "; контактор; реле; клеммы; шина; " * 12)
            if long_text
            else apparatus_text
        )
        item["detailed_technical_composition"] = composition
        item["apparatus"].update(
            text=apparatus_text, source_locator=f"Synthetic!F{position}"
        )
        items.append(item)
    sections = []
    first = 1
    for index, size in enumerate(section_sizes, start=1):
        sections.append(
            {
                "label": f"Секция {index}",
                "first_position": first,
                "last_position": first + size - 1,
            }
        )
        first += size
    document["items"] = items
    document["sections"] = sections
    document["approved_grand_total_kzt"] = total_items * 1000
    document["amount_words"] = {
        "amount_kzt": total_items * 1000,
        "approved_text": f"Synthetic total {total_items * 1000} тенге",
    }
    document["vat"].update(
        rate_percent=12,
        approved_amount_kzt=int(
            (Decimal(total_items * 1000) * Decimal(12) / Decimal(112)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        ),
    )
    document["terms"]["commercial_lines"] = [
        {
            "source_order": index,
            "text": f"Коммерческое условие {index}",
            "source_sha256": "1" * 64,
            "source_locator": f"Synthetic!C{index}",
        }
        for index in range(1, commercial_line_count + 1)
    ]
    document["approval_provenance"]["approval_scope"] = "SYNTHETIC_DYNAMIC_LAYOUT"
    lead_source = document["terms"]["commercial_lines"][0]
    document["terms"]["manufacturing_lead_time_provenance"].update(
        source_order=lead_source["source_order"],
        source_text=lead_source["text"],
        source_sha256=lead_source["source_sha256"],
        source_locator=lead_source["source_locator"],
    )
    refresh_document_fingerprint(document)
    case["document_sha"] = canonical_file(case["document_path"], document)


def test_clean_render_preserves_exact_business_content_and_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case = make_case(tmp_path)
    output = render_case(case, tmp_path / "output.xlsx")
    workbook = load_workbook(output, data_only=False)
    try:
        sheet = workbook["Счёт-КП"]
        item = case["document"]["items"][0]
        assert sheet["F17"].value == item["detailed_technical_composition"]
        assert sheet["B12"].value is None
        assert sheet["C9"].value == "Счёт-КП № TEST-001 от 1 сентября 2026 года"
        assert sheet["I17"].value == (
            '=IF(OR(E17="",H17=""),"",IFERROR(E17*H17,"нужно уточнить"))'
        )
        assert sheet["I18"].value == (
            '=IF(COUNT(I16:I17)=0,"нужно уточнить",SUM(I16:I17))'
        )
        assert not sheet.merged_cells.ranges
        assert sheet.sheet_view.showGridLines is True
        assert sheet["H17"].number_format == "#,##0"
        assert sheet["I17"].number_format == "#,##0"
        assert sheet["B13"].value is None
        assert sheet["G13"].value is None
        assert workbook.sheetnames == ["Счёт-КП"]
    finally:
        workbook.close()
    with ZipFile(output) as archive:
        names = set(archive.namelist())
        asset = case["profile"]["presentation_contract"]["assets"][0]
        assert (
            hashlib.sha256(archive.read("xl/media/image1.png")).hexdigest()
            == asset["sha256"]
        )
        assert b"twoCellAnchor" in archive.read("xl/drawings/drawing1.xml")
        content_types = archive.read("[Content_Types].xml")
        assert (
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"'
            in content_types
        )
        assert b"<ns0:Types" not in content_types
        assert "xl/calcChain.xml" not in names
        assert not any("externalLinks" in name for name in names)


def test_renderer_preserves_ordered_sections_inside_governed_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case = make_case(tmp_path)
    document = case["document"]
    second = json.loads(json.dumps(document["items"][0]))
    second.update(
        position=2,
        quantity=1,
        approved_unit_price_kzt=50000,
        approved_line_total_kzt=50000,
    )
    document["items"].append(second)
    document["sections"] = [
        {"label": "Секция 9", "first_position": 1, "last_position": 1},
        {"label": "Секция 10", "first_position": 2, "last_position": 2},
    ]
    document["approved_grand_total_kzt"] = 250000
    document["amount_words"] = {
        "amount_kzt": 250000,
        "approved_text": "Двести пятьдесят тысяч тенге 00 тиын",
    }
    document["vat"]["approved_amount_kzt"] = 26786
    refresh_document_fingerprint(document)
    case["document_sha"] = canonical_file(case["document_path"], document)
    output = render_case(case, tmp_path / "sectioned.xlsx")
    workbook = load_workbook(output, data_only=False)
    try:
        sheet = workbook["Счёт-КП"]
        assert sheet["C16"].value == "Секция 9"
        assert sheet["B17"].value == 1
        assert sheet["C18"].value == "Секция 10"
        assert sheet["B19"].value == 2
        assert sheet["C20"].value == "ИТОГО"
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("section_sizes", "expected_total_row"),
    [
        ([12], 29),
        ([10, 10, 10, 10], 60),
        ([15, 6, 17, 6, 14, 6, 16, 2, 6], 113),
        ([130], 147),
    ],
)
def test_dynamic_length_matrix_has_no_capacity_tail_and_paginates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section_sizes: list[int],
    expected_total_row: int,
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case = make_case(tmp_path)
    reshape_case(case, section_sizes)
    output = render_case(case, tmp_path / f"dynamic-{sum(section_sizes)}.xlsx")
    workbook = load_workbook(output, data_only=False)
    try:
        sheet = workbook["Счёт-КП"]
        assert sheet[f"C{expected_total_row}"].value == "ИТОГО"
        line_count = len(case["document"]["terms"]["commercial_lines"])
        expected_final = expected_total_row + line_count + 5
        assert sheet.max_row == expected_final
        assert str(sheet.print_area).endswith(f"$I${expected_final}")
        if sum(section_sizes) >= 40:
            assert sheet.row_breaks.brk
        break_ids = {int(value.id) for value in sheet.row_breaks.brk}
        section_rows = {
            row
            for row in range(16, expected_total_row)
            if sheet[f"B{row}"].value is None and sheet[f"C{row}"].value
        }
        assert not break_ids.intersection(section_rows)
    finally:
        workbook.close()


def test_adaptive_widths_heights_and_variable_commercial_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    short_root = tmp_path / "short"
    long_root = tmp_path / "long"
    short_root.mkdir()
    long_root.mkdir()
    short = make_case(short_root)
    reshape_case(short, [1], commercial_line_count=1)
    short_output = render_case(short, tmp_path / "short.xlsx")
    long = make_case(long_root)
    reshape_case(long, [2, 2], long_text=True, commercial_line_count=8)
    long_output = render_case(long, tmp_path / "long.xlsx")
    short_book = load_workbook(short_output, data_only=False)
    long_book = load_workbook(long_output, data_only=False)
    try:
        short_sheet = short_book["Счёт-КП"]
        long_sheet = long_book["Счёт-КП"]
        for column in "CFGI":
            rule = long["profile"]["presentation_contract"]["layout"][
                "column_width_rules"
            ][column]
            width = float(long_sheet.column_dimensions[column].width)
            assert rule["minimum"] <= width <= rule["maximum"]
        assert (
            long_sheet.column_dimensions["F"].width
            > short_sheet.column_dimensions["F"].width
        )
        assert (
            long_sheet.row_dimensions[17].height > short_sheet.row_dimensions[17].height
        )
        assert long_sheet["C32"].value == "Коммерческое условие 8"
        assert long_sheet.max_row == 35
    finally:
        short_book.close()
        long_book.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda case: case.update(profile_sha="0" * 64), "profile SHA-256 mismatch"),
        (
            lambda case: case["profile"].update(document_family="UNKNOWN"),
            "unsupported profile family",
        ),
        (
            lambda case: case["profile"].update(
                presentation_contract_fingerprint="0" * 64
            ),
            "fingerprint mismatch",
        ),
        (
            lambda case: case["document"].pop("payer"),
            "document fields mismatch",
        ),
        (
            lambda case: case["document"].update(basis=None),
            "Invoice519 basis mismatch",
        ),
        (
            lambda case: case["document"].update(basis="WRONG"),
            "Invoice519 basis mismatch",
        ),
    ],
)
def test_renderer_rejects_bad_bindings_and_malformed_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case = make_case(tmp_path)
    mutation(case)
    refresh_document_fingerprint(case["document"])
    if case["profile_sha"] != "0" * 64:
        case["profile_sha"] = canonical_file(case["profile_path"], case["profile"])
    case["document_sha"] = canonical_file(case["document_path"], case["document"])
    with pytest.raises(case["renderer"].RendererError, match=message):
        render_case(case, tmp_path / "bad.xlsx")


def test_renderer_requires_approved_profile_by_default(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    with pytest.raises(case["renderer"].RendererError, match="not immutable"):
        case["renderer"].render(
            profile_path=case["profile_path"],
            expected_profile_sha256=case["profile_sha"],
            document_path=case["document_path"],
            expected_document_sha256=case["document_sha"],
            output=tmp_path / "blocked.xlsx",
        )


def test_renderer_no_overwrite_outside_git_cleanup_and_toctou(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    case = make_case(tmp_path)
    output = tmp_path / "exists.xlsx"
    output.write_bytes(b"occupied")
    with pytest.raises(case["renderer"].RendererError, match="already exists"):
        render_case(case, output)
    case["renderer"].PROJECT_ROOT = tmp_path / "synthetic-repo"
    with pytest.raises(case["renderer"].RendererError, match="outside Git"):
        render_case(case, tmp_path / "synthetic-repo" / "inside.xlsx")
    case["renderer"].PROJECT_ROOT = tmp_path / "another-synthetic-repo"
    original = case["renderer"].render_clean_workbook

    def mutate_after_render(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        case["document_path"].write_text("{}", encoding="utf-8")

    monkeypatch.setattr(case["renderer"], "render_clean_workbook", mutate_after_render)
    final = tmp_path / "toctou.xlsx"
    with pytest.raises(case["renderer"].RendererError, match="changed during render"):
        render_case(case, final)
    assert not final.exists()
    assert not list(tmp_path.glob(".*.candidate.xlsx"))
