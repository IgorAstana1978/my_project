"""Publish one immutable price-only application successor for Invoice 519."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_PUBLISHER_PATH = Path(__file__).with_name(
    "publish_invoice519_price_human_decision.py"
)
SCHEMA_VERSION = "invoice519_price_application.v0.1"
SCHEMA_FILENAME = "invoice519_price_application_v0_1.schema.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / SCHEMA_FILENAME
OUTPUT_FILENAME = "invoice519-price-application-v0.1.json"
PROJECT_ID = "2024/086"
INVOICE_NUMBER = 519
APPLICATION_ID = "IGOR-INVOICE519-PRICE-APPLICATION-2024-086-001"
STATUS = "IGOR_INVOICE519_PRICE_APPLIED_QUOTE_NOT_GENERATED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPLICATION_SCOPE = "PRICE_ONLY"
APPLICATION_STATUS = "APPLIED"
APPROVED_PRICE_KZT = 19_499_186
PREDECESSOR_PATH = Path(
    r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-"
    "2024-086-INVOICE519-PRICE-HUMAN-DECISION-20260827-001\\"
    "invoice519-price-human-decision-v0.1.json"
)
PREDECESSOR_SHA256 = "64d78cb69b00eeb89288793c9867be078e9bfc20c590eaa459bd5fed84635e4c"
PUBLICATION_AUTHORIZATION = "IGOR_INVOICE519_PRICE_APPLICATION_PUBLICATION_AUTHORIZED"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CREATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

PRICE_APPLICATION = {
    "approved_price_kzt": APPROVED_PRICE_KZT,
    "applied_price_kzt": APPROVED_PRICE_KZT,
    "currency": "KZT",
    "authority": AUTHORITY,
    "application_scope": APPLICATION_SCOPE,
    "application_status": APPLICATION_STATUS,
    "positions_recalculated": False,
    "technical_composition_changed": False,
    "reconciliation_preserved": True,
}
SAFETY = {
    "human_decision_recorded": True,
    "price_approved": True,
    "price_application_authorized": True,
    "price_applied": True,
    "quote_generation_authorized": False,
    "invoice_generation_authorized": False,
    "quote_or_invoice_publication_authorized": False,
    "client_send_authorized": False,
    "lead_time_approved": False,
    "procurement_authorized": False,
    "reserve_authorized": False,
    "prepayment_authorized": False,
    "production_authorized": False,
    "downstream_authorized": False,
}
PUBLICATION_CONTROL = {
    "immutable": True,
    "no_overwrite": True,
    "atomic_publication": True,
    "input_toctou_recheck_required": True,
    "final_strict_json_reread_required": True,
    "authorization_token_required": True,
}


class ContractError(ValueError):
    """The requested price application would violate the closed contract."""


@dataclass(frozen=True)
class LoadedPredecessor:
    path: Path
    raw: bytes
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_predecessor_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "publish_invoice519_price_human_decision_for_application",
        PREDECESSOR_PUBLISHER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Invoice 519 price Human Decision publisher is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


predecessor = load_predecessor_module()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_sha256(value: str, description: str) -> None:
    require(
        SHA256_RE.fullmatch(value) is not None,
        f"{description} must be 64 lowercase hexadecimal characters",
    )


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = predecessor.load_json_bytes(raw, description)
    except OSError as exc:
        raise ContractError(f"{description} could not be read: {exc}") from exc
    except predecessor.ContractError as exc:
        raise ContractError(str(exc)) from exc
    return dict(value), raw


def require_mapping(value: Any, description: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{description} must be an object")
    return cast(Mapping[str, Any], value)


def require_list(value: Any, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be an array")
    return cast(list[Any], value)


def _validate_predecessor_payload(payload: Mapping[str, Any]) -> None:
    try:
        predecessor.validate_payload(payload)
    except predecessor.ContractError as exc:
        raise ContractError(f"predecessor contract mismatch: {exc}") from exc
    require(
        payload.get("schema_version") == predecessor.SCHEMA_VERSION,
        "predecessor schema mismatch",
    )
    require(payload.get("decision_id") == predecessor.DECISION_ID, "decision ID drift")
    require(payload.get("status") == predecessor.STATUS, "predecessor status mismatch")
    require(
        payload.get("approval_scope") == predecessor.APPROVAL_SCOPE,
        "predecessor approval scope mismatch",
    )
    require(
        payload.get("application_status") == predecessor.APPLICATION_STATUS,
        "predecessor application status mismatch",
    )
    approval = require_mapping(payload.get("price_approval"), "price approval")
    require(
        approval.get("approved_price_kzt") == APPROVED_PRICE_KZT,
        "predecessor approved price mismatch",
    )
    require(
        payload.get("reconciliation") == predecessor._reconciliation_payload(),
        "predecessor reconciliation mismatch",
    )
    require(payload.get("safety") == predecessor.SAFETY, "predecessor safety mismatch")


def load_and_validate_predecessor(
    path: Path, expected_sha256: str
) -> LoadedPredecessor:
    validate_sha256(expected_sha256, "predecessor expected SHA")
    require(expected_sha256 == PREDECESSOR_SHA256, "predecessor SHA binding mismatch")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"predecessor path unavailable: {exc}") from exc
    require(
        resolved == PREDECESSOR_PATH.resolve(strict=False),
        "predecessor path binding mismatch",
    )
    payload, raw = load_json(resolved, "price Human Decision predecessor")
    require(sha256_bytes(raw) == PREDECESSOR_SHA256, "predecessor initial SHA mismatch")
    _validate_predecessor_payload(payload)
    return LoadedPredecessor(resolved, raw, payload)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _predecessor_binding(loaded: LoadedPredecessor) -> dict[str, Any]:
    return {
        "role": "price_human_decision",
        "path": str(loaded.path),
        "expected_sha256": PREDECESSOR_SHA256,
        "actual_sha256": sha256_bytes(loaded.raw),
        "schema_version": predecessor.SCHEMA_VERSION,
        "decision_id": predecessor.DECISION_ID,
        "status": predecessor.STATUS,
        "application_status": predecessor.APPLICATION_STATUS,
    }


def _technical_composition() -> dict[str, Any]:
    technical = next(
        spec
        for spec in predecessor.INPUT_SPECS
        if spec.role == "completed_technical_input"
    )
    return {
        "status": "UNCHANGED_FROM_PREDECESSOR",
        "source_role": technical.role,
        "path": technical.path,
        "sha256": technical.sha256,
    }


def build_payload(
    loaded: LoadedPredecessor, created_at_utc: str | None = None
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    require(CREATED_AT_RE.fullmatch(created) is not None, "created_at_utc format")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "IMMUTABLE_PRICE_APPLICATION_SUCCESSOR",
        "project_id": PROJECT_ID,
        "invoice_number": INVOICE_NUMBER,
        "application_id": APPLICATION_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "application_scope": APPLICATION_SCOPE,
        "application_status": APPLICATION_STATUS,
        "created_at_utc": created,
        "predecessor": _predecessor_binding(loaded),
        "source_input_bindings": copy.deepcopy(loaded.payload["input_bindings"]),
        "price_application": copy.deepcopy(PRICE_APPLICATION),
        "reconciliation": copy.deepcopy(loaded.payload["reconciliation"]),
        "technical_composition": _technical_composition(),
        "safety": copy.deepcopy(SAFETY),
        "publication_control": copy.deepcopy(PUBLICATION_CONTROL),
    }
    validate_payload(payload)
    return payload


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed price application schema")
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema dialect mismatch",
    )
    require(schema.get("type") == "object", "schema root type mismatch")
    require(schema.get("additionalProperties") is False, "schema must be closed")
    properties = require_mapping(schema.get("properties"), "schema properties")
    schema_version = require_mapping(
        properties.get("schema_version"), "schema schema_version"
    )
    require(schema_version.get("const") == SCHEMA_VERSION, "schema version contract")
    return schema


def _validate_source_input_bindings(value: Any) -> None:
    bindings = require_list(value, "source input bindings")
    require(len(bindings) == len(predecessor.INPUT_SPECS), "input binding count")
    for binding, spec in zip(bindings, predecessor.INPUT_SPECS, strict=True):
        item = require_mapping(binding, "source input binding")
        require(item.get("role") == spec.role, f"{spec.role} role mismatch")
        require(item.get("path") == spec.path, f"{spec.role} path mismatch")
        require(
            item.get("expected_sha256") == spec.sha256,
            f"{spec.role} expected SHA mismatch",
        )
        require(
            item.get("actual_sha256") == spec.sha256,
            f"{spec.role} actual SHA mismatch",
        )
        require(item.get("media_type") == spec.media_type, f"{spec.role} media type")


def validate_payload(payload: Mapping[str, Any]) -> None:
    try:
        predecessor.validate_against_schema(payload, load_schema())
    except predecessor.ContractError as exc:
        raise ContractError(str(exc)) from exc
    binding = require_mapping(payload.get("predecessor"), "predecessor binding")
    require(binding.get("path") == str(PREDECESSOR_PATH.resolve(strict=False)), "path")
    require(binding.get("expected_sha256") == PREDECESSOR_SHA256, "expected SHA")
    require(binding.get("actual_sha256") == PREDECESSOR_SHA256, "actual SHA")
    _validate_source_input_bindings(payload.get("source_input_bindings"))
    require(payload.get("price_application") == PRICE_APPLICATION, "price application")
    reconciliation = payload.get("reconciliation")
    require(
        reconciliation == predecessor._reconciliation_payload(),
        "reconciliation preservation mismatch",
    )
    try:
        predecessor.validate_reconciliation(reconciliation)
    except predecessor.ContractError as exc:
        raise ContractError(f"reconciliation mismatch: {exc}") from exc
    require(
        payload.get("technical_composition") == _technical_composition(),
        "technical composition drift",
    )
    require(payload.get("safety") == SAFETY, "safety boundary mismatch")


def serialize(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _path_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _rollback_publication(
    output: Path,
    staging: Path | None,
    final_link_created: bool,
    staged_identity: tuple[int, int] | None,
) -> list[str]:
    blockers: list[str] = []
    if final_link_created and os.path.lexists(output):
        try:
            if _path_identity(output) == staged_identity:
                output.unlink()
            else:
                blockers.append("foreign final replacement preserved")
        except OSError as exc:
            blockers.append(f"final output cleanup failed: {exc}")
    if staging is not None and os.path.lexists(staging):
        try:
            staging.unlink()
        except OSError as exc:
            blockers.append(f"staging cleanup failed: {exc}")
    if output.parent.exists():
        try:
            output.parent.rmdir()
        except OSError as exc:
            blockers.append(f"output directory cleanup failed: {exc}")
    return blockers


def publish_application(
    predecessor_path: Path,
    predecessor_sha256: str,
    output: Path,
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    require(
        not output.resolve(strict=False).is_relative_to(REPO_ROOT),
        "output must be outside repository",
    )
    loaded = load_and_validate_predecessor(predecessor_path, predecessor_sha256)
    require(
        output.resolve(strict=False) != loaded.path, "output must not alias predecessor"
    )
    payload = build_payload(loaded)
    encoded = serialize(payload)
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    staged_identity: tuple[int, int] | None = None
    final_link_created = False
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".staging", dir=output.parent
        )
        staging = Path(staging_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged, staged_raw = load_json(staging, "staged price application")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged)
        require(
            set(output.parent.iterdir()) == {staging},
            "output directory contains unexpected entries before publication",
        )
        try:
            current = loaded.path.read_bytes()
        except OSError as exc:
            raise ContractError(f"TOCTOU reread failed: predecessor: {exc}") from exc
        require(current == loaded.raw, "TOCTOU bytes changed: predecessor")
        require(
            sha256_bytes(current) == PREDECESSOR_SHA256,
            "TOCTOU SHA mismatch: predecessor",
        )
        require(not output.exists(), "output appeared before publication")
        staged_identity = _path_identity(staging)
        try:
            os.link(staging, output)
        except OSError as exc:
            raise ContractError(
                f"atomic no-overwrite publication failed: {exc}"
            ) from exc
        final_link_created = True
        require(
            _path_identity(output) == staged_identity,
            "published final identity mismatch",
        )
        published, published_raw = load_json(output, "published price application")
        require(published_raw == encoded, "published bytes mismatch")
        validate_payload(published)
        staging.unlink()
        require(
            _path_identity(output) == staged_identity,
            "published final identity changed before success",
        )
        require(
            set(output.parent.iterdir()) == {output},
            "output directory final inventory mismatch",
        )
        return PublicationResult(
            sha256_bytes(published_raw), len(published_raw), encoded
        )
    except BaseException as error:
        blockers: list[str] = []
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                blockers.append(f"staging descriptor cleanup failed: {exc}")
        blockers.extend(
            _rollback_publication(output, staging, final_link_created, staged_identity)
        )
        if blockers:
            raise ContractError(
                "publication rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--price-human-decision", required=True, type=Path)
    parser.add_argument("--price-human-decision-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact Invoice 519 price application publication authorization is required",
    )
    result = publish_application(
        cast(Path, args.price_human_decision),
        cast(str, args.price_human_decision_sha256),
        cast(Path, args.output),
    )
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
