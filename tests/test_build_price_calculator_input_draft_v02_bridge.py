from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "build_price_calculator_input_draft_v02_bridge.py"
)
SOURCE_FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "test_build_confirmed_composition_from_preliminary_bundle.py"
)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bridge = load_module(SCRIPT_PATH, "pricing_input_v02_bridge_under_test")
source_fixtures = load_module(
    SOURCE_FIXTURE_PATH,
    "confirmed_composition_source_fixtures_for_bridge_test",
)
validator = bridge.load_validator_module()


def make_multi_member_aggregate(data: dict[str, Any]) -> None:
    prior = data["prior_v0_22_application"]
    moved = prior["direct_component_quantities"][-2:]
    del prior["direct_component_quantities"][-2:]
    aggregate = prior["cabinet_level_aggregates"][0]
    target_label = aggregate["component_signature"]["component_identity"]
    for decision in moved:
        member = decision["members"][0]
        component_id = member["component_evidence_id"]
        member["canonical_label"] = target_label
        aggregate["members"].append(member)
        for canonical in data["canonical_component_evidence_records"]:
            if canonical["component_evidence_id"] == component_id:
                canonical["label"] = target_label
        for overlay in data["component_signature_overlays"]:
            if overlay["component_evidence_id"] == component_id:
                overlay["original_signature"]["component_identity"] = target_label
                overlay["approved_signature"]["component_identity"] = target_label
    prior["coverage"]["direct_component_count"] = 15
    prior["coverage"]["aggregate_member_count"] = 3
    data["coverage"]["prior_direct_component_count"] = 15
    data["coverage"]["prior_aggregate_member_count"] = 3


def synthetic_applied_bundle() -> dict[str, Any]:
    data = cast(dict[str, Any], source_fixtures.valid_applied_bundle())
    make_multi_member_aggregate(data)
    direct = data["prior_v0_22_application"]["direct_component_quantities"]
    for decision in direct[8:]:
        decision["component_signature"]["cabinet_template"] = "SYNTHETIC-CABINET-B"
    for overlay in data["component_signature_overlays"]:
        overlay["cabinet_template"] = "OVERLAY-TEMPLATE-MUST-NOT-GROUP"
    return data


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def confirmed_from_applied(applied_path: Path) -> dict[str, Any]:
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    return {
        "schema_version": "confirmed_composition_artifact.v0.2",
        "project_id": snapshot.data["project_id"],
        "confirmation_id": "CONFIRM-SYNTHETIC-V023-BRIDGE-001",
        "confirmed_by": "Igor",
        "confirmed_at": "2026-08-03T10:00:00+05:00",
        "approval": {
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "approved_by": "Igor",
            "approval_phrase": "CONFIRM TECHNICAL COMPOSITION",
            "approval_channel": "synthetic_test",
        },
        "source_lineage": {
            "applied_bundle_sha256": snapshot.sha256,
            "applied_bundle_schema_version": ("component_replay_applied_bundle.v0.23"),
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


def write_inputs(
    tmp_path: Path,
    *,
    applied_mutator: Callable[[dict[str, Any]], None] | None = None,
    confirmed_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Path, Path, Path]:
    applied = synthetic_applied_bundle()
    if applied_mutator is not None:
        applied_mutator(applied)
    applied_path = tmp_path / "component-replay-applied-bundle-v0.23.json"
    write_json(applied_path, applied)
    confirmed = confirmed_from_applied(applied_path)
    if confirmed_mutator is not None:
        confirmed_mutator(confirmed)
    confirmed_path = tmp_path / "confirmed-composition-artifact.json"
    write_json(confirmed_path, confirmed)
    return confirmed_path, applied_path, tmp_path / "pricing-input-draft-v0.2.json"


def run_success(tmp_path: Path) -> tuple[Any, dict[str, Any], Path, Path]:
    confirmed_path, applied_path, output_path = write_inputs(tmp_path)
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "PASS", result.red_flags
    return (
        result,
        json.loads(output_path.read_text(encoding="utf-8")),
        confirmed_path,
        applied_path,
    )


def aggregate_components(
    confirmed: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        component
        for component in confirmed["installed_components"]
        if component["quantity"]["decision_kind"] == "CABINET_LEVEL_AGGREGATE"
    ]


def test_valid_direct_projection_preserves_exact_quantity_and_singleton_comp(
    tmp_path: Path,
) -> None:
    _, payload, _, _ = run_success(tmp_path)
    direct_rows = [
        row
        for row in payload["calculator_input_format"]["row_drafts"]
        if row["source_quantity"]["decision_kind"] == "DIRECT_COMPONENT_QUANTITY"
    ]
    assert len(direct_rows) == 15
    assert all(len(row["source_component_evidence_ids"]) == 1 for row in direct_rows)
    assert all(
        row["calculator_values"]["component_qty"]
        == row["source_quantity"]["quantity_per_cabinet"]
        for row in direct_rows
    )


def test_multi_member_aggregate_produces_one_non_multiplied_row(
    tmp_path: Path,
) -> None:
    _, payload, _, _ = run_success(tmp_path)
    aggregate_rows = [
        row
        for row in payload["calculator_input_format"]["row_drafts"]
        if row["source_quantity"]["decision_kind"] == "CABINET_LEVEL_AGGREGATE"
    ]
    assert len(aggregate_rows) == 1
    assert len(aggregate_rows[0]["source_component_evidence_ids"]) == 3
    assert aggregate_rows[0]["calculator_values"]["component_qty"] == 3
    assert aggregate_rows[0]["source_quantity"] == {
        "decision_id": "DEC-018",
        "decision_kind": "CABINET_LEVEL_AGGREGATE",
        "aggregate_quantity_per_cabinet": 3,
        "applies_once_per_cabinet": True,
        "multiply_by_member_count": False,
    }


def test_aggregate_member_signature_mismatch_fails_closed(tmp_path: Path) -> None:
    confirmed_path, applied_path, _ = write_inputs(tmp_path)
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    components = aggregate_components(confirmed)
    components[1]["approved_signature"]["functional_role"] = "different"
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    with pytest.raises(bridge.BridgeError, match="signature mismatch"):
        bridge.project_rows_and_groups(confirmed, snapshot.data)


def test_aggregate_member_quantity_mismatch_fails_closed(tmp_path: Path) -> None:
    confirmed_path, applied_path, _ = write_inputs(tmp_path)
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    components = aggregate_components(confirmed)
    components[1]["quantity"]["aggregate_quantity_per_cabinet"] = 99
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    with pytest.raises(bridge.BridgeError, match="quantity mismatch"):
        bridge.project_rows_and_groups(confirmed, snapshot.data)


def test_aggregate_member_cabinet_group_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmed_path, applied_path, _ = write_inputs(tmp_path)
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    actual_bindings = bridge.build_prior_bindings(snapshot.data)
    component_id = aggregate_components(confirmed)[1]["component_evidence_id"]
    binding = actual_bindings[component_id]
    actual_bindings[component_id] = bridge.PriorBinding(
        decision=binding.decision,
        member=binding.member,
        decision_kind=binding.decision_kind,
        cabinet_template="DIFFERENT-CABINET-GROUP",
    )
    monkeypatch.setattr(
        bridge,
        "build_prior_bindings",
        lambda _applied: actual_bindings,
    )
    with pytest.raises(bridge.BridgeError, match="cabinet group mismatch"):
        bridge.project_rows_and_groups(confirmed, snapshot.data)


def test_reserved_meter_spaces_are_coverage_only_and_never_rows(
    tmp_path: Path,
) -> None:
    _, payload, confirmed_path, _ = run_success(tmp_path)
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    reserved_ids = {
        item["component_evidence_id"] for item in confirmed["reserved_meter_spaces"]
    }
    row_ids = {
        component_id
        for row in payload["calculator_input_format"]["row_drafts"]
        for component_id in row["source_component_evidence_ids"]
    }
    assert len(reserved_ids) == 4
    assert reserved_ids.isdisjoint(row_ids)
    assert payload["coverage"]["reserved_meter_space_count"] == 4
    assert payload["coverage"]["reserved_excluded_from_pricing_count"] == 4


def test_cabinet_group_comes_only_from_v022_prior_not_overlay(
    tmp_path: Path,
) -> None:
    _, payload, _, _ = run_success(tmp_path)
    templates = {
        group["source_cabinet_template"] for group in payload["cabinet_groups"]
    }
    assert templates == {"SYNTHETIC-CABINET", "SYNTHETIC-CABINET-B"}
    assert "OVERLAY-TEMPLATE-MUST-NOT-GROUP" not in templates
    assert all(
        "cabinet_template" not in row["approved_signature"]
        for row in payload["calculator_input_format"]["row_drafts"]
    )


def test_missing_prior_binding_fails_closed(tmp_path: Path) -> None:
    confirmed_path, applied_path, _ = write_inputs(tmp_path)
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    snapshot = validator.load_applied_bundle_snapshot(applied_path)
    applied = copy.deepcopy(snapshot.data)
    del applied["prior_v0_22_application"]["direct_component_quantities"][0]
    with pytest.raises(bridge.BridgeError, match="missing v0.22 prior binding"):
        bridge.project_rows_and_groups(confirmed, applied)


def test_ambiguous_prior_binding_fails_closed(tmp_path: Path) -> None:
    _, applied_path, _ = write_inputs(tmp_path)
    applied = json.loads(applied_path.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(
        applied["prior_v0_22_application"]["direct_component_quantities"][0]
    )
    duplicate["decision_id"] = "AMBIGUOUS-DECISION"
    applied["prior_v0_22_application"]["direct_component_quantities"].append(duplicate)
    with pytest.raises(bridge.BridgeError, match="ambiguous v0.22 prior binding"):
        bridge.build_prior_bindings(applied)


def test_output_inside_git_project_is_rejected_without_creation(
    tmp_path: Path,
) -> None:
    confirmed_path, applied_path, _ = write_inputs(tmp_path)
    output_path = PROJECT_ROOT / f".forbidden-pricing-output-{tmp_path.name}.json"
    assert not output_path.exists()
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert "outside the Git project" in result.red_flags[0]
    assert not output_path.exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    confirmed_path, applied_path, output_path = write_inputs(tmp_path)
    output_path.write_text("sentinel", encoding="utf-8")
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert output_path.read_text(encoding="utf-8") == "sentinel"
    assert "overwrite is forbidden" in result.red_flags[0]


def test_source_validation_failure_creates_no_output(tmp_path: Path) -> None:
    def break_confirmed(confirmed: dict[str, Any]) -> None:
        confirmed["schema_version"] = "confirmed_composition_artifact.v0.1"

    confirmed_path, applied_path, output_path = write_inputs(
        tmp_path,
        confirmed_mutator=break_confirmed,
    )
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert not output_path.exists()
    assert "validation failed" in result.red_flags[0]


def test_output_contract_keeps_all_mapping_values_null_and_safety_false(
    tmp_path: Path,
) -> None:
    _, payload, confirmed_path, applied_path = run_success(tmp_path)
    assert set(payload) == bridge.ROOT_FIELDS
    assert set(payload["source"]) == bridge.SOURCE_FIELDS
    assert (
        payload["source"]["confirmed_composition_sha256"]
        == hashlib.sha256(confirmed_path.read_bytes()).hexdigest()
    )
    assert (
        payload["source"]["applied_bundle_sha256"]
        == hashlib.sha256(applied_path.read_bytes()).hexdigest()
    )
    for group in payload["cabinet_groups"]:
        assert all(
            group[field] is None
            for field in (
                "product_name",
                "cabinet_code",
                "cabinet_label",
                "consumables_factor",
            )
        )
    for row in payload["calculator_input_format"]["row_drafts"]:
        values = row["calculator_values"]
        assert all(
            values[field] is None
            for field in bridge.CALCULATOR_COLUMNS
            if field != "component_qty"
        )
    assert payload["safety"] == {
        field_name: False for field_name in bridge.SAFETY_FIELDS
    }
    assert payload["coverage"] == {
        "installed_component_count": 18,
        "direct_installed_component_count": 15,
        "aggregate_member_count": 3,
        "aggregate_decision_count": 1,
        "pricing_row_draft_count": 16,
        "cabinet_group_count": 2,
        "reserved_meter_space_count": 4,
        "reserved_excluded_from_pricing_count": 4,
        "correction_count": 12,
        "reconfirmation_count": 6,
    }


def test_input_drift_before_publication_fails_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmed_path, applied_path, output_path = write_inputs(tmp_path)
    monkeypatch.setattr(bridge, "inputs_are_unchanged", lambda *_args: False)
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert "input drift" in result.red_flags[0]
    assert not output_path.exists()


def test_staging_write_failure_is_cleaned_and_output_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmed_path, applied_path, output_path = write_inputs(tmp_path)

    def fail_write(_path: Path, _content: bytes) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(bridge, "write_staging_file", fail_write)
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert not output_path.exists()
    assert list(tmp_path.glob(f".{output_path.name}.staging-*")) == []


def test_atomic_rename_failure_is_cleaned_and_output_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    confirmed_path, applied_path, output_path = write_inputs(tmp_path)

    def fail_rename(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic rename failure")

    monkeypatch.setattr(bridge.os, "rename", fail_rename)
    result = bridge.build_price_calculator_input_draft_v02(
        confirmed_path,
        applied_path,
        output_path,
    )
    assert result.status == "FAIL"
    assert not output_path.exists()
    assert list(tmp_path.glob(f".{output_path.name}.staging-*")) == []


def test_bridge_does_not_invoke_old_pricing_or_downstream_scripts() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden = (
        "build_price_calculator_input_draft_from_confirmed_composition",
        "validate_completed_price_calculator_input_draft",
        "run_checked_price_calculator_from_completed_draft",
        "calc_quote_price_draft",
        "subprocess",
        "openpyxl",
        "pandas",
    )
    assert all(name not in source for name in forbidden)
