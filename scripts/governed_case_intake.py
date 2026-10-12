"""Strict, preliminary provenance for a client request and Igor decisions."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"V[0-9]{3}\Z")


class IntakeError(ValueError):
    """The exact governed intake cannot be trusted."""


@dataclass(frozen=True)
class GovernedIntake:
    path: Path
    raw: bytes
    sha256: str
    case_id: str
    version: str
    project_pdf_sha256: str
    project_pdf_path: Path
    base_manifest_sha256: str
    requested_supply: tuple[tuple[str, int], ...]
    excluded_components: tuple[tuple[str, int], ...]


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise IntakeError(f"duplicate intake field: {key}")
        result[key] = value
    return result


def _object(value: Any, name: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise IntakeError(f"{name} must have exact fields {sorted(fields)}")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 10000:
        raise IntakeError(f"{name} must be non-empty bounded text")
    return value


def _evidence(value: Any, name: str) -> str:
    record = _object(value, name, {"text", "source_locator", "text_sha256"})
    body = _text(record["text"], f"{name}.text")
    _text(record["source_locator"], f"{name}.source_locator")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if record["text_sha256"] != digest:
        raise IntakeError(f"{name}.text_sha256 mismatch")
    return body


def _scope_rows(
    value: Any, name: str, *, allow_empty: bool = False
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list) or not value and not allow_empty:
        raise IntakeError(f"{name} must be an explicit valid scope list")
    rows: list[tuple[str, int]] = []
    for index, raw in enumerate(value):
        row = _object(raw, f"{name}[{index}]", {"designation", "quantity"})
        designation = _text(row["designation"], f"{name}[{index}].designation")
        quantity = row["quantity"]
        if type(quantity) is not int or quantity <= 0:
            raise IntakeError(f"{name}[{index}].quantity must be a positive integer")
        rows.append((designation, quantity))
    if len({designation.casefold() for designation, _ in rows}) != len(rows):
        raise IntakeError(f"{name} has duplicate designations")
    return tuple(rows)


def load_governed_intake(
    path: Path,
    *,
    case_id: str,
    version: str,
    project_pdf: Path,
    base_manifest: Path,
) -> GovernedIntake:
    source = path.expanduser().resolve(strict=False)
    try:
        raw = source.read_bytes()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntakeError(
            "governed intake cannot be read as strict UTF-8 JSON"
        ) from error
    root = _object(
        data,
        "governed intake",
        {
            "schema_version",
            "case_id",
            "extraction_version",
            "project_pdf_sha256",
            "project_pdf_path",
            "base_manifest_sha256",
            "client_request",
            "human_decisions",
            "requested_supply",
            "excluded_components",
        },
    )
    if root["schema_version"] != "governed_case_extraction_intake.v0.1":
        raise IntakeError("unsupported governed intake schema")
    if root["case_id"] != case_id or root["extraction_version"] != version:
        raise IntakeError("governed intake Case ID or version mismatch")
    if VERSION_RE.fullmatch(version) is None:
        raise IntakeError("extraction version must match V001-style grammar")
    pdf_sha = root["project_pdf_sha256"]
    if not isinstance(pdf_sha, str) or HASH_RE.fullmatch(pdf_sha) is None:
        raise IntakeError("project PDF SHA-256 is invalid")
    try:
        actual_sha = hashlib.sha256(project_pdf.read_bytes()).hexdigest()
    except OSError as error:
        raise IntakeError("project PDF cannot be read") from error
    if actual_sha != pdf_sha:
        raise IntakeError("project PDF SHA-256 mismatch")
    pdf_path_value = _text(root["project_pdf_path"], "project_pdf_path")
    if Path(pdf_path_value).resolve(strict=False) != project_pdf.resolve(strict=False):
        raise IntakeError("project PDF path mismatch")
    base_sha = root["base_manifest_sha256"]
    if not isinstance(base_sha, str) or HASH_RE.fullmatch(base_sha) is None:
        raise IntakeError("base manifest SHA-256 is invalid")
    try:
        actual_base_sha = hashlib.sha256(base_manifest.read_bytes()).hexdigest()
    except OSError as error:
        raise IntakeError("base manifest cannot be read") from error
    if actual_base_sha != base_sha:
        raise IntakeError("base manifest SHA-256 mismatch")
    client_text = _evidence(root["client_request"], "client_request")
    decisions = root["human_decisions"]
    if not isinstance(decisions, list) or not decisions:
        raise IntakeError("human_decisions must be a non-empty list")
    decision_texts = [
        _evidence(decision, f"human_decisions[{index}]")
        for index, decision in enumerate(decisions)
    ]
    requested = _scope_rows(root["requested_supply"], "requested_supply")
    excluded = _scope_rows(
        root["excluded_components"], "excluded_components", allow_empty=True
    )
    if {name.casefold() for name, _ in requested} & {
        name.casefold() for name, _ in excluded
    }:
        raise IntakeError("requested and excluded identities overlap")
    evidence_texts = [
        client_text.casefold(),
        *(text.casefold() for text in decision_texts),
    ]
    for designation, _ in (*requested, *excluded):
        if not any(designation.casefold() in text for text in evidence_texts):
            raise IntakeError(
                f"scope identity has no request/decision evidence: {designation}"
            )
    return GovernedIntake(
        path=source,
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        case_id=case_id,
        version=version,
        project_pdf_sha256=pdf_sha,
        project_pdf_path=project_pdf.resolve(strict=False),
        base_manifest_sha256=base_sha,
        requested_supply=requested,
        excluded_components=excluded,
    )


VERSIONED_FILES = frozenset(
    {
        "source-bundle-manifest.txt",
        "preliminary-composition-draft.json",
        "igor-review-card.md",
        "governed-intake.json",
    }
)


def _unsafe_reparse(path: Path) -> bool:
    if path.is_symlink() or path.is_junction():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _verify_confirmed_output(
    directory: Path, case_id: str, files: dict[str, Any]
) -> None:
    """Accept only the canonical producer's bound artifact/audit/receipt triple."""
    # Lazy imports avoid the producer -> intake import cycle. No apply is invoked.
    import build_confirmed_composition_from_preliminary_bundle as builder
    from validate_confirmed_composition_artifact import (
        validate_confirmed_composition_artifact,
    )

    folder = directory / builder.OUTPUT_DIR_NAME
    names = {builder.ARTIFACT_NAME, builder.DECISIONS_NAME, builder.RECEIPT_NAME}
    try:
        if (
            not folder.is_dir()
            or _unsafe_reparse(folder)
            or folder.resolve(strict=True).parent != directory.resolve(strict=True)
        ):
            raise IntakeError("confirmed directory is missing or unsafe")
        if {p.name for p in folder.iterdir()} != names:
            raise IntakeError("confirmed output file set mismatch")
        for name in names:
            path = folder / name
            if not path.is_file() or _unsafe_reparse(path):
                raise IntakeError(f"confirmed output is missing or unsafe: {name}")
        raw = {name: (folder / name).read_bytes() for name in names}
        artifact = json.loads(raw[builder.ARTIFACT_NAME], object_pairs_hook=_pairs)
        audit = json.loads(raw[builder.DECISIONS_NAME], object_pairs_hook=_pairs)
        validation = validate_confirmed_composition_artifact(
            folder / builder.ARTIFACT_NAME
        )
        if validation.status != "PASS":
            raise IntakeError("confirmed artifact validation failed")
        links = dict(
            zip(
                ("raw_input_sha256", "preliminary_draft_sha256", "review_card_sha256"),
                (
                    files[builder.MANIFEST_NAME],
                    files[builder.DRAFT_NAME],
                    files[builder.REVIEW_NAME],
                ),
                strict=True,
            )
        )
        if artifact["source_links"] != links or audit["case_id"] != case_id:
            raise IntakeError("confirmed Case/source binding mismatch")
        if any(
            audit[key] != artifact[key]
            for key in ("confirmation_id", "confirmed_by", "confirmed_at")
        ):
            raise IntakeError("confirmed audit/artifact identity mismatch")
        transfers = [
            builder.AutomaticTransfer(
                **_object(
                    row,
                    "automatic transfer",
                    {"source_path", "target_path", "final_value"},
                )
            )
            for row in audit["automatic_transfers"]
        ]
        state = builder.CompositionState(
            items=copy.deepcopy(artifact["items"]),
            automatic_transfers=transfers,
            issues=[],
            preliminary_red_flags=[],
            supply_boundary=audit["supply_boundary_decision"],
            batch_decisions=audit.get("batch_decisions"),
        )
        for field in (
            "corrected_values",
            "resolved_conflicts",
            "accepted_nontechnical_assumptions",
            "not_applicable_technical_details",
            "removed_values",
        ):
            if not isinstance(audit[field], list):
                raise IntakeError("confirmed audit detail must be a list")
            setattr(state, field, audit[field])
        inputs = {name: (directory / name).read_bytes() for name in VERSIONED_FILES}
        snapshot = builder.InputSnapshot(
            paths=builder.resolve_case_paths(
                case_id,
                canonical_root=directory.parent.parent,
                extraction_version=directory.name.removeprefix("extraction-"),
            ),
            manifest_bytes=inputs[builder.MANIFEST_NAME],
            draft_bytes=inputs[builder.DRAFT_NAME],
            review_bytes=inputs[builder.REVIEW_NAME],
            hashes=files,
            draft=json.loads(inputs[builder.DRAFT_NAME], object_pairs_hook=_pairs),
        )
        if "future_review" in audit:
            record = _object(
                audit["future_review"],
                "confirmed future review",
                {"path", "sha256", "reviewed_facts"},
            )
            path = Path(_text(record["path"], "future review path"))
            if not path.is_absolute() or not path.is_file() or _unsafe_reparse(path):
                raise IntakeError("confirmed future review source is unsafe")
            review = builder.load_decisions_input(path)
            if (
                review.sha256 != record["sha256"]
                or review.data != record["reviewed_facts"]
            ):
                raise IntakeError("confirmed future review source drift")
            if review.data["future_context"] != artifact.get("future_context"):
                raise IntakeError("confirmed future context mismatch")
            # Reuse source/classification checks without publication.
            builder.attach_future_review(review, snapshot, state)
            if state.items != artifact["items"]:
                raise IntakeError("confirmed reviewed classification mismatch")
        expected = builder.build_decision_record(
            case_id=case_id,
            confirmation_id=artifact["confirmation_id"],
            approval_channel=_text(audit["approval_channel"], "approval channel"),
            confirmed_at=artifact["confirmed_at"],
            snapshot=snapshot,
            state=state,
            artifact_sha256=hashlib.sha256(raw[builder.ARTIFACT_NAME]).hexdigest(),
        )
        if audit != expected:
            raise IntakeError("confirmed canonical audit/source mismatch")
        receipt = builder.build_receipt(
            record=audit,
            decision_json_sha256=hashlib.sha256(
                raw[builder.DECISIONS_NAME]
            ).hexdigest(),
            state=state,
        ).encode("utf-8")
        if raw[builder.RECEIPT_NAME] != receipt:
            raise IntakeError("confirmed canonical receipt mismatch")
        if _unsafe_reparse(folder) or {p.name for p in folder.iterdir()} != names:
            raise IntakeError("confirmed output changed during verification")
        if any(
            _unsafe_reparse(folder / name) or (folder / name).read_bytes() != raw[name]
            for name in names
        ):
            raise IntakeError("confirmed output changed during verification")
    except (OSError, ValueError, KeyError, TypeError, builder.WorkflowError) as error:
        raise IntakeError(f"confirmed output verification failed: {error}") from error


def verify_versioned_extraction(
    directory: Path,
    *,
    case_id: str,
    version: str,
    base_manifest: Path,
    owned_staging: Path | None = None,
) -> str:
    """Verify immutable intake/binding and optional canonical confirmed output."""
    if VERSION_RE.fullmatch(version) is None:
        raise IntakeError("versioned extraction path/version mismatch")
    if owned_staging is None:
        if (
            directory.name != f"extraction-{version}"
            or directory.parent.name != case_id
        ):
            raise IntakeError("versioned extraction path/version mismatch")
    elif (
        directory != owned_staging / "bundle"
        or owned_staging.parent.name != case_id
        or not owned_staging.name.startswith(f".extraction-{version}-wrapper-")
        or _unsafe_reparse(owned_staging)
    ):
        raise IntakeError("versioned staging owner/path mismatch")
    if not directory.is_dir() or _unsafe_reparse(directory):
        raise IntakeError("versioned extraction directory is missing or unsafe")
    case_directory = directory.parent if owned_staging is None else owned_staging.parent
    if (
        _unsafe_reparse(case_directory)
        or not base_manifest.is_file()
        or _unsafe_reparse(base_manifest)
    ):
        raise IntakeError("versioned Case/base manifest path is unsafe")
    entries = {entry.name for entry in directory.iterdir()}
    expected_entries = VERSIONED_FILES | {"version-binding.json"}
    if owned_staging is None and "confirmed" in entries:
        expected_entries |= {"confirmed"}
    if entries != expected_entries:
        raise IntakeError("versioned extraction file set mismatch")
    binding_path = directory / "version-binding.json"
    if not binding_path.is_file() or _unsafe_reparse(binding_path):
        raise IntakeError("version binding file is missing or unsafe")
    try:
        binding_bytes = binding_path.read_bytes()
        binding = json.loads(binding_bytes.decode("utf-8"), object_pairs_hook=_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntakeError("version binding is unavailable or invalid") from error
    record = _object(
        binding,
        "version binding",
        {
            "schema_version",
            "case_id",
            "extraction_version",
            "base_manifest_sha256",
            "files",
        },
    )
    if (
        record["schema_version"] != "versioned_case_extraction_binding.v0.1"
        or record["case_id"] != case_id
        or record["extraction_version"] != version
    ):
        raise IntakeError("version binding identity mismatch")
    try:
        base_sha = hashlib.sha256(base_manifest.read_bytes()).hexdigest()
    except OSError as error:
        raise IntakeError(
            "base manifest cannot be read during version verification"
        ) from error
    if record["base_manifest_sha256"] != base_sha:
        raise IntakeError("version binding base manifest SHA-256 mismatch")
    files = _object(record["files"], "version binding files", set(VERSIONED_FILES))
    for name in VERSIONED_FILES:
        path = directory / name
        if not path.is_file() or _unsafe_reparse(path):
            raise IntakeError(f"versioned input is missing or unsafe: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != files[name]:
            raise IntakeError(f"versioned input SHA-256 mismatch: {name}")
    intake_data = json.loads(
        (directory / "governed-intake.json").read_text(encoding="utf-8")
    )
    pdf = Path(_text(intake_data.get("project_pdf_path"), "project_pdf_path"))
    intake = load_governed_intake(
        directory / "governed-intake.json",
        case_id=case_id,
        version=version,
        project_pdf=pdf,
        base_manifest=base_manifest,
    )
    manifest = json.loads(
        (directory / "source-bundle-manifest.txt").read_text(encoding="utf-8")
    )
    if manifest.get("governed_intake_sha256") != intake.sha256:
        raise IntakeError("manifest/governed intake SHA-256 mismatch")
    classifications = manifest.get("scope_classification")
    if not isinstance(classifications, list):
        raise IntakeError("scope classification is missing")
    if any(
        not isinstance(row, dict)
        or row.get("classification")
        not in {"requested_supply", "excluded_component", "project_context"}
        for row in classifications
    ):
        raise IntakeError("scope classification contains an unknown row")
    sources = manifest.get("sources")
    if (
        not isinstance(sources, list)
        or len(sources) != 1
        or not isinstance(sources[0], dict)
        or sources[0].get("source_type") != "pdf"
        or sources[0].get("sha256") != intake.project_pdf_sha256
    ):
        raise IntakeError("manifest project PDF identity mismatch")
    requested = {(name, quantity) for name, quantity in intake.requested_supply}
    excluded = {(name, quantity) for name, quantity in intake.excluded_components}
    actual_requested = {
        (row.get("designation"), row.get("quantity"))
        for row in classifications
        if isinstance(row, dict) and row.get("classification") == "requested_supply"
    }
    actual_excluded = {
        (row.get("designation"), row.get("quantity"))
        for row in classifications
        if isinstance(row, dict) and row.get("classification") == "excluded_component"
    }
    if actual_requested != requested or actual_excluded != excluded:
        raise IntakeError("scope classification differs from governed intake")
    decision_rows = [
        row
        for row in classifications
        if isinstance(row, dict)
        and row.get("classification") in {"requested_supply", "excluded_component"}
    ]
    if len(decision_rows) != len(requested) + len(excluded):
        raise IntakeError("scope classification contains duplicate decisions")
    draft = json.loads(
        (directory / "preliminary-composition-draft.json").read_text(encoding="utf-8")
    )
    items = draft.get("items") if isinstance(draft, dict) else None
    if not isinstance(items, list) or len(items) != len(intake.requested_supply):
        raise IntakeError("draft item set differs from governed requested supply")
    if [
        (item.get("product_name_guess"), item.get("quantity_guess"))
        for item in items
        if isinstance(item, dict)
    ] != list(intake.requested_supply):
        raise IntakeError("draft items differ from governed requested supply")
    if "confirmed" in entries:
        _verify_confirmed_output(directory, case_id, files)
    if {entry.name for entry in directory.iterdir()} != expected_entries:
        raise IntakeError("versioned extraction inventory changed during verification")
    if (
        _unsafe_reparse(directory)
        or _unsafe_reparse(binding_path)
        or binding_path.read_bytes() != binding_bytes
        or any(
            _unsafe_reparse(directory / name)
            or hashlib.sha256((directory / name).read_bytes()).hexdigest()
            != files[name]
            for name in VERSIONED_FILES
        )
    ):
        raise IntakeError("versioned bound files changed during verification")
    return hashlib.sha256(binding_bytes).hexdigest()
