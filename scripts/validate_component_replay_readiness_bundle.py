"""Validate a replay readiness bundle directly from frozen source schemas."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

INTAKE_SCHEMA = "component_replay_intake.v0.1"
BUNDLE_SCHEMA = "component_replay_readiness_bundle.v0.1"
BUNDLE_STATUS = "PRELIMINARY_REPLAY_ONLY_NOT_CONFIRMED"
BUNDLE_NAME = "component_replay_readiness_bundle.json"

CUMULATIVE_SCHEMA = "technical_field_component_scheme_completion_review.v0.1"
APPLICABILITY_SCHEMA = "unresolved_field_applicability_audit.v0.1"
AUTHORITY_SCHEMAS = (
    "human_decisions_batch.v0.17",
    "human_decisions_batch.v0.18",
    "human_decisions_batch.v0.19",
    "human_decisions_batch.v0.20",
)
SCHEMA_ROLES = {
    CUMULATIVE_SCHEMA: "cumulative_review",
    APPLICABILITY_SCHEMA: "field_applicability",
    **{schema: "authority_batch" for schema in AUTHORITY_SCHEMAS},
}
SCHEMA_STATUSES = {
    CUMULATIVE_SCHEMA: "REVIEW_ONLY_NOT_CONFIRMED",
    APPLICABILITY_SCHEMA: "READY_FOR_HUMAN_FIELD_APPLICABILITY_REVIEW",
    **{schema: "FROZEN_HUMAN_APPROVAL_DECISIONS" for schema in AUTHORITY_SCHEMAS},
}
AUTHORITY_CODES = {
    "human_decisions_batch.v0.17": {"CE1", "CE2A", "CE2B", "D1A"},
    "human_decisions_batch.v0.18": {"IP1"},
    "human_decisions_batch.v0.19": {"H19-1", "H19-2", "H19-3", "H19-4"},
    "human_decisions_batch.v0.20": {"H20-1", "H20-2", "H20-3", "H20-4"},
}
AUTHORITY_COMPATIBILITY = {
    "human_decisions_batch.v0.17": "human_decisions_batch.v0.16",
    "human_decisions_batch.v0.18": "human_decisions_batch.v0.17",
    "human_decisions_batch.v0.19": "human_decisions_batch.v0.18",
    "human_decisions_batch.v0.20": "human_decisions_batch.v0.19",
}
AUTHORITY_PRIOR_BATCH = {
    "human_decisions_batch.v0.19": "018",
    "human_decisions_batch.v0.20": "019",
}
AUTHORITY_VALUE = {
    "human_decisions_batch.v0.17": "IGOR_HUMAN_APPROVAL",
    "human_decisions_batch.v0.18": "IGOR_HUMAN_APPROVAL",
    "human_decisions_batch.v0.19": "IGOR_DIRECT_HUMAN_APPROVAL",
    "human_decisions_batch.v0.20": "IGOR_DIRECT_HUMAN_APPROVAL",
}

CLASSIFICATIONS = {
    "EXPLICIT_RAW_VALUE_NOT_NORMALIZED",
    "FIELD_NOT_APPLICABLE_BUT_SCHEMA_CHANGE_REQUIRED",
    "FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT",
    "FIELD_SEMANTICS_MISMATCH",
    "REQUIRED_VALUE_CONFLICTED",
    "REQUIRED_VALUE_MISSING",
    "UNDETERMINED_REQUIRES_IGOR",
}
QUANTITY_BLOCKER_CLASSES = {
    "REQUIRED_VALUE_CONFLICTED",
    "REQUIRED_VALUE_MISSING",
}
REQUIRED_FUNCTIONS = {
    "classify_component_field_applicability",
    "normalize_explicit_component_model_type",
}
REQUIRED_TYPES = {"ComponentCandidate", "Provenance"}
COUNT_FIELDS = {
    "canonical_position_count",
    "component_bearing_position_count",
    "component_field_evidence_entry_count",
    "component_absence_evidence_entry_count",
    "identified_component_evidence_record_count",
    "unique_component_evidence_id_count",
    "position_quantity_total",
}
INVARIANT_TYPES = {
    "POSITION_QUANTITY_TOTAL_EQUALS",
    "PARTITION_QUANTITY_EQUALS",
}
REQUIRED_INVARIANTS = {
    "COUNTS_MATCH_FROZEN_STATE",
    "POSITION_BOUNDARIES_PRESERVED",
    "BLOCKERS_PRESERVED",
    "SUPPLY_BOUNDARY_PRESERVED",
    "COMPLETE_SET_EXCLUSIVE",
    "APPLICABILITY_CONFORMS_TO_OWNER",
}
INTAKE_FIELDS = {
    "schema_version",
    "case_id",
    "project_id",
    "source_artifacts",
    "authority_lineage",
    "policy_binding",
    "expected_counts",
    "expected_quantity_invariants",
    "required_invariants",
    "supply_boundary",
    "complete_set_rules",
    "blocker_requirements",
    "safety",
    "output_contract",
}
DESCRIPTOR_FIELDS = {
    "role",
    "input_path",
    "schema_version",
    "sha256",
    "case_id",
    "project_id",
    "artifact_status",
}
ROOT_FIELDS = {
    "schema_version",
    "bundle_id",
    "artifact_status",
    "project_id",
    "source_artifacts",
    "authority_lineage",
    "policy_conformance",
    "counts",
    "quantity_invariants",
    "positions",
    "identified_component_evidence_records",
    "field_applicability_records",
    "component_absence_evidence",
    "blockers",
    "supply_boundary",
    "complete_set_controls",
    "safety",
    "next_required_human_actions",
}
FORBIDDEN_OUTPUT_KEYS = {
    "canonical_components",
    "canonical_component_count",
    "confirmed_composition",
    "confirmed_by",
    "input_path",
}
DOWNSTREAM_FLAG_NAMES = {
    "calculator_run",
    "commercial_csv_created",
    "confirmed_composition_created",
    "csv_created",
    "excel_pdf_quote_created",
    "excel_quote_or_invoice_created",
    "pdf_quote_or_invoice_created",
    "price_tables_read",
    "pricing_created",
    "pricing_executed",
    "procurement_actions_started",
    "procurement_started",
    "production_actions_started",
    "production_started",
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class ReplayValidationError(RuntimeError):
    """A fail-closed direct replay validation failure."""


class DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


@dataclass(frozen=True)
class ArtifactSnapshot:
    descriptor: Mapping[str, Any]
    path: Path
    case_dir: Path
    content: bytes
    data: Mapping[str, Any]


@dataclass(frozen=True)
class DirectProjection:
    positions: tuple[Mapping[str, Any], ...]
    identified_records: tuple[Mapping[str, Any], ...]
    applicability_records: tuple[Mapping[str, Any], ...]
    absence_records: tuple[Mapping[str, Any], ...]
    blockers: tuple[Mapping[str, Any], ...]
    supply_boundary: Mapping[str, Any]
    complete_set_controls: Mapping[str, Any]
    authority_lineage: Mapping[str, Any]
    counts: Mapping[str, int | float]
    quantity_invariants: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class IntakeContext:
    manifest_path: Path
    manifest_content: bytes
    manifest: Mapping[str, Any]
    artifacts: tuple[ArtifactSnapshot, ...]
    cumulative: ArtifactSnapshot
    applicability: ArtifactSnapshot
    authority_batches: tuple[ArtifactSnapshot, ...]
    projection: DirectProjection


@dataclass
class ValidationResult:
    intake_manifest: Path
    bundle_json: Path
    status: str = "FAIL"
    red_flags: list[str] = field(default_factory=list)


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_json_bytes(content: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
        )
    except DuplicateJsonKeyError as exc:
        raise ReplayValidationError(
            f"{label} contains duplicate JSON key: {exc}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayValidationError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ReplayValidationError(f"{label} root must be an object")
    return cast(Mapping[str, Any], value)


def _read_json(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ReplayValidationError(f"missing or unreadable {label}: {path}") from exc
    return content, _load_json_bytes(content, label)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayValidationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact_object(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    actual = {str(key) for key in result}
    missing = sorted(fields - actual)
    unknown = sorted(actual - fields)
    if missing:
        raise ReplayValidationError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise ReplayValidationError(f"{label} unknown fields: {', '.join(unknown)}")
    return result


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReplayValidationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayValidationError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _string(value, label)


def _number(value: Any, label: str, *, nonnegative: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReplayValidationError(f"{label} must be a number")
    if nonnegative and value < 0:
        raise ReplayValidationError(f"{label} must be nonnegative")
    return cast(int | float, value)


def _integer(value: Any, label: str, *, nonnegative: bool = False) -> int:
    number = _number(value, label, nonnegative=nonnegative)
    if not isinstance(number, int):
        raise ReplayValidationError(f"{label} must be an integer")
    return number


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ReplayValidationError(f"{label} must be boolean")
    return value


def _safe_equal(left: Any, right: Any) -> bool:
    return _canonical_bytes(left) == _canonical_bytes(right)


def _require_fields(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    result = _mapping(value, label)
    missing = sorted(fields - {str(key) for key in result})
    if missing:
        raise ReplayValidationError(f"{label} missing fields: {', '.join(missing)}")
    return result


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_blob_bytes(commit: str, owner_path: str) -> bytes:
    root = _repo_root()
    if COMMIT_RE.fullmatch(commit) is None:
        raise ReplayValidationError("policy source_commit must be a full commit ID")
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReplayValidationError("policy source commit does not exist") from exc
    try:
        blob_id = subprocess.run(
            ["git", "rev-parse", f"{commit}:{owner_path}"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return subprocess.run(
            ["git", "cat-file", "blob", blob_id],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReplayValidationError(
            "policy owner blob is missing in source commit"
        ) from exc


def _load_policy_owner(binding_value: Any) -> ModuleType:
    binding = _exact_object(
        binding_value,
        "policy_binding",
        {
            "source_commit",
            "owner_path",
            "owner_sha256",
            "function_names",
            "required_types",
            "expected_classification_counts",
        },
    )
    owner_path = _string(binding["owner_path"], "policy_binding.owner_path")
    if owner_path != "scripts/project_spec_extraction.py":
        raise ReplayValidationError("policy owner_path is not canonical")
    expected_hash = _string(binding["owner_sha256"], "policy_binding.owner_sha256")
    if HASH_RE.fullmatch(expected_hash) is None:
        raise ReplayValidationError("policy owner_sha256 is invalid")
    function_names = {
        _string(item, "policy_binding.function_names[]")
        for item in _list(binding["function_names"], "policy_binding.function_names")
    }
    required_types = {
        _string(item, "policy_binding.required_types[]")
        for item in _list(binding["required_types"], "policy_binding.required_types")
    }
    if function_names != REQUIRED_FUNCTIONS or required_types != REQUIRED_TYPES:
        raise ReplayValidationError("policy required symbols mismatch")
    commit = _string(binding["source_commit"], "policy_binding.source_commit")
    if _sha256(_git_blob_bytes(commit, owner_path)) != expected_hash:
        raise ReplayValidationError("policy owner blob SHA-256 mismatch")
    current_path = _repo_root() / Path(owner_path)
    try:
        current_content = current_path.read_bytes()
    except OSError as exc:
        raise ReplayValidationError("current policy owner is missing") from exc
    if _sha256(current_content) != expected_hash:
        raise ReplayValidationError("current policy owner SHA-256 mismatch")
    spec = importlib.util.spec_from_file_location(
        "component_replay_direct_policy_owner",
        current_path,
    )
    if spec is None or spec.loader is None:
        raise ReplayValidationError("could not load current policy owner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for name in REQUIRED_FUNCTIONS | REQUIRED_TYPES:
        if not hasattr(module, name):
            raise ReplayValidationError(f"policy owner missing required symbol: {name}")
    return module


def _validate_descriptor(
    descriptor_value: Any,
    manifest_project_id: str,
) -> ArtifactSnapshot:
    descriptor = _exact_object(
        descriptor_value,
        "source_artifacts[]",
        DESCRIPTOR_FIELDS,
    )
    role = _string(descriptor["role"], "source_artifacts[].role")
    schema = _string(descriptor["schema_version"], "source_artifacts[].schema_version")
    if schema not in SCHEMA_ROLES:
        raise ReplayValidationError(f"unknown direct input schema: {schema}")
    if role != SCHEMA_ROLES[schema]:
        raise ReplayValidationError(f"role/schema mismatch for {schema}")
    raw_path = Path(_string(descriptor["input_path"], "source_artifacts[].input_path"))
    if not raw_path.is_absolute():
        raise ReplayValidationError("input_path must be absolute")
    path = raw_path.resolve(strict=False)
    if not path.is_file():
        raise ReplayValidationError(f"direct input is missing: {path}")
    content, data = _read_json(path, f"{role} direct input")
    expected_hash = _string(descriptor["sha256"], "source_artifacts[].sha256")
    if HASH_RE.fullmatch(expected_hash) is None or _sha256(content) != expected_hash:
        raise ReplayValidationError(f"{role} SHA-256 mismatch")
    checks = {
        "schema_version": schema,
        "case_id": _string(descriptor["case_id"], "source_artifacts[].case_id"),
        "project_id": manifest_project_id,
        "artifact_status": SCHEMA_STATUSES[schema],
    }
    for key, expected in checks.items():
        if descriptor[key] != expected or data.get(key) != expected:
            raise ReplayValidationError(f"{role} {key} mismatch")
    if descriptor["project_id"] != manifest_project_id:
        raise ReplayValidationError("mixed project_id in source descriptor")
    return ArtifactSnapshot(descriptor, path, path.parent, content, data)


def _validate_authority_chain(
    lineage_value: Any,
    batches: Sequence[ArtifactSnapshot],
) -> Mapping[str, Any]:
    lineage = _exact_object(
        lineage_value,
        "authority_lineage",
        {"ordered_schemas", "ordered_batch_ids"},
    )
    ordered_schemas = [
        _string(item, "authority_lineage.ordered_schemas[]")
        for item in _list(
            lineage["ordered_schemas"],
            "authority_lineage.ordered_schemas",
        )
    ]
    ordered_ids = [
        _string(item, "authority_lineage.ordered_batch_ids[]")
        for item in _list(
            lineage["ordered_batch_ids"],
            "authority_lineage.ordered_batch_ids",
        )
    ]
    if tuple(ordered_schemas) != AUTHORITY_SCHEMAS:
        raise ReplayValidationError("authority schema lineage order mismatch")
    if len(ordered_ids) != 4 or len(set(ordered_ids)) != 4:
        raise ReplayValidationError("authority batch ID lineage must contain four IDs")
    by_schema = {
        cast(str, batch.descriptor["schema_version"]): batch for batch in batches
    }
    if set(by_schema) != set(AUTHORITY_SCHEMAS) or len(batches) != 4:
        raise ReplayValidationError(
            "exactly authority batches v0.17-v0.20 are required"
        )
    projected: list[Mapping[str, Any]] = []
    for schema, expected_id in zip(ordered_schemas, ordered_ids, strict=True):
        batch = by_schema[schema]
        data = batch.data
        batch_id = _string(data.get("batch_id"), f"{schema}.batch_id")
        if batch_id != expected_id:
            raise ReplayValidationError(f"{schema} batch_id mismatch")
        if data.get("compatible_with") != AUTHORITY_COMPATIBILITY[schema]:
            raise ReplayValidationError(f"{schema} compatible_with mismatch")
        if schema in AUTHORITY_PRIOR_BATCH:
            if data.get("prior_batch_id") != AUTHORITY_PRIOR_BATCH[schema]:
                raise ReplayValidationError(f"{schema} prior_batch_id mismatch")
        elif "prior_batch_id" in data:
            raise ReplayValidationError(f"{schema} must not contain prior_batch_id")
        decisions = _list(
            data.get("technical_field_decisions"),
            f"{schema}.technical_field_decisions",
        )
        if not decisions:
            raise ReplayValidationError(f"{schema} decisions must not be empty")
        decision_ids: set[str] = set()
        actual_codes: set[str] = set()
        for raw_decision in decisions:
            decision = _require_fields(
                raw_decision,
                f"{schema}.technical_field_decisions[]",
                {
                    "decision_id",
                    "decision_code",
                    "authority",
                    "accepted_status",
                },
            )
            decision_id = _string(
                decision["decision_id"],
                f"{schema}.decision_id",
            )
            if decision_id in decision_ids:
                raise ReplayValidationError(f"{schema} duplicate decision_id")
            decision_ids.add(decision_id)
            code = _string(decision["decision_code"], f"{schema}.decision_code")
            if code not in AUTHORITY_CODES[schema]:
                raise ReplayValidationError(f"{schema} unknown decision_code: {code}")
            actual_codes.add(code)
            if decision["authority"] != AUTHORITY_VALUE[schema]:
                raise ReplayValidationError(f"{schema} unknown decision authority")
            if decision["accepted_status"] != "APPROVED_BY_IGOR":
                raise ReplayValidationError(f"{schema} unknown accepted_status")
        projected.append(
            {
                "schema_version": schema,
                "batch_id": batch_id,
                "case_id": batch.descriptor["case_id"],
                "sha256": batch.descriptor["sha256"],
                "artifact_status": batch.descriptor["artifact_status"],
                "compatible_with": data["compatible_with"],
                "prior_batch_id": data.get("prior_batch_id"),
                "decision_codes": sorted(actual_codes),
                "decision_count": len(decisions),
            }
        )
    return {
        "ordered_batches": projected,
        "lineage_only": True,
        "replayed_over_cumulative_review": False,
    }


def _position_boundary(position: Mapping[str, Any]) -> tuple[str, str, str]:
    position_id = _string(position.get("evidence_position_id"), "position ID")
    identity = _require_fields(
        position.get("canonical_identity"),
        f"{position_id}.canonical_identity",
        {"section_id"},
    )
    source = _require_fields(
        position.get("project_source"),
        f"{position_id}.project_source",
        {"pdf", "pdf_sha256"},
    )
    section = _string(identity["section_id"], f"{position_id}.section_id")
    document = _string(source["pdf"], f"{position_id}.project_source.pdf")
    if Path(document).is_absolute() or WINDOWS_ABSOLUTE_RE.match(document):
        raise ReplayValidationError("absolute source path cannot enter projection")
    return position_id, section, document


def _project_provenance(value: Any, label: str) -> Mapping[str, Any]:
    source = _mapping(value, label)
    allowed = (
        "pdf",
        "pdf_sha256",
        "page",
        "specification_position_or_locator",
        "source_decision_ids",
        "source_record_ids",
        "row_locator",
    )
    projected = {key: source[key] for key in allowed if key in source}
    pdf = projected.get("pdf")
    if isinstance(pdf, str) and (
        Path(pdf).is_absolute() or WINDOWS_ABSOLUTE_RE.match(pdf)
    ):
        raise ReplayValidationError("absolute provenance path cannot enter projection")
    return projected


def _field_values(
    position: Mapping[str, Any],
    field_name: str,
    position_id: str,
) -> tuple[Mapping[str, Any], list[Any]]:
    technical = _mapping(position.get("technical_fields"), f"{position_id}.technical")
    field_value = _mapping(
        technical.get(field_name),
        f"{position_id}.technical_fields.{field_name}",
    )
    values = field_value.get("evidence_values", [])
    return field_value, _list(
        values,
        f"{position_id}.{field_name}.evidence_values",
    )


def _project_cumulative(
    cumulative: ArtifactSnapshot,
) -> tuple[
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    Mapping[str, tuple[str, str, str, str]],
]:
    positions_raw = _list(cumulative.data.get("positions"), "cumulative.positions")
    if not positions_raw:
        raise ReplayValidationError("cumulative positions must not be empty")
    positions: list[Mapping[str, Any]] = []
    identified: list[Mapping[str, Any]] = []
    absences: list[Mapping[str, Any]] = []
    evidence_boundaries: dict[str, tuple[str, str, str, str]] = {}
    position_ids: set[str] = set()
    field_names = {
        "components": "component_identity",
        "apparatus": "apparatus",
        "ratings": "rating",
    }
    for raw_position in positions_raw:
        source_position = _mapping(raw_position, "cumulative.positions[]")
        position_id, section, document = _position_boundary(source_position)
        if position_id in position_ids:
            raise ReplayValidationError("duplicate cumulative evidence_position_id")
        position_ids.add(position_id)
        quantity = _require_fields(
            source_position.get("quantity"),
            f"{position_id}.quantity",
            {"value", "status"},
        )
        quantity_value = _number(quantity["value"], f"{position_id}.quantity.value")
        if quantity_value <= 0:
            raise ReplayValidationError("position quantity must be positive")
        field_entries: list[Mapping[str, Any]] = []
        absence_entries: list[Mapping[str, Any]] = []
        for source_field, output_field in field_names.items():
            field_value, raw_entries = _field_values(
                source_position,
                source_field,
                position_id,
            )
            for raw_entry in raw_entries:
                entry = _mapping(raw_entry, f"{position_id}.{source_field}[]")
                if "component_evidence_id" not in entry:
                    placeholder = _require_fields(
                        entry,
                        f"{position_id}.{source_field}.NOT_FOUND",
                        {"value", "status", "reason", "provenance"},
                    )
                    if field_value.get("resolution_status") != "NOT_FOUND":
                        raise ReplayValidationError(
                            "field absence parent resolution_status must be NOT_FOUND"
                        )
                    if placeholder["status"] != "NOT_FOUND":
                        raise ReplayValidationError(
                            "field absence status must be NOT_FOUND"
                        )
                    if placeholder["value"] is not None:
                        raise ReplayValidationError("field absence value must be null")
                    reason = _string(
                        placeholder["reason"],
                        f"{position_id}.{source_field}.absence.reason",
                    )
                    provenance = _project_provenance(
                        placeholder["provenance"],
                        f"{position_id}.{source_field}.absence.provenance",
                    )
                    if source_field != "components":
                        continue
                    absence = {
                        "position_id": position_id,
                        "section_id": section,
                        "document_id": document,
                        "status": "NOT_FOUND",
                        "reason": reason,
                        "provenance": provenance,
                    }
                    absence_entries.append(absence)
                    absences.append(absence)
                    continue
                evidence_id = _string(
                    entry["component_evidence_id"],
                    f"{position_id}.{source_field}.component_evidence_id",
                )
                projected_entry = {
                    "component_evidence_id": evidence_id,
                    "field": output_field,
                    "value": entry.get("value"),
                    "status": _string(
                        entry.get("status"),
                        f"{position_id}.{source_field}.status",
                    ),
                    "provenance": _project_provenance(
                        entry.get("provenance", {}),
                        f"{position_id}.{source_field}.provenance",
                    ),
                }
                field_entries.append(projected_entry)
                if source_field == "components":
                    if evidence_id in evidence_boundaries:
                        raise ReplayValidationError("duplicate component evidence ID")
                    label = _string(
                        entry.get("value"),
                        f"{position_id}.components.value",
                    )
                    evidence_boundaries[evidence_id] = (
                        position_id,
                        section,
                        document,
                        label,
                    )
                    identified.append(
                        {
                            "component_evidence_id": evidence_id,
                            "position_id": position_id,
                            "section_id": section,
                            "document_id": document,
                            "label": entry.get("value"),
                            "source_status": entry.get("status"),
                            "provenance": projected_entry["provenance"],
                        }
                    )
        positions.append(
            {
                "position_id": position_id,
                "existing_review_position_id": source_position.get(
                    "existing_review_position_id"
                ),
                "section_id": section,
                "document_id": document,
                "partition": section,
                "quantity": quantity_value,
                "quantity_status": quantity["status"],
                "component_field_evidence": field_entries,
                "component_absence_evidence": absence_entries,
            }
        )
    all_field_ids = {
        cast(str, entry["component_evidence_id"])
        for position in positions
        for entry in cast(list[Mapping[str, Any]], position["component_field_evidence"])
    }
    if not all_field_ids <= set(evidence_boundaries):
        raise ReplayValidationError("new or unbound component evidence ID")
    return (
        tuple(positions),
        tuple(identified),
        tuple(absences),
        evidence_boundaries,
    )


def _applicability_projection(
    applicability: ArtifactSnapshot,
    evidence_boundaries: Mapping[str, tuple[str, str, str, str]],
    policy_module: ModuleType,
    expected_classification_counts: Any,
) -> tuple[tuple[Mapping[str, Any], ...], Mapping[str, Mapping[str, Any]]]:
    expected = _exact_object(
        expected_classification_counts,
        "policy_binding.expected_classification_counts",
        CLASSIFICATIONS,
    )
    expected_counts = {
        key: _integer(value, f"expected_classification_counts.{key}", nonnegative=True)
        for key, value in expected.items()
    }
    actual_declared = _exact_object(
        applicability.data.get("classification_counts"),
        "applicability.classification_counts",
        CLASSIFICATIONS,
    )
    declared_counts = {
        key: _integer(value, f"classification_counts.{key}", nonnegative=True)
        for key, value in actual_declared.items()
    }
    records_raw = _list(applicability.data.get("records"), "applicability.records")
    if not records_raw and sum(expected_counts.values()) != 0:
        raise ReplayValidationError("field applicability records are empty")
    records: list[Mapping[str, Any]] = []
    records_by_id: dict[str, Mapping[str, Any]] = {}
    record_ids: set[str] = set()
    actual_counts: Counter[str] = Counter()
    for raw_record in records_raw:
        record = _require_fields(
            raw_record,
            "applicability.records[]",
            {
                "record_id",
                "component_evidence_id",
                "evidence_position_id",
                "section",
                "field",
                "applicability_classification",
                "remediation_route",
                "determination",
                "raw_designation",
                "raw_quantity",
                "raw_type_model",
                "raw_ratings",
                "value_applied",
                "approval_created",
                "not_an_approval",
            },
        )
        record_id = _string(record["record_id"], "applicability.record_id")
        if record_id in record_ids:
            raise ReplayValidationError("duplicate applicability record_id")
        record_ids.add(record_id)
        evidence_id = _string(
            record["component_evidence_id"],
            f"{record_id}.component_evidence_id",
        )
        if evidence_id not in evidence_boundaries:
            raise ReplayValidationError("applicability has new or missing evidence ID")
        position_id, section, _, policy_label = evidence_boundaries[evidence_id]
        if (
            record["evidence_position_id"] != position_id
            or str(record["section"]) != section
        ):
            raise ReplayValidationError(
                "applicability crosses position/section boundary"
            )
        classification = _string(
            record["applicability_classification"],
            f"{record_id}.applicability_classification",
        )
        if classification not in CLASSIFICATIONS:
            raise ReplayValidationError("unknown applicability classification")
        actual_counts[classification] += 1
        projected = {
            "record_id": record_id,
            "component_evidence_id": evidence_id,
            "evidence_position_id": position_id,
            "section": section,
            "field": record["field"],
            "applicability_classification": classification,
            "remediation_route": record["remediation_route"],
            "determination": record["determination"],
            "raw_designation": record["raw_designation"],
            "raw_quantity": record["raw_quantity"],
            "raw_type_model": record["raw_type_model"],
            "raw_ratings": record["raw_ratings"],
            "value_applied": record["value_applied"],
            "approval_created": record["approval_created"],
            "not_an_approval": record["not_an_approval"],
        }
        records.append(projected)
        records_by_id[record_id] = projected
        _validate_record_policy(policy_module, projected, policy_label)
    computed_counts = {key: actual_counts[key] for key in CLASSIFICATIONS}
    if computed_counts != declared_counts or computed_counts != expected_counts:
        raise ReplayValidationError("applicability classification counts mismatch")
    if applicability.data.get("classification_total") != len(records):
        raise ReplayValidationError("applicability classification_total mismatch")
    return tuple(records), records_by_id


def _provenance_for_policy(module: ModuleType, raw_text: str) -> list[Any]:
    return [
        module.Provenance(
            source_file="frozen_applicability_audit",
            source_type="frozen_json",
            locator="bounded_record",
            raw_text=raw_text,
            confidence=1.0,
            reason="frozen applicability conformance only",
        )
    ]


def _bounded_normalization_text(policy_label: str, raw_text: str) -> str:
    normalized_label = policy_label.casefold()
    rt_matches = re.findall(r"(?:РТ|RT)\s*[- ]?\s*007S", raw_text, re.IGNORECASE)
    tst_matches = re.findall(r"TST\s*[- ]?\s*05", raw_text, re.IGNORECASE)
    if "регулятор" in normalized_label:
        if len(rt_matches) != 1:
            raise ReplayValidationError(
                "regulator normalization token is missing or ambiguous"
            )
        return f"{policy_label} {rt_matches[0]}"
    if "датчик температуры" in normalized_label:
        if len(tst_matches) != 1:
            raise ReplayValidationError(
                "sensor normalization token is missing or ambiguous"
            )
        return f"{policy_label} {tst_matches[0]}"
    raise ReplayValidationError("unknown normalization component identity")


def _validate_record_policy(
    module: ModuleType,
    record: Mapping[str, Any],
    policy_label: str,
) -> None:
    classification = record["applicability_classification"]
    relevant = {
        "FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT",
        "FIELD_SEMANTICS_MISMATCH",
        "EXPLICIT_RAW_VALUE_NOT_NORMALIZED",
    }
    if classification not in relevant:
        return
    raw_label = _string(record["raw_designation"], "applicability.raw_designation")
    model_value = record["raw_type_model"]
    model = (
        None if model_value in (None, "") else _string(model_value, "raw_type_model")
    )
    ratings = record["raw_ratings"]
    rating: str | None = None
    if isinstance(ratings, str) and ratings.strip():
        rating = ratings
    raw_text = " ".join(
        value
        for value in (
            raw_label,
            model or "",
            rating or "",
        )
        if value
    )
    component = module.ComponentCandidate(
        label=policy_label,
        quantity=record["raw_quantity"],
        unit=None,
        model=model,
        brand=None,
        rating=rating,
        note=None,
        provenance=_provenance_for_policy(module, raw_text),
        confidence=1.0,
    )
    if classification == "EXPLICIT_RAW_VALUE_NOT_NORMALIZED":
        if (
            record["value_applied"] is not False
            or record["approval_created"] is not False
            or record["not_an_approval"] is not True
        ):
            raise ReplayValidationError(
                "normalization candidate was applied or approved"
            )
        bounded_raw_text = _bounded_normalization_text(policy_label, raw_text)
        normalized = module.normalize_explicit_component_model_type(
            policy_label,
            bounded_raw_text,
            model,
            rating,
        )
        if normalized[2] != "MODEL_OR_TYPE_SEMANTICS" or normalized[0] not in {
            "РТ 007S",
            "TST05",
        }:
            raise ReplayValidationError(
                "normalization candidate is not recognized by policy owner"
            )
        return
    computed = module.classify_component_field_applicability(
        component,
        "rating_guess",
    )
    expected_status = (
        "NOT_APPLICABLE_WITH_REASON"
        if classification == "FIELD_NOT_APPLICABLE_SUPPORTED_BY_CONTRACT"
        else "MODEL_OR_TYPE_SEMANTICS"
    )
    if computed is None or computed.get("status") != expected_status:
        raise ReplayValidationError("frozen applicability is not policy-conformant")


def _quantity_fingerprint(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "record_id": record["record_id"],
        "component_evidence_id": record["component_evidence_id"],
        "evidence_position_id": record["evidence_position_id"],
        "section": record["section"],
        "field": record["field"],
        "applicability_classification": record["applicability_classification"],
        "remediation_route": record["remediation_route"],
    }


def _install_fingerprint(value: Any) -> Mapping[str, Any]:
    item = _require_fields(
        value,
        "additional_blockers_outside_82[]",
        {
            "blocker_id",
            "meaning",
            "included_in_field_count",
            "schema_or_validator_changed",
            "install_type_selected",
            "next_boundary",
        },
    )
    return {
        key: item[key]
        for key in (
            "blocker_id",
            "meaning",
            "included_in_field_count",
            "schema_or_validator_changed",
            "install_type_selected",
            "next_boundary",
        )
    }


def _sorted_canonical(values: Sequence[Mapping[str, Any]]) -> list[bytes]:
    return sorted(_canonical_bytes(value) for value in values)


def _validate_blockers(
    manifest_value: Any,
    applicability: ArtifactSnapshot,
    records: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    requirements = _exact_object(
        manifest_value,
        "blocker_requirements",
        {
            "expected_quantity_blocker_count",
            "expected_install_type_blocker_count",
            "quantity_blocker_fingerprints",
            "install_type_blocker_fingerprints",
            "require_exact_preservation",
        },
    )
    if requirements["require_exact_preservation"] is not True:
        raise ReplayValidationError("exact blocker preservation is required")
    quantity = [
        _quantity_fingerprint(record)
        for record in records
        if record["applicability_classification"] in QUANTITY_BLOCKER_CLASSES
    ]
    install = [
        _install_fingerprint(value)
        for value in _list(
            applicability.data.get("additional_blockers_outside_82"),
            "additional_blockers_outside_82",
        )
    ]
    expected_quantity_count = _integer(
        requirements["expected_quantity_blocker_count"],
        "expected_quantity_blocker_count",
        nonnegative=True,
    )
    expected_install_count = _integer(
        requirements["expected_install_type_blocker_count"],
        "expected_install_type_blocker_count",
        nonnegative=True,
    )
    if (
        len(quantity) != expected_quantity_count
        or len(install) != expected_install_count
    ):
        raise ReplayValidationError("blocker count mismatch")
    expected_quantity = [
        _mapping(item, "quantity_blocker_fingerprints[]")
        for item in _list(
            requirements["quantity_blocker_fingerprints"],
            "quantity_blocker_fingerprints",
        )
    ]
    expected_install = [
        _mapping(item, "install_type_blocker_fingerprints[]")
        for item in _list(
            requirements["install_type_blocker_fingerprints"],
            "install_type_blocker_fingerprints",
        )
    ]
    if _sorted_canonical(quantity) != _sorted_canonical(
        expected_quantity
    ) or _sorted_canonical(install) != _sorted_canonical(expected_install):
        raise ReplayValidationError("exact blocker fingerprint mismatch")
    if expected_quantity_count and not quantity:
        raise ReplayValidationError("quantity blockers unexpectedly empty")
    if expected_install_count and not install:
        raise ReplayValidationError("install-type blockers unexpectedly empty")
    return tuple(
        [{"blocker_kind": "QUANTITY", **item} for item in quantity]
        + [{"blocker_kind": "INSTALL_TYPE", **item} for item in install]
    )


def _control_number(controls: Mapping[str, Any], name: str) -> int:
    if name not in controls:
        raise ReplayValidationError(f"cumulative controls missing {name}")
    return _integer(controls[name], f"cumulative.controls.{name}", nonnegative=True)


def _validate_rt007s_authority_proof(
    expectation_value: Any,
    cumulative: ArtifactSnapshot,
    authority_batches: Sequence[ArtifactSnapshot],
) -> tuple[Mapping[str, Any], Mapping[str, int]]:
    expectation = _exact_object(
        expectation_value,
        "expected_rt007s_authority_proof",
        {
            "source_schema",
            "batch_id",
            "artifact_sha256",
            "decision_id",
            "decision_code",
            "decision_type",
            "technical_field",
            "authority",
            "accepted_status",
            "rule_payload",
        },
    )
    payload_expectation = _exact_object(
        expectation["rule_payload"],
        "expected_rt007s_authority_proof.rule_payload",
        {
            "rule_id",
            "target_designation",
            "forbidden_transfer_designation",
            "sections",
            "commercial_item_name",
            "bridge_commercial_item_name",
            "future_price_lookup_name",
            "commercial_quantity_per_cabinet",
            "supply_form",
            "bundle_members",
            "bridge_status",
            "application_status",
            "anti_double_counting",
            "raw_source_evidence_preserved",
            "technical_source_rows",
            "technical_model_equivalence",
            "commercial_item_per_cabinet",
            "technical_approval_created",
            "pricing_executed",
            "confirmed_composition_created",
        },
    )
    if (
        expectation["source_schema"] != "human_decisions_batch.v0.19"
        or expectation["batch_id"] != "019"
        or payload_expectation["target_designation"] != "ШУ-Т1"
        or payload_expectation["forbidden_transfer_designation"] != "ШУ-Т2"
    ):
        raise ReplayValidationError(
            "RT007S authority proof has an invalid bounded target"
        )
    batch = next(
        (
            item
            for item in authority_batches
            if item.descriptor["schema_version"] == expectation["source_schema"]
        ),
        None,
    )
    if batch is None:
        raise ReplayValidationError("RT007S authority proof source batch is missing")
    if (
        batch.data.get("batch_id") != expectation["batch_id"]
        or batch.descriptor["sha256"] != expectation["artifact_sha256"]
    ):
        raise ReplayValidationError(
            "RT007S authority proof source fingerprint mismatch"
        )
    matching_decisions = [
        _mapping(item, "human_decisions_batch.v0.19.technical_field_decisions[]")
        for item in _list(
            batch.data.get("technical_field_decisions"),
            "human_decisions_batch.v0.19.technical_field_decisions",
        )
        if isinstance(item, Mapping)
        and item.get("decision_id") == expectation["decision_id"]
    ]
    if len(matching_decisions) != 1:
        raise ReplayValidationError(
            "RT007S authority decision is missing or duplicated"
        )
    decision = matching_decisions[0]
    decision_fingerprint = {
        "decision_id": decision.get("decision_id"),
        "decision_code": decision.get("decision_code"),
        "decision_type": decision.get("decision_type"),
        "technical_field": decision.get("technical_field"),
        "authority": decision.get("authority"),
        "accepted_status": decision.get("accepted_status"),
    }
    expected_decision_fingerprint = {
        key: expectation[key]
        for key in (
            "decision_id",
            "decision_code",
            "decision_type",
            "technical_field",
            "authority",
            "accepted_status",
        )
    }
    if not _safe_equal(decision_fingerprint, expected_decision_fingerprint):
        raise ReplayValidationError("RT007S authority decision fingerprint mismatch")

    accepted_rows = [
        _require_fields(
            item,
            "H19-3.accepted_value[]",
            {
                "section_id",
                "commercial_item_name",
                "future_price_lookup_name",
                "commercial_quantity_per_cabinet",
                "supply_form",
                "separate_TST05_pricing",
                "separate_TST05_procurement",
                "application_status",
            },
        )
        for item in _list(decision.get("accepted_value"), "H19-3.accepted_value")
    ]
    provenance = _mapping(
        decision.get("source_position_provenance"),
        "H19-3.source_position_provenance",
    )
    approval_boundary = _require_fields(
        decision.get("approval_boundary"),
        "H19-3.approval_boundary",
        {
            "technical_source_rows",
            "technical_model_equivalence",
            "commercial_item_per_cabinet",
            "application_status",
        },
    )
    if (
        approval_boundary["technical_source_rows"]
        != payload_expectation["technical_source_rows"]
        or approval_boundary["technical_model_equivalence"]
        != payload_expectation["technical_model_equivalence"]
        or approval_boundary["commercial_item_per_cabinet"]
        != payload_expectation["commercial_item_per_cabinet"]
        or approval_boundary["application_status"]
        != payload_expectation["application_status"]
    ):
        raise ReplayValidationError("RT007S approval boundary payload mismatch")
    bridge_rows = [
        _require_fields(
            item,
            "H19-3.frozen_audit_bridge[]",
            {
                "section",
                "rule_id",
                "commercial_item_name",
                "future_price_lookup_name",
                "commercial_quantity_per_cabinet",
                "bundle_members",
                "status",
                "application_status",
                "anti_double_counting",
                "technical_approval_created",
                "pricing_executed",
                "confirmed_composition_created",
            },
        )
        for item in _list(
            provenance.get("frozen_audit_bridge"),
            "H19-3.frozen_audit_bridge",
        )
    ]
    expected_sections = [
        _string(item, "expected_rt007s_authority_proof.rule_payload.sections[]")
        for item in _list(payload_expectation["sections"], "RT007S proof sections")
    ]
    if len(expected_sections) != 4 or len(set(expected_sections)) != 4:
        raise ReplayValidationError(
            "RT007S authority proof must bind exactly four sections"
        )
    if len(accepted_rows) != 4 or len(bridge_rows) != 4:
        raise ReplayValidationError(
            "RT007S authority proof must contain four RT-820 sets"
        )
    accepted_sections = sorted(
        _string(row["section_id"], "H19-3.section_id") for row in accepted_rows
    )
    bridge_sections = sorted(
        _string(row["section"], "H19-3.bridge.section") for row in bridge_rows
    )
    if accepted_sections != sorted(expected_sections) or bridge_sections != sorted(
        expected_sections
    ):
        raise ReplayValidationError(
            "RT007S authority proof section fingerprint mismatch"
        )

    bundle_members = _list(
        payload_expectation["bundle_members"],
        "RT007S bundle_members",
    )
    standalone = {
        "commercial": sum(
            "РТ 007S" in str(row["commercial_item_name"]) for row in accepted_rows
        ),
        "pricing": sum(
            "РТ 007S" in str(row["future_price_lookup_name"]) for row in accepted_rows
        ),
        "procurement": sum(
            "РТ 007S" in str(row.get("procurement_item_name", ""))
            for row in accepted_rows
        ),
    }
    if any(standalone.values()):
        raise ReplayValidationError(
            "standalone RT007S downstream representation detected"
        )
    for row in accepted_rows:
        if (
            row["commercial_item_name"] != payload_expectation["commercial_item_name"]
            or row["future_price_lookup_name"]
            != payload_expectation["future_price_lookup_name"]
            or row["commercial_quantity_per_cabinet"]
            != payload_expectation["commercial_quantity_per_cabinet"]
            or row["supply_form"] != payload_expectation["supply_form"]
            or row["separate_TST05_pricing"] is not False
            or row["separate_TST05_procurement"] is not False
            or row["application_status"] != payload_expectation["application_status"]
        ):
            raise ReplayValidationError("RT007S accepted rule payload mismatch")
    for row in bridge_rows:
        if (
            row["rule_id"] != payload_expectation["rule_id"]
            or row["commercial_item_name"]
            != payload_expectation["bridge_commercial_item_name"]
            or row["future_price_lookup_name"]
            != payload_expectation["future_price_lookup_name"]
            or row["commercial_quantity_per_cabinet"]
            != payload_expectation["commercial_quantity_per_cabinet"]
            or not _safe_equal(row["bundle_members"], bundle_members)
            or row["status"] != payload_expectation["bridge_status"]
            or row["application_status"] != payload_expectation["application_status"]
            or row["anti_double_counting"]
            is not payload_expectation["anti_double_counting"]
            or row["technical_approval_created"]
            is not payload_expectation["technical_approval_created"]
            or row["pricing_executed"] is not payload_expectation["pricing_executed"]
            or row["confirmed_composition_created"]
            is not payload_expectation["confirmed_composition_created"]
        ):
            raise ReplayValidationError("RT007S frozen bridge rule payload mismatch")

    positions = [
        _mapping(item, "cumulative.positions[]")
        for item in _list(cumulative.data.get("positions"), "cumulative.positions")
    ]
    target_sections = set(expected_sections)
    for position in positions:
        identity = _mapping(position.get("canonical_identity"), "canonical_identity")
        if (
            identity.get("canonical_designation")
            == payload_expectation["forbidden_transfer_designation"]
            and identity.get("section_id") in target_sections
        ):
            raise ReplayValidationError("RT007S rule transferred to ШУ-Т2")
    target_positions: list[Mapping[str, Any]] = []
    for section in expected_sections:
        matches = [
            position
            for position in positions
            if _mapping(position.get("canonical_identity"), "canonical_identity").get(
                "section_id"
            )
            == section
            and _mapping(position.get("canonical_identity"), "canonical_identity").get(
                "canonical_designation"
            )
            == payload_expectation["target_designation"]
        ]
        if len(matches) != 1:
            raise ReplayValidationError(
                "RT007S proof must bind one ШУ-Т1 position per approved section"
            )
        target_positions.extend(matches)
    for position in target_positions:
        technical_fields = _mapping(
            position.get("technical_fields"),
            "technical_fields",
        )
        scheme = _mapping(
            technical_fields.get("scheme"),
            "technical_fields.scheme",
        )
        evidence_values = [
            _mapping(item, "technical_fields.scheme.evidence_values[]")
            for item in _list(
                scheme.get("evidence_values"),
                "technical_fields.scheme.evidence_values",
            )
        ]
        raw_evidence = any(
            "РТ 007S" in str(item.get("raw_text_excerpt", ""))
            for item in evidence_values
        )
        if (
            not raw_evidence
            or scheme.get("source_reference_preserved")
            is not payload_expectation["raw_source_evidence_preserved"]
        ):
            raise ReplayValidationError(
                "RT007S raw source evidence is not preserved for ШУ-Т1"
            )
    proof = {
        "source_schema": batch.descriptor["schema_version"],
        "batch_id": batch.data["batch_id"],
        "artifact_sha256": batch.descriptor["sha256"],
        **decision_fingerprint,
        "rule_payload": {
            **payload_expectation,
            "sections": expected_sections,
            "bundle_members": bundle_members,
        },
    }
    if not _safe_equal(proof, expectation):
        raise ReplayValidationError("RT007S authority proof fingerprint mismatch")
    return proof, standalone


def _validate_hard_controls(
    manifest: Mapping[str, Any],
    cumulative: ArtifactSnapshot,
    authority_batches: Sequence[ArtifactSnapshot],
    applicability_records: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    controls = _mapping(cumulative.data.get("controls"), "cumulative.controls")
    supply_expectations = _exact_object(
        manifest["supply_boundary"],
        "supply_boundary",
        {
            "expected_outside_cabinet_exclusions",
            "expected_new_evidence_ids_for_exclusions",
            "expected_external_rows_included",
            "expected_standalone_tst05",
            "expected_standalone_rt007s",
            "expected_rt007s_authority_proof",
        },
    )
    tst_expected = _exact_object(
        supply_expectations["expected_standalone_tst05"],
        "expected_standalone_tst05",
        {"commercial", "pricing", "procurement"},
    )
    rt_expected = _exact_object(
        supply_expectations["expected_standalone_rt007s"],
        "expected_standalone_rt007s",
        {"commercial", "pricing", "procurement"},
    )
    external_rows = _control_number(
        controls,
        "external_rows_included_in_composition_price_procurement_production",
    )
    actual_tst = {
        "commercial": _control_number(controls, "separate_tst05_commercial_rows"),
        "pricing": _control_number(controls, "separate_tst05_pricing_rows"),
        "procurement": _control_number(controls, "separate_tst05_procurement_rows"),
    }
    rt007s_proof, actual_rt = _validate_rt007s_authority_proof(
        supply_expectations["expected_rt007s_authority_proof"],
        cumulative,
        authority_batches,
    )
    supply = {
        "outside_cabinet_exclusions": _control_number(
            controls,
            "external_shu_t1_source_rows",
        ),
        "new_evidence_ids_for_exclusions": _control_number(
            controls,
            "new_evidence_ids_for_external_rows",
        ),
        "external_rows_included": external_rows,
        "standalone_tst05": actual_tst,
        "standalone_rt007s": actual_rt,
        "rt007s_authority_proof": rt007s_proof,
    }
    expected_supply = {
        "outside_cabinet_exclusions": _integer(
            supply_expectations["expected_outside_cabinet_exclusions"],
            "expected_outside_cabinet_exclusions",
            nonnegative=True,
        ),
        "new_evidence_ids_for_exclusions": _integer(
            supply_expectations["expected_new_evidence_ids_for_exclusions"],
            "expected_new_evidence_ids_for_exclusions",
            nonnegative=True,
        ),
        "external_rows_included": _integer(
            supply_expectations["expected_external_rows_included"],
            "expected_external_rows_included",
            nonnegative=True,
        ),
        "standalone_tst05": {
            key: _integer(value, f"expected_standalone_tst05.{key}", nonnegative=True)
            for key, value in tst_expected.items()
        },
        "standalone_rt007s": {
            key: _integer(value, f"expected_standalone_rt007s.{key}", nonnegative=True)
            for key, value in rt_expected.items()
        },
    }
    for key in (
        "outside_cabinet_exclusions",
        "new_evidence_ids_for_exclusions",
        "external_rows_included",
        "standalone_tst05",
        "standalone_rt007s",
    ):
        if not _safe_equal(supply[key], expected_supply[key]):
            raise ReplayValidationError(f"supply-boundary invariant mismatch: {key}")
    complete_expectations = _exact_object(
        manifest["complete_set_rules"],
        "complete_set_rules",
        {
            "expected_rt_820_complete_sets",
            "protected_component_records",
            "forbid_five_to_one",
        },
    )
    if complete_expectations["forbid_five_to_one"] is not True:
        raise ReplayValidationError("5-to-1 protection must be enabled")
    expected_protected = [
        _exact_object(
            item,
            "protected_component_records[]",
            {
                "component_evidence_id",
                "evidence_position_id",
                "raw_quantity",
            },
        )
        for item in _list(
            complete_expectations["protected_component_records"],
            "protected_component_records",
        )
    ]
    by_evidence: dict[str, Mapping[str, Any]] = {}
    for record in applicability_records:
        evidence_id = cast(str, record["component_evidence_id"])
        existing = by_evidence.get(evidence_id)
        if existing is None:
            by_evidence[evidence_id] = record
        elif not _safe_equal(existing["raw_quantity"], record["raw_quantity"]):
            raise ReplayValidationError("conflicting raw quantity for evidence ID")
    actual_protected: list[Mapping[str, Any]] = []
    for expected_record in expected_protected:
        evidence_id = _string(
            expected_record["component_evidence_id"],
            "protected component evidence ID",
        )
        protected_record = by_evidence.get(evidence_id)
        if protected_record is None:
            raise ReplayValidationError("protected component evidence ID is missing")
        actual = {
            "component_evidence_id": evidence_id,
            "evidence_position_id": protected_record["evidence_position_id"],
            "raw_quantity": protected_record["raw_quantity"],
        }
        if not _safe_equal(actual, expected_record):
            raise ReplayValidationError(
                "protected component changed or 5-to-1 detected"
            )
        actual_protected.append(actual)
    complete = {
        "rt_820_complete_sets": _control_number(
            controls,
            "rt_820_complete_set_records",
        ),
        "protected_component_records": actual_protected,
        "five_to_one_applied": False,
    }
    if complete["rt_820_complete_sets"] != _integer(
        complete_expectations["expected_rt_820_complete_sets"],
        "expected_rt_820_complete_sets",
        nonnegative=True,
    ):
        raise ReplayValidationError("RT-820 complete-set count mismatch")
    if complete["rt_820_complete_sets"] and not actual_protected:
        raise ReplayValidationError("complete-set controls unexpectedly empty")
    return supply, complete


def _compute_counts(
    positions: Sequence[Mapping[str, Any]],
    identified: Sequence[Mapping[str, Any]],
    absences: Sequence[Mapping[str, Any]],
) -> dict[str, int | float]:
    evidence_ids = [
        _string(record["component_evidence_id"], "identified.component_evidence_id")
        for record in identified
    ]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ReplayValidationError("duplicate identified component evidence ID")
    field_entries = [
        entry
        for position in positions
        for entry in _list(
            position["component_field_evidence"],
            "positions[].component_field_evidence",
        )
    ]
    referenced = {
        _string(entry["component_evidence_id"], "field entry evidence ID")
        for entry in field_entries
    }
    if not referenced <= set(evidence_ids):
        raise ReplayValidationError("new component evidence ID in field entries")
    return {
        "canonical_position_count": len(positions),
        "component_bearing_position_count": sum(
            bool(position["component_field_evidence"]) for position in positions
        ),
        "component_field_evidence_entry_count": len(field_entries),
        "component_absence_evidence_entry_count": len(absences),
        "identified_component_evidence_record_count": len(identified),
        "unique_component_evidence_id_count": len(set(evidence_ids)),
        "position_quantity_total": sum(
            cast(int | float, position["quantity"]) for position in positions
        ),
    }


def _validate_expected_counts(
    expected_value: Any,
    actual: Mapping[str, int | float],
    label: str,
) -> None:
    expected = _exact_object(expected_value, label, COUNT_FIELDS)
    for key in COUNT_FIELDS:
        value = _number(expected[key], f"{label}.{key}", nonnegative=True)
        if value != actual[key]:
            raise ReplayValidationError(f"{label}.{key} mismatch")


def _quantity_invariants(
    expected_value: Any,
    positions: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    partition_totals: dict[str, int | float] = {}
    for position in positions:
        position_partition = cast(str, position["partition"])
        partition_totals[position_partition] = partition_totals.get(
            position_partition, 0
        ) + cast(int | float, position["quantity"])
    results: list[Mapping[str, Any]] = []
    for raw in _list(expected_value, "expected_quantity_invariants"):
        item = _exact_object(
            raw,
            "expected_quantity_invariants[]",
            {"type", "partition", "expected_total"},
        )
        kind = _string(item["type"], "quantity invariant type")
        if kind not in INVARIANT_TYPES:
            raise ReplayValidationError("unknown quantity invariant type")
        expected = _number(item["expected_total"], "expected_total", nonnegative=True)
        partition: str | None
        if kind == "POSITION_QUANTITY_TOTAL_EQUALS":
            if item["partition"] is not None:
                raise ReplayValidationError("total invariant partition must be null")
            actual = sum(partition_totals.values())
            partition = None
        else:
            partition = _string(item["partition"], "partition")
            if partition not in partition_totals:
                raise ReplayValidationError("unknown partition in invariant")
            actual = partition_totals[partition]
        if actual != expected:
            raise ReplayValidationError("partition/quantity invariant mismatch")
        results.append(
            {
                "type": kind,
                "partition": partition,
                "expected_total": expected,
                "actual_total": actual,
                "status": "PASS",
            }
        )
    return tuple(results)


def _validate_safety(
    manifest: Mapping[str, Any], artifacts: Sequence[ArtifactSnapshot]
) -> None:
    safety = _exact_object(
        manifest["safety"],
        "safety",
        {
            "confirmed_composition_authorized",
            "pricing_authorized",
            "commercial_authorized",
            "production_authorized",
        },
    )
    if any(value is not False for value in safety.values()):
        raise ReplayValidationError("authorization=true is forbidden")
    for artifact in artifacts:
        for container_name in ("safety_flags", "controls"):
            container = artifact.data.get(container_name)
            if not isinstance(container, Mapping):
                continue
            for key in DOWNSTREAM_FLAG_NAMES:
                value = container.get(key)
                if value not in (None, False, 0):
                    raise ReplayValidationError(
                        f"frozen input has forbidden downstream flag: {key}"
                    )


def _source_output(artifact: ArtifactSnapshot) -> Mapping[str, Any]:
    return {
        "role": artifact.descriptor["role"],
        "file_name": artifact.path.name,
        "schema_version": artifact.descriptor["schema_version"],
        "sha256": artifact.descriptor["sha256"],
        "case_id": artifact.descriptor["case_id"],
        "project_id": artifact.descriptor["project_id"],
        "artifact_status": artifact.descriptor["artifact_status"],
    }


def _reject_output_paths_or_authorization(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key in FORBIDDEN_OUTPUT_KEYS:
                raise ReplayValidationError(f"{path}.{key} is forbidden")
            lowered = key.casefold()
            if child is True and (
                "authorized" in lowered
                or lowered.endswith("_authorization")
                or lowered in {"approval_created", "value_applied"}
            ):
                raise ReplayValidationError(f"{path}.{key}=true is forbidden")
            _reject_output_paths_or_authorization(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_output_paths_or_authorization(child, f"{path}[{index}]")
    elif isinstance(value, str) and (
        Path(value).is_absolute() or WINDOWS_ABSOLUTE_RE.match(value)
    ):
        raise ReplayValidationError(f"{path} contains an absolute path")


def load_intake_context(intake_manifest: Path) -> IntakeContext:
    manifest_path = intake_manifest.resolve(strict=False)
    manifest_content, manifest_value = _read_json(manifest_path, "intake manifest")
    manifest = _exact_object(manifest_value, "intake manifest", INTAKE_FIELDS)
    if manifest["schema_version"] != INTAKE_SCHEMA:
        raise ReplayValidationError("unknown intake schema/version")
    _string(manifest["case_id"], "intake case_id")
    project_id = _string(manifest["project_id"], "intake project_id")
    artifacts = tuple(
        _validate_descriptor(item, project_id)
        for item in _list(manifest["source_artifacts"], "source_artifacts")
    )
    normalized_paths = [str(item.path).casefold() for item in artifacts]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise ReplayValidationError("duplicate direct input path")
    cumulative_items = [
        item for item in artifacts if item.descriptor["role"] == "cumulative_review"
    ]
    applicability_items = [
        item for item in artifacts if item.descriptor["role"] == "field_applicability"
    ]
    batches = [
        item for item in artifacts if item.descriptor["role"] == "authority_batch"
    ]
    if len(cumulative_items) != 1 or len(applicability_items) != 1:
        raise ReplayValidationError(
            "exactly one cumulative and one applicability input are required"
        )
    authority_lineage = _validate_authority_chain(
        manifest["authority_lineage"],
        batches,
    )
    policy_module = _load_policy_owner(manifest["policy_binding"])
    positions, identified, absences, boundaries = _project_cumulative(
        cumulative_items[0]
    )
    policy_binding = _mapping(manifest["policy_binding"], "policy_binding")
    applicability_records, _ = _applicability_projection(
        applicability_items[0],
        boundaries,
        policy_module,
        policy_binding["expected_classification_counts"],
    )
    blockers = _validate_blockers(
        manifest["blocker_requirements"],
        applicability_items[0],
        applicability_records,
    )
    supply, complete = _validate_hard_controls(
        manifest,
        cumulative_items[0],
        batches,
        applicability_records,
    )
    counts = _compute_counts(positions, identified, absences)
    _validate_expected_counts(manifest["expected_counts"], counts, "expected_counts")
    invariants = _quantity_invariants(
        manifest["expected_quantity_invariants"],
        positions,
    )
    required = {
        _string(item, "required_invariants[]")
        for item in _list(manifest["required_invariants"], "required_invariants")
    }
    if required != REQUIRED_INVARIANTS:
        raise ReplayValidationError("required invariant registry mismatch")
    _validate_safety(manifest, artifacts)
    output_contract = _exact_object(
        manifest["output_contract"],
        "output_contract",
        {"schema_version", "artifact_status", "authorization"},
    )
    if (
        output_contract["schema_version"] != BUNDLE_SCHEMA
        or output_contract["artifact_status"] != BUNDLE_STATUS
        or output_contract["authorization"] is not False
    ):
        raise ReplayValidationError("output contract mismatch or authorization=true")
    projection = DirectProjection(
        positions,
        identified,
        applicability_records,
        absences,
        blockers,
        supply,
        complete,
        authority_lineage,
        counts,
        invariants,
    )
    return IntakeContext(
        manifest_path,
        manifest_content,
        manifest,
        artifacts,
        cumulative_items[0],
        applicability_items[0],
        tuple(batches),
        projection,
    )


def validate_output_location(context: IntakeContext, path: Path) -> Path:
    resolved = path.resolve(strict=False)
    for artifact in context.artifacts:
        case_dir = artifact.case_dir.resolve()
        if resolved == case_dir or case_dir in resolved.parents:
            raise ReplayValidationError("output path is inside an input frozen case")
    return resolved


def expected_bundle(context: IntakeContext) -> Mapping[str, Any]:
    manifest = context.manifest
    policy = _mapping(manifest["policy_binding"], "policy_binding")
    return {
        "schema_version": BUNDLE_SCHEMA,
        "bundle_id": f"{manifest['case_id']}:component-replay-readiness:v0.1",
        "artifact_status": BUNDLE_STATUS,
        "project_id": manifest["project_id"],
        "source_artifacts": [_source_output(item) for item in context.artifacts],
        "authority_lineage": context.projection.authority_lineage,
        "policy_conformance": {
            "source_commit": policy["source_commit"],
            "owner_path": policy["owner_path"],
            "owner_sha256": policy["owner_sha256"],
            "function_names": policy["function_names"],
            "required_types": policy["required_types"],
            "classification_counts": policy["expected_classification_counts"],
            "conformance_status": "PASS",
            "frozen_values_replaced": False,
        },
        "counts": context.projection.counts,
        "quantity_invariants": list(context.projection.quantity_invariants),
        "positions": list(context.projection.positions),
        "identified_component_evidence_records": list(
            context.projection.identified_records
        ),
        "field_applicability_records": list(context.projection.applicability_records),
        "component_absence_evidence": list(context.projection.absence_records),
        "blockers": list(context.projection.blockers),
        "supply_boundary": context.projection.supply_boundary,
        "complete_set_controls": context.projection.complete_set_controls,
        "safety": {
            **_mapping(manifest["safety"], "safety"),
            "replay_only": True,
            "not_confirmed": True,
        },
        "next_required_human_actions": [
            "Review preliminary replay evidence and preserved blockers",
            "Provide separate approval before any confirmed or downstream action",
        ],
    }


def _validate_bundle(context: IntakeContext, bundle: Mapping[str, Any]) -> None:
    _exact_object(bundle, "bundle", ROOT_FIELDS)
    _reject_output_paths_or_authorization(bundle)
    expected = expected_bundle(context)
    if not _safe_equal(bundle, expected):
        for key in ROOT_FIELDS:
            if not _safe_equal(bundle.get(key), expected.get(key)):
                raise ReplayValidationError(f"bundle {key} mismatch")
        raise ReplayValidationError("bundle mismatch")
    output_counts = _compute_counts(
        cast(list[Mapping[str, Any]], bundle["positions"]),
        cast(
            list[Mapping[str, Any]],
            bundle["identified_component_evidence_records"],
        ),
        cast(list[Mapping[str, Any]], bundle["component_absence_evidence"]),
    )
    if output_counts != context.projection.counts:
        raise ReplayValidationError("validator output counts mismatch")
    _validate_expected_counts(bundle["counts"], output_counts, "bundle.counts")


def validate_component_replay_readiness_bundle(
    intake_manifest: Path,
    bundle_json: Path,
) -> ValidationResult:
    result = ValidationResult(intake_manifest, bundle_json)
    try:
        context = load_intake_context(intake_manifest)
        validate_output_location(context, bundle_json)
        _, bundle = _read_json(bundle_json, "readiness bundle")
        _validate_bundle(context, bundle)
        result.status = "PASS"
    except (ReplayValidationError, OSError) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a direct-input component replay readiness bundle."
    )
    parser.add_argument("--intake-manifest", required=True, type=Path)
    parser.add_argument("--bundle-json", required=True, type=Path)
    return parser.parse_args(argv)


def format_report(result: ValidationResult) -> str:
    lines = [
        "COMPONENT_REPLAY_READINESS_VALIDATION_REPORT_START",
        f"status: {result.status}",
    ]
    lines.extend(f"red_flag: {item}" for item in result.red_flags)
    lines.append("COMPONENT_REPLAY_READINESS_VALIDATION_REPORT_END")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_component_replay_readiness_bundle(
        args.intake_manifest,
        args.bundle_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
