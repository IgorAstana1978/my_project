import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_confirmed_composition_artifact.py"
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
    PROJECT_ROOT / "scripts" / "validate_preliminary_composition_draft.py",
    PROJECT_ROOT / "scripts" / "verify_preliminary_composition_source_bundle.py",
    PROJECT_ROOT / "scripts" / "build_preliminary_composition_review_card.py",
)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_confirmed_composition_artifact_for_test",
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
    path = tmp_path / "confirmed.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_validation(data: dict[str, Any], tmp_path: Path) -> Any:
    return validator.validate_confirmed_composition_artifact(write_json(tmp_path, data))


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

    result = validator.validate_confirmed_composition_artifact(path)

    assert result.status == "FAIL"
    assert "input JSON is malformed" in result.red_flags


def test_missing_required_root_field_fails(tmp_path: Path) -> None:
    data = valid_data()
    del data["confirmation_id"]

    assert_fails_with(data, tmp_path, "required field is missing: confirmation_id")


def test_wrong_schema_version_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["schema_version"] = "confirmed_composition_artifact.v9"

    assert_fails_with(data, tmp_path, "schema_version must be")


def test_composition_confirmed_by_igor_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["composition_confirmed_by_igor"] = False

    assert_fails_with(
        data,
        tmp_path,
        "safety.composition_confirmed_by_igor must be true",
    )


def test_calculator_input_draft_allowed_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["calculator_input_draft_allowed"] = False

    assert_fails_with(
        data,
        tmp_path,
        "safety.calculator_input_draft_allowed must be true",
    )


def test_price_approved_by_igor_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["price_approved_by_igor"] = True

    assert_fails_with(data, tmp_path, "safety.price_approved_by_igor must be false")


def test_commercial_csv_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["commercial_csv_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.commercial_csv_authorized must be false")


def test_client_style_export_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["client_style_export_authorized"] = True

    assert_fails_with(
        data,
        tmp_path,
        "safety.client_style_export_authorized must be false",
    )


def test_sending_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["sending_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.sending_authorized must be false")


def test_production_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["safety"])["production_authorized"] = True

    assert_fails_with(data, tmp_path, "safety.production_authorized must be false")


def test_forbidden_key_unit_price_kzt_anywhere_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["unit_price_kzt"] = 1000

    assert_fails_with(data, tmp_path, "forbidden key present")


def test_forbidden_preliminary_key_product_name_guess_anywhere_fails(
    tmp_path: Path,
) -> None:
    data = valid_data()
    first_item(data)["product_name_guess"] = "guess"

    assert_fails_with(data, tmp_path, "product_name_guess")


def test_forbidden_preliminary_key_confidence_anywhere_fails(
    tmp_path: Path,
) -> None:
    data = valid_data()
    first_component(data)["confidence"] = 0.8

    assert_fails_with(data, tmp_path, "confidence")


def test_invalid_source_hash_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source_links"])["raw_input_sha256"] = "ABC"

    assert_fails_with(data, tmp_path, "raw_input_sha256 must be 64 lowercase hex")


def test_empty_items_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["items"] = []

    assert_fails_with(data, tmp_path, "items must be a non-empty list")


def test_item_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["quantity"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive integer")


def test_missing_cabinet_code_fails(tmp_path: Path) -> None:
    data = valid_data()
    del cast(dict[str, Any], first_item(data)["cabinet"])["cabinet_code"]

    assert_fails_with(data, tmp_path, "required field is missing")


def test_empty_components_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_item(data)["components"] = []

    assert_fails_with(data, tmp_path, "field must be a non-empty list")


def test_component_quantity_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["quantity"] = 0

    assert_fails_with(data, tmp_path, "field must be a positive number")


def test_install_type_manual_review_required_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["install_type"] = "manual_review_required"

    assert_fails_with(data, tmp_path, "manual_review_required is not allowed")


def test_invalid_install_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["install_type"] = "panel_magic"

    assert_fails_with(data, tmp_path, "install_type is not allowed")


def test_n_pe_bus_set_install_type_passes(tmp_path: Path) -> None:
    data = valid_data()
    first_component(data)["install_type"] = "n_pe_bus_set"

    result = run_validation(data, tmp_path)

    assert result.status == "PASS", result.red_flags


def test_report_has_safety_boundaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path, valid_data())

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert report.startswith("CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_START")
    assert "Mode:\nconfirmed composition artifact validation only" in report
    assert "Commercial status:\ncomposition confirmed only" in report
    assert "not price approval" in report
    assert "not commercial CSV" in report
    assert "not client-ready КП" in report
    assert "Human Approval:\nIgor approval still required" in report
    assert report.rstrip().endswith(
        "CONFIRMED_COMPOSITION_ARTIFACT_VALIDATION_REPORT_END"
    )


def test_report_does_not_leak_long_notes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = valid_data()
    secret_long_note = "SECRET CONFIRMED COMPOSITION NOTE " * 40
    data["notes"] = [secret_long_note]
    path = write_json(tmp_path, data)

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert secret_long_note not in report
    assert "SECRET CONFIRMED COMPOSITION NOTE" not in report


def test_old_workflows_do_not_reference_this_validator() -> None:
    validator_name = "validate_confirmed_composition_artifact"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert validator_name not in path.read_text(encoding="utf-8"), path
