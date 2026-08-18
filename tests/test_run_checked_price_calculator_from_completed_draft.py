import copy
import csv
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
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
    successful = runner.CheckedRunResult(
        completed_input_json=completed_json,
        price_workbook=PRICE_WORKBOOK,
        status="PASS",
    )
    monkeypatch.setattr(
        runner,
        "run_checked_price_calculator_from_completed_draft",
        lambda *args, **kwargs: successful,
    )

    assert (
        runner.main(
            [
                "--completed-input-json",
                str(completed_json),
                "--price-workbook",
                str(PRICE_WORKBOOK),
                "--pricing-profile",
                str(tmp_path / "profile.json"),
                "--expected-pricing-profile-sha256",
                "a" * 64,
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


def valid_pricing_profile_contract() -> dict[str, Any]:
    return {
        "schema_version": runner.PRICING_PROFILE_SCHEMA,
        "project_id": "2024/086",
        "status": runner.PRICING_PROFILE_STATUS,
        "decision_id": runner.PRICING_PROFILE_DECISION_ID,
        "authority": {
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "decision_source": "DIRECT_IGOR_INSTRUCTION_2026-08-14",
            "no_scope_expansion": True,
        },
        "immutable_state": {"immutable": True, "no_overwrite": True},
        "application_status": "NOT_APPLIED",
        "scope_expansion": False,
        "authoritative_inputs": [
            {
                "role": role,
                "path": path,
                "sha256": sha256,
                "schema_or_type": schema,
            }
            for role, path, sha256, schema in runner.EXPECTED_PROFILE_INPUTS
        ],
        "scope_partition": {
            "current_completed_technical_scope": {
                "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
                "pricing_profile_decision_status": "APPROVED_NOT_APPLIED",
                "pricing_calculation_status": "NOT_EXECUTED",
                "coverage": runner.EXPECTED_PROFILE_COVERAGE,
            },
            "reserved_case_level_formula_rules": {
                "formula_rule_status": ("HUMAN_APPROVED_CASE_LEVEL_RULE_NOT_APPLIED"),
                "technical_scope_status": (
                    "NO_CONFIRMED_POSITION_IN_CURRENT_COMPLETED_INPUT"
                ),
                "application_status": "NOT_APPLIED",
                "excluded_from_current_coverage": True,
            },
        },
        "pricing_grain": {
            "unit": "section-aware priceable cabinet position / composition variant",
            "cabinet_group_is_technical_mapping_scope_not_automatic_unit_pricing": True,
            "unit_price_before_multiplicity": True,
            "cabinet_base_once_per_physical_cabinet": True,
            "multiplicity_after_unit_price_rounding": True,
            "cross_section_quantity_aggregation_before_unit_calculation": False,
            "completed_input_is_technical_authority": True,
            "pdf_or_invoice_override_applied_human_decisions": False,
        },
        "rounding_policy": {
            "stage": "AFTER_FULL_UNIT_PRICE_FORMULA",
            "precision_kzt": 1,
            "mode": "ROUND_HALF_UP",
            "intermediate_rounding": False,
            "multiplicity_stage": "AFTER_UNIT_PRICE_ROUNDING",
            "invoice_manual_adjustment": False,
        },
        "external_pricing_tail": {
            "scope": "PROJECT_2024_086_INVOICE_519_ONLY",
            "formula": "*1.08765/1.16*1.2",
            "factor_1_08765_semantics": (
                "case-specific Igor correction instead of a separate general 1.2 mm "
                "metal thickness coefficient"
            ),
            "divide_1_16_semantics": ("remove VAT because Invoice 519 is without VAT"),
            "final_factor_1_2_semantics": "buyer representative bonus",
            "pre_tail_factors": ["1.25", "1.15"],
            "global_default": False,
            "unknown_other_project_factor_requires_igor_decision": True,
            "must_not_mix_with_internal_material_factor": True,
        },
        "safety_flags": {
            "pricing_profile_decision_recorded": True,
            "pricing_profile_applied": False,
            "current_scope_pricing_calculated": False,
            "reserved_formula_rules_applied": False,
            "calculator_run_authorized": False,
            "checked_calculator_run_authorized": False,
            "quote_generation_authorized": False,
            "price_approval_for_client": False,
            "lead_time_approved": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
            "scope_expansion": False,
        },
        "non_approvals": {
            "project_total_approved": False,
            "remaining_current_position_prices_approved": False,
            "reserved_family_prices_approved": False,
            "lead_time_approved": False,
            "final_invoice_or_quote_approved": False,
            "client_send_authorized": False,
        },
    }


def additive_pricing_profile_contract(completed_path: Path) -> dict[str, Any]:
    profile = valid_pricing_profile_contract()
    completed_sha = "a" * 64
    profile["additive_successor"] = {
        "contract": runner.ADDITIVE_PROFILE_CONTRACT,
        "project_id": "2024/086",
        "parent": {
            "path": str(runner.PRICING_PROFILE_PATH),
            "sha256": runner.PRICING_PROFILE_SHA256,
        },
        "completed_input_successor": {
            "path": str(completed_path),
            "sha256": completed_sha,
            "contract": runner.ADDITIVE_COMPLETED_CONTRACT,
        },
        "direct_human_decision_inputs": copy.deepcopy(
            runner.ADDITIVE_DECISION_BINDINGS
        ),
        "append_only": True,
        "scope_expansion": False,
        "pricing_calculation_executed": False,
        "approved_shu_t1_unit_price_kzt": 53763,
        "approved_shu_t1_exact_scope_total_kzt": 215052,
        "candidate_project_total_kzt": 11841516,
        "candidate_project_total_status": runner.PROFILE_DRAFT_STATUS,
        "price_approval_status": runner.PROFILE_APPROVAL_STATUS,
    }
    profile["authoritative_inputs"].extend(
        [
            {
                "role": "completed_technical_input_additive_successor",
                "path": str(completed_path),
                "sha256": completed_sha,
                "schema_or_type": "price_calculator_input_draft.v0.2",
                "purpose": "exact 15-group/112-row additive technical authority",
            },
            *copy.deepcopy(runner.ADDITIVE_DECISION_BINDINGS),
        ]
    )
    profile["scope_partition"]["current_completed_technical_scope"]["coverage"] = (
        copy.deepcopy(runner.ADDITIVE_PROFILE_COVERAGE)
    )
    return profile


def test_additive_profile_exact_envelope_passes_and_drifts_fail(
    tmp_path: Path,
) -> None:
    profile = additive_pricing_profile_contract(tmp_path / "completed-successor.json")
    assert runner.validate_pricing_profile_contract(profile, profile_result(tmp_path))
    mutations = [
        lambda value: value["additive_successor"].__setitem__(
            "candidate_project_total_kzt", 11841515
        ),
        lambda value: value["additive_successor"]["direct_human_decision_inputs"][
            2
        ].__setitem__("sha256", "0" * 64),
        lambda value: value["additive_successor"].__setitem__(
            "pricing_calculation_executed", True
        ),
        lambda value: value["scope_partition"]["current_completed_technical_scope"][
            "coverage"
        ].__setitem__("physical_cabinets", 136),
    ]
    for mutation in mutations:
        changed = copy.deepcopy(profile)
        mutation(changed)
        result = profile_result(tmp_path)
        assert not runner.validate_pricing_profile_contract(changed, result)
        assert result.red_flags


def profile_result(tmp_path: Path) -> Any:
    return runner.CheckedRunResult(
        completed_input_json=tmp_path / "completed.json",
        price_workbook=tmp_path / "prices.xlsx",
    )


def test_exact_pricing_profile_contract_passes_and_root_drifts_fail(
    tmp_path: Path,
) -> None:
    profile = valid_pricing_profile_contract()
    assert runner.validate_pricing_profile_contract(profile, profile_result(tmp_path))

    mutations: tuple[tuple[str, Any], ...] = (
        ("schema_version", "wrong"),
        ("project_id", "other"),
        ("status", "wrong"),
        ("decision_id", "wrong"),
        ("authority", {"authority": "OTHER"}),
        ("immutable_state", {"immutable": False, "no_overwrite": True}),
        ("application_status", "APPLIED"),
        ("scope_expansion", True),
        ("authoritative_inputs", []),
    )
    for key, value in mutations:
        changed = copy.deepcopy(profile)
        changed[key] = value
        result = profile_result(tmp_path)
        assert not runner.validate_pricing_profile_contract(changed, result), key
        assert result.red_flags


def test_pricing_profile_policy_is_fail_closed_for_each_boundary(
    tmp_path: Path,
) -> None:
    profile = valid_pricing_profile_contract()
    mutations: tuple[tuple[str, Any], ...] = (
        ("scope_partition", {}),
        ("pricing_grain", {}),
        ("rounding_policy", {}),
        ("external_pricing_tail", {}),
        ("safety_flags", {}),
        ("non_approvals", {}),
    )
    assert all(
        runner.validate_profile_policy_contract(profile, profile_result(tmp_path))
    )
    for key, value in mutations:
        changed = copy.deepcopy(profile)
        changed[key] = value
        result = profile_result(tmp_path)
        assert not all(runner.validate_profile_policy_contract(changed, result))
        assert result.red_flags


def test_pricing_profile_loader_enforces_path_sha_utf8_json_and_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "profile.json"
    payload = json.dumps(valid_pricing_profile_contract()).encode("utf-8")
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(runner, "PRICING_PROFILE_PATH", path)
    monkeypatch.setattr(runner, "PRICING_PROFILE_SHA256", digest)

    result = profile_result(tmp_path)
    assert runner.load_pricing_profile(result, path, digest) is not None
    assert runner.load_pricing_profile(result, tmp_path / "other.json", digest) is None
    assert runner.load_pricing_profile(result, path, "0" * 64) is None

    path.write_text("{}", encoding="utf-8")
    assert runner.load_pricing_profile(profile_result(tmp_path), path, digest) is None
    duplicate = b'{"schema_version":"one","schema_version":"two"}'
    path.write_bytes(duplicate)
    duplicate_sha = hashlib.sha256(duplicate).hexdigest()
    monkeypatch.setattr(runner, "PRICING_PROFILE_SHA256", duplicate_sha)
    assert (
        runner.load_pricing_profile(
            profile_result(tmp_path),
            path,
            duplicate_sha,
        )
        is None
    )
    malformed = b"{"
    path.write_bytes(malformed)
    malformed_sha = hashlib.sha256(malformed).hexdigest()
    monkeypatch.setattr(runner, "PRICING_PROFILE_SHA256", malformed_sha)
    assert (
        runner.load_pricing_profile(profile_result(tmp_path), path, malformed_sha)
        is None
    )
    invalid_utf8 = b"\xff"
    path.write_bytes(invalid_utf8)
    invalid_utf8_sha = hashlib.sha256(invalid_utf8).hexdigest()
    monkeypatch.setattr(runner, "PRICING_PROFILE_SHA256", invalid_utf8_sha)
    assert (
        runner.load_pricing_profile(
            profile_result(tmp_path),
            path,
            invalid_utf8_sha,
        )
        is None
    )
    array_payload = b"[]"
    path.write_bytes(array_payload)
    array_sha = hashlib.sha256(array_payload).hexdigest()
    monkeypatch.setattr(runner, "PRICING_PROFILE_SHA256", array_sha)
    assert (
        runner.load_pricing_profile(profile_result(tmp_path), path, array_sha) is None
    )
    monkeypatch.setattr(runner, "PRICING_PROFILE_PATH", tmp_path)
    assert (
        runner.load_pricing_profile(profile_result(tmp_path), tmp_path, array_sha)
        is None
    )


def valid_formula_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    current = {
        "modular_formula_family": {
            "scope_cabinet_group_ids": [
                *(f"CABINET-GROUP-{index:03d}" for index in range(1, 10)),
                "CABINET-GROUP-014",
            ],
            "material_factor": "1.2",
            "approved_formula": (
                "ROUND_HALF_UP((X + I + G*1.2 + H)*1.25*1.15*1.08765/1.16*"
                "1.2, 1 KZT)"
            ),
            "symbols": {
                "X": "exact cabinet base for the position",
                "I": (
                    "approved additional cabinet cost; numeric 0 when no approved I "
                    "exists"
                ),
                "G": "material total for one cabinet",
                "H": "work total for one cabinet",
            },
            "cabinet_bases_kzt": {
                "CAB-KURN-038-24": 12557,
                "CAB-KRN-18": 7678,
                "CAB-KRN-12": 6936,
                "CAB-KRN-24": 7985,
            },
        },
        "pr_approved_calculated_unit_prices": [
            {
                "sections": ["9", "13"],
                "G_material_kzt": 14850,
                "H_work_kzt": 3024,
                "X_cabinet_base_kzt": 12557,
                "I_additional_cabinet_cost_kzt": 0,
                "raw_unit_price_kzt": "54023.13012607758620689655173",
                "approved_unit_price_kzt": 54023,
                "decision_status": "APPROVED_NOT_APPLIED",
                "invoice_comparator_kzt": 54019,
                "invoice_override_used": False,
            },
            {
                "sections": ["11", "15"],
                "G_material_kzt": 17050,
                "H_work_kzt": 3564,
                "X_cabinet_base_kzt": 12557,
                "I_additional_cabinet_cost_kzt": 0,
                "raw_unit_price_kzt": "59166.49570797413793103448277",
                "approved_unit_price_kzt": 59166,
                "decision_status": "APPROVED_NOT_APPLIED",
                "invoice_comparator_kzt": 59163,
                "invoice_override_used": False,
            },
        ],
    }
    sche_prices = []
    for product, apartments, raw, approved in (
        ("ЩЭ-3кв", 3, "80412.80082866379310344827588", 80413),
        ("ЩЭ-4кв", 4, "96269.89396228448275862068967", 96270),
        ("ЩЭ-5кв", 5, "112126.9870959051724137931035", 112127),
        ("ЩЭ-6кв", 6, "127984.0802295258620689655173", 127984),
    ):
        sche_prices.append(
            {
                "product_name": product,
                "apartment_count": apartments,
                "G_material_kzt": 3200 * apartments,
                "H_work_kzt": 864 * apartments,
                "apartment_component_kzt": 5100 * apartments,
                "raw_unit_price_kzt": raw,
                "approved_unit_price_kzt": approved,
                "decision_status": "APPROVED_NOT_APPLIED",
            }
        )
    current["sche_formula_family"] = {
        "scope_products": list(runner.EXPECTED_SCHE_APARTMENTS),
        "cabinet_code": runner.CUSTOM_SCHE_CABINET_CODE,
        "cabinet_base_kzt": 20305,
        "cabinet_base_raw_kzt": "20304.41634565600",
        "cabinet_base_rounding": "ROUND_UP_TO_1_KZT",
        "physical_identity": {
            "dimensions_mm": [900, 900, 120],
            "metal_thickness_mm": "1.2",
        },
        "prohibited_cached_base_kzt": 18762,
        "material_factor": "1.2",
        "apartment_component_kzt_per_apartment": 5100,
        "apartment_component_formula": "850*6",
        "approved_formula": (
            "ROUND_HALF_UP((20305 + G*1.2 + H + 5100*apartment_count)*1.25*"
            "1.15*1.08765/1.16*1.2, 1 KZT)"
        ),
        "existing_workbook_baseline_formula": ("J2+(G2+H2+(850*6*I2))*1.25*1.15"),
        "case_profile_decision_is_not_inferred_from_workbook_baseline": True,
        "approved_calculated_unit_prices": sche_prices,
    }
    reserved = []
    for family in runner.EXPECTED_RESERVED_FAMILIES:
        common = {
            "family": family,
            "formula_rule_status": "HUMAN_APPROVED_CASE_LEVEL_RULE_NOT_APPLIED",
            "technical_scope_status": (
                "NO_CONFIRMED_POSITION_IN_CURRENT_COMPLETED_INPUT"
            ),
            "application_status": "NOT_APPLIED",
        }
        if family == "ВРУ-ВА":
            common.update(
                {
                    "material_factor": "1.2",
                    "work_formula_cell": "ВРУ-ВА!H2",
                    "work_formula": "SUM(component work)+3000",
                    "fixed_work_adjustment_kzt": 3000,
                    "fixed_work_adjustment_semantics": (
                        "unlabelled fixed work adjustment"
                    ),
                    "approved_case_formula": (
                        "ROUND_HALF_UP((X + I + G*1.2 + H)*1.25*1.15*"
                        "1.08765/1.16*1.2, 1 KZT)"
                    ),
                }
            )
        else:
            common.update(
                {
                    "material_factor": "1.05",
                    "workbook_formula_cell": f"{family}!H2",
                    "workbook_formula": "(G2+E2*1.05+F2)*1.25*1.15",
                    "approved_case_formula": (
                        "ROUND_HALF_UP((X + I + G*1.05 + H)*1.25*1.15*"
                        "1.08765/1.16*1.2, 1 KZT)"
                    ),
                }
            )
        reserved.append(common)
    return current, {"reserved_case_level_formula_rules": reserved}


def test_formula_profile_validates_current_and_reserved_exactly(
    tmp_path: Path,
) -> None:
    current, profile = valid_formula_profile()
    assert runner.validate_profile_formula_contract(
        current,
        profile,
        profile_result(tmp_path),
    )

    for target, key, value in (
        (current, "modular_formula_family", {}),
        (current, "sche_formula_family", {}),
        (current, "pr_approved_calculated_unit_prices", []),
        (profile, "reserved_case_level_formula_rules", []),
    ):
        changed_current = copy.deepcopy(current)
        changed_profile = copy.deepcopy(profile)
        changed_target = changed_current if target is current else changed_profile
        changed_target[key] = value
        assert not runner.validate_profile_formula_contract(
            changed_current,
            changed_profile,
            profile_result(tmp_path),
        )


def test_formula_profile_rejects_sche_apartment_and_reserved_rule_drift(
    tmp_path: Path,
) -> None:
    current, profile = valid_formula_profile()
    current["sche_formula_family"]["approved_calculated_unit_prices"][0][
        "apartment_count"
    ] = 4
    assert not runner.validate_profile_formula_contract(
        current,
        profile,
        profile_result(tmp_path),
    )


def synthetic_profile_inventory() -> tuple[dict[str, Any], dict[str, Any]]:
    products = runner.EXPECTED_PROFILE_PRODUCTS
    codes = [
        "CAB-KURN-038-24",
        "CAB-KRN-18",
        *("CAB-KRN-12" for _ in range(6)),
        "CAB-KRN-24",
        *(runner.CUSTOM_SCHE_CABINET_CODE for _ in range(4)),
        "CAB-KRN-12",
    ]
    bases = {
        "CAB-KURN-038-24": 12557,
        "CAB-KRN-18": 7678,
        "CAB-KRN-12": 6936,
        "CAB-KRN-24": 7985,
        runner.CUSTOM_SCHE_CABINET_CODE: 20305,
    }
    completed_groups: list[dict[str, Any]] = []
    profile_groups: list[dict[str, Any]] = []
    for index, (product, code) in enumerate(zip(products, codes, strict=True)):
        group_id = f"CABINET-GROUP-{index + 1:03d}"
        completed_groups.append(
            {
                "cabinet_group_id": group_id,
                "source_cabinet_template": product,
                "product_name": product,
                "cabinet_code": code,
                "cabinet_label": f"cabinet {index + 1}",
                "row_draft_ids": [],
            }
        )
        profile_groups.append(
            {
                "cabinet_group_id": group_id,
                "completed_input_json_path": f"$.cabinet_groups[{index}]",
                "source_cabinet_template": product,
                "product_name": product,
                "cabinet_code": code,
                "cabinet_base_kzt": bases[code],
                "approved_additional_cabinet_cost_kzt": 0,
                "formula_family": (
                    "CURRENT_SCHE_CASE_PROFILE"
                    if code == runner.CUSTOM_SCHE_CABINET_CODE
                    else "CURRENT_MODULAR_CASE_PROFILE"
                ),
                "row_draft_ids": [],
            }
        )

    rows: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    derived: dict[str, dict[str, Any]] = {}
    next_row = 1
    for position_index in range(51):
        group_index = position_index % 14
        group = completed_groups[group_index]
        profile_group = profile_groups[group_index]
        row_count = 3 if position_index < 7 else 2
        variant = position_index if position_index < 7 else 7 + position_index % 4
        selected: list[dict[str, Any]] = []
        row_ids: list[str] = []
        row_paths: list[str] = []
        for component_index in range(row_count):
            row_id = f"ROW-DRAFT-{next_row:04d}"
            values = {
                "product_name": group["product_name"],
                "cabinet_code": group["cabinet_code"],
                "consumables_factor": 1.2,
                "component_code": f"COMP-{variant}-{component_index}",
                "component_qty": component_index + 1,
                "install_type": f"install-{component_index}",
            }
            row = {
                "row_id": row_id,
                "cabinet_group_id": group["cabinet_group_id"],
                "component_label": f"component {variant}-{component_index}",
                "calculator_values": values,
            }
            rows.append(row)
            selected.append(row)
            row_ids.append(row_id)
            row_paths.append(f"$.calculator_input_format.row_drafts[{next_row - 1}]")
            group["row_draft_ids"].append(row_id)
            profile_group["row_draft_ids"].append(row_id)
            next_row += 1
        fingerprint = runner.canonical_composition_fingerprint(selected)
        position_id = f"PRICE-POSITION-{position_index + 1:03d}"
        source_id = f"TFE-{position_index + 1:03d}"
        approved = (
            group["product_name"] == "ПР"
            or group["product_name"] in runner.EXPECTED_SCHE_APARTMENTS
        )
        positions.append(
            {
                "pricing_position_id": position_id,
                "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
                "section": str(9 + position_index // 10),
                "discipline": "ЭОМ",
                "source_document": {
                    "document_id": f"Секция {9 + position_index // 10}_ЭОМ.pdf",
                    "sha256": "a" * 64,
                },
                "source_position_id": source_id,
                "source_position_json_path": f"$.positions[{position_index}]",
                "cabinet_group_id": group["cabinet_group_id"],
                "cabinet_group_json_path": f"$.cabinet_groups[{group_index}]",
                "product_name": group["product_name"],
                "cabinet_code": group["cabinet_code"],
                "row_draft_ids": row_ids,
                "row_draft_json_paths": row_paths,
                "composition_fingerprint_sha256": fingerprint,
                "physical_multiplicity": 83 if position_index == 0 else 1,
                "unit_pricing_before_multiplicity": True,
                "invoice_comparator": {"manual_override_used": False},
                "pricing_calculation_status": "NOT_EXECUTED",
                "approved_unit_price_kzt": 1 if approved else None,
                "approved_unit_price_decision_status": (
                    "APPROVED_NOT_APPLIED"
                    if approved
                    else "NOT_CALCULATED_NOT_APPROVED"
                ),
            }
        )
        record = derived.setdefault(
            fingerprint,
            {
                "fingerprint_sha256": fingerprint,
                "canonicalization": (
                    "SHA256 UTF-8 canonical JSON of sorted "
                    "component_code/component_qty/install_type tuples"
                ),
                "components": [
                    {
                        "component_code": row["calculator_values"]["component_code"],
                        "component_qty": row["calculator_values"]["component_qty"],
                        "install_type": row["calculator_values"]["install_type"],
                    }
                    for row in selected
                ],
                "source_position_ids": [],
                "pricing_position_ids": [],
            },
        )
        record["source_position_ids"].append(source_id)
        record["pricing_position_ids"].append(position_id)
    completed = {
        "schema_version": "price_calculator_input_draft.v0.2",
        "calculator_input_format": {"row_drafts": rows},
        "cabinet_groups": completed_groups,
    }
    profile = {
        "current_completed_technical_scope": {
            "coverage": dict(runner.EXPECTED_PROFILE_COVERAGE),
            "products": products,
            "cabinet_groups": profile_groups,
            "pricing_positions": positions,
            "composition_fingerprints": [derived[key] for key in sorted(derived)],
        }
    }
    return completed, profile


def synthetic_additive_profile_inventory(
    completed_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    completed, profile = synthetic_profile_inventory()
    completed["source"] = {
        "additive_completed_input_successor": {
            "contract": runner.ADDITIVE_COMPLETED_CONTRACT,
            "direct_human_decision_inputs": copy.deepcopy(
                runner.ADDITIVE_DECISION_BINDINGS
            ),
            "scope_expansion": False,
        }
    }
    group = {
        "cabinet_group_id": "CABINET-GROUP-015",
        "source_cabinet_template": "ЩРН-12",
        "product_name": "ШУ-Т1",
        "cabinet_code": "CAB-KRN-12",
        "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
        "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
    }
    profile_group = {
        "cabinet_group_id": "CABINET-GROUP-015",
        "completed_input_json_path": "$.cabinet_groups[14]",
        "source_cabinet_template": "ЩРН-12",
        "product_name": "ШУ-Т1",
        "cabinet_code": "CAB-KRN-12",
        "cabinet_base_kzt": 6936,
        "approved_additional_cabinet_cost_kzt": 0,
        "formula_family": "CURRENT_MODULAR_CASE_PROFILE",
        "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
    }
    values = [
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-RT-820",
            "component_qty": 1,
            "install_type": "temperature_relay_din_2mod",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
            "component_qty": 1,
            "install_type": "diff_1p_n",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-VA47-29-2P",
            "component_qty": 1,
            "install_type": "modular_2p",
        },
    ]
    labels = [
        "Реле температуры RT-820 EKF PROxima с внешним датчиком",
        "АД12 Basic АВДТ 2P C16/30мА 4.5kA",
        "Автоматический выключатель ВА47-29 BASIC 2P C10 4.5kA",
    ]
    new_rows = [
        {
            "row_id": f"ROW-DRAFT-{index:04d}",
            "cabinet_group_id": "CABINET-GROUP-015",
            "component_label": label,
            "calculator_values": row_values,
        }
        for index, row_values, label in zip(
            range(110, 113), values, labels, strict=True
        )
    ]
    completed["cabinet_groups"].append(group)
    completed["calculator_input_format"]["row_drafts"].extend(new_rows)
    current = profile["current_completed_technical_scope"]
    current["coverage"] = copy.deepcopy(runner.ADDITIVE_PROFILE_COVERAGE)
    current["products"] = list(runner.ADDITIVE_PROFILE_PRODUCTS)
    current["cabinet_groups"].append(profile_group)
    position_ids = [f"PRICE-POSITION-{index:03d}" for index in range(52, 56)]
    source_ids = ["TFE-006", "TFE-029", "TFE-052", "TFE-074"]
    source_indexes = [5, 28, 51, 73]
    sections = ["9", "11", "13", "15"]
    documents = [
        "b03d2d87f8ce6a8def89eed3e796dd5daaad1ba9ae55e07c5d643acfaa417e46",
        "a00829db7ca196995a53b8313106e90037990a5284cef8fa7dcda92cdc24137e",
        "02dde3268d3ceef4d4f0ad6e616f44bbfe37fe8f66a39d4b7fabb4a04b0aa6c2",
        "4ca1bd6f27d6474e0fbf2b56d67ba8100016d4350556e704a91fc880ad0a62dd",
    ]
    new_positions = []
    for position_id, source_id, source_index, section, document_sha in zip(
        position_ids, source_ids, source_indexes, sections, documents, strict=True
    ):
        new_positions.append(
            {
                "pricing_position_id": position_id,
                "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
                "section": section,
                "discipline": "ЭОМ",
                "source_document": {
                    "document_id": f"Секция {section}_ЭОМ.pdf",
                    "sha256": document_sha,
                },
                "source_position_id": source_id,
                "source_position_json_path": f"$.positions[{source_index}]",
                "cabinet_group_id": "CABINET-GROUP-015",
                "cabinet_group_json_path": "$.cabinet_groups[14]",
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "row_draft_ids": [
                    "ROW-DRAFT-0110",
                    "ROW-DRAFT-0111",
                    "ROW-DRAFT-0112",
                ],
                "row_draft_json_paths": [
                    "$.calculator_input_format.row_drafts[109]",
                    "$.calculator_input_format.row_drafts[110]",
                    "$.calculator_input_format.row_drafts[111]",
                ],
                "composition_fingerprint_sha256": runner.SHU_T1_FINGERPRINT,
                "physical_multiplicity": 1,
                "unit_pricing_before_multiplicity": True,
                "invoice_comparator": {"manual_override_used": False},
                "pricing_calculation_status": "NOT_EXECUTED",
                "approved_unit_price_kzt": 53763,
                "approved_unit_price_decision_status": "APPROVED_NOT_APPLIED",
            }
        )
    current["pricing_positions"].extend(new_positions)
    current["composition_fingerprints"].append(
        {
            "fingerprint_sha256": runner.SHU_T1_FINGERPRINT,
            "canonicalization": (
                "SHA256 UTF-8 canonical JSON of sorted "
                "component_code/component_qty/install_type tuples"
            ),
            "components": sorted(
                [
                    {
                        "component_code": value["component_code"],
                        "component_qty": value["component_qty"],
                        "install_type": value["install_type"],
                    }
                    for value in values
                ],
                key=lambda item: (
                    item["component_code"],
                    item["component_qty"],
                    item["install_type"],
                ),
            ),
            "source_position_ids": source_ids,
            "pricing_position_ids": position_ids,
        }
    )
    profile["additive_successor"] = additive_pricing_profile_contract(completed_path)[
        "additive_successor"
    ]
    return completed, profile


def test_additive_inventory_builds_15_groups_55_positions_137_cabinets_12_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed_path = tmp_path / "completed-successor.json"
    completed, profile = synthetic_additive_profile_inventory(completed_path)
    result = runner.CheckedRunResult(
        completed_input_json=completed_path,
        price_workbook=tmp_path / "prices.xlsx",
    )
    monkeypatch.setattr(
        runner, "validate_profile_formula_contract", lambda current, root, output: True
    )
    positions = runner.validate_and_build_profile_positions(completed, profile, result)
    assert len(positions) == 55
    assert sum(position.physical_multiplicity for position in positions) == 137
    assert (
        len({position.composition_fingerprint_sha256 for position in positions}) == 12
    )
    assert [position.product_name for position in positions[-4:]] == ["ШУ-Т1"] * 4
    assert not result.red_flags


def test_additive_inventory_rejects_missing_binding_and_section_aggregation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner, "validate_profile_formula_contract", lambda current, root, output: True
    )
    completed_path = tmp_path / "completed-successor.json"
    completed, profile = synthetic_additive_profile_inventory(completed_path)
    completed["source"]["additive_completed_input_successor"][
        "direct_human_decision_inputs"
    ].pop()
    result = runner.CheckedRunResult(completed_path, tmp_path / "prices.xlsx")
    assert not runner.validate_and_build_profile_positions(completed, profile, result)

    completed, profile = synthetic_additive_profile_inventory(completed_path)
    profile["current_completed_technical_scope"]["pricing_positions"][-4][
        "physical_multiplicity"
    ] = 4
    del profile["current_completed_technical_scope"]["pricing_positions"][-3:]
    result = runner.CheckedRunResult(completed_path, tmp_path / "prices.xlsx")
    assert not runner.validate_and_build_profile_positions(completed, profile, result)


def test_exact_inventory_builds_14_groups_51_positions_133_cabinets_11_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed, profile = synthetic_profile_inventory()
    monkeypatch.setattr(
        runner,
        "validate_profile_formula_contract",
        lambda current, root, result: True,
    )
    result = profile_result(tmp_path)
    positions = runner.validate_and_build_profile_positions(completed, profile, result)
    assert len(positions) == 51
    assert sum(position.physical_multiplicity for position in positions) == 133
    assert (
        len({position.composition_fingerprint_sha256 for position in positions}) == 11
    )
    assert not result.red_flags


def test_inventory_rejects_position_row_fingerprint_multiplicity_and_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "validate_profile_formula_contract",
        lambda current, root, result: True,
    )

    def fails(mutator: Any) -> None:
        completed, profile = synthetic_profile_inventory()
        mutator(completed, profile)
        result = profile_result(tmp_path)
        assert not runner.validate_and_build_profile_positions(
            completed,
            profile,
            result,
        )
        assert result.red_flags

    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ].pop()
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ].append(
            copy.deepcopy(
                profile["current_completed_technical_scope"]["pricing_positions"][0]
            )
        )
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ].reverse()
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ][0]["row_draft_ids"].reverse()
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ][0].__setitem__("composition_fingerprint_sha256", "0" * 64)
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "pricing_positions"
        ][0].__setitem__("physical_multiplicity", 82)
    )
    for key, value in (
        ("section", "wrong"),
        ("discipline", "wrong"),
        ("product_name", "wrong"),
        ("cabinet_code", "wrong"),
    ):
        fails(
            lambda completed, profile, key=key, value=value: profile[
                "current_completed_technical_scope"
            ]["pricing_positions"][0].__setitem__(key, value)
        )


def test_inventory_rejects_group_row_and_coverage_expansion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "validate_profile_formula_contract",
        lambda current, root, result: True,
    )

    def fails(mutator: Any) -> None:
        completed, profile = synthetic_profile_inventory()
        mutator(completed, profile)
        result = profile_result(tmp_path)
        assert not runner.validate_and_build_profile_positions(
            completed,
            profile,
            result,
        )

    fails(
        lambda completed, profile: completed["calculator_input_format"][
            "row_drafts"
        ].pop()
    )
    fails(lambda completed, profile: completed["cabinet_groups"].pop())
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "cabinet_groups"
        ][0].__setitem__("cabinet_base_kzt", 18762)
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "composition_fingerprints"
        ].pop()
    )
    fails(
        lambda completed, profile: profile["current_completed_technical_scope"][
            "coverage"
        ].__setitem__("section_aware_pricing_positions", 52)
    )


def profile_bound_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, dict[str, Any], Path, Path]:
    profile_path = tmp_path / "profile.json"
    completed = tmp_path / "completed.json"
    prices = tmp_path / "prices.xlsx"
    metal = tmp_path / "metal.xlsx"
    for path, content in (
        (profile_path, b"profile"),
        (completed, b"completed"),
        (prices, b"prices"),
        (metal, b"metal"),
    ):
        path.write_bytes(content)
    monkeypatch.setattr(runner, "PRICING_PROFILE_PATH", profile_path)
    monkeypatch.setattr(
        runner,
        "PRICING_PROFILE_SHA256",
        hashlib.sha256(b"profile").hexdigest(),
    )
    profile = {
        "authoritative_inputs": [
            {
                "role": role,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for role, path in (
                ("completed_technical_input", completed),
                ("main_price_workbook", prices),
                ("custom_sche_metal_workbook", metal),
            )
        ]
    }
    result = runner.CheckedRunResult(
        completed_input_json=completed,
        price_workbook=prices,
    )
    return result, profile, profile_path, metal


def test_profile_inputs_have_initial_and_repeatable_toctou_sha_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    snapshots = runner.capture_profile_input_shas(
        result,
        profile,
        profile_path,
        metal,
    )
    assert snapshots is not None
    assert runner.recheck_profile_input_shas(result, snapshots, "pre-calculation")
    assert set(result.input_sha_provenance) == {
        "pricing_profile",
        "completed_technical_input",
        "main_price_workbook",
        "custom_sche_metal_workbook",
    }

    result.completed_input_json.write_bytes(b"drift")
    assert not runner.recheck_profile_input_shas(result, snapshots, "final")
    assert any("drift" in flag for flag in result.red_flags)


def test_additive_profile_rechecks_all_three_human_decision_shas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    completed_input = profile["authoritative_inputs"][0]
    completed_input["role"] = "completed_technical_input_additive_successor"
    decision_paths = [tmp_path / f"decision-{index}.json" for index in range(1, 4)]
    bindings = []
    for index, path in enumerate(decision_paths, start=1):
        path.write_bytes(f"decision-{index}".encode())
        binding = {
            "role": f"decision_{index}",
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        bindings.append(binding)
        profile["authoritative_inputs"].append(copy.deepcopy(binding))
    profile["additive_successor"] = {}
    monkeypatch.setattr(runner, "ADDITIVE_DECISION_BINDINGS", bindings)

    snapshots = runner.capture_profile_input_shas(
        result,
        profile,
        profile_path,
        metal,
    )
    assert snapshots is not None
    assert {"decision_1", "decision_2", "decision_3"} <= set(snapshots)
    decision_paths[1].write_bytes(b"drift")
    assert not runner.recheck_profile_input_shas(result, snapshots, "final")
    assert any("decision_2" in flag for flag in result.red_flags)


def test_profile_input_sha_checks_control_path_mismatch_missing_and_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    assert (
        runner.capture_profile_input_shas(
            result,
            profile,
            profile_path,
            None,
        )
        is None
    )
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    result.completed_input_json = tmp_path / "wrong.json"
    assert (
        runner.capture_profile_input_shas(
            result,
            profile,
            profile_path,
            metal,
        )
        is None
    )
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    result.price_workbook.unlink()
    assert (
        runner.capture_profile_input_shas(
            result,
            profile,
            profile_path,
            metal,
        )
        is None
    )
    result, profile, profile_path, metal = profile_bound_files(tmp_path, monkeypatch)
    snapshots = runner.capture_profile_input_shas(
        result,
        profile,
        profile_path,
        metal,
    )
    assert snapshots is not None
    metal.unlink()
    assert not runner.recheck_profile_input_shas(result, snapshots, "final")
    assert any("could not be read" in flag for flag in result.red_flags)


def sample_profile_position(index: int = 1) -> Any:
    return runner.ProfilePositionInput(
        pricing_position_id=f"PRICE-POSITION-{index:03d}",
        section="9",
        discipline="ЭОМ",
        source_document={"document_id": "Секция 9_ЭОМ.pdf", "sha256": "a" * 64},
        cabinet_group_id="CABINET-GROUP-001",
        product_name="ПР",
        cabinet_code="CAB-KURN-038-24",
        formula_family="CURRENT_MODULAR_CASE_PROFILE",
        row_draft_ids=["ROW-DRAFT-0001"],
        rows=[
            {
                "product_name": "ПР",
                "cabinet_code": "CAB-KURN-038-24",
                "consumables_factor": 1.2,
                "component_code": "EKF-VA47-29-1P",
                "component_qty": 1,
                "install_type": "modular_1p",
                "component_label": "component",
                "cabinet_label": "cabinet",
            }
        ],
        composition_fingerprint_sha256="a" * 64,
        physical_multiplicity=1,
        apartment_count=None,
        approved_unit_price_kzt=54023,
        cabinet_base_kzt=12557,
        additional_cabinet_cost_kzt=0,
    )


def test_execute_profile_position_calculates_anchor_and_expands_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = profile_result(tmp_path)

    def fake_execute(*args: Any, **kwargs: Any) -> bool:
        result.item_summaries.append(
            runner.ItemCalculationSummary(
                product_name="ПР",
                input_rows_count=1,
                cabinet="CAB-KURN-038-24 / cabinet",
                cabinet_price="12 557",
                component_material_total="14 850",
                work_total="3 024",
                additional_materials_total="2 970",
                total_preliminary_price=1,
            )
        )
        return True

    monkeypatch.setattr(runner, "execute_calculator", fake_execute)
    calculator = runner.load_calculator_module()
    assert runner.execute_profile_position(
        result,
        sample_profile_position(),
        tmp_path / "bridge.csv",
        calculator,
        None,
    )
    calculation = result.position_calculations[0]
    assert calculation.rounded_unit_price_kzt == 54023
    assert calculation.rounding_stage == "AFTER_FULL_UNIT_PRICE_FORMULA"
    assert calculation.rounding_mode == "ROUND_HALF_UP"
    assert result.group_summaries == {"CABINET-GROUP-001": 54023}


def test_execute_shu_t1_profile_position_calculates_exact_53763_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = profile_result(tmp_path)
    position = runner.ProfilePositionInput(
        pricing_position_id="PRICE-POSITION-052",
        section="9",
        discipline="ЭОМ",
        source_document={"document_id": "Секция 9_ЭОМ.pdf", "sha256": "a" * 64},
        cabinet_group_id="CABINET-GROUP-015",
        product_name="ШУ-Т1",
        cabinet_code="CAB-KRN-12",
        formula_family="CURRENT_MODULAR_CASE_PROFILE",
        row_draft_ids=["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
        rows=[
            {
                "product_name": "ШУ-Т1",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_code": "EKF-RT-820",
                "component_qty": 1,
                "install_type": "temperature_relay_din_2mod",
                "component_label": (
                    "Реле температуры RT-820 EKF PROxima с внешним датчиком"
                ),
                "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
            },
            {},
            {},
        ],
        composition_fingerprint_sha256=runner.SHU_T1_FINGERPRINT,
        physical_multiplicity=1,
        apartment_count=None,
        approved_unit_price_kzt=53763,
        cabinet_base_kzt=6936,
        additional_cabinet_cost_kzt=0,
    )

    def fake_execute(*args: Any, **kwargs: Any) -> bool:
        result.item_summaries.append(
            runner.ItemCalculationSummary(
                product_name="ШУ-Т1",
                input_rows_count=3,
                cabinet="CAB-KRN-12 / cabinet",
                cabinet_price="6 936",
                component_material_total="20 450",
                work_total="1 764",
                additional_materials_total="4 090",
                total_preliminary_price=47783,
            )
        )
        return True

    monkeypatch.setattr(runner, "execute_calculator", fake_execute)
    calculator = runner.load_calculator_module()
    assert runner.execute_profile_position(
        result, position, tmp_path / "bridge.csv", calculator, None
    )
    calculation = result.position_calculations[0]
    assert calculation.unrounded_unit_price_kzt == "53762.72702586206896551724138"
    assert calculation.rounded_unit_price_kzt == 53763
    assert calculation.position_total_kzt == 53763


def test_execute_profile_position_rejects_failed_fields_formula_and_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = profile_result(tmp_path)
    monkeypatch.setattr(runner, "execute_calculator", lambda *args, **kwargs: False)
    assert not runner.execute_profile_position(
        result,
        sample_profile_position(),
        tmp_path / "bridge.csv",
        SimpleNamespace(),
        None,
    )

    def append_summary(material: str = "14 850") -> Any:
        def fake_execute(*args: Any, **kwargs: Any) -> bool:
            result.item_summaries.append(
                runner.ItemCalculationSummary(
                    "ПР",
                    1,
                    "cabinet",
                    "12 557",
                    material,
                    "3 024",
                    "2 970",
                    1,
                )
            )
            return True

        return fake_execute

    monkeypatch.setattr(runner, "execute_calculator", append_summary("invalid"))
    assert not runner.execute_profile_position(
        result,
        sample_profile_position(),
        tmp_path / "bridge.csv",
        SimpleNamespace(),
        None,
    )
    monkeypatch.setattr(runner, "execute_calculator", append_summary())
    assert not runner.execute_profile_position(
        result,
        sample_profile_position(),
        tmp_path / "bridge.csv",
        SimpleNamespace(
            calculate_invoice519_position_price=lambda **kwargs: (_ for _ in ()).throw(
                ValueError("fail")
            )
        ),
        None,
    )
    wrong_anchor = sample_profile_position()
    wrong_anchor = runner.ProfilePositionInput(
        **(wrong_anchor.__dict__ | {"approved_unit_price_kzt": 1})
    )
    monkeypatch.setattr(runner, "execute_calculator", append_summary())
    assert not runner.execute_profile_position(
        result,
        wrong_anchor,
        tmp_path / "bridge.csv",
        runner.load_calculator_module(),
        None,
    )


@pytest.mark.parametrize("exception_type", [ValueError, AttributeError])
def test_execute_profile_position_formula_exceptions_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[Exception],
) -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "except (AttributeError, ValueError):  # fmt: skip" in source
    result = profile_result(tmp_path)

    def append_summary(*args: Any, **kwargs: Any) -> bool:
        result.item_summaries.append(
            runner.ItemCalculationSummary(
                "ПР",
                1,
                "cabinet",
                "12 557",
                "14 850",
                "3 024",
                "2 970",
                1,
            )
        )
        return True

    def fail_formula(**kwargs: Any) -> Any:
        raise exception_type("synthetic formula failure")

    monkeypatch.setattr(runner, "execute_calculator", append_summary)
    assert not runner.execute_profile_position(
        result,
        sample_profile_position(),
        tmp_path / "bridge.csv",
        SimpleNamespace(calculate_invoice519_position_price=fail_formula),
        None,
    )
    assert result.red_flags == ["case formula failed closed for PRICE-POSITION-001"]
    assert not result.position_calculations


def configure_profile_run_mocks(
    monkeypatch: pytest.MonkeyPatch,
    positions: list[Any],
    rechecks: list[bool] | None = None,
) -> None:
    monkeypatch.setattr(runner, "load_pricing_profile", lambda *args: {})
    monkeypatch.setattr(runner, "validate_pricing_profile_contract", lambda *args: True)
    monkeypatch.setattr(
        runner,
        "capture_profile_input_shas",
        lambda *args: {"profile": (Path("profile"), "a" * 64)},
    )

    def valid_completed(result: Any) -> bool:
        result.checks["completed input validation"] = "pass"
        result.checks["safety boundary"] = "pass"
        return True

    monkeypatch.setattr(runner, "run_completed_input_validation", valid_completed)
    monkeypatch.setattr(runner, "load_completed_input_json", lambda result: {})
    monkeypatch.setattr(
        runner,
        "validate_and_build_profile_positions",
        lambda *args: positions,
    )
    answers = iter(rechecks if rechecks is not None else [True, True])
    monkeypatch.setattr(
        runner,
        "recheck_profile_input_shas",
        lambda *args: next(answers),
    )
    monkeypatch.setattr(runner, "resolve_custom_sche_base_cost", lambda path: 20305)
    monkeypatch.setattr(runner, "load_calculator_module", lambda: SimpleNamespace())

    def fake_execute(
        result: Any,
        position: Any,
        input_csv: Path,
        calculator: Any,
        custom_base: int | None,
    ) -> bool:
        assert input_csv.exists()
        result.position_calculations.append(
            runner.ProfilePositionCalculation(
                position.pricing_position_id,
                position.section,
                position.discipline,
                position.source_document,
                position.cabinet_group_id,
                position.product_name,
                position.row_draft_ids,
                position.composition_fingerprint_sha256,
                position.formula_family,
                position.cabinet_base_kzt,
                0,
                100,
                20,
                0,
                position.apartment_count,
                "100.5",
                "AFTER_FULL_UNIT_PRICE_FORMULA",
                "ROUND_HALF_UP",
                101,
                1,
                101,
            )
        )
        result.group_summaries[position.cabinet_group_id] = (
            result.group_summaries.get(position.cabinet_group_id, 0) + 101
        )
        return True

    monkeypatch.setattr(runner, "execute_profile_position", fake_execute)


def test_full_checked_profile_flow_returns_51_position_draft_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = [sample_profile_position(index) for index in range(1, 52)]
    configure_profile_run_mocks(monkeypatch, positions)
    result = runner.run_checked_price_calculator_from_completed_draft(
        tmp_path / "completed.json",
        tmp_path / "prices.xlsx",
        custom_sche_metal_workbook=tmp_path / "metal.xlsx",
        pricing_profile_path=tmp_path / "profile.json",
        expected_pricing_profile_sha256="a" * 64,
    )

    assert result.status == "PASS"
    assert result.pricing_status == "DRAFT_PRELIMINARY_PRICE_CALCULATION"
    assert result.approval_status == "REQUIRES_IGOR_PRICE_APPROVAL"
    assert len(result.position_calculations) == 51
    assert result.preliminary_project_total == 51 * 101
    assert result.non_approval_flags and not any(result.non_approval_flags.values())
    assert result.temp_csv_paths
    assert all(not path.exists() for path in result.temp_csv_paths)
    report = runner.format_report(result)
    assert "Pricing profile provenance:" in report
    assert "Position-level calculations:" in report
    assert "Explicit non-approval flags:" in report


def test_profile_flow_final_toctou_drift_fails_and_cleans_all_temp_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = [sample_profile_position(index) for index in range(1, 52)]
    configure_profile_run_mocks(monkeypatch, positions, [True, False])
    result = runner.run_checked_price_calculator_from_completed_draft(
        tmp_path / "completed.json",
        tmp_path / "prices.xlsx",
        custom_sche_metal_workbook=tmp_path / "metal.xlsx",
        pricing_profile_path=tmp_path / "profile.json",
        expected_pricing_profile_sha256="a" * 64,
    )

    assert result.status == "FAIL"
    assert result.pricing_status is None
    assert result.checks["final TOCTOU"] == "fail"
    assert all(not path.exists() for path in result.temp_csv_paths)


def test_profile_flow_requires_path_and_sha_together(tmp_path: Path) -> None:
    result = runner.run_checked_price_calculator_from_completed_draft(
        tmp_path / "completed.json",
        tmp_path / "prices.xlsx",
        pricing_profile_path=tmp_path / "profile.json",
    )
    assert result.status == "FAIL"
    assert any("both required" in flag for flag in result.red_flags)

    current, profile = valid_formula_profile()
    profile["reserved_case_level_formula_rules"][-1][
        "fixed_work_adjustment_semantics"
    ] = "invented label"
    assert not runner.validate_profile_formula_contract(
        current,
        profile,
        profile_result(tmp_path),
    )
