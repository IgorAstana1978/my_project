"""Verify that a preliminary composition draft is bound to its raw source text."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

REPORT_START = "PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_START"
REPORT_END = "PRELIMINARY_COMPOSITION_SOURCE_BUNDLE_REPORT_END"
MODE = "preliminary composition source bundle verification only"
COMMERCIAL_STATUS = "not confirmed composition; not price approval; not client-ready КП"
HUMAN_APPROVAL = "Igor confirmation required before price calculation or commercial CSV"
HASH_LENGTH = 64

VALIDATOR_PATH = Path(__file__).with_name("validate_preliminary_composition_draft.py")


@dataclass
class SourceMetadata:
    source_type: str | None = None
    raw_input_sha256: str | None = None


@dataclass
class BundleVerificationResult:
    raw_input_text: Path
    draft_json: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "raw input readable": "fail",
            "draft validation": "fail",
            "source hash match": "fail",
            "safety boundary": "fail",
        }
    )
    calculated_hash: str | None = None
    draft_hash: str | None = None
    source_type: str | None = None
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a preliminary composition draft against the exact raw source "
            "text bytes it claims to analyze."
        )
    )
    parser.add_argument("--raw-input-text", required=True, type=Path)
    parser.add_argument("--draft-json", required=True, type=Path)
    return parser.parse_args(argv)


def add_red_flag(result: BundleVerificationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_preliminary_composition_draft_for_bundle",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "preliminary composition draft validator could not be loaded"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_raw_input_hash(path: Path, result: BundleVerificationResult) -> str | None:
    try:
        raw_bytes = path.read_bytes()
        raw_bytes.decode("utf-8")
    except FileNotFoundError:
        add_red_flag(result, "raw input text does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "raw input text must be valid UTF-8")
        return None
    except OSError:
        add_red_flag(result, "raw input text could not be read")
        return None

    digest = hashlib.sha256(raw_bytes).hexdigest()
    result.checks["raw input readable"] = "pass"
    result.calculated_hash = digest
    return digest


def load_source_metadata(
    path: Path,
    result: BundleVerificationResult,
) -> SourceMetadata:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SourceMetadata()
    except UnicodeDecodeError:
        return SourceMetadata()
    except json.JSONDecodeError:
        return SourceMetadata()
    except OSError:
        return SourceMetadata()

    if not isinstance(raw, Mapping):
        return SourceMetadata()

    source = raw.get("source")
    if not isinstance(source, Mapping):
        add_red_flag(result, "source object is missing or invalid")
        return SourceMetadata()

    source_type = source.get("source_type")
    raw_input_sha256 = source.get("raw_input_sha256")
    metadata = SourceMetadata(
        source_type=source_type if isinstance(source_type, str) else None,
        raw_input_sha256=(
            raw_input_sha256 if isinstance(raw_input_sha256, str) else None
        ),
    )

    if metadata.raw_input_sha256 is None:
        add_red_flag(result, "source.raw_input_sha256 is missing or invalid")
    return metadata


def run_draft_validation(
    draft_json: Path,
    result: BundleVerificationResult,
) -> None:
    validator = load_validator_module()
    validation = validator.validate_preliminary_composition_draft(draft_json)

    if validation.status == "PASS":
        result.checks["draft validation"] = "pass"
    else:
        add_red_flag(result, "preliminary draft validator failed")

    safety_status = validation.checks.get("safety boundary")
    if safety_status == "pass":
        result.checks["safety boundary"] = "pass"

    for red_flag in validation.red_flags:
        add_red_flag(result, f"draft validation: {red_flag}")


def is_valid_hash(value: str | None) -> bool:
    if value is None or len(value) != HASH_LENGTH:
        return False
    return all(character in "0123456789abcdef" for character in value)


def compare_hashes(
    calculated_hash: str | None,
    metadata: SourceMetadata,
    result: BundleVerificationResult,
) -> None:
    result.source_type = metadata.source_type
    result.draft_hash = metadata.raw_input_sha256

    if calculated_hash is None:
        add_red_flag(result, "calculated raw input SHA256 is unavailable")
        return
    if not is_valid_hash(metadata.raw_input_sha256):
        add_red_flag(
            result,
            "source.raw_input_sha256 must be 64 lowercase hex characters",
        )
        return
    if calculated_hash != metadata.raw_input_sha256:
        add_red_flag(result, "raw input SHA256 mismatch")
        return

    result.checks["source hash match"] = "pass"


def verify_source_bundle(
    raw_input_text: Path,
    draft_json: Path,
) -> BundleVerificationResult:
    result = BundleVerificationResult(
        raw_input_text=raw_input_text.expanduser().resolve(strict=False),
        draft_json=draft_json.expanduser().resolve(strict=False),
    )

    calculated_hash = read_raw_input_hash(result.raw_input_text, result)
    run_draft_validation(result.draft_json, result)
    metadata = load_source_metadata(result.draft_json, result)
    compare_hashes(calculated_hash, metadata, result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_optional(value: str | None) -> str:
    return value if value is not None else "unavailable"


def format_report(result: BundleVerificationResult) -> str:
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
    lines.extend(
        [
            "",
            "Source:",
            f"source_type: {format_optional(result.source_type)}",
            f"calculated raw_input_sha256: {format_optional(result.calculated_hash)}",
            f"draft raw_input_sha256: {format_optional(result.draft_hash)}",
            "",
            "Red flags:",
        ]
    )
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
    result = verify_source_bundle(args.raw_input_text, args.draft_json)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
