import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPACT_RUNNER_SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv_compact.py"
)
ITEMS_BRIDGE_TESTS = (
    PROJECT_ROOT / "tests" / "test_run_invoice_quote_extended_from_items.py"
)
REQUIRED_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
)
FORBIDDEN_COMMERCIAL_COLUMNS = {
    "price",
    "sum",
    "vat",
    "currency",
    "term",
    "discount",
    "price_confirmed_by_igor",
}


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


items_bridge_tests = cast(
    Any,
    load_script_module(
        "run_invoice_quote_extended_from_items_helpers_for_short_capacity_test",
        ITEMS_BRIDGE_TESTS,
    ),
)
SHEET_NAME = items_bridge_tests.SHEET_NAME
write_extended_template = items_bridge_tests.write_extended_template


def output_path(tmp_path: Path) -> Path:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    return output_dir / "draft.xlsx"


def write_synthetic_short_items_csv(path: Path) -> None:
    assert REQUIRED_COLUMNS == (
        "name",
        "unit",
        "quantity",
        "instruments_and_devices",
        "cabinet_type_dimensions_material",
    )
    assert not FORBIDDEN_COMMERCIAL_COLUMNS.intersection(REQUIRED_COLUMNS)

    rows = [
        ["ЩР-ТЕСТ-1", "шт.", "1", "Синтетика-автомат-1", "Синтетика-шкаф-1"],
        ["ЩР-ТЕСТ-2", "шт.", "1", "Синтетика-автомат-2", "Синтетика-шкаф-2"],
        ["ЩР-ТЕСТ-3", "шт.", "1", "Синтетика-автомат-3", "Синтетика-шкаф-3"],
    ]
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow(REQUIRED_COLUMNS)
        writer.writerows(rows)


def run_compact_runner(
    items_csv: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(COMPACT_RUNNER_SCRIPT),
            "--items-csv",
            str(items_csv),
            "--template",
            str(template),
            "--template-capacity",
            str(capacity),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_capacity100_compact_csv_runtime_supports_three_item_rows(
    tmp_path: Path,
) -> None:
    template = tmp_path / "capacity100_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template, capacity=100)
    write_synthetic_short_items_csv(items_csv)

    result = run_compact_runner(items_csv, template, 100, output)

    assert result.returncode == 0
    assert "CREATED:" in result.stdout
    assert "ERROR:" not in result.stderr
    assert output.is_file()

    workbook = load_workbook(output, data_only=False)
    sheet = workbook[SHEET_NAME]

    used_rows = [row for row in range(17, 117) if sheet[f"C{row}"].value is not None]
    hidden_rows = [row for row in range(17, 117) if sheet.row_dimensions[row].hidden]

    assert used_rows == [17, 18, 19]
    assert hidden_rows == list(range(20, 117))
    assert len(hidden_rows) == 97

    for offset, row in enumerate(range(17, 20), start=1):
        assert sheet.row_dimensions[row].hidden is False
        assert sheet[f"C{row}"].value == f"ЩР-ТЕСТ-{offset}"
        assert sheet[f"D{row}"].value == "шт."
        assert sheet[f"E{row}"].value == 1
        assert sheet[f"F{row}"].value == f"Синтетика-автомат-{offset}"
        assert sheet[f"G{row}"].value == f"Синтетика-шкаф-{offset}"

    assert sheet["C20"].value is None
    for row in range(20, 117):
        assert sheet.row_dimensions[row].hidden is True
        for column in "CDEFGH":
            assert sheet[f"{column}{row}"].value is None

    assert sheet["I117"].value == "=SUM(I17:I116)"
    assert sheet["B120"].value == "signature"
    assert tuple(str(item) for item in sheet.merged_cells.ranges) == ("B120:I122",)
