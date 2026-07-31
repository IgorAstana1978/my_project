"""Apply frozen v0.22 and v0.23 batches as a bounded generic overlay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPLAY_SCHEMA_VERSION = "component_replay_readiness_bundle.v0.2"
PRIOR_BATCH_SCHEMA_VERSION = "human_decisions_batch.v0.22"
CORRECTION_BATCH_SCHEMA_VERSION = "human_decisions_batch.v0.23"
APPLIED_SCHEMA_VERSION = "component_replay_applied_bundle.v0.23"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_STATUS = "APPLIED"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
SCOPE_EXCLUSION = "SCOPE_EXCLUSION"
COMPONENT_SIGNATURE_CORRECTION = "COMPONENT_SIGNATURE_CORRECTION"
COMPONENT_RECONFIRMATION = "COMPONENT_RECONFIRMATION"
RESERVED_METER_SPACE = "RESERVED_METER_SPACE"

CANONICAL_RECORD_FIELDS = {
    "component_evidence_id",
    "document_id",
    "label",
    "position_id",
    "provenance",
    "section_id",
    "source_status",
}
SIGNATURE_FIELDS = {
    "component_identity",
    "model_type",
    "ratings",
    "poles",
    "functional_role",
}
COMPONENT_OVERLAY_FIELDS = {
    "item_id",
    "item_kind",
    "cabinet_record_id",
    "cabinet_template",
    "component_evidence_id",
    "position_id",
    "section",
    "source_locator",
    "original_signature",
    "approved_signature",
    "quantity_per_cabinet",
    "provenance",
    "correction_reason",
    "canonical_evidence_modified",
    "application_status",
}
RESERVED_REQUIREMENT_FIELDS = {
    "item_id",
    "item_kind",
    "cabinet_record_id",
    "cabinet_template",
    "component_evidence_id",
    "position_id",
    "section",
    "source_locator",
    "requirement_kind",
    "meter_connection",
    "reserved_space_per_cabinet",
    "installed_component",
    "original_identity",
    "provenance",
    "future_inclusion_requires",
    "prohibited_downstream",
    "canonical_evidence_modified",
    "application_status",
}
ROOT_FIELDS = {
    "schema_version",
    "project_id",
    "application_status",
    "authority",
    "application_order",
    "source_lineage",
    "canonical_component_evidence_records",
    "prior_v0_22_application",
    "component_signature_overlays",
    "reserved_meter_space_requirements",
    "coverage",
    "confirmed_composition_created",
    "pricing_started",
    "downstream_started",
}
SOURCE_LINEAGE_FIELDS = {
    "canonical_replay_sha256",
    "canonical_replay_schema_version",
    "prior_batch_sha256",
    "prior_batch_schema_version",
    "prior_batch_id",
    "correction_batch_sha256",
    "correction_batch_schema_version",
    "correction_batch_id",
    "correction_prior_batch_id",
}
PRIOR_APPLICATION_FIELDS = {
    "application_status",
    "direct_component_quantities",
    "cabinet_level_aggregates",
    "scope_exclusions",
    "coverage",
}
COVERAGE_FIELDS = {
    "canonical_component_count",
    "prior_direct_component_count",
    "prior_aggregate_member_count",
    "prior_exclusion_component_count",
    "prior_union_component_count",
    "component_signature_correction_count",
    "component_reconfirmation_count",
    "reserved_meter_space_count",
    "overlay_component_count",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REPORT_START = "HUMAN_DECISIONS_BATCH_V023_APPLICATION_REPORT_START"
REPORT_END = "HUMAN_DECISIONS_BATCH_V023_APPLICATION_REPORT_END"


class V023ApplicationError(RuntimeError):
    """The three inputs cannot be applied under the bounded v0.23 contract."""


class DuplicateJsonKeyError(ValueError):
    """An input JSON object contains a duplicate key."""


@dataclass
class ApplicationResult:
    canonical_replay: Path
    prior_batch_json: Path
    correction_batch_json: Path
    output_json: Path
    status: str = "FAIL"
    output_created: bool = False
    red_flags: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    canonical_replay_sha256: str | None = None
    prior_batch_sha256: str | None = None
    correction_batch_sha256: str | None = None


def _load_sibling(name: str, filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise V023ApplicationError(f"cannot load application dependency: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V022_APPLICATION = _load_sibling(
    "apply_human_decisions_batch_v0_22_for_v023_application",
    "apply_human_decisions_batch_v0_22_to_component_replay.py",
)
V023_VALIDATOR = _load_sibling(
    "validate_human_decisions_batch_v0_23_for_application",
    "validate_human_decisions_batch_v0_23.py",
)


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(content, object_pairs_hook=_duplicate_key_guard)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        DuplicateJsonKeyError,
    ) as exc:
        raise V023ApplicationError(f"{label} cannot be read: {exc}") from exc
    return content, value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise V023ApplicationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise V023ApplicationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V023ApplicationError(f"{label} must be a non-empty string")
    return value


def _exact(
    value: Any,
    label: str,
    fields: set[str],
) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise V023ApplicationError(f"{label} fields mismatch")
    return result


def _canonical_locator(record: Mapping[str, Any]) -> str:
    provenance = _mapping(record["provenance"], "canonical provenance")
    row_locator = _string(
        provenance.get("row_locator"),
        "canonical provenance row_locator",
    )
    specification_locator = _string(
        provenance.get("specification_position_or_locator"),
        "canonical provenance specification_position_or_locator",
    )
    return f"{row_locator}; {specification_locator}"


def _signature_projection(signature_value: Any) -> dict[str, Any]:
    signature = _mapping(signature_value, "prior component_signature")
    return {key: copy.deepcopy(signature.get(key)) for key in SIGNATURE_FIELDS}


def _validate_standard_inputs(
    canonical: Mapping[str, Any],
    prior_batch: Mapping[str, Any],
    correction_batch: Mapping[str, Any],
) -> tuple[
    Mapping[str, Mapping[str, Any]],
    Mapping[str, int],
    Mapping[str, int],
]:
    try:
        canonical_records = V022_APPLICATION._validate_canonical_replay(canonical)
    except Exception as exc:
        raise V023ApplicationError(
            f"canonical replay validation failed: {exc}"
        ) from exc
    try:
        prior_counts = V022_APPLICATION.BATCH_VALIDATOR.validate_batch_value(
            prior_batch
        )
    except Exception as exc:
        raise V023ApplicationError(f"batch v0.22 validation failed: {exc}") from exc
    try:
        correction_counts = V023_VALIDATOR.validate_batch_value(correction_batch)
    except Exception as exc:
        raise V023ApplicationError(f"batch v0.23 validation failed: {exc}") from exc
    return (
        cast(Mapping[str, Mapping[str, Any]], canonical_records),
        cast(Mapping[str, int], prior_counts),
        cast(Mapping[str, int], correction_counts),
    )


def _prior_member_index(
    prior_batch: Mapping[str, Any],
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for raw_decision in _list(
        prior_batch["quantity_decisions"],
        "batch v0.22 quantity_decisions",
    ):
        decision = _mapping(raw_decision, "batch v0.22 decision")
        for raw_member in _list(decision["members"], "batch v0.22 members"):
            member = _mapping(raw_member, "batch v0.22 member")
            component_id = _string(
                member.get("component_evidence_id"),
                "batch v0.22 member component_evidence_id",
            )
            if component_id in index:
                raise V023ApplicationError("duplicate COMP in batch v0.22")
            index[component_id] = (decision, member)
    return index


def _v023_item_index(
    correction_batch: Mapping[str, Any],
) -> dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]]:
    index: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for raw_cabinet in _list(
        correction_batch["cabinet_records"],
        "batch v0.23 cabinet_records",
    ):
        cabinet = _mapping(raw_cabinet, "batch v0.23 cabinet record")
        for raw_item in _list(cabinet["items"], "batch v0.23 items"):
            item = _mapping(raw_item, "batch v0.23 item")
            component_id = _string(
                item.get("component_evidence_id"),
                "batch v0.23 component_evidence_id",
            )
            if component_id in index:
                raise V023ApplicationError("duplicate COMP in batch v0.23")
            index[component_id] = (cabinet, item)
    return index


def _check_canonical_binding(
    component_id: str,
    cabinet: Mapping[str, Any],
    item: Mapping[str, Any],
    canonical: Mapping[str, Any],
    canonical_sha256: str,
    prior_batch_sha256: str,
    prior_decision: Mapping[str, Any],
) -> str:
    locator = _canonical_locator(canonical)
    checks = {
        "cabinet section": (cabinet.get("section"), canonical["section_id"]),
        "cabinet position": (cabinet.get("position_id"), canonical["position_id"]),
        "item source locator": (
            _mapping(item["provenance"], "item provenance").get("source_locator"),
            locator,
        ),
    }
    canonical_provenance = _mapping(
        canonical["provenance"],
        "canonical provenance",
    )
    checks["cabinet source locator"] = (
        cabinet.get("source_locator"),
        canonical_provenance.get("specification_position_or_locator"),
    )
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise V023ApplicationError(
                f"{component_id} {label} does not match canonical replay"
            )

    provenance = _mapping(item["provenance"], "item provenance")
    source_sha256 = provenance.get("source_artifact_sha256")
    source_record_id = provenance.get("source_record_id")
    if source_sha256 == canonical_sha256:
        expected_record_id = component_id
    elif source_sha256 == prior_batch_sha256:
        expected_record_id = prior_decision["decision_id"]
    else:
        raise V023ApplicationError(
            f"{component_id} provenance SHA is not an exact source binding"
        )
    if source_record_id != expected_record_id:
        raise V023ApplicationError(
            f"{component_id} provenance source_record_id mismatch"
        )
    return locator


def _validate_v023_semantics(
    canonical_records: Mapping[str, Mapping[str, Any]],
    prior_index: Mapping[
        str,
        tuple[Mapping[str, Any], Mapping[str, Any]],
    ],
    item_index: Mapping[
        str,
        tuple[Mapping[str, Any], Mapping[str, Any]],
    ],
    canonical_sha256: str,
    prior_batch_sha256: str,
) -> None:
    for component_id, (cabinet, item) in item_index.items():
        if component_id not in canonical_records:
            raise V023ApplicationError(
                f"batch v0.23 COMP is absent from canonical replay: {component_id}"
            )
        if component_id not in prior_index:
            raise V023ApplicationError(
                f"batch v0.23 COMP is absent from batch v0.22: {component_id}"
            )
        canonical = canonical_records[component_id]
        prior_decision, prior_member = prior_index[component_id]
        locator = _check_canonical_binding(
            component_id,
            cabinet,
            item,
            canonical,
            canonical_sha256,
            prior_batch_sha256,
            prior_decision,
        )
        prior_checks = {
            "evidence_position_id": canonical["position_id"],
            "section": canonical["section_id"],
            "source_locator": locator,
        }
        for field_name, expected in prior_checks.items():
            if prior_member.get(field_name) != expected:
                raise V023ApplicationError(
                    f"{component_id} prior {field_name} does not match canonical replay"
                )

        kind = item["item_kind"]
        canonical_identity = canonical["label"]
        if kind == COMPONENT_SIGNATURE_CORRECTION:
            if item["original_signature"] != _signature_projection(
                prior_decision["component_signature"]
            ):
                raise V023ApplicationError(
                    f"{component_id} original signature does not match batch v0.22"
                )
            approved = _mapping(item["approved_signature"], "approved_signature")
            if approved.get("component_identity") != canonical_identity:
                raise V023ApplicationError(
                    f"{component_id} approved identity does not match canonical replay"
                )
        elif kind == COMPONENT_RECONFIRMATION:
            original = _mapping(
                item["original_signature"],
                "original_signature",
            )
            if original.get("component_identity") != canonical_identity:
                raise V023ApplicationError(
                    f"{component_id} reconfirmed identity does not match "
                    "canonical replay"
                )
        elif kind == RESERVED_METER_SPACE:
            if item["original_identity"] != canonical_identity:
                raise V023ApplicationError(
                    f"{component_id} reserved identity does not match canonical replay"
                )
            if prior_decision["decision_kind"] != SCOPE_EXCLUSION:
                raise V023ApplicationError(
                    f"{component_id} reserved space requires prior scope exclusion"
                )
        else:
            raise V023ApplicationError(f"unknown batch v0.23 item kind: {kind}")


def _project_prior_member(
    member_value: Any,
    canonical_records: Mapping[str, Mapping[str, Any]],
    correction_items: Mapping[
        str,
        tuple[Mapping[str, Any], Mapping[str, Any]],
    ],
    signature: Mapping[str, Any],
) -> dict[str, Any]:
    member = _mapping(member_value, "batch v0.22 member")
    component_id = cast(str, member["component_evidence_id"])
    if component_id not in canonical_records:
        raise V023ApplicationError(
            f"batch v0.22 COMP is absent from canonical replay: {component_id}"
        )
    canonical = canonical_records[component_id]
    locator = _canonical_locator(canonical)
    checks = {
        "evidence_position_id": canonical["position_id"],
        "section": canonical["section_id"],
        "source_locator": locator,
    }
    for field_name, expected in checks.items():
        if member.get(field_name) != expected:
            raise V023ApplicationError(
                f"{component_id} prior {field_name} does not match canonical replay"
            )
    if signature["component_identity"] != canonical["label"]:
        correction = correction_items.get(component_id)
        if (
            correction is None
            or correction[1]["item_kind"] != COMPONENT_SIGNATURE_CORRECTION
            or correction[1]["original_signature"] != _signature_projection(signature)
        ):
            raise V023ApplicationError(
                f"{component_id} prior identity mismatch lacks exact v0.23 correction"
            )
    return {
        "component_evidence_id": component_id,
        "evidence_position_id": member["evidence_position_id"],
        "section": member["section"],
        "source_locator": member["source_locator"],
        "canonical_label": canonical["label"],
        "canonical_document_id": canonical["document_id"],
        "canonical_source_status": canonical["source_status"],
        "canonical_provenance": copy.deepcopy(canonical["provenance"]),
    }


def _project_prior_decision(
    decision_value: Any,
    canonical_records: Mapping[str, Mapping[str, Any]],
    correction_items: Mapping[
        str,
        tuple[Mapping[str, Any], Mapping[str, Any]],
    ],
) -> dict[str, Any]:
    decision = _mapping(decision_value, "batch v0.22 decision")
    signature = _mapping(decision["component_signature"], "component_signature")
    projected = {
        "decision_id": decision["decision_id"],
        "decision_code": decision["decision_code"],
        "decision_kind": decision["decision_kind"],
        "component_signature": copy.deepcopy(signature),
        "members": [
            _project_prior_member(
                member,
                canonical_records,
                correction_items,
                signature,
            )
            for member in _list(decision["members"], "batch v0.22 members")
        ],
        "application_status": APPLICATION_STATUS,
    }
    kind = decision["decision_kind"]
    if kind == DIRECT_COMPONENT_QUANTITY:
        projected["quantity_per_cabinet"] = decision["quantity_per_cabinet"]
    elif kind == CABINET_LEVEL_AGGREGATE:
        projected.update(
            {
                "aggregate_quantity_per_cabinet": decision[
                    "aggregate_quantity_per_cabinet"
                ],
                "applies_once_per_cabinet": True,
                "multiply_by_member_count": False,
            }
        )
    elif kind == SCOPE_EXCLUSION:
        projected.update(
            {
                "scope_status": decision["scope_status"],
                "future_inclusion_requires": decision["future_inclusion_requires"],
                "prohibited_downstream": copy.deepcopy(
                    decision["prohibited_downstream"]
                ),
            }
        )
    else:
        raise V023ApplicationError(f"unknown batch v0.22 decision kind: {kind}")
    return projected


def _project_component_overlay(
    cabinet: Mapping[str, Any],
    item: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": item["item_id"],
        "item_kind": item["item_kind"],
        "cabinet_record_id": cabinet["cabinet_record_id"],
        "cabinet_template": cabinet["cabinet_template"],
        "component_evidence_id": item["component_evidence_id"],
        "position_id": cabinet["position_id"],
        "section": cabinet["section"],
        "source_locator": item["provenance"]["source_locator"],
        "original_signature": copy.deepcopy(item["original_signature"]),
        "approved_signature": copy.deepcopy(item["approved_signature"]),
        "quantity_per_cabinet": item["quantity_per_cabinet"],
        "provenance": copy.deepcopy(item["provenance"]),
        "correction_reason": item["correction_reason"],
        "canonical_evidence_modified": False,
        "application_status": APPLICATION_STATUS,
    }


def _project_reserved_requirement(
    cabinet: Mapping[str, Any],
    item: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": item["item_id"],
        "item_kind": item["item_kind"],
        "cabinet_record_id": cabinet["cabinet_record_id"],
        "cabinet_template": cabinet["cabinet_template"],
        "component_evidence_id": item["component_evidence_id"],
        "position_id": cabinet["position_id"],
        "section": cabinet["section"],
        "source_locator": item["provenance"]["source_locator"],
        "requirement_kind": item["requirement_kind"],
        "meter_connection": item["meter_connection"],
        "reserved_space_per_cabinet": item["reserved_space_per_cabinet"],
        "installed_component": False,
        "original_identity": item["original_identity"],
        "provenance": copy.deepcopy(item["provenance"]),
        "future_inclusion_requires": item["future_inclusion_requires"],
        "prohibited_downstream": copy.deepcopy(item["prohibited_downstream"]),
        "canonical_evidence_modified": False,
        "application_status": APPLICATION_STATUS,
    }


def _validate_generated_value(value: Any) -> Mapping[str, int]:
    applied = _exact(value, "applied bundle v0.23", ROOT_FIELDS)
    expected_root = {
        "schema_version": APPLIED_SCHEMA_VERSION,
        "application_status": APPLICATION_STATUS,
        "authority": AUTHORITY,
        "application_order": [
            PRIOR_BATCH_SCHEMA_VERSION,
            CORRECTION_BATCH_SCHEMA_VERSION,
        ],
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    for key, expected in expected_root.items():
        if applied[key] != expected:
            raise V023ApplicationError(f"generated applied bundle {key} mismatch")
    _string(applied["project_id"], "generated applied project_id")

    lineage = _exact(
        applied["source_lineage"],
        "generated source_lineage",
        SOURCE_LINEAGE_FIELDS,
    )
    for field_name in (
        "canonical_replay_sha256",
        "prior_batch_sha256",
        "correction_batch_sha256",
    ):
        value_sha = _string(lineage[field_name], field_name)
        if SHA256_RE.fullmatch(value_sha) is None:
            raise V023ApplicationError(f"{field_name} must be 64 lowercase hex")
    expected_lineage = {
        "canonical_replay_schema_version": REPLAY_SCHEMA_VERSION,
        "prior_batch_schema_version": PRIOR_BATCH_SCHEMA_VERSION,
        "prior_batch_id": "022",
        "correction_batch_schema_version": CORRECTION_BATCH_SCHEMA_VERSION,
        "correction_batch_id": "023",
        "correction_prior_batch_id": "022",
    }
    for key, expected in expected_lineage.items():
        if lineage[key] != expected:
            raise V023ApplicationError(f"generated source lineage {key} mismatch")

    canonical_records: dict[str, Mapping[str, Any]] = {}
    for raw_record in _list(
        applied["canonical_component_evidence_records"],
        "generated canonical records",
    ):
        record = _exact(
            raw_record,
            "generated canonical record",
            CANONICAL_RECORD_FIELDS,
        )
        component_id = _string(
            record["component_evidence_id"],
            "generated canonical component_evidence_id",
        )
        if component_id in canonical_records:
            raise V023ApplicationError("duplicate generated canonical COMP")
        canonical_records[component_id] = record
    if not canonical_records:
        raise V023ApplicationError("generated canonical records must be non-empty")

    prior = _exact(
        applied["prior_v0_22_application"],
        "prior_v0_22_application",
        PRIOR_APPLICATION_FIELDS,
    )
    prior_bundle = {
        "schema_version": V022_APPLICATION.APPLIED_SCHEMA_VERSION,
        "project_id": applied["project_id"],
        "application_status": APPLICATION_STATUS,
        "authority": AUTHORITY,
        "source_lineage": {
            "canonical_replay_sha256": lineage["canonical_replay_sha256"],
            "canonical_replay_schema_version": REPLAY_SCHEMA_VERSION,
            "human_decisions_batch_sha256": lineage["prior_batch_sha256"],
            "human_decisions_batch_schema_version": PRIOR_BATCH_SCHEMA_VERSION,
            "batch_id": "022",
            "prior_batch_id": "021",
        },
        "direct_component_quantities": prior["direct_component_quantities"],
        "cabinet_level_aggregates": prior["cabinet_level_aggregates"],
        "scope_exclusions": prior["scope_exclusions"],
        "coverage": prior["coverage"],
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    try:
        prior_counts = V022_APPLICATION.APPLIED_VALIDATOR.validate_applied_value(
            prior_bundle
        )
    except Exception as exc:
        raise V023ApplicationError(
            f"generated prior v0.22 layer validation failed: {exc}"
        ) from exc
    if prior["application_status"] != APPLICATION_STATUS:
        raise V023ApplicationError("generated prior application_status mismatch")

    component_ids: set[str] = set()
    correction_count = 0
    reconfirmation_count = 0
    for raw_overlay in _list(
        applied["component_signature_overlays"],
        "component_signature_overlays",
    ):
        overlay = _exact(
            raw_overlay,
            "component signature overlay",
            COMPONENT_OVERLAY_FIELDS,
        )
        component_id = _string(
            overlay["component_evidence_id"],
            "overlay component_evidence_id",
        )
        if component_id in component_ids or component_id not in canonical_records:
            raise V023ApplicationError("duplicate or unknown overlay COMP")
        component_ids.add(component_id)
        kind = overlay["item_kind"]
        if kind == COMPONENT_SIGNATURE_CORRECTION:
            correction_count += 1
        elif kind == COMPONENT_RECONFIRMATION:
            reconfirmation_count += 1
        else:
            raise V023ApplicationError("unknown component signature overlay kind")
        if (
            overlay["canonical_evidence_modified"] is not False
            or overlay["application_status"] != APPLICATION_STATUS
        ):
            raise V023ApplicationError("component overlay boundary mismatch")
        if set(_mapping(overlay["approved_signature"], "approved signature")) != (
            SIGNATURE_FIELDS
        ):
            raise V023ApplicationError("approved signature fields mismatch")
        if (
            overlay["approved_signature"]["component_identity"]
            != canonical_records[component_id]["label"]
        ):
            raise V023ApplicationError(
                "approved signature identity differs from canonical evidence"
            )

    reserved_count = 0
    for raw_requirement in _list(
        applied["reserved_meter_space_requirements"],
        "reserved_meter_space_requirements",
    ):
        requirement = _exact(
            raw_requirement,
            "reserved meter space requirement",
            RESERVED_REQUIREMENT_FIELDS,
        )
        component_id = _string(
            requirement["component_evidence_id"],
            "reserved component_evidence_id",
        )
        if component_id in component_ids or component_id not in canonical_records:
            raise V023ApplicationError("duplicate or unknown reserved COMP")
        component_ids.add(component_id)
        reserved_count += 1
        if (
            requirement["item_kind"] != RESERVED_METER_SPACE
            or requirement["requirement_kind"] != RESERVED_METER_SPACE
            or requirement["installed_component"] is not False
            or requirement["reserved_space_per_cabinet"] != 1
            or requirement["canonical_evidence_modified"] is not False
            or requirement["application_status"] != APPLICATION_STATUS
        ):
            raise V023ApplicationError("reserved meter space boundary mismatch")

    coverage = _exact(applied["coverage"], "generated coverage", COVERAGE_FIELDS)
    actual = {
        "canonical_component_count": len(canonical_records),
        "prior_direct_component_count": prior_counts["direct_component_count"],
        "prior_aggregate_member_count": prior_counts["aggregate_member_count"],
        "prior_exclusion_component_count": prior_counts["exclusion_component_count"],
        "prior_union_component_count": prior_counts["union_component_count"],
        "component_signature_correction_count": correction_count,
        "component_reconfirmation_count": reconfirmation_count,
        "reserved_meter_space_count": reserved_count,
        "overlay_component_count": len(component_ids),
    }
    if dict(coverage) != actual:
        raise V023ApplicationError("generated coverage mismatch")
    return actual


def build_applied_value(
    canonical_value: Any,
    prior_batch_value: Any,
    correction_batch_value: Any,
    canonical_sha256: str,
    prior_batch_sha256: str,
    correction_batch_sha256: str,
) -> dict[str, Any]:
    """Build and validate an in-memory v0.22 base plus bounded v0.23 overlay."""

    canonical = _mapping(canonical_value, "canonical replay")
    prior_batch = _mapping(prior_batch_value, "batch v0.22")
    correction_batch = _mapping(correction_batch_value, "batch v0.23")
    canonical_records, prior_counts, correction_counts = _validate_standard_inputs(
        canonical,
        prior_batch,
        correction_batch,
    )
    project_id = _string(canonical["project_id"], "canonical project_id")
    if (
        prior_batch.get("project_id") != project_id
        or correction_batch.get("project_id") != project_id
    ):
        raise V023ApplicationError("project_id mismatch across application inputs")
    prior_bindings = _mapping(
        prior_batch["source_bindings"],
        "batch v0.22 source_bindings",
    )
    correction_bindings = _mapping(
        correction_batch["source_bindings"],
        "batch v0.23 source_bindings",
    )
    if prior_bindings.get("canonical_bundle_sha256") != canonical_sha256:
        raise V023ApplicationError("batch v0.22 canonical SHA-256 binding mismatch")
    if correction_bindings.get("canonical_bundle_sha256") != canonical_sha256:
        raise V023ApplicationError("batch v0.23 canonical SHA-256 binding mismatch")
    if correction_bindings.get("prior_batch_sha256") != prior_batch_sha256:
        raise V023ApplicationError("batch v0.23 prior SHA-256 binding mismatch")

    prior_index = _prior_member_index(prior_batch)
    item_index = _v023_item_index(correction_batch)
    _validate_v023_semantics(
        canonical_records,
        prior_index,
        item_index,
        canonical_sha256,
        prior_batch_sha256,
    )

    projections = {
        DIRECT_COMPONENT_QUANTITY: [],
        CABINET_LEVEL_AGGREGATE: [],
        SCOPE_EXCLUSION: [],
    }
    for decision_value in _list(
        prior_batch["quantity_decisions"],
        "batch v0.22 quantity_decisions",
    ):
        decision = _mapping(decision_value, "batch v0.22 decision")
        kind = cast(str, decision["decision_kind"])
        projections[kind].append(
            _project_prior_decision(
                decision,
                canonical_records,
                item_index,
            )
        )

    component_overlays = []
    reserved_requirements = []
    for cabinet, item in item_index.values():
        if item["item_kind"] == RESERVED_METER_SPACE:
            reserved_requirements.append(_project_reserved_requirement(cabinet, item))
        else:
            component_overlays.append(_project_component_overlay(cabinet, item))

    coverage = {
        "canonical_component_count": len(canonical_records),
        "prior_direct_component_count": prior_counts["direct_component_count"],
        "prior_aggregate_member_count": prior_counts["aggregate_member_count"],
        "prior_exclusion_component_count": prior_counts["exclusion_component_count"],
        "prior_union_component_count": prior_counts["union_component_count"],
        "component_signature_correction_count": correction_counts[
            "component_signature_correction_count"
        ],
        "component_reconfirmation_count": correction_counts[
            "component_reconfirmation_count"
        ],
        "reserved_meter_space_count": correction_counts["reserved_meter_space_count"],
        "overlay_component_count": correction_counts["unique_component_count"],
    }
    applied = {
        "schema_version": APPLIED_SCHEMA_VERSION,
        "project_id": project_id,
        "application_status": APPLICATION_STATUS,
        "authority": AUTHORITY,
        "application_order": [
            PRIOR_BATCH_SCHEMA_VERSION,
            CORRECTION_BATCH_SCHEMA_VERSION,
        ],
        "source_lineage": {
            "canonical_replay_sha256": canonical_sha256,
            "canonical_replay_schema_version": REPLAY_SCHEMA_VERSION,
            "prior_batch_sha256": prior_batch_sha256,
            "prior_batch_schema_version": PRIOR_BATCH_SCHEMA_VERSION,
            "prior_batch_id": prior_batch["batch_id"],
            "correction_batch_sha256": correction_batch_sha256,
            "correction_batch_schema_version": CORRECTION_BATCH_SCHEMA_VERSION,
            "correction_batch_id": correction_batch["batch_id"],
            "correction_prior_batch_id": correction_batch["prior_batch_id"],
        },
        "canonical_component_evidence_records": copy.deepcopy(
            canonical["identified_component_evidence_records"]
        ),
        "prior_v0_22_application": {
            "application_status": APPLICATION_STATUS,
            "direct_component_quantities": projections[DIRECT_COMPONENT_QUANTITY],
            "cabinet_level_aggregates": projections[CABINET_LEVEL_AGGREGATE],
            "scope_exclusions": projections[SCOPE_EXCLUSION],
            "coverage": copy.deepcopy(prior_batch["coverage"]),
        },
        "component_signature_overlays": component_overlays,
        "reserved_meter_space_requirements": reserved_requirements,
        "coverage": coverage,
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    _validate_generated_value(applied)
    return applied


def _serialize(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _validated_output_path(
    output_json: Path,
    input_paths: Sequence[Path],
) -> Path:
    output_path = output_json.expanduser().resolve(strict=False)
    if output_path.is_relative_to(PROJECT_ROOT.resolve(strict=False)):
        raise V023ApplicationError("output JSON must be outside the Git project")
    resolved_inputs = {
        input_path.expanduser().resolve(strict=False) for input_path in input_paths
    }
    if output_path in resolved_inputs:
        raise V023ApplicationError("output JSON must not alias an input artifact")
    return output_path


def _atomic_write(output_json: Path, content: bytes, overwrite: bool) -> None:
    parent = output_json.parent
    if not parent.is_dir():
        raise V023ApplicationError("output parent directory does not exist")
    if output_json.exists() and not overwrite:
        raise V023ApplicationError("output already exists; use --overwrite explicitly")

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{output_json.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, output_json)
        else:
            os.link(temporary_path, output_json)
            temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def apply_artifacts(
    canonical_replay: Path,
    prior_batch_json: Path,
    correction_batch_json: Path,
    output_json: Path,
    *,
    overwrite: bool = False,
) -> ApplicationResult:
    """Validate three inputs and atomically write one outside-Git overlay."""

    result = ApplicationResult(
        canonical_replay,
        prior_batch_json,
        correction_batch_json,
        output_json,
    )
    try:
        output_path = _validated_output_path(
            output_json,
            (canonical_replay, prior_batch_json, correction_batch_json),
        )
        result.output_json = output_path
        if output_path.exists() and not overwrite:
            raise V023ApplicationError(
                "output already exists; use --overwrite explicitly"
            )
        canonical_content, canonical_value = _load_json(
            canonical_replay,
            "canonical replay",
        )
        prior_content, prior_value = _load_json(
            prior_batch_json,
            "batch v0.22",
        )
        correction_content, correction_value = _load_json(
            correction_batch_json,
            "batch v0.23",
        )
        result.canonical_replay_sha256 = hashlib.sha256(canonical_content).hexdigest()
        result.prior_batch_sha256 = hashlib.sha256(prior_content).hexdigest()
        result.correction_batch_sha256 = hashlib.sha256(correction_content).hexdigest()
        applied = build_applied_value(
            canonical_value,
            prior_value,
            correction_value,
            result.canonical_replay_sha256,
            result.prior_batch_sha256,
            result.correction_batch_sha256,
        )
        result.counts = dict(applied["coverage"])
        _atomic_write(output_path, _serialize(applied), overwrite)
        result.output_created = True
        result.status = "PASS"
    except (
        V023ApplicationError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a canonical replay, frozen v0.22 batch, and bounded v0.23 "
            "correction batch without creating confirmed composition."
        )
    )
    parser.add_argument("--canonical-replay", required=True, type=Path)
    parser.add_argument("--prior-batch-json", required=True, type=Path)
    parser.add_argument("--correction-batch-json", required=True, type=Path)
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="New applied bundle JSON path outside the Git project",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Atomically replace an existing outside-Git output; this never permits "
            "an output inside the Git project"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = apply_artifacts(
        args.canonical_replay,
        args.prior_batch_json,
        args.correction_batch_json,
        args.output_json,
        overwrite=args.overwrite,
    )
    print(REPORT_START)
    print(f"status: {result.status}")
    print(f"output_created: {str(result.output_created).lower()}")
    if result.status == "PASS":
        print(f"canonical_replay_sha256: {result.canonical_replay_sha256}")
        print(f"prior_batch_sha256: {result.prior_batch_sha256}")
        print(f"correction_batch_sha256: {result.correction_batch_sha256}")
        for key, value in result.counts.items():
            print(f"{key}: {value}")
    else:
        print(f"red_flag: {result.red_flags[0]}")
    print(REPORT_END)
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
