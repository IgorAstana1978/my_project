"""Publish one checked Phase 2.32 extraction bundle under a canonical Case ID."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extract_mixed_source_composition import (
    DRAFT_NAME,
    MANIFEST_NAME,
    REVIEW_NAME,
    run_operator,
)
from project_spec_extraction import SUPPORTED_WORKBOOK_SUFFIXES

CANONICAL_ROOT = Path.home() / "Documents" / "production_ai_cases"
CASE_ID_RE = re.compile(r"CASE-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
MAX_CASE_ID_LENGTH = 128
EXPECTED_FILES = frozenset({MANIFEST_NAME, DRAFT_NAME, REVIEW_NAME})
REQUIRED_EXTRACTOR_CHECKS = frozenset(
    {
        "input policy",
        "source extraction",
        "preliminary draft validation",
        "source bundle verification and review card",
        "safety boundary",
    }
)
REPORT_START = "MIXED_SOURCE_CASE_EXTRACTION_REPORT_START"
REPORT_END = "MIXED_SOURCE_CASE_EXTRACTION_REPORT_END"


class CaseExtractionError(RuntimeError):
    """Expected fail-closed case extraction failure."""


@dataclass
class CaseExtractionResult:
    case_id: str
    output_dir: Path
    status: str = "FAIL"
    output_created: bool = False
    source_mode: str = "none"
    created_files: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)


ExtractorFunction = Callable[[Path | None, Path | None, Path], Any]
RenameFunction = Callable[[Path, Path], None]
UuidFunction = Callable[[], Any]
OwnerMkdirFunction = Callable[[Path], None]
CleanupFunction = Callable[[Path], str | None]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract one checked Phase 2.32 bundle directly to the canonical "
            "production_ai_cases directory for an explicit Case ID."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--project-pdf", type=Path)
    parser.add_argument("--spec-workbook", type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def valid_case_id(value: str) -> bool:
    return len(value) <= MAX_CASE_ID_LENGTH and CASE_ID_RE.fullmatch(value) is not None


def resolve_case_directory(case_id: str, canonical_root: Path) -> tuple[Path, Path]:
    if not valid_case_id(case_id):
        raise CaseExtractionError(
            "case_id must match CASE-[A-Z0-9]+ segments separated by single "
            "hyphens and be at most 128 characters"
        )
    root = resolved(canonical_root)
    if not root.is_dir():
        raise CaseExtractionError(f"canonical root does not exist: {root}")
    case_dir = resolved(root / case_id)
    if case_dir.parent != root or case_dir.name != case_id:
        raise CaseExtractionError("Case ID does not resolve to an exact root child")
    return root, case_dir


def source_mode(project_pdf: Path | None, spec_workbook: Path | None) -> str:
    if project_pdf is not None and spec_workbook is not None:
        return "pdf_and_workbook"
    if project_pdf is not None:
        return "pdf_only"
    if spec_workbook is not None:
        return "workbook_only"
    return "none"


def validate_source(
    path: Path,
    *,
    label: str,
    allowed_suffixes: frozenset[str] | set[str],
    case_dir: Path,
) -> Path:
    source = resolved(path)
    if not source.exists():
        raise CaseExtractionError(f"{label} does not exist: {source}")
    if not source.is_file():
        raise CaseExtractionError(f"{label} must be a regular file: {source}")
    if source.suffix.casefold() not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise CaseExtractionError(f"{label} extension must be one of: {allowed}")
    if source.is_relative_to(case_dir):
        raise CaseExtractionError(f"{label} must be outside the future Case directory")
    return source


def validate_sources(
    project_pdf: Path | None,
    spec_workbook: Path | None,
    *,
    case_dir: Path,
) -> tuple[Path | None, Path | None]:
    if project_pdf is None and spec_workbook is None:
        raise CaseExtractionError("at least one source must be provided")
    if (
        project_pdf is not None
        and spec_workbook is not None
        and resolved(project_pdf) == resolved(spec_workbook)
    ):
        raise CaseExtractionError("PDF and workbook must be different source paths")
    pdf = (
        validate_source(
            project_pdf,
            label="project PDF",
            allowed_suffixes={".pdf"},
            case_dir=case_dir,
        )
        if project_pdf is not None
        else None
    )
    workbook = (
        validate_source(
            spec_workbook,
            label="spec workbook",
            allowed_suffixes=SUPPORTED_WORKBOOK_SUFFIXES,
            case_dir=case_dir,
        )
        if spec_workbook is not None
        else None
    )
    return pdf, workbook


def is_reparse_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def path_entry_exists(path: Path) -> bool:
    return os.path.lexists(path)


def validate_staging_outputs(staging: Path, extractor_result: Any) -> list[str]:
    if getattr(extractor_result, "status", None) != "PASS":
        details = "; ".join(getattr(extractor_result, "red_flags", [])[:5])
        raise CaseExtractionError(f"existing extractor failed: {details or 'unknown'}")
    checks = getattr(extractor_result, "checks", {})
    if not isinstance(checks, Mapping) or any(
        checks.get(name) != "pass" for name in REQUIRED_EXTRACTOR_CHECKS
    ):
        raise CaseExtractionError(
            "existing extractor PASS did not guarantee required validation checks"
        )
    returned_output = getattr(extractor_result, "output_dir", None)
    if not isinstance(returned_output, (str, os.PathLike)):
        raise CaseExtractionError("existing extractor returned no valid output path")
    if resolved(Path(returned_output)) != staging:
        raise CaseExtractionError(
            "existing extractor returned an unexpected output path"
        )
    if not staging.is_dir() or is_reparse_like(staging):
        raise CaseExtractionError("staging output is missing or reparse-point-like")
    entries = list(staging.iterdir())
    names = {entry.name for entry in entries}
    if names != EXPECTED_FILES:
        missing = sorted(EXPECTED_FILES - names)
        extra = sorted(names - EXPECTED_FILES)
        raise CaseExtractionError(
            f"staging file set mismatch: missing={missing}; extra={extra}"
        )
    for entry in entries:
        if is_reparse_like(entry) or not entry.is_file():
            raise CaseExtractionError(
                f"staging entry must be a regular non-reparse file: {entry.name}"
            )
        if entry.stat().st_size <= 0:
            raise CaseExtractionError(f"staging file must be non-empty: {entry.name}")
    return sorted(names)


def create_owner_directory(owner: Path) -> None:
    owner.mkdir()


def cleanup_owned_container(owner: Path) -> str | None:
    if not path_entry_exists(owner):
        return None
    try:
        shutil.rmtree(owner)
    except OSError as error:
        return f"{error}"
    if path_entry_exists(owner):
        return "owned container still exists after cleanup"
    return None


def remove_empty_owner_after_publication(owner: Path) -> str | None:
    try:
        entries = [entry.name for entry in owner.iterdir()]
    except OSError as error:
        return f"could not inspect published owner container: {error}"
    if entries:
        return f"unexpected entries remain after publication: {sorted(entries)}"
    try:
        owner.rmdir()
    except OSError as error:
        return f"could not remove empty published owner container: {error}"
    if path_entry_exists(owner):
        return "published owner container still exists after cleanup"
    return None


def add_red_flag(result: CaseExtractionResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def run_case_extraction(
    *,
    case_id: str,
    project_pdf: Path | None,
    spec_workbook: Path | None,
    canonical_root: Path | None = None,
    extractor_fn: ExtractorFunction = run_operator,
    rename_fn: RenameFunction = os.rename,
    uuid_fn: UuidFunction = uuid.uuid4,
    owner_mkdir_fn: OwnerMkdirFunction = create_owner_directory,
    cleanup_fn: CleanupFunction = cleanup_owned_container,
    post_publish_cleanup_fn: CleanupFunction = remove_empty_owner_after_publication,
) -> CaseExtractionResult:
    root_value = CANONICAL_ROOT if canonical_root is None else canonical_root
    unresolved_root = resolved(root_value)
    result = CaseExtractionResult(
        case_id=case_id,
        output_dir=resolved(unresolved_root / case_id),
        source_mode=source_mode(project_pdf, spec_workbook),
    )
    owner: Path | None = None
    bundle: Path | None = None
    owner_owned = False
    published = False
    try:
        root, case_dir = resolve_case_directory(case_id, root_value)
        result.output_dir = case_dir
        pdf, workbook = validate_sources(
            project_pdf,
            spec_workbook,
            case_dir=case_dir,
        )
        if path_entry_exists(case_dir):
            raise CaseExtractionError(
                "final Case directory already exists; overwrite is forbidden: "
                f"{case_dir}"
            )
        owner = root / f".{case_id}-wrapper-{uuid_fn().hex}"
        if owner.parent != root:
            raise CaseExtractionError(f"unsafe owner container path: {owner}")
        if path_entry_exists(owner):
            raise CaseExtractionError(
                "selected owner container already exists and was preserved; "
                f"manual inspection required at {owner}"
            )
        try:
            owner_mkdir_fn(owner)
        except FileExistsError as error:
            raise CaseExtractionError(
                "owner container appeared concurrently and was preserved; "
                f"manual inspection required at {owner}: {error}"
            ) from error
        owner_owned = True
        bundle = owner / "bundle"
        if bundle.parent != owner or path_entry_exists(bundle):
            raise CaseExtractionError(f"unsafe or existing owned bundle path: {bundle}")
        for label, source in (("project PDF", pdf), ("spec workbook", workbook)):
            if source is not None and source.is_relative_to(owner):
                raise CaseExtractionError(f"{label} must be outside owned staging")

        extractor_result = extractor_fn(pdf, workbook, bundle)
        created_files = validate_staging_outputs(bundle, extractor_result)
        if path_entry_exists(case_dir):
            raise CaseExtractionError(
                "final Case directory appeared before publication; overwrite is "
                "forbidden and manual inspection is required"
            )
        rename_fn(bundle, case_dir)
        published = True
        result.created_files = created_files
        result.output_created = True
        try:
            cleanup_error = post_publish_cleanup_fn(owner)
        except Exception as error:
            cleanup_error = f"owner cleanup raised an exception: {error}"
        if cleanup_error is not None:
            add_red_flag(
                result,
                "published final Case was preserved, but owner cleanup requires "
                f"manual inspection at {owner}: {cleanup_error}",
            )
            return result
        result.status = "PASS"
        return result
    except Exception as error:
        add_red_flag(result, str(error))
        if owner is not None and owner_owned and not published:
            cleanup_error = cleanup_fn(owner)
            if cleanup_error is not None:
                add_red_flag(
                    result,
                    "owned staging cleanup failed; manual inspection required at "
                    f"{owner}: {cleanup_error}",
                )
        elif owner is not None and not owner_owned and path_entry_exists(owner):
            add_red_flag(
                result,
                "owner container ownership was not established; path was "
                f"preserved for manual inspection at {owner}",
            )
        if path_entry_exists(result.output_dir) and not published:
            add_red_flag(
                result,
                "final Case directory exists after failed publication; it was "
                "preserved and requires manual inspection",
            )
        return result


def format_report(result: CaseExtractionResult) -> str:
    return "\n".join(
        [
            REPORT_START,
            "",
            "Status:",
            result.status,
            "",
            "Case ID:",
            result.case_id,
            "",
            "Source mode:",
            result.source_mode,
            "",
            "Output:",
            str(result.output_dir),
            "",
            "Output created:",
            "yes" if result.output_created else "no",
            "",
            "Created files:",
            *(result.created_files or ["none"]),
            "",
            "Red flags:",
            *(result.red_flags or ["none"]),
            "",
            "Human Approval:",
            (
                "preliminary extraction only; Igor review is required; no "
                "confirmed composition, calculator input, calculator, price, "
                "schedule, CSV/XLSX/quote, client send, procurement, reserve, "
                "prepayment, workshop, envelope, consumer execution, or "
                "production approval"
            ),
            "",
            REPORT_END,
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_case_extraction(
        case_id=args.case_id,
        project_pdf=args.project_pdf,
        spec_workbook=args.spec_workbook,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
