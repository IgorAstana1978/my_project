"""Publish one immutable price-only Human Decision for Invoice 519."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "invoice519_price_human_decision.v0.1"
SCHEMA_FILENAME = "invoice519_price_human_decision_v0_1.schema.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / SCHEMA_FILENAME
OUTPUT_FILENAME = "invoice519-price-human-decision-v0.1.json"
PROJECT_ID = "2024/086"
INVOICE_NUMBER = 519
DECISION_ID = "IGOR-INVOICE519-PRICE-2024-086-001"
STATUS = "IGOR_INVOICE519_PRICE_APPROVED_NOT_APPLIED"
AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPROVAL_SCOPE = "PRICE_ONLY"
APPLICATION_STATUS = "NOT_APPLIED"
APPROVED_PRICE_KZT = 19_499_186
FROZEN_55_SUBTOTAL_KZT = 11_963_792
MISSING_33_SUBTOTAL_KZT = 7_535_394
PUBLICATION_AUTHORIZATION = (
    "IGOR_INVOICE519_PRICE_HUMAN_DECISION_PUBLICATION_AUTHORIZED"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CREATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JSON_MEDIA_TYPE = "application/json"

FROZEN_55_POSITIONS = (
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    16,
    17,
    18,
    19,
    20,
    27,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    39,
    40,
    41,
    42,
    43,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    59,
    60,
    61,
    62,
    63,
    70,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    81,
    82,
    83,
    84,
    85,
    88,
)
MISSING_33_POSITIONS = (
    1,
    2,
    3,
    4,
    5,
    15,
    21,
    22,
    23,
    24,
    25,
    26,
    28,
    29,
    38,
    44,
    45,
    46,
    47,
    48,
    49,
    58,
    64,
    65,
    66,
    67,
    68,
    69,
    71,
    72,
    80,
    86,
    87,
)
FAMILY_SUBTOTALS = (
    ("VSHZH_VRU", (1, 22, 45, 65), 1_583_790),
    ("RSHZH", (2, 23, 46, 66), 1_020_560),
    ("AVR", (3, 24, 47, 67), 2_069_624),
    ("SHCHSP", (4, 25, 48, 68), 931_420),
    ("UKRM", (5, 26, 49, 69), 538_880),
    ("YARV100", (15, 21, 38, 44, 58, 64, 80, 86), 517_872),
    ("VSHCHO", (28, 71), 466_928),
    ("RSHCHO", (29, 72), 326_574),
    ("YAUO9601_3474", (87,), 79_746),
)


@dataclass(frozen=True)
class InputSpec:
    role: str
    path: str
    sha256: str
    media_type: str


INPUT_SPECS = (
    InputSpec(
        "completed_technical_input",
        (
            r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-"
            "2024-086-SHU-T2-RT820-TECHNICAL-SUCCESSOR-20260824-001\\"
            "price-calculator-input-v0.2-completed-shu-t2-rt820-successor.json"
        ),
        "c27c2c3032699cb07c981aeb4af429b27ec18180225319f45ce65ab77fedee44",
        JSON_MEDIA_TYPE,
    ),
    InputSpec(
        "main_price_workbook",
        (
            r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current"
            "\\"
            "Таблица 05.01.2026 верная.xlsx"
        ),
        "79b3ace77e84b87c46eb708f1c3b2ae63b5c6d75c5ebf6889c12b99624112ba1",
        XLSX_MEDIA_TYPE,
    ),
    InputSpec(
        "custom_sche_metal_workbook",
        (
            r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current"
            "\\"
            "прайс_металл_лотки_крышки с 2026.06.18.xlsx"
        ),
        "b51d7087e0bd8f92e48985294062ead6826c6b50ce3cfacd0f9d0dc22c05f7f2",
        XLSX_MEDIA_TYPE,
    ),
    InputSpec(
        "pricing_profile",
        (
            r"C:\Users\IgorN\Documents\production_ai_cases\CASE-QF-PROJECT-"
            "2024-086-SHU-T2-RT820-PRICING-PROFILE-SUCCESSOR-20260825-002\\"
            "invoice519-pricing-profile-shu-t2-rt820-successor.json"
        ),
        "ae604108514a2b19b58c262c0e2fae379be6eac8a7286ffc2da605ac29637c9e",
        JSON_MEDIA_TYPE,
    ),
    InputSpec(
        "canonical_invoice_519",
        r"C:\Users\IgorN\Downloads\2026.06.22_519_ТОО «Sensata Industrial».xlsx",
        "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5",
        XLSX_MEDIA_TYPE,
    ),
    InputSpec(
        "ukrm_price_workbook",
        (
            r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current"
            "\\"
            "Таблица УКМ 17.02.2023.xlsx"
        ),
        "3570045b9e8de542136664c99ff74963f1db6a0a3f5c24f7ac9e81482f5128b6",
        XLSX_MEDIA_TYPE,
    ),
    InputSpec(
        "yarv100_price_workbook",
        (
            r"C:\Users\IgorN\Documents\invoice_quote_filler_data\prices\current"
            "\\"
            "ЯРВ ПРАЙС СТАНДАРТНАЯ ЦЕНА 19.11.2024.xlsx"
        ),
        "d41f1730c446fde866ed1739cf71e73c1f58f83c46f6e2c41e2478e005e9b35d",
        XLSX_MEDIA_TYPE,
    ),
)

SAFETY = {
    "human_decision_recorded": True,
    "price_approved": True,
    "price_application_authorized": False,
    "price_applied": False,
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
    """The requested artifact would violate the price-only contract."""


class DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


@dataclass(frozen=True)
class LoadedInput:
    spec: InputSpec
    path: Path
    raw: bytes
    parsed: Mapping[str, Any] | None


@dataclass(frozen=True)
class PublicationResult:
    sha256: str
    size: int
    encoded: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


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


def require_list(value: Any, description: str) -> list[Any]:
    require(isinstance(value, list), f"{description} must be an array")
    return cast(list[Any], value)


def _collect_invoice_position_numbers(value: Any) -> list[int]:
    result: list[int] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            if "invoice_position_number" in current:
                number = current["invoice_position_number"]
                require(
                    type(number) is int,
                    "pricing profile invoice_position_number must be an integer",
                )
                result.append(cast(int, number))
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return sorted(result)


def _validate_completed_input(value: Mapping[str, Any]) -> None:
    require(
        value.get("schema_version") == "price_calculator_input_draft.v0.2",
        "completed technical input schema mismatch",
    )
    safety = require_mapping(value.get("safety"), "completed technical input safety")
    required_false = (
        "price_approved_by_igor",
        "production_authorized",
        "downstream_started",
        "sending_authorized",
        "commercial_csv_authorized",
    )
    for field_name in required_false:
        require(
            safety.get(field_name) is False,
            f"completed technical input safety.{field_name} must be false",
        )


def _validate_pricing_profile(value: Mapping[str, Any]) -> None:
    require(
        value.get("schema_version")
        == "technical_invoice519_pricing_profile_human_decisions.v0.1",
        "pricing profile schema mismatch",
    )
    require(
        value.get("status") == "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "pricing profile status mismatch",
    )
    require(
        value.get("application_status") == "NOT_APPLIED",
        "pricing profile application status mismatch",
    )
    positions = _collect_invoice_position_numbers(value)
    require(
        positions == list(FROZEN_55_POSITIONS),
        "pricing profile frozen 55 membership mismatch",
    )


def load_and_validate_inputs(
    paths: Mapping[str, Path], shas: Mapping[str, str]
) -> dict[str, LoadedInput]:
    require(
        set(paths) == {item.role for item in INPUT_SPECS}, "input path roles mismatch"
    )
    require(
        set(shas) == {item.role for item in INPUT_SPECS}, "input SHA roles mismatch"
    )
    loaded: dict[str, LoadedInput] = {}
    for spec in INPUT_SPECS:
        path = paths[spec.role]
        expected_sha = shas[spec.role]
        validate_sha256(expected_sha, f"{spec.role} expected SHA")
        require(expected_sha == spec.sha256, f"{spec.role} approved SHA mismatch")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ContractError(
                f"{spec.role} input path could not be resolved: {exc}"
            ) from exc
        require(resolved.is_file(), f"{spec.role} input must be a file")
        require(
            resolved == Path(spec.path).resolve(strict=False),
            f"{spec.role} input path mismatch",
        )
        try:
            raw = resolved.read_bytes()
        except OSError as exc:
            raise ContractError(f"{spec.role} input could not be read: {exc}") from exc
        require(sha256_bytes(raw) == expected_sha, f"{spec.role} initial SHA mismatch")
        parsed: Mapping[str, Any] | None = None
        if spec.media_type == JSON_MEDIA_TYPE:
            parsed = load_json_bytes(raw, spec.role)
        if spec.role == "completed_technical_input":
            _validate_completed_input(require_mapping(parsed, spec.role))
        elif spec.role == "pricing_profile":
            _validate_pricing_profile(require_mapping(parsed, spec.role))
        loaded[spec.role] = LoadedInput(spec, resolved, raw, parsed)
    return loaded


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _input_bindings(loaded: Mapping[str, LoadedInput]) -> list[dict[str, Any]]:
    return [
        {
            "role": spec.role,
            "path": spec.path,
            "expected_sha256": spec.sha256,
            "actual_sha256": sha256_bytes(loaded[spec.role].raw),
            "media_type": spec.media_type,
        }
        for spec in INPUT_SPECS
    ]


def _reconciliation_payload() -> dict[str, Any]:
    return {
        "status": "CHECKED_RECONCILIATION_PASS",
        "frozen_55": {
            "position_count": 55,
            "subtotal_kzt": FROZEN_55_SUBTOTAL_KZT,
            "invoice_position_numbers": list(FROZEN_55_POSITIONS),
        },
        "checked_missing_33": {
            "position_count": 33,
            "subtotal_kzt": MISSING_33_SUBTOTAL_KZT,
            "invoice_position_numbers": list(MISSING_33_POSITIONS),
            "family_subtotals": [
                {
                    "family": family,
                    "positions": list(positions),
                    "subtotal_kzt": subtotal,
                }
                for family, positions, subtotal in FAMILY_SUBTOTALS
            ],
        },
        "coverage": {"covered": 88, "total": 88, "overlap": 0, "uncovered": 0},
        "combined_total_kzt": APPROVED_PRICE_KZT,
        "frozen_55_recalculated": False,
        "evidence": {
            "frozen_55": "REAL_CHECKED_CALCULATOR_RUN_PASS",
            "checked_missing_33": "NINE_FAMILY_READ_ONLY_CHECKS_PASS",
            "membership": "CANONICAL_INVOICE_AND_PRICING_PROFILE_PARTITION_PASS",
        },
    }


def build_payload(
    loaded: Mapping[str, LoadedInput], created_at_utc: str | None = None
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
        "application_status": APPLICATION_STATUS,
        "created_at_utc": created,
        "input_bindings": _input_bindings(loaded),
        "price_approval": {
            "approved_price_kzt": APPROVED_PRICE_KZT,
            "currency": "KZT",
            "approval_scope": APPROVAL_SCOPE,
            "authority": AUTHORITY,
            "application_status": APPLICATION_STATUS,
        },
        "reconciliation": _reconciliation_payload(),
        "safety": copy.deepcopy(SAFETY),
        "publication_control": copy.deepcopy(PUBLICATION_CONTROL),
    }
    validate_payload(payload)
    return payload


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
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
    if "enum" in schema:
        require(
            any(_json_equal(value, candidate) for candidate in schema["enum"]),
            f"schema enum mismatch at {path}",
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
    if isinstance(value, list):
        if "minItems" in schema:
            require(len(value) >= schema["minItems"], f"schema minItems at {path}")
        if "maxItems" in schema:
            require(len(value) <= schema["maxItems"], f"schema maxItems at {path}")
        item_schema = schema.get("items")
        if item_schema is not None:
            mapping = require_mapping(item_schema, f"schema items at {path}")
            for index, item in enumerate(value):
                validate_against_schema(item, mapping, f"{path}[{index}]")


def load_schema() -> dict[str, Any]:
    schema, _raw = load_json(SCHEMA_PATH, "committed decision schema")
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


def validate_reconciliation(value: Any) -> None:
    reconciliation = require_mapping(value, "reconciliation")
    frozen = require_mapping(reconciliation.get("frozen_55"), "frozen_55")
    missing = require_mapping(
        reconciliation.get("checked_missing_33"), "checked_missing_33"
    )
    frozen_positions = require_list(
        frozen.get("invoice_position_numbers"), "frozen_55 positions"
    )
    missing_positions = require_list(
        missing.get("invoice_position_numbers"), "checked_missing_33 positions"
    )
    require(
        all(type(item) is int for item in frozen_positions + missing_positions),
        "reconciliation position IDs must be integers",
    )
    frozen_set = set(cast(list[int], frozen_positions))
    missing_set = set(cast(list[int], missing_positions))
    require(len(frozen_positions) == len(frozen_set) == 55, "frozen 55 membership")
    require(len(missing_positions) == len(missing_set) == 33, "missing 33 membership")
    require(frozen_set == set(FROZEN_55_POSITIONS), "frozen 55 exact membership")
    require(missing_set == set(MISSING_33_POSITIONS), "missing 33 exact membership")
    require(not frozen_set & missing_set, "reconciliation overlap must be zero")
    require(frozen_set | missing_set == set(range(1, 89)), "reconciliation union")
    family_items = require_list(missing.get("family_subtotals"), "family subtotals")
    family_positions: list[int] = []
    family_total = 0
    for item in family_items:
        family = require_mapping(item, "family subtotal")
        positions = require_list(family.get("positions"), "family positions")
        require(
            all(type(position) is int for position in positions),
            "family position IDs must be integers",
        )
        family_positions.extend(cast(list[int], positions))
        subtotal = family.get("subtotal_kzt")
        require(type(subtotal) is int, "family subtotal must be an integer")
        family_total += cast(int, subtotal)
    require(len(family_positions) == len(set(family_positions)), "family overlap")
    require(set(family_positions) == missing_set, "family missing membership")
    require(family_total == MISSING_33_SUBTOTAL_KZT, "family subtotal reconciliation")
    require(
        frozen.get("subtotal_kzt") == FROZEN_55_SUBTOTAL_KZT,
        "frozen 55 subtotal mismatch",
    )
    require(
        missing.get("subtotal_kzt") == MISSING_33_SUBTOTAL_KZT,
        "missing 33 subtotal mismatch",
    )
    require(
        FROZEN_55_SUBTOTAL_KZT + MISSING_33_SUBTOTAL_KZT == APPROVED_PRICE_KZT,
        "approved price arithmetic mismatch",
    )
    require(
        reconciliation.get("combined_total_kzt") == APPROVED_PRICE_KZT,
        "combined total mismatch",
    )
    require(reconciliation.get("frozen_55_recalculated") is False, "frozen 55 drift")
    coverage = require_mapping(reconciliation.get("coverage"), "coverage")
    require(
        coverage == {"covered": 88, "total": 88, "overlap": 0, "uncovered": 0},
        "coverage mismatch",
    )


def validate_payload(payload: Mapping[str, Any]) -> None:
    validate_against_schema(payload, load_schema())
    bindings = require_list(payload.get("input_bindings"), "input_bindings")
    require(
        [item.get("role") for item in bindings if isinstance(item, Mapping)]
        == [spec.role for spec in INPUT_SPECS],
        "input binding role order mismatch",
    )
    for binding, spec in zip(bindings, INPUT_SPECS, strict=True):
        item = require_mapping(binding, "input binding")
        require(item.get("path") == spec.path, f"{spec.role} binding path mismatch")
        require(
            item.get("expected_sha256") == spec.sha256,
            f"{spec.role} binding expected SHA mismatch",
        )
        require(
            item.get("actual_sha256") == spec.sha256,
            f"{spec.role} binding actual SHA mismatch",
        )
        require(
            item.get("media_type") == spec.media_type,
            f"{spec.role} binding media type mismatch",
        )
    validate_reconciliation(payload.get("reconciliation"))
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
            current_identity = _path_identity(output)
            if current_identity == staged_identity:
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
    paths: Mapping[str, Path], shas: Mapping[str, str], output: Path
) -> PublicationResult:
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "output directory already exists")
    loaded = load_and_validate_inputs(paths, shas)
    input_paths = {item.path for item in loaded.values()}
    require(
        output.resolve(strict=False) not in input_paths,
        "output must not alias an input",
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
        staged, staged_raw = load_json(staging, "staged price Human Decision")
        require(staged_raw == encoded, "staged bytes mismatch")
        validate_payload(staged)
        require(
            set(output.parent.iterdir()) == {staging},
            "output directory contains unexpected entries before publication",
        )
        for item in loaded.values():
            try:
                current = item.path.read_bytes()
            except OSError as exc:
                raise ContractError(
                    f"TOCTOU reread failed: {item.spec.role}: {exc}"
                ) from exc
            require(current == item.raw, f"TOCTOU bytes changed: {item.spec.role}")
            require(
                sha256_bytes(current) == item.spec.sha256,
                f"TOCTOU SHA mismatch: {item.spec.role}",
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
        published, published_raw = load_json(output, "published price Human Decision")
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
    for spec in INPUT_SPECS:
        option = spec.role.replace("_", "-")
        parser.add_argument(f"--{option}", dest=spec.role, required=True, type=Path)
        parser.add_argument(
            f"--{option}-sha256", dest=f"{spec.role}_sha256", required=True
        )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    require(
        args.authorization == PUBLICATION_AUTHORIZATION,
        "exact Invoice 519 price Human Decision publication authorization is required",
    )
    paths = {spec.role: cast(Path, getattr(args, spec.role)) for spec in INPUT_SPECS}
    shas = {
        spec.role: cast(str, getattr(args, f"{spec.role}_sha256"))
        for spec in INPUT_SPECS
    }
    result = publish_decision(paths, shas, cast(Path, args.output))
    print(
        f"PUBLISHED_IMMUTABLE_NO_OVERWRITE {args.output} "
        f"SHA256={result.sha256} SIZE={result.size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
