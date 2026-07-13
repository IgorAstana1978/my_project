import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_confirmed_composition_bridge_envelope.py"
DOC = (
    PROJECT_ROOT
    / "docs"
    / "invoice_quote_filler_confirmed_composition_bridge_envelope_v0_1.md"
)


def load_validator_module() -> ModuleType:
    scripts_dir = str(SCRIPT.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "validate_confirmed_composition_bridge_envelope_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator_module()


def valid_confirmed_artifact() -> dict[str, Any]:
    return {
        "schema_version": "confirmed_composition_artifact.v0.1",
        "confirmation_id": "CONFIRMED-COMPOSITION-TEST-001",
        "confirmed_by": "Igor",
        "confirmed_at": "2099-01-01T12:30:00+05:00",
        "source_links": {
            "raw_input_sha256": "1" * 64,
            "preliminary_draft_sha256": "2" * 64,
            "review_card_sha256": "3" * 64,
        },
        "safety": {
            "status": "confirmed_composition_only",
            "composition_confirmed_by_igor": True,
            "calculator_input_draft_allowed": True,
            "price_approved_by_igor": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "items": [
            {
                "item_id": "ITEM-001",
                "product_name": "Synthetic switchboard",
                "product_type": "switchboard",
                "quantity": 1,
                "cabinet": {
                    "cabinet_code": "CAB-001",
                    "cabinet_label": "Synthetic cabinet",
                },
                "components": [
                    {
                        "component_id": "COMP-001",
                        "component_code": "SYNTHETIC-1P",
                        "component_label": "Synthetic breaker",
                        "quantity": 1,
                        "install_type": "modular_1p",
                    }
                ],
                "confirmation_note": "Synthetic test fixture only.",
            }
        ],
        "red_flags": [],
        "notes": ["Synthetic test fixture only."],
        "next_allowed_step": "build_price_calculator_input_draft",
    }


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_envelope(artifact_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "confirmed_composition_bridge_envelope.v0.1",
        "case": {
            "case_id": "CASE-2099-001",
            "customer_label": "Operational customer label",
            "object_name": "Synthetic object",
        },
        "confirmed_composition": {
            "schema_version": "confirmed_composition_artifact.v0.1",
            "artifact_sha256": file_sha256(artifact_path),
        },
        "supply_boundary": {
            "status": "approved_by_igor",
            "description": "Synthetic supply boundary approved for transfer only.",
            "approved_by_igor": True,
        },
        "approval": {
            "approval_record_id": "APPROVAL-TEST-001",
            "approved_by": "Igor",
            "approved_at": "2099-01-01T12:30:00+05:00",
            "approval_channel": "synthetic-test",
            "scope": ("transfer_confirmed_composition_for_calculator_input_draft_only"),
        },
        "safety": {
            "status": "confirmed_composition_bridge_only",
            "transfer_confirmed_composition_only": True,
            "price_approved_by_igor": False,
            "quote_generation_authorized": False,
            "client_send_authorized": False,
            "production_action_authorized": False,
        },
    }


def make_case(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    artifact_path = tmp_path / "confirmed.json"
    artifact = valid_confirmed_artifact()
    write_json(artifact_path, artifact)
    envelope_path = tmp_path / "envelope.json"
    envelope = valid_envelope(artifact_path)
    write_json(envelope_path, envelope)
    return envelope_path, artifact_path, envelope, artifact


def validate(envelope_path: Path, artifact_path: Path) -> Any:
    return VALIDATOR.validate_confirmed_composition_bridge_envelope(
        envelope_path,
        artifact_path,
    )


def test_valid_envelope_and_confirmed_artifact_pass(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    result = validate(envelope_path, artifact_path)
    assert result.status == "PASS"
    assert all(value == "pass" for value in result.checks.values())
    assert result.red_flags == []


def test_wrong_envelope_schema_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    envelope["schema_version"] = "wrong"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_unknown_root_field_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    envelope["unexpected"] = True
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert "unknown field is not allowed: unexpected" in result.red_flags


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("case", "unexpected_case"),
        ("confirmed_composition", "unexpected_reference"),
        ("supply_boundary", "unexpected_boundary"),
        ("approval", "unexpected_approval"),
        ("safety", "unexpected_safety"),
    ],
)
def test_unknown_nested_field_fails(
    tmp_path: Path,
    section: str,
    field: str,
) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope[section])[field] = "unexpected"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_missing_required_field_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    del envelope["case"]
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert "required field is missing: case" in result.red_flags


@pytest.mark.parametrize(
    "case_id",
    ["", "case-2099-001", "CASE free text", "../CASE-001", "CASE-001/../../x"],
)
def test_invalid_case_id_fails(tmp_path: Path, case_id: str) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["case"])["case_id"] = case_id
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_case_id_with_control_character_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["case"])["case_id"] = "CASE-001\nNEXT"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


@pytest.mark.parametrize("field", ["customer_label", "object_name"])
def test_empty_case_label_fails(tmp_path: Path, field: str) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["case"])[field] = "  "
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_invalid_artifact_sha_format_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = "ABC"
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert result.expected_artifact_sha256 == "invalid"


def test_artifact_sha_mismatch_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = (
        "0" * 64
    )
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert "confirmed artifact SHA-256 does not match envelope" in result.red_flags


def test_confirmed_artifact_schema_mismatch_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, artifact = make_case(tmp_path)
    artifact["schema_version"] = "wrong"
    write_json(artifact_path, artifact)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = (
        file_sha256(artifact_path)
    )
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert result.checks["confirmed artifact schema"] == "fail"


def test_existing_confirmed_artifact_validator_fail_is_propagated(
    tmp_path: Path,
) -> None:
    envelope_path, artifact_path, envelope, artifact = make_case(tmp_path)
    cast(dict[str, Any], artifact["safety"])["production_authorized"] = True
    write_json(artifact_path, artifact)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = (
        file_sha256(artifact_path)
    )
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert result.checks["confirmed artifact validator"] == "fail"


def test_confirmed_artifact_red_flags_must_be_empty(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, artifact = make_case(tmp_path)
    artifact["red_flags"] = ["Synthetic unresolved issue"]
    write_json(artifact_path, artifact)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = (
        file_sha256(artifact_path)
    )
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert result.checks["confirmed artifact validator"] == "pass"
    assert result.checks["confirmed artifact red_flags"] == "fail"


def test_confirmed_artifact_red_flags_wrong_type_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, artifact = make_case(tmp_path)
    artifact["red_flags"] = "none"
    write_json(artifact_path, artifact)
    cast(dict[str, Any], envelope["confirmed_composition"])["artifact_sha256"] = (
        file_sha256(artifact_path)
    )
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_supply_boundary_status_wrong_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["supply_boundary"])["status"] = "pending"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_supply_boundary_not_approved_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["supply_boundary"])["approved_by_igor"] = False
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_empty_supply_boundary_description_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["supply_boundary"])["description"] = ""
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_missing_approval_record_id_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    del cast(dict[str, Any], envelope["approval"])["approval_record_id"]
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


@pytest.mark.parametrize(
    "approved_at",
    ["2099-01-01T12:30:00", "not-a-timestamp"],
)
def test_approval_timestamp_requires_iso_timezone(
    tmp_path: Path,
    approved_at: str,
) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["approval"])["approved_at"] = approved_at
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert (
        "approval.approved_at must be an ISO 8601 timestamp with timezone"
        in result.red_flags
    )


def test_approval_timestamp_accepts_z(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["approval"])["approved_at"] = "2099-01-01T07:30:00Z"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "PASS"


def test_unknown_approval_scope_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["approval"])["scope"] = "approve_everything"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_safety_status_wrong_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["safety"])["status"] = "unsafe"
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_transfer_confirmed_composition_only_false_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["safety"])[
        "transfer_confirmed_composition_only"
    ] = False
    write_json(envelope_path, envelope)
    assert validate(envelope_path, artifact_path).status == "FAIL"


@pytest.mark.parametrize(
    "field",
    [
        "price_approved_by_igor",
        "quote_generation_authorized",
        "client_send_authorized",
        "production_action_authorized",
    ],
)
def test_commercial_or_production_flag_true_fails(
    tmp_path: Path,
    field: str,
) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    cast(dict[str, Any], envelope["safety"])[field] = True
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert f"commercial or production flag is true: safety.{field}" in result.red_flags


@pytest.mark.parametrize("field", ["items", "components", "cabinet"])
def test_confirmed_payload_fields_are_forbidden_in_envelope(
    tmp_path: Path,
    field: str,
) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    envelope[field] = []
    write_json(envelope_path, envelope)
    result = validate(envelope_path, artifact_path)
    assert result.status == "FAIL"
    assert f"unknown field is not allowed: {field}" in result.red_flags


def test_missing_envelope_fails(tmp_path: Path) -> None:
    _, artifact_path, _, _ = make_case(tmp_path)
    result = validate(tmp_path / "missing-envelope.json", artifact_path)
    assert result.status == "FAIL"
    assert "envelope JSON does not exist" in result.red_flags


def test_missing_confirmed_artifact_fails(tmp_path: Path) -> None:
    envelope_path, _, _, _ = make_case(tmp_path)
    result = validate(envelope_path, tmp_path / "missing-confirmed.json")
    assert result.status == "FAIL"
    assert "confirmed artifact JSON does not exist" in result.red_flags


def test_envelope_root_must_be_object(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    write_json(envelope_path, [])
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_malformed_envelope_json_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    envelope_path.write_text("{not-json", encoding="utf-8")
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_non_utf8_envelope_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    envelope_path.write_bytes(b"\xff\xfe")
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_malformed_confirmed_artifact_json_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    artifact_path.write_text("{not-json", encoding="utf-8")
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_non_utf8_confirmed_artifact_fails(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    artifact_path.write_bytes(b"\xff\xfe")
    assert validate(envelope_path, artifact_path).status == "FAIL"


def test_cli_pass_exit_code_and_report(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--envelope-json",
            str(envelope_path),
            "--confirmed-composition-json",
            str(artifact_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0
    assert "Status:\nPASS" in completed.stdout
    assert completed.stdout.startswith(
        "CONFIRMED_COMPOSITION_BRIDGE_ENVELOPE_VALIDATION_REPORT_START"
    )
    assert completed.stdout.rstrip().endswith(
        "CONFIRMED_COMPOSITION_BRIDGE_ENVELOPE_VALIDATION_REPORT_END"
    )


def test_cli_fail_exit_code(tmp_path: Path) -> None:
    envelope_path, artifact_path, envelope, _ = make_case(tmp_path)
    envelope["schema_version"] = "wrong"
    write_json(envelope_path, envelope)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--envelope-json",
            str(envelope_path),
            "--confirmed-composition-json",
            str(artifact_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode != 0
    assert "Status:\nFAIL" in completed.stdout


def test_validator_does_not_create_or_modify_files(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    before_names = sorted(path.name for path in tmp_path.iterdir())
    before_envelope = envelope_path.read_bytes()
    before_artifact = artifact_path.read_bytes()
    result = validate(envelope_path, artifact_path)
    assert result.status == "PASS"
    assert sorted(path.name for path in tmp_path.iterdir()) == before_names
    assert envelope_path.read_bytes() == before_envelope
    assert artifact_path.read_bytes() == before_artifact


def test_report_has_required_read_only_fields(tmp_path: Path) -> None:
    envelope_path, artifact_path, _, _ = make_case(tmp_path)
    report = VALIDATOR.format_report(validate(envelope_path, artifact_path))
    for text in (
        "Validator:\nconfirmed composition bridge envelope validator",
        "Mode:\nread-only",
        "Envelope path:",
        "Confirmed artifact path:",
        "Expected artifact SHA-256:",
        "Actual artifact SHA-256:",
        "confirmed artifact validator: pass",
        "confirmed artifact red_flags: pass",
        "Human Approval:",
    ):
        assert text in report


def test_customer_label_is_not_payer_or_legal_customer() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8").lower()
    doc_text = DOC.read_text(encoding="utf-8").lower()
    assert "operational label" in doc_text
    assert "legal payer" in doc_text
    assert "customer_label" in script_text
    assert "customer_label" in doc_text


def test_valid_fixture_helper_is_not_mutated(tmp_path: Path) -> None:
    artifact = valid_confirmed_artifact()
    before = copy.deepcopy(artifact)
    path = tmp_path / "artifact.json"
    write_json(path, artifact)
    valid_envelope(path)
    assert artifact == before
