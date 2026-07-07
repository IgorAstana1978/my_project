import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_preliminary_composition_draft.py"
EXAMPLE = PROJECT_ROOT / "examples" / "preliminary_composition_draft.example.json"
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


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_preliminary_composition_draft_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def valid_data() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(EXAMPLE.read_text(encoding="utf-8")))


def write_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_validation(data: dict[str, Any], tmp_path: Path) -> Any:
    return validator.validate_preliminary_composition_draft(write_json(tmp_path, data))


def first_item(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["items"][0])


def first_component(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], first_item(data)["components"][0])


def assert_fails_with(
    data: dict[str, Any],
    tmp_path: Path,
    expected: str,
) -> None:
    result = run_validation(data, tmp_path)

    assert result.status == "FAIL"
    assert any(expected in red_flag for red_flag in result.red_flags), result.red_flags


def test_valid_example_passes(tmp_path: Path) -> None:
    result = run_validation(valid_data(), tmp_path)

    assert result.status == "PASS"
    assert result.red_flags == []
    assert all(status == "pass" for status in result.checks.values())


def test_malformed_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")

    result = validator.validate_preliminary_composition_draft(path)

    assert result.status == "FAIL"
    assert "input JSON is malformed" in result.red_flags


def test_missing_required_root_field_fails(tmp_path: Path) -> None:
    data = valid_data()
    del data["draft_id"]

    assert_fails_with(data, tmp_path, "required field is missing: draft_id")


def test_wrong_schema_version_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["schema_version"] = "preliminary_composition_draft.v9"

    assert_fails_with(data, tmp_path, "schema_version must be")


def test_confirmed_by_igor_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["confirmed_by_igor"] = True

    assert_fails_with(data, tmp_path, "safety.confirmed_by_igor must be false")


def test_price_execution_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["price_execution_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.price_execution_authorized must be false")


def test_commercial_csv_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["commercial_csv_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.commercial_csv_authorized must be false")


def test_sending_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["sending_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.sending_authorized must be false")


def test_forbidden_key_unit_price_kzt_anywhere_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["unit_price_kzt"] = 1000

    assert_fails_with(data, tmp_path, "forbidden key present")


def test_forbidden_key_price_confirmed_by_igor_anywhere_fails(
    tmp_path: Path,
) -> None:
    data = valid_data()
    first_item(data)["price_confirmed_by_igor"] = False

    assert_fails_with(data, tmp_path, "price_confirmed_by_igor")


def test_empty_items_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["items"] = []

    assert_fails_with(data, tmp_path, "items must be a non-empty list")


def test_item_requires_igor_confirmation_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["requires_igor_confirmation"] = False

    assert_fails_with(data, tmp_path, "requires_igor_confirmation must be true")


def test_component_requires_igor_confirmation_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["requires_igor_confirmation"] = False

    assert_fails_with(data, tmp_path, "requires_igor_confirmation must be true")


def test_invalid_confidence_below_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["confidence"] = -0.01

    assert_fails_with(data, tmp_path, "confidence must be a number from 0 to 1")


def test_invalid_confidence_above_one_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["confidence"] = 1.01

    assert_fails_with(data, tmp_path, "confidence must be a number from 0 to 1")


def test_missing_evidence_fails(tmp_path: Path) -> None:
    data = valid_data()
    del first_item(data)["evidence"]

    assert_fails_with(data, tmp_path, "required field is missing: items[0].evidence")


def test_invalid_raw_input_sha256_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source"])["raw_input_sha256"] = "ABC"

    assert_fails_with(data, tmp_path, "raw_input_sha256 must be 64 lowercase hex")


def test_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["quantity_guess"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive integer")


def test_component_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["quantity_guess"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive number")


def test_invalid_install_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["install_type_guess"] = "panel_magic"

    assert_fails_with(data, tmp_path, "install_type_guess is not allowed")


def test_report_has_safety_boundaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path, valid_data())

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert report.startswith("PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START")
    assert "Mode:\npreliminary composition draft validation only" in report
    assert "Commercial status:\nnot confirmed composition" in report
    assert "not price approval" in report
    assert "not client-ready КП" in report
    assert "Human Approval:\nIgor confirmation required" in report
    assert report.rstrip().endswith(
        "PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END"
    )


def test_report_does_not_leak_long_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = valid_data()
    secret_long_evidence = "SECRET RAW PROJECT TEXT " * 40
    first_item(data)["evidence"] = [secret_long_evidence]
    path = write_json(tmp_path, data)

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert secret_long_evidence not in report
    assert "SECRET RAW PROJECT TEXT" not in report


def test_old_workflows_do_not_reference_this_validator() -> None:
    validator_name = "validate_preliminary_composition_draft"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert validator_name not in path.read_text(encoding="utf-8"), path
