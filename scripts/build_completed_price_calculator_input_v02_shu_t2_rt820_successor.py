"""Build the immutable SHU-T2 RT-820 completed technical successor.

This case-scoped builder validates three exact immutable inputs and projects one
approved-not-applied Human Decision into four appended technical/calculator
rows.  It never calculates a price and publishes only through an exclusive
hard link in a fresh output directory.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ID = "2024/086"
PARENT_SCHEMA = "price_calculator_input_draft.v0.2"
PARENT_STATUS = "V02_TECHNICAL_COMPLETION_APPLIED_NOT_PRICED"
DECISION_SCHEMA = "technical_shu_t2_rt820_scope_human_decision.v0.1"
DECISION_ID = "IGOR-SHU-T2-RT820-SCOPE-2024-086-001"
DECISION_STATUS = "IGOR_SHU_T2_RT820_SCOPE_APPROVED_NOT_APPLIED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_STATUS = "NOT_APPLIED"
APPLIED_SCHEMA = "component_replay_applied_bundle.v0.23"
CANONICAL_SCHEMA = "component_replay_readiness_bundle.v0.2"
CANONICAL_SHA256 = "41ca4e3b63433c8f06c7630565c3d5d5380659e49027bf091a6aff6ab007123e"
SUCCESSOR_CONTRACT = "controlled_shu_t2_rt820_technical_successor.v0.1"
PUBLICATION_AUTHORIZATION = (
    "IGOR_SHU_T2_RT820_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED"
)
OUTPUT_FILENAME = "price-calculator-input-v0.2-completed-shu-t2-rt820-successor.json"
REPO_ROOT = Path(__file__).resolve().parents[1]

PARENT_COMPLETED_INPUT = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T1-TECHNICAL-SUCCESSOR-20260818-001\price-calculator-input-v0.2-completed-additive-successor.json"
)
PARENT_COMPLETED_INPUT_SHA256 = (
    "08808d1dfa0f5fa2c5a9b9d4a697a8cb44d9875bd32240d77300a0b3f570205e"
)
SHU_T2_RT820_DECISION = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-SHU-T2-RT820-SCOPE-DECISION-20260820-001\technical-shu-t2-rt820-scope-human-decision-v0.1.json"
)
SHU_T2_RT820_DECISION_SHA256 = (
    "92a79401591fa6202af493848dd979a227ae20da8e66b8dea6e8084fc80c2ac6"
)
APPLIED_COMPONENT_LINEAGE = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-2024-086-HUMAN-DECISIONS-20260731-023\component-replay-applied-bundle-v0.23.json"
)
APPLIED_COMPONENT_LINEAGE_SHA256 = (
    "6433e862c7281ac699a12b81e30a02e7f45702ddab22441efd2c79d36589dd6f"
)

CANONICAL_EVIDENCE_PATH = "$.canonical_component_evidence_records"
TARGET_GROUP_ID = "CABINET-GROUP-003"
SHU_T1_GROUP_ID = "CABINET-GROUP-015"
NEW_ROW_IDS = tuple(f"ROW-DRAFT-{number:04d}" for number in range(113, 117))
SHU_T1_ROW_IDS = ("ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112")
POSITION_SCOPE = (
    ("10", "TFE-016", "PRICE-POSITION-009", "COMP-031", "COMP-034"),
    ("12", "TFE-041", "PRICE-POSITION-023", "COMP-085", "COMP-088"),
    ("14", "TFE-061", "PRICE-POSITION-035", "COMP-128", "COMP-131"),
    ("16", "TFE-083", "PRICE-POSITION-047", "COMP-178", "COMP-181"),
)


class ContractError(ValueError):
    """Raised when an input or successor violates the exact contract."""


@dataclass(frozen=True)
class InputPaths:
    parent_completed_input: Path
    shu_t2_rt820_decision: Path
    applied_component_lineage: Path


@dataclass(frozen=True)
class ExpectedShas:
    parent_completed_input: str
    shu_t2_rt820_decision: str
    applied_component_lineage: str


@dataclass(frozen=True)
class LoadedInput:
    role: str
    path: Path
    expected_sha256: str
    value: dict[str, Any]
    raw: bytes


@dataclass(frozen=True)
class LoadedInputs:
    parent: LoadedInput
    decision: LoadedInput
    applied: LoadedInput


@dataclass(frozen=True)
class EvidenceValidation:
    target_records: tuple[dict[str, Any], ...]
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{name} must be an object")
    return value


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {description}: {path}: {exc}") from exc
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {description}: {path}: {exc}") from exc
    require(isinstance(value, dict), f"{description} root must be an object")
    return value, raw


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_sha(value: str, role: str) -> None:
    require(
        re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"{role} SHA-256 must be 64 lowercase hexadecimal characters",
    )


def _input_contracts(
    paths: InputPaths, shas: ExpectedShas
) -> tuple[tuple[str, Path, str, Path, str], ...]:
    return (
        (
            "parent completed input",
            paths.parent_completed_input,
            shas.parent_completed_input,
            PARENT_COMPLETED_INPUT,
            PARENT_COMPLETED_INPUT_SHA256,
        ),
        (
            "SHU-T2 RT-820 Human Decision",
            paths.shu_t2_rt820_decision,
            shas.shu_t2_rt820_decision,
            SHU_T2_RT820_DECISION,
            SHU_T2_RT820_DECISION_SHA256,
        ),
        (
            "applied component lineage",
            paths.applied_component_lineage,
            shas.applied_component_lineage,
            APPLIED_COMPONENT_LINEAGE,
            APPLIED_COMPONENT_LINEAGE_SHA256,
        ),
    )


def _find_group(parent: Mapping[str, Any], group_id: str) -> Mapping[str, Any]:
    groups = parent.get("cabinet_groups")
    require(isinstance(groups, list), "parent cabinet_groups must be an array")
    matches = [item for item in groups if item.get("cabinet_group_id") == group_id]
    require(len(matches) == 1, f"parent requires exactly one {group_id}")
    return require_mapping(matches[0], group_id)


def _parent_rows(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    calculator = require_mapping(
        parent.get("calculator_input_format"), "parent calculator_input_format"
    )
    rows = calculator.get("row_drafts")
    require(isinstance(rows, list), "parent row_drafts must be an array")
    require(
        all(isinstance(row, dict) for row in rows),
        "parent row_drafts must contain objects",
    )
    return rows


def _row_by_id(rows: Sequence[Mapping[str, Any]], row_id: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("row_id") == row_id]
    require(len(matches) == 1, f"requires exactly one row {row_id}")
    return matches[0]


def validate_parent(parent: Mapping[str, Any], applied_sha256: str) -> None:
    require(parent.get("schema_version") == PARENT_SCHEMA, "parent schema mismatch")
    require(
        parent.get("draft_type") == "price_calculator_input_draft",
        "parent draft type mismatch",
    )
    source = require_mapping(parent.get("source"), "parent source")
    require(source.get("project_id") == PROJECT_ID, "parent project mismatch")
    require(
        source.get("applied_bundle_sha256") == applied_sha256,
        "parent applied-lineage binding mismatch",
    )
    groups = parent.get("cabinet_groups")
    rows = _parent_rows(parent)
    require(
        isinstance(groups, list) and len(groups) == 15, "parent group count mismatch"
    )
    require(len(rows) == 112, "parent row count mismatch")
    expected_row_ids = [f"ROW-DRAFT-{number:04d}" for number in range(1, 113)]
    actual_row_ids = [row.get("row_id") for row in rows]
    require(actual_row_ids == expected_row_ids, "parent row IDs/order mismatch")
    group_ids = [group.get("cabinet_group_id") for group in groups]
    require(len(group_ids) == len(set(group_ids)), "parent duplicate cabinet group")
    target_group = _find_group(parent, TARGET_GROUP_ID)
    require(target_group.get("product_name") == "ШУ-Т2", "SHU-T2 product mismatch")
    require(target_group.get("cabinet_code") == "CAB-KRN-12", "SHU-T2 cabinet mismatch")
    require(
        target_group.get("row_draft_ids")
        == [f"ROW-DRAFT-{number:04d}" for number in range(20, 28)],
        "SHU-T2 parent group structure mismatch",
    )
    target_rows = [
        row for row in rows if row.get("cabinet_group_id") == TARGET_GROUP_ID
    ]
    require(len(target_rows) == 8, "SHU-T2 parent row membership mismatch")
    require(
        all(
            require_mapping(
                row.get("calculator_values"), "parent calculator values"
            ).get("component_code")
            != "EKF-RT-820"
            for row in target_rows
        ),
        "parent SHU-T2 already contains RT-820",
    )
    shu_t1_group = _find_group(parent, SHU_T1_GROUP_ID)
    require(
        shu_t1_group.get("row_draft_ids") == list(SHU_T1_ROW_IDS),
        "SHU-T1 parent group structure mismatch",
    )
    rt820 = _row_by_id(rows, "ROW-DRAFT-0110")
    rt_values = require_mapping(rt820.get("calculator_values"), "SHU-T1 RT-820 values")
    require(
        rt820.get("cabinet_group_id") == SHU_T1_GROUP_ID
        and rt_values.get("product_name") == "ШУ-Т1"
        and rt_values.get("component_code") == "EKF-RT-820"
        and rt_values.get("component_qty") == 1
        and rt_values.get("install_type") == "temperature_relay_din_2mod",
        "SHU-T1 RT-820 row mismatch",
    )
    completion = require_mapping(parent.get("completion"), "parent completion")
    require(completion.get("status") == PARENT_STATUS, "parent status mismatch")
    scope = require_mapping(completion.get("scope"), "parent completion scope")
    require(
        scope.get("component_groups") == 34
        and scope.get("rows") == "112/112"
        and scope.get("cabinet_groups") == "15/15",
        "parent completion counts mismatch",
    )
    coverage = require_mapping(parent.get("coverage"), "parent coverage")
    require(
        coverage.get("installed_component_count") == 124
        and coverage.get("direct_installed_component_count") == 110
        and coverage.get("pricing_row_draft_count") == 112
        and coverage.get("cabinet_group_count") == 15,
        "parent coverage mismatch",
    )
    safety = require_mapping(parent.get("safety"), "parent safety")
    require(bool(safety), "parent safety is empty")
    require(
        all(value is False for value in safety.values()), "parent safety must be false"
    )


def _expected_positions() -> list[dict[str, Any]]:
    return [
        {
            "section": section,
            "technical_position_id": technical,
            "pricing_position_id": pricing,
            "relay_evidence_id": relay,
            "sensor_evidence_id": sensor,
            "physical_multiplicity": 1,
        }
        for section, technical, pricing, relay, sensor in POSITION_SCOPE
    ]


def _decision_input_binding(decision: Mapping[str, Any]) -> Mapping[str, Any]:
    bindings = decision.get("input_bindings")
    require(isinstance(bindings, list), "decision input_bindings must be an array")
    matches = [item for item in bindings if item.get("role") == "technical_successor"]
    require(len(matches) == 1, "decision technical-successor binding mismatch")
    return require_mapping(matches[0], "decision technical-successor binding")


def validate_decision(
    decision: Mapping[str, Any],
    parent_path: Path,
    parent_sha256: str,
    applied_sha256: str,
) -> tuple[str, ...]:
    require(
        decision.get("schema_version") == DECISION_SCHEMA, "decision schema mismatch"
    )
    require(
        decision.get("artifact_type") == "IMMUTABLE_HUMAN_DECISION_CAPTURE",
        "decision artifact type mismatch",
    )
    require(decision.get("project_id") == PROJECT_ID, "decision project mismatch")
    require(decision.get("decision_id") == DECISION_ID, "decision ID mismatch")
    require(decision.get("status") == DECISION_STATUS, "decision status mismatch")
    require(decision.get("authority") == AUTHORITY, "decision authority mismatch")
    require(
        decision.get("application_status") == APPLICATION_STATUS,
        "decision application status mismatch",
    )
    binding = _decision_input_binding(decision)
    require(
        binding.get("path") == str(parent_path)
        and binding.get("expected_sha256") == parent_sha256
        and binding.get("actual_sha256") == parent_sha256
        and binding.get("schema_version") == PARENT_SCHEMA
        and binding.get("status") == PARENT_STATUS,
        "decision parent path/SHA binding mismatch",
    )
    anchors = require_mapping(decision.get("lineage_anchors"), "decision lineage")
    require(
        anchors.get("applied_component_lineage_sha256") == applied_sha256,
        "decision applied-lineage binding mismatch",
    )
    exact_scope = require_mapping(decision.get("exact_scope"), "decision exact_scope")
    require(
        exact_scope.get("product") == "ШУ-Т2"
        and exact_scope.get("cabinet_group_id") == TARGET_GROUP_ID
        and exact_scope.get("cabinet_code") == "CAB-KRN-12"
        and exact_scope.get("positions") == _expected_positions()
        and exact_scope.get("source_evidence_row_count") == 8
        and exact_scope.get("future_component_row_count") == 4,
        "decision exact scope mismatch",
    )
    contract = require_mapping(
        decision.get("rt820_contract"), "decision RT-820 contract"
    )
    require(
        contract
        == {
            "component_code": "EKF-RT-820",
            "component_qty_per_physical_cabinet": 1,
            "install_type": "temperature_relay_din_2mod",
            "module_width": 2,
            "source_range": "КРН!A19:C19",
            "source_label": "Терморегулятор RT-820",
            "material_kzt": 15000,
            "work_kzt": 900,
            "generic_work_432_prohibited": True,
            "family_fallback_prohibited": True,
            "fuzzy_fallback_prohibited": True,
            "similar_relay_fallback_prohibited": True,
        },
        "decision RT-820 contract mismatch",
    )
    bundle = require_mapping(decision.get("bundle_semantics"), "decision bundle")
    require(
        bundle
        == {
            "relay_and_sensor_form_one_indivisible_complete_set": True,
            "tst05_provenance_only": True,
            "separate_tst05_component_row": False,
            "separate_tst05_material_charge": False,
            "separate_tst05_work_charge": False,
            "separate_tst05_pricing_row": False,
            "double_counting_prohibited": True,
        },
        "decision bundle semantics mismatch",
    )
    target_ids = tuple(
        evidence
        for _section, _technical, _pricing, relay, sensor in POSITION_SCOPE
        for evidence in (relay, sensor)
    )
    supersession = require_mapping(
        decision.get("supersession"), "decision supersession"
    )
    require(
        supersession.get("prior_decision_id") == "HDA-019-H19-3"
        and supersession.get("superseded_field")
        == (
            "$.supply_boundary.rt007s_authority_proof.rule_payload."
            "forbidden_transfer_designation"
        )
        and supersession.get("prior_value") == "ШУ-Т2"
        and supersession.get("applies_only_to_evidence_ids") == list(target_ids)
        and supersession.get("outside_cabinet_exclusion_count_must_be_derived") is True
        and supersession.get("outside_cabinet_exclusion_count_override_prohibited")
        is True
        and supersession.get("all_other_supply_boundaries_unchanged") is True
        and supersession.get("all_other_human_decisions_unchanged") is True
        and supersession.get("shu_t1_unchanged") is True,
        "decision supersession mismatch",
    )
    safety = require_mapping(decision.get("safety"), "decision safety")
    require(
        safety.get("human_decision_recorded") is True
        and all(
            value is False
            for key, value in safety.items()
            if key != "human_decision_recorded"
        ),
        "decision safety mismatch",
    )
    publication = require_mapping(
        decision.get("publication_control"), "decision publication_control"
    )
    require(
        all(value is True for value in publication.values()),
        "decision publication mismatch",
    )
    return target_ids


def validate_applied_lineage(
    applied: Mapping[str, Any],
    target_ids: tuple[str, ...],
) -> EvidenceValidation:
    require(applied.get("schema_version") == APPLIED_SCHEMA, "applied schema mismatch")
    require(applied.get("project_id") == PROJECT_ID, "applied project mismatch")
    require(applied.get("application_status") == "APPLIED", "applied status mismatch")
    lineage = require_mapping(applied.get("source_lineage"), "applied source_lineage")
    require(
        lineage.get("canonical_replay_schema_version") == CANONICAL_SCHEMA
        and lineage.get("canonical_replay_sha256") == CANONICAL_SHA256,
        "applied canonical binding mismatch",
    )
    records = applied.get("canonical_component_evidence_records")
    require(isinstance(records, list) and records, "applied canonical records missing")
    require(
        all(isinstance(record, dict) for record in records),
        "malformed canonical evidence records",
    )
    record_ids = [record.get("component_evidence_id") for record in records]
    require(
        all(isinstance(item, str) for item in record_ids),
        "malformed component evidence ID",
    )
    counts = Counter(record_ids)
    require(
        all(count == 1 for count in counts.values()),
        "duplicate applied component evidence ID",
    )
    require(len(set(target_ids)) == 8, "target evidence count must be 8")
    require(
        all(counts[evidence_id] == 1 for evidence_id in target_ids),
        "each target evidence ID must occur exactly once in applied lineage",
    )
    by_id = {str(record["component_evidence_id"]): record for record in records}
    for position, (_section, technical, _pricing, relay, sensor) in zip(
        _expected_positions(), POSITION_SCOPE, strict=True
    ):
        require(
            position["technical_position_id"] == technical, "position contract drift"
        )
        require(
            by_id[relay].get("position_id") == technical
            and by_id[sensor].get("position_id") == technical,
            "target evidence position binding mismatch",
        )
    target_records = tuple(copy.deepcopy(by_id[item]) for item in target_ids)
    return EvidenceValidation(target_records, target_ids)


def load_and_validate_inputs(paths: InputPaths, shas: ExpectedShas) -> LoadedInputs:
    loaded: list[LoadedInput] = []
    for role, path, supplied_sha, exact_path, exact_sha in _input_contracts(
        paths, shas
    ):
        validate_sha(supplied_sha, role)
        require(_resolved(path) == _resolved(exact_path), f"{role} path mismatch")
        require(supplied_sha == exact_sha, f"{role} expected SHA mismatch")
        value, raw = load_json(path, role)
        require(sha256_bytes(raw) == supplied_sha, f"initial SHA mismatch: {role}")
        loaded.append(LoadedInput(role, path, supplied_sha, value, raw))
    parent, decision, applied = loaded
    validate_parent(parent.value, applied.expected_sha256)
    target_ids = validate_decision(
        decision.value,
        parent.path,
        parent.expected_sha256,
        applied.expected_sha256,
    )
    validate_applied_lineage(applied.value, target_ids)
    return LoadedInputs(parent, decision, applied)


def validate_projection_evidence(loaded: LoadedInputs) -> EvidenceValidation:
    validate_parent(loaded.parent.value, loaded.applied.expected_sha256)
    target_ids = validate_decision(
        loaded.decision.value,
        loaded.parent.path,
        loaded.parent.expected_sha256,
        loaded.applied.expected_sha256,
    )
    return validate_applied_lineage(loaded.applied.value, target_ids)


def _decision_binding(loaded: LoadedInputs) -> dict[str, Any]:
    return {
        "path": str(loaded.decision.path),
        "sha256": loaded.decision.expected_sha256,
        "schema_version": DECISION_SCHEMA,
        "decision_id": DECISION_ID,
        "status": DECISION_STATUS,
        "authority": AUTHORITY,
        "application_status": APPLICATION_STATUS,
    }


def _successor_metadata(
    loaded: LoadedInputs, evidence: EvidenceValidation
) -> dict[str, Any]:
    return {
        "contract": SUCCESSOR_CONTRACT,
        "parent": {
            "path": str(loaded.parent.path),
            "sha256": loaded.parent.expected_sha256,
            "schema_version": PARENT_SCHEMA,
            "status": PARENT_STATUS,
        },
        "human_decision": _decision_binding(loaded),
        "applied_component_lineage": {
            "path": str(loaded.applied.path),
            "sha256": loaded.applied.expected_sha256,
            "schema_version": APPLIED_SCHEMA,
            "canonical_schema_version": CANONICAL_SCHEMA,
            "canonical_sha256": CANONICAL_SHA256,
        },
        "technical_projection": {
            "evidence_records_json_path": CANONICAL_EVIDENCE_PATH,
            "row_count": len(NEW_ROW_IDS),
            "row_ids": list(NEW_ROW_IDS),
            "evidence_count": len(evidence.target_ids),
            "evidence_ids": list(evidence.target_ids),
            "evidence_records": list(evidence.target_records),
            "evidence_existence_validated": True,
            "evidence_position_binding_validated": True,
            "outside_cabinet_membership_asserted": False,
            "outside_cabinet_count_transition_asserted": False,
        },
        "narrow_supersession": {
            "prior_decision_id": "HDA-019-H19-3",
            "field": "forbidden_transfer_designation",
            "prior_value": "ШУ-Т2",
            "applies_only_to_evidence_ids": list(evidence.target_ids),
            "all_other_supply_boundaries_unchanged": True,
            "shu_t1_unchanged": True,
        },
        "rt820_pricing_provenance_only": {
            "source_range": "КРН!A19:C19",
            "material_kzt": 15000,
            "work_kzt": 900,
            "pricing_calculation_executed": False,
            "generic_work_432_prohibited": True,
            "family_fallback_prohibited": True,
            "fuzzy_fallback_prohibited": True,
            "similar_relay_fallback_prohibited": True,
        },
        "append_only": True,
        "scope_expansion": False,
    }


def _appended_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_id, (section, technical, pricing, relay, sensor) in zip(
        NEW_ROW_IDS, POSITION_SCOPE, strict=True
    ):
        rows.append(
            {
                "row_id": row_id,
                "cabinet_group_id": TARGET_GROUP_ID,
                "calculator_values": {
                    "product_name": "ШУ-Т2",
                    "cabinet_code": "CAB-KRN-12",
                    "consumables_factor": 1.2,
                    "component_code": "EKF-RT-820",
                    "component_qty": 1,
                    "install_type": "temperature_relay_din_2mod",
                },
                "source_quantity": {
                    "decision_id": DECISION_ID,
                    "decision_kind": "DIRECT_PER_CABINET_COMPLETE_SET",
                    "technical_position_id": technical,
                    "pricing_position_id": pricing,
                    "section": section,
                    "quantity_per_individual_cabinet": 1,
                    "physical_multiplicity": 1,
                    "applies_once_per_cabinet": True,
                    "multiply_by_member_count": False,
                    "scope_expansion": False,
                },
                "source_component_evidence_ids": [relay, sensor],
                "approved_signature": {
                    "manufacturer": "EKF",
                    "product": "Реле температуры RT-820 EKF PROxima",
                    "manufacturer_article": "RT-820",
                    "supply_form": (
                        "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR"
                    ),
                    "module_width_din": 2,
                    "TST05_evidence_included_as_provenance_only": True,
                    "TST05_separate_component_row": False,
                },
                "mapping_status": "APPROVED_HUMAN_DECISIONS_APPLIED",
                "component_label": (
                    "Реле температуры RT-820 EKF PROxima с внешним датчиком"
                ),
            }
        )
    return rows


def _calculated_component_group_count(parent: Mapping[str, Any]) -> int:
    scope = require_mapping(
        require_mapping(parent.get("completion"), "parent completion").get("scope"),
        "parent completion scope",
    )
    rows = _parent_rows(parent)
    existing_target_codes = {
        require_mapping(row.get("calculator_values"), "target calculator values").get(
            "component_code"
        )
        for row in rows
        if row.get("cabinet_group_id") == TARGET_GROUP_ID
    }
    require("EKF-RT-820" not in existing_target_codes, "RT-820 group already exists")
    parent_count = scope.get("component_groups")
    require(type(parent_count) is int, "parent component-group count must be integer")
    return parent_count + 1


def build_successor_payload(loaded: LoadedInputs) -> dict[str, Any]:
    evidence = validate_projection_evidence(loaded)
    parent = loaded.parent.value
    successor = copy.deepcopy(parent)
    source = require_mapping(successor["source"], "successor source")
    source["shu_t2_rt820_technical_successor"] = _successor_metadata(loaded, evidence)
    target_group = _find_group(successor, TARGET_GROUP_ID)
    target_group["row_draft_ids"].extend(NEW_ROW_IDS)
    _parent_rows(successor).extend(_appended_rows())
    coverage = require_mapping(successor["coverage"], "successor coverage")
    added = len(NEW_ROW_IDS)
    coverage["installed_component_count"] += added
    coverage["direct_installed_component_count"] += added
    coverage["pricing_row_draft_count"] += added
    completion = require_mapping(successor["completion"], "successor completion")
    scope = require_mapping(completion["scope"], "successor completion scope")
    scope["component_groups"] = _calculated_component_group_count(parent)
    scope["rows"] = f"{len(_parent_rows(successor))}/{len(_parent_rows(successor))}"
    completion["shu_t2_rt820_technical_successor"] = {
        "contract": SUCCESSOR_CONTRACT,
        "decision_application": "PROJECTED_TO_TECHNICAL_SUCCESSOR_ONLY",
        "pricing_calculation_executed": False,
        "calculator_authorized": False,
        "successor_publication_requires_separate_exact_igor_authorization": True,
    }
    validate_successor_payload(successor, loaded)
    return successor


def validate_successor_payload(
    successor: Mapping[str, Any], loaded: LoadedInputs
) -> None:
    parent = loaded.parent.value
    evidence = validate_projection_evidence(loaded)
    require(
        successor.get("schema_version") == PARENT_SCHEMA, "successor schema mismatch"
    )
    require(set(successor) == set(parent), "successor top-level structure changed")
    controlled = {
        "source",
        "cabinet_groups",
        "calculator_input_format",
        "coverage",
        "completion",
    }
    for key in set(parent) - controlled:
        require(successor[key] == parent[key], f"successor changed parent field: {key}")
    parent_source = require_mapping(parent.get("source"), "parent source")
    successor_source = require_mapping(successor.get("source"), "successor source")
    require(
        {key: successor_source[key] for key in parent_source} == parent_source,
        "successor changed parent source",
    )
    require(
        set(successor_source) == {*parent_source, "shu_t2_rt820_technical_successor"},
        "successor source keys mismatch",
    )
    require(
        successor_source["shu_t2_rt820_technical_successor"]
        == _successor_metadata(loaded, evidence),
        "successor exact bindings/provenance mismatch",
    )
    parent_groups = parent["cabinet_groups"]
    groups = successor.get("cabinet_groups")
    require(
        isinstance(groups, list) and len(groups) == 15, "successor group count mismatch"
    )
    for parent_group, group in zip(parent_groups, groups, strict=True):
        if parent_group.get("cabinet_group_id") == TARGET_GROUP_ID:
            expected = copy.deepcopy(parent_group)
            expected["row_draft_ids"].extend(NEW_ROW_IDS)
            require(group == expected, "SHU-T2 group append mismatch")
        else:
            require(group == parent_group, "non-target cabinet group changed")
    require(
        _find_group(successor, SHU_T1_GROUP_ID) == _find_group(parent, SHU_T1_GROUP_ID),
        "SHU-T1 group changed",
    )
    parent_rows = _parent_rows(parent)
    rows = _parent_rows(successor)
    require(len(rows) == 116, "successor row count mismatch")
    require(rows[:112] == parent_rows, "parent row prefix changed")
    require(rows[112:] == _appended_rows(), "appended RT-820 rows mismatch")
    require(
        [row.get("row_id") for row in rows]
        == [f"ROW-DRAFT-{number:04d}" for number in range(1, 117)],
        "successor row IDs/order mismatch",
    )
    target_rows = [
        row for row in rows if row.get("cabinet_group_id") == TARGET_GROUP_ID
    ]
    rt820_rows = [
        row
        for row in target_rows
        if require_mapping(row.get("calculator_values"), "target values").get(
            "component_code"
        )
        == "EKF-RT-820"
    ]
    require(len(rt820_rows) == 4, "SHU-T2 must contain exactly four RT-820 rows")
    require(
        all(
            "TST05"
            not in str(
                require_mapping(row.get("calculator_values"), "target values").get(
                    "component_code"
                )
            )
            for row in rows
        ),
        "separate TST05 row is forbidden",
    )
    successor_coverage = require_mapping(
        successor.get("coverage"), "successor coverage"
    )
    expected_coverage = copy.deepcopy(parent["coverage"])
    expected_coverage["installed_component_count"] += 4
    expected_coverage["direct_installed_component_count"] += 4
    expected_coverage["pricing_row_draft_count"] += 4
    require(successor_coverage == expected_coverage, "successor coverage mismatch")
    successor_completion = require_mapping(
        successor.get("completion"), "successor completion"
    )
    expected_completion = copy.deepcopy(parent["completion"])
    expected_completion["scope"]["component_groups"] = (
        _calculated_component_group_count(parent)
    )
    expected_completion["scope"]["rows"] = "116/116"
    expected_completion["shu_t2_rt820_technical_successor"] = {
        "contract": SUCCESSOR_CONTRACT,
        "decision_application": "PROJECTED_TO_TECHNICAL_SUCCESSOR_ONLY",
        "pricing_calculation_executed": False,
        "calculator_authorized": False,
        "successor_publication_requires_separate_exact_igor_authorization": True,
    }
    require(
        successor_completion == expected_completion, "successor completion mismatch"
    )
    metadata = require_mapping(
        successor_source["shu_t2_rt820_technical_successor"], "successor metadata"
    )
    pricing = require_mapping(
        metadata.get("rt820_pricing_provenance_only"), "pricing provenance"
    )
    require(
        pricing.get("pricing_calculation_executed") is False
        and pricing.get("generic_work_432_prohibited") is True
        and pricing.get("family_fallback_prohibited") is True
        and pricing.get("fuzzy_fallback_prohibited") is True
        and pricing.get("similar_relay_fallback_prohibited") is True,
        "pricing/fallback safety mismatch",
    )


def validate_real_inputs_read_only(
    paths: InputPaths, shas: ExpectedShas
) -> dict[str, Any]:
    loaded = load_and_validate_inputs(paths, shas)
    evidence = validate_projection_evidence(loaded)
    return {
        "status": "PASS",
        "publication_called": False,
        "authority_source": "exact immutable SHU-T2 RT-820 Human Decision",
        "projected_row_count": len(NEW_ROW_IDS),
        "validated_evidence_count": len(evidence.target_ids),
        "target_ids": list(evidence.target_ids),
        "outside_cabinet_membership_asserted": False,
        "outside_cabinet_count_transition_asserted": False,
    }


def _path_identity(path: Path) -> tuple[int, int]:
    value = os.lstat(path)
    return value.st_dev, value.st_ino


def _recheck_inputs(loaded: LoadedInputs, phase: str) -> None:
    for item in (loaded.parent, loaded.decision, loaded.applied):
        try:
            current = item.path.read_bytes()
        except OSError as exc:
            raise ContractError(
                f"{phase} TOCTOU reread failed: {item.role}: {exc}"
            ) from exc
        require(current == item.raw, f"{phase} TOCTOU bytes changed: {item.role}")
        require(
            sha256_bytes(current) == item.expected_sha256,
            f"{phase} TOCTOU SHA mismatch: {item.role}",
        )


def _rollback_publication(
    output: Path,
    staging: Path | None,
    final_link_created: bool,
    staged_identity: tuple[int, int] | None,
) -> list[str]:
    blockers: list[str] = []
    if final_link_created and os.path.lexists(output):
        try:
            if staged_identity is None or _path_identity(output) != staged_identity:
                blockers.append("foreign final replacement preserved")
            else:
                output.unlink()
        except OSError as exc:
            blockers.append(f"owned final cleanup failed: {exc}")
    if staging is not None and os.path.lexists(staging):
        try:
            staging.unlink()
        except OSError as exc:
            blockers.append(f"staging cleanup failed: {exc}")
    if output.parent.exists():
        try:
            output.parent.rmdir()
        except OSError:
            if not os.path.lexists(output):
                blockers.append("output directory cleanup failed")
    return blockers


def publish_successor(
    paths: InputPaths, shas: ExpectedShas, output: Path
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    try:
        _resolved(output).relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise ContractError("successor output must be outside the repository")
    input_paths = {_resolved(path) for path in vars(paths).values()}
    require(_resolved(output) not in input_paths, "output must not alias an input")
    loaded = load_and_validate_inputs(paths, shas)
    payload = build_successor_payload(loaded)
    encoded = serialize(payload)
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    staged_identity: tuple[int, int] | None = None
    final_link_created = False
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".staging", dir=output.parent
        )
        staging = Path(staging_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged, staged_raw = load_json(staging, "staged technical successor")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_successor_payload(staged, loaded)
        require(
            set(output.parent.iterdir()) == {staging},
            "output directory contains unexpected pre-publication entries",
        )
        _recheck_inputs(loaded, "pre-publication")
        require(not output.exists(), "output appeared before publication")
        staged_identity = _path_identity(staging)
        try:
            os.link(staging, output)
        except OSError as exc:
            raise ContractError(
                f"atomic no-overwrite publication failed: {exc}"
            ) from exc
        final_link_created = True
        require(
            _path_identity(output) == staged_identity, "published identity mismatch"
        )
        published, published_raw = load_json(output, "published technical successor")
        require(published_raw == encoded, "published bytes mismatch")
        validate_successor_payload(published, loaded)
        _recheck_inputs(loaded, "final")
        staging.unlink()
        require(_path_identity(output) == staged_identity, "final identity changed")
        require(
            set(output.parent.iterdir()) == {output},
            "output directory final inventory mismatch",
        )
        return PublicationResult(
            sha256_bytes(published_raw), len(published_raw), encoded
        )
    except BaseException as error:
        blockers: list[str] = []
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                blockers.append(f"staging descriptor cleanup failed: {exc}")
        blockers.extend(
            _rollback_publication(output, staging, final_link_created, staged_identity)
        )
        if blockers:
            raise ContractError(
                "publication rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-completed-input", required=True, type=Path)
    parser.add_argument("--parent-completed-input-sha256", required=True)
    parser.add_argument("--shu-t2-rt820-decision", required=True, type=Path)
    parser.add_argument("--shu-t2-rt820-decision-sha256", required=True)
    parser.add_argument("--applied-component-lineage", required=True, type=Path)
    parser.add_argument("--applied-component-lineage-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact SHU-T2 RT-820 technical-successor publication authorization is required",
    )
    paths = InputPaths(
        args.parent_completed_input,
        args.shu_t2_rt820_decision,
        args.applied_component_lineage,
    )
    shas = ExpectedShas(
        args.parent_completed_input_sha256,
        args.shu_t2_rt820_decision_sha256,
        args.applied_component_lineage_sha256,
    )
    result = publish_successor(paths, shas, args.output)
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
