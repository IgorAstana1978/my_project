"""Validate an unexecuted generic human decisions batch v0.22."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "human_decisions_batch.v0.22"
COMPATIBLE_WITH = "human_decisions_batch.v0.21"
ARTIFACT_STATUS = "FROZEN_HUMAN_APPROVAL_DECISIONS"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
BATCH_ID = "022"
PRIOR_BATCH_ID = "021"
APPLICATION_STATUS = "NOT_EXECUTED"

DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
SCOPE_EXCLUSION = "SCOPE_EXCLUSION"
DECISION_KINDS = {
    DIRECT_COMPONENT_QUANTITY,
    CABINET_LEVEL_AGGREGATE,
    SCOPE_EXCLUSION,
}
SCOPE_STATUSES = {
    "NOT_IN_INSTALLED_SCOPE",
    "NOT_IN_INSTALLED_SCOPE_BY_DEFAULT",
}
PROHIBITED_DOWNSTREAM = {
    "installed_composition",
    "pricing",
    "procurement",
    "production",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REPORT_START = "HUMAN_DECISIONS_BATCH_V022_VALIDATION_REPORT_START"
REPORT_END = "HUMAN_DECISIONS_BATCH_V022_VALIDATION_REPORT_END"

ROOT_FIELDS = {
    "schema_version",
    "compatible_with",
    "case_id",
    "project_id",
    "batch_id",
    "prior_batch_id",
    "artifact_status",
    "authority",
    "application_status",
    "confirmed_composition_created",
    "pricing_started",
    "downstream_started",
    "source_bindings",
    "quantity_decisions",
    "coverage",
    "approval_boundary",
    "safety_flags",
}
SOURCE_BINDING_FIELDS = {
    "canonical_bundle_sha256",
    "prior_batch_sha256",
}
COVERAGE_FIELDS = {
    "direct_component_count",
    "aggregate_member_count",
    "exclusion_component_count",
    "union_component_count",
}
APPROVAL_FIELDS = {
    "application_requires_separate_approval",
    "confirmed_composition_requires_separate_approval",
}
SAFETY_FIELDS = {
    "batch_applied",
    "replay_started",
    "frozen_sources_modified",
}
COMMON_DECISION_FIELDS = {
    "decision_id",
    "decision_code",
    "decision_kind",
    "accepted_status",
    "authority",
    "component_signature",
    "members",
    "application_status",
}
SIGNATURE_FIELDS = {
    "cabinet_template",
    "component_identity",
    "model_type",
    "ratings",
    "poles",
    "functional_role",
}
MEMBER_FIELDS = {
    "component_evidence_id",
    "evidence_position_id",
    "section",
    "source_locator",
}
DIRECT_FIELDS = COMMON_DECISION_FIELDS | {"quantity_per_cabinet"}
AGGREGATE_FIELDS = COMMON_DECISION_FIELDS | {
    "aggregate_quantity_per_cabinet",
    "applies_once_per_cabinet",
    "multiply_by_member_count",
}
EXCLUSION_FIELDS = COMMON_DECISION_FIELDS | {
    "scope_status",
    "future_inclusion_requires",
    "prohibited_downstream",
}


class BatchV022ValidationError(RuntimeError):
    """The v0.22 authority artifact violates its generic closed contract."""


@dataclass
class ValidationResult:
    batch_json: Path
    status: str = "FAIL"
    red_flags: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BatchV022ValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise BatchV022ValidationError(f"{label} fields mismatch")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BatchV022ValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchV022ValidationError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BatchV022ValidationError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _string(value, label)
    if SHA256_RE.fullmatch(result) is None:
        raise BatchV022ValidationError(f"{label} must be 64 lowercase hex")
    return result


def _reject_zero_quantities(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                isinstance(key, str)
                and "quantity" in key
                and isinstance(item, (int, float))
                and not isinstance(item, bool)
                and item == 0
            ):
                raise BatchV022ValidationError("quantity=0 is forbidden")
            _reject_zero_quantities(item)
    elif isinstance(value, list):
        for item in value:
            _reject_zero_quantities(item)


def _validate_signature(value: Any) -> None:
    signature = _exact(value, "component_signature", SIGNATURE_FIELDS)
    _string(signature["cabinet_template"], "component_signature.cabinet_template")
    _string(signature["component_identity"], "component_signature.component_identity")
    model_type = signature["model_type"]
    if model_type is not None:
        _string(model_type, "component_signature.model_type")
    ratings = _list(signature["ratings"], "component_signature.ratings")
    normalized_ratings = [
        _string(item, "component_signature.ratings[]") for item in ratings
    ]
    if len(normalized_ratings) != len(set(normalized_ratings)):
        raise BatchV022ValidationError("component_signature ratings must be unique")
    poles = signature["poles"]
    if poles is not None:
        _positive_int(poles, "component_signature.poles")
    _string(signature["functional_role"], "component_signature.functional_role")


def _validate_members(value: Any) -> tuple[str, ...]:
    members = _list(value, "decision members")
    if not members:
        raise BatchV022ValidationError("decision members must be non-empty")
    component_ids: list[str] = []
    for raw_member in members:
        member = _exact(raw_member, "decision member", MEMBER_FIELDS)
        component_ids.append(
            _string(
                member["component_evidence_id"],
                "member component_evidence_id",
            )
        )
        _string(member["evidence_position_id"], "member evidence_position_id")
        _string(member["section"], "member section")
        _string(member["source_locator"], "member source_locator")
    if len(component_ids) != len(set(component_ids)):
        raise BatchV022ValidationError("duplicate COMP within decision")
    return tuple(component_ids)


def _validate_common_decision(decision: Mapping[str, Any]) -> tuple[str, ...]:
    _string(decision["decision_id"], "decision_id")
    _string(decision["decision_code"], "decision_code")
    if decision["accepted_status"] != "APPROVED_BY_IGOR":
        raise BatchV022ValidationError("decision accepted_status mismatch")
    if decision["authority"] != AUTHORITY:
        raise BatchV022ValidationError("decision authority mismatch")
    if decision["application_status"] != APPLICATION_STATUS:
        raise BatchV022ValidationError("decision must remain NOT_EXECUTED")
    _validate_signature(decision["component_signature"])
    return _validate_members(decision["members"])


def _validate_direct(decision: Mapping[str, Any]) -> None:
    _positive_int(
        decision["quantity_per_cabinet"],
        "DIRECT_COMPONENT_QUANTITY quantity_per_cabinet",
    )


def _validate_aggregate(decision: Mapping[str, Any]) -> None:
    _positive_int(
        decision["aggregate_quantity_per_cabinet"],
        "CABINET_LEVEL_AGGREGATE aggregate_quantity_per_cabinet",
    )
    if (
        decision["applies_once_per_cabinet"] is not True
        or decision["multiply_by_member_count"] is not False
    ):
        raise BatchV022ValidationError(
            "aggregate must apply once and must not multiply by member count"
        )


def _validate_exclusion(decision: Mapping[str, Any]) -> None:
    if decision["scope_status"] not in SCOPE_STATUSES:
        raise BatchV022ValidationError("scope exclusion status is not allowed")
    _string(
        decision["future_inclusion_requires"],
        "scope exclusion future_inclusion_requires",
    )
    downstream = [
        _string(item, "scope exclusion prohibited_downstream[]")
        for item in _list(
            decision["prohibited_downstream"],
            "scope exclusion prohibited_downstream",
        )
    ]
    if set(downstream) != PROHIBITED_DOWNSTREAM or len(downstream) != len(
        PROHIBITED_DOWNSTREAM
    ):
        raise BatchV022ValidationError("scope exclusion prohibited_downstream mismatch")


def validate_batch_value(batch_value: Any) -> Mapping[str, int]:
    """Validate a generic v0.22 batch without applying any decision."""

    batch = _exact(batch_value, "batch v0.22", ROOT_FIELDS)
    _reject_zero_quantities(batch)
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "compatible_with": COMPATIBLE_WITH,
        "batch_id": BATCH_ID,
        "prior_batch_id": PRIOR_BATCH_ID,
        "artifact_status": ARTIFACT_STATUS,
        "authority": AUTHORITY,
        "application_status": APPLICATION_STATUS,
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    for key, expected in expected_root.items():
        if batch[key] != expected:
            raise BatchV022ValidationError(f"batch v0.22 {key} mismatch")
    _string(batch["case_id"], "batch v0.22 case_id")
    _string(batch["project_id"], "batch v0.22 project_id")

    bindings = _exact(
        batch["source_bindings"],
        "batch v0.22 source_bindings",
        SOURCE_BINDING_FIELDS,
    )
    _sha256(
        bindings["canonical_bundle_sha256"],
        "source_bindings.canonical_bundle_sha256",
    )
    _sha256(
        bindings["prior_batch_sha256"],
        "source_bindings.prior_batch_sha256",
    )

    approval = _exact(
        batch["approval_boundary"],
        "batch v0.22 approval_boundary",
        APPROVAL_FIELDS,
    )
    if (
        approval["application_requires_separate_approval"] is not True
        or approval["confirmed_composition_requires_separate_approval"] is not True
    ):
        raise BatchV022ValidationError("batch v0.22 approval boundary mismatch")
    safety = _exact(
        batch["safety_flags"],
        "batch v0.22 safety_flags",
        SAFETY_FIELDS,
    )
    if any(value is not False for value in safety.values()):
        raise BatchV022ValidationError("batch v0.22 safety flags must remain false")

    decisions = _list(batch["quantity_decisions"], "batch v0.22 quantity_decisions")
    if not decisions:
        raise BatchV022ValidationError("quantity_decisions must be non-empty")
    decision_ids: set[str] = set()
    decision_codes: set[str] = set()
    covered_ids: set[str] = set()
    counts = {
        "direct_component_count": 0,
        "aggregate_member_count": 0,
        "exclusion_component_count": 0,
        "union_component_count": 0,
    }
    for raw_decision in decisions:
        base = _mapping(raw_decision, "quantity decision")
        kind = base.get("decision_kind")
        if kind not in DECISION_KINDS:
            raise BatchV022ValidationError("unknown decision_kind")
        expected_fields = {
            DIRECT_COMPONENT_QUANTITY: DIRECT_FIELDS,
            CABINET_LEVEL_AGGREGATE: AGGREGATE_FIELDS,
            SCOPE_EXCLUSION: EXCLUSION_FIELDS,
        }[cast(str, kind)]
        decision = _exact(base, f"{kind} decision", expected_fields)
        component_ids = _validate_common_decision(decision)
        decision_id = cast(str, decision["decision_id"])
        decision_code = cast(str, decision["decision_code"])
        if decision_id in decision_ids or decision_code in decision_codes:
            raise BatchV022ValidationError("duplicate decision id or code")
        decision_ids.add(decision_id)
        decision_codes.add(decision_code)
        if covered_ids.intersection(component_ids):
            raise BatchV022ValidationError("COMP covered by more than one decision")
        covered_ids.update(component_ids)

        if kind == DIRECT_COMPONENT_QUANTITY:
            _validate_direct(decision)
            counts["direct_component_count"] += len(component_ids)
        elif kind == CABINET_LEVEL_AGGREGATE:
            _validate_aggregate(decision)
            counts["aggregate_member_count"] += len(component_ids)
        else:
            _validate_exclusion(decision)
            counts["exclusion_component_count"] += len(component_ids)

    counts["union_component_count"] = len(covered_ids)
    declared_coverage = _exact(
        batch["coverage"],
        "batch v0.22 coverage",
        COVERAGE_FIELDS,
    )
    for key, actual in counts.items():
        if declared_coverage[key] != actual:
            raise BatchV022ValidationError(f"coverage {key} mismatch")
    return counts


def validate_batch_artifact(batch_json: Path) -> ValidationResult:
    result = ValidationResult(batch_json)
    try:
        value = json.loads(batch_json.read_bytes())
        result.counts = dict(validate_batch_value(value))
        result.status = "PASS"
    except (
        BatchV022ValidationError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an unexecuted generic human decisions batch v0.22."
    )
    parser.add_argument("--batch-json", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_batch_artifact(args.batch_json)
    print(REPORT_START)
    print(f"status: {result.status}")
    if result.status == "PASS":
        for key, value in result.counts.items():
            print(f"{key}: {value}")
    else:
        print(f"red_flag: {result.red_flags[0]}")
    print(REPORT_END)
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
