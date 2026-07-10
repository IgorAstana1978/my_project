"""Checked operator CLI for preliminary PDF/workbook composition extraction."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from project_spec_extraction import ExtractionError, build_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_preliminary_composition_draft.py")
REVIEW_BUILDER_PATH = Path(__file__).with_name(
    "build_preliminary_composition_review_card.py"
)
REPORT_START = "MIXED_SOURCE_COMPOSITION_EXTRACTION_REPORT_START"
REPORT_END = "MIXED_SOURCE_COMPOSITION_EXTRACTION_REPORT_END"
MANIFEST_NAME = "source-bundle-manifest.txt"
DRAFT_NAME = "preliminary-composition-draft.json"
REVIEW_NAME = "igor-review-card.md"


@dataclass
class OperatorResult:
    output_dir: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "input policy": "fail",
            "source extraction": "fail",
            "preliminary draft validation": "fail",
            "source bundle verification and review card": "fail",
            "safety boundary": "fail",
        }
    )
    summary: dict[str, object] = field(default_factory=dict)
    red_flags: list[str] = field(default_factory=list)
    manifest_path: Path | None = None
    draft_path: Path | None = None
    review_path: Path | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract one preliminary switchboard composition review bundle from "
            "a text-layer PDF, an Excel specification, or both."
        )
    )
    parser.add_argument("--project-pdf", type=Path)
    parser.add_argument("--spec-workbook", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def add_red_flag(result: OperatorResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def validate_output_policy(output_dir: Path) -> Path:
    output = resolved(output_dir)
    if output.is_relative_to(PROJECT_ROOT):
        raise ExtractionError(
            f"output directory must be outside the Git project: {output}"
        )
    if output.exists():
        raise ExtractionError(f"output directory already exists: {output}")
    if not output.parent.is_dir():
        raise ExtractionError(
            f"output parent directory does not exist: {output.parent}"
        )
    return output


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load required workflow module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cleanup_created_output(output_dir: Path) -> None:
    for file_name in (REVIEW_NAME, DRAFT_NAME, MANIFEST_NAME):
        path = output_dir / file_name
        if path.is_file():
            path.unlink()
    try:
        output_dir.rmdir()
    except OSError:
        return


def run_operator(
    project_pdf: Path | None,
    spec_workbook: Path | None,
    output_dir: Path,
) -> OperatorResult:
    result = OperatorResult(output_dir=resolved(output_dir))
    created_output = False
    try:
        if project_pdf is None and spec_workbook is None:
            raise ExtractionError("at least one source must be provided")
        output = validate_output_policy(output_dir)
        result.output_dir = output
        result.checks["input policy"] = "pass"

        artifacts = build_artifacts(project_pdf, spec_workbook)
        result.summary = artifacts.summary
        result.checks["source extraction"] = "pass"

        output.mkdir()
        created_output = True
        manifest_path = output / MANIFEST_NAME
        draft_path = output / DRAFT_NAME
        review_path = output / REVIEW_NAME
        manifest_path.write_bytes(artifacts.manifest_text.encode("utf-8"))
        draft_path.write_text(
            json.dumps(artifacts.draft, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result.manifest_path = manifest_path
        result.draft_path = draft_path

        validator = load_module("mixed_source_preliminary_validator", VALIDATOR_PATH)
        validation = validator.validate_preliminary_composition_draft(draft_path)
        if validation.status != "PASS":
            for red_flag in validation.red_flags:
                add_red_flag(result, f"preliminary validator: {red_flag}")
            raise ExtractionError(
                "generated preliminary composition draft failed validation"
            )
        result.checks["preliminary draft validation"] = "pass"
        result.checks["safety boundary"] = "pass"

        review_builder = load_module("mixed_source_review_builder", REVIEW_BUILDER_PATH)
        review_result = review_builder.build_review_card(
            manifest_path, draft_path, review_path
        )
        if review_result.status != "PASS":
            for red_flag in review_result.red_flags:
                add_red_flag(result, f"review card: {red_flag}")
            raise ExtractionError("existing Igor review card workflow failed")
        result.review_path = review_path
        result.checks["source bundle verification and review card"] = "pass"
        result.status = "PASS"
        return result
    except (ExtractionError, OSError, RuntimeError) as error:
        add_red_flag(result, str(error))
        if created_output and result.output_dir.is_dir():
            cleanup_created_output(result.output_dir)
        result.manifest_path = None
        result.draft_path = None
        result.review_path = None
        return result


def format_report(result: OperatorResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(["", "Summary:"])
    if result.summary:
        lines.extend(f"{name}: {value}" for name, value in result.summary.items())
    else:
        lines.append("not available")
    lines.extend(["", "Requires Igor review:"])
    lines.extend(result.red_flags or ["see Igor review card"])
    lines.extend(
        [
            "",
            "Outputs:",
            f"manifest: {result.manifest_path or 'not created'}",
            f"draft: {result.draft_path or 'not created'}",
            f"review card: {result.review_path or 'not created'}",
            "",
            "Human Approval:",
            (
                "Extraction PASS is preliminary only. Igor must separately approve "
                "composition, price, term, commercial CSV, final КП, sending, "
                "procurement, and production."
            ),
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_operator(args.project_pdf, args.spec_workbook, args.output_dir)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
