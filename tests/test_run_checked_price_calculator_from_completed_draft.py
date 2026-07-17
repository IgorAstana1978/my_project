import csv
import importlib.util
import io
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
                    },
                    {
                        "component_id": "C-002",
                        "component_code": "EKF-VA47-29-3P",
                        "component_label": "ВА47 3 полюсный до 63А",
                        "quantity": 3,
                        "install_type": "modular_3p",
                    },
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


def multi_item_data() -> dict[str, Any]:
    data = valid_data()
    specs = (
        (
            "ЩО-TEST",
            "ПР",
            "ПР 800×600×250 мм, металл",
            21,
            "RAW-VA88",
            "CHINT, автоматический выключатель 3P 63А",
            "mccb_up_to_100a",
        ),
        (
            "НЩР-TEST",
            "КРН-36",
            "КРН-36, 540×330×100 мм, металл",
            13,
            "RAW-AVDT",
            "CHINT, АВДТ 2P C16/30мА",
            "diff_1p_n",
        ),
        (
            "АВР-TEST",
            "КРН-36",
            "КРН-36, 540×330×100 мм, металл",
            12,
            "RAW-VN",
            "CHINT, выключатель нагрузки 3P 32А",
            "load_switch_3p",
        ),
    )
    rows: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for item_index, spec in enumerate(specs, start=1):
        product, cabinet_code, cabinet_label, count, code, label, install_type = spec
        components: list[dict[str, Any]] = []
        for component_index in range(1, count + 1):
            component = {
                "component_id": f"I{item_index}-C{component_index}",
                "component_code": code,
                "component_label": label,
                "quantity": 1,
                "install_type": install_type,
            }
            components.append(component)
            rows.append(
                {
                    "product_name": product,
                    "cabinet_code": cabinet_code,
                    "consumables_factor": 1.2,
                    "component_code": code,
                    "component_qty": 1,
                    "install_type": install_type,
                }
            )
        items.append(
            {
                "item_id": f"ITEM-{item_index}",
                "product_name": product,
                "product_type": "switchboard",
                "quantity": 1,
                "cabinet": {
                    "cabinet_code": cabinet_code,
                    "cabinet_label": cabinet_label,
                },
                "components": components,
            }
        )
    data["calculator_input_format"]["rows"] = rows
    data["items"] = items
    return data


def write_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "completed-input.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def calculator_stdout(
    status: str = "PASS",
    *,
    rows: int = 2,
    total: int = 44512,
    red_flags: list[str] | None = None,
) -> str:
    lines = [
        "PRICE_CALCULATION_DRAFT_REPORT_START",
        "",
        "Status:",
        status,
        "",
        "Mode:",
        "read-only preliminary price draft",
        "",
        "Input rows count:",
        str(rows),
        "",
        "Cabinet:",
        "CAB-KRN-24 / Корпус КРН-24 395х330х100",
        "",
        "Cabinet price:",
        "7 985",
        "",
        "Component material total:",
        "16 900",
        "",
        "Work total:",
        "2 700",
        "",
        "Additional materials total:",
        "3 380",
        "",
        "Total preliminary price:",
        f"{total:,}".replace(",", " "),
        "",
        "Red flags:",
    ]
    lines.extend(red_flags if red_flags is not None else ["none"])
    lines.extend(
        [
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
    return "\n".join(lines)


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


def test_multi_item_split_runs_21_13_12_and_aggregates_total(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, multi_item_data())
    expected_counts = [21, 13, 12]
    expected_totals = [101000, 202000, 303000]
    calls: list[Path] = []

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        call_index = len(calls)
        with input_csv.open("r", encoding="utf-8", newline="") as csv_file:
            csv_rows = list(csv.reader(csv_file, delimiter=";"))
        assert len(csv_rows) - 1 == expected_counts[call_index]
        assert len({row[0] for row in csv_rows[1:]}) == 1
        calls.append(input_csv)
        return runner.CalculatorProcessResult(
            returncode=0,
            stdout=calculator_stdout(
                rows=expected_counts[call_index],
                total=expected_totals[call_index],
            ),
        )

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)
    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "PASS"
    assert [summary.input_rows_count for summary in result.item_summaries] == [
        21,
        13,
        12,
    ]
    assert result.overall_preliminary_total == sum(expected_totals)
    assert len(result.calculator_runs) == 3
    assert len(result.temp_csv_paths) == 3
    assert all(not path.exists() for path in calls)


def test_item_component_audit_mismatch_fails_before_calculator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = valid_data()
    data["items"][0]["components"][0]["component_code"] = "MISMATCH"
    completed_json = write_json(tmp_path, data)
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: (_ for _ in ()).throw(
            AssertionError("calculator should not run")
        ),
    )

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "FAIL"
    assert any("audit mismatch" in flag for flag in result.red_flags)


def test_multi_item_run_preserves_safety_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = multi_item_data()
    original_safety = dict(data["safety"])
    completed_json = write_json(tmp_path, data)
    call_count = 0

    def fake_calculator(price_workbook: Path, input_csv: Path) -> Any:
        nonlocal call_count
        rows = (21, 13, 12)[call_count]
        call_count += 1
        return runner.CalculatorProcessResult(
            returncode=0,
            stdout=calculator_stdout(rows=rows, total=1000),
        )

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)
    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    reloaded = json.loads(completed_json.read_text(encoding="utf-8"))
    assert result.checks["safety boundary"] == "pass"
    assert reloaded["safety"] == original_safety
    assert all(
        reloaded["safety"][field_name] is False
        for field_name in (
            "price_calculation_executed",
            "price_approved_by_igor",
            "commercial_csv_authorized",
            "client_style_export_authorized",
            "sending_authorized",
            "production_authorized",
        )
    )


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
        assert rows[0] == CALCULATOR_COLUMNS + ["component_label", "cabinet_label"]
        assert rows[1] == [
            "РУ-АВР / ЩРН-24",
            "CAB-KRN-24",
            "1.2",
            "EKF-VA47-29-1P",
            "4",
            "modular_1p",
            "ВА47 1P",
            "КРН-24",
        ]
        return successful_calculator_result()

    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )

    assert result.status == "PASS"
    assert captured_text
    assert captured_text[0].splitlines()[0] == ";".join(
        CALCULATOR_COLUMNS + ["component_label", "cabinet_label"]
    )
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


def test_child_calculator_uses_utf8_environment_and_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured.update(kwargs)
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "ПР 800×600×250", "stderr": ""},
        )()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_calculator_cli(PRICE_WORKBOOK, Path("input.csv"))

    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert captured["env"]["PYTHONUTF8"] == "1"
    assert captured["text"] is True
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "strict"
    assert result.stdout == "ПР 800×600×250"


def test_cli_utf8_reconfigure_prints_multiplication_sign_from_cp1251(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1251")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1251")
    monkeypatch.setattr(runner.sys, "stdout", stdout)
    monkeypatch.setattr(runner.sys, "stderr", stderr)

    runner.configure_cli_utf8()
    stdout.write("ПР 800×600×250 мм, металл")
    stdout.flush()

    assert stdout.encoding == "utf-8"
    assert stderr.encoding == "utf-8"
    assert stdout_bytes.getvalue().decode("utf-8") == "ПР 800×600×250 мм, металл"


def test_failed_calculator_report_preserves_full_output_and_all_red_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    stdout = calculator_stdout(
        "FAIL",
        red_flags=["- first exact flag", "- second exact flag"],
    )
    stderr = "Traceback (most recent call last):\n  exact frame\nExactError: boom\n"
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: runner.CalculatorProcessResult(
            returncode=1,
            stdout=stdout,
            stderr=stderr,
        ),
    )

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )
    report = runner.format_report(result)

    assert result.status == "FAIL"
    assert result.calculator_stdout == stdout
    assert result.calculator_stderr == stderr
    assert "calculator: - first exact flag" in result.red_flags
    assert "calculator: - second exact flag" in result.red_flags
    assert f"Calculator stdout:\n{stdout}" in report
    assert f"Calculator stderr:\n{stderr.rstrip()}" in report
    assert "Traceback (most recent call last):\n  exact frame" in report


def test_failed_calculator_report_marks_empty_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_json = write_json(tmp_path, valid_data())
    monkeypatch.setattr(
        runner,
        "run_calculator_cli",
        lambda price_workbook, input_csv: runner.CalculatorProcessResult(returncode=1),
    )

    result = runner.run_checked_price_calculator_from_completed_draft(
        completed_json,
        PRICE_WORKBOOK,
    )
    report = runner.format_report(result)

    assert "Calculator stdout:\nempty" in report
    assert "Calculator stderr:\nempty" in report


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
