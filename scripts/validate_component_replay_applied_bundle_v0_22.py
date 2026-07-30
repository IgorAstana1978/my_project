"""Validate a generic component replay applied bundle v0.22."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "component_replay_applied_bundle.v0.22"
REPLAY_SCHEMA_VERSION = "component_replay_readiness_bundle.v0.2"
BATCH_SCHEMA_VERSION = "human_decisions_batch.v0.22"
BATCH_ID = "022"
PRIOR_BATCH_ID = "021"
APPLICATION_STATUS = "APPLIED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"

DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
SCOPE_EXCLUSION = "SCOPE_EXCLUSION"
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
REPORT_START = "COMPONENT_REPLAY_APPLIED_BUNDLE_V022_VALIDATION_REPORT_START"
REPORT_END = "COMPONENT_REPLAY_APPLIED_BUNDLE_V022_VALIDATION_REPORT_END"

ROOT_FIELDS = {
    "schema_version",
    "project_id",
    "application_status",
    "authority",
    "source_lineage",
    "direct_component_quantities",
    "cabinet_level_aggregates",
    "scope_exclusions",
    "coverage",
    "confirmed_composition_created",
    "pricing_started",
    "downstream_started",
}
SOURCE_LINEAGE_FIELDS = {
    "canonical_replay_sha256",
    "canonical_replay_schema_version",
    "human_decisions_batch_sha256",
    "human_decisions_batch_schema_version",
    "batch_id",
    "prior_batch_id",
}
COVERAGE_FIELDS = {
    "direct_component_count",
    "aggregate_member_count",
    "exclusion_component_count",
    "union_component_count",
}
COMMON_DECISION_FIELDS = {
    "decision_id",
    "decision_code",
    "decision_kind",
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
    "canonical_label",
    "canonical_document_id",
    "canonical_source_status",
    "canonical_provenance",
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


class AppliedBundleV022ValidationError(RuntimeError):
    """The applied bundle violates its generic closed contract."""


class DuplicateJsonKeyError(ValueError):
    """An applied bundle JSON object contains a duplicate key."""


@dataclass
class ValidationResult:
    bundle_json: Path
    status: str = "FAIL"
    red_flags: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AppliedBundleV022ValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise AppliedBundleV022ValidationError(f"{label} fields mismatch")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AppliedBundleV022ValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AppliedBundleV022ValidationError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AppliedBundleV022ValidationError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _string(value, label)
    if SHA256_RE.fullmatch(result) is None:
        raise AppliedBundleV022ValidationError(f"{label} must be 64 lowercase hex")
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
                raise AppliedBundleV022ValidationError("quantity=0 is forbidden")
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
    ratings = [
        _string(item, "component_signature.ratings[]")
        for item in _list(signature["ratings"], "component_signature.ratings")
    ]
    if len(ratings) != len(set(ratings)):
        raise AppliedBundleV022ValidationError(
            "component_signature ratings must be unique"
        )
    poles = signature["poles"]
    if poles is not None:
        _positive_int(poles, "component_signature.poles")
    _string(signature["functional_role"], "component_signature.functional_role")


def _validate_members(value: Any) -> tuple[str, ...]:
    members = _list(value, "decision members")
    if not members:
        raise AppliedBundleV022ValidationError("decision members must be non-empty")
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
        _string(member["canonical_label"], "member canonical_label")
        _string(member["canonical_document_id"], "member canonical_document_id")
        _string(
            member["canonical_source_status"],
            "member canonical_source_status",
        )
        provenance = _mapping(
            member["canonical_provenance"],
            "member canonical_provenance",
        )
        if not provenance:
            raise AppliedBundleV022ValidationError(
                "member canonical_provenance must be non-empty"
            )
    if len(component_ids) != len(set(component_ids)):
        raise AppliedBundleV022ValidationError("duplicate COMP within decision")
    return tuple(component_ids)


def _validate_decision_common(
    decision: Mapping[str, Any],
    expected_kind: str,
) -> tuple[str, ...]:
    _string(decision["decision_id"], "decision_id")
    _string(decision["decision_code"], "decision_code")
    if decision["decision_kind"] != expected_kind:
        raise AppliedBundleV022ValidationError("decision_kind mismatch")
    if decision["application_status"] != APPLICATION_STATUS:
        raise AppliedBundleV022ValidationError("decision application_status mismatch")
    _validate_signature(decision["component_signature"])
    return _validate_members(decision["members"])


def _validate_decision_list(
    value: Any,
    label: str,
    kind: str,
    fields: set[str],
) -> list[tuple[Mapping[str, Any], tuple[str, ...]]]:
    validated: list[tuple[Mapping[str, Any], tuple[str, ...]]] = []
    for raw_decision in _list(value, label):
        decision = _exact(raw_decision, f"{kind} decision", fields)
        validated.append((decision, _validate_decision_common(decision, kind)))
    return validated


def validate_applied_value(bundle_value: Any) -> Mapping[str, int]:
    """Validate an applied overlay without consulting project-specific data."""

    bundle = _exact(bundle_value, "applied bundle v0.22", ROOT_FIELDS)
    _reject_zero_quantities(bundle)
    expected_root = {
        "schema_version": SCHEMA_VERSION,
        "application_status": APPLICATION_STATUS,
        "authority": AUTHORITY,
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    for key, expected in expected_root.items():
        if bundle[key] != expected:
            raise AppliedBundleV022ValidationError(
                f"applied bundle v0.22 {key} mismatch"
            )
    _string(bundle["project_id"], "applied bundle project_id")

    lineage = _exact(
        bundle["source_lineage"],
        "source_lineage",
        SOURCE_LINEAGE_FIELDS,
    )
    _sha256(
        lineage["canonical_replay_sha256"],
        "source_lineage.canonical_replay_sha256",
    )
    _sha256(
        lineage["human_decisions_batch_sha256"],
        "source_lineage.human_decisions_batch_sha256",
    )
    if lineage["canonical_replay_schema_version"] != REPLAY_SCHEMA_VERSION:
        raise AppliedBundleV022ValidationError(
            "source lineage canonical replay schema mismatch"
        )
    if lineage["human_decisions_batch_schema_version"] != BATCH_SCHEMA_VERSION:
        raise AppliedBundleV022ValidationError("source lineage batch schema mismatch")
    if lineage["batch_id"] != BATCH_ID:
        raise AppliedBundleV022ValidationError("source lineage batch_id mismatch")
    if lineage["prior_batch_id"] != PRIOR_BATCH_ID:
        raise AppliedBundleV022ValidationError("source lineage prior_batch_id mismatch")

    direct = _validate_decision_list(
        bundle["direct_component_quantities"],
        "direct_component_quantities",
        DIRECT_COMPONENT_QUANTITY,
        DIRECT_FIELDS,
    )
    aggregates = _validate_decision_list(
        bundle["cabinet_level_aggregates"],
        "cabinet_level_aggregates",
        CABINET_LEVEL_AGGREGATE,
        AGGREGATE_FIELDS,
    )
    exclusions = _validate_decision_list(
        bundle["scope_exclusions"],
        "scope_exclusions",
        SCOPE_EXCLUSION,
        EXCLUSION_FIELDS,
    )

    decision_ids: set[str] = set()
    decision_codes: set[str] = set()
    covered_ids: set[str] = set()
    counts = {
        "direct_component_count": 0,
        "aggregate_member_count": 0,
        "exclusion_component_count": 0,
        "union_component_count": 0,
    }
    for decision, component_ids in direct:
        _positive_int(
            decision["quantity_per_cabinet"],
            "DIRECT_COMPONENT_QUANTITY quantity_per_cabinet",
        )
        counts["direct_component_count"] += len(component_ids)
        _register_decision(
            decision,
            component_ids,
            decision_ids,
            decision_codes,
            covered_ids,
        )
    for decision, component_ids in aggregates:
        _positive_int(
            decision["aggregate_quantity_per_cabinet"],
            "CABINET_LEVEL_AGGREGATE aggregate_quantity_per_cabinet",
        )
        if (
            decision["applies_once_per_cabinet"] is not True
            or decision["multiply_by_member_count"] is not False
        ):
            raise AppliedBundleV022ValidationError(
                "aggregate must apply once and must not multiply by member count"
            )
        counts["aggregate_member_count"] += len(component_ids)
        _register_decision(
            decision,
            component_ids,
            decision_ids,
            decision_codes,
            covered_ids,
        )
    for decision, component_ids in exclusions:
        if decision["scope_status"] not in SCOPE_STATUSES:
            raise AppliedBundleV022ValidationError(
                "scope exclusion status is not allowed"
            )
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
            raise AppliedBundleV022ValidationError(
                "scope exclusion prohibited_downstream mismatch"
            )
        counts["exclusion_component_count"] += len(component_ids)
        _register_decision(
            decision,
            component_ids,
            decision_ids,
            decision_codes,
            covered_ids,
        )

    if not covered_ids:
        raise AppliedBundleV022ValidationError(
            "applied bundle must cover at least one COMP"
        )
    counts["union_component_count"] = len(covered_ids)
    declared_coverage = _exact(
        bundle["coverage"],
        "coverage",
        COVERAGE_FIELDS,
    )
    for key, actual in counts.items():
        if declared_coverage[key] != actual:
            raise AppliedBundleV022ValidationError(f"coverage {key} mismatch")
    return counts


def _register_decision(
    decision: Mapping[str, Any],
    component_ids: tuple[str, ...],
    decision_ids: set[str],
    decision_codes: set[str],
    covered_ids: set[str],
) -> None:
    decision_id = cast(str, decision["decision_id"])
    decision_code = cast(str, decision["decision_code"])
    if decision_id in decision_ids or decision_code in decision_codes:
        raise AppliedBundleV022ValidationError("duplicate decision id or code")
    if covered_ids.intersection(component_ids):
        raise AppliedBundleV022ValidationError("COMP covered by more than one decision")
    decision_ids.add(decision_id)
    decision_codes.add(decision_code)
    covered_ids.update(component_ids)


def validate_applied_bundle(bundle_json: Path) -> ValidationResult:
    result = ValidationResult(bundle_json)
    try:
        value = json.loads(
            bundle_json.read_bytes(),
            object_pairs_hook=_duplicate_key_guard,
        )
        result.counts = dict(validate_applied_value(value))
        result.status = "PASS"
    except (
        AppliedBundleV022ValidationError,
        DuplicateJsonKeyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a generic component replay applied bundle v0.22."
    )
    parser.add_argument("--bundle-json", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_applied_bundle(args.bundle_json)
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
