import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "apply_human_decisions_batch_v0_22_to_component_replay.py"
)
VALIDATOR_SCRIPT = (
    PROJECT_ROOT / "scripts" / "validate_component_replay_applied_bundle_v0_22.py"
)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


application = cast(
    Any,
    load_module("apply_v022_for_test", APPLICATION_SCRIPT),
)
validator = cast(
    Any,
    load_module("validate_applied_v022_for_test", VALIDATOR_SCRIPT),
)


def canonical_record(
    number: int,
    label: str,
) -> dict[str, Any]:
    return {
        "component_evidence_id": f"COMP-{number:03d}",
        "document_id": "synthetic-source.pdf",
        "label": label,
        "position_id": f"TFE-{number:03d}",
        "provenance": {
            "pdf": "synthetic-source.pdf",
            "pdf_sha256": "c" * 64,
            "page": number,
            "row_locator": f"table_row={number}",
            "specification_position_or_locator": (f"specification_position=1.{number}"),
            "source_record_ids": [f"SOURCE-{number:03d}"],
            "source_decision_ids": [],
        },
        "section_id": str(number),
        "source_status": "PROJECT_EVIDENCE_UNAPPROVED",
    }


def canonical_data() -> dict[str, Any]:
    return {
        "schema_version": "component_replay_readiness_bundle.v0.2",
        "project_id": "SYNTHETIC",
        "identified_component_evidence_records": [
            canonical_record(1, "BREAKER"),
            canonical_record(2, "CONTACT"),
            canonical_record(3, "CONTACT"),
            canonical_record(4, "SPARE"),
        ],
    }


def member(number: int) -> dict[str, Any]:
    return {
        "component_evidence_id": f"COMP-{number:03d}",
        "evidence_position_id": f"TFE-{number:03d}",
        "section": str(number),
        "source_locator": (f"table_row={number}; specification_position=1.{number}"),
    }


def signature(identity: str, poles: int | None = 1) -> dict[str, Any]:
    return {
        "cabinet_template": "CABINET-A",
        "component_identity": identity,
        "model_type": None,
        "ratings": ["10А", "6кА"],
        "poles": poles,
        "functional_role": "AUTOMATIC_PROTECTION",
    }


def common_decision(
    code: str,
    kind: str,
    identity: str,
    members: list[dict[str, Any]],
    *,
    poles: int | None = 1,
) -> dict[str, Any]:
    return {
        "decision_id": f"HDA-022-{code}",
        "decision_code": code,
        "decision_kind": kind,
        "accepted_status": "APPROVED_BY_IGOR",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "component_signature": signature(identity, poles),
        "members": members,
        "application_status": "NOT_EXECUTED",
    }


def batch_data(canonical_sha256: str) -> dict[str, Any]:
    direct = common_decision(
        "H22-D1",
        "DIRECT_COMPONENT_QUANTITY",
        "BREAKER",
        [member(1)],
        poles=None,
    )
    direct["quantity_per_cabinet"] = 2
    aggregate = common_decision(
        "H22-A1",
        "CABINET_LEVEL_AGGREGATE",
        "CONTACT",
        [member(2), member(3)],
    )
    aggregate.update(
        {
            "aggregate_quantity_per_cabinet": 6,
            "applies_once_per_cabinet": True,
            "multiply_by_member_count": False,
        }
    )
    exclusion = common_decision(
        "H22-X1",
        "SCOPE_EXCLUSION",
        "SPARE",
        [member(4)],
    )
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
            "canonical_bundle_sha256": canonical_sha256,
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


def write_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    canonical = canonical_data()
    canonical_path = tmp_path / "canonical.json"
    canonical_path.write_text(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    canonical_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    batch = batch_data(canonical_sha256)
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps(batch, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return (
        canonical_path,
        batch_path,
        tmp_path / "applied.json",
        canonical,
        batch,
    )


def rewrite_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def decision(
    batch: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    return cast(list[dict[str, Any]], batch["quantity_decisions"])[index]


def applied_data(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_bytes()))


def assert_application_fails(
    canonical_path: Path,
    batch_path: Path,
    output_path: Path,
    expected: str,
) -> None:
    result = application.apply_artifacts(
        canonical_path,
        batch_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert result.output_created is False
    assert expected in result.red_flags[0]
    assert not output_path.exists()


def assert_validation_fails(value: Any, expected: str) -> None:
    with pytest.raises(
        validator.AppliedBundleV022ValidationError,
        match=expected,
    ):
        validator.validate_applied_value(value)


def test_pass_projects_three_kinds_without_mutating_inputs(
    tmp_path: Path,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    canonical_before = canonical_path.read_bytes()
    batch_before = batch_path.read_bytes()

    result = application.apply_artifacts(
        canonical_path,
        batch_path,
        output_path,
    )

    assert result.status == "PASS"
    assert result.output_created is True
    assert result.counts == {
        "direct_component_count": 1,
        "aggregate_member_count": 2,
        "exclusion_component_count": 1,
        "union_component_count": 4,
    }
    applied = applied_data(output_path)
    assert validator.validate_applied_value(applied) == result.counts
    assert applied["source_lineage"]["batch_id"] == "022"
    assert applied["source_lineage"]["prior_batch_id"] == "021"
    direct = applied["direct_component_quantities"][0]
    assert direct["quantity_per_cabinet"] == 2
    assert direct["component_signature"]["poles"] is None
    aggregate = applied["cabinet_level_aggregates"][0]
    assert aggregate["aggregate_quantity_per_cabinet"] == 6
    assert aggregate["applies_once_per_cabinet"] is True
    assert aggregate["multiply_by_member_count"] is False
    assert all(
        not any("quantity" in key for key in member) for member in aggregate["members"]
    )
    exclusion = applied["scope_exclusions"][0]
    assert not any("quantity" in key for key in exclusion)
    assert exclusion["members"][0]["canonical_provenance"]
    assert canonical_path.read_bytes() == canonical_before
    assert batch_path.read_bytes() == batch_before


def test_cli_application_then_independent_validator_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)

    assert (
        application.main(
            [
                "--canonical-replay",
                str(canonical_path),
                "--batch-json",
                str(batch_path),
                "--output-json",
                str(output_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "status: PASS" in output
    assert "output_created: true" in output

    validation = validator.validate_applied_bundle(output_path)
    assert validation.status == "PASS"
    assert validation.red_flags == []
    assert validation.counts["union_component_count"] == 4


@pytest.mark.parametrize(
    ("needle", "replacement", "duplicate_key"),
    [
        (
            '"schema_version":"component_replay_applied_bundle.v0.22"',
            (
                '"schema_version":"component_replay_applied_bundle.v0.22",'
                '"schema_version":"component_replay_applied_bundle.v0.22"'
            ),
            "schema_version",
        ),
        (
            '"batch_id":"022"',
            '"batch_id":"022","batch_id":"022"',
            "batch_id",
        ),
    ],
)
def test_validator_cli_rejects_duplicate_json_keys(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    needle: str,
    replacement: str,
    duplicate_key: str,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    assert (
        application.apply_artifacts(
            canonical_path,
            batch_path,
            output_path,
        ).status
        == "PASS"
    )
    raw_json = output_path.read_text(encoding="utf-8")
    assert raw_json.count(needle) == 1
    invalid_path = tmp_path / f"duplicate-{duplicate_key}.json"
    invalid_path.write_text(
        raw_json.replace(needle, replacement, 1),
        encoding="utf-8",
    )

    assert validator.main(["--bundle-json", str(invalid_path)]) == 1
    output = capsys.readouterr().out
    assert "status: FAIL" in output
    assert f"duplicate JSON key: {duplicate_key}" in output


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("batch_id", "999"),
        ("prior_batch_id", "020"),
    ],
)
def test_validator_requires_exact_lineage_batch_ids(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    assert (
        application.apply_artifacts(
            canonical_path,
            batch_path,
            output_path,
        ).status
        == "PASS"
    )
    applied = applied_data(output_path)
    applied["source_lineage"][field] = value

    assert_validation_fails(
        applied,
        f"source lineage {field} mismatch",
    )


def test_duplicate_comp_fails_before_output(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    decision(batch, 1)["members"][0] = member(1)
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "COMP covered by more than one decision",
    )


def test_zero_quantity_fails_before_output(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    decision(batch, 0)["quantity_per_cabinet"] = 0
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "quantity=0 is forbidden",
    )


def test_wrong_batch_coverage_fails_before_output(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    cast(dict[str, int], batch["coverage"])["union_component_count"] = 5
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "coverage union_component_count mismatch",
    )


def test_incompatible_project_id_fails_before_output(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    batch["project_id"] = "OTHER"
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "project_id mismatch",
    )


def test_invalid_source_lineage_fails_before_output(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    cast(dict[str, Any], batch["source_bindings"])["canonical_bundle_sha256"] = "f" * 64
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "canonical source lineage SHA-256 mismatch",
    )


def test_canonical_fingerprint_mismatch_fails_before_output(
    tmp_path: Path,
) -> None:
    canonical_path, batch_path, output_path, _, batch = write_inputs(tmp_path)
    decision(batch, 0)["members"][0]["source_locator"] = "table_row=999"
    rewrite_json(batch_path, batch)

    assert_application_fails(
        canonical_path,
        batch_path,
        output_path,
        "source_locator does not match canonical replay",
    )


def test_existing_output_is_preserved(tmp_path: Path) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    output_path.write_text("existing", encoding="utf-8")

    result = application.apply_artifacts(
        canonical_path,
        batch_path,
        output_path,
    )

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output already exists" in result.red_flags[0]
    assert output_path.read_text(encoding="utf-8") == "existing"


def test_atomic_failure_leaves_no_output_or_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)

    def fail_link(source: Path, target: Path) -> None:
        raise OSError(f"synthetic atomic failure: {source} -> {target}")

    monkeypatch.setattr(application.os, "link", fail_link)
    result = application.apply_artifacts(
        canonical_path,
        batch_path,
        output_path,
    )

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "synthetic atomic failure" in result.red_flags[0]
    assert not output_path.exists()
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))


def test_applied_validator_rejects_duplicate_comp_and_bad_coverage(
    tmp_path: Path,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    assert (
        application.apply_artifacts(
            canonical_path,
            batch_path,
            output_path,
        ).status
        == "PASS"
    )
    applied = applied_data(output_path)

    duplicate = copy.deepcopy(applied)
    duplicate["cabinet_level_aggregates"][0]["members"][0][
        "component_evidence_id"
    ] = "COMP-001"
    assert_validation_fails(
        duplicate,
        "COMP covered by more than one decision",
    )

    bad_coverage = copy.deepcopy(applied)
    bad_coverage["coverage"]["union_component_count"] = 99
    assert_validation_fails(
        bad_coverage,
        "coverage union_component_count mismatch",
    )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda data: data["source_lineage"].update(
                {"canonical_replay_sha256": "INVALID"}
            ),
            "must be 64 lowercase hex",
        ),
        (
            lambda data: data["cabinet_level_aggregates"][0].update(
                {"multiply_by_member_count": True}
            ),
            "aggregate must apply once",
        ),
        (
            lambda data: data["scope_exclusions"][0].update(
                {"quantity_per_cabinet": 1}
            ),
            "SCOPE_EXCLUSION decision fields mismatch",
        ),
        (
            lambda data: data.update({"downstream_started": True}),
            "downstream_started mismatch",
        ),
    ],
)
def test_applied_validator_rejects_contract_violations(
    tmp_path: Path,
    mutator: Any,
    expected: str,
) -> None:
    canonical_path, batch_path, output_path, _, _ = write_inputs(tmp_path)
    assert (
        application.apply_artifacts(
            canonical_path,
            batch_path,
            output_path,
        ).status
        == "PASS"
    )
    applied = applied_data(output_path)
    mutator(applied)

    assert_validation_fails(applied, expected)
