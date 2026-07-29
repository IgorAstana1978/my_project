import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_human_decisions_batch_v0_22.py"


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_human_decisions_batch_v0_22_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def member(number: int) -> dict[str, Any]:
    return {
        "component_evidence_id": f"COMP-{number:03d}",
        "evidence_position_id": f"TFE-{number:03d}",
        "section": str(number),
        "source_locator": f"table_row={number}; specification_position=1.{number}",
    }


def signature(identity: str) -> dict[str, Any]:
    return {
        "cabinet_template": "CABINET-A",
        "component_identity": identity,
        "model_type": None,
        "ratings": ["10А", "6кА"],
        "poles": 1,
        "functional_role": "AUTOMATIC_PROTECTION",
    }


def common_decision(
    code: str,
    kind: str,
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "decision_id": f"HDA-022-{code}",
        "decision_code": code,
        "decision_kind": kind,
        "accepted_status": "APPROVED_BY_IGOR",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "component_signature": signature(code),
        "members": members,
        "application_status": "NOT_EXECUTED",
    }


def valid_data() -> dict[str, Any]:
    direct = common_decision("H22-D1", "DIRECT_COMPONENT_QUANTITY", [member(1)])
    direct["quantity_per_cabinet"] = 2
    aggregate = common_decision(
        "H22-A1",
        "CABINET_LEVEL_AGGREGATE",
        [member(2), member(3)],
    )
    aggregate.update(
        {
            "aggregate_quantity_per_cabinet": 6,
            "applies_once_per_cabinet": True,
            "multiply_by_member_count": False,
        }
    )
    exclusion = common_decision("H22-X1", "SCOPE_EXCLUSION", [member(4)])
    exclusion.update(
        {
            "scope_status": "NOT_IN_INSTALLED_SCOPE",
            "future_inclusion_requires": (
                "DIRECT_CLIENT_REQUEST_AND_SEPARATE_IGOR_APPROVAL"
            ),
            "prohibited_downstream": [
                "installed_composition",
                "pricing",
                "procurement",
                "production",
            ],
        }
    )
    return {
        "schema_version": "human_decisions_batch.v0.22",
        "compatible_with": "human_decisions_batch.v0.21",
        "case_id": "CASE-V022-SYNTHETIC",
        "project_id": "SYNTHETIC",
        "batch_id": "022",
        "prior_batch_id": "021",
        "artifact_status": "FROZEN_HUMAN_APPROVAL_DECISIONS",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_EXECUTED",
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
        "source_bindings": {
            "canonical_bundle_sha256": "a" * 64,
            "prior_batch_sha256": "b" * 64,
        },
        "quantity_decisions": [direct, aggregate, exclusion],
        "coverage": {
            "direct_component_count": 1,
            "aggregate_member_count": 2,
            "exclusion_component_count": 1,
            "union_component_count": 4,
        },
        "approval_boundary": {
            "application_requires_separate_approval": True,
            "confirmed_composition_requires_separate_approval": True,
        },
        "safety_flags": {
            "batch_applied": False,
            "replay_started": False,
            "frozen_sources_modified": False,
        },
    }


def write_json(tmp_path: Path, data: Any) -> Path:
    path = tmp_path / "batch-v022.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def assert_fails(data: Any, expected: str) -> None:
    with pytest.raises(validator.BatchV022ValidationError, match=expected):
        validator.validate_batch_value(data)


def decision(data: dict[str, Any], index: int) -> dict[str, Any]:
    return cast(list[dict[str, Any]], data["quantity_decisions"])[index]


def test_valid_batch_and_artifact_pass(tmp_path: Path) -> None:
    data = valid_data()
    assert validator.validate_batch_value(data) == data["coverage"]

    result = validator.validate_batch_artifact(write_json(tmp_path, data))

    assert result.status == "PASS"
    assert result.red_flags == []
    assert result.counts == data["coverage"]


def test_cli_pass_and_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    valid_path = write_json(tmp_path, valid_data())
    assert validator.main(["--batch-json", str(valid_path)]) == 0
    output = capsys.readouterr().out
    assert validator.REPORT_START in output
    assert "status: PASS" in output
    assert "union_component_count: 4" in output
    assert validator.REPORT_END in output

    valid_path.write_text("{broken", encoding="utf-8")
    assert validator.main(["--batch-json", str(valid_path)]) == 1
    output = capsys.readouterr().out
    assert "status: FAIL" in output
    assert "red_flag:" in output


def test_missing_file_and_invalid_utf8_fail(tmp_path: Path) -> None:
    missing = validator.validate_batch_artifact(tmp_path / "missing.json")
    assert missing.status == "FAIL"
    assert missing.red_flags

    path = tmp_path / "invalid-utf8.json"
    path.write_bytes(b"\xff")
    invalid = validator.validate_batch_artifact(path)
    assert invalid.status == "FAIL"
    assert invalid.red_flags


def test_root_must_be_exact_object() -> None:
    assert_fails([], "batch v0.22 must be an object")
    data = valid_data()
    data["unexpected"] = True
    assert_fails(data, "batch v0.22 fields mismatch")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "human_decisions_batch.v9"),
        ("compatible_with", "human_decisions_batch.v0.20"),
        ("batch_id", "999"),
        ("prior_batch_id", "020"),
        ("artifact_status", "DRAFT"),
        ("authority", "OTHER"),
        ("application_status", "EXECUTED"),
        ("confirmed_composition_created", True),
        ("pricing_started", True),
        ("downstream_started", True),
    ],
)
def test_root_constants_fail(field: str, value: Any) -> None:
    data = valid_data()
    data[field] = value
    assert_fails(data, f"batch v0.22 {field} mismatch")


@pytest.mark.parametrize("field", ["case_id", "project_id"])
def test_root_strings_must_be_non_empty(field: str) -> None:
    data = valid_data()
    data[field] = ""
    assert_fails(data, f"batch v0.22 {field} must be a non-empty string")


def test_source_bindings_fail_closed() -> None:
    data = valid_data()
    data["source_bindings"] = []
    assert_fails(data, "source_bindings must be an object")

    data = valid_data()
    cast(dict[str, Any], data["source_bindings"])["extra"] = "x"
    assert_fails(data, "source_bindings fields mismatch")

    data = valid_data()
    cast(dict[str, Any], data["source_bindings"])["canonical_bundle_sha256"] = "ABC"
    assert_fails(data, "canonical_bundle_sha256 must be 64 lowercase hex")

    data = valid_data()
    cast(dict[str, Any], data["source_bindings"])["prior_batch_sha256"] = 12
    assert_fails(data, "prior_batch_sha256 must be a non-empty string")


def test_approval_and_safety_fail_closed() -> None:
    data = valid_data()
    cast(dict[str, Any], data["approval_boundary"])[
        "application_requires_separate_approval"
    ] = False
    assert_fails(data, "approval boundary mismatch")

    data = valid_data()
    cast(dict[str, Any], data["approval_boundary"])["extra"] = False
    assert_fails(data, "approval_boundary fields mismatch")

    data = valid_data()
    cast(dict[str, Any], data["safety_flags"])["batch_applied"] = True
    assert_fails(data, "safety flags must remain false")

    data = valid_data()
    cast(dict[str, Any], data["safety_flags"])["extra"] = False
    assert_fails(data, "safety_flags fields mismatch")


def test_decisions_must_be_non_empty_list() -> None:
    data = valid_data()
    data["quantity_decisions"] = {}
    assert_fails(data, "quantity_decisions must be a list")

    data = valid_data()
    data["quantity_decisions"] = []
    assert_fails(data, "quantity_decisions must be non-empty")

    data = valid_data()
    data["quantity_decisions"] = ["not-an-object"]
    assert_fails(data, "quantity decision must be an object")


def test_unknown_kind_and_decision_fields_fail() -> None:
    data = valid_data()
    decision(data, 0)["decision_kind"] = "UNKNOWN"
    assert_fails(data, "unknown decision_kind")

    data = valid_data()
    decision(data, 0)["unexpected"] = True
    assert_fails(data, "DIRECT_COMPONENT_QUANTITY decision fields mismatch")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_id", "", "decision_id must be a non-empty string"),
        ("decision_code", "", "decision_code must be a non-empty string"),
        ("accepted_status", "DRAFT", "accepted_status mismatch"),
        ("authority", "OTHER", "decision authority mismatch"),
        ("application_status", "EXECUTED", "decision must remain NOT_EXECUTED"),
    ],
)
def test_common_decision_fields_fail(
    field: str,
    value: Any,
    message: str,
) -> None:
    data = valid_data()
    decision(data, 0)[field] = value
    assert_fails(data, message)


def test_duplicate_decision_id_or_code_fails() -> None:
    data = valid_data()
    decision(data, 1)["decision_id"] = decision(data, 0)["decision_id"]
    assert_fails(data, "duplicate decision id or code")

    data = valid_data()
    decision(data, 1)["decision_code"] = decision(data, 0)["decision_code"]
    assert_fails(data, "duplicate decision id or code")


def test_signature_fail_closed() -> None:
    data = valid_data()
    decision(data, 0)["component_signature"] = []
    assert_fails(data, "component_signature must be an object")

    data = valid_data()
    signature_value = cast(dict[str, Any], decision(data, 0)["component_signature"])
    signature_value["extra"] = True
    assert_fails(data, "component_signature fields mismatch")

    for field in ("cabinet_template", "component_identity", "functional_role"):
        data = valid_data()
        cast(dict[str, Any], decision(data, 0)["component_signature"])[field] = ""
        assert_fails(data, f"component_signature.{field} must be a non-empty string")

    data = valid_data()
    cast(dict[str, Any], decision(data, 0)["component_signature"])["model_type"] = 1
    assert_fails(data, "component_signature.model_type must be a non-empty string")

    data = valid_data()
    cast(dict[str, Any], decision(data, 0)["component_signature"])["poles"] = 0
    assert_fails(data, "component_signature.poles must be a positive integer")


def test_signature_ratings_fail_closed() -> None:
    data = valid_data()
    cast(dict[str, Any], decision(data, 0)["component_signature"])["ratings"] = {}
    assert_fails(data, "component_signature.ratings must be a list")

    data = valid_data()
    cast(dict[str, Any], decision(data, 0)["component_signature"])["ratings"] = [""]
    assert_fails(data, r"component_signature.ratings\[\] must be a non-empty string")

    data = valid_data()
    cast(dict[str, Any], decision(data, 0)["component_signature"])["ratings"] = [
        "10А",
        "10А",
    ]
    assert_fails(data, "component_signature ratings must be unique")


def test_members_fail_closed() -> None:
    data = valid_data()
    decision(data, 0)["members"] = {}
    assert_fails(data, "decision members must be a list")

    data = valid_data()
    decision(data, 0)["members"] = []
    assert_fails(data, "decision members must be non-empty")

    data = valid_data()
    cast(list[Any], decision(data, 0)["members"])[0] = []
    assert_fails(data, "decision member must be an object")

    data = valid_data()
    cast(list[dict[str, Any]], decision(data, 0)["members"])[0]["extra"] = True
    assert_fails(data, "decision member fields mismatch")

    for field, label in (
        ("component_evidence_id", "member component_evidence_id"),
        ("evidence_position_id", "member evidence_position_id"),
        ("section", "member section"),
        ("source_locator", "member source_locator"),
    ):
        data = valid_data()
        cast(list[dict[str, Any]], decision(data, 0)["members"])[0][field] = ""
        assert_fails(data, f"{label} must be a non-empty string")


def test_duplicate_member_and_cross_decision_coverage_fail() -> None:
    data = valid_data()
    decision(data, 0)["members"] = [member(1), member(1)]
    assert_fails(data, "duplicate COMP within decision")

    data = valid_data()
    decision(data, 1)["members"] = [member(1)]
    assert_fails(data, "COMP covered by more than one decision")


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_direct_quantity_must_be_positive_integer(value: Any) -> None:
    data = valid_data()
    decision(data, 0)["quantity_per_cabinet"] = value
    expected = (
        "quantity=0 is forbidden"
        if value == 0 and not isinstance(value, bool)
        else "quantity_per_cabinet must be a positive integer"
    )
    assert_fails(data, expected)


def test_aggregate_quantity_and_single_application_fail_closed() -> None:
    data = valid_data()
    decision(data, 1)["aggregate_quantity_per_cabinet"] = -1
    assert_fails(data, "aggregate_quantity_per_cabinet must be a positive integer")

    data = valid_data()
    decision(data, 1)["applies_once_per_cabinet"] = False
    assert_fails(data, "aggregate must apply once")

    data = valid_data()
    decision(data, 1)["multiply_by_member_count"] = True
    assert_fails(data, "aggregate must apply once")


def test_scope_exclusion_fail_closed() -> None:
    data = valid_data()
    decision(data, 2)["scope_status"] = "UNKNOWN"
    assert_fails(data, "scope exclusion status is not allowed")

    data = valid_data()
    decision(data, 2)["future_inclusion_requires"] = ""
    assert_fails(data, "future_inclusion_requires must be a non-empty string")

    data = valid_data()
    decision(data, 2)["prohibited_downstream"] = {}
    assert_fails(data, "prohibited_downstream must be a list")

    data = valid_data()
    decision(data, 2)["prohibited_downstream"] = ["pricing"]
    assert_fails(data, "prohibited_downstream mismatch")

    data = valid_data()
    decision(data, 2)["quantity"] = 0
    assert_fails(data, "quantity=0 is forbidden")


def test_coverage_is_exact_and_computed() -> None:
    data = valid_data()
    data["coverage"] = []
    assert_fails(data, "coverage must be an object")

    data = valid_data()
    cast(dict[str, Any], data["coverage"])["extra"] = 0
    assert_fails(data, "coverage fields mismatch")

    data = valid_data()
    cast(dict[str, Any], data["coverage"])["direct_component_count"] = 2
    assert_fails(data, "coverage direct_component_count mismatch")


def test_parse_args_returns_path() -> None:
    args = validator.parse_args(["--batch-json", "batch.json"])
    assert args.batch_json == Path("batch.json")


def test_valid_nullable_signature_fields_and_default_scope_status() -> None:
    data = copy.deepcopy(valid_data())
    signature_value = cast(dict[str, Any], decision(data, 0)["component_signature"])
    signature_value["model_type"] = "MODEL-1"
    signature_value["poles"] = None
    decision(data, 2)["scope_status"] = "NOT_IN_INSTALLED_SCOPE_BY_DEFAULT"

    assert validator.validate_batch_value(data)["union_component_count"] == 4
