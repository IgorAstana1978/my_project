"""Apply a generic human decisions batch v0.22 as a non-mutating overlay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPLAY_SCHEMA_VERSION = "component_replay_readiness_bundle.v0.2"
BATCH_SCHEMA_VERSION = "human_decisions_batch.v0.22"
APPLIED_SCHEMA_VERSION = "component_replay_applied_bundle.v0.22"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_STATUS = "APPLIED"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DIRECT_COMPONENT_QUANTITY = "DIRECT_COMPONENT_QUANTITY"
CABINET_LEVEL_AGGREGATE = "CABINET_LEVEL_AGGREGATE"
SCOPE_EXCLUSION = "SCOPE_EXCLUSION"

CANONICAL_RECORD_FIELDS = {
    "component_evidence_id",
    "document_id",
    "label",
    "position_id",
    "provenance",
    "section_id",
    "source_status",
}
REPORT_START = "HUMAN_DECISIONS_BATCH_V022_APPLICATION_REPORT_START"
REPORT_END = "HUMAN_DECISIONS_BATCH_V022_APPLICATION_REPORT_END"


class V022ApplicationError(RuntimeError):
    """The inputs cannot be applied without violating the v0.22 contract."""


class DuplicateJsonKeyError(ValueError):
    """An input JSON object contains a duplicate key."""


@dataclass
class ApplicationResult:
    canonical_replay: Path
    batch_json: Path
    output_json: Path
    status: str = "FAIL"
    output_created: bool = False
    red_flags: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    canonical_replay_sha256: str | None = None
    batch_sha256: str | None = None


def _load_sibling(name: str, filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise V022ApplicationError(f"cannot load validator: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BATCH_VALIDATOR = _load_sibling(
    "validate_human_decisions_batch_v0_22_for_application",
    "validate_human_decisions_batch_v0_22.py",
)
APPLIED_VALIDATOR = _load_sibling(
    "validate_component_replay_applied_bundle_v0_22_for_application",
    "validate_component_replay_applied_bundle_v0_22.py",
)


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        content = path.read_bytes()
        value = json.loads(
            content,
            object_pairs_hook=_duplicate_key_guard,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        DuplicateJsonKeyError,
    ) as exc:
        raise V022ApplicationError(f"{label} cannot be read: {exc}") from exc
    return content, value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise V022ApplicationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise V022ApplicationError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V022ApplicationError(f"{label} must be a non-empty string")
    return value


def _validate_canonical_replay(value: Any) -> Mapping[str, Mapping[str, Any]]:
    replay = _mapping(value, "canonical replay")
    if replay.get("schema_version") != REPLAY_SCHEMA_VERSION:
        raise V022ApplicationError("canonical replay schema_version mismatch")
    _string(replay.get("project_id"), "canonical replay project_id")
    records = _list(
        replay.get("identified_component_evidence_records"),
        "canonical replay identified_component_evidence_records",
    )
    by_component: dict[str, Mapping[str, Any]] = {}
    for raw_record in records:
        record = _mapping(raw_record, "canonical component evidence record")
        if set(record) != CANONICAL_RECORD_FIELDS:
            raise V022ApplicationError(
                "canonical component evidence record fields mismatch"
            )
        component_id = _string(
            record["component_evidence_id"],
            "canonical component_evidence_id",
        )
        if component_id in by_component:
            raise V022ApplicationError("duplicate COMP in canonical replay")
        _string(record["document_id"], "canonical document_id")
        _string(record["label"], "canonical label")
        _string(record["position_id"], "canonical position_id")
        _string(record["section_id"], "canonical section_id")
        _string(record["source_status"], "canonical source_status")
        provenance = _mapping(record["provenance"], "canonical provenance")
        if not provenance:
            raise V022ApplicationError("canonical provenance must be non-empty")
        by_component[component_id] = record
    if not by_component:
        raise V022ApplicationError(
            "canonical replay must contain component evidence records"
        )
    return by_component


def _canonical_locator(record: Mapping[str, Any]) -> str:
    provenance = _mapping(record["provenance"], "canonical provenance")
    row_locator = _string(
        provenance.get("row_locator"),
        "canonical provenance row_locator",
    )
    specification_locator = _string(
        provenance.get("specification_position_or_locator"),
        "canonical provenance specification_position_or_locator",
    )
    return f"{row_locator}; {specification_locator}"


def _project_member(
    member_value: Any,
    signature: Mapping[str, Any],
    canonical_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    member = _mapping(member_value, "batch decision member")
    component_id = _string(
        member.get("component_evidence_id"),
        "batch member component_evidence_id",
    )
    try:
        canonical = canonical_records[component_id]
    except KeyError as exc:
        raise V022ApplicationError(
            f"batch COMP is absent from canonical replay: {component_id}"
        ) from exc
    checks = {
        "evidence_position_id": canonical["position_id"],
        "section": canonical["section_id"],
        "source_locator": _canonical_locator(canonical),
    }
    for field_name, expected in checks.items():
        if member.get(field_name) != expected:
            raise V022ApplicationError(
                f"{component_id} {field_name} does not match canonical replay"
            )
    if signature["component_identity"] != canonical["label"]:
        raise V022ApplicationError(
            f"{component_id} component identity does not match canonical replay"
        )
    return {
        "component_evidence_id": component_id,
        "evidence_position_id": member["evidence_position_id"],
        "section": member["section"],
        "source_locator": member["source_locator"],
        "canonical_label": canonical["label"],
        "canonical_document_id": canonical["document_id"],
        "canonical_source_status": canonical["source_status"],
        "canonical_provenance": copy.deepcopy(canonical["provenance"]),
    }


def _project_decision(
    decision_value: Any,
    canonical_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    decision = _mapping(decision_value, "batch quantity decision")
    signature = _mapping(decision["component_signature"], "component_signature")
    projected = {
        "decision_id": decision["decision_id"],
        "decision_code": decision["decision_code"],
        "decision_kind": decision["decision_kind"],
        "component_signature": copy.deepcopy(signature),
        "members": [
            _project_member(member, signature, canonical_records)
            for member in _list(decision["members"], "decision members")
        ],
        "application_status": APPLICATION_STATUS,
    }
    kind = decision["decision_kind"]
    if kind == DIRECT_COMPONENT_QUANTITY:
        projected["quantity_per_cabinet"] = decision["quantity_per_cabinet"]
    elif kind == CABINET_LEVEL_AGGREGATE:
        projected.update(
            {
                "aggregate_quantity_per_cabinet": decision[
                    "aggregate_quantity_per_cabinet"
                ],
                "applies_once_per_cabinet": True,
                "multiply_by_member_count": False,
            }
        )
    elif kind == SCOPE_EXCLUSION:
        projected.update(
            {
                "scope_status": decision["scope_status"],
                "future_inclusion_requires": decision["future_inclusion_requires"],
                "prohibited_downstream": copy.deepcopy(
                    decision["prohibited_downstream"]
                ),
            }
        )
    else:
        raise V022ApplicationError(f"unknown decision_kind: {kind}")
    return projected


def build_applied_value(
    canonical_value: Any,
    batch_value: Any,
    canonical_sha256: str,
    batch_sha256: str,
) -> dict[str, Any]:
    """Build and independently validate an in-memory applied overlay."""

    canonical = _mapping(canonical_value, "canonical replay")
    batch = _mapping(batch_value, "batch v0.22")
    canonical_records = _validate_canonical_replay(canonical)
    try:
        batch_counts = dict(BATCH_VALIDATOR.validate_batch_value(batch))
    except Exception as exc:
        if exc.__class__.__module__ == "builtins":
            raise
        raise V022ApplicationError(f"batch v0.22 validation failed: {exc}") from exc

    project_id = _string(canonical["project_id"], "canonical replay project_id")
    if batch.get("project_id") != project_id:
        raise V022ApplicationError("project_id mismatch between replay and batch")
    bindings = _mapping(batch["source_bindings"], "batch source_bindings")
    if bindings.get("canonical_bundle_sha256") != canonical_sha256:
        raise V022ApplicationError("batch canonical source lineage SHA-256 mismatch")

    projections = {
        DIRECT_COMPONENT_QUANTITY: [],
        CABINET_LEVEL_AGGREGATE: [],
        SCOPE_EXCLUSION: [],
    }
    for decision_value in _list(
        batch["quantity_decisions"],
        "batch quantity_decisions",
    ):
        decision = _mapping(decision_value, "batch quantity decision")
        kind = cast(str, decision["decision_kind"])
        projections[kind].append(_project_decision(decision, canonical_records))

    applied = {
        "schema_version": APPLIED_SCHEMA_VERSION,
        "project_id": project_id,
        "application_status": APPLICATION_STATUS,
        "authority": AUTHORITY,
        "source_lineage": {
            "canonical_replay_sha256": canonical_sha256,
            "canonical_replay_schema_version": REPLAY_SCHEMA_VERSION,
            "human_decisions_batch_sha256": batch_sha256,
            "human_decisions_batch_schema_version": BATCH_SCHEMA_VERSION,
            "batch_id": batch["batch_id"],
            "prior_batch_id": batch["prior_batch_id"],
        },
        "direct_component_quantities": projections[DIRECT_COMPONENT_QUANTITY],
        "cabinet_level_aggregates": projections[CABINET_LEVEL_AGGREGATE],
        "scope_exclusions": projections[SCOPE_EXCLUSION],
        "coverage": batch_counts,
        "confirmed_composition_created": False,
        "pricing_started": False,
        "downstream_started": False,
    }
    try:
        APPLIED_VALIDATOR.validate_applied_value(applied)
    except Exception as exc:
        if exc.__class__.__module__ == "builtins":
            raise
        raise V022ApplicationError(
            f"generated applied bundle validation failed: {exc}"
        ) from exc
    return applied


def _serialize(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _validated_output_path(output_json: Path) -> Path:
    output_path = output_json.expanduser().resolve(strict=False)
    if output_path.is_relative_to(PROJECT_ROOT.resolve(strict=False)):
        raise V022ApplicationError("output JSON must be outside the Git project")
    return output_path


def _atomic_write(output_json: Path, content: bytes, overwrite: bool) -> None:
    parent = output_json.parent
    if not parent.is_dir():
        raise V022ApplicationError("output parent directory does not exist")
    if output_json.exists() and not overwrite:
        raise V022ApplicationError("output already exists; use --overwrite explicitly")

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{output_json.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, output_json)
        else:
            os.link(temporary_path, output_json)
            temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def apply_artifacts(
    canonical_replay: Path,
    batch_json: Path,
    output_json: Path,
    *,
    overwrite: bool = False,
) -> ApplicationResult:
    """Validate inputs and atomically write one deterministic applied overlay."""

    result = ApplicationResult(canonical_replay, batch_json, output_json)
    try:
        output_path = _validated_output_path(output_json)
        result.output_json = output_path
        if output_path.exists() and not overwrite:
            raise V022ApplicationError(
                "output already exists; use --overwrite explicitly"
            )
        canonical_content, canonical_value = _load_json(
            canonical_replay,
            "canonical replay",
        )
        batch_content, batch_value = _load_json(batch_json, "batch v0.22")
        result.canonical_replay_sha256 = hashlib.sha256(canonical_content).hexdigest()
        result.batch_sha256 = hashlib.sha256(batch_content).hexdigest()
        applied = build_applied_value(
            canonical_value,
            batch_value,
            result.canonical_replay_sha256,
            result.batch_sha256,
        )
        result.counts = dict(applied["coverage"])
        _atomic_write(output_path, _serialize(applied), overwrite)
        result.output_created = True
        result.status = "PASS"
    except (
        V022ApplicationError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        result.red_flags.append(str(exc))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply human_decisions_batch.v0.22 to a canonical component replay "
            "as a non-mutating overlay."
        )
    )
    parser.add_argument("--canonical-replay", required=True, type=Path)
    parser.add_argument("--batch-json", required=True, type=Path)
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
        help="New applied overlay JSON path outside the Git project",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Atomically replace an existing outside-Git output; this never permits "
            "an output inside the Git project"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = apply_artifacts(
        args.canonical_replay,
        args.batch_json,
        args.output_json,
        overwrite=args.overwrite,
    )
    print(REPORT_START)
    print(f"status: {result.status}")
    print(f"output_created: {str(result.output_created).lower()}")
    if result.status == "PASS":
        print(f"canonical_replay_sha256: {result.canonical_replay_sha256}")
        print(f"batch_sha256: {result.batch_sha256}")
        for key, value in result.counts.items():
            print(f"{key}: {value}")
    else:
        print(f"red_flag: {result.red_flags[0]}")
    print(REPORT_END)
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
