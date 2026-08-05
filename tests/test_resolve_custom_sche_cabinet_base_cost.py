import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "resolve_custom_sche_cabinet_base_cost.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


resolver = cast(
    Any,
    load_script_module("resolve_custom_sche_cabinet_base_cost_for_test", SCRIPT),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checked_workbook(
    path: Path,
    *,
    mutate: Callable[[Any], None] | None = None,
    sheet_name: str = "Лист1",
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet["B1"] = 1
    sheet["B2"] = 100
    sheet["B3"] = 200
    sheet["B5"] = 1
    sheet["C5"] = 1
    sheet["A82"] = "ЩЭ 5кв 900х900х120"
    sheet["B82"] = "=ROUNDUP(D82*$B$5,0)"
    sheet["C82"] = "=ROUNDUP(D82*$C$5,0)"
    sheet["D82"] = "=ROUNDUP((M82+N82)*R82+O82+P82+S82+Q82,0)"
    sheet["E82"] = 900
    sheet["F82"] = 900
    sheet["G82"] = 120
    sheet["H82"] = "=(E82/1000)"
    sheet["I82"] = "=(F82/1000)"
    sheet["J82"] = "=(G82/1000)"
    sheet["K82"] = "=(H82+0.066)*(I82+0.066)+0.1*" "((H82-0.01)*4+I82*2+I82-0.09+J82*8)"
    sheet["L82"] = "=K82*$B$1*8.42"
    sheet["M82"] = "=L82*$B$2"
    sheet["N82"] = "=K82*2*0.25*$B$3*1.33"
    sheet["O82"] = 3750
    sheet["P82"] = 900
    sheet["Q82"] = "=1250"
    sheet["R82"] = 1.05
    sheet["S82"] = 1700
    if mutate is not None:
        mutate(sheet)
    workbook.save(path)
    workbook.close()


def resolve(
    workbook_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    **overrides: object,
) -> dict[str, Any]:
    actual_sha256 = sha256(workbook_path)
    monkeypatch.setattr(resolver, "APPROVED_WORKBOOK_SHA256", actual_sha256)
    arguments: dict[str, object] = {
        "metal_workbook_path": workbook_path,
        "expected_workbook_sha256": actual_sha256,
        "internal_cabinet_code": "CAB-SCHE-BI-900X900X120-M12",
        "metal_thickness": "1.2",
        "expected_sheet": "Лист1",
        "expected_row": 82,
    }
    arguments.update(overrides)
    return cast(
        dict[str, Any],
        resolver.resolve_custom_sche_cabinet_base_cost(**arguments),
    )


def test_checked_synthetic_workbook_resolves_without_modification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = tmp_path / "metal.xlsx"
    write_checked_workbook(workbook_path)
    before = sha256(workbook_path)

    result = resolve(workbook_path, monkeypatch)

    assert result["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_VALIDATED"
    assert result["errors"] == []
    assert result["cabinet_identity"] == {
        "internal_cabinet_code": "CAB-SCHE-BI-900X900X120-M12",
        "source_cabinet_label": "ЩЭ 5кв 900х900х120",
        "installation": "built_in",
        "dimensions_mm": {"width": "900", "height": "900", "depth": "120"},
        "metal_thickness_mm": "1.2",
        "shared_source_templates": ["ЩЭ-3кв", "ЩЭ-4кв", "ЩЭ-5кв", "ЩЭ-6кв"],
    }
    assert result["computed_formula_roles"] == {
        "H82_width_m": "0.9",
        "I82_height_m": "0.9",
        "J82_depth_m": "0.12",
        "K82_sheet_area_m2": "1.646156",
        "L82_metal_mass_kg": "16.632760224",
        "M82_metal_cost": "1663.276022400",
        "N82_labor_cost": "218.9387480000",
        "D82_base_cost": "9577",
    }
    assert result["base_cost"] == {
        "source_role": "D82",
        "value": "9577",
        "rounding": "ROUNDUP_TO_INTEGER",
        "excluded_output_roles": ["B82", "C82"],
    }
    assert result["source_provenance"]["excel_recalculation_executed"] is False
    assert sha256(workbook_path) == before


@pytest.mark.parametrize(
    ("overrides", "error_fragment"),
    [
        ({"expected_workbook_sha256": "0" * 64}, "approved workbook hash"),
        ({"expected_sheet": "Другой"}, "approved source sheet"),
        ({"expected_row": 81}, "approved source row"),
        ({"internal_cabinet_code": "CAB-WRONG"}, "not approved"),
        ({"metal_thickness": ""}, "must be numeric"),
        ({"metal_thickness": "0"}, "positive finite"),
        ({"metal_thickness": "1.0"}, "approved 1.2 mm"),
    ],
)
def test_invalid_explicit_inputs_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    error_fragment: str,
) -> None:
    workbook_path = tmp_path / "metal.xlsx"
    write_checked_workbook(workbook_path)

    result = resolve(workbook_path, monkeypatch, **overrides)

    assert result["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_FAILED"
    assert error_fragment in result["errors"][0]


@pytest.mark.parametrize(
    ("mutate", "error_fragment"),
    [
        (lambda sheet: setattr(sheet["A82"], "value", "wrong"), "source label drift"),
        (lambda sheet: setattr(sheet["E82"], "value", 901), "dimensions drift"),
        (lambda sheet: setattr(sheet["D82"], "value", "=1"), "formula drift"),
        (lambda sheet: setattr(sheet["O82"], "value", 3751), "value drift"),
        (lambda sheet: setattr(sheet["P82"], "value", 901), "value drift"),
        (lambda sheet: setattr(sheet["Q82"], "value", "=1251"), "formula drift"),
        (lambda sheet: setattr(sheet["R82"], "value", 1.06), "value drift"),
        (lambda sheet: setattr(sheet["S82"], "value", 1701), "value drift"),
        (lambda sheet: setattr(sheet["B2"], "value", None), "numeric value"),
        (lambda sheet: setattr(sheet["B3"], "value", None), "numeric value"),
        (lambda sheet: setattr(sheet["B3"], "value", 0), "positive numeric"),
    ],
)
def test_source_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[Any], None],
    error_fragment: str,
) -> None:
    workbook_path = tmp_path / "metal.xlsx"
    write_checked_workbook(workbook_path, mutate=mutate)

    result = resolve(workbook_path, monkeypatch)

    assert result["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_FAILED"
    assert error_fragment in result["errors"][0]


def test_absent_approved_sheet_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = tmp_path / "metal.xlsx"
    write_checked_workbook(workbook_path, sheet_name="Другой")

    result = resolve(workbook_path, monkeypatch)

    assert result["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_FAILED"
    assert "required sheet" in result["errors"][0]


def test_output_is_json_and_never_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = tmp_path / "metal.xlsx"
    output_path = tmp_path / "result.json"
    write_checked_workbook(workbook_path)

    first = resolve(
        workbook_path,
        monkeypatch,
        output_json_path=output_path,
    )
    output_before = output_path.read_bytes()
    second = resolve(
        workbook_path,
        monkeypatch,
        output_json_path=output_path,
    )

    assert first["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_VALIDATED"
    assert json.loads(output_before)["base_cost"]["value"] == "9577"
    assert second["status"] == "CUSTOM_SCHE_BASE_COST_RESOLUTION_FAILED"
    assert "overwrite is forbidden" in second["errors"][0]
    assert output_path.read_bytes() == output_before
