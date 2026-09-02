"""Publish an immutable approved DINVA classic presentation profile."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "dinva_classic_presentation_profile_v0_1.schema.json"
)
PROFILE_SCHEMA_VERSION = "dinva_classic_presentation_profile.v0.1"
PROFILE_FAMILY = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1"
DRAFT_PROFILE_SHA256 = (
    "e1240c471435ba99709ff8cd44571151e9467f1d010b7e83770869383d734b40"
)
APPROVED_CONTRACT_FINGERPRINT = (
    "246ad0bf2526319eb5b0be067f6d8493560b5ec0722662b1eaf2340ec31bd8cc"
)
APPROVAL_AUTHORITY = "IGOR_DIRECT_HUMAN_APPROVAL"
APPROVAL_ID_PREFIX = "IGOR-DINVA-CLASSIC-PRESENTATION-PROFILE-V0-1-20260902-001"
PUBLICATION_AUTHORIZATION = (
    "IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_APPROVAL_PUBLICATION_AUTHORIZED"
)
OUTPUT_FILENAME = "dinva-classic-presentation-profile-v0.1-APPROVED.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PROFILE_KEYS = {
    "schema_version",
    "profile_id",
    "document_family",
    "artifact_status",
    "reference_provenance",
    "presentation_contract",
    "presentation_contract_fingerprint",
    "approval_provenance",
}
APPROVAL_KEYS = {
    "status",
    "authority",
    "approval_id",
    "approved_at",
    "approved_contract_fingerprint",
}
UNCHANGED_PROFILE_KEYS = PROFILE_KEYS - {"artifact_status", "approval_provenance"}


class ApprovalPublicationError(ValueError):
    """The approval publication would violate the closed contract."""


class DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


@dataclass(frozen=True)
class DraftInput:
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LoadedDraft:
    path: Path
    raw: bytes
    payload: dict[str, Any]


@dataclass(frozen=True)
class PublicationResult:
    path: Path
    sha256: str
    size: int
    approved_at: str
    approval_id: str


def fail(message: str) -> NoReturn:
    raise ApprovalPublicationError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ApprovalPublicationError(f"{label} must be strict UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
        raise ApprovalPublicationError(f"{label} is not strict JSON: {exc}") from exc
    require(isinstance(value, Mapping), f"{label} root must be an object")
    return dict(cast(Mapping[str, Any], value))


def load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ApprovalPublicationError(f"{label} could not be read: {exc}") from exc
    return load_json_bytes(raw, label), raw


def mapping(value: object, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    require(set(value) == expected, f"{label} fields mismatch")


def json_equal(left: object, right: object) -> bool:
    return canonical_json(left) == canonical_json(right)


def schema_type_matches(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in {int, float}
    if expected == "boolean":
        return type(value) is bool
    if expected == "null":
        return value is None
    fail(f"unsupported schema type: {expected}")


def resolve_schema_ref(root: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    require(reference.startswith("#/"), "only local schema references are supported")
    current: object = root
    for component in reference[2:].split("/"):
        current = mapping(current, "schema reference").get(component)
    return mapping(current, f"schema reference {reference}")


def validate_against_schema(
    value: object,
    schema: Mapping[str, Any],
    root: Mapping[str, Any] | None = None,
    path: str = "$",
) -> None:
    root_schema = root or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        require(isinstance(reference, str), f"schema reference invalid at {path}")
        validate_against_schema(
            value, resolve_schema_ref(root_schema, reference), root_schema, path
        )
        return
    alternatives = schema.get("anyOf")
    if alternatives is not None:
        require(isinstance(alternatives, list), f"schema anyOf invalid at {path}")
        for alternative in alternatives:
            try:
                validate_against_schema(
                    value,
                    mapping(alternative, f"schema anyOf at {path}"),
                    root_schema,
                    path,
                )
                break
            except ApprovalPublicationError:
                continue
        else:
            fail(f"schema anyOf mismatch at {path}")
        return
    if "const" in schema:
        require(json_equal(value, schema["const"]), f"schema const mismatch at {path}")
    if "enum" in schema:
        allowed = schema["enum"]
        require(isinstance(allowed, list), f"schema enum invalid at {path}")
        require(
            any(json_equal(value, item) for item in allowed),
            f"schema enum mismatch at {path}",
        )
    expected_type = schema.get("type")
    if expected_type is not None:
        types = [expected_type] if isinstance(expected_type, str) else expected_type
        require(
            isinstance(types, list)
            and all(isinstance(item, str) for item in types)
            and any(schema_type_matches(value, cast(str, item)) for item in types),
            f"schema type mismatch at {path}",
        )
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if minimum_length is not None:
            require(
                type(minimum_length) is int and len(value) >= minimum_length,
                f"schema minLength mismatch at {path}",
            )
        pattern = schema.get("pattern")
        if pattern is not None:
            require(
                isinstance(pattern, str) and re.search(pattern, value) is not None,
                f"schema pattern mismatch at {path}",
            )
    if type(value) in {int, float}:
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None:
            require(value >= minimum, f"schema minimum mismatch at {path}")
        if maximum is not None:
            require(value <= maximum, f"schema maximum mismatch at {path}")
    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if minimum_items is not None:
            require(
                type(minimum_items) is int and len(value) >= minimum_items,
                f"schema minItems mismatch at {path}",
            )
        if maximum_items is not None:
            require(
                type(maximum_items) is int and len(value) <= maximum_items,
                f"schema maxItems mismatch at {path}",
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                validate_against_schema(
                    item,
                    mapping(item_schema, f"schema items at {path}"),
                    root_schema,
                    f"{path}[{index}]",
                )
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        require(isinstance(required, list), f"schema required invalid at {path}")
        require(isinstance(properties, Mapping), f"schema properties invalid at {path}")
        missing = [key for key in required if key not in value]
        require(not missing, f"schema missing keys at {path}: {missing}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            require(not extra, f"schema extra keys at {path}: {sorted(extra)}")
        for key, child_schema in properties.items():
            if key in value:
                validate_against_schema(
                    value[key],
                    mapping(child_schema, f"schema property {path}.{key}"),
                    root_schema,
                    f"{path}.{key}",
                )


def load_profile_schema() -> dict[str, Any]:
    schema, _raw = load_json(PROFILE_SCHEMA_PATH, "committed profile schema")
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "profile schema dialect mismatch",
    )
    require(schema.get("additionalProperties") is False, "profile schema is not closed")
    properties = mapping(schema.get("properties"), "profile schema properties")
    required = schema.get("required")
    require(
        set(properties) == PROFILE_KEYS
        and isinstance(required, list)
        and set(required) == PROFILE_KEYS,
        "profile schema top-level contract mismatch",
    )
    approval = mapping(properties.get("approval_provenance"), "approval schema")
    approval_properties = mapping(approval.get("properties"), "approval properties")
    approval_required = approval.get("required")
    require(
        approval.get("additionalProperties") is False
        and set(approval_properties) == APPROVAL_KEYS
        and isinstance(approval_required, list)
        and set(approval_required) == APPROVAL_KEYS,
        "profile approval schema shape mismatch",
    )
    require(
        "IMMUTABLE_APPROVED_PROFILE"
        in cast(list[object], mapping(properties["artifact_status"], "status")["enum"])
        and "APPROVED"
        in cast(
            list[object], mapping(approval_properties["status"], "approval")["enum"]
        ),
        "approved profile state is not schema-compatible",
    )
    return schema


def contract_fingerprint(profile: Mapping[str, Any]) -> str:
    contract = mapping(profile.get("presentation_contract"), "presentation contract")
    return sha256_bytes(canonical_json(contract))


def validate_draft_profile(profile: Mapping[str, Any]) -> None:
    exact_keys(profile, PROFILE_KEYS, "DRAFT profile")
    validate_against_schema(profile, load_profile_schema())
    require(
        profile.get("schema_version") == PROFILE_SCHEMA_VERSION,
        "DRAFT profile schema version mismatch",
    )
    require(profile.get("profile_id") == PROFILE_FAMILY, "DRAFT profile id mismatch")
    require(
        profile.get("document_family") == PROFILE_FAMILY,
        "DRAFT profile family mismatch",
    )
    require(
        profile.get("artifact_status") == "DRAFT_PROFILE_CANDIDATE",
        "source profile is not a DRAFT candidate",
    )
    approval = mapping(profile.get("approval_provenance"), "DRAFT approval provenance")
    exact_keys(approval, APPROVAL_KEYS, "DRAFT approval provenance")
    require(
        approval
        == {
            "status": "DRAFT_UNAPPROVED",
            "authority": None,
            "approval_id": None,
            "approved_at": None,
            "approved_contract_fingerprint": None,
        },
        "source profile approval state is not DRAFT_UNAPPROVED",
    )
    fingerprint = contract_fingerprint(profile)
    require(
        profile.get("presentation_contract_fingerprint") == fingerprint,
        "DRAFT presentation contract fingerprint mismatch",
    )
    require(
        fingerprint == APPROVED_CONTRACT_FINGERPRINT,
        "DRAFT contract fingerprint is not the approved candidate fingerprint",
    )


def load_draft(source: DraftInput) -> LoadedDraft:
    path = source.path.resolve(strict=True)
    require(
        not path.is_relative_to(REPO_ROOT.resolve(strict=False)),
        "DRAFT profile must be outside Git",
    )
    require(
        SHA256_RE.fullmatch(source.expected_sha256) is not None,
        "DRAFT profile supplied SHA-256 format is invalid",
    )
    require(
        source.expected_sha256 == DRAFT_PROFILE_SHA256,
        "DRAFT profile supplied SHA-256 is not the approved source SHA-256",
    )
    payload, raw = load_json(path, "DRAFT profile")
    require(
        sha256_bytes(raw) == DRAFT_PROFILE_SHA256,
        "DRAFT profile actual bytes SHA-256 mismatch",
    )
    validate_draft_profile(payload)
    require(path.read_bytes() == raw, "DRAFT profile changed during initial validation")
    return LoadedDraft(path, raw, payload)


def approval_id() -> str:
    return f"{APPROVAL_ID_PREFIX}|DRAFT_SHA256={DRAFT_PROFILE_SHA256}"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_approved_profile(
    draft: Mapping[str, Any], approved_at: str
) -> dict[str, Any]:
    require(UTC_RE.fullmatch(approved_at) is not None, "approval timestamp is invalid")
    approved = copy.deepcopy(dict(draft))
    approved["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    approved["approval_provenance"] = {
        "status": "APPROVED",
        "authority": APPROVAL_AUTHORITY,
        "approval_id": approval_id(),
        "approved_at": approved_at,
        "approved_contract_fingerprint": APPROVED_CONTRACT_FINGERPRINT,
    }
    validate_approved_profile(approved, draft)
    return approved


def validate_approved_profile(
    approved: Mapping[str, Any], draft: Mapping[str, Any]
) -> None:
    exact_keys(approved, PROFILE_KEYS, "approved profile")
    validate_against_schema(approved, load_profile_schema())
    require(
        approved.get("artifact_status") == "IMMUTABLE_APPROVED_PROFILE",
        "approved profile artifact status mismatch",
    )
    approval = mapping(
        approved.get("approval_provenance"), "approved profile provenance"
    )
    exact_keys(approval, APPROVAL_KEYS, "approved profile provenance")
    require(
        approval.get("status") == "APPROVED"
        and approval.get("authority") == APPROVAL_AUTHORITY
        and approval.get("approval_id") == approval_id()
        and isinstance(approval.get("approved_at"), str)
        and UTC_RE.fullmatch(cast(str, approval.get("approved_at"))) is not None
        and approval.get("approved_contract_fingerprint")
        == APPROVED_CONTRACT_FINGERPRINT,
        "approved profile provenance mismatch",
    )
    for key in UNCHANGED_PROFILE_KEYS:
        require(
            json_equal(approved.get(key), draft.get(key)),
            f"approved profile changed forbidden field: {key}",
        )
    fingerprint = contract_fingerprint(approved)
    require(
        fingerprint
        == approved.get("presentation_contract_fingerprint")
        == APPROVED_CONTRACT_FINGERPRINT,
        "approved profile fingerprint mismatch",
    )


def serialize(profile: Mapping[str, Any]) -> bytes:
    return (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def recheck_draft(draft: LoadedDraft) -> None:
    try:
        raw = draft.path.read_bytes()
    except OSError as exc:
        raise ApprovalPublicationError(
            f"DRAFT profile TOCTOU reread failed: {exc}"
        ) from exc
    require(
        raw == draft.raw and sha256_bytes(raw) == DRAFT_PROFILE_SHA256,
        "DRAFT profile TOCTOU mismatch",
    )


def rollback_publication(
    output: Path,
    staging: Path | None,
    final_link_created: bool,
    staged_identity: tuple[int, int] | None,
    directory_created: bool,
) -> list[str]:
    blockers: list[str] = []
    if final_link_created and staged_identity is not None and os.path.lexists(output):
        try:
            if path_identity(output) == staged_identity:
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
    if directory_created and output.parent.exists():
        try:
            if any(output.parent.iterdir()):
                blockers.append("non-empty output directory preserved")
            else:
                output.parent.rmdir()
        except OSError as exc:
            blockers.append(f"output directory cleanup failed: {exc}")
    return blockers


def publish_profile_approval(
    source: DraftInput, output: Path, authorization: str
) -> PublicationResult:
    require(
        authorization == PUBLICATION_AUTHORIZATION,
        "exact profile approval publication authorization is required",
    )
    output = output.resolve(strict=False)
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent != output, "output directory mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(not output.parent.exists(), "new output directory already exists")
    require(
        not output.is_relative_to(REPO_ROOT.resolve(strict=False)),
        "approved profile output must be outside Git",
    )
    draft = load_draft(source)
    require(output != draft.path, "approved output must not alias the DRAFT source")
    approved_at = utc_now()
    approved = build_approved_profile(draft.payload, approved_at)
    encoded = serialize(approved)
    output.parent.mkdir()
    directory_created = True
    descriptor = -1
    staging: Path | None = None
    final_link_created = False
    staged_identity: tuple[int, int] | None = None
    try:
        descriptor, raw_staging = tempfile.mkstemp(
            prefix=".dinva-profile-approval-", suffix=".tmp", dir=output.parent
        )
        staging = Path(raw_staging)
        os.chmod(staging, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged_identity = path_identity(staging)
        staged_payload, staged_raw = load_json(staging, "staged approved profile")
        require(staged_raw == encoded, "staged approved profile bytes mismatch")
        validate_approved_profile(staged_payload, draft.payload)
        recheck_draft(draft)
        os.link(staging, output)
        final_link_created = True
        require(
            path_identity(output) == staged_identity,
            "published approved profile identity mismatch",
        )
        published, published_raw = load_json(output, "published approved profile")
        require(published_raw == encoded, "published approved profile bytes mismatch")
        validate_approved_profile(published, draft.payload)
        staging.unlink()
        require(
            path_identity(output) == staged_identity,
            "published approved profile identity changed before success",
        )
        require(
            set(output.parent.iterdir()) == {output},
            "approved profile final directory inventory mismatch",
        )
        return PublicationResult(
            output,
            sha256_bytes(published_raw),
            len(published_raw),
            approved_at,
            approval_id(),
        )
    except BaseException as error:
        blockers: list[str] = []
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                blockers.append(f"staging descriptor cleanup failed: {exc}")
        blockers.extend(
            rollback_publication(
                output,
                staging,
                final_link_created,
                staged_identity,
                directory_created,
            )
        )
        if blockers:
            raise ApprovalPublicationError(
                "approval publication rollback cleanup blocked: " + "; ".join(blockers)
            ) from error
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-profile", required=True, type=Path)
    parser.add_argument("--draft-profile-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = publish_profile_approval(
            DraftInput(
                cast(Path, args.draft_profile),
                cast(str, args.draft_profile_sha256),
            ),
            cast(Path, args.output),
            cast(str, args.authorization),
        )
    except (OSError, ApprovalPublicationError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_PRESENTATION_PROFILE=IMMUTABLE_APPROVED_PROFILE")
    print(f"APPROVAL_ID={result.approval_id}")
    print(f"APPROVED_AT={result.approved_at}")
    print(f"SHA256={result.sha256}")
    print(f"SIZE={result.size}")
    print(f"OUTPUT={result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
