"""Exact successor binding and read-only price-ingestion contract tests."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

from scripts import price_baseline_contract as binding


def load_script(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / "scripts" / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


calculator = cast(
    Any, load_script("successor_calculator_test", "calc_quote_price_draft.py")
)
runner = cast(
    Any,
    load_script(
        "successor_runner_test", "run_checked_price_calculator_from_completed_draft.py"
    ),
)


def price_result(version: str, path: Path) -> Any:
    return calculator.PriceCalculationResult(
        price_workbook=path,
        input_csv=Path("unused.csv"),
        price_baseline_version=version,
    )


def price_names(path: Path) -> dict[str, set[int]]:
    """Bounded A/B scan; never traverse a formatted used-range."""
    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    found: dict[str, set[int]] = {}
    try:
        for sheet in workbook:
            for label, value in sheet.iter_rows(
                min_row=1, max_row=200, min_col=1, max_col=2, values_only=True
            ):
                if isinstance(label, str) and isinstance(value, int) and value > 0:
                    found.setdefault(label, set()).add(value)
    finally:
        workbook.close()
    return found


def test_exact_versions_paths_and_shas_fail_closed(monkeypatch: Any) -> None:
    assert (
        binding.require_price_baseline(
            binding.HISTORICAL.path, binding.HISTORICAL.version
        )
        == binding.HISTORICAL
    )
    assert (
        binding.require_price_baseline(
            binding.SUCCESSOR.path, binding.SUCCESSOR.version
        )
        == binding.SUCCESSOR
    )
    for path, version in (
        (binding.HISTORICAL.path, binding.SUCCESSOR.version),
        (binding.SUCCESSOR.path, binding.HISTORICAL.version),
        (binding.SUCCESSOR.path, "unknown"),
        (Path("other.xlsx"), binding.SUCCESSOR.version),
    ):
        with pytest.raises(ValueError):
            binding.require_price_baseline(path, version)
    monkeypatch.setitem(
        binding.BASELINES,
        binding.SUCCESSOR.version,
        replace(binding.SUCCESSOR, sha256="0" * 64),
    )
    with pytest.raises(ValueError, match="SHA-256"):
        binding.require_price_baseline(
            binding.SUCCESSOR.path, binding.SUCCESSOR.version
        )


def test_all_16_changed_names_are_classified_from_actual_ingestion() -> None:
    before = price_names(binding.HISTORICAL.path)
    after = price_names(binding.SUCCESSOR.path)
    assert before.keys() == after.keys()
    changed = {name for name in before if before[name] != after[name]}
    assert len(changed) == 16
    exact = {
        calculator.normalize_workbook_label(mapping.expected_label)
        for mapping in calculator.APPROVED_COMPONENT_PRICE_MAPPINGS
    }
    dynamic = {
        calculator.normalize_workbook_label(definition.workbook_label)
        for definition in calculator.COMPONENT_DEFINITIONS.values()
        if definition.workbook_label is not None
    }
    b_names = {
        name for name in changed if calculator.normalize_workbook_label(name) in exact
    }
    a_names = {
        name
        for name in changed
        if calculator.normalize_workbook_label(name) in dynamic and name not in b_names
    }
    c_names = changed - a_names - b_names
    assert a_names == {
        "ВА47 1 полюсный",
        "ВА47 2 полюсный",
        "ВА47 3 полюсный до 63А",
    }
    assert b_names == {
        "ВА55/57/59, АМ1  3 полюсные от 16 до 63А",
        "УЗО АД-32 1Р+N до 63А EKF",
    }
    assert c_names == {
        "ВА47 1 полюсный 10А",
        "ВА47 3 полюсный 10А",
        "ВА55/57/59 400А",
        "ВА55/57/59,  АМ1 от 80 до 100А",
        "Контактор до 250А",
        "Контактор до 400А",
        "Контактор до 630А",
        "ПН-2 100А",
        "ПН-2 250А",
        "ПН-2 400А",
        "Реле времени суточное ТЭ-15",
    }
    assert (len(a_names), len(b_names), len(c_names)) == (3, 2, 11)


def test_successor_exact_mappings_and_historical_values_are_disjoint() -> None:
    old = calculator.APPROVED_COMPONENT_PRICE_MAPPINGS
    new = calculator.SUCCESSOR_COMPONENT_PRICE_MAPPINGS
    assert len(old) == len(new)
    affected = [
        (historical, successor)
        for historical, successor in zip(old, new, strict=True)
        if historical != successor
    ]
    assert len(affected) == 5
    for historical, successor in affected:
        assert (
            calculator.resolve_component_mapping(
                historical.signature, historical.component_code, old
            )
            == historical
        )
        assert (
            calculator.resolve_component_mapping(
                successor.signature, successor.component_code, new
            )
            == successor
        )
    assert [
        (m.sheet_name, m.row, m.expected_material_price, m.expected_work_price)
        for m, _ in affected
    ] == [
        ("ЩР", 8, 13000, 1800),
        ("КРН", 5, 4100, 432),
        ("КРН", 5, 4100, 432),
        ("КРН", 5, 4100, 432),
        ("КРН", 5, 4100, 432),
    ]
    assert [
        (m.sheet_name, m.row, m.expected_material_price, m.expected_work_price)
        for _, m in affected
    ] == [
        ("ЩР", 8, 15000, 1800),
        ("КРН", 5, 4500, 432),
        ("КРН", 5, 4500, 432),
        ("КРН", 5, 4500, 432),
        ("КРН", 5, 4500, 432),
    ]
    assert runner.EXPECTED_PROFILE_INPUTS[1][1:] == (
        str(binding.HISTORICAL.path),
        binding.HISTORICAL.sha256,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def test_real_successor_dynamic_and_exact_prices_are_read_literal() -> None:
    binding.require_price_baseline(binding.SUCCESSOR.path, binding.SUCCESSOR.version)
    workbook = load_workbook(
        binding.SUCCESSOR.path, read_only=True, data_only=False, keep_links=False
    )
    result = price_result(binding.SUCCESSOR.version, binding.SUCCESSOR.path)
    try:
        dynamic = calculator.read_component_prices(
            workbook["КРН"],
            {"EKF-VA47-29-1P", "EKF-VA47-29-2P", "EKF-VA47-29-3P"},
            result,
        )
        assert dynamic == {
            "EKF-VA47-29-1P": (800, 216),
            "EKF-VA47-29-2P": (1500, 432),
            "EKF-VA47-29-3P": (2400, 540),
        }
        for mapping in calculator.SUCCESSOR_COMPONENT_PRICE_MAPPINGS:
            if (mapping.sheet_name, mapping.row) in {("ЩР", 8), ("КРН", 5)}:
                assert calculator.read_approved_component_price(
                    workbook, mapping, result
                ) == (mapping.expected_material_price, mapping.expected_work_price)
        assert result.red_flags == []
        old_mapping = calculator.APPROVED_COMPONENT_PRICE_MAPPINGS[0]
        assert (
            calculator.read_approved_component_price(workbook, old_mapping, result)
            is None
        )
        assert "cross-version" in result.red_flags[-1]
    finally:
        workbook.close()


def test_formula_and_duplicate_price_cases_fail_closed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    book_path = tmp_path / "synthetic.xlsx"
    book = Workbook()
    shr = book.active
    shr.title = "ЩР"
    shr["A8"] = "ВА55/57/59, АМ1  3 полюсные от 16 до 63А"
    shr["B8"] = "=15000"
    shr["C8"] = 1800
    krn = book.create_sheet("КРН")
    krn["A2"] = "ВА47 1 полюсный"
    krn["B2"] = 800
    krn["C2"] = 216
    krn["A3"] = "ВА47 1 полюсный"
    krn["B3"] = 800
    krn["C3"] = 216
    book.save(book_path)
    book.close()
    monkeypatch.setattr(
        calculator, "require_price_baseline", lambda path, version: None
    )
    loaded = load_workbook(book_path, read_only=True, data_only=False)
    result = price_result(binding.SUCCESSOR.version, book_path)
    try:
        assert (
            calculator.read_approved_component_price(
                loaded, calculator.SUCCESSOR_COMPONENT_PRICE_MAPPINGS[0], result
            )
            is None
        )
        assert any("price mismatch" in flag for flag in result.red_flags)
        assert calculator.read_component_prices(
            loaded["КРН"], {"EKF-VA47-29-1P"}, result
        ) == {"EKF-VA47-29-1P": (800, 216)}
        assert any("duplicate component price row" in flag for flag in result.red_flags)
    finally:
        loaded.close()


def test_frozen_invoice519_profile_rejects_successor_version() -> None:
    result = runner.run_checked_price_calculator_from_completed_draft(
        Path("unused.json"),
        binding.SUCCESSOR.path,
        pricing_profile_path=Path("frozen-profile.json"),
        expected_pricing_profile_sha256="a" * 64,
        price_baseline_version=binding.SUCCESSOR.version,
    )
    assert result.status == "FAIL"
    assert result.red_flags == [
        "frozen Invoice519 profile rejects successor price baseline"
    ]


def test_unversioned_and_unknown_entrypoint_calls_fail_before_input_reads() -> None:
    calc = calculator.calculate_price_draft(binding.SUCCESSOR.path, Path("missing.csv"))
    assert calc.status == "FAIL"
    assert calc.red_flags == ["explicit price baseline version is required"]
    calc_unknown = calculator.calculate_price_draft(
        binding.SUCCESSOR.path,
        Path("missing.csv"),
        price_baseline_version="unknown",
    )
    assert calc_unknown.status == "FAIL"
    assert calc_unknown.red_flags == ["unknown price baseline version"]
    checked = runner.run_checked_price_calculator_from_completed_draft(
        Path("missing.json"), binding.SUCCESSOR.path
    )
    assert checked.status == "FAIL"
    assert checked.red_flags == ["explicit price baseline version is required"]
