"""Publish the immutable Invoice 519 YAUO enclosure Human Decision."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
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
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
INSPECTOR_PATH = Path(__file__).with_name("inspect_excel_template.py")
SCHEMA_VERSION = "invoice519_yauo_enclosure_human_decision.v0.1"
SCHEMA_FILENAME = "invoice519_yauo_enclosure_human_decision_v0_1.schema.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / SCHEMA_FILENAME
OUTPUT_FILENAME = "invoice519-yauo-enclosure-human-decision-v0.1.json"
PROJECT_ID = "2024/086"
INVOICE_NUMBER = 519
DECISION_ID = "IGOR-INVOICE519-YAUO-ENCLOSURE-2024-086-001"
STATUS = "IGOR_INVOICE519_YAUO_ENCLOSURE_APPROVED_NOT_APPLIED_TO_QUOTE"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPROVAL_SCOPE = "ENCLOSURE_DIMENSIONS_ONLY"
QUOTE_APPLICATION_STATUS = "NOT_APPLIED"
CANONICAL_WORKBOOK_PATH = Path(
    r"C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx"
)
CANONICAL_WORKBOOK_SHA256 = (
    "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5"
)
CANONICAL_WORKSHEET = "Лист1"
CANONICAL_CELL = "G111"
CANONICAL_CELL_VALUE = "Накладной 450х300х250 металл 1,2мм"
PUBLICATION_AUTHORIZATION = (
    "IGOR_INVOICE519_YAUO_ENCLOSURE_HUMAN_DECISION_PUBLICATION_AUTHORIZED"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CREATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

TECHNICAL_DECISION = {
    "invoice_position_number": 87,
    "product_identity": "YAUO9601_3474",
    "field": "enclosure_dimensions",
    "previous_value": "450×300×250 mm",
    "approved_value": "400×300×250 mm",
    "change_scope": "POSITION_87_ENCLOSURE_ONLY",
    "quote_application_status": QUOTE_APPLICATION_STATUS,
}
SAFETY = {
    "human_decision_recorded": True,
    "technical_decision_recorded": True,
    "quote_application_authorized": False,
    "quote_generation_authorized": False,
    "invoice_generation_authorized": False,
    "quote_publication_authorized": False,
    "invoice_publication_authorized": False,
    "client_send_authorized": False,
    "procurement_authorized": False,
    "reserve_authorized": False,
    "prepayment_authorized": False,
    "production_authorized": False,
    "downstream_authorized": False,
}
PUBLICATION_CONTROL = {
    "immutable": True,
    "no_overwrite": True,
    "new_directory_required": True,
    "atomic_publication": True,
    "input_toctou_recheck_required": True,
    "final_strict_json_reread_required": True,
    "rollback_on_failure": True,
    "authorization_token_required": True,
}


class ContractError(ValueError):
    """The requested publication would violate the closed contract."""


class DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


@dataclass(frozen=True)
class LoadedCanonicalSource:
    path: Path
    raw: bytes
    cell_value: str


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_inspector_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "inspect_excel_template_for_yauo_decision", INSPECTOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Excel template inspector is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


inspector = load_inspector_module()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_sha256(value: str, description: str) -> None:
    require(
        SHA256_RE.fullmatch(value) is not None,
        f"{description} must be 64 lowercase hexadecimal characters",
    )


def load_json_bytes(raw: bytes, description: str) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{description} must be strict UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
        raise ContractError(f"{description} is not strict JSON: {exc}") from exc
    require(isinstance(value, Mapping), f"{description} root must be an object")
    return cast(Mapping[str, Any], value)


def load_json(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"{description} could not be read: {exc}") from exc
    return dict(load_json_bytes(raw, description)), raw


def require_mapping(value: Any, description: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{description} must be an object")
    return cast(Mapping[str, Any], value)


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return type(value) is int
    if expected_type == "boolean":
        return type(value) is bool
    raise ContractError(f"unsupported schema type: {expected_type}")


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def validate_against_schema(
    value: Any, schema: Mapping[str, Any], path: str = "$"
) -> None:
    if "const" in schema:
        require(_json_equal(value, schema["const"]), f"schema const mismatch at {path}")
    expected_type = schema.get("type")
    if expected_type is not None:
        require(
            isinstance(expected_type, str)
            and _schema_type_matches(value, expected_type),
            f"schema type mismatch at {path}",
        )
    if isinstance(value, str):
        if "minLength" in schema:
            require(len(value) >= schema["minLength"], f"schema minLength at {path}")
        if "pattern" in schema:
            require(
                re.search(schema["pattern"], value) is not None,
                f"schema pattern at {path}",
            )
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        require(isinstance(required, list), f"schema required invalid at {path}")
        missing = [key for key in required if key not in value]
        require(not missing, f"schema missing keys at {path}: {missing}")
        properties = schema.get("properties", {})
        require(isinstance(properties, Mapping), f"schema properties invalid at {path}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            require(not extra, f"schema extra keys at {path}: {sorted(extra)}")
        for key, child in properties.items():
            if key in value:
                validate_against_schema(
                    value[key],
                    require_mapping(child, f"schema {path}.{key}"),
                    f"{path}.{key}",
                )


def _read_canonical_cell(raw: bytes) -> str:
    try:
        with ZipFile(io.BytesIO(raw), "r") as archive:
            shared_strings = inspector.load_shared_strings(archive)
            sheets = inspector.workbook_sheets(archive)
            matches = [part for name, part in sheets if name == CANONICAL_WORKSHEET]
            require(len(matches) == 1, "canonical worksheet binding mismatch")
            worksheet = inspector.read_xml_part(archive, matches[0])
            cells = [
                cell
                for cell in worksheet.findall(".//main:c", inspector.NS)
                if cell.get("r") == CANONICAL_CELL
            ]
            require(len(cells) == 1, "canonical source cell binding mismatch")
            value = inspector.cell_value(cells[0], shared_strings)
    except (BadZipFile, KeyError, ParseError, ValueError) as exc:
        raise ContractError(
            f"canonical workbook could not be inspected: {exc}"
        ) from exc
    require(value == CANONICAL_CELL_VALUE, "canonical source cell value mismatch")
    return cast(str, value)


def load_and_validate_canonical_source(
    path: Path, expected_sha256: str
) -> LoadedCanonicalSource:
    validate_sha256(expected_sha256, "canonical workbook expected SHA")
    require(
        expected_sha256 == CANONICAL_WORKBOOK_SHA256,
        "canonical workbook SHA binding mismatch",
    )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"canonical workbook path unavailable: {exc}") from exc
    require(
        resolved == CANONICAL_WORKBOOK_PATH.resolve(strict=False),
        "canonical workbook path binding mismatch",
    )
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise ContractError(f"canonical workbook could not be read: {exc}") from exc
    require(
        sha256_bytes(raw) == CANONICAL_WORKBOOK_SHA256,
        "canonical workbook initial SHA mismatch",
    )
    return LoadedCanonicalSource(resolved, raw, _read_canonical_cell(raw))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_binding(source: LoadedCanonicalSource) -> dict[str, Any]:
    return {
        "role": "canonical_invoice_519",
        "path": str(source.path),
        "expected_sha256": CANONICAL_WORKBOOK_SHA256,
        "actual_sha256": sha256_bytes(source.raw),
        "media_type": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        "worksheet": CANONICAL_WORKSHEET,
        "cell": CANONICAL_CELL,
        "canonical_cell_value": source.cell_value,
    }


def build_payload(
    source: LoadedCanonicalSource, created_at_utc: str | None = None
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    require(CREATED_AT_RE.fullmatch(created) is not None, "created_at_utc format")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "IMMUTABLE_HUMAN_DECISION_CAPTURE",
        "project_id": PROJECT_ID,
        "invoice_number": INVOICE_NUMBER,
        "decision_id": DECISION_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "approval_scope": APPROVAL_SCOPE,
        "quote_application_status": QUOTE_APPLICATION_STATUS,
        "created_at_utc": created,
        "source_binding": _source_binding(source),
        "technical_decision": copy.deepcopy(TECHNICAL_DECISION),
        "safety": copy.deepcopy(SAFETY),
        "publication_control": copy.deepcopy(PUBLICATION_CONTROL),
    }
    validate_payload(payload)
    return payload


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed YAUO decision schema")
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema dialect mismatch",
    )
    require(schema.get("type") == "object", "schema root type mismatch")
    require(schema.get("additionalProperties") is False, "schema must be closed")
    properties = require_mapping(schema.get("properties"), "schema properties")
    require(
        require_mapping(properties.get("schema_version"), "schema version").get("const")
        == SCHEMA_VERSION,
        "schema version contract",
    )
    require(
        require_mapping(properties.get("technical_decision"), "schema decision").get(
            "const"
        )
        == TECHNICAL_DECISION,
        "schema technical decision contract",
    )
    require(
        require_mapping(properties.get("safety"), "schema safety").get("const")
        == SAFETY,
        "schema safety contract",
    )
    return schema


def validate_payload(payload: Mapping[str, Any]) -> None:
    validate_against_schema(payload, load_schema())
    binding = require_mapping(payload.get("source_binding"), "source binding")
    require(
        binding.get("path") == str(CANONICAL_WORKBOOK_PATH.resolve(strict=False)),
        "canonical source binding path mismatch",
    )
    require(
        binding.get("expected_sha256") == CANONICAL_WORKBOOK_SHA256,
        "canonical source binding expected SHA mismatch",
    )
    require(
        binding.get("actual_sha256") == CANONICAL_WORKBOOK_SHA256,
        "canonical source binding actual SHA mismatch",
    )
    require(
        payload.get("technical_decision") == TECHNICAL_DECISION,
        "technical decision mismatch",
    )
    require(payload.get("safety") == SAFETY, "safety boundary mismatch")
    require(
        payload.get("publication_control") == PUBLICATION_CONTROL,
        "publication control mismatch",
    )


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


def publish_decision(
    canonical_workbook: Path,
    canonical_workbook_sha256: str,
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
    source = load_and_validate_canonical_source(
        canonical_workbook, canonical_workbook_sha256
    )
    require(output.resolve(strict=False) != source.path, "output must not alias source")
    encoded = serialize(build_payload(source))
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
        staged, staged_raw = load_json(staging, "staged YAUO Human Decision")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged)
        require(
            set(output.parent.iterdir()) == {staging},
            "output directory contains unexpected entries before publication",
        )
        try:
            current = source.path.read_bytes()
        except OSError as exc:
            raise ContractError(
                f"TOCTOU reread failed: canonical workbook: {exc}"
            ) from exc
        require(current == source.raw, "TOCTOU bytes changed: canonical workbook")
        require(
            sha256_bytes(current) == CANONICAL_WORKBOOK_SHA256,
            "TOCTOU SHA mismatch: canonical workbook",
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
        published, published_raw = load_json(output, "published YAUO Human Decision")
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
    parser.add_argument("--canonical-invoice-519", required=True, type=Path)
    parser.add_argument("--canonical-invoice-519-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact Invoice 519 YAUO Human Decision publication authorization is required",
    )
    result = publish_decision(
        cast(Path, args.canonical_invoice_519),
        cast(str, args.canonical_invoice_519_sha256),
        cast(Path, args.output),
    )
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
