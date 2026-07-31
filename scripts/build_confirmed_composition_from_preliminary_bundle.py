"""Build one Igor-confirmed composition from a canonical preliminary bundle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
CANONICAL_ROOT = Path.home() / "Documents" / "production_ai_cases"
MANIFEST_NAME = "source-bundle-manifest.txt"
DRAFT_NAME = "preliminary-composition-draft.json"
REVIEW_NAME = "igor-review-card.md"
OUTPUT_DIR_NAME = "confirmed"
ARTIFACT_NAME = "confirmed-composition-artifact.json"
DECISIONS_NAME = "igor-composition-decisions.json"
RECEIPT_NAME = "igor-composition-decisions.md"
APPROVAL_PHRASE = "CONFIRM TECHNICAL COMPOSITION"
APPLIED_BUNDLE_SCHEMA = "component_replay_applied_bundle.v0.23"
CONFIRMED_V02_SCHEMA = "confirmed_composition_artifact.v0.2"
APPROVAL_AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
DECISIONS_INPUT_SCHEMA = "igor_composition_decisions_input.v0.1"
CASE_ID_RE = re.compile(r"CASE-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
MAX_CASE_ID_LENGTH = 128
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
BLOCKED_SOURCE_STATUSES = {
    "unreadable",
    "image_only",
    "encrypted_or_protected",
    "corrupt",
    "manual_recovery_required",
}
INSTALL_TYPES = {
    "modular_1p",
    "modular_2p",
    "modular_3p",
    "modular_4p",
    "diff_1p_n",
    "diff_3p_4p",
    "load_switch_1p",
    "load_switch_2p",
    "load_switch_3p",
    "load_switch_4p",
    "mccb_up_to_100a",
    "mccb_125_250a",
    "mccb_400a_plus",
}
REPORT_START = "CONFIRMED_COMPOSITION_BUILD_REPORT_START"
REPORT_END = "CONFIRMED_COMPOSITION_BUILD_REPORT_END"


class WorkflowError(RuntimeError):
    """Expected fail-closed workflow failure."""


class WorkflowCancelled(WorkflowError):
    """Explicit operator cancellation."""


@dataclass(frozen=True)
class CasePaths:
    case_id: str
    root: Path
    case_dir: Path
    manifest: Path
    draft: Path
    review: Path
    output_dir: Path


@dataclass(frozen=True)
class AppliedPaths:
    case_dir: Path
    applied_bundle: Path
    output_dir: Path


@dataclass(frozen=True)
class InputSnapshot:
    paths: CasePaths
    manifest_bytes: bytes
    draft_bytes: bytes
    review_bytes: bytes
    hashes: dict[str, str]
    draft: Mapping[str, Any]


@dataclass(frozen=True)
class AppliedInputSnapshot:
    paths: AppliedPaths
    content: bytes
    sha256: str
    data: Mapping[str, Any]
    installed_components: list[dict[str, Any]]
    reserved_meter_spaces: list[dict[str, Any]]
    coverage: dict[str, int]


@dataclass(frozen=True)
class DecisionsInputSnapshot:
    path: Path
    content: bytes
    sha256: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class AutomaticTransfer:
    source_path: str
    target_path: str
    final_value: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "target_path": self.target_path,
            "final_value": self.final_value,
        }


@dataclass(frozen=True)
class ExceptionIssue:
    issue_id: str
    kind: str
    source_path: str
    target_path: tuple[str | int, ...] | None
    message: str
    value_kind: str
    suggested_value: Any = None
    allowed_actions: tuple[str, ...] = ("correct", "cancel")
    original_value: Any = None
    classification: str | None = None
    group_fingerprint: tuple[str, ...] | None = None
    group_display: Mapping[str, Any] | None = None


@dataclass
class CompositionState:
    items: list[dict[str, Any]]
    automatic_transfers: list[AutomaticTransfer]
    issues: list[ExceptionIssue]
    preliminary_red_flags: list[dict[str, str]]
    corrected_values: list[dict[str, Any]] = field(default_factory=list)
    resolved_conflicts: list[dict[str, Any]] = field(default_factory=list)
    accepted_nontechnical_assumptions: list[dict[str, Any]] = field(
        default_factory=list
    )
    not_applicable_technical_details: list[dict[str, Any]] = field(default_factory=list)
    removed_values: list[dict[str, Any]] = field(default_factory=list)
    unresolved_issue_ids: set[str] = field(default_factory=set)
    supply_boundary: str = ""
    batch_decisions: dict[str, Any] | None = None


@dataclass
class BuildResult:
    case_id: str
    status: str = "FAIL"
    output_created: bool = False
    output_dir: Path | None = None
    red_flags: list[str] = field(default_factory=list)


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]
NowFunction = Callable[[], datetime]
ValidatorFunction = Callable[[Path], Any]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a validated confirmed composition from one canonical "
            "Phase 2.32 bundle."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--case-id")
    source_group.add_argument("--applied-bundle-json", type=Path)
    parser.add_argument("--confirmation-id", required=True)
    parser.add_argument("--approval-channel", required=True)
    parser.add_argument("--decisions-json", type=Path)
    args = parser.parse_args(argv)
    if args.applied_bundle_json is not None and args.decisions_json is not None:
        parser.error(
            "--decisions-json is preliminary-only and cannot be mixed with "
            "--applied-bundle-json"
        )
    return args


def valid_case_id(value: str) -> bool:
    return len(value) <= MAX_CASE_ID_LENGTH and CASE_ID_RE.fullmatch(value) is not None


def require_metadata(value: str, name: str) -> str:
    if not value.strip():
        raise WorkflowError(f"{name} must be non-empty")
    if len(value) > 256 or any(ord(character) < 32 for character in value):
        raise WorkflowError(f"{name} contains invalid characters")
    return value


def resolve_case_paths(
    case_id: str,
    *,
    canonical_root: Path = CANONICAL_ROOT,
) -> CasePaths:
    if not valid_case_id(case_id):
        raise WorkflowError(
            "case_id must match CASE-[A-Z0-9]+ segments separated by single hyphens"
        )
    root = canonical_root.expanduser().resolve(strict=False)
    case_dir = (root / case_id).resolve(strict=False)
    if case_dir.parent != root or case_dir.name != case_id:
        raise WorkflowError("Case ID does not match the canonical case directory")
    return CasePaths(
        case_id=case_id,
        root=root,
        case_dir=case_dir,
        manifest=case_dir / MANIFEST_NAME,
        draft=case_dir / DRAFT_NAME,
        review=case_dir / REVIEW_NAME,
        output_dir=case_dir / OUTPUT_DIR_NAME,
    )


def validate_case_directory(paths: CasePaths) -> None:
    if not paths.root.is_dir():
        raise WorkflowError("canonical production_ai_cases root does not exist")
    if paths.case_dir.parent != paths.root or paths.case_dir.name != paths.case_id:
        raise WorkflowError("Case ID does not match the canonical case directory")
    if not paths.case_dir.is_dir():
        raise WorkflowError("canonical Case ID directory does not exist")
    if paths.output_dir.exists():
        raise WorkflowError(
            "confirmed directory already exists; overwrite is forbidden"
        )
    for path in (paths.manifest, paths.draft, paths.review):
        if path.parent != paths.case_dir:
            raise WorkflowError("input is outside the canonical Case ID directory")
        if not path.is_file():
            raise WorkflowError(f"missing canonical input: {path.name}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_exact_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise WorkflowError(f"could not read canonical input: {path.name}") from exc


def parse_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkflowError(f"{label} must be valid UTF-8") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{label} is malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise WorkflowError(f"{label} root must be an object")
    return cast(Mapping[str, Any], value)


class DuplicateJsonKeyError(ValueError):
    """A strict JSON object contains the same key more than once."""


def strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise DuplicateJsonKeyError(f"duplicate JSON field: {key}")
        value[key] = child
    return value


def parse_strict_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkflowError(f"{label} must be valid UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=strict_object_pairs)
    except DuplicateJsonKeyError as exc:
        raise WorkflowError(f"{label} contains {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{label} is malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise WorkflowError(f"{label} root must be an object")
    return cast(Mapping[str, Any], value)


def exact_object(value: Any, label: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkflowError(f"{label} must be an object")
    actual = {str(key) for key in value}
    missing = sorted(fields - actual)
    unknown = sorted(actual - fields)
    if missing:
        raise WorkflowError(f"{label} missing required fields: {', '.join(missing)}")
    if unknown:
        raise WorkflowError(f"{label} has unknown fields: {', '.join(unknown)}")
    return cast(Mapping[str, Any], value)


def exact_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorkflowError(f"{label} must be a list")
    return value


def strict_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{label} must be a non-empty string")
    return value


def positive_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise WorkflowError(f"{label} must be a positive number")
    return cast(int | float, value)


def unique_strings(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    raw = exact_list(value, label)
    result = [strict_nonempty_string(child, f"{label}[]") for child in raw]
    if not allow_empty and not result:
        raise WorkflowError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise WorkflowError(f"{label} contains duplicate values")
    return result


def load_decisions_input(path: Path) -> DecisionsInputSnapshot:
    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise WorkflowError("decisions JSON does not exist or is not a file")
    try:
        content = resolved.read_bytes()
    except OSError as exc:
        raise WorkflowError("could not read decisions JSON") from exc
    return DecisionsInputSnapshot(
        path=resolved,
        content=content,
        sha256=sha256_bytes(content),
        data=parse_strict_json_object(content, "decisions JSON"),
    )


def assert_decisions_unchanged(snapshot: DecisionsInputSnapshot) -> None:
    try:
        current = snapshot.path.read_bytes()
    except OSError as exc:
        raise WorkflowError(
            "could not re-read decisions JSON after Human Approval"
        ) from exc
    if sha256_bytes(current) != snapshot.sha256:
        raise WorkflowError("decisions JSON hash drift detected after Human Approval")


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise WorkflowError(f"could not load required module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_existing_contracts(paths: CasePaths) -> None:
    preliminary = load_module(
        "confirmed_builder_preliminary_validator",
        SCRIPTS_DIR / "validate_preliminary_composition_draft.py",
    )
    validation = preliminary.validate_preliminary_composition_draft(paths.draft)
    if validation.status != "PASS":
        details = "; ".join(validation.red_flags[:5])
        raise WorkflowError(f"preliminary validator failed: {details}")

    verifier = load_module(
        "confirmed_builder_source_bundle_verifier",
        SCRIPTS_DIR / "verify_preliminary_composition_source_bundle.py",
    )
    verification = verifier.verify_source_bundle(paths.manifest, paths.draft)
    if verification.status != "PASS":
        details = "; ".join(verification.red_flags[:5])
        raise WorkflowError(f"source-bundle verifier failed: {details}")


def check_review_card_consistency(
    review_bytes: bytes,
    draft: Mapping[str, Any],
) -> None:
    try:
        review = review_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkflowError("igor-review-card.md must be valid UTF-8") from exc
    source = as_mapping(draft.get("source"))
    required_markers = (
        f"- draft_id: {draft.get('draft_id')}",
        f"- raw_input_sha256: {source.get('raw_input_sha256')}",
    )
    for marker in required_markers:
        if marker not in review:
            raise WorkflowError(
                "review card does not contain the expected draft identity markers"
            )


def load_snapshot(paths: CasePaths) -> InputSnapshot:
    validate_case_directory(paths)
    manifest_bytes = read_exact_bytes(paths.manifest)
    draft_bytes = read_exact_bytes(paths.draft)
    review_bytes = read_exact_bytes(paths.review)
    draft = parse_json_object(draft_bytes, DRAFT_NAME)
    validate_existing_contracts(paths)
    check_review_card_consistency(review_bytes, draft)
    return InputSnapshot(
        paths=paths,
        manifest_bytes=manifest_bytes,
        draft_bytes=draft_bytes,
        review_bytes=review_bytes,
        hashes={
            MANIFEST_NAME: sha256_bytes(manifest_bytes),
            DRAFT_NAME: sha256_bytes(draft_bytes),
            REVIEW_NAME: sha256_bytes(review_bytes),
        },
        draft=draft,
    )


def assert_snapshot_unchanged(snapshot: InputSnapshot) -> None:
    current = {
        MANIFEST_NAME: sha256_bytes(read_exact_bytes(snapshot.paths.manifest)),
        DRAFT_NAME: sha256_bytes(read_exact_bytes(snapshot.paths.draft)),
        REVIEW_NAME: sha256_bytes(read_exact_bytes(snapshot.paths.review)),
    }
    if current != snapshot.hashes:
        raise WorkflowError("input hash drift detected after Human Approval")


def resolve_applied_paths(applied_bundle_json: Path) -> AppliedPaths:
    applied_path = applied_bundle_json.expanduser().resolve(strict=False)
    project_root = PROJECT_ROOT.resolve(strict=False)
    if applied_path.is_relative_to(project_root):
        raise WorkflowError("applied bundle JSON must be outside the Git project")
    if not applied_path.is_file():
        raise WorkflowError("applied bundle JSON does not exist")
    case_dir = applied_path.parent
    output_dir = case_dir / OUTPUT_DIR_NAME
    if output_dir.exists():
        raise WorkflowError(
            "confirmed directory already exists; overwrite is forbidden"
        )
    return AppliedPaths(
        case_dir=case_dir,
        applied_bundle=applied_path,
        output_dir=output_dir,
    )


def load_applied_snapshot(applied_bundle_json: Path) -> AppliedInputSnapshot:
    paths = resolve_applied_paths(applied_bundle_json)
    module = load_module(
        "confirmed_builder_applied_source_validator",
        SCRIPTS_DIR / "validate_confirmed_composition_artifact.py",
    )
    try:
        validated = module.load_applied_bundle_snapshot(paths.applied_bundle)
    except Exception as exc:
        raise WorkflowError(f"applied bundle validation failed: {exc}") from exc
    return AppliedInputSnapshot(
        paths=paths,
        content=validated.content,
        sha256=validated.sha256,
        data=validated.data,
        installed_components=copy.deepcopy(validated.installed_components),
        reserved_meter_spaces=copy.deepcopy(validated.reserved_meter_spaces),
        coverage=dict(validated.coverage),
    )


def assert_applied_snapshot_unchanged(snapshot: AppliedInputSnapshot) -> None:
    current = sha256_bytes(read_exact_bytes(snapshot.paths.applied_bundle))
    if current != snapshot.sha256:
        raise WorkflowError("applied bundle hash drift detected after Human Approval")


def as_mapping(value: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value if isinstance(value, Mapping) else {})


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def nonempty(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def unresolved(value: Any) -> bool:
    return isinstance(value, str) and "unresolved" in value.casefold()


def provenance_available(value: Mapping[str, Any]) -> bool:
    provenance = value.get("provenance")
    return isinstance(provenance, list) and bool(provenance)


def collect_preliminary_red_flags(
    draft: Mapping[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key == "red_flags" and isinstance(child, list):
                    for index, red_flag in enumerate(child):
                        if isinstance(red_flag, str) and red_flag.strip():
                            findings.append(
                                {
                                    "source_path": f"{child_path}[{index}]",
                                    "red_flag": red_flag,
                                }
                            )
                else:
                    visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(draft, "")
    return findings


def validate_identifier_integrity(draft: Mapping[str, Any]) -> None:
    item_ids: set[str] = set()
    component_ids: set[str] = set()
    for item_index, item_value in enumerate(as_list(draft.get("items"))):
        item = as_mapping(item_value)
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise WorkflowError(f"items[{item_index}].item_id must be non-empty")
        if item_id in item_ids:
            raise WorkflowError(f"duplicate item_id is forbidden: {item_id}")
        item_ids.add(item_id)
        for component_index, component_value in enumerate(
            as_list(item.get("components"))
        ):
            component = as_mapping(component_value)
            component_id = component.get("component_id")
            if not isinstance(component_id, str) or not component_id.strip():
                raise WorkflowError(
                    f"items[{item_index}].components[{component_index}]."
                    "component_id must be non-empty"
                )
            if component_id in component_ids:
                raise WorkflowError(
                    f"duplicate component_id is forbidden: {component_id}"
                )
            component_ids.add(component_id)


def validate_source_metadata_integrity(draft: Mapping[str, Any]) -> None:
    source = as_mapping(draft.get("source"))
    source_files_value = source.get("source_files")
    if source_files_value is None:
        return
    metadata = source_metadata_by_name(draft)
    for file_name, entry in metadata.items():
        if not nonempty(entry.get("status")):
            raise WorkflowError(
                f"source metadata status is missing for source.source_files: "
                f"{file_name}"
            )

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            provenance = value.get("provenance")
            if isinstance(provenance, list):
                for index, provenance_value in enumerate(provenance):
                    entry = as_mapping(provenance_value)
                    file_name = entry.get("source_file")
                    source_path = f"{path}.provenance[{index}]"
                    if not isinstance(file_name, str) or file_name not in metadata:
                        raise WorkflowError(
                            "provenance source_file has no source metadata: "
                            f"{source_path}"
                        )
                    page_number = entry.get("page")
                    if page_number is not None:
                        matching_pages = [
                            as_mapping(page)
                            for page in as_list(metadata[file_name].get("pages"))
                            if as_mapping(page).get("page") == page_number
                        ]
                        if not matching_pages or not nonempty(
                            matching_pages[0].get("status")
                        ):
                            raise WorkflowError(
                                "provenance page has no source metadata status: "
                                f"{source_path}"
                            )
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(draft, "")


def source_is_blocked(
    value: Mapping[str, Any],
    source_metadata: Mapping[str, Mapping[str, Any]],
) -> bool:
    if not source_metadata:
        return True
    for entry_value in as_list(value.get("provenance")):
        entry = as_mapping(entry_value)
        file_name = entry.get("source_file")
        metadata = source_metadata.get(str(file_name))
        if metadata is None or not nonempty(metadata.get("status")):
            return True
        if metadata.get("status") in BLOCKED_SOURCE_STATUSES:
            return True
        page_number = entry.get("page")
        matching_page_found = page_number is None
        for page_value in as_list(metadata.get("pages")):
            page = as_mapping(page_value)
            if page.get("page") == page_number:
                matching_page_found = True
                if not nonempty(page.get("status")):
                    return True
                if page.get("status") in BLOCKED_SOURCE_STATUSES:
                    return True
        if not matching_page_found:
            return True
    return False


def conflict_for(value: Mapping[str, Any], field_names: set[str]) -> bool:
    for conflict_value in as_list(value.get("conflicts")):
        conflict = as_mapping(conflict_value)
        field = str(conflict.get("field", "")).casefold()
        conflict_type = str(conflict.get("type", "")).casefold()
        if any(name in field or name in conflict_type for name in field_names):
            return True
    return False


def missing_field(value: Mapping[str, Any], field_names: set[str]) -> bool:
    missing = {str(item).casefold() for item in as_list(value.get("missing_fields"))}
    return bool(missing.intersection(field_names))


def unmapped_conflicts(
    value: Mapping[str, Any],
    mapped_terms: set[str],
) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for conflict_value in as_list(value.get("conflicts")):
        conflict = as_mapping(conflict_value)
        text = (
            str(conflict.get("field", "")) + " " + str(conflict.get("type", ""))
        ).casefold()
        if not any(term in text for term in mapped_terms):
            result.append(conflict)
    return result


def reliable_value(
    owner: Mapping[str, Any],
    value: Any,
    *,
    field_names: set[str],
    source_metadata: Mapping[str, Mapping[str, Any]],
) -> bool:
    return (
        nonempty(value)
        and not unresolved(value)
        and provenance_available(owner)
        and not source_is_blocked(owner, source_metadata)
        and not conflict_for(owner, field_names)
        and not missing_field(owner, field_names)
    )


def source_metadata_by_name(draft: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    source = as_mapping(draft.get("source"))
    result: dict[str, Mapping[str, Any]] = {}
    for value in as_list(source.get("source_files")):
        metadata = as_mapping(value)
        name = metadata.get("file_name")
        if isinstance(name, str):
            result[name] = metadata
    return result


def add_transfer(
    transfers: list[AutomaticTransfer],
    source_path: str,
    target_path: str,
    value: Any,
) -> Any:
    transfers.append(AutomaticTransfer(source_path, target_path, value))
    return value


def mandatory_value(
    *,
    owner: Mapping[str, Any],
    value: Any,
    source_path: str,
    target_path_text: str,
    target_path: tuple[str | int, ...],
    field_names: set[str],
    value_kind: str,
    source_metadata: Mapping[str, Mapping[str, Any]],
    transfers: list[AutomaticTransfer],
    issues: list[ExceptionIssue],
) -> Any:
    if reliable_value(
        owner,
        value,
        field_names=field_names,
        source_metadata=source_metadata,
    ):
        return add_transfer(transfers, source_path, target_path_text, value)
    suggested = value if nonempty(value) and not unresolved(value) else None
    has_conflict = conflict_for(owner, field_names)
    issues.append(
        ExceptionIssue(
            issue_id=f"ISSUE-{len(issues) + 1:03d}",
            kind="conflict" if has_conflict else "required_value",
            source_path=source_path,
            target_path=target_path,
            message=f"Resolve required confirmed field {target_path_text}",
            value_kind=value_kind,
            suggested_value=suggested,
            allowed_actions=("correct", "cancel"),
            original_value=(as_list(owner.get("conflicts")) if has_conflict else value),
        )
    )
    return None


def detail_is_represented(component: Mapping[str, Any], detail: Any) -> bool:
    if not nonempty(detail):
        return True
    combined = " ".join(
        str(component.get(name, ""))
        for name in ("component_code_guess", "component_label_guess")
    ).casefold()
    return str(detail).casefold() in combined


def classify_assumption(value: str) -> str:
    marker = value.strip().casefold()
    if marker.startswith("nontechnical:") or marker.startswith("[nontechnical]"):
        return "nontechnical"
    return "technical"


def install_group_fingerprint(
    component: Mapping[str, Any],
) -> tuple[str, ...] | None:
    fields = (
        "component_code_guess",
        "component_label_guess",
        "model_guess",
        "brand_guess",
        "rating_guess",
        "unit_guess",
        "note_guess",
        "install_type_guess",
    )
    values = tuple(str(component.get(field, "")).strip() for field in fields)
    if not all(values):
        return None
    return values


def classify_composition(draft: Mapping[str, Any]) -> CompositionState:
    metadata = source_metadata_by_name(draft)
    transfers: list[AutomaticTransfer] = []
    issues: list[ExceptionIssue] = []
    items: list[dict[str, Any]] = []

    for item_index, item_value in enumerate(as_list(draft.get("items"))):
        item = as_mapping(item_value)
        source_prefix = f"items[{item_index}]"
        target_prefix = f"items[{item_index}]"
        confirmed_item: dict[str, Any] = {
            "item_id": add_transfer(
                transfers,
                f"{source_prefix}.item_id",
                f"{target_prefix}.item_id",
                item.get("item_id"),
            ),
            "product_name": None,
            "product_type": add_transfer(
                transfers,
                "extractor scope",
                f"{target_prefix}.product_type",
                "switchboard",
            ),
            "quantity": None,
            "cabinet": {"cabinet_code": None, "cabinet_label": None},
            "components": [],
            "confirmation_note": "",
        }
        items.append(confirmed_item)
        confirmed_item["product_name"] = mandatory_value(
            owner=item,
            value=item.get("product_name_guess"),
            source_path=f"{source_prefix}.product_name_guess",
            target_path_text=f"{target_prefix}.product_name",
            target_path=("items", item_index, "product_name"),
            field_names={"product_name_guess", "product_name", "title", "name"},
            value_kind="string",
            source_metadata=metadata,
            transfers=transfers,
            issues=issues,
        )
        confirmed_item["quantity"] = mandatory_value(
            owner=item,
            value=item.get("quantity_guess"),
            source_path=f"{source_prefix}.quantity_guess",
            target_path_text=f"{target_prefix}.quantity",
            target_path=("items", item_index, "quantity"),
            field_names={"quantity_guess", "quantity"},
            value_kind="positive_integer",
            source_metadata=metadata,
            transfers=transfers,
            issues=issues,
        )
        cabinet = as_mapping(item.get("cabinet_guess"))
        suggested_cabinet = None
        if nonempty(cabinet.get("code_guess")) and nonempty(cabinet.get("label_guess")):
            suggested_cabinet = {
                "cabinet_code": cabinet.get("code_guess"),
                "cabinet_label": cabinet.get("label_guess"),
            }
        issues.append(
            ExceptionIssue(
                issue_id=f"ISSUE-{len(issues) + 1:03d}",
                kind="cabinet",
                source_path=f"{source_prefix}.cabinet_guess",
                target_path=("items", item_index, "cabinet"),
                message=(
                    f"Resolve cabinet code and label for {target_prefix} as "
                    "'code | label'; current cabinet contract has no provenance field"
                ),
                value_kind="cabinet",
                suggested_value=suggested_cabinet,
                allowed_actions=(
                    ("accept", "correct", "cancel")
                    if suggested_cabinet is not None
                    else ("correct", "cancel")
                ),
                original_value=dict(cabinet),
            )
        )

        for component_index, component_value in enumerate(
            as_list(item.get("components"))
        ):
            component = as_mapping(component_value)
            component_source = f"{source_prefix}.components[{component_index}]"
            component_target = f"{target_prefix}.components[{component_index}]"
            confirmed_component: dict[str, Any] = {
                "component_id": add_transfer(
                    transfers,
                    f"{component_source}.component_id",
                    f"{component_target}.component_id",
                    component.get("component_id"),
                ),
                "component_code": None,
                "component_label": None,
                "quantity": None,
                "install_type": None,
            }
            cast(list[dict[str, Any]], confirmed_item["components"]).append(
                confirmed_component
            )
            confirmed_component["component_code"] = mandatory_value(
                owner=component,
                value=component.get("component_code_guess")
                or component.get("model_guess"),
                source_path=f"{component_source}.component_code_guess",
                target_path_text=f"{component_target}.component_code",
                target_path=(
                    "items",
                    item_index,
                    "components",
                    component_index,
                    "component_code",
                ),
                field_names={"component_code_guess", "model_guess", "model", "code"},
                value_kind="string",
                source_metadata=metadata,
                transfers=transfers,
                issues=issues,
            )
            confirmed_component["component_label"] = mandatory_value(
                owner=component,
                value=component.get("component_label_guess"),
                source_path=f"{component_source}.component_label_guess",
                target_path_text=f"{component_target}.component_label",
                target_path=(
                    "items",
                    item_index,
                    "components",
                    component_index,
                    "component_label",
                ),
                field_names={
                    "component_label_guess",
                    "label",
                    "name",
                    "brand",
                    "rating",
                    "series",
                },
                value_kind="string",
                source_metadata=metadata,
                transfers=transfers,
                issues=issues,
            )
            confirmed_component["quantity"] = mandatory_value(
                owner=component,
                value=component.get("quantity_guess"),
                source_path=f"{component_source}.quantity_guess",
                target_path_text=f"{component_target}.quantity",
                target_path=(
                    "items",
                    item_index,
                    "components",
                    component_index,
                    "quantity",
                ),
                field_names={"quantity_guess", "quantity"},
                value_kind="positive_number",
                source_metadata=metadata,
                transfers=transfers,
                issues=issues,
            )
            install_type = component.get("install_type_guess")
            install_reliable = install_type in INSTALL_TYPES and reliable_value(
                component,
                install_type,
                field_names={"install_type_guess", "install_type"},
                source_metadata=metadata,
            )
            if install_reliable:
                confirmed_component["install_type"] = add_transfer(
                    transfers,
                    f"{component_source}.install_type_guess",
                    f"{component_target}.install_type",
                    install_type,
                )
            else:
                issues.append(
                    ExceptionIssue(
                        issue_id=f"ISSUE-{len(issues) + 1:03d}",
                        kind="manual_review_required",
                        source_path=f"{component_source}.install_type_guess",
                        target_path=(
                            "items",
                            item_index,
                            "components",
                            component_index,
                            "install_type",
                        ),
                        message=(
                            f"Choose confirmed install_type for {component_target}; "
                            "manual_review_required is forbidden"
                        ),
                        value_kind="install_type",
                        suggested_value=None,
                        allowed_actions=("correct", "cancel"),
                        original_value=install_type,
                        group_fingerprint=install_group_fingerprint(component),
                        group_display={
                            "item_id": item.get("item_id"),
                            "component_id": component.get("component_id"),
                            "code": component.get("component_code_guess")
                            or component.get("model_guess"),
                            "label": component.get("component_label_guess"),
                            "rating": component.get("rating_guess"),
                            "quantity": component.get("quantity_guess"),
                        },
                    )
                )

            context = {
                "item_id": item.get("item_id"),
                "component_id": component.get("component_id"),
                "brand": component.get("brand_guess"),
                "model": component.get("model_guess"),
                "rating": component.get("rating_guess"),
                "unit": component.get("unit_guess"),
                "note": component.get("note_guess"),
            }
            missing_technical = {
                str(value).casefold()
                for value in as_list(component.get("missing_fields"))
            }.intersection(
                {
                    "brand_guess",
                    "model_guess",
                    "rating_guess",
                    "unit_guess",
                    "note_guess",
                }
            )
            unrepresented = {
                key: value
                for key, value in context.items()
                if key in {"brand", "model", "rating", "note", "unit"}
                and nonempty(value)
                and not detail_is_represented(component, value)
            }
            if unrepresented or missing_technical:
                issues.append(
                    ExceptionIssue(
                        issue_id=f"ISSUE-{len(issues) + 1:03d}",
                        kind="technical_details",
                        source_path=component_source,
                        target_path=(
                            "items",
                            item_index,
                            "components",
                            component_index,
                            "component_label",
                        ),
                        message=(
                            "Technical details are missing or not represented "
                            "unambiguously in component_code/component_label: "
                            f"values={unrepresented}, "
                            f"missing={sorted(missing_technical)}"
                        ),
                        value_kind="string",
                        suggested_value=confirmed_component["component_label"],
                        allowed_actions=("correct", "not_applicable", "cancel"),
                        original_value={
                            "technical_context": context,
                            "unrepresented": unrepresented,
                            "missing": sorted(missing_technical),
                        },
                    )
                )

            remaining_conflicts = unmapped_conflicts(
                component,
                {
                    "code",
                    "model",
                    "label",
                    "name",
                    "brand",
                    "rating",
                    "series",
                    "quantity",
                    "install",
                },
            )
            if remaining_conflicts:
                issues.append(
                    ExceptionIssue(
                        issue_id=f"ISSUE-{len(issues) + 1:03d}",
                        kind="conflict",
                        source_path=f"{component_source}.conflicts",
                        target_path=None,
                        message=(
                            "Unsupported targetless component conflict; builder "
                            "cannot map it to a confirmed field. Cancel and resolve "
                            f"upstream: {remaining_conflicts}"
                        ),
                        value_kind="assumption",
                        suggested_value=remaining_conflicts,
                        allowed_actions=("cancel",),
                        original_value=remaining_conflicts,
                    )
                )

            assumptions = [
                value
                for value in as_list(component.get("assumptions"))
                if isinstance(value, str) and value.strip()
            ]
            if assumptions:
                for assumption_index, assumption in enumerate(assumptions):
                    classification = classify_assumption(assumption)
                    issues.append(
                        ExceptionIssue(
                            issue_id=f"ISSUE-{len(issues) + 1:03d}",
                            kind="assumption",
                            source_path=(
                                f"{component_source}.assumptions[{assumption_index}]"
                            ),
                            target_path=None,
                            message=(
                                f"Accept nontechnical assumption: {assumption}"
                                if classification == "nontechnical"
                                else (
                                    "Technical assumption has no supported confirmed "
                                    "target. Cancel and resolve upstream: "
                                    f"{assumption}"
                                )
                            ),
                            value_kind="assumption",
                            suggested_value=assumption,
                            allowed_actions=(
                                ("accept", "cancel")
                                if classification == "nontechnical"
                                else ("cancel",)
                            ),
                            original_value=assumption,
                            classification=classification,
                        )
                    )

        assumptions = [
            value
            for value in as_list(item.get("assumptions"))
            if isinstance(value, str) and value.strip()
        ]
        if assumptions:
            for assumption_index, assumption in enumerate(assumptions):
                classification = classify_assumption(assumption)
                issues.append(
                    ExceptionIssue(
                        issue_id=f"ISSUE-{len(issues) + 1:03d}",
                        kind="assumption",
                        source_path=f"{source_prefix}.assumptions[{assumption_index}]",
                        target_path=None,
                        message=(
                            f"Accept nontechnical assumption: {assumption}"
                            if classification == "nontechnical"
                            else (
                                "Technical assumption has no supported confirmed "
                                "target. Cancel and resolve upstream: "
                                f"{assumption}"
                            )
                        ),
                        value_kind="assumption",
                        suggested_value=assumption,
                        allowed_actions=(
                            ("accept", "cancel")
                            if classification == "nontechnical"
                            else ("cancel",)
                        ),
                        original_value=assumption,
                        classification=classification,
                    )
                )

        remaining_item_conflicts = unmapped_conflicts(
            item,
            {
                "product",
                "name",
                "title",
                "quantity",
                "cabinet",
                "enclosure",
            },
        )
        if remaining_item_conflicts:
            issues.append(
                ExceptionIssue(
                    issue_id=f"ISSUE-{len(issues) + 1:03d}",
                    kind="conflict",
                    source_path=f"{source_prefix}.conflicts",
                    target_path=None,
                    message=(
                        "Unsupported targetless item conflict; builder cannot map "
                        "it to a confirmed field. Cancel and resolve upstream: "
                        f"{remaining_item_conflicts}"
                    ),
                    value_kind="assumption",
                    suggested_value=remaining_item_conflicts,
                    allowed_actions=("cancel",),
                    original_value=remaining_item_conflicts,
                )
            )

    root_assumptions = [
        value
        for value in as_list(draft.get("assumptions"))
        if isinstance(value, str) and value.strip()
    ]
    if root_assumptions:
        for assumption_index, assumption in enumerate(root_assumptions):
            classification = classify_assumption(assumption)
            issues.append(
                ExceptionIssue(
                    issue_id=f"ISSUE-{len(issues) + 1:03d}",
                    kind="assumption",
                    source_path=f"assumptions[{assumption_index}]",
                    target_path=None,
                    message=(
                        f"Accept nontechnical assumption: {assumption}"
                        if classification == "nontechnical"
                        else (
                            "Technical assumption has no supported confirmed target. "
                            f"Cancel and resolve upstream: {assumption}"
                        )
                    ),
                    value_kind="assumption",
                    suggested_value=assumption,
                    allowed_actions=(
                        ("accept", "cancel")
                        if classification == "nontechnical"
                        else ("cancel",)
                    ),
                    original_value=assumption,
                    classification=classification,
                )
            )

    issues.append(
        ExceptionIssue(
            issue_id=f"ISSUE-{len(issues) + 1:03d}",
            kind="supply_boundary",
            source_path="operator decision",
            target_path=None,
            message="Enter the technical supply boundary approved by Igor",
            value_kind="supply_boundary",
            allowed_actions=("correct", "cancel"),
            original_value=None,
        )
    )
    preliminary_red_flags = collect_preliminary_red_flags(draft)
    return CompositionState(
        items=items,
        automatic_transfers=transfers,
        issues=issues,
        preliminary_red_flags=preliminary_red_flags,
        unresolved_issue_ids={issue.issue_id for issue in issues},
    )


def set_nested_value(
    root: dict[str, Any],
    path: tuple[str | int, ...],
    value: Any,
) -> None:
    current: Any = root
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


def parse_corrected_value(raw: str, kind: str) -> Any:
    value = raw.strip()
    if not value:
        raise WorkflowError("corrected value must be non-empty")
    if kind in {"string", "supply_boundary"}:
        return value
    if kind == "cabinet":
        parts = [part.strip() for part in value.split("|", maxsplit=1)]
        if len(parts) != 2 or not all(parts):
            raise WorkflowError("cabinet correction must use 'code | label'")
        return {"cabinet_code": parts[0], "cabinet_label": parts[1]}
    if kind == "positive_integer":
        try:
            parsed = int(value)
        except ValueError as exc:
            raise WorkflowError("corrected value must be a positive integer") from exc
        if parsed <= 0:
            raise WorkflowError("corrected value must be a positive integer")
        return parsed
    if kind == "positive_number":
        try:
            parsed_number = float(value)
        except ValueError as exc:
            raise WorkflowError("corrected value must be a positive number") from exc
        if parsed_number <= 0:
            raise WorkflowError("corrected value must be a positive number")
        return int(parsed_number) if parsed_number.is_integer() else parsed_number
    if kind == "install_type":
        if value not in INSTALL_TYPES:
            raise WorkflowError("corrected install_type is not allowed")
        return value
    raise WorkflowError(f"unsupported correction kind: {kind}")


def apply_interactive_decisions(
    state: CompositionState,
    *,
    input_fn: InputFunction,
    output_fn: OutputFunction,
) -> None:
    root = {"items": state.items}
    install_groups: dict[tuple[str, ...], list[ExceptionIssue]] = {}
    for candidate in state.issues:
        if (
            candidate.kind == "manual_review_required"
            and candidate.group_fingerprint is not None
        ):
            install_groups.setdefault(candidate.group_fingerprint, []).append(candidate)
    individual_groups: set[tuple[str, ...]] = set()

    def target_path_text(issue: ExceptionIssue) -> str | None:
        if issue.target_path is None:
            return None
        return ".".join(str(part) for part in issue.target_path)

    def decision(
        issue: ExceptionIssue,
        *,
        action: str,
        final_value: Any,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "issue_id": issue.issue_id,
            "issue_kind": issue.kind,
            "message": issue.message,
            "source_path": issue.source_path,
            "target_path": target_path_text(issue),
            "action": action,
            "original_value": (
                issue.original_value
                if issue.original_value is not None
                else issue.suggested_value
            ),
            "final_value": final_value,
            "reason": reason,
        }

    for issue in state.issues:
        if issue.issue_id not in state.unresolved_issue_ids:
            continue
        group = (
            install_groups.get(issue.group_fingerprint, [])
            if issue.group_fingerprint is not None
            else []
        )
        if len(group) > 1 and issue.group_fingerprint not in individual_groups:
            output_fn("\nHomogeneous install-type group:")
            for member in group:
                output_fn(
                    json.dumps(
                        dict(member.group_display or {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            group_action = (
                input_fn("Group action [apply/individual/cancel]: ").strip().casefold()
            )
            if group_action == "cancel":
                raise WorkflowCancelled("operation cancelled by operator")
            if group_action == "apply":
                corrected = parse_corrected_value(
                    input_fn("Install type for the displayed group: "),
                    "install_type",
                )
                for member in group:
                    if member.target_path is None:
                        raise WorkflowError("install group member has no target path")
                    set_nested_value(root, member.target_path, corrected)
                    state.corrected_values.append(
                        decision(
                            member,
                            action="corrected_value",
                            final_value=corrected,
                            reason="explicit homogeneous group decision",
                        )
                    )
                    state.unresolved_issue_ids.discard(member.issue_id)
                continue
            if group_action != "individual":
                raise WorkflowError("invalid install group action")
            individual_groups.add(cast(tuple[str, ...], issue.group_fingerprint))

        output_fn(f"\n{issue.issue_id}: {issue.message}")
        if issue.suggested_value is not None:
            output_fn(f"Suggested: {issue.suggested_value}")
        actions = "/".join(issue.allowed_actions)
        action = input_fn(f"Action [{actions}]: ").strip().casefold()
        if action not in issue.allowed_actions:
            raise WorkflowError(f"invalid action for {issue.issue_id}")
        if action == "cancel":
            raise WorkflowCancelled("operation cancelled by operator")
        if action == "accept":
            if issue.suggested_value is None:
                raise WorkflowError(f"{issue.issue_id} has no value to accept")
            if issue.kind == "assumption":
                if issue.classification != "nontechnical":
                    raise WorkflowError("technical assumption cannot be accepted")
                reason = input_fn(
                    "Reason for accepting nontechnical assumption: "
                ).strip()
                if not reason:
                    raise WorkflowError(
                        "assumption acceptance reason must be non-empty"
                    )
                accepted = decision(
                    issue,
                    action="accepted_nontechnical_assumption",
                    final_value=issue.suggested_value,
                    reason=reason,
                )
                accepted["classification"] = "nontechnical"
                state.accepted_nontechnical_assumptions.append(accepted)
            else:
                if issue.target_path is None:
                    raise WorkflowError("accepted value has no target path")
                set_nested_value(root, issue.target_path, issue.suggested_value)
                state.corrected_values.append(
                    decision(
                        issue,
                        action="accepted_suggested_value",
                        final_value=issue.suggested_value,
                    )
                )
            state.unresolved_issue_ids.discard(issue.issue_id)
            continue
        if action == "not_applicable":
            reason = input_fn("Reason technical detail is not applicable: ").strip()
            if not reason:
                raise WorkflowError("not_applicable reason must be non-empty")
            state.not_applicable_technical_details.append(
                decision(
                    issue,
                    action="marked_not_applicable",
                    final_value=issue.suggested_value,
                    reason=reason,
                )
            )
            state.unresolved_issue_ids.discard(issue.issue_id)
            continue
        corrected = parse_corrected_value(
            input_fn("Corrected value: "),
            issue.value_kind,
        )
        if issue.kind == "supply_boundary":
            state.supply_boundary = cast(str, corrected)
        elif issue.target_path is not None:
            set_nested_value(root, issue.target_path, corrected)
        else:
            raise WorkflowError(f"{issue.issue_id} has no correctable target path")
        action_name = (
            "resolved_conflict"
            if issue.kind == "conflict"
            else (
                "corrected_technical_detail"
                if issue.kind == "technical_details"
                else "corrected_value"
            )
        )
        resolved = decision(issue, action=action_name, final_value=corrected)
        if issue.kind == "conflict":
            state.resolved_conflicts.append(resolved)
        else:
            state.corrected_values.append(resolved)
        state.unresolved_issue_ids.discard(issue.issue_id)
    if not state.supply_boundary:
        raise WorkflowError("supply boundary remains unresolved")
    if state.unresolved_issue_ids:
        raise WorkflowError(
            "unresolved issues remain: " + ", ".join(sorted(state.unresolved_issue_ids))
        )


def collect_assumptions(draft: Mapping[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key == "assumptions" and isinstance(child, list):
                    for index, assumption in enumerate(child):
                        if isinstance(assumption, str) and assumption.strip():
                            findings.append(
                                {
                                    "source_path": f"{child_path}[{index}]",
                                    "assumption": assumption,
                                }
                            )
                else:
                    visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(draft, "")
    return findings


def reject_unresolved_conflicts(draft: Mapping[str, Any]) -> None:
    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key == "conflicts" and isinstance(child, list) and child:
                    raise WorkflowError(
                        f"batch decisions do not resolve conflicts: {child_path}"
                    )
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(draft, "")


def require_exact_red_flags(
    value: Any,
    actual: Any,
    label: str,
) -> list[str]:
    acknowledged = unique_strings(value, label, allow_empty=True)
    actual_flags = [
        strict_nonempty_string(child, f"{label} source red flag")
        for child in exact_list(actual, f"{label} source")
    ]
    if acknowledged != actual_flags:
        raise WorkflowError(f"{label} does not exactly match source red_flags")
    return acknowledged


def normalized_text(value: str) -> str:
    return "".join(value.casefold().split())


def validate_decisions_binding(
    data: Mapping[str, Any],
    *,
    case_id: str,
    snapshot: InputSnapshot,
) -> None:
    if data.get("schema_version") != DECISIONS_INPUT_SCHEMA:
        raise WorkflowError(
            f"decisions JSON schema_version must be {DECISIONS_INPUT_SCHEMA}"
        )
    if data.get("case_id") != case_id:
        raise WorkflowError("decisions JSON Case ID does not match")
    if data.get("draft_id") != snapshot.draft.get("draft_id"):
        raise WorkflowError("decisions JSON draft ID does not match")
    bindings = exact_object(
        data.get("input_sha256"),
        "input_sha256",
        {
            "source_bundle_manifest",
            "preliminary_composition_draft",
            "igor_review_card",
        },
    )
    expected = {
        "source_bundle_manifest": snapshot.hashes[MANIFEST_NAME],
        "preliminary_composition_draft": snapshot.hashes[DRAFT_NAME],
        "igor_review_card": snapshot.hashes[REVIEW_NAME],
    }
    for field_name, expected_hash in expected.items():
        value = strict_nonempty_string(bindings.get(field_name), field_name)
        if HASH_RE.fullmatch(value) is None or value != expected_hash:
            raise WorkflowError(f"decisions JSON hash binding failed: {field_name}")


def validate_source_quality_acknowledgements(
    value: Any,
    draft: Mapping[str, Any],
) -> tuple[list[dict[str, str]], set[str]]:
    entries = exact_list(value, "source_quality_acknowledgements")
    expected = {
        f"red_flags[{index}]": warning
        for index, warning in enumerate(as_list(draft.get("red_flags")))
        if isinstance(warning, str) and warning.strip()
    }
    result: list[dict[str, str]] = []
    paths: set[str] = set()
    for index, raw in enumerate(entries):
        entry = exact_object(
            raw,
            f"source_quality_acknowledgements[{index}]",
            {"source_path", "warning", "reason"},
        )
        source_path = strict_nonempty_string(entry.get("source_path"), "source_path")
        warning = strict_nonempty_string(entry.get("warning"), "warning")
        reason = strict_nonempty_string(entry.get("reason"), "reason")
        if source_path in paths:
            raise WorkflowError("duplicate source-quality acknowledgement")
        if expected.get(source_path) != warning:
            raise WorkflowError("unknown or stale source-quality acknowledgement")
        paths.add(source_path)
        result.append(
            {"source_path": source_path, "warning": warning, "reason": reason}
        )
    if paths != set(expected):
        raise WorkflowError("source-quality warnings are not exactly acknowledged")
    return result, paths


def validate_assumption_resolutions(
    value: Any,
    draft: Mapping[str, Any],
) -> list[dict[str, str]]:
    entries = exact_list(value, "technical_assumption_resolutions")
    expected = {
        finding["source_path"]: finding["assumption"]
        for finding in collect_assumptions(draft)
    }
    result: list[dict[str, str]] = []
    paths: set[str] = set()
    allowed = {"acknowledged", "resolved_by_explicit_composition_decisions"}
    for index, raw in enumerate(entries):
        entry = exact_object(
            raw,
            f"technical_assumption_resolutions[{index}]",
            {"source_path", "assumption", "resolution", "reason"},
        )
        source_path = strict_nonempty_string(entry.get("source_path"), "source_path")
        assumption = strict_nonempty_string(entry.get("assumption"), "assumption")
        resolution = strict_nonempty_string(entry.get("resolution"), "resolution")
        reason = strict_nonempty_string(entry.get("reason"), "reason")
        if source_path in paths:
            raise WorkflowError("duplicate technical assumption resolution")
        if expected.get(source_path) != assumption:
            raise WorkflowError("unknown or stale technical assumption resolution")
        if resolution not in allowed:
            raise WorkflowError("unsupported technical assumption resolution")
        paths.add(source_path)
        result.append(
            {
                "source_path": source_path,
                "assumption": assumption,
                "resolution": resolution,
                "reason": reason,
            }
        )
    if paths != set(expected):
        raise WorkflowError("technical assumptions are not exactly resolved")
    return result


def apply_batch_decisions(
    snapshot: InputSnapshot,
    decisions_snapshot: DecisionsInputSnapshot,
    *,
    case_id: str,
) -> CompositionState:
    data = exact_object(
        decisions_snapshot.data,
        "decisions JSON",
        {
            "schema_version",
            "case_id",
            "draft_id",
            "input_sha256",
            "items",
            "source_quality_acknowledgements",
            "technical_assumption_resolutions",
            "supply_boundary",
        },
    )
    validate_decisions_binding(
        data,
        case_id=case_id,
        snapshot=snapshot,
    )
    reject_unresolved_conflicts(snapshot.draft)
    source_acknowledgements, covered_red_flag_paths = (
        validate_source_quality_acknowledgements(
            data.get("source_quality_acknowledgements"), snapshot.draft
        )
    )
    assumption_resolutions = validate_assumption_resolutions(
        data.get("technical_assumption_resolutions"), snapshot.draft
    )
    supply_boundary = strict_nonempty_string(
        data.get("supply_boundary"), "supply_boundary"
    )

    state = classify_composition(snapshot.draft)
    source_items = as_list(snapshot.draft.get("items"))
    decisions_items = exact_list(data.get("items"), "items")
    source_item_ids = [as_mapping(item).get("item_id") for item in source_items]
    decision_item_ids = [as_mapping(item).get("item_id") for item in decisions_items]
    if len(set(decision_item_ids)) != len(decision_item_ids):
        raise WorkflowError("decisions JSON contains duplicate item_id")
    if decision_item_ids != source_item_ids:
        raise WorkflowError("decisions JSON items must exactly follow source item IDs")

    expanded_components: list[dict[str, Any]] = []
    item_audit: list[dict[str, Any]] = []
    overridden_targets: set[str] = set()
    for item_index, (source_raw, decision_raw) in enumerate(
        zip(source_items, decisions_items, strict=True)
    ):
        source_item = as_mapping(source_raw)
        item_decision = exact_object(
            decision_raw,
            f"items[{item_index}]",
            {
                "item_id",
                "product_name",
                "quantity",
                "manufacturer",
                "acknowledged_red_flags",
                "cabinet",
                "component_groups",
            },
        )
        item_id = strict_nonempty_string(item_decision.get("item_id"), "item_id")
        product_name = strict_nonempty_string(
            item_decision.get("product_name"), "product_name"
        )
        item_quantity = positive_number(item_decision.get("quantity"), "quantity")
        if not isinstance(item_quantity, int):
            raise WorkflowError("item quantity must be a positive integer")
        manufacturer = strict_nonempty_string(
            item_decision.get("manufacturer"), "manufacturer"
        )
        item_flags = require_exact_red_flags(
            item_decision.get("acknowledged_red_flags"),
            source_item.get("red_flags"),
            f"items[{item_index}].acknowledged_red_flags",
        )
        covered_red_flag_paths.update(
            f"items[{item_index}].red_flags[{index}]"
            for index in range(len(item_flags))
        )

        source_cabinet = as_mapping(source_item.get("cabinet_guess"))
        cabinet = exact_object(
            item_decision.get("cabinet"),
            f"items[{item_index}].cabinet",
            {"code", "label", "acknowledged_red_flags"},
        )
        cabinet_code = strict_nonempty_string(cabinet.get("code"), "cabinet.code")
        cabinet_label = strict_nonempty_string(cabinet.get("label"), "cabinet.label")
        cabinet_flags = require_exact_red_flags(
            cabinet.get("acknowledged_red_flags"),
            source_cabinet.get("red_flags"),
            f"items[{item_index}].cabinet.acknowledged_red_flags",
        )
        covered_red_flag_paths.update(
            f"items[{item_index}].cabinet_guess.red_flags[{index}]"
            for index in range(len(cabinet_flags))
        )

        confirmed_item = state.items[item_index]
        confirmed_item["product_name"] = product_name
        confirmed_item["quantity"] = item_quantity
        confirmed_item["cabinet"] = {
            "cabinet_code": cabinet_code,
            "cabinet_label": cabinet_label,
        }
        overridden_targets.update(
            {f"items[{item_index}].product_name", f"items[{item_index}].quantity"}
        )

        source_components = as_list(source_item.get("components"))
        source_by_id = {
            as_mapping(component).get("component_id"): (index, as_mapping(component))
            for index, component in enumerate(source_components)
        }
        covered_component_ids: set[str] = set()
        groups = exact_list(
            item_decision.get("component_groups"),
            f"items[{item_index}].component_groups",
        )
        if not groups:
            raise WorkflowError("component_groups must not be empty")
        for group_index, group_raw in enumerate(groups):
            group = exact_object(
                group_raw,
                f"items[{item_index}].component_groups[{group_index}]",
                {
                    "component_ids",
                    "total_quantity",
                    "final_description",
                    "install_type",
                    "substitution",
                    "acknowledged_red_flags",
                },
            )
            component_ids = unique_strings(
                group.get("component_ids"),
                f"items[{item_index}].component_groups[{group_index}].component_ids",
            )
            if covered_component_ids.intersection(component_ids):
                raise WorkflowError("component_id is covered more than once")
            if any(component_id not in source_by_id for component_id in component_ids):
                raise WorkflowError("component group contains unknown component_id")
            final_description = strict_nonempty_string(
                group.get("final_description"), "final_description"
            )
            if normalized_text(manufacturer) not in normalized_text(final_description):
                raise WorkflowError("final_description must contain manufacturer")
            install_type = strict_nonempty_string(
                group.get("install_type"), "install_type"
            )
            if install_type not in INSTALL_TYPES:
                raise WorkflowError("batch install_type is not allowed")
            acknowledged_flags = unique_strings(
                group.get("acknowledged_red_flags"),
                "component group acknowledged_red_flags",
                allow_empty=True,
            )
            total_quantity = positive_number(
                group.get("total_quantity"), "total_quantity"
            )
            source_total = 0.0
            for component_id in component_ids:
                source_index, source_component = source_by_id[component_id]
                source_quantity = positive_number(
                    source_component.get("quantity_guess"),
                    f"source quantity_guess for {component_id}",
                )
                source_total += float(source_quantity)
                actual_flags = require_exact_red_flags(
                    acknowledged_flags,
                    source_component.get("red_flags"),
                    f"component group red_flags for {component_id}",
                )
                covered_red_flag_paths.update(
                    f"items[{item_index}].components[{source_index}].red_flags[{index}]"
                    for index in range(len(actual_flags))
                )
                source_code = source_component.get(
                    "component_code_guess"
                ) or source_component.get("model_guess")
                source_code = strict_nonempty_string(
                    source_code, f"source component code for {component_id}"
                )
                source_values = {
                    value
                    for field_name in (
                        "component_code_guess",
                        "model_guess",
                        "component_label_guess",
                        "rating_guess",
                        "note_guess",
                    )
                    if isinstance((value := source_component.get(field_name)), str)
                    and value.strip()
                }
                substitution_raw = group.get("substitution")
                substitution: dict[str, Any] | None = None
                rating = source_component.get("rating_guess")
                rating_changed = (
                    isinstance(rating, str)
                    and rating.strip()
                    and normalized_text(rating)
                    not in normalized_text(final_description)
                )
                if substitution_raw is None:
                    if rating_changed:
                        raise WorkflowError(
                            f"explicit substitution is required for {component_id}"
                        )
                else:
                    substitution_value = exact_object(
                        substitution_raw,
                        "substitution",
                        {"original", "final", "reason"},
                    )
                    original = strict_nonempty_string(
                        substitution_value.get("original"), "substitution.original"
                    )
                    final = strict_nonempty_string(
                        substitution_value.get("final"), "substitution.final"
                    )
                    reason = strict_nonempty_string(
                        substitution_value.get("reason"), "substitution.reason"
                    )
                    if original not in source_values:
                        raise WorkflowError(
                            "substitution.original must exactly match source "
                            "component data"
                        )
                    if final != final_description:
                        raise WorkflowError(
                            "substitution.final must equal final_description"
                        )
                    substitution = {
                        "source_component_id": component_id,
                        "original": original,
                        "final": final,
                        "reason": reason,
                        "explicit_igor_decision": True,
                    }

                confirmed_component = as_mapping(
                    as_list(confirmed_item.get("components"))[source_index]
                )
                cast(dict[str, Any], confirmed_component)[
                    "component_code"
                ] = source_code
                cast(dict[str, Any], confirmed_component)[
                    "component_label"
                ] = final_description
                cast(dict[str, Any], confirmed_component)["quantity"] = source_quantity
                cast(dict[str, Any], confirmed_component)["install_type"] = install_type
                overridden_targets.update(
                    {
                        f"items[{item_index}].components[{source_index}].component_label",
                        f"items[{item_index}].components[{source_index}].install_type",
                    }
                )
                expanded_components.append(
                    {
                        "item_id": item_id,
                        "component_id": component_id,
                        "manufacturer": manufacturer,
                        "source_component": {
                            field_name: copy.deepcopy(source_component.get(field_name))
                            for field_name in (
                                "component_code_guess",
                                "model_guess",
                                "component_label_guess",
                                "rating_guess",
                                "note_guess",
                                "provenance",
                            )
                        },
                        "source_code_semantics": (
                            "project_designation_not_manufacturer_catalog_number"
                        ),
                        "final_component": {
                            "component_code": source_code,
                            "component_label": final_description,
                            "quantity": source_quantity,
                            "install_type": install_type,
                        },
                        "acknowledged_red_flags": actual_flags,
                        "substitution": substitution,
                    }
                )
            if source_total != float(total_quantity):
                raise WorkflowError(
                    "total_quantity does not equal source quantity_guess sum"
                )
            covered_component_ids.update(component_ids)
        if covered_component_ids != set(source_by_id):
            raise WorkflowError(
                "component decisions do not exactly cover source components"
            )
        item_audit.append(
            {
                "item_id": item_id,
                "source_product_name": source_item.get("product_name_guess"),
                "product_name": product_name,
                "quantity": item_quantity,
                "manufacturer": manufacturer,
                "cabinet": {
                    "cabinet_code": cabinet_code,
                    "cabinet_label": cabinet_label,
                },
                "acknowledged_red_flags": item_flags,
                "cabinet_acknowledged_red_flags": cabinet_flags,
            }
        )

    expected_red_flag_paths = {
        finding["source_path"]
        for finding in collect_preliminary_red_flags(snapshot.draft)
    }
    if covered_red_flag_paths != expected_red_flag_paths:
        raise WorkflowError("preliminary red_flags are not exactly covered")
    state.automatic_transfers = [
        transfer
        for transfer in state.automatic_transfers
        if transfer.target_path not in overridden_targets
    ]
    state.preliminary_red_flags = []
    state.unresolved_issue_ids.clear()
    state.supply_boundary = supply_boundary
    state.batch_decisions = {
        "input_schema_version": DECISIONS_INPUT_SCHEMA,
        "input_sha256": decisions_snapshot.sha256,
        "item_decisions": item_audit,
        "expanded_component_decisions": expanded_components,
        "source_quality_acknowledgements": source_acknowledgements,
        "technical_assumption_resolutions": assumption_resolutions,
        "resolved_preliminary_red_flag_paths": sorted(covered_red_flag_paths),
    }
    return state


def ensure_candidate_complete(state: CompositionState) -> None:
    if not state.items:
        raise WorkflowError("confirmed composition must contain at least one item")
    for item_index, item in enumerate(state.items):
        for field_name in ("item_id", "product_name", "product_type", "quantity"):
            if not nonempty(item.get(field_name)):
                raise WorkflowError(
                    f"required confirmed field remains unresolved: "
                    f"items[{item_index}].{field_name}"
                )
        cabinet = as_mapping(item.get("cabinet"))
        for field_name in ("cabinet_code", "cabinet_label"):
            if not nonempty(cabinet.get(field_name)):
                raise WorkflowError(
                    f"required confirmed field remains unresolved: "
                    f"items[{item_index}].cabinet.{field_name}"
                )
        components = as_list(item.get("components"))
        if not components:
            raise WorkflowError("confirmed item must contain at least one component")
        for component_index, component_value in enumerate(components):
            component = as_mapping(component_value)
            for field_name in (
                "component_id",
                "component_code",
                "component_label",
                "quantity",
                "install_type",
            ):
                if not nonempty(component.get(field_name)):
                    raise WorkflowError(
                        "required confirmed field remains unresolved: "
                        f"items[{item_index}].components[{component_index}]."
                        f"{field_name}"
                    )
            if component.get("install_type") not in INSTALL_TYPES:
                raise WorkflowError("confirmed install_type is not allowed")


def final_safety_red_flags(state: CompositionState) -> list[str]:
    findings = [
        f"{value['source_path']}: {value['red_flag']}"
        for value in state.preliminary_red_flags
    ]
    findings.extend(
        f"unresolved issue: {issue_id}"
        for issue_id in sorted(state.unresolved_issue_ids)
    )
    if not state.supply_boundary:
        findings.append("supply boundary is unresolved")
    return findings


def ensure_ready_for_approval(state: CompositionState) -> None:
    ensure_candidate_complete(state)
    findings = final_safety_red_flags(state)
    if findings:
        raise WorkflowError(
            "candidate is not ready for approval: " + "; ".join(findings)
        )


def render_final_summary(
    *,
    case_id: str,
    confirmation_id: str,
    state: CompositionState,
) -> str:
    safety_findings = final_safety_red_flags(state)
    lines = [
        "FINAL TECHNICAL COMPOSITION REVIEW",
        f"Case ID: {case_id}",
        f"Confirmation ID: {confirmation_id}",
        f"Supply boundary: {state.supply_boundary}",
        "",
        "Items and cabinets:",
    ]
    for item in state.items:
        cabinet = as_mapping(item.get("cabinet"))
        lines.append(
            f"- {item.get('item_id')}: {item.get('product_name')} "
            f"x {item.get('quantity')}; cabinet "
            f"{cabinet.get('cabinet_code')} / {cabinet.get('cabinet_label')}"
        )
        for component_value in as_list(item.get("components")):
            component = as_mapping(component_value)
            lines.append(
                "  - "
                f"{component.get('component_id')}: "
                f"{component.get('component_code')} / "
                f"{component.get('component_label')}; "
                f"qty={component.get('quantity')}; "
                f"install_type={component.get('install_type')}"
            )
    sections = (
        ("Corrected values", state.corrected_values),
        ("Resolved conflicts", state.resolved_conflicts),
        (
            "Accepted nontechnical assumptions",
            state.accepted_nontechnical_assumptions,
        ),
        (
            "Not-applicable technical details",
            state.not_applicable_technical_details,
        ),
        ("Removed values", state.removed_values),
    )
    for title, values in sections:
        lines.extend(["", f"{title}:"])
        if values:
            lines.extend(
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                for value in values
            )
        else:
            lines.append("none")
    lines.extend(["", "Preliminary red flags:"])
    if state.preliminary_red_flags:
        lines.extend(
            f"- {value['source_path']}: {value['red_flag']}"
            for value in state.preliminary_red_flags
        )
    else:
        lines.append("none")
    lines.extend(
        [
            "",
            f"Unresolved issues: {len(state.unresolved_issue_ids)}",
            "Computed final safety status: "
            + ("BLOCKED" if safety_findings else "CLEAR"),
        ]
    )
    return "\n".join(lines)


def build_confirmed_artifact(
    *,
    confirmation_id: str,
    confirmed_at: str,
    snapshot: InputSnapshot,
    state: CompositionState,
) -> dict[str, Any]:
    safety_findings = final_safety_red_flags(state)
    if safety_findings:
        raise WorkflowError(
            "confirmed artifact cannot be built with unresolved safety findings"
        )
    items: list[dict[str, Any]] = []
    for value in state.items:
        item = dict(value)
        item["confirmation_note"] = (
            f"Technical composition confirmed by Igor under {confirmation_id}."
        )
        items.append(item)
    return {
        "schema_version": "confirmed_composition_artifact.v0.1",
        "confirmation_id": confirmation_id,
        "confirmed_by": "Igor",
        "confirmed_at": confirmed_at,
        "source_links": {
            "raw_input_sha256": snapshot.hashes[MANIFEST_NAME],
            "preliminary_draft_sha256": snapshot.hashes[DRAFT_NAME],
            "review_card_sha256": snapshot.hashes[REVIEW_NAME],
        },
        "safety": {
            "status": "confirmed_composition_only",
            "composition_confirmed_by_igor": True,
            "calculator_input_draft_allowed": True,
            "price_approved_by_igor": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "items": items,
        "red_flags": safety_findings,
        "notes": [],
        "next_allowed_step": "build_price_calculator_input_draft",
    }


def build_confirmed_artifact_from_applied_bundle(
    *,
    confirmation_id: str,
    approval_channel: str,
    confirmed_at: str,
    snapshot: AppliedInputSnapshot,
    approval_phrase: str = APPROVAL_PHRASE,
) -> dict[str, Any]:
    return {
        "schema_version": CONFIRMED_V02_SCHEMA,
        "project_id": snapshot.data["project_id"],
        "confirmation_id": confirmation_id,
        "confirmed_by": "Igor",
        "confirmed_at": confirmed_at,
        "approval": {
            "authority": APPROVAL_AUTHORITY,
            "approved_by": "Igor",
            "approval_phrase": approval_phrase,
            "approval_channel": approval_channel,
        },
        "source_lineage": {
            "applied_bundle_sha256": snapshot.sha256,
            "applied_bundle_schema_version": APPLIED_BUNDLE_SCHEMA,
            "applied_source_lineage": copy.deepcopy(snapshot.data["source_lineage"]),
        },
        "installed_components": copy.deepcopy(snapshot.installed_components),
        "reserved_meter_spaces": copy.deepcopy(snapshot.reserved_meter_spaces),
        "coverage": dict(snapshot.coverage),
        "confirmed_composition_created": True,
        "pricing_started": False,
        "downstream_started": False,
        "red_flags": [],
    }


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_decision_record(
    *,
    case_id: str,
    confirmation_id: str,
    approval_channel: str,
    confirmed_at: str,
    snapshot: InputSnapshot,
    state: CompositionState,
    artifact_sha256: str,
    final_approval_phrase: str = APPROVAL_PHRASE,
) -> dict[str, Any]:
    record = {
        "record_type": "igor_composition_decisions.v0.1",
        "case_id": case_id,
        "confirmation_id": confirmation_id,
        "confirmed_by": "Igor",
        "confirmed_at": confirmed_at,
        "approval_channel": approval_channel,
        "inputs": {
            MANIFEST_NAME: {
                "relative_path": MANIFEST_NAME,
                "sha256": snapshot.hashes[MANIFEST_NAME],
            },
            DRAFT_NAME: {
                "relative_path": DRAFT_NAME,
                "sha256": snapshot.hashes[DRAFT_NAME],
            },
            REVIEW_NAME: {
                "relative_path": REVIEW_NAME,
                "sha256": snapshot.hashes[REVIEW_NAME],
            },
        },
        "automatic_transfers": [
            transfer.as_dict() for transfer in state.automatic_transfers
        ],
        "corrected_values": state.corrected_values,
        "resolved_conflicts": state.resolved_conflicts,
        "accepted_nontechnical_assumptions": (state.accepted_nontechnical_assumptions),
        "not_applicable_technical_details": (state.not_applicable_technical_details),
        "removed_values": state.removed_values,
        "supply_boundary_decision": state.supply_boundary,
        "final_approval_phrase": final_approval_phrase,
        "confirmed_artifact": {
            "relative_path": ARTIFACT_NAME,
            "sha256": artifact_sha256,
        },
        "approvals": {
            "technical_composition": True,
            "price": False,
            "schedule": False,
            "quote_generation": False,
            "client_send": False,
            "procurement": False,
            "production": False,
        },
    }
    if state.batch_decisions is not None:
        record["record_type"] = "igor_composition_decisions.v0.2"
        record["decision_mode"] = "batch_json"
        record["batch_decisions"] = state.batch_decisions
    return record


def build_applied_decision_record(
    *,
    confirmation_id: str,
    approval_channel: str,
    confirmed_at: str,
    snapshot: AppliedInputSnapshot,
    artifact_sha256: str,
    final_approval_phrase: str = APPROVAL_PHRASE,
) -> dict[str, Any]:
    return {
        "record_type": "igor_composition_decisions.v0.3",
        "case_id": snapshot.data["project_id"],
        "confirmation_id": confirmation_id,
        "confirmed_by": "Igor",
        "confirmed_at": confirmed_at,
        "approval_channel": approval_channel,
        "inputs": {
            snapshot.paths.applied_bundle.name: {
                "relative_path": snapshot.paths.applied_bundle.name,
                "sha256": snapshot.sha256,
                "schema_version": APPLIED_BUNDLE_SCHEMA,
                "source_lineage": copy.deepcopy(snapshot.data["source_lineage"]),
            }
        },
        "final_approval_phrase": final_approval_phrase,
        "confirmed_artifact": {
            "relative_path": ARTIFACT_NAME,
            "sha256": artifact_sha256,
        },
        "approvals": {
            "technical_composition": True,
            "price": False,
            "schedule": False,
            "quote_generation": False,
            "client_send": False,
            "procurement": False,
            "production": False,
        },
    }


def build_receipt(
    *,
    record: Mapping[str, Any],
    decision_json_sha256: str,
    state: CompositionState,
) -> str:
    artifact = as_mapping(record.get("confirmed_artifact"))
    component_count = sum(len(as_list(item.get("components"))) for item in state.items)
    lines = [
        "# Igor technical composition decision receipt",
        "",
        f"- Case ID: {record.get('case_id')}",
        f"- Confirmation ID: {record.get('confirmation_id')}",
        f"- Confirmed at: {record.get('confirmed_at')}",
        f"- Confirmed by: {record.get('confirmed_by')}",
        f"- Approval channel: {record.get('approval_channel')}",
        f"- Supply boundary: {record.get('supply_boundary_decision')}",
        f"- Confirmed artifact SHA-256: {artifact.get('sha256')}",
        f"- Decision JSON SHA-256: {decision_json_sha256}",
        f"- Items: {len(state.items)}",
        f"- Components: {component_count}",
        f"- Corrections: {len(state.corrected_values)}",
        f"- Resolved conflicts: {len(state.resolved_conflicts)}",
        (
            "- Accepted nontechnical assumptions: "
            f"{len(state.accepted_nontechnical_assumptions)}"
        ),
        (
            "- Not-applicable technical details: "
            f"{len(state.not_applicable_technical_details)}"
        ),
        "",
        (
            f"The full confirmed technical composition is in {ARTIFACT_NAME}; "
            "this receipt is only a concise audit summary."
        ),
        "",
        "## Safety boundary",
        "",
        (
            "This receipt confirms technical composition only. It does not "
            "authorize price, schedule, КП, client sending, procurement, "
            "reservation, prepayment, workshop launch, or production."
        ),
        "",
    ]
    if state.batch_decisions is not None:
        warnings = as_list(state.batch_decisions.get("source_quality_acknowledgements"))
        assumptions = as_list(
            state.batch_decisions.get("technical_assumption_resolutions")
        )
        components = as_list(state.batch_decisions.get("expanded_component_decisions"))
        substitutions = [
            as_mapping(component).get("substitution")
            for component in components
            if as_mapping(component).get("substitution") is not None
        ]
        lines.extend(["## Batch decision audit", ""])
        lines.append("Source-quality acknowledgements:")
        lines.extend(
            f"- {as_mapping(value).get('source_path')}: "
            f"{as_mapping(value).get('warning')} — "
            f"{as_mapping(value).get('reason')}"
            for value in warnings
        )
        if not warnings:
            lines.append("- none")
        lines.append("Technical assumption resolutions:")
        lines.extend(
            f"- {as_mapping(value).get('source_path')}: "
            f"{as_mapping(value).get('resolution')} — "
            f"{as_mapping(value).get('reason')}"
            for value in assumptions
        )
        if not assumptions:
            lines.append("- none")
        lines.append("Explicit substitutions:")
        lines.extend(
            f"- {as_mapping(value).get('source_component_id')}: "
            f"{as_mapping(value).get('original')} -> "
            f"{as_mapping(value).get('final')} — "
            f"{as_mapping(value).get('reason')}"
            for value in substitutions
        )
        if not substitutions:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)


def build_applied_receipt(
    *,
    record: Mapping[str, Any],
    decision_json_sha256: str,
    snapshot: AppliedInputSnapshot,
) -> str:
    artifact = as_mapping(record.get("confirmed_artifact"))
    return "\n".join(
        [
            "# Igor technical composition decision receipt",
            "",
            f"- Case ID: {record.get('case_id')}",
            f"- Confirmation ID: {record.get('confirmation_id')}",
            f"- Confirmed at: {record.get('confirmed_at')}",
            f"- Confirmed by: {record.get('confirmed_by')}",
            f"- Approval channel: {record.get('approval_channel')}",
            f"- Applied bundle SHA-256: {snapshot.sha256}",
            f"- Confirmed artifact SHA-256: {artifact.get('sha256')}",
            f"- Decision JSON SHA-256: {decision_json_sha256}",
            (
                "- Installed components: "
                f"{snapshot.coverage['installed_component_count']}"
            ),
            (
                "- Reserved meter spaces: "
                f"{snapshot.coverage['reserved_meter_space_count']}"
            ),
            "",
            "## Safety boundary",
            "",
            (
                "This receipt confirms technical composition only. It does not "
                "authorize pricing, schedule, КП, client sending, procurement, "
                "reservation, prepayment, workshop launch, or production."
            ),
            "",
        ]
    )


def default_confirmed_validator(
    path: Path,
    *,
    applied_bundle_json: Path | None = None,
) -> Any:
    module = load_module(
        "confirmed_builder_confirmed_validator",
        SCRIPTS_DIR / "validate_confirmed_composition_artifact.py",
    )
    return module.validate_confirmed_composition_artifact(
        path,
        applied_bundle_json=applied_bundle_json,
    )


def write_fsynced(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def publish_atomically(
    *,
    paths: CasePaths | AppliedPaths,
    artifact: Mapping[str, Any],
    record_factory: Callable[[str], Mapping[str, Any]],
    receipt_factory: Callable[[Mapping[str, Any], str], str],
    confirmed_validator: ValidatorFunction = default_confirmed_validator,
) -> tuple[str, str]:
    if paths.output_dir.exists():
        raise WorkflowError(
            "confirmed directory already exists; overwrite is forbidden"
        )
    staging = paths.case_dir / f".confirmed-staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        artifact_bytes = canonical_json_bytes(artifact)
        artifact_path = staging / ARTIFACT_NAME
        write_fsynced(artifact_path, artifact_bytes)
        validation = confirmed_validator(artifact_path)
        if validation.status != "PASS":
            details = "; ".join(getattr(validation, "red_flags", [])[:5])
            raise WorkflowError(f"confirmed artifact validator failed: {details}")
        artifact_data = parse_json_object(artifact_bytes, ARTIFACT_NAME)
        if artifact_data.get("red_flags") != []:
            raise WorkflowError("confirmed artifact root red_flags must be empty")
        artifact_hash = sha256_bytes(artifact_bytes)
        record = record_factory(artifact_hash)
        decision_bytes = canonical_json_bytes(record)
        decision_hash = sha256_bytes(decision_bytes)
        receipt = receipt_factory(record, decision_hash).encode("utf-8")
        write_fsynced(staging / DECISIONS_NAME, decision_bytes)
        write_fsynced(staging / RECEIPT_NAME, receipt)
        os.rename(staging, paths.output_dir)
        return artifact_hash, decision_hash
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging)
        if paths.output_dir.exists():
            raise WorkflowError(
                "publication failed after canonical directory appeared; manual "
                "inspection is required"
            ) from exc
        raise


def timezone_aware_now() -> datetime:
    return datetime.now().astimezone()


def run_builder(
    *,
    case_id: str,
    confirmation_id: str,
    approval_channel: str,
    decisions_json: Path | None = None,
    canonical_root: Path = CANONICAL_ROOT,
    input_fn: InputFunction = input,
    output_fn: OutputFunction = print,
    now_fn: NowFunction = timezone_aware_now,
    before_drift_check: Callable[[], None] | None = None,
    confirmed_validator: ValidatorFunction = default_confirmed_validator,
    approval_phrase: str = APPROVAL_PHRASE,
) -> BuildResult:
    result = BuildResult(case_id=case_id)
    try:
        confirmation_id = require_metadata(confirmation_id, "confirmation_id")
        approval_channel = require_metadata(approval_channel, "approval_channel")
        paths = resolve_case_paths(case_id, canonical_root=canonical_root)
        result.output_dir = paths.output_dir
        snapshot = load_snapshot(paths)
        validate_identifier_integrity(snapshot.draft)
        validate_source_metadata_integrity(snapshot.draft)
        decisions_snapshot = (
            load_decisions_input(decisions_json) if decisions_json is not None else None
        )
        if decisions_snapshot is None:
            preliminary_red_flags = collect_preliminary_red_flags(snapshot.draft)
            if preliminary_red_flags:
                output_fn("Preliminary red flags block confirmed composition:")
                for finding in preliminary_red_flags:
                    output_fn(f"- {finding['source_path']}: {finding['red_flag']}")
                raise WorkflowError(
                    "preliminary red flags block confirmed composition: "
                    + "; ".join(
                        f"{finding['source_path']}={finding['red_flag']}"
                        for finding in preliminary_red_flags
                    )
                )
            state = classify_composition(snapshot.draft)
            apply_interactive_decisions(
                state,
                input_fn=input_fn,
                output_fn=output_fn,
            )
        else:
            state = apply_batch_decisions(
                snapshot,
                decisions_snapshot,
                case_id=case_id,
            )
        ensure_ready_for_approval(state)
        output_fn(
            render_final_summary(
                case_id=case_id,
                confirmation_id=confirmation_id,
                state=state,
            )
        )
        phrase = input_fn(f"Type exact approval phrase [{approval_phrase}]: ")
        if phrase != approval_phrase:
            raise WorkflowError("exact technical composition approval phrase required")
        if before_drift_check is not None:
            before_drift_check()
        assert_snapshot_unchanged(snapshot)
        if decisions_snapshot is not None:
            assert_decisions_unchanged(decisions_snapshot)
        confirmed_at_value = now_fn()
        if confirmed_at_value.tzinfo is None or confirmed_at_value.utcoffset() is None:
            raise WorkflowError("confirmed_at must be timezone-aware")
        confirmed_at = confirmed_at_value.isoformat()
        artifact = build_confirmed_artifact(
            confirmation_id=confirmation_id,
            confirmed_at=confirmed_at,
            snapshot=snapshot,
            state=state,
        )
        publish_atomically(
            paths=paths,
            artifact=artifact,
            record_factory=lambda artifact_hash: build_decision_record(
                case_id=case_id,
                confirmation_id=confirmation_id,
                approval_channel=approval_channel,
                confirmed_at=confirmed_at,
                snapshot=snapshot,
                state=state,
                artifact_sha256=artifact_hash,
                final_approval_phrase=approval_phrase,
            ),
            receipt_factory=lambda record, decision_hash: build_receipt(
                record=record,
                decision_json_sha256=decision_hash,
                state=state,
            ),
            confirmed_validator=confirmed_validator,
        )
        result.status = "PASS"
        result.output_created = True
    except (WorkflowError, OSError) as exc:
        result.red_flags.append(str(exc))
    return result


def render_applied_final_summary(
    *,
    confirmation_id: str,
    snapshot: AppliedInputSnapshot,
) -> str:
    return "\n".join(
        [
            "Applied v0.23 confirmed-composition review:",
            f"- Project ID: {snapshot.data['project_id']}",
            f"- Confirmation ID: {confirmation_id}",
            f"- Applied bundle SHA-256: {snapshot.sha256}",
            (
                "- Installed components: "
                f"{snapshot.coverage['installed_component_count']}"
            ),
            (
                "- Signature corrections: "
                f"{snapshot.coverage['component_signature_correction_count']}"
            ),
            (
                "- Signature reconfirmations: "
                f"{snapshot.coverage['component_reconfirmation_count']}"
            ),
            (
                "- Reserved meter spaces (not installed): "
                f"{snapshot.coverage['reserved_meter_space_count']}"
            ),
            "- Pricing started: false",
            "- Downstream started: false",
        ]
    )


def run_applied_builder(
    *,
    applied_bundle_json: Path,
    confirmation_id: str,
    approval_channel: str,
    input_fn: InputFunction = input,
    output_fn: OutputFunction = print,
    now_fn: NowFunction = timezone_aware_now,
    before_drift_check: Callable[[], None] | None = None,
    confirmed_validator: ValidatorFunction | None = None,
    approval_phrase: str = APPROVAL_PHRASE,
) -> BuildResult:
    result = BuildResult(case_id="")
    try:
        confirmation_id = require_metadata(confirmation_id, "confirmation_id")
        approval_channel = require_metadata(approval_channel, "approval_channel")
        snapshot = load_applied_snapshot(applied_bundle_json)
        result.case_id = cast(str, snapshot.data["project_id"])
        result.output_dir = snapshot.paths.output_dir
        output_fn(
            render_applied_final_summary(
                confirmation_id=confirmation_id,
                snapshot=snapshot,
            )
        )
        phrase = input_fn(f"Type exact approval phrase [{approval_phrase}]: ")
        if phrase != approval_phrase:
            raise WorkflowError("exact technical composition approval phrase required")
        if before_drift_check is not None:
            before_drift_check()
        assert_applied_snapshot_unchanged(snapshot)
        confirmed_at_value = now_fn()
        if confirmed_at_value.tzinfo is None or confirmed_at_value.utcoffset() is None:
            raise WorkflowError("confirmed_at must be timezone-aware")
        confirmed_at = confirmed_at_value.isoformat()
        artifact = build_confirmed_artifact_from_applied_bundle(
            confirmation_id=confirmation_id,
            approval_channel=approval_channel,
            confirmed_at=confirmed_at,
            snapshot=snapshot,
            approval_phrase=approval_phrase,
        )
        if confirmed_validator is None:

            def validator(path: Path) -> Any:
                return default_confirmed_validator(
                    path,
                    applied_bundle_json=snapshot.paths.applied_bundle,
                )

        else:
            validator = confirmed_validator
        publish_atomically(
            paths=snapshot.paths,
            artifact=artifact,
            record_factory=lambda artifact_hash: build_applied_decision_record(
                confirmation_id=confirmation_id,
                approval_channel=approval_channel,
                confirmed_at=confirmed_at,
                snapshot=snapshot,
                artifact_sha256=artifact_hash,
                final_approval_phrase=approval_phrase,
            ),
            receipt_factory=lambda record, decision_hash: build_applied_receipt(
                record=record,
                decision_json_sha256=decision_hash,
                snapshot=snapshot,
            ),
            confirmed_validator=validator,
        )
        result.status = "PASS"
        result.output_created = True
    except (WorkflowError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.red_flags.append(str(exc))
    return result


def format_report(result: BuildResult) -> str:
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
            "Output:",
            str(result.output_dir) if result.output_created else "not created",
            "",
            "Red flags:",
            *(result.red_flags or ["none"]),
            "",
            "Human Approval:",
            (
                "technical composition only; no price, schedule, quote, client "
                "send, procurement, or production approval"
            ),
            "",
            REPORT_END,
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.applied_bundle_json is not None:
        result = run_applied_builder(
            applied_bundle_json=args.applied_bundle_json,
            confirmation_id=args.confirmation_id,
            approval_channel=args.approval_channel,
        )
    else:
        result = run_builder(
            case_id=args.case_id,
            confirmation_id=args.confirmation_id,
            approval_channel=args.approval_channel,
            decisions_json=args.decisions_json,
        )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
