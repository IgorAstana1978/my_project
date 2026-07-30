import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_human_decisions_batch_v0_23.py"


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_human_decisions_batch_v0_23_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def signature(
    identity: str,
    *,
    model_type: str | None = None,
    ratings: list[str] | None = None,
    poles: int | None = None,
    functional_role: str = "PROTECTION",
) -> dict[str, Any]:
    return {
        "component_identity": identity,
        "model_type": model_type,
        "ratings": [] if ratings is None else ratings,
        "poles": poles,
        "functional_role": functional_role,
    }


def provenance(number: int) -> dict[str, Any]:
    return {
        "source_artifact_sha256": "a" * 64,
        "source_record_id": f"SOURCE-{number:03d}",
        "source_locator": f"table_row={number}; specification_position=1.6",
    }


def component_item(
    number: int,
    kind: str,
    original: dict[str, Any],
    approved: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": f"ITEM-{number:03d}",
        "item_kind": kind,
        "component_evidence_id": f"COMP-{number:03d}",
        "original_signature": original,
        "approved_signature": approved,
        "quantity_per_cabinet": number,
        "provenance": provenance(number),
        "correction_reason": "DIRECT_IGOR_TECHNICAL_SIGNATURE_DECISION",
        "application_status": "NOT_EXECUTED",
    }


def reserved_item(number: int) -> dict[str, Any]:
    return {
        "item_id": f"ITEM-{number:03d}",
        "item_kind": "RESERVED_METER_SPACE",
        "component_evidence_id": f"COMP-{number:03d}",
        "requirement_kind": "RESERVED_METER_SPACE",
        "meter_connection": "THREE_PHASE_DIRECT",
        "reserved_space_per_cabinet": 1,
        "installed_component": False,
        "original_identity": "СЧЕТЧИК",
        "provenance": provenance(number),
        "future_inclusion_requires": ("SEPARATE_METER_SELECTION_AND_IGOR_APPROVAL"),
        "prohibited_downstream": [
            "installed_composition",
            "pricing",
            "procurement",
            "production",
        ],
        "application_status": "NOT_EXECUTED",
    }


def valid_data() -> dict[str, Any]:
    raw_signature = signature("RAW APPARATUS", model_type=None, poles=None)
    approved_signature = signature(
        "LOAD SWITCH",
        model_type=None,
        poles=None,
        functional_role="LOAD_SWITCHING",
    )
    confirmed_signature = signature(
        "AUTOMATIC BREAKER",
        model_type="AB-1",
        ratings=["16A", "6kA"],
        poles=3,
    )
    correction = component_item(
        1,
        "COMPONENT_SIGNATURE_CORRECTION",
        raw_signature,
        approved_signature,
    )
    reconfirmation = component_item(
        2,
        "COMPONENT_RECONFIRMATION",
        confirmed_signature,
        copy.deepcopy(confirmed_signature),
    )
    return {
        "schema_version": "human_decisions_batch.v0.23",
        "compatible_with": "human_decisions_batch.v0.22",
        "case_id": "CASE-V023-SYNTHETIC",
        "project_id": "SYNTHETIC",
        "batch_id": "023",
        "prior_batch_id": "022",
        "artifact_status": "FROZEN_HUMAN_APPROVAL_CORRECTIONS",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_EXECUTED",
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
        "source_bindings": {
            "canonical_bundle_sha256": "a" * 64,
            "prior_batch_sha256": "b" * 64,
        },
        "cabinet_records": [
            {
                "cabinet_record_id": "CABINET-001",
                "cabinet_template": "CABINET-A",
                "position_id": "TFE-001",
                "section": "1",
                "source_locator": "specification_position=1.6",
                "items": [correction, reconfirmation],
            },
            {
                "cabinet_record_id": "CABINET-002",
                "cabinet_template": "CABINET-B",
                "position_id": "TFE-002",
                "section": "2",
                "source_locator": "specification_position=2.1",
                "items": [reserved_item(3)],
            },
        ],
    }


def write_json(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "batch-v023.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def cabinet(data: dict[str, Any], index: int) -> dict[str, Any]:
    return cast(list[dict[str, Any]], data["cabinet_records"])[index]


def item(
    data: dict[str, Any],
    cabinet_index: int,
    item_index: int,
) -> dict[str, Any]:
    return cast(
        list[dict[str, Any]],
        cabinet(data, cabinet_index)["items"],
    )[item_index]


def assert_fails(data: Any, expected: str) -> None:
    with pytest.raises(validator.BatchV023ValidationError, match=expected):
        validator.validate_batch_value(data)


def test_synthetic_all_three_kinds_pass_and_preserve_nulls(
    tmp_path: Path,
) -> None:
    data = valid_data()

    counts = validator.validate_batch_value(data)
    result = validator.validate_batch_artifact(write_json(tmp_path, data))

    assert counts == {
        "cabinet_record_count": 2,
        "item_count": 3,
        "component_signature_correction_count": 1,
        "component_reconfirmation_count": 1,
        "reserved_meter_space_count": 1,
        "unique_component_count": 3,
    }
    assert result.status == "PASS"
    assert result.red_flags == []
    assert result.counts == counts
    correction = item(data, 0, 0)
    assert correction["original_signature"]["model_type"] is None
    assert correction["original_signature"]["poles"] is None
    assert correction["approved_signature"]["model_type"] is None
    assert correction["approved_signature"]["poles"] is None


def test_prior_batch_provenance_binding_passes() -> None:
    data = valid_data()
    item(data, 0, 0)["provenance"]["source_artifact_sha256"] = "b" * 64

    counts = validator.validate_batch_value(data)

    assert counts["item_count"] == 3


def test_cli_pass_and_duplicate_json_key_fail(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path, valid_data())
    assert validator.main(["--batch-json", str(path)]) == 0
    output = capsys.readouterr().out
    assert "status: PASS" in output
    assert "item_count: 3" in output

    raw = path.read_text(encoding="utf-8")
    needle = '"batch_id": "023"'
    assert raw.count(needle) == 1
    path.write_text(
        raw.replace(needle, f"{needle}, {needle}", 1),
        encoding="utf-8",
    )
    assert validator.main(["--batch-json", str(path)]) == 1
    output = capsys.readouterr().out
    assert "status: FAIL" in output
    assert "duplicate JSON key: batch_id" in output


def test_correction_equal_signatures_fail() -> None:
    data = valid_data()
    correction = item(data, 0, 0)
    correction["approved_signature"] = copy.deepcopy(correction["original_signature"])

    assert_fails(data, "signature correction requires different signatures")


def test_reconfirmation_different_signatures_fail() -> None:
    data = valid_data()
    reconfirmation = item(data, 0, 1)
    reconfirmation["approved_signature"]["component_identity"] = "OTHER"

    assert_fails(
        data,
        "component reconfirmation requires equal signatures",
    )


def test_quantity_zero_fails() -> None:
    data = valid_data()
    item(data, 0, 0)["quantity_per_cabinet"] = 0

    assert_fails(data, "quantity=0 is forbidden")


def test_reserved_space_rejects_component_quantity() -> None:
    data = valid_data()
    item(data, 1, 0)["quantity_per_cabinet"] = 1

    assert_fails(data, "RESERVED_METER_SPACE item fields mismatch")


def test_reserved_space_cannot_be_installed_component() -> None:
    data = valid_data()
    item(data, 1, 0)["installed_component"] = True

    assert_fails(
        data,
        "reserved meter space cannot be an installed component",
    )


def test_duplicate_comp_between_cabinets_fails() -> None:
    data = valid_data()
    item(data, 1, 0)["component_evidence_id"] = "COMP-001"

    assert_fails(data, "COMP occurs more than once in batch v0.23")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "human_decisions_batch.v9"),
        ("compatible_with", "human_decisions_batch.v0.21"),
        ("batch_id", "999"),
        ("prior_batch_id", "021"),
        ("artifact_status", "DRAFT"),
        ("authority", "OTHER"),
        ("application_status", "APPLIED"),
        ("confirmed_composition_created", True),
        ("pricing_started", True),
        ("downstream_started", True),
    ],
)
def test_root_constants_and_downstream_fail(field: str, value: Any) -> None:
    data = valid_data()
    data[field] = value

    assert_fails(data, f"batch v0.23 {field} mismatch")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("canonical_bundle_sha256", "A" * 64),
        ("prior_batch_sha256", "short"),
    ],
)
def test_invalid_source_sha_fails(field: str, value: str) -> None:
    data = valid_data()
    cast(dict[str, Any], data["source_bindings"])[field] = value

    assert_fails(data, "must be 64 lowercase hex")


def test_exact_fields_and_non_empty_collections_fail() -> None:
    data = valid_data()
    data["unexpected"] = True
    assert_fails(data, "batch v0.23 fields mismatch")

    data = valid_data()
    data["cabinet_records"] = []
    assert_fails(data, "cabinet_records must be non-empty")

    data = valid_data()
    cabinet(data, 0)["items"] = []
    assert_fails(data, "cabinet items must be non-empty")

    data = valid_data()
    item(data, 0, 0)["unexpected"] = True
    assert_fails(data, "COMPONENT_SIGNATURE_CORRECTION item fields mismatch")


def test_duplicate_ids_and_unknown_kind_fail() -> None:
    data = valid_data()
    cabinet(data, 1)["cabinet_record_id"] = "CABINET-001"
    assert_fails(data, "duplicate cabinet_record_id")

    data = valid_data()
    item(data, 0, 1)["item_id"] = "ITEM-001"
    assert_fails(data, "duplicate item_id")

    data = valid_data()
    item(data, 0, 0)["item_kind"] = "UNKNOWN"
    assert_fails(data, "unknown item_kind")


def test_signature_and_provenance_fail_closed() -> None:
    data = valid_data()
    item(data, 0, 1)["approved_signature"]["ratings"] = ["16A", "16A"]
    assert_fails(data, "ratings must be unique")

    data = valid_data()
    item(data, 0, 1)["approved_signature"]["poles"] = 0
    assert_fails(data, "must be a positive integer")

    data = valid_data()
    item(data, 0, 0)["provenance"] = {}
    assert_fails(data, "item provenance fields mismatch")


@pytest.mark.parametrize("reserved_space", [0, 2, True])
def test_reserved_space_must_equal_one(reserved_space: Any) -> None:
    data = valid_data()
    item(data, 1, 0)["reserved_space_per_cabinet"] = reserved_space
    assert_fails(data, "reserved_space_per_cabinet must equal 1")


def test_one_reserved_meter_space_per_cabinet() -> None:
    data = valid_data()
    cast(list[dict[str, Any]], cabinet(data, 1)["items"]).append(reserved_item(4))

    assert_fails(
        data,
        "cabinet record contains more than one reserved meter space",
    )


def test_future_inclusion_requires_exact_value() -> None:
    data = valid_data()
    item(data, 1, 0)["future_inclusion_requires"] = "SEPARATE_APPROVAL"

    assert_fails(data, "reserved space future_inclusion_requires mismatch")


def test_provenance_sha_must_match_source_bindings() -> None:
    data = valid_data()
    item(data, 0, 0)["provenance"]["source_artifact_sha256"] = "c" * 64

    assert_fails(
        data,
        "provenance source SHA-256 is not bound by source_bindings",
    )


def test_reserved_constants_and_downstream_fail() -> None:
    data = valid_data()
    item(data, 1, 0)["requirement_kind"] = "OTHER"
    assert_fails(data, "reserved space requirement_kind mismatch")

    data = valid_data()
    item(data, 1, 0)["meter_connection"] = "OTHER"
    assert_fails(data, "reserved space meter_connection mismatch")

    data = valid_data()
    item(data, 1, 0)["prohibited_downstream"] = ["pricing"]
    assert_fails(data, "reserved space prohibited_downstream mismatch")


def test_item_status_and_missing_file_fail(tmp_path: Path) -> None:
    data = valid_data()
    item(data, 0, 0)["application_status"] = "APPLIED"
    assert_fails(data, "item application_status mismatch")

    result = validator.validate_batch_artifact(tmp_path / "missing.json")
    assert result.status == "FAIL"
    assert result.red_flags
