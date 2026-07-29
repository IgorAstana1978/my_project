"""Validate and expand the approved N/PE human decisions batch v0.21."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

SCHEMA_VERSION = "human_decisions_batch.v0.21"
ARTIFACT_STATUS = "FROZEN_HUMAN_APPROVAL_DECISIONS"
COMPATIBLE_WITH = "human_decisions_batch.v0.20"
PRIOR_BATCH_ID = "020"
BATCH_ID = "021"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
DECISION_ID = "HDA-021-H21-1"
DECISION_CODE = "H21-1"
DECISION_TYPE = "N_PE_BUS_SET_AUTHORITY"
TECHNICAL_FIELD = "component_identity_quantity_and_install_type"
COMPONENT_IDENTITY = "ШИНА N/PE"
QUANTITY_PER_CABINET = 1
INSTALL_TYPE = "n_pe_bus_set"
EXPANSION_COUNT = 29
REPORT_START = "HUMAN_DECISIONS_BATCH_V021_VALIDATION_REPORT_START"
REPORT_END = "HUMAN_DECISIONS_BATCH_V021_VALIDATION_REPORT_END"

CONFLICTED_COMPONENT_IDS = {"COMP-040", "COMP-137", "COMP-187"}

ROOT_FIELDS = {
    "schema_version",
    "compatible_with",
    "case_id",
    "project_id",
    "batch_id",
    "prior_batch_id",
    "artifact_status",
    "authority",
    "technical_field_decisions",
    "approval_boundary",
    "safety_flags",
}
DECISION_FIELDS = {
    "decision_id",
    "decision_code",
    "decision_type",
    "technical_field",
    "accepted_status",
    "authority",
    "component_identity",
    "quantity_per_cabinet",
    "install_type",
    "component_mapping",
    "group_expansion_count",
    "separate_n_pe_identities_created",
    "anti_double_counting",
    "application_status",
}
MAPPING_FIELDS = {
    "record_id",
    "component_evidence_id",
    "evidence_position_id",
    "section",
}
APPROVAL_FIELDS = {
    "correction_schema",
    "conflicted_component_ids",
    "correction_required_before_application",
    "confirmed_composition_created",
}
SAFETY_FIELDS = {
    "frozen_sources_modified",
    "extraction_repeated",
    "new_evidence_ids_created",
    "split_n_pe_identities_created",
    "confirmed_composition_created",
    "pricing_executed",
}


class BatchV021ValidationError(RuntimeError):
    """The v0.21 authority artifact violates its approved closed contract."""


@dataclass
class ValidationResult:
    batch_json: Path
    status: str = "FAIL"
    red_flags: list[str] = field(default_factory=list)
    audit_mappings: tuple[Mapping[str, Any], ...] = ()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BatchV021ValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise BatchV021ValidationError(f"{label} fields mismatch")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BatchV021ValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchV021ValidationError(f"{label} must be a non-empty string")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_confirmed_validator() -> ModuleType:
    path = Path(__file__).with_name("validate_confirmed_composition_artifact.py")
    spec = importlib.util.spec_from_file_location(
        "confirmed_composition_validator_for_v021",
        path,
    )
    if spec is None or spec.loader is None:
        raise BatchV021ValidationError("could not load authoritative install_type")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _approved_install_types() -> set[str]:
    module = _load_confirmed_validator()
    values = getattr(module, "INSTALL_TYPES", None)
    if not isinstance(values, set) or not all(isinstance(item, str) for item in values):
        raise BatchV021ValidationError("authoritative install_type registry is invalid")
    return cast(set[str], values)


def _records_by_id(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        record_id = _string(record.get("record_id"), "applicability record_id")
        if record_id in result:
            raise BatchV021ValidationError("duplicate applicability record_id")
        result[record_id] = record
    return result


def _identified_by_id(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        evidence_id = _string(
            record.get("component_evidence_id"),
            "identified component_evidence_id",
        )
        if evidence_id in result:
            raise BatchV021ValidationError("duplicate identified component ID")
        result[evidence_id] = record
    return result


def validate_and_expand_batch(
    batch_value: Any,
    *,
    project_id: str,
    applicability_records: Sequence[Mapping[str, Any]],
    identified_records: Sequence[Mapping[str, Any]],
    projected_corrections: Sequence[Mapping[str, Any]],
    source_blockers: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate one grouped decision and expand it into 29 audit mappings."""

    batch = _exact(batch_value, "batch v0.21", ROOT_FIELDS)
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "compatible_with": COMPATIBLE_WITH,
        "batch_id": BATCH_ID,
        "prior_batch_id": PRIOR_BATCH_ID,
        "artifact_status": ARTIFACT_STATUS,
        "authority": AUTHORITY,
    }
    for key, expected in expected_root.items():
        if batch[key] != expected:
            raise BatchV021ValidationError(f"batch v0.21 {key} mismatch")
    _string(batch["case_id"], "batch v0.21 case_id")
    if batch["project_id"] != project_id:
        raise BatchV021ValidationError("batch v0.21 project_id mismatch")

    safety = _exact(batch["safety_flags"], "batch v0.21 safety_flags", SAFETY_FIELDS)
    if any(safety.values()):
        raise BatchV021ValidationError("batch v0.21 safety flags must remain false")
    approval = _exact(
        batch["approval_boundary"],
        "batch v0.21 approval_boundary",
        APPROVAL_FIELDS,
    )
    if (
        approval["correction_schema"]
        != "component_replay_row_alignment_correction.v0.1"
        or set(
            _string(item, "approval_boundary.conflicted_component_ids[]")
            for item in _list(
                approval["conflicted_component_ids"],
                "approval_boundary.conflicted_component_ids",
            )
        )
        != CONFLICTED_COMPONENT_IDS
        or approval["correction_required_before_application"] is not True
        or approval["confirmed_composition_created"] is not False
    ):
        raise BatchV021ValidationError("batch v0.21 approval boundary mismatch")

    decisions = _list(
        batch["technical_field_decisions"],
        "batch v0.21 technical_field_decisions",
    )
    if len(decisions) != 1:
        raise BatchV021ValidationError("exactly one grouped v0.21 decision is required")
    decision = _exact(decisions[0], "batch v0.21 decision", DECISION_FIELDS)
    expected_decision = {
        "decision_id": DECISION_ID,
        "decision_code": DECISION_CODE,
        "decision_type": DECISION_TYPE,
        "technical_field": TECHNICAL_FIELD,
        "accepted_status": "APPROVED_BY_IGOR",
        "authority": AUTHORITY,
        "component_identity": COMPONENT_IDENTITY,
        "quantity_per_cabinet": QUANTITY_PER_CABINET,
        "install_type": INSTALL_TYPE,
        "group_expansion_count": EXPANSION_COUNT,
        "separate_n_pe_identities_created": False,
        "anti_double_counting": True,
        "application_status": "NOT_EXECUTED",
    }
    for key, expected in expected_decision.items():
        if decision[key] != expected:
            raise BatchV021ValidationError(f"v0.21 decision {key} mismatch")
    if INSTALL_TYPE not in _approved_install_types():
        raise BatchV021ValidationError("approved install_type is not authoritative")

    mappings = _list(decision["component_mapping"], "v0.21 component_mapping")
    if len(mappings) != EXPANSION_COUNT:
        raise BatchV021ValidationError("grouped expansion count must equal 29")
    blockers = [
        item for item in source_blockers if item.get("blocker_kind") == "QUANTITY"
    ]
    install = [
        item for item in source_blockers if item.get("blocker_kind") == "INSTALL_TYPE"
    ]
    if len(blockers) != EXPANSION_COUNT or len(install) != 1:
        raise BatchV021ValidationError("source blocker set is not exact 29 plus 1")

    expected_fingerprints = {
        (
            item.get("record_id"),
            item.get("component_evidence_id"),
            item.get("evidence_position_id"),
            item.get("section"),
        )
        for item in blockers
    }
    records = _records_by_id(applicability_records)
    identified = _identified_by_id(identified_records)
    corrected_ids = {
        _string(item.get("component_evidence_id"), "correction component ID")
        for item in projected_corrections
    }
    if corrected_ids != CONFLICTED_COMPONENT_IDS:
        raise BatchV021ValidationError("validated correction set is incomplete")

    actual_fingerprints: set[tuple[Any, Any, Any, Any]] = set()
    component_ids: set[str] = set()
    audit_mappings: list[Mapping[str, Any]] = []
    for raw_mapping in mappings:
        mapping = _exact(raw_mapping, "v0.21 component_mapping[]", MAPPING_FIELDS)
        fingerprint = (
            mapping["record_id"],
            mapping["component_evidence_id"],
            mapping["evidence_position_id"],
            mapping["section"],
        )
        if fingerprint in actual_fingerprints:
            raise BatchV021ValidationError("duplicate v0.21 mapping")
        actual_fingerprints.add(fingerprint)
        evidence_id = _string(mapping["component_evidence_id"], "mapping COMP")
        if evidence_id in component_ids:
            raise BatchV021ValidationError("component ID covered more than once")
        component_ids.add(evidence_id)
        record = records.get(_string(mapping["record_id"], "mapping record_id"))
        component = identified.get(evidence_id)
        if record is None or component is None:
            raise BatchV021ValidationError("v0.21 mapping references unknown source")
        if component.get("label") != COMPONENT_IDENTITY:
            raise BatchV021ValidationError(
                "split or changed N/PE identity is forbidden"
            )
        classification = record.get("applicability_classification")
        if classification not in {
            "REQUIRED_VALUE_MISSING",
            "REQUIRED_VALUE_CONFLICTED",
        }:
            raise BatchV021ValidationError("mapping is not a quantity blocker")
        correction_id = None
        if classification == "REQUIRED_VALUE_CONFLICTED":
            if evidence_id not in corrected_ids:
                raise BatchV021ValidationError(
                    "conflicted component applied without correction"
                )
            correction = next(
                item
                for item in projected_corrections
                if item["component_evidence_id"] == evidence_id
            )
            correction_id = correction["correction_id"]
        audit_mappings.append(
            {
                "audit_id": f"{DECISION_ID}:{evidence_id}",
                "decision_id": DECISION_ID,
                "record_id": mapping["record_id"],
                "component_evidence_id": evidence_id,
                "evidence_position_id": mapping["evidence_position_id"],
                "section": mapping["section"],
                "component_identity": COMPONENT_IDENTITY,
                "quantity_per_cabinet": QUANTITY_PER_CABINET,
                "install_type": INSTALL_TYPE,
                "source_applicability_classification": classification,
                "source_raw_designation": record.get("raw_designation"),
                "source_raw_quantity": record.get("raw_quantity"),
                "source_raw_type_model": record.get("raw_type_model"),
                "source_provenance": component.get("provenance"),
                "correction_id": correction_id,
                "anti_double_counting": True,
                "application_status": "APPLIED_ONCE_IN_REPLAY_PROJECTION",
            }
        )

    if actual_fingerprints != expected_fingerprints:
        raise BatchV021ValidationError("missing or unknown v0.21 mapping")
    if len({_canonical(item) for item in audit_mappings}) != EXPANSION_COUNT:
        raise BatchV021ValidationError("audit expansion is not unique")
    return {
        "schema_version": "component_replay_authority_application.v0.1",
        "batch_schema_version": SCHEMA_VERSION,
        "batch_id": BATCH_ID,
        "decision_id": DECISION_ID,
        "decision_code": DECISION_CODE,
        "component_identity": COMPONENT_IDENTITY,
        "quantity_per_cabinet": QUANTITY_PER_CABINET,
        "install_type": INSTALL_TYPE,
        "grouped_input_count": EXPANSION_COUNT,
        "expanded_audit_count": len(audit_mappings),
        "audit_mappings": sorted(
            audit_mappings,
            key=lambda item: cast(str, item["component_evidence_id"]),
        ),
        "resolved_blockers": {"quantity": EXPANSION_COUNT, "install_type": 1},
        "remaining_blocker_count": 0,
        "separate_n_pe_identities_created": False,
        "anti_double_counting": True,
        "application_order": [
            "component_replay_row_alignment_correction.v0.1",
            SCHEMA_VERSION,
        ],
    }


def validate_batch_artifact(
    batch_json: Path,
    *,
    project_id: str,
    applicability_records: Sequence[Mapping[str, Any]],
    identified_records: Sequence[Mapping[str, Any]],
    projected_corrections: Sequence[Mapping[str, Any]],
    source_blockers: Sequence[Mapping[str, Any]],
) -> ValidationResult:
    result = ValidationResult(batch_json)
    try:
        value = _mapping(json.loads(batch_json.read_bytes()), "batch v0.21")
        application = validate_and_expand_batch(
            value,
            project_id=project_id,
            applicability_records=applicability_records,
            identified_records=identified_records,
            projected_corrections=projected_corrections,
            source_blockers=source_blockers,
        )
        result.audit_mappings = tuple(
            cast(list[Mapping[str, Any]], application["audit_mappings"])
        )
        result.status = "PASS"
    except (BatchV021ValidationError, OSError, json.JSONDecodeError) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate batch v0.21 through replay integration; standalone source "
            "context is required by the importing replay validator."
        )
    )
    parser.add_argument("--batch-json", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(REPORT_START)
    print("status: FAIL")
    print(f"red_flag: standalone context unavailable for {args.batch_json}")
    print(REPORT_END)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
