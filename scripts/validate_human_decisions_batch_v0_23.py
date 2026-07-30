"""Validate an unexecuted generic human decisions batch v0.23."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "human_decisions_batch.v0.23"
COMPATIBLE_WITH = "human_decisions_batch.v0.22"
BATCH_ID = "023"
PRIOR_BATCH_ID = "022"
ARTIFACT_STATUS = "FROZEN_HUMAN_APPROVAL_CORRECTIONS"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_STATUS = "NOT_EXECUTED"

COMPONENT_SIGNATURE_CORRECTION = "COMPONENT_SIGNATURE_CORRECTION"
COMPONENT_RECONFIRMATION = "COMPONENT_RECONFIRMATION"
RESERVED_METER_SPACE = "RESERVED_METER_SPACE"
ITEM_KINDS = {
    COMPONENT_SIGNATURE_CORRECTION,
    COMPONENT_RECONFIRMATION,
    RESERVED_METER_SPACE,
}
METER_CONNECTION = "THREE_PHASE_DIRECT"
FUTURE_INCLUSION_REQUIRES = "SEPARATE_METER_SELECTION_AND_IGOR_APPROVAL"
PROHIBITED_DOWNSTREAM = {
    "installed_composition",
    "pricing",
    "procurement",
    "production",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REPORT_START = "HUMAN_DECISIONS_BATCH_V023_VALIDATION_REPORT_START"
REPORT_END = "HUMAN_DECISIONS_BATCH_V023_VALIDATION_REPORT_END"

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
    "cabinet_records",
}
SOURCE_BINDING_FIELDS = {
    "canonical_bundle_sha256",
    "prior_batch_sha256",
}
CABINET_FIELDS = {
    "cabinet_record_id",
    "cabinet_template",
    "position_id",
    "section",
    "source_locator",
    "items",
}
SIGNATURE_FIELDS = {
    "component_identity",
    "model_type",
    "ratings",
    "poles",
    "functional_role",
}
PROVENANCE_FIELDS = {
    "source_artifact_sha256",
    "source_record_id",
    "source_locator",
}
COMPONENT_ITEM_FIELDS = {
    "item_id",
    "item_kind",
    "component_evidence_id",
    "original_signature",
    "approved_signature",
    "quantity_per_cabinet",
    "provenance",
    "correction_reason",
    "application_status",
}
RESERVED_ITEM_FIELDS = {
    "item_id",
    "item_kind",
    "component_evidence_id",
    "requirement_kind",
    "meter_connection",
    "reserved_space_per_cabinet",
    "installed_component",
    "original_identity",
    "provenance",
    "future_inclusion_requires",
    "prohibited_downstream",
    "application_status",
}


class BatchV023ValidationError(RuntimeError):
    """The v0.23 authority artifact violates its generic closed contract."""


class DuplicateJsonKeyError(ValueError):
    """A batch JSON object contains a duplicate key."""


@dataclass
class ValidationResult:
    batch_json: Path
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
        raise BatchV023ValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise BatchV023ValidationError(f"{label} fields mismatch")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BatchV023ValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchV023ValidationError(f"{label} must be a non-empty string")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BatchV023ValidationError(f"{label} must be a positive integer")
    return value


def _sha256(value: Any, label: str) -> str:
    result = _string(value, label)
    if SHA256_RE.fullmatch(result) is None:
        raise BatchV023ValidationError(f"{label} must be 64 lowercase hex")
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
                raise BatchV023ValidationError("quantity=0 is forbidden")
            _reject_zero_quantities(item)
    elif isinstance(value, list):
        for item in value:
            _reject_zero_quantities(item)


def _validate_signature(value: Any, label: str) -> Mapping[str, Any]:
    signature = _exact(value, label, SIGNATURE_FIELDS)
    _string(signature["component_identity"], f"{label}.component_identity")
    model_type = signature["model_type"]
    if model_type is not None:
        _string(model_type, f"{label}.model_type")
    ratings = [
        _string(item, f"{label}.ratings[]")
        for item in _list(signature["ratings"], f"{label}.ratings")
    ]
    if len(ratings) != len(set(ratings)):
        raise BatchV023ValidationError(f"{label} ratings must be unique")
    poles = signature["poles"]
    if poles is not None:
        _positive_int(poles, f"{label}.poles")
    _string(signature["functional_role"], f"{label}.functional_role")
    return signature


def _validate_provenance(
    value: Any,
    allowed_source_sha256: set[str],
) -> None:
    provenance = _exact(value, "item provenance", PROVENANCE_FIELDS)
    source_sha256 = _sha256(
        provenance["source_artifact_sha256"],
        "provenance.source_artifact_sha256",
    )
    if source_sha256 not in allowed_source_sha256:
        raise BatchV023ValidationError(
            "provenance source SHA-256 is not bound by source_bindings"
        )
    _string(provenance["source_record_id"], "provenance.source_record_id")
    _string(provenance["source_locator"], "provenance.source_locator")


def _validate_component_item(
    item: Mapping[str, Any],
    kind: str,
    allowed_source_sha256: set[str],
) -> None:
    original = _validate_signature(
        item["original_signature"],
        "original_signature",
    )
    approved = _validate_signature(
        item["approved_signature"],
        "approved_signature",
    )
    if kind == COMPONENT_SIGNATURE_CORRECTION and original == approved:
        raise BatchV023ValidationError(
            "signature correction requires different signatures"
        )
    if kind == COMPONENT_RECONFIRMATION and original != approved:
        raise BatchV023ValidationError(
            "component reconfirmation requires equal signatures"
        )
    _positive_int(
        item["quantity_per_cabinet"],
        f"{kind} quantity_per_cabinet",
    )
    _validate_provenance(item["provenance"], allowed_source_sha256)
    _string(item["correction_reason"], f"{kind} correction_reason")


def _validate_reserved_item(
    item: Mapping[str, Any],
    allowed_source_sha256: set[str],
) -> None:
    if item["requirement_kind"] != RESERVED_METER_SPACE:
        raise BatchV023ValidationError("reserved space requirement_kind mismatch")
    if item["meter_connection"] != METER_CONNECTION:
        raise BatchV023ValidationError("reserved space meter_connection mismatch")
    reserved_space = item["reserved_space_per_cabinet"]
    if isinstance(reserved_space, bool) or reserved_space != 1:
        raise BatchV023ValidationError("reserved_space_per_cabinet must equal 1")
    if item["installed_component"] is not False:
        raise BatchV023ValidationError(
            "reserved meter space cannot be an installed component"
        )
    _string(item["original_identity"], "reserved space original_identity")
    _validate_provenance(item["provenance"], allowed_source_sha256)
    if item["future_inclusion_requires"] != FUTURE_INCLUSION_REQUIRES:
        raise BatchV023ValidationError(
            "reserved space future_inclusion_requires mismatch"
        )
    downstream = [
        _string(entry, "reserved space prohibited_downstream[]")
        for entry in _list(
            item["prohibited_downstream"],
            "reserved space prohibited_downstream",
        )
    ]
    if set(downstream) != PROHIBITED_DOWNSTREAM or len(downstream) != len(
        PROHIBITED_DOWNSTREAM
    ):
        raise BatchV023ValidationError("reserved space prohibited_downstream mismatch")


def validate_batch_value(batch_value: Any) -> Mapping[str, int]:
    """Validate a generic frozen v0.23 authority artifact."""

    batch = _exact(batch_value, "batch v0.23", ROOT_FIELDS)
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
            raise BatchV023ValidationError(f"batch v0.23 {key} mismatch")
    _string(batch["case_id"], "batch v0.23 case_id")
    _string(batch["project_id"], "batch v0.23 project_id")

    bindings = _exact(
        batch["source_bindings"],
        "batch v0.23 source_bindings",
        SOURCE_BINDING_FIELDS,
    )
    canonical_sha256 = _sha256(
        bindings["canonical_bundle_sha256"],
        "source_bindings.canonical_bundle_sha256",
    )
    prior_batch_sha256 = _sha256(
        bindings["prior_batch_sha256"],
        "source_bindings.prior_batch_sha256",
    )
    allowed_source_sha256 = {
        canonical_sha256,
        prior_batch_sha256,
    }

    cabinets = _list(batch["cabinet_records"], "cabinet_records")
    if not cabinets:
        raise BatchV023ValidationError("cabinet_records must be non-empty")
    cabinet_ids: set[str] = set()
    item_ids: set[str] = set()
    component_ids: set[str] = set()
    counts = {
        "cabinet_record_count": 0,
        "item_count": 0,
        "component_signature_correction_count": 0,
        "component_reconfirmation_count": 0,
        "reserved_meter_space_count": 0,
        "unique_component_count": 0,
    }
    count_field_by_kind = {
        COMPONENT_SIGNATURE_CORRECTION: ("component_signature_correction_count"),
        COMPONENT_RECONFIRMATION: "component_reconfirmation_count",
        RESERVED_METER_SPACE: "reserved_meter_space_count",
    }
    for raw_cabinet in cabinets:
        cabinet = _exact(raw_cabinet, "cabinet record", CABINET_FIELDS)
        cabinet_id = _string(
            cabinet["cabinet_record_id"],
            "cabinet_record_id",
        )
        if cabinet_id in cabinet_ids:
            raise BatchV023ValidationError("duplicate cabinet_record_id")
        cabinet_ids.add(cabinet_id)
        _string(cabinet["cabinet_template"], "cabinet_template")
        _string(cabinet["position_id"], "cabinet position_id")
        _string(cabinet["section"], "cabinet section")
        _string(cabinet["source_locator"], "cabinet source_locator")
        items = _list(cabinet["items"], "cabinet items")
        if not items:
            raise BatchV023ValidationError("cabinet items must be non-empty")
        counts["cabinet_record_count"] += 1
        reserved_space_count = 0

        for raw_item in items:
            base = _mapping(raw_item, "cabinet item")
            kind = base.get("item_kind")
            if kind not in ITEM_KINDS:
                raise BatchV023ValidationError("unknown item_kind")
            expected_fields = (
                RESERVED_ITEM_FIELDS
                if kind == RESERVED_METER_SPACE
                else COMPONENT_ITEM_FIELDS
            )
            item = _exact(base, f"{kind} item", expected_fields)
            item_id = _string(item["item_id"], "item_id")
            component_id = _string(
                item["component_evidence_id"],
                "component_evidence_id",
            )
            if item_id in item_ids:
                raise BatchV023ValidationError("duplicate item_id")
            if component_id in component_ids:
                raise BatchV023ValidationError(
                    "COMP occurs more than once in batch v0.23"
                )
            item_ids.add(item_id)
            component_ids.add(component_id)
            if item["application_status"] != APPLICATION_STATUS:
                raise BatchV023ValidationError("item application_status mismatch")

            if kind == RESERVED_METER_SPACE:
                reserved_space_count += 1
                if reserved_space_count > 1:
                    raise BatchV023ValidationError(
                        "cabinet record contains more than one reserved meter space"
                    )
                _validate_reserved_item(item, allowed_source_sha256)
            else:
                _validate_component_item(
                    item,
                    cast(str, kind),
                    allowed_source_sha256,
                )
            counts[count_field_by_kind[cast(str, kind)]] += 1
            counts["item_count"] += 1

    counts["unique_component_count"] = len(component_ids)
    return counts


def validate_batch_artifact(batch_json: Path) -> ValidationResult:
    result = ValidationResult(batch_json)
    try:
        value = json.loads(
            batch_json.read_bytes(),
            object_pairs_hook=_duplicate_key_guard,
        )
        result.counts = dict(validate_batch_value(value))
        result.status = "PASS"
    except (
        BatchV023ValidationError,
        DuplicateJsonKeyError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an unexecuted generic human decisions batch v0.23."
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
