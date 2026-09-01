from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import (  # type: ignore[import-untyped]
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)

ROOT = Path(__file__).resolve().parents[1]
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)
PLACEMENT = {
    "anchor_type": "ONE_CELL",
    "from": {"column": 0, "column_offset": 76200, "row": 1, "row_offset": 66675},
    "extent": {"cx": 781050, "cy": 428625},
}
RUNTIME_MERGES = [
    "C2:F2",
    "G2:I2",
    "C3:F3",
    "G3:I3",
    "B4:F4",
    "G4:I4",
    "B5:F5",
    "G5:I5",
    "B6:F6",
    "G6:I6",
    "B9:F9",
    "G9:I9",
    "B10:F10",
    "G10:I10",
    "B11:F11",
    "G11:I11",
    "B12:F12",
    "G12:I12",
    "B13:F13",
    "G13:I13",
    "C22:I22",
    "C24:I24",
    "C25:I25",
    "C26:I26",
    "C27:I27",
    "C28:I28",
    "B30:E30",
    "F30:I30",
    "B31:E31",
    "F31:I31",
    "B32:I32",
]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(cell: Any, *, bold: bool = False, red: bool = False) -> None:
    cell.font = Font(
        name="Times New Roman",
        size=11,
        bold=bold,
        color="FFFF0000" if red else "FF000000",
    )
    cell.fill = PatternFill(fill_type=None)
    cell.border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    cell.number_format = "General"


def base_page(sheet: Any) -> None:
    sheet.page_setup.paperSize = "9"
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.scale = 54
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def write_reference(
    path: Path,
    *,
    case_marker: str,
    first_item_row: int = 16,
    classic: bool = True,
    renderer: ModuleType | None = None,
) -> str:
    renderer = renderer or load_script("render_dinva_classic_quote_invoice")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Лист1"
    sheet["C2"] = "ТОО «ДиН ВА-КЭС»" if classic else "Другая компания"
    sheet["G9"] = "ВНИМАНИЕ!"
    apply(sheet["C2"], bold=True)
    apply(sheet["G9"], bold=True, red=True)
    headers = {
        "B": "№ п/п",
        "C": "Наименование",
        "D": "Ед.",
        "E": "Кол-во",
        "F": f"Приборы {case_marker}",
        "G": f"Шкаф {case_marker}",
        "H": "Цена",
        "I": "Сумма",
    }
    for column, value in headers.items():
        sheet[f"{column}15"] = value
        apply(sheet[f"{column}15"], bold=True)
    row = first_item_row
    values: dict[str, Any] = {
        f"B{row}": 1,
        f"C{row}": f"Case-only {case_marker}",
        f"D{row}": "шт.",
        f"E{row}": 1,
        f"F{row}": f"Composition {case_marker}",
        f"G{row}": f"Enclosure {case_marker}",
        f"H{row}": 100,
        f"I{row}": f"=E{row}*H{row}",
    }
    for coordinate, value in values.items():
        sheet[coordinate] = value
        apply(sheet[coordinate])
    base_page(sheet)
    workbook.save(path)
    workbook.close()
    renderer.inject_governed_parts(path, TINY_PNG, PLACEMENT, {"fixture": case_marker})
    return sha(path)


def write_runtime_template(
    path: Path,
    *,
    renderer: ModuleType | None = None,
    width_b: float = 10.0,
    logo: bytes = TINY_PNG,
) -> str:
    renderer = renderer or load_script("render_dinva_classic_quote_invoice")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Счёт-КП шаблон"
    company = {
        "C2": "ТОО «ДиН ВА-КЭС»",
        "C3": "Республика Казахстан",
        "B4": "г. Астана",
        "B5": "Тел: +7",
        "B6": "info@dinva.kz",
        "G2": "БИН 000",
        "G3": "Банк",
        "G4": "IBAN KZ00",
        "G5": "BIK TEST",
        "G6": "КБЕ: 17",
    }
    for coordinate, value in company.items():
        sheet[coordinate] = value
        apply(sheet[coordinate], bold=coordinate == "C2")
    metadata = {
        "B9": "Черновик счёта-КП",
        "G9": "ВНИМАНИЕ!",
        "B10": "Плательщик",
        "G10": "Не отправлять",
        "B11": "Объект",
        "G11": "Проверить",
        "B12": "Основание",
        "G12": "Не запускать",
        "B13": "Статус",
        "G13": "Внутренний черновик",
    }
    for coordinate, value in metadata.items():
        sheet[coordinate] = value
        apply(sheet[coordinate], bold=coordinate == "G9", red=coordinate == "G9")
    headers = {
        "B": "№\nп/п",
        "C": "Наименование",
        "D": "Ед.",
        "E": "Кол-\nво",
        "F": "Применяемые приборы и аппараты согласно схемы",
        "G": "Тип шкафа, габариты ВхШхГ, материал",
        "H": "Цена",
        "I": "Сумма",
    }
    for column, value in headers.items():
        sheet[f"{column}15"] = value
        apply(sheet[f"{column}15"], bold=True)
    sheet["C16"] = "Раздел / объект / позиция проекта: нужно уточнить"
    apply(sheet["C16"])
    for row in range(17, 20):
        for column in "BCDEFGHI":
            apply(sheet[f"{column}{row}"])
        sheet.row_dimensions[row].height = 24
    sheet["B17"] = 1
    sheet["D17"] = "шт."
    sheet["I17"] = '=IF(OR(E17="",H17=""),"",IFERROR(E17*H17,"нужно уточнить"))'
    sheet["H20"] = "ИТОГО"
    sheet["I20"] = '=IF(COUNT(I17:I19)=0,"нужно уточнить",SUM(I17:I19))'
    sheet["H21"] = "НДС"
    sheet["I21"] = 0
    sheet["C22"] = "Всего прописью: нужно уточнить"
    sheet["C24"] = "Счёт действителен: нужно уточнить"
    sheet["C25"] = "Условия оплаты и поставки: нужно уточнить"
    sheet["C26"] = "Предположительный срок изготовления: нужно уточнить"
    sheet["C27"] = "Спецификация и условия подлежат проверке"
    sheet["C28"] = "Документ внутренний. Клиенту не отправлять"
    sheet["B30"] = "Директор"
    sheet["F30"] = "Директор Тест"
    sheet["B31"] = "Исполнитель:"
    sheet["F31"] = "Исполнитель Тест"
    sheet["B32"] = "Дата проверки: ____ / ____ / 2026"
    for coordinate in ("H20", "I20"):
        apply(sheet[coordinate], bold=True)
    for coordinate in ("H21", "I21"):
        apply(sheet[coordinate])
    for row in (22, 24, 25, 26, 27, 28):
        apply(sheet[f"C{row}"])
    for coordinate in ("B30", "F30", "B31", "F31", "B32"):
        apply(sheet[coordinate], bold=True)
    for column, width in zip(
        "BCDEFGHI", (width_b, 28, 7, 13, 35, 24, 14, 15), strict=True
    ):
        sheet.column_dimensions[column].width = width
    for merged_range in RUNTIME_MERGES:
        sheet.merge_cells(merged_range)
    base_page(sheet)
    workbook.save(path)
    workbook.close()
    renderer.inject_governed_parts(path, logo, PLACEMENT, {"fixture": "runtime"})
    return sha(path)


@pytest.fixture
def modules() -> tuple[ModuleType, ModuleType]:
    return (
        load_script("extract_dinva_classic_presentation_profile"),
        load_script("render_dinva_classic_quote_invoice"),
    )


def synthetic_inputs(
    tmp_path: Path, extractor: ModuleType, renderer: ModuleType
) -> tuple[list[Any], list[Any]]:
    first = tmp_path / "463.xlsx"
    second = tmp_path / "519.xlsx"
    runtime = tmp_path / "tuned-v4.xlsx"
    first_sha = write_reference(first, case_marker="463", renderer=renderer)
    second_sha = write_reference(
        second, case_marker="519", first_item_row=17, renderer=renderer
    )
    runtime_sha = write_runtime_template(runtime, renderer=renderer)
    return (
        [
            extractor.ReferenceInput(first, first_sha),
            extractor.ReferenceInput(second, second_sha),
        ],
        [extractor.ReferenceInput(runtime, runtime_sha)],
    )


def test_extraction_uses_certified_runtime_geometry_and_is_draft(
    tmp_path: Path, modules: tuple[ModuleType, ModuleType]
) -> None:
    extractor, renderer = modules
    project_root = tmp_path / "synthetic-repo"
    project_root.mkdir()
    extractor.__dict__["PROJECT_ROOT"] = project_root
    family, runtime = synthetic_inputs(tmp_path, extractor, renderer)
    left = extractor.extract_profile(family, runtime)
    right = extractor.extract_profile(list(reversed(family)), runtime)
    assert left == right
    layout = left["presentation_contract"]["layout"]
    assert layout["table_header_row"] == 15
    assert layout["first_item_row"] == 17
    assert layout["family_evidence_first_item_rows"] == [16, 17]
    assert layout["merged_cells"]["ranges"] == sorted(RUNTIME_MERGES)
    assert left["artifact_status"] == "DRAFT_PROFILE_CANDIDATE"
    assert left["approval_provenance"]["status"] == "DRAFT_UNAPPROVED"
    encoded = json.dumps(left, ensure_ascii=False)
    assert "Case-only 463" not in encoded
    assert "Case-only 519" not in encoded


def test_extractor_rejects_sha_nonclassic_and_runtime_geometry_conflict(
    tmp_path: Path, modules: tuple[ModuleType, ModuleType]
) -> None:
    extractor, renderer = modules
    project_root = tmp_path / "synthetic-repo"
    project_root.mkdir()
    extractor.__dict__["PROJECT_ROOT"] = project_root
    family, runtime = synthetic_inputs(tmp_path, extractor, renderer)
    with pytest.raises(extractor.ProfileExtractionError, match="SHA-256 mismatch"):
        extractor.extract_profile(
            [extractor.ReferenceInput(family[0].path, "0" * 64), family[1]], runtime
        )
    nonclassic = tmp_path / "637.xlsx"
    nonclassic_sha = write_reference(
        nonclassic, case_marker="637", classic=False, renderer=renderer
    )
    with pytest.raises(
        extractor.ProfileExtractionError, match="unsupported/non-classic"
    ):
        extractor.extract_profile(
            [family[0], extractor.ReferenceInput(nonclassic, nonclassic_sha)], runtime
        )
    conflicting = tmp_path / "conflicting-runtime.xlsx"
    conflicting_sha = write_runtime_template(
        conflicting, renderer=renderer, width_b=11.0
    )
    runtime_copy = tmp_path / "matching-runtime-copy.xlsx"
    runtime_copy.write_bytes(runtime[0].path.read_bytes())
    matching_runtime = runtime + [
        extractor.ReferenceInput(runtime_copy, sha(runtime_copy))
    ]
    assert extractor.extract_profile(family, matching_runtime)
    with pytest.raises(extractor.ProfileExtractionError, match="lacks consensus"):
        extractor.extract_profile(
            family,
            runtime + [extractor.ReferenceInput(conflicting, conflicting_sha)],
        )


def test_extractor_rejects_runtime_logo_not_bound_to_family_consensus(
    tmp_path: Path, modules: tuple[ModuleType, ModuleType]
) -> None:
    extractor, renderer = modules
    project_root = tmp_path / "synthetic-repo"
    project_root.mkdir()
    extractor.__dict__["PROJECT_ROOT"] = project_root
    family, runtime = synthetic_inputs(tmp_path, extractor, renderer)
    differing = tmp_path / "different-brand-runtime.xlsx"
    differing_sha = write_runtime_template(
        differing,
        renderer=renderer,
        logo=TINY_PNG + b"\x00",
    )
    with pytest.raises(
        extractor.ProfileExtractionError,
        match="runtime template logo differs from classic family logo evidence",
    ):
        extractor.extract_profile(
            family,
            runtime + [extractor.ReferenceInput(differing, differing_sha)],
        )


def test_profile_publication_is_no_overwrite_and_outside_git(
    tmp_path: Path, modules: tuple[ModuleType, ModuleType]
) -> None:
    extractor, _ = modules
    project_root = tmp_path / "synthetic-repo"
    project_root.mkdir()
    extractor.__dict__["PROJECT_ROOT"] = project_root
    output = tmp_path / "profile.json"
    assert extractor.publish_profile({"draft": True}, output) == output
    with pytest.raises(extractor.ProfileExtractionError, match="already exists"):
        extractor.publish_profile({"draft": True}, output)
    with pytest.raises(extractor.ProfileExtractionError, match="outside Git"):
        extractor.publish_profile({"draft": True}, project_root / "profile.json")
