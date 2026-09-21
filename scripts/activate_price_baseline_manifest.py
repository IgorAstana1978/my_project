"""Publish one approved immutable baseline manifest and atomically select it."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]
from price_baseline_contract import (  # type: ignore[import-not-found]
    APPROVAL_AUTHORITY,
    APPROVAL_SCHEMA,
    DEFAULT_ACTIVE_SELECTOR,
    MANIFEST_SCHEMA,
    SELECTOR_SCHEMA,
    BaselineContractError,
    canonical_json_bytes,
    load_json_bytes,
    resolve_active_price_baseline,
    sha256_bytes,
    sha256_file,
    validate_manifest,
    validate_selector,
)

AUDIT_SCHEMA = "price_baseline_candidate_audit.v0.1"


class ActivationError(RuntimeError):
    """Approved candidate cannot be published or selected safely."""


@dataclass(frozen=True)
class ActivationResult:
    manifest_path: Path
    manifest_sha256: str
    selector_path: Path
    selector_sha256: str


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ActivationError(f"{label} fields mismatch")


def _read(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise ActivationError(f"{label} does not exist")
        return path.read_bytes()
    except OSError as exc:
        raise ActivationError(f"{label} could not be read") from exc


def _load(path: Path, label: str) -> tuple[bytes, Mapping[str, Any]]:
    raw = _read(path, label)
    try:
        return raw, load_json_bytes(raw, label)
    except BaselineContractError as exc:
        raise ActivationError(str(exc)) from exc


def validate_audit(data: Mapping[str, Any]) -> None:
    _exact_keys(
        data,
        {
            "schema_version",
            "status",
            "manifest_id",
            "predecessor",
            "candidate_workbook",
            "structural_compatibility",
            "changed_prices",
            "added_names",
            "removed_names",
            "conflicts",
            "mapping_snapshot",
            "hold_reasons",
            "approval_payload",
            "approval_fingerprint",
        },
        "candidate audit",
    )
    if (
        data["schema_version"] != AUDIT_SCHEMA
        or data["status"] != "PASS_CANDIDATE_ONLY"
        or data["structural_compatibility"] is not True
        or data["hold_reasons"] != []
        or data["added_names"] != []
        or data["removed_names"] != []
    ):
        raise ActivationError("candidate audit is not an activatable PASS")
    conflicts = data["conflicts"]
    if not isinstance(conflicts, Mapping) or any(conflicts.values()):
        raise ActivationError("candidate audit contains conflicts")
    payload = data["approval_payload"]
    if not isinstance(payload, Mapping):
        raise ActivationError("candidate approval payload is invalid")
    predecessor = cast(Mapping[str, Any], data["predecessor"])
    candidate = cast(Mapping[str, Any], data["candidate_workbook"])
    expected_payload = {
        "manifest_id": data["manifest_id"],
        "predecessor_manifest_id": predecessor.get("manifest_id"),
        "predecessor_manifest_sha256": predecessor.get("manifest_sha256"),
        "candidate_workbook_path": candidate.get("path"),
        "candidate_workbook_sha256": candidate.get("sha256"),
        "candidate_structural_fingerprint": candidate.get("structural_fingerprint"),
        "mapping_snapshot_sha256": sha256_bytes(
            canonical_json_bytes(data["mapping_snapshot"])
        ),
        "future_cases_only": True,
        "historical_repricing_authorized": False,
    }
    if dict(payload) != expected_payload:
        raise ActivationError("candidate approval payload/top-level audit mismatch")
    expected_fingerprint = sha256_bytes(canonical_json_bytes(payload))
    if data["approval_fingerprint"] != expected_fingerprint:
        raise ActivationError("candidate approval fingerprint mismatch")


def validate_approval(
    approval: Mapping[str, Any],
    *,
    audit_sha256: str,
    audit_fingerprint: str,
) -> None:
    _exact_keys(
        approval,
        {
            "schema_version",
            "authority",
            "approval_id",
            "approved_by",
            "approved_at",
            "candidate_audit_sha256",
            "approval_fingerprint",
        },
        "approval",
    )
    if (
        approval["schema_version"] != APPROVAL_SCHEMA
        or approval["authority"] != APPROVAL_AUTHORITY
        or approval["approved_by"] != "Igor"
    ):
        raise ActivationError("exact Igor approval authority mismatch")
    if approval["candidate_audit_sha256"] != audit_sha256:
        raise ActivationError("approval is not bound to exact candidate audit bytes")
    if approval["approval_fingerprint"] != audit_fingerprint:
        raise ActivationError("approval is not bound to candidate content")


def _build_manifest(
    audit: Mapping[str, Any], approval: Mapping[str, Any]
) -> dict[str, Any]:
    predecessor = cast(Mapping[str, Any], audit["predecessor"])
    candidate = cast(Mapping[str, Any], audit["candidate_workbook"])
    return {
        "schema_version": MANIFEST_SCHEMA,
        "manifest_id": audit["manifest_id"],
        "created_at": approval["approved_at"],
        "predecessor": {
            "manifest_id": predecessor["manifest_id"],
            "manifest_sha256": predecessor["manifest_sha256"],
        },
        "workbook": {
            "path": candidate["path"],
            "sha256": candidate["sha256"],
            "structural_fingerprint": candidate["structural_fingerprint"],
        },
        "mapping_snapshot": audit["mapping_snapshot"],
        "approval": dict(approval),
        "scope": {
            "future_cases_only": True,
            "historical_repricing_authorized": False,
        },
    }


def _normalized_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.replace("\xa0", " ").split())
    return normalized or None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 and value.is_integer() else None
    return None


def verify_snapshot_against_workbook(
    workbook_path: Path,
    snapshot: Any,
) -> None:
    try:
        workbook = load_workbook(
            workbook_path,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except (OSError, ValueError) as exc:
        raise ActivationError("candidate workbook could not be opened safely") from exc
    try:
        for raw_entry in cast(list[Mapping[str, Any]], snapshot):
            source = cast(Mapping[str, Any], raw_entry["source"])
            identity = cast(Mapping[str, Any], raw_entry["identity"])
            prices = cast(Mapping[str, Any], raw_entry["prices"])
            try:
                worksheet = workbook[cast(str, source["sheet"])]
            except KeyError as exc:
                raise ActivationError("mapping snapshot worksheet is missing") from exc
            label_cell = cast(str, source["label_cell"]).split("!", 1)[-1]
            actual_label = worksheet[label_cell].value
            expected_label = identity.get("expected_label")
            if identity.get("strict_label") is not True:
                actual_label = _normalized_label(actual_label)
                expected_label = _normalized_label(expected_label)
            if actual_label != expected_label:
                raise ActivationError("mapping identity drift before activation")
            values = []
            for coordinate in cast(list[str], source["price_cells"]):
                cell = coordinate.split("!", 1)[-1]
                raw_value = worksheet[cell].value
                if isinstance(raw_value, str) and raw_value.startswith("="):
                    raise ActivationError("formula price is forbidden")
                value = _positive_int(raw_value)
                if value is None:
                    raise ActivationError("mapping price is missing or invalid")
                values.append(value)
            expected_values = (
                [prices["material_kzt"], prices["work_kzt"]]
                if cast(str, raw_entry["mapping_kind"]).startswith("component_")
                else [prices["price_kzt"]]
            )
            if values != expected_values:
                raise ActivationError("mapping price snapshot/workbook mismatch")
    finally:
        workbook.close()


def verify_price_only_transition(
    predecessor_snapshot: Sequence[Mapping[str, Any]],
    candidate_snapshot: Any,
) -> None:
    candidate_entries = cast(list[Mapping[str, Any]], candidate_snapshot)
    predecessor_by_id = {
        cast(str, entry["mapping_id"]): entry for entry in predecessor_snapshot
    }
    candidate_by_id = {
        cast(str, entry["mapping_id"]): entry for entry in candidate_entries
    }
    if set(predecessor_by_id) != set(candidate_by_id):
        raise ActivationError("mapping identity membership changed")
    for mapping_id, predecessor in predecessor_by_id.items():
        candidate = candidate_by_id[mapping_id]
        predecessor_identity = {
            key: value for key, value in predecessor.items() if key != "prices"
        }
        candidate_identity = {
            key: value for key, value in candidate.items() if key != "prices"
        }
        if canonical_json_bytes(predecessor_identity) != canonical_json_bytes(
            candidate_identity
        ):
            raise ActivationError(
                f"mapping identity drift is not price approval: {mapping_id}"
            )


def _write_immutable(path: Path, content: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as exc:
        raise ActivationError("immutable manifest already exists") from exc
    except OSError as exc:
        raise ActivationError("immutable manifest could not be published") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_selector_atomically(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ActivationError("active selector atomic replacement failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def activate(
    *,
    candidate_audit_json: Path,
    approval_json: Path,
    active_selector: Path = DEFAULT_ACTIVE_SELECTOR,
) -> ActivationResult:
    audit_file = candidate_audit_json.resolve(strict=False)
    approval_file = approval_json.resolve(strict=False)
    selector_file = active_selector.resolve(strict=False)
    audit_raw, audit = _load(audit_file, "candidate audit")
    approval_raw, approval = _load(approval_file, "approval")
    validate_audit(audit)
    audit_sha = sha256_bytes(audit_raw)
    validate_approval(
        approval,
        audit_sha256=audit_sha,
        audit_fingerprint=cast(str, audit["approval_fingerprint"]),
    )

    selector_before = _read(selector_file, "active selector")
    try:
        active = resolve_active_price_baseline(selector_file)
    except BaselineContractError as exc:
        raise ActivationError(f"active predecessor is invalid: {exc}") from exc
    predecessor = cast(Mapping[str, Any], audit["predecessor"])
    if (
        predecessor.get("manifest_id") != active.manifest_id
        or predecessor.get("manifest_path") != str(active.manifest_path)
        or predecessor.get("manifest_sha256") != active.manifest_sha256
    ):
        raise ActivationError("candidate predecessor is no longer active")
    verify_price_only_transition(active.mapping_snapshot, audit["mapping_snapshot"])

    candidate = cast(Mapping[str, Any], audit["candidate_workbook"])
    candidate_path = Path(cast(str, candidate["path"])).resolve(strict=False)
    try:
        if sha256_file(candidate_path) != candidate["sha256"]:
            raise ActivationError("candidate workbook SHA-256 drifted")
    except OSError as exc:
        raise ActivationError("candidate workbook could not be rechecked") from exc

    manifest = _build_manifest(audit, approval)
    try:
        validate_manifest(manifest)
    except BaselineContractError as exc:
        raise ActivationError(f"candidate manifest contract failed: {exc}") from exc
    manifest_raw = canonical_json_bytes(manifest)
    manifest_sha = sha256_bytes(manifest_raw)
    manifest_dir = selector_file.parent / "manifests"
    if not selector_file.parent.is_dir():
        raise ActivationError("canonical price root does not exist")
    try:
        manifest_dir.mkdir(exist_ok=True)
    except OSError as exc:
        raise ActivationError("manifest directory could not be created") from exc
    manifest_path = manifest_dir / f"{audit['manifest_id']}.json"
    if manifest_path.parent != manifest_dir:
        raise ActivationError("unsafe manifest path")

    if (
        _read(audit_file, "candidate audit") != audit_raw
        or _read(approval_file, "approval") != approval_raw
        or _read(selector_file, "active selector") != selector_before
        or sha256_file(candidate_path) != candidate["sha256"]
    ):
        raise ActivationError("activation input drift detected before publication")
    verify_snapshot_against_workbook(candidate_path, audit["mapping_snapshot"])

    _write_immutable(manifest_path, manifest_raw)
    if _read(manifest_path, "published manifest") != manifest_raw:
        raise ActivationError("published manifest byte verification failed")
    if sha256_file(manifest_path) != manifest_sha:
        raise ActivationError("published manifest SHA-256 verification failed")

    selector = {
        "schema_version": SELECTOR_SCHEMA,
        "manifest_id": audit["manifest_id"],
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "activated_at": approval["approved_at"],
        "approval_id": approval["approval_id"],
    }
    try:
        validate_selector(selector)
    except BaselineContractError as exc:
        raise ActivationError(f"active selector contract failed: {exc}") from exc
    selector_raw = canonical_json_bytes(selector)
    if (
        _read(audit_file, "candidate audit") != audit_raw
        or _read(approval_file, "approval") != approval_raw
        or _read(selector_file, "active selector") != selector_before
        or sha256_file(candidate_path) != candidate["sha256"]
    ):
        raise ActivationError("activation input drift before selector replacement")
    _replace_selector_atomically(selector_file, selector_raw)
    if _read(selector_file, "active selector") != selector_raw:
        raise ActivationError("active selector byte verification failed")
    resolved = resolve_active_price_baseline(selector_file)
    if resolved.manifest_sha256 != manifest_sha or resolved.path != candidate_path:
        raise ActivationError("published selector chain verification failed")
    return ActivationResult(
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        selector_path=selector_file,
        selector_sha256=sha256_bytes(selector_raw),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-audit-json", type=Path, required=True)
    parser.add_argument("--approval-json", type=Path, required=True)
    parser.add_argument(
        "--active-selector",
        type=Path,
        default=DEFAULT_ACTIVE_SELECTOR,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = activate(
            candidate_audit_json=args.candidate_audit_json,
            approval_json=args.approval_json,
            active_selector=args.active_selector,
        )
    except (ActivationError, OSError) as exc:
        print(f"ACTIVATION HOLD: {exc}")
        return 1
    print("PRICE_BASELINE_ACTIVATION=PASS")
    print(f"MANIFEST={result.manifest_path}")
    print(f"MANIFEST_SHA256={result.manifest_sha256}")
    print(f"SELECTOR={result.selector_path}")
    print(f"SELECTOR_SHA256={result.selector_sha256}")
    print("HISTORICAL_REPRICING_AUTHORIZED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
