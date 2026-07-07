"""Create a draft client-style approval JSON outside the project tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_START = "CLIENT_STYLE_APPROVAL_DRAFT_REPORT_START"
REPORT_END = "CLIENT_STYLE_APPROVAL_DRAFT_REPORT_END"
MODE = "approval JSON draft only"
COMMERCIAL_STATUS = "not commercial approval"
SENDING_STATUS = "not sending approval"
HUMAN_REVIEW = "manual Igor review required before exporter/launcher"

APPROVAL_FIELDS = (
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


@dataclass
class ApprovalDraftResult:
    commercial_csv: Path
    internal_draft_xlsx: Path
    template_xlsx: Path
    output_json: Path
    status: str = "FAIL"
    draft_created: bool = False
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "output policy": "fail",
            "input paths": "fail",
            "hash calculation": "fail",
            "draft write": "fail",
            "safety boundaries": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a reviewable client-style approval JSON draft."
    )
    parser.add_argument("--commercial-csv", required=True, type=Path)
    parser.add_argument("--internal-draft-xlsx", required=True, type=Path)
    parser.add_argument("--template-xlsx", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--invoice-number", required=True)
    parser.add_argument("--invoice-date", required=True)
    parser.add_argument("--payer-name", required=True)
    parser.add_argument("--vat-text-approved", required=True)
    parser.add_argument("--payment-terms-approved", required=True)
    parser.add_argument("--delivery-terms-approved", required=True)
    parser.add_argument("--validity-terms-approved", required=True)
    parser.add_argument("--return-terms-approved", required=True)
    parser.add_argument("--signer-name", required=True)
    parser.add_argument("--signer-title", required=True)
    parser.add_argument("--approval-note", required=True)
    parser.add_argument("--object-name")
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: ApprovalDraftResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def validate_output_policy(result: ApprovalDraftResult) -> bool:
    valid = True
    output = result.output_json

    if output.exists():
        valid = False
        add_red_flag(result, "output JSON already exists")
    if is_inside_project(output):
        valid = False
        add_red_flag(result, "output JSON must be outside the project")
    if not output.parent.is_dir():
        valid = False
        add_red_flag(result, "output parent directory does not exist")

    result.checks["output policy"] = "pass" if valid else "fail"
    return valid


def validate_input_paths(result: ApprovalDraftResult) -> bool:
    valid = True
    inputs = (
        ("commercial CSV", result.commercial_csv),
        ("internal draft XLSX", result.internal_draft_xlsx),
        ("client-style template", result.template_xlsx),
    )

    for label, path in inputs:
        if not path.is_file():
            valid = False
            add_red_flag(result, f"{label} does not exist")
        if is_inside_project(path):
            valid = False
            add_red_flag(result, f"{label} must be outside the project")

    result.checks["input paths"] = "pass" if valid else "fail"
    return valid


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def approval_payload(
    args: argparse.Namespace,
    hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "approval_id": args.approval_id,
        "approved_by": args.approved_by,
        "approved_at": args.approved_at,
        "commercial_csv_sha256": hashes["commercial_csv_sha256"],
        "internal_draft_xlsx_sha256": hashes["internal_draft_xlsx_sha256"],
        "template_sha256": hashes["template_sha256"],
        "invoice_number": args.invoice_number,
        "invoice_date": args.invoice_date,
        "payer_name": args.payer_name,
        "object_name": args.object_name,
        "vat_text_approved": args.vat_text_approved,
        "payment_terms_approved": args.payment_terms_approved,
        "delivery_terms_approved": args.delivery_terms_approved,
        "validity_terms_approved": args.validity_terms_approved,
        "return_terms_approved": args.return_terms_approved,
        "signer_name": args.signer_name,
        "signer_title": args.signer_title,
        "approval_note": args.approval_note,
    }


def write_approval_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def create_draft(args: argparse.Namespace) -> ApprovalDraftResult:
    result = ApprovalDraftResult(
        commercial_csv=resolved(args.commercial_csv),
        internal_draft_xlsx=resolved(args.internal_draft_xlsx),
        template_xlsx=resolved(args.template_xlsx),
        output_json=resolved(args.output_json),
    )

    output_ok = validate_output_policy(result)
    inputs_ok = validate_input_paths(result)
    if not output_ok or not inputs_ok:
        result.checks["safety boundaries"] = "pass"
        return result

    try:
        hashes = {
            "commercial_csv_sha256": sha256_file(result.commercial_csv),
            "internal_draft_xlsx_sha256": sha256_file(result.internal_draft_xlsx),
            "template_sha256": sha256_file(result.template_xlsx),
        }
    except OSError:
        add_red_flag(result, "input file could not be hashed")
        result.checks["hash calculation"] = "fail"
        result.checks["safety boundaries"] = "pass"
        return result

    result.checks["hash calculation"] = "pass"
    payload = approval_payload(args, hashes)
    try:
        write_approval_json(result.output_json, payload)
    except OSError:
        add_red_flag(result, "approval JSON draft could not be written")
        result.checks["draft write"] = "fail"
        result.checks["safety boundaries"] = "pass"
        return result

    result.draft_created = True
    result.checks["draft write"] = "pass"
    result.checks["safety boundaries"] = "pass"
    result.status = (
        "PASS" if all(v == "pass" for v in result.checks.values()) else "FAIL"
    )
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ApprovalDraftResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        MODE,
        "",
        "Draft created:",
        "yes" if result.draft_created else "no",
        "",
        "Output JSON:",
        str(result.output_json),
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
            "Sending status:",
            SENDING_STATUS,
            "",
            "Human review:",
            HUMAN_REVIEW,
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = create_draft(args)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
