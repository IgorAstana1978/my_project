"""Build a replay readiness bundle directly from frozen source artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

BUNDLE_NAME = "component_replay_readiness_bundle.json"
SCRIPTS_DIR = Path(__file__).resolve().parent


class ReplayBuildError(RuntimeError):
    """A fail-closed direct replay build failure."""


@dataclass(frozen=True)
class InputSnapshot:
    context: Any
    hashes: Mapping[Path, str]


@dataclass
class BuildResult:
    status: str = "FAIL"
    output_dir: Path | None = None
    output_created: bool = False
    validate_only: bool = False
    red_flags: list[str] = field(default_factory=list)


def _load_validator() -> ModuleType:
    path = SCRIPTS_DIR / "validate_component_replay_readiness_bundle.py"
    spec = importlib.util.spec_from_file_location(
        "component_replay_direct_validator_for_builder",
        path,
    )
    if spec is None or spec.loader is None:
        raise ReplayBuildError("could not load separate readiness validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _snapshot_inputs(context: Any) -> InputSnapshot:
    paths = [context.manifest_path]
    paths.extend(artifact.path for artifact in context.artifacts)
    hashes: dict[Path, str] = {}
    for path in paths:
        try:
            hashes[path] = _sha256(path.read_bytes())
        except OSError as exc:
            raise ReplayBuildError(f"could not snapshot direct input: {path}") from exc
    return InputSnapshot(context, hashes)


def _assert_inputs_unchanged(snapshot: InputSnapshot) -> None:
    for path, expected in snapshot.hashes.items():
        try:
            actual = _sha256(path.read_bytes())
        except OSError as exc:
            raise ReplayBuildError(
                f"direct input disappeared before publish: {path}"
            ) from exc
        if actual != expected:
            raise ReplayBuildError(f"input drift detected before publish: {path.name}")


def _builder_counts(bundle: Mapping[str, Any]) -> dict[str, int | float]:
    """Compute output count semantics independently from the validator."""
    positions = cast(list[Mapping[str, Any]], bundle["positions"])
    identified = cast(
        list[Mapping[str, Any]],
        bundle["identified_component_evidence_records"],
    )
    absences = cast(
        list[Mapping[str, Any]],
        bundle["component_absence_evidence"],
    )
    ids = [cast(str, item["component_evidence_id"]) for item in identified]
    if len(ids) != len(set(ids)):
        raise ReplayBuildError("builder found duplicate component evidence ID")
    field_entries = [
        entry
        for position in positions
        for entry in cast(
            list[Mapping[str, Any]],
            position["component_field_evidence"],
        )
    ]
    referenced = {cast(str, entry["component_evidence_id"]) for entry in field_entries}
    if not referenced <= set(ids):
        raise ReplayBuildError("builder found new component evidence ID")
    quantity_total: int | float = 0
    for position in positions:
        quantity = position["quantity"]
        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, (int, float))
            or quantity <= 0
        ):
            raise ReplayBuildError("builder found invalid position quantity")
        quantity_total += quantity
    return {
        "canonical_position_count": len(positions),
        "component_bearing_position_count": sum(
            bool(position["component_field_evidence"]) for position in positions
        ),
        "component_field_evidence_entry_count": len(field_entries),
        "component_absence_evidence_entry_count": len(absences),
        "identified_component_evidence_record_count": len(identified),
        "unique_component_evidence_id_count": len(set(ids)),
        "position_quantity_total": quantity_total,
    }


def _build_bundle(validator: ModuleType, snapshot: InputSnapshot) -> Mapping[str, Any]:
    bundle = validator.expected_bundle(snapshot.context)
    builder_counts = _builder_counts(bundle)
    if builder_counts != snapshot.context.projection.counts:
        raise ReplayBuildError("builder counts disagree with direct frozen projection")
    if builder_counts != bundle["counts"]:
        raise ReplayBuildError("builder counts disagree with output counts")
    return cast(Mapping[str, Any], bundle)


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _validate_output_dir(
    validator: ModuleType,
    context: Any,
    output_dir: Path,
) -> Path:
    resolved = validator.validate_output_location(context, output_dir)
    if resolved.exists():
        raise ReplayBuildError("output directory already exists; overwrite forbidden")
    if not resolved.parent.is_dir():
        raise ReplayBuildError("output parent directory does not exist")
    return cast(Path, resolved)


def _run_separate_validator(
    validator: ModuleType,
    manifest_path: Path,
    bundle_path: Path,
) -> None:
    validation = validator.validate_component_replay_readiness_bundle(
        manifest_path,
        bundle_path,
    )
    if validation.status != "PASS":
        details = "; ".join(validation.red_flags[:5])
        raise ReplayBuildError(f"separate validator failed: {details}")


def run_builder(
    *,
    intake_manifest: Path,
    output_dir: Path,
    validate_only: bool = False,
    before_drift_check: Callable[[], None] | None = None,
) -> BuildResult:
    result = BuildResult(
        output_dir=output_dir,
        validate_only=validate_only,
    )
    staging: Path | None = None
    resolved_output: Path | None = None
    try:
        validator = _load_validator()
        context = validator.load_intake_context(intake_manifest)
        resolved_output = _validate_output_dir(validator, context, output_dir)
        result.output_dir = resolved_output
        snapshot = _snapshot_inputs(context)
        bundle = _build_bundle(validator, snapshot)
        staging = resolved_output.parent / f".replay-readiness-{uuid.uuid4().hex}"
        staging.mkdir()
        bundle_path = staging / BUNDLE_NAME
        _write_exclusive(bundle_path, _canonical_json(bundle))
        _run_separate_validator(
            validator,
            context.manifest_path,
            bundle_path,
        )
        if before_drift_check is not None:
            before_drift_check()
        _assert_inputs_unchanged(snapshot)
        if validate_only:
            shutil.rmtree(staging)
            staging = None
        else:
            os.rename(staging, resolved_output)
            staging = None
            result.output_created = True
        result.status = "PASS"
    except (ReplayBuildError, OSError, RuntimeError) as exc:
        result.red_flags.append(str(exc))
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        if resolved_output is not None and resolved_output.exists():
            result.red_flags.append(
                "publication target appeared during failure; manual inspection required"
            )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a direct-input component replay readiness bundle."
    )
    parser.add_argument("--intake-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def format_report(result: BuildResult) -> str:
    lines = [
        "COMPONENT_REPLAY_READINESS_BUILD_REPORT_START",
        f"status: {result.status}",
        f"validate_only: {str(result.validate_only).lower()}",
        f"output_created: {str(result.output_created).lower()}",
    ]
    lines.extend(f"red_flag: {item}" for item in result.red_flags)
    lines.append("COMPONENT_REPLAY_READINESS_BUILD_REPORT_END")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_builder(
        intake_manifest=args.intake_manifest,
        output_dir=args.output_dir,
        validate_only=args.validate_only,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
