import hashlib
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


def compact_applied_bundle() -> dict[str, Any]:
    def signature(label: str) -> dict[str, Any]:
        return {
            "component_identity": label,
            "model_type": "SYNTHETIC",
            "ratings": ["16A"],
            "poles": 1,
            "functional_role": "synthetic",
        }

    canonical = []
    direct = []
    exclusions = []
    overlays = []
    reserved = []
    for index in range(1, 4):
        component_id = f"COMP-{index:03d}"
        label = f"Synthetic {index}"
        canonical.append(
            {
                "component_evidence_id": component_id,
                "document_id": "DOC-SYNTHETIC",
                "label": label,
                "position_id": f"POS-{index:03d}",
                "provenance": {"row_locator": f"row={index}"},
                "section_id": "SYNTHETIC",
                "source_status": "identified",
            }
        )
        member = {
            "component_evidence_id": component_id,
            "evidence_position_id": f"POS-{index:03d}",
            "section": "SYNTHETIC",
            "source_locator": f"row={index}",
            "canonical_label": label,
            "canonical_document_id": "DOC-SYNTHETIC",
            "canonical_source_status": "identified",
            "canonical_provenance": {"row_locator": f"row={index}"},
        }
        common = {
            "decision_id": f"DEC-{index:03d}",
            "decision_code": f"CODE-{index:03d}",
            "component_signature": signature(label),
            "members": [member],
            "application_status": "APPLIED",
        }
        if index <= 2:
            direct.append(
                {
                    **common,
                    "decision_kind": "DIRECT_COMPONENT_QUANTITY",
                    "quantity_per_cabinet": index,
                }
            )
            overlays.append(
                {
                    "item_id": f"ITEM-{index:03d}",
                    "item_kind": (
                        "COMPONENT_SIGNATURE_CORRECTION"
                        if index == 1
                        else "COMPONENT_RECONFIRMATION"
                    ),
                    "cabinet_record_id": f"CAB-{index:03d}",
                    "cabinet_template": "SYNTHETIC-CABINET",
                    "component_evidence_id": component_id,
                    "position_id": f"POS-{index:03d}",
                    "section": "SYNTHETIC",
                    "source_locator": f"row={index}",
                    "original_signature": signature(label),
                    "approved_signature": signature(label),
                    "quantity_per_cabinet": index,
                    "provenance": {"source_locator": f"row={index}"},
                    "correction_reason": "synthetic",
                    "canonical_evidence_modified": False,
                    "application_status": "APPLIED",
                }
            )
        else:
            exclusions.append(
                {
                    **common,
                    "decision_kind": "SCOPE_EXCLUSION",
                    "scope_status": "EXCLUDED_RESERVED_SPACE_ONLY",
                    "future_inclusion_requires": "SEPARATE_IGOR_APPROVAL",
                    "prohibited_downstream": ["pricing"],
                }
            )
            reserved.append(
                {
                    "item_id": "ITEM-003",
                    "item_kind": "RESERVED_METER_SPACE",
                    "cabinet_record_id": "CAB-003",
                    "cabinet_template": "SYNTHETIC-CABINET",
                    "component_evidence_id": component_id,
                    "position_id": "POS-003",
                    "section": "SYNTHETIC",
                    "source_locator": "row=3",
                    "requirement_kind": "RESERVED_METER_SPACE",
                    "meter_connection": "THREE_PHASE_DIRECT",
                    "reserved_space_per_cabinet": 1,
                    "installed_component": False,
                    "original_identity": label,
                    "provenance": {"source_locator": "row=3"},
                    "future_inclusion_requires": "SEPARATE_IGOR_APPROVAL",
                    "prohibited_downstream": ["pricing"],
                    "canonical_evidence_modified": False,
                    "application_status": "APPLIED",
                }
            )
    return {
        "schema_version": "component_replay_applied_bundle.v0.23",
        "project_id": "CASE-SYNTHETIC-V023",
        "application_status": "APPLIED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_order": [
            "human_decisions_batch.v0.22",
            "human_decisions_batch.v0.23",
        ],
        "source_lineage": {
            "canonical_replay_sha256": "1" * 64,
            "canonical_replay_schema_version": (
                "component_replay_readiness_bundle.v0.2"
            ),
            "prior_batch_sha256": "2" * 64,
            "prior_batch_schema_version": "human_decisions_batch.v0.22",
            "prior_batch_id": "022",
            "correction_batch_sha256": "3" * 64,
            "correction_batch_schema_version": "human_decisions_batch.v0.23",
            "correction_batch_id": "023",
            "correction_prior_batch_id": "022",
        },
        "canonical_component_evidence_records": canonical,
        "prior_v0_22_application": {
            "application_status": "APPLIED",
            "direct_component_quantities": direct,
            "cabinet_level_aggregates": [],
            "scope_exclusions": exclusions,
            "coverage": {
                "direct_component_count": 2,
                "aggregate_member_count": 0,
                "exclusion_component_count": 1,
                "union_component_count": 3,
            },
        },
        "component_signature_overlays": overlays,
        "reserved_meter_space_requirements": reserved,
        "coverage": {
            "canonical_component_count": 3,
            "prior_direct_component_count": 2,
            "prior_aggregate_member_count": 0,
            "prior_exclusion_component_count": 1,
            "prior_union_component_count": 3,
            "component_signature_correction_count": 1,
            "component_reconfirmation_count": 1,
            "reserved_meter_space_count": 1,
            "overlay_component_count": 3,
        },
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }


def write_applied_source(tmp_path: Path) -> Path:
    path = tmp_path / "applied-v0.23.json"
    path.write_text(
        json.dumps(compact_applied_bundle(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def valid_v02_data(applied_path: Path) -> dict[str, Any]:
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    return {
        "schema_version": "confirmed_composition_artifact.v0.2",
        "project_id": snapshot.data["project_id"],
        "confirmation_id": "CONFIRM-SYNTHETIC-V023",
        "confirmed_by": "Igor",
        "confirmed_at": "2099-01-01T12:30:00+05:00",
        "approval": {
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "approved_by": "Igor",
            "approval_phrase": "CONFIRM TECHNICAL COMPOSITION",
            "approval_channel": "synthetic_test",
        },
        "source_lineage": {
            "applied_bundle_sha256": hashlib.sha256(
                applied_path.read_bytes()
            ).hexdigest(),
            "applied_bundle_schema_version": "component_replay_applied_bundle.v0.23",
            "applied_source_lineage": snapshot.data["source_lineage"],
        },
        "installed_components": snapshot.installed_components,
        "reserved_meter_spaces": snapshot.reserved_meter_spaces,
        "coverage": snapshot.coverage,
        "confirmed_composition_created": True,
        "pricing_started": False,
        "downstream_started": False,
        "red_flags": [],
    }


def run_v02_validation(
    data: dict[str, Any],
    tmp_path: Path,
    applied_path: Path,
) -> Any:
    return validator.validate_confirmed_composition_artifact(
        write_json(tmp_path, data),
        applied_bundle_json=applied_path,
    )


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


def test_valid_confirmed_v02_passes_with_exact_applied_binding(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_source(tmp_path)
    data = valid_v02_data(applied_path)

    result = run_v02_validation(data, tmp_path, applied_path)

    assert result.status == "PASS"
    assert result.red_flags == []
    assert all(status == "pass" for status in result.checks.values())


def test_confirmed_v02_requires_exact_existing_igor_approval(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_source(tmp_path)
    data = valid_v02_data(applied_path)
    cast(dict[str, Any], data["approval"])["approval_phrase"] = "SECOND MECHANISM"

    result = run_v02_validation(data, tmp_path, applied_path)

    assert result.status == "FAIL"
    assert any("exact Igor approval mismatch" in value for value in result.red_flags)


@pytest.mark.parametrize(
    ("field_name", "replacement", "expected"),
    [
        ("applied_bundle_sha256", "0" * 64, "SHA-256 binding mismatch"),
        ("applied_source_lineage", {}, "applied source lineage mismatch"),
    ],
)
def test_confirmed_v02_sha_and_lineage_tampering_fails_closed(
    tmp_path: Path,
    field_name: str,
    replacement: Any,
    expected: str,
) -> None:
    applied_path = write_applied_source(tmp_path)
    data = valid_v02_data(applied_path)
    cast(dict[str, Any], data["source_lineage"])[field_name] = replacement

    result = run_v02_validation(data, tmp_path, applied_path)

    assert result.status == "FAIL"
    assert any(expected in value for value in result.red_flags)


def test_confirmed_v02_rejects_reserved_space_leakage(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_source(tmp_path)
    data = valid_v02_data(applied_path)
    leaked = dict(data["reserved_meter_spaces"][0])
    leaked.update(
        {
            "canonical_label": leaked["original_identity"],
            "approved_signature": {
                "component_identity": leaked["original_identity"],
                "model_type": "SYNTHETIC",
                "ratings": [],
                "poles": None,
                "functional_role": "reserved",
            },
            "quantity": {
                "decision_id": "DEC-003",
                "decision_kind": "DIRECT_COMPONENT_QUANTITY",
                "quantity_per_cabinet": 1,
            },
            "signature_source": "V0_22_PRIOR",
            "overlay_kind": None,
        }
    )
    for key in list(leaked):
        if key not in validator.V02_INSTALLED_COMPONENT_FIELDS:
            del leaked[key]
    cast(list[Any], data["installed_components"]).append(leaked)

    result = run_v02_validation(data, tmp_path, applied_path)

    assert result.status == "FAIL"
    assert any("reserved space leaked" in value for value in result.red_flags)


@pytest.mark.parametrize(
    ("field_name", "replacement", "expected"),
    [
        ("coverage", {}, "coverage mismatch"),
        ("pricing_started", True, "pricing_started must be false"),
        ("downstream_started", True, "downstream_started must be false"),
    ],
)
def test_confirmed_v02_coverage_and_downstream_tampering_fails_closed(
    tmp_path: Path,
    field_name: str,
    replacement: Any,
    expected: str,
) -> None:
    applied_path = write_applied_source(tmp_path)
    data = valid_v02_data(applied_path)
    data[field_name] = replacement

    result = run_v02_validation(data, tmp_path, applied_path)

    assert result.status == "FAIL"
    assert any(expected in value for value in result.red_flags)


def test_validator_rejects_mixed_v01_and_applied_inputs(
    tmp_path: Path,
) -> None:
    applied_path = write_applied_source(tmp_path)

    result = validator.validate_confirmed_composition_artifact(
        write_json(tmp_path, valid_data()),
        applied_bundle_json=applied_path,
    )

    assert result.status == "FAIL"
    assert any("forbidden for confirmed v0.1" in value for value in result.red_flags)


@pytest.mark.parametrize("fault", ["duplicate", "unknown"])
def test_applied_source_duplicate_and_unknown_comp_fail_closed(
    tmp_path: Path,
    fault: str,
) -> None:
    data = compact_applied_bundle()
    if fault == "duplicate":
        data["component_signature_overlays"][1]["component_evidence_id"] = data[
            "component_signature_overlays"
        ][0]["component_evidence_id"]
    else:
        data["component_signature_overlays"][0][
            "component_evidence_id"
        ] = "COMP-UNKNOWN"
    applied_path = tmp_path / "bad-applied.json"
    applied_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(validator.AppliedBundleValidationError):
        validator.load_applied_bundle_snapshot(applied_path)
