"""Validate the bounded N/PE replay row-alignment correction artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "component_replay_row_alignment_correction.v0.1"
ARTIFACT_STATUS = "FROZEN_BOUNDED_ROW_ALIGNMENT_CORRECTIONS"
CORRECTION_ACTION = "DETACH_ADJACENT_CABINET_TEXT"
COMPONENT_IDENTITY = "ШИНА N/PE"
ADJACENT_TEXT = "ЩРН-12"
REPORT_START = "COMPONENT_REPLAY_ROW_ALIGNMENT_CORRECTION_REPORT_START"
REPORT_END = "COMPONENT_REPLAY_ROW_ALIGNMENT_CORRECTION_REPORT_END"

APPROVED_CORRECTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("ICF-049", "COMP-040", "TFE-018", "10"),
    ("ICF-055", "COMP-137", "TFE-063", "14"),
    ("ICF-059", "COMP-187", "TFE-085", "16"),
)

ROOT_FIELDS = {
    "schema_version",
    "case_id",
    "project_id",
    "artifact_status",
    "source_bindings",
    "corrections",
    "safety",
}
SOURCE_BINDING_FIELDS = {
    "cumulative_review_sha256",
    "field_applicability_sha256",
}
CORRECTION_FIELDS = {
    "correction_id",
    "record_id",
    "component_evidence_id",
    "evidence_position_id",
    "section",
    "action",
    "original_conflict",
    "corrected_component",
    "preserves_original_evidence",
    "creates_new_evidence_id",
}
ORIGINAL_FIELDS = {
    "raw_designation",
    "raw_type_model",
    "raw_quantity",
    "applicability_classification",
    "remediation_route",
    "provenance",
}
CORRECTED_FIELDS = {
    "component_identity",
    "detached_adjacent_text",
    "quantity_per_cabinet",
}
SAFETY_FIELDS = {
    "frozen_sources_modified",
    "extraction_repeated",
    "new_evidence_ids_created",
    "confirmed_composition_created",
    "pricing_executed",
}


class CorrectionValidationError(RuntimeError):
    """The bounded correction artifact violates its closed contract."""


@dataclass
class ValidationResult:
    correction_json: Path
    status: str = "FAIL"
    red_flags: list[str] = field(default_factory=list)
    corrections: tuple[Mapping[str, Any], ...] = ()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CorrectionValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    if set(result) != fields:
        raise CorrectionValidationError(f"{label} fields mismatch")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CorrectionValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorrectionValidationError(f"{label} must be a non-empty string")
    return value


def _hash(value: Any, label: str) -> str:
    result = _string(value, label)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise CorrectionValidationError(f"{label} must be lowercase SHA-256")
    return result


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_equal(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _read_json(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        raise CorrectionValidationError(f"could not read {label}") from exc
    return content, _mapping(value, label)


def _source_records(
    cumulative: Mapping[str, Any],
    applicability: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    components: dict[str, Mapping[str, Any]] = {}
    for raw_position in _list(cumulative.get("positions"), "cumulative.positions"):
        position = _mapping(raw_position, "cumulative.positions[]")
        position_id = _string(
            position.get("evidence_position_id"),
            "cumulative evidence_position_id",
        )
        fields = _mapping(position.get("technical_fields"), "technical_fields")
        component_field = _mapping(fields.get("components"), "components")
        for raw_entry in _list(
            component_field.get("evidence_values"),
            "components.evidence_values",
        ):
            entry = _mapping(raw_entry, "components.evidence_values[]")
            evidence_id = entry.get("component_evidence_id")
            if evidence_id is None:
                continue
            evidence_id = _string(evidence_id, "component_evidence_id")
            if evidence_id in components:
                raise CorrectionValidationError(
                    "duplicate source component evidence ID"
                )
            components[evidence_id] = {
                "evidence_position_id": position_id,
                "value": entry.get("value"),
                "provenance": entry.get("provenance"),
            }

    records: dict[str, Mapping[str, Any]] = {}
    for raw_record in _list(applicability.get("records"), "applicability.records"):
        record = _mapping(raw_record, "applicability.records[]")
        record_id = _string(record.get("record_id"), "record_id")
        if record_id in records:
            raise CorrectionValidationError("duplicate applicability record ID")
        records[record_id] = record
    return components, records


def validate_correction_data(
    correction_value: Any,
    *,
    cumulative: Mapping[str, Any],
    cumulative_sha256: str,
    applicability: Mapping[str, Any],
    applicability_sha256: str,
    project_id: str,
) -> tuple[Mapping[str, Any], ...]:
    """Validate and project the three approved corrections."""

    correction = _exact(correction_value, "correction", ROOT_FIELDS)
    if correction["schema_version"] != SCHEMA_VERSION:
        raise CorrectionValidationError("unknown correction schema/version")
    if correction["artifact_status"] != ARTIFACT_STATUS:
        raise CorrectionValidationError("correction artifact_status mismatch")
    _string(correction["case_id"], "correction.case_id")
    if correction["project_id"] != project_id:
        raise CorrectionValidationError("correction project_id mismatch")

    bindings = _exact(
        correction["source_bindings"],
        "correction.source_bindings",
        SOURCE_BINDING_FIELDS,
    )
    if (
        _hash(
            bindings["cumulative_review_sha256"],
            "source_bindings.cumulative_review_sha256",
        )
        != cumulative_sha256
        or _hash(
            bindings["field_applicability_sha256"],
            "source_bindings.field_applicability_sha256",
        )
        != applicability_sha256
    ):
        raise CorrectionValidationError("correction source binding mismatch")

    safety = _exact(correction["safety"], "correction.safety", SAFETY_FIELDS)
    if any(safety.values()):
        raise CorrectionValidationError("correction safety flags must remain false")

    components, records = _source_records(cumulative, applicability)
    corrections = _list(correction["corrections"], "correction.corrections")
    if len(corrections) != len(APPROVED_CORRECTIONS):
        raise CorrectionValidationError("exactly three corrections are required")

    projected: list[Mapping[str, Any]] = []
    actual_fingerprints: set[tuple[str, str, str, str]] = set()
    correction_ids: set[str] = set()
    for raw_item in corrections:
        item = _exact(raw_item, "correction.corrections[]", CORRECTION_FIELDS)
        correction_id = _string(item["correction_id"], "correction_id")
        if correction_id in correction_ids:
            raise CorrectionValidationError("duplicate correction_id")
        correction_ids.add(correction_id)
        fingerprint = (
            _string(item["record_id"], "record_id"),
            _string(item["component_evidence_id"], "component_evidence_id"),
            _string(item["evidence_position_id"], "evidence_position_id"),
            _string(item["section"], "section"),
        )
        if fingerprint in actual_fingerprints:
            raise CorrectionValidationError("duplicate correction mapping")
        actual_fingerprints.add(fingerprint)
        if fingerprint not in APPROVED_CORRECTIONS:
            raise CorrectionValidationError("unknown correction mapping")
        if item["action"] != CORRECTION_ACTION:
            raise CorrectionValidationError("unknown correction action")
        if (
            item["preserves_original_evidence"] is not True
            or item["creates_new_evidence_id"] is not False
        ):
            raise CorrectionValidationError("correction evidence boundary mismatch")

        record = records.get(fingerprint[0])
        component = components.get(fingerprint[1])
        if record is None or component is None:
            raise CorrectionValidationError("correction source record is missing")
        if (
            record.get("component_evidence_id") != fingerprint[1]
            or record.get("evidence_position_id") != fingerprint[2]
            or record.get("section") != fingerprint[3]
            or component.get("evidence_position_id") != fingerprint[2]
        ):
            raise CorrectionValidationError("correction/source mapping mismatch")
        if component.get("value") != COMPONENT_IDENTITY:
            raise CorrectionValidationError("correction source identity mismatch")

        original = _exact(
            item["original_conflict"],
            "correction.original_conflict",
            ORIGINAL_FIELDS,
        )
        expected_original = {
            "raw_designation": record.get("raw_designation"),
            "raw_type_model": record.get("raw_type_model"),
            "raw_quantity": record.get("raw_quantity"),
            "applicability_classification": record.get("applicability_classification"),
            "remediation_route": record.get("remediation_route"),
            "provenance": component.get("provenance"),
        }
        if not _safe_equal(original, expected_original):
            raise CorrectionValidationError(
                "original conflict/provenance was not preserved"
            )
        if (
            original["applicability_classification"] != "REQUIRED_VALUE_CONFLICTED"
            or original["remediation_route"]
            != "EXTRACTOR_ROW_ALIGNMENT_CORRECTION_REQUIRED"
            or original["raw_quantity"] is not None
            or original["raw_type_model"] != ADJACENT_TEXT
            or "Шина N и PE"
            not in _string(
                original["raw_designation"],
                "original raw_designation",
            )
            or "Щит модульный" not in original["raw_designation"]
        ):
            raise CorrectionValidationError("source is not the approved row conflict")

        corrected = _exact(
            item["corrected_component"],
            "correction.corrected_component",
            CORRECTED_FIELDS,
        )
        if corrected != {
            "component_identity": COMPONENT_IDENTITY,
            "detached_adjacent_text": ADJACENT_TEXT,
            "quantity_per_cabinet": None,
        }:
            raise CorrectionValidationError("corrected component boundary mismatch")

        projected.append(
            {
                "correction_id": correction_id,
                "record_id": fingerprint[0],
                "component_evidence_id": fingerprint[1],
                "evidence_position_id": fingerprint[2],
                "section": fingerprint[3],
                "action": CORRECTION_ACTION,
                "original_conflict": original,
                "corrected_component": corrected,
                "preserves_original_evidence": True,
                "creates_new_evidence_id": False,
                "application_status": "VALIDATED_NOT_MUTATED",
            }
        )

    if actual_fingerprints != set(APPROVED_CORRECTIONS):
        raise CorrectionValidationError("incomplete approved correction mapping")
    return tuple(
        sorted(projected, key=lambda item: cast(str, item["component_evidence_id"]))
    )


def validate_correction_artifact(
    correction_json: Path,
    cumulative_review_json: Path,
    field_applicability_json: Path,
) -> ValidationResult:
    result = ValidationResult(correction_json)
    try:
        correction_content, correction = _read_json(
            correction_json,
            "correction artifact",
        )
        cumulative_content, cumulative = _read_json(
            cumulative_review_json,
            "cumulative review",
        )
        applicability_content, applicability = _read_json(
            field_applicability_json,
            "field applicability",
        )
        del correction_content
        project_id = _string(cumulative.get("project_id"), "cumulative project_id")
        result.corrections = validate_correction_data(
            correction,
            cumulative=cumulative,
            cumulative_sha256=_sha256(cumulative_content),
            applicability=applicability,
            applicability_sha256=_sha256(applicability_content),
            project_id=project_id,
        )
        result.status = "PASS"
    except (CorrectionValidationError, OSError) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate bounded N/PE replay row-alignment corrections."
    )
    parser.add_argument("--correction-json", required=True, type=Path)
    parser.add_argument("--cumulative-review-json", required=True, type=Path)
    parser.add_argument("--field-applicability-json", required=True, type=Path)
    return parser.parse_args(argv)


def format_report(result: ValidationResult) -> str:
    lines = [
        REPORT_START,
        f"status: {result.status}",
        f"correction_count: {len(result.corrections)}",
    ]
    lines.extend(f"red_flag: {flag}" for flag in result.red_flags)
    lines.append(REPORT_END)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_correction_artifact(
        args.correction_json,
        args.cumulative_review_json,
        args.field_applicability_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
