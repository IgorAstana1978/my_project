"""Preflight approved client-style invoice inputs without creating output."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_START = "CLIENT_STYLE_INVOICE_PREFLIGHT_REPORT_START"
REPORT_END = "CLIENT_STYLE_INVOICE_PREFLIGHT_REPORT_END"
MODE = "read-only client-style invoice export preflight"
COMMERCIAL_STATUS = "preflight only; PASS is not commercial approval"
HUMAN_APPROVAL = "required before sending to client"

REQUIRED_FIELDS = (
    "approval_id",
    "approved_by",
    "approved_at",
    "commercial_csv_sha256",
    "internal_draft_xlsx_sha256",
    "template_sha256",
    "invoice_number",
    "invoice_date",
    "payer_name",
    "object_name",
    "vat_text_approved",
    "payment_terms_approved",
    "delivery_terms_approved",
    "validity_terms_approved",
    "return_terms_approved",
    "signer_name",
    "signer_title",
    "approval_note",
)
HASH_FIELDS = (
    "commercial_csv_sha256",
    "internal_draft_xlsx_sha256",
    "template_sha256",
)
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d{1,6})?)?"
    r"(?:Z|[+-]\d{2}:\d{2})\Z"
)


@dataclass
class ClientStylePreflightResult:
    commercial_csv: Path
    internal_draft_xlsx: Path
    template_xlsx: Path
    approval_json: Path
    output_xlsx: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "input paths": "fail",
            "output policy": "fail",
            "approval artifact schema": "fail",
            "hash verification": "fail",
            "safety boundaries": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only fail-closed preflight for future client-style invoice " "export."
        )
    )
    parser.add_argument("--commercial-csv", required=True, type=Path)
    parser.add_argument("--internal-draft-xlsx", required=True, type=Path)
    parser.add_argument("--template-xlsx", required=True, type=Path)
    parser.add_argument("--approval-json", required=True, type=Path)
    parser.add_argument("--output-xlsx", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: ClientStylePreflightResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def validate_input_paths(result: ClientStylePreflightResult) -> bool:
    valid = True
    inputs = (
        ("commercial CSV", result.commercial_csv, ".csv"),
        ("internal draft XLSX", result.internal_draft_xlsx, ".xlsx"),
        ("client-style template", result.template_xlsx, ".xlsx"),
        ("approval JSON", result.approval_json, ".json"),
    )

    for label, path, suffix in inputs:
        if not path.is_file():
            valid = False
            add_red_flag(result, f"{label} does not exist")
        if path.suffix.casefold() != suffix:
            valid = False
            add_red_flag(result, f"{label} suffix must be {suffix}")

    outside_git_inputs = (
        ("commercial CSV", result.commercial_csv),
        ("internal draft XLSX", result.internal_draft_xlsx),
        ("client-style template", result.template_xlsx),
        ("approval JSON", result.approval_json),
    )
    for label, path in outside_git_inputs:
        if is_inside_project(path):
            valid = False
            add_red_flag(result, f"{label} must be outside the Git project")

    result.checks["input paths"] = "pass" if valid else "fail"
    return valid


def validate_output_policy(result: ClientStylePreflightResult) -> bool:
    valid = True
    output = result.output_xlsx

    if output.suffix.casefold() != ".xlsx":
        valid = False
        add_red_flag(result, "output suffix must be .xlsx")
    if is_inside_project(output):
        valid = False
        add_red_flag(result, "output XLSX must be outside the Git project")
    if output.exists():
        valid = False
        add_red_flag(result, "output XLSX already exists")
    if not output.parent.is_dir():
        valid = False
        add_red_flag(result, "output parent directory does not exist")

    input_paths = {
        result.commercial_csv,
        result.internal_draft_xlsx,
        result.template_xlsx,
        result.approval_json,
    }
    if output in input_paths:
        valid = False
        add_red_flag(result, "output XLSX must not match any input path")

    result.checks["output policy"] = "pass" if valid else "fail"
    return valid


def load_approval_artifact(
    path: Path,
    result: ClientStylePreflightResult,
) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        add_red_flag(result, "approval JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "approval JSON is invalid")
        return None
    except OSError:
        add_red_flag(result, "approval JSON could not be read")
        return None

    if not isinstance(raw, Mapping):
        add_red_flag(result, "approval JSON root must be an object")
        return None
    return cast(Mapping[str, Any], raw)


def valid_approved_at(value: str) -> bool:
    if TIMESTAMP_RE.fullmatch(value) is None:
        return False
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_approval_schema(
    artifact: Mapping[str, Any] | None,
    result: ClientStylePreflightResult,
) -> bool:
    if artifact is None:
        result.checks["approval artifact schema"] = "fail"
        return False

    valid = True
    for field_name in REQUIRED_FIELDS:
        if field_name not in artifact:
            valid = False
            add_red_flag(result, f"approval field is missing: {field_name}")

    if not all(field_name in artifact for field_name in REQUIRED_FIELDS):
        result.checks["approval artifact schema"] = "fail"
        return False

    object_name = artifact["object_name"]
    if object_name is not None and not isinstance(object_name, str):
        valid = False
        add_red_flag(result, "object_name must be a string or null")

    for field_name in REQUIRED_FIELDS:
        if field_name == "object_name":
            continue
        value = artifact[field_name]
        if not isinstance(value, str) or value.strip() == "":
            valid = False
            add_red_flag(
                result, f"approval field must be a non-empty string: {field_name}"
            )

    for field_name in HASH_FIELDS:
        value = artifact[field_name]
        if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
            valid = False
            add_red_flag(
                result,
                f"approval hash must be 64 lowercase hex characters: {field_name}",
            )

    approved_at = artifact["approved_at"]
    if not isinstance(approved_at, str) or not valid_approved_at(approved_at):
        valid = False
        add_red_flag(result, "approved_at must be an ISO 8601 timestamp with timezone")

    result.checks["approval artifact schema"] = "pass" if valid else "fail"
    return valid


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_hashes(
    artifact: Mapping[str, Any] | None,
    input_paths_ok: bool,
    schema_ok: bool,
    result: ClientStylePreflightResult,
) -> bool:
    if artifact is None or not input_paths_ok or not schema_ok:
        add_red_flag(result, "hash verification could not run safely")
        result.checks["hash verification"] = "fail"
        return False

    expected_by_path = (
        (
            "commercial CSV",
            result.commercial_csv,
            cast(str, artifact["commercial_csv_sha256"]),
        ),
        (
            "internal draft XLSX",
            result.internal_draft_xlsx,
            cast(str, artifact["internal_draft_xlsx_sha256"]),
        ),
        (
            "client-style template",
            result.template_xlsx,
            cast(str, artifact["template_sha256"]),
        ),
    )

    valid = True
    for label, path, expected_hash in expected_by_path:
        try:
            actual_hash = sha256_file(path)
        except OSError:
            valid = False
            add_red_flag(result, f"{label} could not be hashed")
            continue
        if actual_hash != expected_hash:
            valid = False
            add_red_flag(result, f"{label} SHA256 does not match approval")

    result.checks["hash verification"] = "pass" if valid else "fail"
    return valid


def preflight(
    commercial_csv: Path,
    internal_draft_xlsx: Path,
    template_xlsx: Path,
    approval_json: Path,
    output_xlsx: Path,
) -> ClientStylePreflightResult:
    result = ClientStylePreflightResult(
        commercial_csv=resolved(commercial_csv),
        internal_draft_xlsx=resolved(internal_draft_xlsx),
        template_xlsx=resolved(template_xlsx),
        approval_json=resolved(approval_json),
        output_xlsx=resolved(output_xlsx),
    )

    input_paths_ok = validate_input_paths(result)
    output_policy_ok = validate_output_policy(result)
    artifact = load_approval_artifact(result.approval_json, result)
    schema_ok = validate_approval_schema(artifact, result)
    hashes_ok = verify_hashes(artifact, input_paths_ok, schema_ok, result)

    result.checks["safety boundaries"] = "pass"
    all_checks_pass = (
        input_paths_ok
        and output_policy_ok
        and schema_ok
        and hashes_ok
        and all(status == "pass" for status in result.checks.values())
    )
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ClientStylePreflightResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        MODE,
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(["", "Red flags:"])
    lines.extend(format_items(result.red_flags))
    lines.extend(
        [
            "",
            "Commercial status:",
            COMMERCIAL_STATUS,
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
    result = preflight(
        args.commercial_csv,
        args.internal_draft_xlsx,
        args.template_xlsx,
        args.approval_json,
        args.output_xlsx,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
