"""Regression coverage for rotated CAD specification tables."""

# ruff: noqa: E402

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import governed_rotated_extraction as extraction  # type: ignore[import-not-found]


def test_rotated_page_coordinates_use_page_and_text_transforms() -> None:
    coordinates = extraction.page_space_coordinates(
        [0, -1, 1, 0, 6481, 9289],
        [0.12, 0, 0, 0.12, 0, 0],
        rotation=270,
        width=842,
        height=1191,
    )

    assert coordinates == (76.32, 777.72)


def test_rotated_specification_preserves_requested_and_excluded_rows() -> None:
    block = extraction.PdfBlock
    rows = [
        block("Позиция", 80, 778, 1),
        block("Наименование и техническая характеристика", 213, 778, 2),
        block("Тип. марка. обозначение", 528, 778, 3),
        block("Ед. измерения", 886, 778, 4),
        block("Количество", 964, 778, 5),
        block("ВРУ", 80, 697, 6),
        block("Вводно-распределительное устройство без учёта", 127, 697, 7),
        block("ВРУ1-13-20 УХЛ4", 498, 697, 8),
        block("компл.", 899, 697, 9),
        block("1", 965, 697, 10),
        block("Счетчик STAR 301/1 R2-5(60)Э", 127, 674, 11),
        block("шт.", 899, 674, 12),
        block("2", 965, 674, 13),
        block("Вводно-распределительное устройство", 127, 652, 14),
        block("ВРУ-1-45-00", 498, 652, 15),
        block("компл.", 899, 652, 16),
        block("2", 965, 652, 17),
        block("АВР", 80, 629, 18),
        block("Контакторная схема 2-1, приоритет первого ввода 63А", 127, 629, 19),
        block("компл.", 899, 629, 20),
        block("1", 965, 629, 21),
        block("ЩР", 80, 607, 22),
        block("Другой проектный щит", 127, 607, 23),
        block("шт.", 899, 607, 24),
        block("1", 965, 607, 25),
    ]

    result = extraction.extract_requested_specification_page(
        "synthetic.pdf",
        2,
        rows,
        (("ВРУ1-13-20 УХЛ4", 1), ("ВРУ-1-45-00", 2), ("АВР", 1)),
        (("STAR 301/1 R2-5(60)Э", 2),),
    )

    assert result.gated
    assert [(board.designation, board.quantity) for board in result.boards] == [
        ("ВРУ1-13-20 УХЛ4", 1),
        ("ВРУ-1-45-00", 2),
        ("АВР", 1),
    ]
    assert [row["classification"] for row in result.rows] == [
        "requested_supply",
        "excluded_component",
        "requested_supply",
        "requested_supply",
        "project_context",
    ]


def test_rotated_specification_rejects_missing_or_ambiguous_scope() -> None:
    block = extraction.PdfBlock
    headers = [
        block("Позиция", 80, 778, 1),
        block("Наименование и техническая характеристика", 213, 778, 2),
        block("Тип. марка. обозначение", 528, 778, 3),
        block("Ед. измерения", 886, 778, 4),
        block("Количество", 964, 778, 5),
    ]
    meter_rows = [
        block("STAR 301/1 variant A", 127, 674, 6),
        block("шт.", 899, 674, 7),
        block("2", 965, 674, 8),
        block("STAR 301/1 variant B", 127, 652, 9),
        block("шт.", 899, 652, 10),
        block("2", 965, 652, 11),
    ]

    result = extraction.extract_requested_specification_page(
        "synthetic.pdf",
        2,
        headers + meter_rows,
        (("VRU-1", 1),),
        (("STAR 301/1", 2),),
    )

    assert not result.gated
    assert not result.boards
    assert any("exclusion mismatch" in flag for flag in result.diagnostics)
    assert any(
        "requested supply is not fully matched" in flag for flag in result.diagnostics
    )
