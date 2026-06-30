import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py"
OLD_FIVE_COLUMN_SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv.py"
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


writer = cast(
    Any,
    load_script_module("run_invoice_quote_commercial_from_csv_for_test", SCRIPT),
)


def commercial_row(
    index: int = 1,
    *,
    quantity: str | None = None,
    unit_price: str | None = None,
    vat_mode: str = "no",
    confirmation: str = "yes",
) -> list[str]:
    return [
        f"SYNTHETIC-ITEM-{index}",
        "шт.",
        quantity if quantity is not None else str(index),
        f"SYNTHETIC-DEVICES-{index}",
        f"SYNTHETIC-CABINET-{index}",
        unit_price if unit_price is not None else str(index * 1000),
        vat_mode,
        confirmation,
    ]


def write_commercial_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        csv_writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
        csv_writer.writerow(writer.commercial_preflight.REQUIRED_COLUMNS)
        csv_writer.writerows(rows)


def write_capacity100_template(
    path: Path,
    *,
    wrong_item_formula: bool = False,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = writer.SHEET_NAME

    for row in range(writer.ITEM_START_ROW, writer.ITEM_END_ROW + 1):
        worksheet[f"C{row}"] = "template item"
        worksheet[f"D{row}"] = "template unit"
        worksheet[f"E{row}"] = 1
        worksheet[f"F{row}"] = "template devices"
        worksheet[f"G{row}"] = "template cabinet"
        worksheet[f"H{row}"] = "template internal price placeholder"
        worksheet[f"I{row}"] = writer.commercial_reconciliation.item_formula(row)
    if wrong_item_formula:
        worksheet[f"I{writer.ITEM_START_ROW}"] = "=E17*H17"

    worksheet[f"I{writer.commercial_reconciliation.TOTAL_ROW}"] = (
        writer.commercial_reconciliation.total_formula()
    )
    worksheet[f"C{writer.AMOUNT_WORDS_ROW}"] = (
        "Всего прописью: template internal placeholder"
    )
    for merge_range in writer.commercial_reconciliation.EXPECTED_LOWER_MERGES:
        worksheet.merge_cells(merge_range)

    workbook.save(path)
    workbook.close()


def output_path(tmp_path: Path) -> Path:
    output_directory = tmp_path / "out"
    output_directory.mkdir()
    return output_directory / "commercial-internal-draft.xlsx"


def writer_args(
    commercial_csv: Path,
    template: Path,
    output: Path,
    capacity: int = writer.CERTIFIED_CAPACITY,
) -> list[str]:
    return [
        "--commercial-csv",
        str(commercial_csv),
        "--template",
        str(template),
        "--template-capacity",
        str(capacity),
        "--output",
        str(output),
    ]


def run_cli(
    commercial_csv: Path,
    template: Path,
    output: Path,
    capacity: int = writer.CERTIFIED_CAPACITY,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            *writer_args(commercial_csv, template, output, capacity),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def candidate_paths(output: Path) -> list[Path]:
    return list(output.parent.glob(".*.candidate.xlsx"))


def test_valid_commercial_csv_creates_reconciled_internal_draft(
    tmp_path: Path,
) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    rows = [
        commercial_row(1, quantity="2", unit_price="100000"),
        commercial_row(2, quantity="4", unit_price="50000"),
    ]
    write_commercial_csv(commercial_csv, rows)
    write_capacity100_template(template)

    template_workbook = load_workbook(template, data_only=False)
    template_sheet = template_workbook[writer.SHEET_NAME]
    line_formulas_before = {
        f"I{row}": template_sheet[f"I{row}"].value
        for row in range(writer.ITEM_START_ROW, writer.ITEM_END_ROW + 1)
    }
    total_formula_before = template_sheet[
        f"I{writer.commercial_reconciliation.TOTAL_ROW}"
    ].value
    template_workbook.close()

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 0
    assert result.stderr == ""
    assert "Status:\nPASS" in result.stdout
    assert "Mode:\ninternal draft only" in result.stdout
    assert "commercial reconciliation: pass" in result.stdout
    assert "Manual Igor check:\nrequired" in result.stdout
    assert "Human Approval:\nseparate approval required" in result.stdout
    assert output.is_file()
    assert candidate_paths(output) == []

    workbook = load_workbook(output, data_only=False)
    worksheet = workbook[writer.SHEET_NAME]
    assert worksheet["C17"].value == rows[0][0]
    assert worksheet["D17"].value == rows[0][1]
    assert worksheet["E17"].value == int(rows[0][2])
    assert worksheet["F17"].value == rows[0][3]
    assert worksheet["G17"].value == rows[0][4]
    assert worksheet["H17"].value == int(rows[0][5])
    assert isinstance(worksheet["H17"].value, int)
    assert not isinstance(worksheet["H17"].value, bool)
    assert worksheet["H17"].number_format == writer.NUMBER_FORMAT_CODE
    assert worksheet["I17"].data_type == "f"
    assert worksheet["I17"].number_format == writer.NUMBER_FORMAT_CODE
    assert worksheet[f"I{writer.commercial_reconciliation.TOTAL_ROW}"].data_type == "f"
    assert (
        worksheet[f"I{writer.commercial_reconciliation.TOTAL_ROW}"].number_format
        == writer.NUMBER_FORMAT_CODE
    )
    assert all(
        worksheet[f"H{row}"].number_format == writer.NUMBER_FORMAT_CODE
        and worksheet[f"I{row}"].number_format == writer.NUMBER_FORMAT_CODE
        for row in range(writer.ITEM_START_ROW, writer.ITEM_END_ROW + 1)
    )
    assert {
        f"I{row}": worksheet[f"I{row}"].value
        for row in range(writer.ITEM_START_ROW, writer.ITEM_END_ROW + 1)
    } == line_formulas_before
    assert (
        worksheet[f"I{writer.commercial_reconciliation.TOTAL_ROW}"].value
        == total_formula_before
    )
    assert worksheet[f"C{writer.AMOUNT_WORDS_ROW}"].value == (
        "Всего прописью: четыреста тысяч тенге 00 тиын"
    )
    assert all(
        worksheet.cell(row=row, column=column).value not in {"yes", "no"}
        for row in range(1, worksheet.max_row + 1)
        for column in range(1, worksheet.max_column + 1)
    )
    workbook.close()


def test_grand_total_words_use_independent_python_arithmetic() -> None:
    rows = [
        {"quantity": "2", "unit_price_kzt": "100000"},
        {"quantity": "4", "unit_price_kzt": "50000"},
    ]

    grand_total = writer.calculate_grand_total(rows)

    assert grand_total == 400000
    assert writer.amount_words_text(grand_total) == (
        "Всего прописью: четыреста тысяч тенге 00 тиын"
    )


def test_invalid_commercial_csv_fails_without_output(tmp_path: Path) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    row = commercial_row(unit_price="1.5")
    write_commercial_csv(commercial_csv, [row])
    write_capacity100_template(template)

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 1
    assert "Status:\nFAIL" in result.stdout
    assert "commercial preflight: fail" in result.stdout
    assert "1.5" not in result.stdout
    assert not output.exists()
    assert candidate_paths(output) == []


def test_existing_output_fails_without_overwrite(tmp_path: Path) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    existing_content = b"existing-output"
    output.write_bytes(existing_content)
    write_commercial_csv(commercial_csv, [commercial_row()])
    write_capacity100_template(template)

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 1
    assert "output already exists" in result.stdout
    assert output.read_bytes() == existing_content
    assert candidate_paths(output) == []


def test_output_inside_git_fails_before_candidate_generation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    fake_project_root = tmp_path / "repo"
    fake_project_root.mkdir()
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = fake_project_root / "blocked.xlsx"
    write_commercial_csv(commercial_csv, [commercial_row()])
    write_capacity100_template(template)
    monkeypatch.setattr(writer, "PROJECT_ROOT", fake_project_root)

    result = writer.run_commercial_writer(
        commercial_csv,
        template,
        writer.CERTIFIED_CAPACITY,
        output,
    )
    report = writer.format_report(result)

    assert result.status == "FAIL"
    assert "output is inside the Git project" in report
    assert not output.exists()
    assert candidate_paths(output) == []


def test_reconciliation_failure_prevents_output_and_cleans_candidate(
    tmp_path: Path,
) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100-wrong-formula.xlsx"
    output = output_path(tmp_path)
    row = commercial_row()
    write_commercial_csv(commercial_csv, [row])
    write_capacity100_template(template, wrong_item_formula=True)

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 1
    assert "Status:\nFAIL" in result.stdout
    assert "candidate generation: pass" in result.stdout
    assert "commercial reconciliation: fail" in result.stdout
    assert "reconciliation line formulas: fail" in result.stdout
    assert not output.exists()
    assert candidate_paths(output) == []


def test_reports_do_not_leak_commercial_values_or_full_rows(
    tmp_path: Path,
) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    secret_price = "987654321"
    row = commercial_row(unit_price=secret_price)
    write_commercial_csv(commercial_csv, [row])
    write_capacity100_template(template)

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 0
    assert secret_price not in result.stdout
    secret_total = int(row[2]) * int(secret_price)
    assert str(secret_total) not in result.stdout
    assert writer.integer_to_russian_words(secret_total) not in result.stdout
    assert ";".join(row) not in result.stdout
    assert row[0] not in result.stdout
    assert row[3] not in result.stdout


def test_preflight_failure_report_does_not_leak_commercial_values(
    tmp_path: Path,
) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    secret_price = "876543219"
    row = commercial_row(unit_price=secret_price, confirmation="no")
    write_commercial_csv(commercial_csv, [row])
    write_capacity100_template(template)

    result = run_cli(commercial_csv, template, output)

    assert result.returncode == 1
    assert secret_price not in result.stdout
    assert ";".join(row) not in result.stdout
    assert row[0] not in result.stdout
    assert not output.exists()


def test_only_certified_capacity100_is_accepted(tmp_path: Path) -> None:
    commercial_csv = tmp_path / "commercial.csv"
    template = tmp_path / "capacity100.xlsx"
    output = output_path(tmp_path)
    write_commercial_csv(commercial_csv, [commercial_row()])
    write_capacity100_template(template)

    result = run_cli(commercial_csv, template, output, capacity=99)

    assert result.returncode == 1
    assert "only the certified capacity100 profile is supported" in result.stdout
    assert not output.exists()
    assert candidate_paths(output) == []


def test_old_five_column_workflow_contract_is_unchanged() -> None:
    old_workflow = cast(
        Any,
        load_script_module(
            "run_invoice_quote_extended_from_csv_commercial_writer_contract_test",
            OLD_FIVE_COLUMN_SCRIPT,
        ),
    )

    assert old_workflow.REQUIRED_COLUMNS == (
        "name",
        "unit",
        "quantity",
        "instruments_and_devices",
        "cabinet_type_dimensions_material",
    )
    assert "unit_price_kzt" not in old_workflow.REQUIRED_COLUMNS
