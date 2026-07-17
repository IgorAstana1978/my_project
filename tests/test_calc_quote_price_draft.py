import csv
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py"
TECHNICAL_WORKFLOW = PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1"
COMMERCIAL_WORKFLOW = (
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1"
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


calculator = cast(
    Any,
    load_script_module("calc_quote_price_draft_for_test", SCRIPT),
)


def confirmed_rows() -> list[list[str]]:
    return [
        [
            "РУ-АВР / ЩРН-24",
            "CAB-KRN-24",
            "1.20",
            "EKF-VA47-29-1P",
            "4",
            "modular_1p",
        ],
        [
            "РУ-АВР / ЩРН-24",
            "CAB-KRN-24",
            "1.20",
            "EKF-VA47-29-3P",
            "3",
            "modular_3p",
        ],
        [
            "РУ-АВР / ЩРН-24",
            "CAB-KRN-24",
            "1.20",
            "EKF-RN-47",
            "1",
            "modular_1p",
        ],
    ]


def write_csv(path: Path, rows: list[list[str]] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
        writer.writerow(calculator.REQUIRED_COLUMNS)
        writer.writerows(confirmed_rows() if rows is None else rows)


def write_technical_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
        writer.writerow(calculator.TECHNICAL_COLUMNS)
        writer.writerows(rows)


def write_workbook(
    path: Path,
    *,
    include_component: bool = True,
    include_cabinet: bool = True,
) -> None:
    workbook = Workbook()
    krn = workbook.active
    krn.title = "КРН"
    krn.append(["Наименование", "Материал", "Работа"])
    if include_component:
        krn.append(["ВА47 1 полюсный", 700, 216])
        krn.append(["ВА47 3 полюсный до 63А", 2200, 540])
        krn.append(["независимый расцепитель для ВА47 РН47", 7500, 216])
    if include_cabinet:
        krn["L8"] = "Корпус КРН-24 395х330х100"
        krn["M8"] = 7985

    forbidden = workbook.create_sheet("Прайс")
    forbidden.append(["ВА47 1 полюсный", 1, 1])
    forbidden.append(["ВА47 3 полюсный до 63А", 1, 1])
    forbidden.append(["независимый расцепитель для ВА47 РН47", 1, 1])
    forbidden["L8"] = "Корпус КРН-24 395х330х100"
    forbidden["M8"] = 1

    workbook.save(path)
    workbook.close()


def write_approved_workbook(path: Path) -> None:
    workbook = Workbook()
    krn = workbook.active
    krn.title = "КРН"
    krn["A5"] = "УЗО АД-32 1Р+N до 63А EKF"
    krn["B5"] = 4100
    krn["C5"] = 432
    krn["L9"] = "Корпус КРН-36 540х330х100"
    krn["M9"] = 9405
    krn["A14"] = "ВН-32 3Р 16-25-40-63-80-100А"
    krn["B14"] = 2750
    krn["C14"] = 540

    shr = workbook.create_sheet("ЩР")
    shr["A8"] = "ВА55/57/59, АМ1  3 полюсные от 16 до 63А"
    shr["B8"] = 13000
    shr["C8"] = 1800
    shr["L8"] = "800х600х250"
    shr["M8"] = 21336

    forbidden = workbook.create_sheet("Прайс")
    forbidden["A5"] = "УЗО АД-32 1Р+N до 63А EKF"
    forbidden["B5"] = 1
    forbidden["C5"] = 1
    workbook.save(path)
    workbook.close()


def technical_row(
    *,
    product_name: str = "TEST-PANEL",
    cabinet_code: str,
    component_code: str,
    install_type: str,
    component_label: str,
    cabinet_label: str,
) -> list[str]:
    return [
        product_name,
        cabinet_code,
        "1.20",
        component_code,
        "1",
        install_type,
        component_label,
        cabinet_label,
    ]


def test_approved_component_mappings_use_technical_signatures(tmp_path: Path) -> None:
    workbook_path = tmp_path / "approved.xlsx"
    write_approved_workbook(workbook_path)
    cases = (
        (
            "RAW-VA88-32",
            "mccb_up_to_100a",
            "CHINT, автоматический выключатель 3P 63А",
            "ПР",
            "ПР 800×600×250 мм, металл",
            13000,
            1800,
        ),
        (
            "RAW-AVDT32",
            "diff_1p_n",
            "CHINT, АВДТ 2P C16/30мА",
            "КРН-36",
            "КРН-36, 540×330×100 мм, металл",
            4100,
            432,
        ),
        (
            "ANOTHER-RAW-CODE",
            "load_switch_3p",
            "CHINT, выключатель нагрузки 3P 32А",
            "КРН-36",
            "КРН-36, 540×330×100 мм, металл",
            2750,
            540,
        ),
    )

    for index, case in enumerate(cases):
        code, install_type, label, cabinet_code, cabinet_label, material, work = case
        csv_path = tmp_path / f"technical-{index}.csv"
        write_technical_csv(
            csv_path,
            [
                technical_row(
                    cabinet_code=cabinet_code,
                    component_code=code,
                    install_type=install_type,
                    component_label=label,
                    cabinet_label=cabinet_label,
                )
            ],
        )
        result = calculate(workbook_path, csv_path)
        assert result.status == "PASS"
        assert result.component_material_total == material
        assert result.work_total == work


def test_approved_cabinet_mappings_are_exact(tmp_path: Path) -> None:
    workbook_path = tmp_path / "approved.xlsx"
    write_approved_workbook(workbook_path)
    cases = (
        ("ПР", "ПР 800×600×250 мм, металл", 21336),
        ("КРН-36", "КРН-36, 540×330×100 мм, металл", 9405),
    )
    for index, (cabinet_code, cabinet_label, expected_price) in enumerate(cases):
        csv_path = tmp_path / f"cabinet-{index}.csv"
        is_pr = cabinet_code == "ПР"
        write_technical_csv(
            csv_path,
            [
                technical_row(
                    cabinet_code=cabinet_code,
                    component_code="RAW",
                    install_type=("mccb_up_to_100a" if is_pr else "diff_1p_n"),
                    component_label=(
                        "CHINT, автоматический выключатель 3P 63А"
                        if is_pr
                        else "CHINT, АВДТ 2P C20/30мА"
                    ),
                    cabinet_label=cabinet_label,
                )
            ],
        )
        assert calculate(workbook_path, csv_path).cabinet_price == expected_price


def test_approved_workbook_row_signature_mismatch_fails(tmp_path: Path) -> None:
    workbook_path = tmp_path / "mismatch.xlsx"
    write_approved_workbook(workbook_path)
    workbook = load_workbook(workbook_path)
    workbook["КРН"]["A5"] = "changed signature"
    workbook.save(workbook_path)
    workbook.close()
    csv_path = tmp_path / "composition.csv"
    write_technical_csv(
        csv_path,
        [
            technical_row(
                cabinet_code="КРН-36",
                component_code="RAW",
                install_type="diff_1p_n",
                component_label="CHINT, АВДТ 2P C16/30мА",
                cabinet_label="КРН-36, 540×330×100 мм, металл",
            )
        ],
    )
    result = calculate(workbook_path, csv_path)
    assert result.status == "FAIL"
    assert any("signature mismatch" in flag for flag in result.red_flags)


def test_unknown_technical_mapping_fails_closed(tmp_path: Path) -> None:
    workbook_path = tmp_path / "approved.xlsx"
    write_approved_workbook(workbook_path)
    csv_path = tmp_path / "composition.csv"
    write_technical_csv(
        csv_path,
        [
            technical_row(
                cabinet_code="КРН-36",
                component_code="RAW",
                install_type="diff_1p_n",
                component_label="CHINT, АВДТ 2P C25/30мА",
                cabinet_label="КРН-36, 540×330×100 мм, металл",
            )
        ],
    )
    result = calculate(workbook_path, csv_path)
    assert result.status == "FAIL"
    assert any("unknown or ambiguous" in flag for flag in result.red_flags)


def test_ambiguous_technical_mapping_fails_closed(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    workbook_path = tmp_path / "approved.xlsx"
    write_approved_workbook(workbook_path)
    duplicate = calculator.APPROVED_COMPONENT_PRICE_MAPPINGS[1]
    monkeypatch.setattr(
        calculator,
        "APPROVED_COMPONENT_PRICE_MAPPINGS",
        calculator.APPROVED_COMPONENT_PRICE_MAPPINGS + (duplicate,),
    )
    csv_path = tmp_path / "composition.csv"
    write_technical_csv(
        csv_path,
        [
            technical_row(
                cabinet_code="КРН-36",
                component_code="RAW",
                install_type="diff_1p_n",
                component_label="CHINT, АВДТ 2P C16/30мА",
                cabinet_label="КРН-36, 540×330×100 мм, металл",
            )
        ],
    )
    result = calculate(workbook_path, csv_path)
    assert result.status == "FAIL"
    assert any("unknown or ambiguous" in flag for flag in result.red_flags)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calculate(workbook_path: Path, csv_path: Path) -> Any:
    return calculator.calculate_price_draft(workbook_path, csv_path)


def test_confirmed_reference_calculation_is_44512(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    write_csv(csv_path)

    result = calculate(workbook_path, csv_path)

    assert result.status == "PASS"
    assert result.product_name == "РУ-АВР / ЩРН-24"
    assert result.cabinet_price == 7985
    assert result.component_material_total == 16900
    assert result.work_total == 2700
    assert result.consumables_factor == calculator.Decimal("1.20")
    assert result.base == calculator.Decimal("30965")
    assert result.total_preliminary_price == 44512


def test_forbidden_price_worksheet_is_never_selected(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    write_csv(csv_path)
    real_load_workbook = calculator.load_workbook
    selected_sheets: list[str] = []

    class TrackingWorkbook:
        def __init__(self, wrapped: Any) -> None:
            self.wrapped = wrapped

        def __getitem__(self, name: str) -> Any:
            selected_sheets.append(name)
            if name == "Прайс":
                raise AssertionError("forbidden worksheet was selected")
            return self.wrapped[name]

        def close(self) -> None:
            self.wrapped.close()

    def tracking_load_workbook(*args: Any, **kwargs: Any) -> TrackingWorkbook:
        return TrackingWorkbook(real_load_workbook(*args, **kwargs))

    monkeypatch.setattr(calculator, "load_workbook", tracking_load_workbook)

    result = calculate(workbook_path, csv_path)

    assert result.status == "PASS"
    assert selected_sheets == ["КРН"]
    assert result.total_preliminary_price == 44512


def test_unknown_component_code_fails_with_red_flag(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    rows = confirmed_rows()
    rows[0][3] = "UNKNOWN-COMPONENT"
    write_csv(csv_path, rows)

    result = calculate(workbook_path, csv_path)
    report = calculator.format_report(result)

    assert result.status == "FAIL"
    assert "component_code is not confirmed: UNKNOWN-COMPONENT" in report
    assert "ask Igor" in report
    assert result.total_preliminary_price is None


def test_unknown_cabinet_code_fails_with_red_flag(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    rows = confirmed_rows()
    for row in rows:
        row[1] = "UNKNOWN-CABINET"
    write_csv(csv_path, rows)

    result = calculate(workbook_path, csv_path)
    report = calculator.format_report(result)

    assert result.status == "FAIL"
    assert "cabinet_code is not confirmed: UNKNOWN-CABINET" in report
    assert "ask Igor" in report
    assert result.cabinet_price is None


def test_missing_confirmed_component_price_fails(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path, include_component=False)
    write_csv(csv_path)

    result = calculate(workbook_path, csv_path)
    report = calculator.format_report(result)

    assert result.status == "FAIL"
    assert "component price row was not found in КРН" in report
    assert "ask Igor" in report


def test_missing_confirmed_cabinet_price_fails(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path, include_cabinet=False)
    write_csv(csv_path)

    result = calculate(workbook_path, csv_path)
    report = calculator.format_report(result)

    assert result.status == "FAIL"
    assert "cabinet price row was not found in КРН" in report
    assert "ask Igor" in report


def test_install_type_mismatch_fails_closed(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    rows = confirmed_rows()
    rows[0][5] = "modular_3p"
    write_csv(csv_path, rows)

    result = calculate(workbook_path, csv_path)

    assert result.status == "FAIL"
    assert any("install_type does not match" in flag for flag in result.red_flags)


def test_calculation_does_not_create_or_change_xlsx(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    write_csv(csv_path)
    xlsx_before = sorted(tmp_path.glob("*.xlsx"))
    workbook_hash_before = sha256(workbook_path)

    result = calculate(workbook_path, csv_path)

    assert result.status == "PASS"
    assert sorted(tmp_path.glob("*.xlsx")) == xlsx_before
    assert sha256(workbook_path) == workbook_hash_before


def test_report_contains_required_safety_boundaries(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    write_csv(csv_path)

    report = calculator.format_report(calculate(workbook_path, csv_path))

    assert report.startswith("PRICE_CALCULATION_DRAFT_REPORT_START")
    assert report.endswith("PRICE_CALCULATION_DRAFT_REPORT_END")
    assert "Mode:\nread-only preliminary price draft" in report
    assert "Total preliminary price:\n44 512" in report
    assert "PASS is not commercial approval" in report
    assert "Igor approval required" in report
    assert "Manual Igor check:\nrequired" in report
    assert "Human Approval:" in report


def test_cli_prints_pass_report_and_returns_zero(tmp_path: Path) -> None:
    workbook_path = tmp_path / "price.xlsx"
    csv_path = tmp_path / "composition.csv"
    write_workbook(workbook_path)
    write_csv(csv_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--price-workbook",
            str(workbook_path),
            "--input-csv",
            str(csv_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Status:\nPASS" in result.stdout
    assert "Cabinet price:\n7 985" in result.stdout
    assert "Component material total:\n16 900" in result.stdout
    assert "Work total:\n2 700" in result.stdout
    assert "Base:\n30 965" in result.stdout
    assert "Total preliminary price:\n44 512" in result.stdout


def test_existing_workflows_remain_isolated_from_calculator() -> None:
    calculator_text = SCRIPT.read_text(encoding="utf-8")
    technical_text = TECHNICAL_WORKFLOW.read_text(encoding="utf-8")
    commercial_text = COMMERCIAL_WORKFLOW.read_text(encoding="utf-8")

    assert "make_quote_capacity100_checked.ps1" not in calculator_text
    assert "make_quote_capacity100_commercial_checked.ps1" not in calculator_text
    assert "calc_quote_price_draft.py" not in technical_text
    assert "calc_quote_price_draft.py" not in commercial_text
