"""Publish the immutable DINVA classic canonical-logo Human Decision."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import struct
import tempfile
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from zipfile import BadZipFile, ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "dinva_classic_canonical_logo_human_decision.v0.1"
SCHEMA_PATH = (
    REPO_ROOT
    / "schemas"
    / "dinva_classic_canonical_logo_human_decision_v0_1.schema.json"
)
OUTPUT_FILENAME = "dinva-classic-canonical-logo-human-decision-v0.1.json"
ARTIFACT_TYPE = "IMMUTABLE_HUMAN_DECISION_CAPTURE"
DECISION_ID = "IGOR-DINVA-CLASSIC-CANONICAL-LOGO-20260901-001"
STATUS = "IGOR_DINVA_CLASSIC_CANONICAL_LOGO_APPROVED_NOT_APPLIED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPROVAL_SCOPE = "BRAND_LOGO_ONLY"
APPLICATION_STATUS = "NOT_APPLIED_TO_PROFILE"
MEDIA_PART_PATH = "xl/media/image1.png"
PUBLICATION_AUTHORIZATION = (
    "IGOR_DINVA_CLASSIC_CANONICAL_LOGO_HUMAN_DECISION_PUBLICATION_AUTHORIZED"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CREATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class SourceSpec:
    label: str
    role: str
    path: Path
    workbook_sha256: str
    logo_raw_sha256: str
    normalized_pixel_fingerprint: str
    native_dimensions: tuple[int, int]
    decoded_mode: str


@dataclass(frozen=True)
class SourceInput:
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LoadedSource:
    spec: SourceSpec
    path: Path
    workbook_raw: bytes
    logo_raw: bytes


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


CANONICAL_LOGO_RAW_SHA256 = (
    "28a6a59ae0a5ca274c206c70545f70b333cac0276a7c4dcbebbf9156f88e0fa8"
)
CANONICAL_LOGO_PIXEL_FINGERPRINT = (
    "81d979c4c158452cca8e3b40d23a4fd321538dfcef238b6f8133beb33a122846"
)
RUNTIME_LOGO_RAW_SHA256 = (
    "18e0f9446c72f8aa80ea833df07c2e42eb830770a0186decc476c5f948987301"
)
RUNTIME_LOGO_PIXEL_FINGERPRINT = (
    "0bb630c32bad53195a7d82ac1adedfe9a318f7236c18f333d6a1e93fce3bd561"
)

SOURCE_SPECS = (
    SourceSpec(
        "Invoice519",
        "CLASSIC_FAMILY_EVIDENCE",
        Path(r"C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx"),
        "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5",
        CANONICAL_LOGO_RAW_SHA256,
        CANONICAL_LOGO_PIXEL_FINGERPRINT,
        (200, 68),
        "RGB",
    ),
    SourceSpec(
        "Invoice463",
        "CLASSIC_FAMILY_EVIDENCE",
        Path(r"C:\Users\IgorN\Downloads\2026.06.04_463_ТОО «Rich energy» эталон.xlsx"),
        "8cf9f2b4ecca94e51a9f868891b6bc00151ef4b05b012db0d875862599c5253c",
        CANONICAL_LOGO_RAW_SHA256,
        CANONICAL_LOGO_PIXEL_FINGERPRINT,
        (200, 68),
        "RGB",
    ),
    SourceSpec(
        "Invoice551",
        "CLASSIC_FAMILY_EVIDENCE",
        Path(r"C:\Users\IgorN\Downloads\2026.07.02_551_ТОО «TDK Energy».xlsx"),
        "d8e652325c142a72ffa4aa390197b3e357b5efc317d07f6d763e01d3c1c4fec9",
        CANONICAL_LOGO_RAW_SHA256,
        CANONICAL_LOGO_PIXEL_FINGERPRINT,
        (200, 68),
        "RGB",
    ),
    SourceSpec(
        "capacity100_tuned_v4",
        "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE",
        Path(
            r"C:\Users\IgorN\Downloads\Фирменный_шаблон_счёта-КП_v0.4_capacity100_tuned_v4_ДиН_ВА-КЭС.xlsx"
        ),
        "9c5ea4bd3be0dc920860a9900565f38092362edd6b0827a21a28ac53e2808292",
        RUNTIME_LOGO_RAW_SHA256,
        RUNTIME_LOGO_PIXEL_FINGERPRINT,
        (115, 43),
        "RGBA",
    ),
)

CANONICAL_LOGO_DECISION = {
    "approved_variant": "A_FAMILY_INVOICE519",
    "authoritative_brand_source": "CLASSIC_FAMILY_EMBEDDED_LOGO",
    "media_part_path": MEDIA_PART_PATH,
    "raw_sha256": CANONICAL_LOGO_RAW_SHA256,
    "normalized_pixel_fingerprint": CANONICAL_LOGO_PIXEL_FINGERPRINT,
    "native_dimensions": [200, 68],
    "decoded_mode": "RGB",
}
RUNTIME_TEMPLATE_POLICY = {
    "template_id": "capacity100_tuned_v4",
    "permitted_role": "RUNTIME_GEOMETRY_STYLE_LAYOUT_SOURCE_ONLY",
    "authoritative_brand_logo_source": False,
    "differing_logo_raw_sha256": RUNTIME_LOGO_RAW_SHA256,
}
SAFETY = {
    "human_decision_recorded": True,
    "canonical_logo_approved": True,
    "profile_approval_authorized": False,
    "profile_generation_authorized": False,
    "profile_publication_authorized": False,
    "runtime_template_modification_authorized": False,
    "quote_generation_authorized": False,
    "invoice_generation_authorized": False,
    "xlsx_generation_authorized": False,
    "pdf_generation_authorized": False,
    "client_send_authorized": False,
    "procurement_authorized": False,
    "reserve_authorized": False,
    "prepayment_authorized": False,
    "payment_authorized": False,
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
    """The requested operation violates the closed decision contract."""


class DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


def fail(message: str) -> NoReturn:
    raise ContractError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


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


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "boolean":
        return type(value) is bool
    fail(f"unsupported schema type: {expected}")


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    require(reference.startswith("#/"), "only local schema references are supported")
    current: Any = root
    for component in reference[2:].split("/"):
        current = require_mapping(current, "schema reference").get(component)
    return require_mapping(current, f"schema reference {reference}")


def validate_against_schema(
    value: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any] | None = None,
    path: str = "$",
) -> None:
    root_schema = root or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        require(isinstance(reference, str), f"schema reference invalid at {path}")
        validate_against_schema(
            value, _resolve_ref(root_schema, reference), root_schema, path
        )
        return
    if "const" in schema:
        require(_json_equal(value, schema["const"]), f"schema const mismatch at {path}")
    if "enum" in schema:
        allowed = schema["enum"]
        require(isinstance(allowed, list), f"schema enum invalid at {path}")
        require(
            any(_json_equal(value, item) for item in allowed), f"schema enum at {path}"
        )
    expected_type = schema.get("type")
    if expected_type is not None:
        require(
            isinstance(expected_type, str)
            and _schema_type_matches(value, expected_type),
            f"schema type mismatch at {path}",
        )
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if minimum is not None:
            require(
                isinstance(minimum, int) and len(value) >= minimum,
                f"schema minLength at {path}",
            )
        pattern = schema.get("pattern")
        if pattern is not None:
            require(
                isinstance(pattern, str) and re.search(pattern, value) is not None,
                f"schema pattern at {path}",
            )
    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None:
            require(
                isinstance(minimum, int) and len(value) >= minimum,
                f"schema minItems at {path}",
            )
        if maximum is not None:
            require(
                isinstance(maximum, int) and len(value) <= maximum,
                f"schema maxItems at {path}",
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            child_schema = require_mapping(item_schema, f"schema items at {path}")
            for index, item in enumerate(value):
                validate_against_schema(
                    item, child_schema, root_schema, f"{path}[{index}]"
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
                    root_schema,
                    f"{path}.{key}",
                )


def _paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    left_distance = abs(prediction - left)
    above_distance = abs(prediction - above)
    upper_left_distance = abs(prediction - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def decode_png_rgba(raw: bytes) -> tuple[tuple[int, int], str, bytes]:
    try:
        require(raw[:8] == b"\x89PNG\r\n\x1a\n", "logo asset is not PNG")
        offset = 8
        ihdr: tuple[int, int, int, int, int, int, int] | None = None
        idat_parts: list[bytes] = []
        ended = False
        while offset < len(raw):
            require(offset + 12 <= len(raw), "logo PNG chunk is truncated")
            length = struct.unpack(">I", raw[offset : offset + 4])[0]
            end = offset + 12 + length
            require(end <= len(raw), "logo PNG chunk length is invalid")
            kind_raw = raw[offset + 4 : offset + 8]
            kind = kind_raw.decode("ascii")
            data = raw[offset + 8 : offset + 8 + length]
            expected_crc = struct.unpack(">I", raw[offset + 8 + length : end])[0]
            require(
                zlib.crc32(kind_raw + data) & 0xFFFFFFFF == expected_crc,
                f"logo PNG {kind} CRC mismatch",
            )
            if kind == "IHDR":
                require(ihdr is None and length == 13, "logo PNG IHDR mismatch")
                ihdr = struct.unpack(">IIBBBBB", data)
            elif kind == "IDAT":
                idat_parts.append(data)
            elif kind == "IEND":
                require(length == 0, "logo PNG IEND mismatch")
                ended = True
                offset = end
                break
            offset = end
        require(ended and offset == len(raw), "logo PNG package boundary mismatch")
        if ihdr is None or not idat_parts:
            fail("logo PNG structure mismatch")
        width, height, depth, color_type, compression, filter_method, interlace = ihdr
        require(width > 0 and height > 0, "logo PNG dimensions invalid")
        require(
            (depth, compression, filter_method, interlace) == (8, 0, 0, 0),
            "logo PNG encoding is unsupported",
        )
        if color_type == 2:
            mode, bytes_per_pixel = "RGB", 3
        elif color_type == 6:
            mode, bytes_per_pixel = "RGBA", 4
        else:
            fail("logo PNG color type is unsupported")
        packed = zlib.decompress(b"".join(idat_parts))
        stride = width * bytes_per_pixel
        require(
            len(packed) == height * (stride + 1),
            "logo PNG scanline length mismatch",
        )
        previous = bytearray(stride)
        decoded = bytearray()
        cursor = 0
        for _row_index in range(height):
            filter_type = packed[cursor]
            cursor += 1
            row = bytearray(packed[cursor : cursor + stride])
            cursor += stride
            for index in range(stride):
                left = row[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
                above = previous[index]
                upper_left = (
                    previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
                )
                if filter_type == 1:
                    row[index] = (row[index] + left) & 0xFF
                elif filter_type == 2:
                    row[index] = (row[index] + above) & 0xFF
                elif filter_type == 3:
                    row[index] = (row[index] + ((left + above) // 2)) & 0xFF
                elif filter_type == 4:
                    row[index] = (row[index] + _paeth(left, above, upper_left)) & 0xFF
                else:
                    require(filter_type == 0, "logo PNG filter type is unsupported")
            decoded.extend(row)
            previous = row
        if mode == "RGB":
            rgba = bytearray()
            for index in range(0, len(decoded), 3):
                rgba.extend(decoded[index : index + 3])
                rgba.append(0xFF)
            return (width, height), mode, bytes(rgba)
        return (width, height), mode, bytes(decoded)
    except (UnicodeDecodeError, struct.error, zlib.error) as exc:
        raise ContractError(f"logo PNG could not be decoded: {exc}") from exc


def normalized_pixel_fingerprint(dimensions: tuple[int, int], rgba: bytes) -> str:
    return sha256_bytes(struct.pack(">II", *dimensions) + rgba)


def _extract_logo(workbook_raw: bytes, label: str) -> bytes:
    try:
        with ZipFile(io.BytesIO(workbook_raw), "r") as archive:
            media = sorted(
                name for name in archive.namelist() if name.startswith("xl/media/")
            )
            require(media == [MEDIA_PART_PATH], f"{label} logo media binding mismatch")
            return archive.read(MEDIA_PART_PATH)
    except (BadZipFile, KeyError) as exc:
        raise ContractError(f"{label} workbook media could not be read: {exc}") from exc


def load_and_validate_source(
    source_input: SourceInput, spec: SourceSpec
) -> LoadedSource:
    require(
        SHA256_RE.fullmatch(source_input.expected_sha256) is not None,
        f"{spec.label} expected workbook SHA format",
    )
    require(
        source_input.expected_sha256 == spec.workbook_sha256,
        f"{spec.label} workbook SHA binding mismatch",
    )
    try:
        path = source_input.path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"{spec.label} source path unavailable: {exc}") from exc
    require(
        path == spec.path.resolve(strict=False),
        f"{spec.label} source path binding mismatch",
    )
    try:
        workbook_raw = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"{spec.label} workbook could not be read: {exc}") from exc
    require(
        sha256_bytes(workbook_raw) == spec.workbook_sha256,
        f"{spec.label} workbook initial SHA mismatch",
    )
    logo_raw = _extract_logo(workbook_raw, spec.label)
    require(
        sha256_bytes(logo_raw) == spec.logo_raw_sha256,
        f"{spec.label} logo raw SHA mismatch",
    )
    dimensions, mode, rgba = decode_png_rgba(logo_raw)
    require(
        dimensions == spec.native_dimensions, f"{spec.label} logo dimensions mismatch"
    )
    require(mode == spec.decoded_mode, f"{spec.label} logo decoded mode mismatch")
    require(
        normalized_pixel_fingerprint(dimensions, rgba)
        == spec.normalized_pixel_fingerprint,
        f"{spec.label} logo normalized fingerprint mismatch",
    )
    return LoadedSource(spec, path, workbook_raw, logo_raw)


def load_and_validate_sources(
    source_inputs: Sequence[SourceInput],
) -> tuple[LoadedSource, ...]:
    require(len(source_inputs) == len(SOURCE_SPECS), "source input count mismatch")
    loaded = tuple(
        load_and_validate_source(source_input, spec)
        for source_input, spec in zip(source_inputs, SOURCE_SPECS, strict=True)
    )
    family = [item for item in loaded if item.spec.role == "CLASSIC_FAMILY_EVIDENCE"]
    runtime = [
        item
        for item in loaded
        if item.spec.role == "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE"
    ]
    require(len(family) == 3 and len(runtime) == 1, "source evidence role set mismatch")
    require(
        {sha256_bytes(item.logo_raw) for item in family}
        == {CANONICAL_LOGO_DECISION["raw_sha256"]},
        "classic-family canonical logo consensus mismatch",
    )
    require(
        runtime[0].spec.logo_raw_sha256
        == RUNTIME_TEMPLATE_POLICY["differing_logo_raw_sha256"],
        "runtime differing logo binding mismatch",
    )
    require(
        runtime[0].spec.logo_raw_sha256 != CANONICAL_LOGO_DECISION["raw_sha256"],
        "runtime differing-logo decision premise mismatch",
    )
    return loaded


def _source_binding(source: LoadedSource) -> dict[str, Any]:
    spec = source.spec
    return {
        "label": spec.label,
        "role": spec.role,
        "path": str(source.path),
        "expected_workbook_sha256": spec.workbook_sha256,
        "actual_workbook_sha256": sha256_bytes(source.workbook_raw),
        "media_part_path": MEDIA_PART_PATH,
        "expected_logo_raw_sha256": spec.logo_raw_sha256,
        "actual_logo_raw_sha256": sha256_bytes(source.logo_raw),
        "normalized_pixel_fingerprint": spec.normalized_pixel_fingerprint,
        "native_dimensions": list(spec.native_dimensions),
        "decoded_mode": spec.decoded_mode,
    }


def _expected_source_bindings() -> list[dict[str, Any]]:
    return [
        {
            "label": spec.label,
            "role": spec.role,
            "path": str(spec.path.resolve(strict=False)),
            "expected_workbook_sha256": spec.workbook_sha256,
            "actual_workbook_sha256": spec.workbook_sha256,
            "media_part_path": MEDIA_PART_PATH,
            "expected_logo_raw_sha256": spec.logo_raw_sha256,
            "actual_logo_raw_sha256": spec.logo_raw_sha256,
            "normalized_pixel_fingerprint": spec.normalized_pixel_fingerprint,
            "native_dimensions": list(spec.native_dimensions),
            "decoded_mode": spec.decoded_mode,
        }
        for spec in SOURCE_SPECS
    ]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_payload(
    sources: Sequence[LoadedSource], created_at_utc: str | None = None
) -> dict[str, Any]:
    created = created_at_utc or utc_now()
    require(CREATED_AT_RE.fullmatch(created) is not None, "created_at_utc format")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "decision_id": DECISION_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "approval_scope": APPROVAL_SCOPE,
        "canonical_logo_application_status": APPLICATION_STATUS,
        "created_at_utc": created,
        "source_bindings": [_source_binding(source) for source in sources],
        "canonical_logo_decision": copy.deepcopy(CANONICAL_LOGO_DECISION),
        "runtime_template_policy": copy.deepcopy(RUNTIME_TEMPLATE_POLICY),
        "safety": copy.deepcopy(SAFETY),
        "publication_control": copy.deepcopy(PUBLICATION_CONTROL),
    }
    validate_payload(payload)
    return payload


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed canonical-logo decision schema")
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
        "schema version contract mismatch",
    )
    require(
        require_mapping(properties.get("status"), "schema status").get("const")
        == STATUS,
        "schema status contract mismatch",
    )
    require(
        require_mapping(properties.get("approval_scope"), "schema scope").get("const")
        == APPROVAL_SCOPE,
        "schema approval scope mismatch",
    )
    return schema


def validate_payload(payload: Mapping[str, Any]) -> None:
    validate_against_schema(payload, load_schema())
    exact_top_level = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "decision_id": DECISION_ID,
        "status": STATUS,
        "authority": AUTHORITY,
        "approval_scope": APPROVAL_SCOPE,
        "canonical_logo_application_status": APPLICATION_STATUS,
    }
    for key, expected in exact_top_level.items():
        require(payload.get(key) == expected, f"{key} exact constant mismatch")
    require(
        payload.get("source_bindings") == _expected_source_bindings(),
        "source bindings exact contract mismatch",
    )
    require(
        payload.get("canonical_logo_decision") == CANONICAL_LOGO_DECISION,
        "canonical logo decision mismatch",
    )
    require(
        payload.get("runtime_template_policy") == RUNTIME_TEMPLATE_POLICY,
        "runtime template policy mismatch",
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


def _recheck_sources(sources: Sequence[LoadedSource]) -> None:
    for source in sources:
        try:
            reread = source.path.read_bytes()
        except OSError as exc:
            raise ContractError(
                f"{source.spec.label} TOCTOU reread failed: {exc}"
            ) from exc
        require(
            reread == source.workbook_raw
            and sha256_bytes(reread) == source.spec.workbook_sha256,
            f"{source.spec.label} source TOCTOU mismatch",
        )


def publish_decision(
    source_inputs: Sequence[SourceInput], output: Path
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    require(
        not output.resolve(strict=False).is_relative_to(
            REPO_ROOT.resolve(strict=False)
        ),
        "output must be outside repository",
    )
    sources = load_and_validate_sources(source_inputs)
    source_paths = {source.path for source in sources}
    require(
        output.resolve(strict=False) not in source_paths,
        "output must not alias a source",
    )
    encoded = serialize(build_payload(sources))
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    final_link_created = False
    staged_identity: tuple[int, int] | None = None
    try:
        descriptor, raw_staging = tempfile.mkstemp(
            prefix=".canonical-logo-decision-",
            suffix=".tmp",
            dir=output.parent,
        )
        staging = Path(raw_staging)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged_identity = _path_identity(staging)
        staged_payload, staged_raw = load_json(
            staging, "staged canonical-logo Human Decision"
        )
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged_payload)
        _recheck_sources(sources)
        os.link(staging, output)
        final_link_created = True
        require(
            _path_identity(output) == staged_identity,
            "published final identity mismatch",
        )
        published, published_raw = load_json(
            output, "published canonical-logo Human Decision"
        )
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
    parser.add_argument("--invoice-519", required=True, type=Path)
    parser.add_argument("--invoice-519-sha256", required=True)
    parser.add_argument("--invoice-463", required=True, type=Path)
    parser.add_argument("--invoice-463-sha256", required=True)
    parser.add_argument("--invoice-551", required=True, type=Path)
    parser.add_argument("--invoice-551-sha256", required=True)
    parser.add_argument("--runtime-template", required=True, type=Path)
    parser.add_argument("--runtime-template-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact canonical-logo Human Decision publication authorization is required",
    )
    result = publish_decision(
        (
            SourceInput(
                cast(Path, args.invoice_519), cast(str, args.invoice_519_sha256)
            ),
            SourceInput(
                cast(Path, args.invoice_463), cast(str, args.invoice_463_sha256)
            ),
            SourceInput(
                cast(Path, args.invoice_551), cast(str, args.invoice_551_sha256)
            ),
            SourceInput(
                cast(Path, args.runtime_template),
                cast(str, args.runtime_template_sha256),
            ),
        ),
        cast(Path, args.output),
    )
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
