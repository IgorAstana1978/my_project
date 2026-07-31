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
    / "apply_human_decisions_batch_v0_23_to_component_replay.py"
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
    load_module("apply_v023_for_test", APPLICATION_SCRIPT),
)


def canonical_record(number: int, label: str) -> dict[str, Any]:
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
            canonical_record(1, "LOAD SWITCH"),
            canonical_record(2, "BREAKER"),
            canonical_record(3, "METER"),
            canonical_record(4, "UNTOUCHED"),
        ],
    }


def member(number: int) -> dict[str, Any]:
    return {
        "component_evidence_id": f"COMP-{number:03d}",
        "evidence_position_id": f"TFE-{number:03d}",
        "section": str(number),
        "source_locator": (f"table_row={number}; specification_position=1.{number}"),
    }


def prior_signature(identity: str) -> dict[str, Any]:
    return {
        "cabinet_template": "CABINET-A",
        "component_identity": identity,
        "model_type": None,
        "ratings": ["10А"],
        "poles": 1,
        "functional_role": "PROTECTION",
    }


def v023_signature(identity: str) -> dict[str, Any]:
    return {
        "component_identity": identity,
        "model_type": None,
        "ratings": ["10А"],
        "poles": 1,
        "functional_role": "PROTECTION",
    }


def prior_decision(
    number: int,
    kind: str,
    identity: str,
) -> dict[str, Any]:
    decision: dict[str, Any] = {
        "decision_id": f"HDA-022-D{number}",
        "decision_code": f"H22-D{number}",
        "decision_kind": kind,
        "accepted_status": "APPROVED_BY_IGOR",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "component_signature": prior_signature(identity),
        "members": [member(number)],
        "application_status": "NOT_EXECUTED",
    }
    if kind == "DIRECT_COMPONENT_QUANTITY":
        decision["quantity_per_cabinet"] = number
    else:
        decision.update(
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
    return decision


def prior_batch_data(canonical_sha256: str) -> dict[str, Any]:
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
        "quantity_decisions": [
            prior_decision(1, "DIRECT_COMPONENT_QUANTITY", "RAW APPARATUS"),
            prior_decision(2, "DIRECT_COMPONENT_QUANTITY", "BREAKER"),
            prior_decision(3, "SCOPE_EXCLUSION", "METER"),
        ],
        "coverage": {
            "direct_component_count": 2,
            "aggregate_member_count": 0,
            "exclusion_component_count": 1,
            "union_component_count": 3,
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


def provenance(number: int, canonical_sha256: str) -> dict[str, Any]:
    return {
        "source_artifact_sha256": canonical_sha256,
        "source_record_id": f"COMP-{number:03d}",
        "source_locator": (f"table_row={number}; specification_position=1.{number}"),
    }


def correction_item(canonical_sha256: str) -> dict[str, Any]:
    original = v023_signature("RAW APPARATUS")
    approved = v023_signature("LOAD SWITCH")
    return {
        "item_id": "ITEM-001",
        "item_kind": "COMPONENT_SIGNATURE_CORRECTION",
        "component_evidence_id": "COMP-001",
        "original_signature": original,
        "approved_signature": approved,
        "quantity_per_cabinet": 1,
        "provenance": provenance(1, canonical_sha256),
        "correction_reason": "DIRECT_IGOR_TECHNICAL_SIGNATURE_DECISION",
        "application_status": "NOT_EXECUTED",
    }


def reconfirmation_item(canonical_sha256: str) -> dict[str, Any]:
    confirmed = v023_signature("BREAKER")
    return {
        "item_id": "ITEM-002",
        "item_kind": "COMPONENT_RECONFIRMATION",
        "component_evidence_id": "COMP-002",
        "original_signature": confirmed,
        "approved_signature": copy.deepcopy(confirmed),
        "quantity_per_cabinet": 2,
        "provenance": provenance(2, canonical_sha256),
        "correction_reason": "DIRECT_IGOR_COMPONENT_RECONFIRMATION",
        "application_status": "NOT_EXECUTED",
    }


def reserved_item(canonical_sha256: str) -> dict[str, Any]:
    return {
        "item_id": "ITEM-003",
        "item_kind": "RESERVED_METER_SPACE",
        "component_evidence_id": "COMP-003",
        "requirement_kind": "RESERVED_METER_SPACE",
        "meter_connection": "THREE_PHASE_DIRECT",
        "reserved_space_per_cabinet": 1,
        "installed_component": False,
        "original_identity": "METER",
        "provenance": provenance(3, canonical_sha256),
        "future_inclusion_requires": ("SEPARATE_METER_SELECTION_AND_IGOR_APPROVAL"),
        "prohibited_downstream": [
            "installed_composition",
            "pricing",
            "procurement",
            "production",
        ],
        "application_status": "NOT_EXECUTED",
    }


def cabinet(
    number: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "cabinet_record_id": f"CABINET-{number:03d}",
        "cabinet_template": "CABINET-A",
        "position_id": f"TFE-{number:03d}",
        "section": str(number),
        "source_locator": f"specification_position=1.{number}",
        "items": items,
    }


def correction_batch_data(
    canonical_sha256: str,
    prior_sha256: str,
) -> dict[str, Any]:
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
            "canonical_bundle_sha256": canonical_sha256,
            "prior_batch_sha256": prior_sha256,
        },
        "cabinet_records": [
            cabinet(
                1,
                [
                    correction_item(canonical_sha256),
                ],
            ),
            cabinet(
                2,
                [
                    reconfirmation_item(canonical_sha256),
                ],
            ),
            cabinet(
                3,
                [
                    reserved_item(canonical_sha256),
                ],
            ),
        ],
    }


def rewrite_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def write_inputs(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    Path,
    Path,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    canonical = canonical_data()
    canonical_path = tmp_path / "canonical.json"
    rewrite_json(canonical_path, canonical)
    canonical_sha256 = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    prior = prior_batch_data(canonical_sha256)
    prior_path = tmp_path / "prior-v022.json"
    rewrite_json(prior_path, prior)
    prior_sha256 = hashlib.sha256(prior_path.read_bytes()).hexdigest()
    correction = correction_batch_data(canonical_sha256, prior_sha256)
    correction_path = tmp_path / "correction-v023.json"
    rewrite_json(correction_path, correction)
    return (
        canonical_path,
        prior_path,
        correction_path,
        tmp_path / "applied-v023.json",
        canonical,
        prior,
        correction,
    )


def assert_application_fails(
    canonical_path: Path,
    prior_path: Path,
    correction_path: Path,
    output_path: Path,
    expected: str,
) -> None:
    result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert result.output_created is False
    assert expected in result.red_flags[0]
    assert not output_path.exists()
    assert not list(output_path.parent.glob(f".{output_path.name}.*.tmp"))


def replace_canonical_binding_and_provenance(
    data: dict[str, Any],
) -> None:
    bindings = cast(dict[str, str], data["source_bindings"])
    original_sha256 = bindings["canonical_bundle_sha256"]
    replacement_sha256 = "f" * 64
    bindings["canonical_bundle_sha256"] = replacement_sha256
    for cabinet_record in cast(
        list[dict[str, Any]],
        data["cabinet_records"],
    ):
        for batch_item in cast(
            list[dict[str, Any]],
            cabinet_record["items"],
        ):
            item_provenance = cast(dict[str, str], batch_item["provenance"])
            if item_provenance["source_artifact_sha256"] == original_sha256:
                item_provenance["source_artifact_sha256"] = replacement_sha256
    application.V023_VALIDATOR.validate_batch_value(data)


def test_pass_applies_v022_then_all_v023_kinds_without_mutation(
    tmp_path: Path,
) -> None:
    (
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        canonical,
        _,
        _,
    ) = write_inputs(tmp_path)
    before = {
        path: path.read_bytes()
        for path in (canonical_path, prior_path, correction_path)
    }

    result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
    )

    assert result.status == "PASS"
    assert result.output_created is True
    applied = cast(dict[str, Any], json.loads(output_path.read_bytes()))
    assert application._validate_generated_value(applied) == result.counts
    assert applied["application_order"] == [
        "human_decisions_batch.v0.22",
        "human_decisions_batch.v0.23",
    ]
    assert (
        applied["canonical_component_evidence_records"]
        == canonical["identified_component_evidence_records"]
    )
    assert applied["confirmed_composition_created"] is False
    assert applied["pricing_started"] is False
    assert applied["downstream_started"] is False
    overlays = cast(
        list[dict[str, Any]],
        applied["component_signature_overlays"],
    )
    assert {item["item_kind"] for item in overlays} == {
        "COMPONENT_SIGNATURE_CORRECTION",
        "COMPONENT_RECONFIRMATION",
    }
    assert all(item["canonical_evidence_modified"] is False for item in overlays)
    requirements = cast(
        list[dict[str, Any]],
        applied["reserved_meter_space_requirements"],
    )
    assert len(requirements) == 1
    assert requirements[0]["installed_component"] is False
    assert requirements[0]["canonical_evidence_modified"] is False
    assert "COMP-004" not in {
        item["component_evidence_id"] for item in overlays + requirements
    }
    assert all(path.read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda data: data["cabinet_records"][0]["items"][0][
                "approved_signature"
            ].update({"component_identity": "OTHER"}),
            "approved identity does not match canonical replay",
        ),
        (
            lambda data: data["cabinet_records"][0]["items"][0]["provenance"].update(
                {"source_locator": "table_row=999"}
            ),
            "item source locator does not match canonical replay",
        ),
        (
            replace_canonical_binding_and_provenance,
            "batch v0.23 canonical SHA-256 binding mismatch",
        ),
        (
            lambda data: data["cabinet_records"][2]["items"][0].update(
                {"component_evidence_id": "COMP-002"}
            ),
            "COMP occurs more than once",
        ),
        (
            lambda data: data["cabinet_records"][2]["items"][0].update(
                {"installed_component": True}
            ),
            "reserved meter space cannot be an installed component",
        ),
        (
            lambda data: data["cabinet_records"][0]["items"][0].update(
                {"original_signature": v023_signature("OTHER RAW")}
            ),
            "original signature does not match batch v0.22",
        ),
    ],
)
def test_semantic_and_boundary_mismatches_fail_without_output(
    tmp_path: Path,
    mutation: Any,
    expected: str,
) -> None:
    (
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        _,
        _,
        correction,
    ) = write_inputs(tmp_path)
    mutation(correction)
    rewrite_json(correction_path, correction)

    assert_application_fails(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        expected,
    )


@pytest.mark.parametrize("overwrite", [False, True])
def test_inside_git_output_is_blocked_even_with_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overwrite: bool,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    monkeypatch.setattr(application, "PROJECT_ROOT", project_root)
    canonical_path, prior_path, correction_path, _, _, _, _ = write_inputs(tmp_path)
    output_path = project_root / "applied-v023.json"

    result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        overwrite=overwrite,
    )

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output JSON must be outside the Git project" in result.red_flags[0]
    assert not output_path.exists()
    assert not list(project_root.glob(f".{output_path.name}.*.tmp"))


@pytest.mark.parametrize("input_index", [0, 1, 2])
def test_output_cannot_alias_any_frozen_input_even_with_overwrite(
    tmp_path: Path,
    input_index: int,
) -> None:
    canonical_path, prior_path, correction_path, _, _, _, _ = write_inputs(tmp_path)
    input_paths = (canonical_path, prior_path, correction_path)
    before = {path: path.read_bytes() for path in input_paths}
    input_path = input_paths[input_index]

    same_path_result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        input_path,
        overwrite=True,
    )

    assert same_path_result.status == "FAIL"
    assert same_path_result.output_created is False
    assert (
        "output JSON must not alias an input artifact" in same_path_result.red_flags[0]
    )
    assert {path: path.read_bytes() for path in input_paths} == before
    assert not list(tmp_path.glob(f".{input_path.name}.*.tmp"))

    output_path = input_path.parent / "lexical-alias" / ".." / input_path.name
    assert output_path != input_path
    assert output_path.resolve(strict=False) == input_path.resolve(strict=False)

    result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        overwrite=True,
    )

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "output JSON must not alias an input artifact" in result.red_flags[0]
    assert {path: path.read_bytes() for path in input_paths} == before
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))


def test_prior_only_unknown_comp_fails_without_output_or_temp(
    tmp_path: Path,
) -> None:
    (
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        _,
        prior,
        correction,
    ) = write_inputs(tmp_path)
    prior["quantity_decisions"].append(
        prior_decision(5, "DIRECT_COMPONENT_QUANTITY", "UNKNOWN")
    )
    prior["coverage"]["direct_component_count"] = 3
    prior["coverage"]["union_component_count"] = 4
    rewrite_json(prior_path, prior)
    correction["source_bindings"]["prior_batch_sha256"] = hashlib.sha256(
        prior_path.read_bytes()
    ).hexdigest()
    rewrite_json(correction_path, correction)

    assert_application_fails(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        "batch v0.22 COMP is absent from canonical replay: COMP-005",
    )


def test_atomic_failure_leaves_no_output_or_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_path, prior_path, correction_path, output_path, _, _, _ = write_inputs(
        tmp_path
    )

    def fail_link(source: Path, target: Path) -> None:
        raise OSError(f"synthetic atomic failure: {source} -> {target}")

    monkeypatch.setattr(application.os, "link", fail_link)
    result = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
    )

    assert result.status == "FAIL"
    assert result.output_created is False
    assert "synthetic atomic failure" in result.red_flags[0]
    assert not output_path.exists()
    assert not list(tmp_path.glob(f".{output_path.name}.*.tmp"))


def test_existing_output_requires_explicit_outside_git_overwrite(
    tmp_path: Path,
) -> None:
    canonical_path, prior_path, correction_path, output_path, _, _, _ = write_inputs(
        tmp_path
    )
    output_path.write_text("existing", encoding="utf-8")

    blocked = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
    )
    assert blocked.status == "FAIL"
    assert output_path.read_text(encoding="utf-8") == "existing"

    replaced = application.apply_artifacts(
        canonical_path,
        prior_path,
        correction_path,
        output_path,
        overwrite=True,
    )
    assert replaced.status == "PASS"
    assert json.loads(output_path.read_bytes())["schema_version"] == (
        "component_replay_applied_bundle.v0.23"
    )


def test_cli_pass_and_help_expose_three_inputs_and_safety(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canonical_path, prior_path, correction_path, output_path, _, _, _ = write_inputs(
        tmp_path
    )
    assert (
        application.main(
            [
                "--canonical-replay",
                str(canonical_path),
                "--prior-batch-json",
                str(prior_path),
                "--correction-batch-json",
                str(correction_path),
                "--output-json",
                str(output_path),
            ]
        )
        == 0
    )
    assert "status: PASS" in capsys.readouterr().out

    with pytest.raises(SystemExit) as error:
        application.parse_args(["--help"])
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    assert "--prior-batch-json" in help_text
    assert "--correction-batch-json" in help_text
    assert "outside the Git project" in help_text
    assert "--overwrite" in help_text
