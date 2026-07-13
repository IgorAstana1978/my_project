"""Validate a read-only bridge envelope for a confirmed composition artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from validate_confirmed_composition_artifact import (
    validate_confirmed_composition_artifact,
)

REPORT_START = "CONFIRMED_COMPOSITION_BRIDGE_ENVELOPE_VALIDATION_REPORT_START"
REPORT_END = "CONFIRMED_COMPOSITION_BRIDGE_ENVELOPE_VALIDATION_REPORT_END"
VALIDATOR_NAME = "confirmed composition bridge envelope validator"
MODE = "read-only"
HUMAN_APPROVAL = (
    "Igor approval is still required before price, quote generation, client sending, "
    "procurement or production"
)

SCHEMA_VERSION = "confirmed_composition_bridge_envelope.v0.1"
CONFIRMED_SCHEMA_VERSION = "confirmed_composition_artifact.v0.1"
APPROVAL_SCOPE = "transfer_confirmed_composition_for_calculator_input_draft_only"
SUPPLY_BOUNDARY_STATUS = "approved_by_igor"
SAFETY_STATUS = "confirmed_composition_bridge_only"

ROOT_FIELDS = (
    "schema_version",
    "case",
    "confirmed_composition",
    "supply_boundary",
    "approval",
    "safety",
)
CASE_FIELDS = ("case_id", "customer_label", "object_name")
CONFIRMED_COMPOSITION_FIELDS = ("schema_version", "artifact_sha256")
SUPPLY_BOUNDARY_FIELDS = ("status", "description", "approved_by_igor")
APPROVAL_FIELDS = (
    "approval_record_id",
    "approved_by",
    "approved_at",
    "approval_channel",
    "scope",
)
SAFETY_FIELDS = (
    "status",
    "transfer_confirmed_composition_only",
    "price_approved_by_igor",
    "quote_generation_authorized",
    "client_send_authorized",
    "production_action_authorized",
)

HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
CASE_ID_RE = re.compile(r"CASE-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
MAX_CASE_ID_LENGTH = 128


@dataclass
class ValidationResult:
    envelope_json: Path
    confirmed_composition_json: Path
    status: str = "FAIL"
    expected_artifact_sha256: str = "unavailable"
    actual_artifact_sha256: str = "unavailable"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "envelope JSON readable": "fail",
            "envelope schema": "fail",
            "Case ID": "fail",
            "approval": "fail",
            "supply boundary": "fail",
            "safety": "fail",
            "artifact SHA-256": "fail",
            "confirmed artifact JSON readable": "fail",
            "confirmed artifact schema": "fail",
            "confirmed artifact validator": "fail",
            "confirmed artifact red_flags": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a confirmed composition bridge envelope read-only."
    )
    parser.add_argument("--envelope-json", required=True, type=Path)
    parser.add_argument("--confirmed-composition-json", required=True, type=Path)
    return parser.parse_args(argv)


def add_red_flag(result: ValidationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def require_fields(
    data: Mapping[str, Any],
    fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    for field_name in fields:
        if field_name not in data:
            valid = False
            add_red_flag(
                result,
                f"required field is missing: {field_path(path, field_name)}",
            )
    return valid


def reject_unknown_fields(
    data: Mapping[str, Any],
    fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    allowed = set(fields)
    for field_name in data:
        if field_name not in allowed:
            valid = False
            add_red_flag(
                result,
                f"unknown field is not allowed: {field_path(path, field_name)}",
            )
    return valid


def require_mapping(
    value: Any,
    path: str,
    result: ValidationResult,
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        add_red_flag(result, f"field must be an object: {path}")
        return None
    return cast(Mapping[str, Any], value)


def require_non_empty_string(
    value: Any,
    path: str,
    result: ValidationResult,
) -> bool:
    if not isinstance(value, str) or not value.strip():
        add_red_flag(result, f"field must be a non-empty string: {path}")
        return False
    return True


def read_file_bytes(
    path: Path,
    label: str,
    result: ValidationResult,
) -> bytes | None:
    if not path.exists():
        add_red_flag(result, f"{label} does not exist")
        return None
    if not path.is_file():
        add_red_flag(result, f"{label} must be a regular file")
        return None
    try:
        return path.read_bytes()
    except OSError:
        add_red_flag(result, f"{label} could not be read")
        return None


def parse_json_object(
    raw_bytes: bytes,
    label: str,
    result: ValidationResult,
) -> Mapping[str, Any] | None:
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        add_red_flag(result, f"{label} must be valid UTF-8")
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        add_red_flag(result, f"{label} is malformed JSON")
        return None
    if not isinstance(value, Mapping):
        add_red_flag(result, f"{label} root must be an object")
        return None
    return cast(Mapping[str, Any], value)


def valid_case_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_CASE_ID_LENGTH
        and CASE_ID_RE.fullmatch(value) is not None
    )


def valid_timezone_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_case(value: Any, result: ValidationResult) -> None:
    case = require_mapping(value, "case", result)
    if case is None:
        return
    valid = require_fields(case, CASE_FIELDS, "case", result)
    if not reject_unknown_fields(case, CASE_FIELDS, "case", result):
        valid = False
    if not valid_case_id(case.get("case_id")):
        valid = False
        add_red_flag(
            result,
            "case.case_id must match CASE-[A-Z0-9]+ segments separated by "
            "single hyphens",
        )
    for field_name in ("customer_label", "object_name"):
        if not require_non_empty_string(
            case.get(field_name),
            field_path("case", field_name),
            result,
        ):
            valid = False
    result.checks["Case ID"] = "pass" if valid else "fail"


def validate_confirmed_reference(value: Any, result: ValidationResult) -> bool:
    reference = require_mapping(value, "confirmed_composition", result)
    if reference is None:
        return False
    valid = require_fields(
        reference,
        CONFIRMED_COMPOSITION_FIELDS,
        "confirmed_composition",
        result,
    )
    if not reject_unknown_fields(
        reference,
        CONFIRMED_COMPOSITION_FIELDS,
        "confirmed_composition",
        result,
    ):
        valid = False
    if reference.get("schema_version") != CONFIRMED_SCHEMA_VERSION:
        valid = False
        add_red_flag(
            result,
            "confirmed_composition.schema_version must be "
            "confirmed_composition_artifact.v0.1",
        )
    sha256_value = reference.get("artifact_sha256")
    if not isinstance(sha256_value, str) or HASH_RE.fullmatch(sha256_value) is None:
        valid = False
        result.expected_artifact_sha256 = "invalid"
        add_red_flag(
            result,
            "confirmed_composition.artifact_sha256 must be 64 lowercase hex characters",
        )
    else:
        result.expected_artifact_sha256 = sha256_value
    return valid


def validate_supply_boundary(value: Any, result: ValidationResult) -> None:
    boundary = require_mapping(value, "supply_boundary", result)
    if boundary is None:
        return
    valid = require_fields(
        boundary,
        SUPPLY_BOUNDARY_FIELDS,
        "supply_boundary",
        result,
    )
    if not reject_unknown_fields(
        boundary,
        SUPPLY_BOUNDARY_FIELDS,
        "supply_boundary",
        result,
    ):
        valid = False
    if boundary.get("status") != SUPPLY_BOUNDARY_STATUS:
        valid = False
        add_red_flag(result, "supply_boundary.status must be approved_by_igor")
    if boundary.get("approved_by_igor") is not True:
        valid = False
        add_red_flag(result, "supply_boundary.approved_by_igor must be true")
    if not require_non_empty_string(
        boundary.get("description"),
        "supply_boundary.description",
        result,
    ):
        valid = False
    result.checks["supply boundary"] = "pass" if valid else "fail"


def validate_approval(value: Any, result: ValidationResult) -> None:
    approval = require_mapping(value, "approval", result)
    if approval is None:
        return
    valid = require_fields(approval, APPROVAL_FIELDS, "approval", result)
    if not reject_unknown_fields(approval, APPROVAL_FIELDS, "approval", result):
        valid = False
    for field_name in ("approval_record_id", "approved_by", "approval_channel"):
        if not require_non_empty_string(
            approval.get(field_name),
            field_path("approval", field_name),
            result,
        ):
            valid = False
    if not valid_timezone_timestamp(approval.get("approved_at")):
        valid = False
        add_red_flag(
            result,
            "approval.approved_at must be an ISO 8601 timestamp with timezone",
        )
    if approval.get("scope") != APPROVAL_SCOPE:
        valid = False
        add_red_flag(
            result,
            "approval.scope must be "
            "transfer_confirmed_composition_for_calculator_input_draft_only",
        )
    result.checks["approval"] = "pass" if valid else "fail"


def validate_safety(value: Any, result: ValidationResult) -> None:
    safety = require_mapping(value, "safety", result)
    if safety is None:
        return
    valid = require_fields(safety, SAFETY_FIELDS, "safety", result)
    if not reject_unknown_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if safety.get("status") != SAFETY_STATUS:
        valid = False
        add_red_flag(result, "safety.status must be confirmed_composition_bridge_only")
    if safety.get("transfer_confirmed_composition_only") is not True:
        valid = False
        add_red_flag(result, "safety.transfer_confirmed_composition_only must be true")
    for field_name in (
        "price_approved_by_igor",
        "quote_generation_authorized",
        "client_send_authorized",
        "production_action_authorized",
    ):
        if safety.get(field_name) is not False:
            valid = False
            add_red_flag(result, f"safety.{field_name} must be false")
        if safety.get(field_name) is True:
            add_red_flag(
                result, f"commercial or production flag is true: safety.{field_name}"
            )
    result.checks["safety"] = "pass" if valid else "fail"


def validate_envelope_schema(
    data: Mapping[str, Any],
    result: ValidationResult,
) -> None:
    root_valid = require_fields(data, ROOT_FIELDS, "", result)
    if not reject_unknown_fields(data, ROOT_FIELDS, "", result):
        root_valid = False
    if data.get("schema_version") != SCHEMA_VERSION:
        root_valid = False
        add_red_flag(
            result,
            "schema_version must be confirmed_composition_bridge_envelope.v0.1",
        )
    validate_case(data.get("case"), result)
    reference_valid = validate_confirmed_reference(
        data.get("confirmed_composition"), result
    )
    validate_supply_boundary(data.get("supply_boundary"), result)
    validate_approval(data.get("approval"), result)
    validate_safety(data.get("safety"), result)
    result.checks["envelope schema"] = (
        "pass" if root_valid and reference_valid else "fail"
    )


def validate_confirmed_artifact(
    data: Mapping[str, Any] | None,
    result: ValidationResult,
) -> None:
    artifact_result = validate_confirmed_composition_artifact(
        result.confirmed_composition_json
    )
    if artifact_result.status == "PASS":
        result.checks["confirmed artifact validator"] = "pass"
    else:
        for red_flag in artifact_result.red_flags:
            add_red_flag(result, f"confirmed artifact validator: {red_flag}")
        add_red_flag(result, "confirmed artifact validator returned FAIL")

    if data is None:
        return
    if data.get("schema_version") == CONFIRMED_SCHEMA_VERSION:
        result.checks["confirmed artifact schema"] = "pass"
    else:
        add_red_flag(
            result,
            "confirmed artifact schema_version must be "
            "confirmed_composition_artifact.v0.1",
        )
    red_flags = data.get("red_flags")
    if isinstance(red_flags, list) and not red_flags:
        result.checks["confirmed artifact red_flags"] = "pass"
    elif not isinstance(red_flags, list):
        add_red_flag(result, "confirmed artifact red_flags must be a list")
    else:
        add_red_flag(result, "confirmed artifact red_flags must be empty")


def validate_confirmed_composition_bridge_envelope(
    envelope_json: Path,
    confirmed_composition_json: Path,
) -> ValidationResult:
    result = ValidationResult(
        envelope_json=envelope_json.expanduser().resolve(strict=False),
        confirmed_composition_json=confirmed_composition_json.expanduser().resolve(
            strict=False
        ),
    )

    envelope_bytes = read_file_bytes(result.envelope_json, "envelope JSON", result)
    envelope_data = (
        parse_json_object(envelope_bytes, "envelope JSON", result)
        if envelope_bytes is not None
        else None
    )
    if envelope_data is not None:
        result.checks["envelope JSON readable"] = "pass"
        validate_envelope_schema(envelope_data, result)

    artifact_bytes = read_file_bytes(
        result.confirmed_composition_json,
        "confirmed artifact JSON",
        result,
    )
    artifact_data = (
        parse_json_object(artifact_bytes, "confirmed artifact JSON", result)
        if artifact_bytes is not None
        else None
    )
    if artifact_bytes is not None:
        result.actual_artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if artifact_data is not None:
        result.checks["confirmed artifact JSON readable"] = "pass"

    if (
        HASH_RE.fullmatch(result.expected_artifact_sha256) is not None
        and result.expected_artifact_sha256 == result.actual_artifact_sha256
    ):
        result.checks["artifact SHA-256"] = "pass"
    elif result.expected_artifact_sha256 not in {"unavailable", "invalid"}:
        add_red_flag(result, "confirmed artifact SHA-256 does not match envelope")

    validate_confirmed_artifact(artifact_data, result)

    all_checks_pass = all(value == "pass" for value in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ValidationResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Validator:",
        VALIDATOR_NAME,
        "",
        "Mode:",
        MODE,
        "",
        "Envelope path:",
        str(result.envelope_json),
        "",
        "Confirmed artifact path:",
        str(result.confirmed_composition_json),
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(
        [
            "",
            "Expected artifact SHA-256:",
            result.expected_artifact_sha256,
            "",
            "Actual artifact SHA-256:",
            result.actual_artifact_sha256,
            "",
            "Red flags:",
        ]
    )
    lines.extend(format_items(result.red_flags))
    lines.extend(
        [
            "",
            "Status:",
            result.status,
            "",
            "Human Approval:",
            HUMAN_APPROVAL,
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_confirmed_composition_bridge_envelope(
        args.envelope_json,
        args.confirmed_composition_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
