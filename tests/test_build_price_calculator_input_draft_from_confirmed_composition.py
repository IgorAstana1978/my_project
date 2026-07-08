import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "build_price_calculator_input_draft_from_confirmed_composition.py"
)
EXAMPLE = PROJECT_ROOT / "examples" / "confirmed_composition_artifact.example.json"
OLD_WORKFLOWS = (
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py",
    PROJECT_ROOT / "scripts" / "export_client_style_invoice.py",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py",
)
FORBIDDEN_OUTPUT_KEYS = (
    "price_confirmed_by_igor",
    "price_includes_vat",
    "unit_price_kzt",
    "line_total",
    "total_kzt",
    "final_price",
    "client_ready",
    "ready_to_send",
    "send_to_client",
    "commercial_approved",
    "production_approved",
    "production_action_authorized",
    "token_execution_authorized",
    "product_name_guess",
    "product_type_guess",
    "quantity_guess",
    "cabinet_guess",
    "component_code_guess",
    "component_label_guess",
    "install_type_guess",
    "confidence",
    "evidence",
    "requires_igor_confirmation",
)


def load_builder_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_price_calculator_input_draft_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_builder_module())


def valid_data() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EXAMPLE.read_text(encoding="utf-8")))


def write_confirmed_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "confirmed-composition.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_draft(
    tmp_path: Path,
    data: dict[str, Any] | None = None,
    output_name: str = "calculator-input-draft.json",
) -> Any:
    confirmed_path = write_confirmed_json(
        tmp_path,
        data if data is not None else valid_data(),
    )
    output_path = tmp_path / output_name
    return builder.build_price_calculator_input_draft(confirmed_path, output_path)


def read_output(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(result.output_json.read_text("utf-8")))


def test_valid_confirmed_composition_creates_draft_outside_git(tmp_path: Path) -> None:
    result = build_draft(tmp_path)

    assert result.status == "PASS"
    assert result.output_created is True
    assert result.output_json.is_file()
    assert all(status == "pass" for status in result.checks.values())


def test_confirmed_composition_validation_fail_prevents_output(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["price_approved_by_igor"] = True

    result = build_draft(tmp_path, data=data)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert not result.output_json.exists()
    assert result.checks["confirmed composition validation"] == "fail"


def test_output_already_exists_fails_without_overwrite(tmp_path: Path) -> None:
    output_path = tmp_path / "calculator-input-draft.json"
    output_path.write_text("KEEP THIS", encoding="utf-8")
    result = build_draft(tmp_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert output_path.read_text(encoding="utf-8") == "KEEP THIS"
    assert "output JSON already exists" in result.red_flags


def test_output_inside_git_fails(tmp_path: Path) -> None:
    confirmed_path = write_confirmed_json(tmp_path, valid_data())
    output_path = PROJECT_ROOT / "calculator-input-draft.inside-git.json"

    result = builder.build_price_calculator_input_draft(confirmed_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output JSON must be outside the project" in result.red_flags


def test_output_parent_missing_fails(tmp_path: Path) -> None:
    confirmed_path = write_confirmed_json(tmp_path, valid_data())
    output_path = tmp_path / "missing-parent" / "calculator-input-draft.json"

    result = builder.build_price_calculator_input_draft(confirmed_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output parent directory does not exist" in result.red_flags


def test_malformed_confirmed_composition_prevents_output(tmp_path: Path) -> None:
    confirmed_path = tmp_path / "confirmed-composition.json"
    confirmed_path.write_text("{not-json", encoding="utf-8")
    output_path = tmp_path / "calculator-input-draft.json"

    result = builder.build_price_calculator_input_draft(confirmed_path, output_path)

    assert result.status == "FAIL"
    assert result.output_created is False
    assert not output_path.exists()
    assert any("malformed" in flag for flag in result.red_flags)


def test_output_contains_item_product_identity(tmp_path: Path) -> None:
    result = build_draft(tmp_path)
    output = read_output(result)

    assert output["items"][0]["item_id"] == "ITEM-001"
    assert output["items"][0]["product_name"] == "РУ-АВР / ЩРН-24"
    assert output["items"][0]["product_type"] == "switchboard"


def test_output_contains_cabinet_code_and_label(tmp_path: Path) -> None:
    result = build_draft(tmp_path)
    output = read_output(result)

    cabinet = output["items"][0]["cabinet"]
    assert cabinet["cabinet_code"] == "CAB-KRN-24"
    assert cabinet["cabinet_label"] == "КРН-24"


def test_output_contains_components_and_install_type(tmp_path: Path) -> None:
    result = build_draft(tmp_path)
    output = read_output(result)
    rows = output["calculator_input_format"]["rows"]

    assert rows[0]["component_code"] == "EKF-VA47-29-1P"
    assert rows[0]["component_qty"] == 4
    assert rows[0]["install_type"] == "modular_1p"
    assert output["items"][0]["components"][1]["install_type"] == "modular_3p"


def test_output_contains_source_traceability_fields(tmp_path: Path) -> None:
    result = build_draft(tmp_path)
    output = read_output(result)

    assert output["source"]["confirmation_id"] == "CONFIRMED-COMPOSITION-EXAMPLE-001"
    assert output["source"]["confirmed_by"] == "Igor"
    assert output["source"]["source_links"]["raw_input_sha256"] == "1" * 64


def test_output_contains_safety_block_with_no_price_execution(tmp_path: Path) -> None:
    result = build_draft(tmp_path)
    output = read_output(result)
    safety = output["safety"]

    assert safety["status"] == "price_calculator_input_draft_only"
    assert safety["derived_from_confirmed_composition"] is True
    assert safety["price_calculation_executed"] is False
    assert safety["price_approved_by_igor"] is False


def test_output_contains_no_forbidden_price_or_commercial_fields(
    tmp_path: Path,
) -> None:
    result = build_draft(tmp_path)
    output_text = result.output_json.read_text(encoding="utf-8")
    output = read_output(result)

    for key in FORBIDDEN_OUTPUT_KEYS[:13]:
        assert f'"{key}"' not in output_text
    assert "total" not in json.dumps(output, ensure_ascii=False).lower()


def test_output_contains_no_preliminary_guess_confidence_or_evidence_fields(
    tmp_path: Path,
) -> None:
    result = build_draft(tmp_path)
    output_text = result.output_json.read_text(encoding="utf-8")

    for key in FORBIDDEN_OUTPUT_KEYS[13:]:
        assert f'"{key}"' not in output_text


def test_script_does_not_call_price_calculator() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "calc_quote_price_draft" not in source
    assert "calculate_price_draft" not in source
    assert "load_workbook" not in source


def test_script_does_not_calculate_totals_or_prices() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "Decimal" not in source
    assert "ROUND_HALF_UP" not in source
    assert "total_preliminary_price" not in source
    assert "component_material_total" not in source
    assert "work_total" not in source


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

    assert "subprocess" not in source
    assert " git " not in source
    assert "git." not in source


def test_report_has_required_markers_and_safety_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    confirmed_path = write_confirmed_json(tmp_path, valid_data())
    output_path = tmp_path / "calculator-input-draft.json"

    assert (
        builder.main(
            [
                "--confirmed-composition-json",
                str(confirmed_path),
                "--output-json",
                str(output_path),
            ]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert report.startswith("PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_START")
    assert "Mode:\nprice calculator input draft build only" in report
    assert "Commercial status:\ncalculator input draft only" in report
    assert "no price calculated" in report
    assert str(output_path) in report
    assert report.rstrip().endswith("PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_END")


def test_report_does_not_leak_long_notes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = valid_data()
    data["notes"] = ["SECRET CONFIRMED COMPOSITION NOTE " * 40]
    confirmed_path = write_confirmed_json(tmp_path, data)
    output_path = tmp_path / "calculator-input-draft.json"

    assert (
        builder.main(
            [
                "--confirmed-composition-json",
                str(confirmed_path),
                "--output-json",
                str(output_path),
            ]
        )
        == 0
    )
    report = capsys.readouterr().out

    assert "SECRET CONFIRMED COMPOSITION NOTE" not in report


def test_old_workflows_do_not_reference_this_builder() -> None:
    builder_name = "build_price_calculator_input_draft_from_confirmed_composition"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert builder_name not in path.read_text(encoding="utf-8"), path
