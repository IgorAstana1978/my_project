import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_checked_price_calculator_from_completed_draft.py"
)
CALCULATOR_SCRIPT = PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py"
VALIDATOR_SCRIPT = (
    PROJECT_ROOT / "scripts" / "validate_completed_price_calculator_input_draft.py"
)
OLD_WORKFLOWS = (
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py",
    PROJECT_ROOT / "scripts" / "export_client_style_invoice.py",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py",
    PROJECT_ROOT / "scripts" / "validate_completed_price_calculator_input_draft.py",
    PROJECT_ROOT
    / "scripts"
    / "build_price_calculator_input_draft_from_confirmed_composition.py",
)
CALCULATOR_COLUMNS = [
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
]
PRICE_WORKBOOK = Path("/outside-git/price-workbook.xlsx").resolve(strict=False)


def load_runner_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_checked_price_calculator_from_completed_draft_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = cast(Any, load_runner_module())


def valid_data() -> dict[str, Any]:
    return {
        "schema_version": "price_calculator_input_draft.v0.1",
        "draft_type": "price_calculator_input_draft",
        "source": {
            "confirmation_id": "CONFIRMED-COMPOSITION-EXAMPLE-001",
            "confirmed_by": "Igor",
            "confirmed_at": "2026-07-07T12:00:00+05:00",
            "source_links": {
                "raw_input_sha256": "1" * 64,
                "preliminary_draft_sha256": "2" * 64,
                "review_card_sha256": "3" * 64,
            },
        },
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_rows",
            "delimiter": ";",
            "columns": CALCULATOR_COLUMNS,
            "rows": [
                {
                    "product_name": "РУ-АВР / ЩРН-24",
                    "cabinet_code": "CAB-KRN-24",
                    "consumables_factor": 1.2,
                    "component_code": "EKF-VA47-29-1P",
                    "component_qty": 4,
                    "install_type": "modular_1p",
                },
                {
                    "product_name": "РУ-АВР / ЩРН-24",
                    "cabinet_code": "CAB-KRN-24",
                    "consumables_factor": 1.2,
                    "component_code": "EKF-VA47-29-3P",
                    "component_qty": 3,
                    "install_type": "modular_3p",
                },
            ],
            "missing_required_fields": [],
            "missing_required_fields_note": "resolved by Igor",
        },
        "items": [
            {
                "item_id": "ITEM-001",
                "product_name": "РУ-АВР / ЩРН-24",
                "product_type": "switchboard",
                "quantity": 1,
                "cabinet": {
                    "cabinet_code": "CAB-KRN-24",
                    "cabinet_label": "КРН-24",
                },
                "components": [
                    {
                        "component_id": "C-001",
                        "component_code": "EKF-VA47-29-1P",
                        "component_label": "ВА47 1P",
                        "quantity": 4,
                        "install_type": "modular_1p",
                    }
                ],
            }
        ],
        "safety": {
            "status": "price_calculator_input_draft_only",
            "derived_from_confirmed_composition": True,
            "price_calculation_executed": False,
            "price_approved_by_igor": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "next_required_human_actions": [
            "Igor reviews any future price result before commercial CSV or КП.",
        ],
        "operator_completion": {
            "completed_by": "Igor",
            "completed_at": "2026-07-08T10:00:00+05:00",
            "completion_note": "consumables factor confirmed",
            "consumables_factor_confirmed_by_igor": True,
        },
    }


def write_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "completed-input.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def calculator_stdout(status: str = "PASS") -> str:
    return "\n".join(
        [
            "PRICE_CALCULATION_DRAFT_REPORT_START",
            "",
            "Status:",
            status,
            "",
            "Mode:",
            "read-only preliminary price draft",
            "",
            "Input rows count:",
            "2",
            "",
            "Total preliminary price:",
            "44 512",
            "",
            "Commercial status:",
            "preliminary only; PASS is not commercial approval",
            "",
            "Human Approval:",
            "required before using price in commercial КП",
            "",
            "PRICE_CALCULATION_DRAFT_REPORT_END",
        ]
    )


def successful_calculator_result() -> Any:
    return runner.CalculatorProcessResult(returncode=0, stdout=calculator_stdout())


def test_valid_completed_draft_runs_validator_then_calculator_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    calls: list[Path] = []

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        assert price_workbook == PRICE_WORKBOOK
        assert input_csv.exists()
        calls.append(input_csv)
        return successful_calculator_result()

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "PASS"
    assert result.checks["completed input validation"] == "pass"
    assert result.checks["calculator execution"] == "pass"
    assert len(calls) == 1
    assert not calls[0].exists()


def test_validator_fail_prevents_calculator_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = valid_data()
    data["operator_completion"]["consumables_factor_confirmed_by_igor"] = False
    completed_json = write_json(tmp_path, data)

    def fail_if_called(price_workbook: Path, input_csv: Path) -> Any:
        raise AssertionError("calculator should not run")

    monkeypatch.setattr(runner, "run_calculator_cli", fail_if_called)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "FAIL"
    assert result.checks["completed input validation"] == "fail"
    assert result.temp_csv_path is None


def test_malformed_completed_json_prevents_calculator_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = tmp_path / "malformed.json"
    completed_json.write_text("{not-json", encoding="utf-8")

    def fail_if_called(price_workbook: Path, input_csv: Path) -> Any:
        raise AssertionError("calculator should not run")

    monkeypatch.setattr(runner, "run_calculator_cli", fail_if_called)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "FAIL"
    assert result.checks["CSV bridge"] == "fail"
    assert result.temp_csv_path is None


def test_csv_bridge_uses_exact_columns_and_semicolon_delimiter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    captured_text: list[str] = []

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        captured_text.append(input_csv.read_text(encoding="utf-8"))
        with input_csv.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.reader(csv_file, delimiter=";"))
        assert rows[0] == CALCULATOR_COLUMNS
        assert rows[1] == [
            "РУ-АВР / ЩРН-24",
            "CAB-KRN-24",
            "1.2",
            "EKF-VA47-29-1P",
            "4",
            "modular_1p",
        ]
        return successful_calculator_result()

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "PASS"
    assert captured_text
    assert captured_text[0].splitlines()[0] == ";".join(CALCULATOR_COLUMNS)
    assert "," not in captured_text[0].splitlines()[0]


def test_temporary_csv_is_deleted_after_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    temp_paths: list[Path] = []

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        assert input_csv.exists()
        temp_paths.append(input_csv)
        return successful_calculator_result()

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "PASS"
    assert result.checks["temp cleanup"] == "pass"
    assert temp_paths
    assert not temp_paths[0].exists()


def test_temporary_csv_is_deleted_after_calculator_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    temp_paths: list[Path] = []

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        assert input_csv.exists()
        temp_paths.append(input_csv)
        return runner.CalculatorProcessResult(
            returncode=7,
            stdout=calculator_stdout("FAIL"),
            stderr="calculator failed",
        )

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "FAIL"
    assert result.checks["temp cleanup"] == "pass"
    assert temp_paths
    assert not temp_paths[0].exists()


def test_calculator_non_zero_causes_runner_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        return runner.CalculatorProcessResult(
            returncode=3,
            stdout=calculator_stdout("FAIL"),
        )

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "FAIL"
    assert result.checks["calculator execution"] == "fail"
    assert any("non-zero" in flag for flag in result.red_flags)


def test_report_has_required_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    assert (
        runner.main(
            [
                "--completed-input-json",
                str(completed_json),
                "--price-workbook",
                str(PRICE_WORKBOOK),
            ]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert report.startswith("CHECKED_PRICE_CALCULATOR_RUN_REPORT_START")
    assert (
        "Mode:\nchecked read-only price calculator run from completed draft" in report
    )
    assert "Calculator result:" in report
    assert report.rstrip().endswith("CHECKED_PRICE_CALCULATOR_RUN_REPORT_END")


def test_report_states_draft_price_calculation_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )
    report = runner.format_report(result)

    assert "draft price calculation only" in report
    assert "not price approval" in report
    assert "PASS is not commercial approval" in report


def test_report_does_not_create_client_ready_statement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    report = runner.format_report(
        runner.run_checked_price_calculator_from_completed_draft(
            completed_json,
            PRICE_WORKBOOK,
        )
    )

    assert "client-ready КП" in report
    assert "not client-ready КП" in report
    assert "Status:\nclient-ready КП" not in report


def test_report_does_not_approve_commercial_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    report = runner.format_report(
        runner.run_checked_price_calculator_from_completed_draft(
            completed_json,
            PRICE_WORKBOOK,
        )
    )

    assert "not commercial CSV" in report
    assert "commercial CSV approved" not in report.lower()


def test_report_does_not_authorize_sending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    report = runner.format_report(
        runner.run_checked_price_calculator_from_completed_draft(
            completed_json,
            PRICE_WORKBOOK,
        )
    )

    assert "sending or production" in report
    assert "sending authorized" not in report.lower()


def test_report_does_not_authorize_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    report = runner.format_report(
        runner.run_checked_price_calculator_from_completed_draft(
            completed_json,
            PRICE_WORKBOOK,
        )
    )

    assert "sending or production" in report
    assert "production authorized" not in report.lower()


def test_script_calls_validator_231f() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert VALIDATOR_SCRIPT.name in source
    assert "validate_completed_price_calculator_input_draft" in source


def test_script_uses_existing_calc_quote_price_draft_without_modifying_it() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert CALCULATOR_SCRIPT.name in source
    assert "--price-workbook" in source
    assert "--input-csv" in source


def test_script_does_not_reference_commercial_writer_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "run_invoice_quote_commercial_from_csv" not in source
    assert "make_quote_capacity100_commercial_checked" not in source
    assert "commercial writer" not in source.lower()


def test_script_does_not_reference_client_style_exporter_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "export_client_style_invoice" not in source
    assert "run_client_style_invoice_export" not in source
    assert "client-style exporter" not in source.lower()


def test_script_does_not_call_git() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()

    assert " git " not in source
    assert "git." not in source


def test_old_workflows_do_not_reference_this_runner() -> None:
    runner_name = "run_checked_price_calculator_from_completed_draft"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert runner_name not in path.read_text(encoding="utf-8"), path


def test_no_persistent_csv_xlsx_generated_or_client_files_are_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    before = {
        path
        for pattern in ("*.csv", "*.xlsx", "*.generated*", "*.client*")
        for path in PROJECT_ROOT.glob(pattern)
    }
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: successful_calculator_result(),
    )

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    after = {
        path
        for pattern in ("*.csv", "*.xlsx", "*.generated*", "*.client*")
        for path in PROJECT_ROOT.glob(pattern)
    }
    assert result.status == "PASS"
    assert after == before
    assert result.temp_csv_path is not None
    assert not result.temp_csv_path.exists()
