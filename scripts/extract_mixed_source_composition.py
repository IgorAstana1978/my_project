"""Checked operator CLI for preliminary PDF/workbook composition extraction."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from project_spec_extraction import (
    ExtractionArtifacts,
    ExtractionError,
    build_artifacts,
)

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
SECTION_AWARE_INTAKE_VERSION = "section_aware_extraction_intake.v0.1"
SECTION_AWARE_SCHEMA_VERSION = "preliminary_composition_draft.section_aware.v0.1"
SECTION_AWARE_MANIFEST_VERSION = "section_aware_source_bundle.v0.1"
SOURCE_DOCUMENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SECTION_SOURCE_FIELDS = frozenset(
    {"path", "source_document_id", "section_id", "discipline", "source_role"}
)


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


@dataclass(frozen=True)
class SectionSourceDocument:
    path: Path
    intake_path: str
    source_document_id: str
    section_id: str
    discipline: str
    source_role: str


@dataclass(frozen=True)
class SectionAwareIntake:
    path: Path
    project_id: str
    source_documents: tuple[SectionSourceDocument, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract one preliminary switchboard composition review bundle from "
            "a text-layer PDF, an Excel specification, or both."
        )
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--project-pdf", type=Path)
    source_group.add_argument("--section-aware-intake", type=Path)
    parser.add_argument("--spec-workbook", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.section_aware_intake is not None and args.spec_workbook is not None:
        parser.error("--section-aware-intake cannot be combined with --spec-workbook")
    return args


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def add_red_flag(result: OperatorResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtractionError(f"{field_name} must be a non-empty string")
    return value.strip()


def load_section_aware_intake(path: Path) -> SectionAwareIntake:
    intake_path = resolved(path)
    try:
        raw = json.loads(intake_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ExtractionError(
            f"section-aware intake does not exist: {intake_path}"
        ) from error
    except UnicodeDecodeError as error:
        raise ExtractionError("section-aware intake must be valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise ExtractionError("section-aware intake JSON is malformed") from error
    except OSError as error:
        raise ExtractionError("section-aware intake could not be read") from error

    if not isinstance(raw, Mapping):
        raise ExtractionError("section-aware intake root must be an object")
    allowed_root = {"intake_version", "project_id", "source_documents"}
    unknown_root = sorted(set(raw) - allowed_root)
    if unknown_root:
        raise ExtractionError(
            f"section-aware intake has unknown fields: {unknown_root}"
        )
    missing_root = sorted(allowed_root - set(raw))
    if missing_root:
        raise ExtractionError(
            f"section-aware intake is missing required fields: {missing_root}"
        )
    if raw.get("intake_version") != SECTION_AWARE_INTAKE_VERSION:
        raise ExtractionError(
            "intake_version must be section_aware_extraction_intake.v0.1"
        )
    project_id = require_non_empty_string(raw.get("project_id"), "project_id")
    documents_value = raw.get("source_documents")
    if not isinstance(documents_value, list) or not documents_value:
        raise ExtractionError("source_documents must be a non-empty list")

    documents: list[SectionSourceDocument] = []
    records_by_id: dict[str, dict[str, str]] = {}
    for index, value in enumerate(documents_value):
        record_path = f"source_documents[{index}]"
        if not isinstance(value, Mapping):
            raise ExtractionError(f"{record_path} must be an object")
        unknown = sorted(set(value) - SECTION_SOURCE_FIELDS)
        missing = sorted(SECTION_SOURCE_FIELDS - set(value))
        if unknown:
            raise ExtractionError(f"{record_path} has unknown fields: {unknown}")
        if missing:
            raise ExtractionError(
                f"{record_path} is missing required fields: {missing}"
            )
        record = {
            field_name: require_non_empty_string(
                value.get(field_name), f"{record_path}.{field_name}"
            )
            for field_name in SECTION_SOURCE_FIELDS
        }
        document_id = record["source_document_id"]
        if SOURCE_DOCUMENT_ID_RE.fullmatch(document_id) is None:
            raise ExtractionError(
                f"{record_path}.source_document_id must match "
                "[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
            )
        previous = records_by_id.get(document_id)
        if previous is not None:
            detail = "conflicting metadata" if previous != record else "duplicate ID"
            raise ExtractionError(
                f"source_document_id {document_id!r} is repeated with {detail}"
            )
        records_by_id[document_id] = record
        if record["source_role"] != "project_pdf":
            raise ExtractionError(
                f"{record_path}.source_role must be project_pdf in this pilot"
            )
        source_path = Path(record["path"]).expanduser()
        if not source_path.is_absolute():
            source_path = intake_path.parent / source_path
        source_path = source_path.resolve(strict=False)
        if not source_path.is_file():
            raise ExtractionError(f"section-aware source is not a file: {source_path}")
        if source_path.suffix.casefold() != ".pdf":
            raise ExtractionError(f"section-aware source must be a PDF: {source_path}")
        documents.append(
            SectionSourceDocument(
                path=source_path,
                intake_path=record["path"],
                source_document_id=document_id,
                section_id=record["section_id"],
                discipline=record["discipline"],
                source_role=record["source_role"],
            )
        )
    return SectionAwareIntake(
        path=intake_path,
        project_id=project_id,
        source_documents=tuple(documents),
    )


def section_context(
    intake: SectionAwareIntake,
    document: SectionSourceDocument,
) -> dict[str, str]:
    return {
        "project_id": intake.project_id,
        "section_id": document.section_id,
        "discipline": document.discipline,
        "source_document_id": document.source_document_id,
        "source_role": document.source_role,
    }


def decorate_provenance(
    values: object,
    context: Mapping[str, str],
    *,
    item_id: str,
    component_id: str | None = None,
) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        if not isinstance(value, dict):
            continue
        value.update(context)
        value["item_id"] = item_id
        if component_id is not None:
            value["component_id"] = component_id


def decorate_conflicts(
    values: object,
    context: Mapping[str, str],
    *,
    item_id: str,
    component_id: str | None = None,
) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        if isinstance(value, dict):
            decorate_provenance(
                value.get("sources"),
                context,
                item_id=item_id,
                component_id=component_id,
            )


def decorate_section_item(
    item_value: object,
    *,
    context: Mapping[str, str],
    item_id: str,
    source_designation: str,
) -> dict[str, Any]:
    item = copy.deepcopy(cast(dict[str, Any], item_value))
    item["item_id"] = item_id
    item.update(context)
    item["source_designation"] = source_designation
    decorate_provenance(item.get("provenance"), context, item_id=item_id)
    decorate_conflicts(item.get("conflicts"), context, item_id=item_id)
    for index, component_value in enumerate(item.get("components", []), start=1):
        component = cast(dict[str, Any], component_value)
        component_id = f"{item_id}-COMP-{index:03d}"
        component["component_id"] = component_id
        component.update(context)
        component["item_id"] = item_id
        decorate_provenance(
            component.get("provenance"),
            context,
            item_id=item_id,
            component_id=component_id,
        )
        decorate_conflicts(
            component.get("conflicts"),
            context,
            item_id=item_id,
            component_id=component_id,
        )
    return item


def combined_summary(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for key in summaries[0]:
        values = [summary[key] for summary in summaries]
        if key == "file_types":
            combined[key] = [file_type for value in values for file_type in value]
        elif key == "ready_for_preliminary_workflow":
            combined[key] = any(bool(value) for value in values)
        else:
            combined[key] = sum(cast(int, value) for value in values)
    return combined


def build_section_aware_artifacts(intake_path: Path) -> ExtractionArtifacts:
    intake = load_section_aware_intake(intake_path)
    source_documents: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    summaries: list[Mapping[str, Any]] = []
    root_red_flags: list[str] = []
    confidence_values: list[float] = []

    for document in intake.source_documents:
        artifacts = build_artifacts(document.path, None)
        context = section_context(intake, document)
        summaries.append(artifacts.summary)
        root_red_flags.extend(cast(list[str], artifacts.draft["red_flags"]))
        confidence_values.append(cast(float, artifacts.draft["overall_confidence"]))
        source_files = cast(
            list[dict[str, Any]],
            cast(dict[str, Any], artifacts.draft["source"])["source_files"],
        )
        source_record = copy.deepcopy(source_files[0])
        source_record.update(context)
        source_record["intake_path"] = document.intake_path
        source_record["resolved_path"] = str(document.path)
        source_documents.append(source_record)

        draft_items = cast(list[dict[str, Any]], artifacts.draft["items"])
        if len(draft_items) != len(artifacts.boards):
            raise ExtractionError(
                "section-aware extraction lost board-to-item correspondence"
            )
        for draft_item, board in zip(draft_items, artifacts.boards, strict=True):
            item_id = f"ITEM-{len(items) + 1:03d}"
            items.append(
                decorate_section_item(
                    draft_item,
                    context=context,
                    item_id=item_id,
                    source_designation=board.designation,
                )
            )

    manifest_data = {
        "manifest_version": SECTION_AWARE_MANIFEST_VERSION,
        "project_id": intake.project_id,
        "source_documents": source_documents,
    }
    manifest_text = (
        json.dumps(manifest_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    manifest_hash = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    summary = combined_summary(summaries)
    draft = {
        "schema_version": SECTION_AWARE_SCHEMA_VERSION,
        "draft_id": f"PRELIM-SECTION-{manifest_hash[:12].upper()}",
        "created_by": "project_spec_extraction.section_aware",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "source_type": "other",
            "source_summary": "Section-aware multi-PDF extraction bundle.",
            "raw_input_sha256": manifest_hash,
            "source_documents": source_documents,
        },
        "safety": {
            "status": "preliminary_only",
            "confirmed_by_igor": False,
            "price_execution_authorized": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "items": items,
        "overall_confidence": min(confidence_values, default=0.0),
        "red_flags": list(dict.fromkeys(root_red_flags)),
        "assumptions": [
            "Extraction is heuristic and preliminary; no engineering substitutions "
            "were made."
        ],
        "next_required_human_actions": [
            "Igor reviews conflicts, missing values, and source-only rows before "
            "confirming composition."
        ],
        "extraction_summary": summary,
    }
    return ExtractionArtifacts(
        manifest_text=manifest_text,
        draft=draft,
        summary=summary,
    )


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
    *,
    section_aware_intake: Path | None = None,
) -> OperatorResult:
    result = OperatorResult(output_dir=resolved(output_dir))
    created_output = False
    try:
        if section_aware_intake is not None and (
            project_pdf is not None or spec_workbook is not None
        ):
            raise ExtractionError(
                "section-aware intake cannot be combined with v0.1 PDF/workbook inputs"
            )
        if (
            project_pdf is None
            and spec_workbook is None
            and section_aware_intake is None
        ):
            raise ExtractionError("at least one source must be provided")
        output = validate_output_policy(output_dir)
        result.output_dir = output
        result.checks["input policy"] = "pass"

        artifacts = (
            build_section_aware_artifacts(section_aware_intake)
            if section_aware_intake is not None
            else build_artifacts(project_pdf, spec_workbook)
        )
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
    result = run_operator(
        args.project_pdf,
        args.spec_workbook,
        args.output_dir,
        section_aware_intake=args.section_aware_intake,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
