"""Publish an approved DINVA classic presentation profile v0.2 after approval."""

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
PROFILE_SCHEMA_VERSION = "dinva_classic_presentation_profile.v0.2"
PROFILE_ID = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_2"
DOCUMENT_FAMILY = "DINVA_CLASSIC_QUOTE_INVOICE_V0_1"
OUTPUT_FILENAME = "dinva-classic-presentation-profile-v0.2-APPROVED.json"
PUBLICATION_AUTHORIZATION_PREFIX = (
    "IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_V0_2_APPROVAL_PUBLICATION_AUTHORIZED"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ProfileV02ApprovalError(ValueError):
    """Approval publication would violate the v0.2 profile boundary."""


@dataclass(frozen=True)
class DraftInput:
    path: Path
    expected_sha256: str


@dataclass(frozen=True)
class LoadedDraft:
    path: Path
    raw: bytes
    payload: dict[str, Any]
    sha256: str
    contract_fingerprint: str


@dataclass(frozen=True)
class PublicationResult:
    path: Path
    sha256: str
    size: int
    approved_at: str
    approval_id: str


def fail(message: str) -> NoReturn:
    raise ProfileV02ApprovalError(message)


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
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileV02ApprovalError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    require(isinstance(value, Mapping), f"{label} root must be an object")
    return dict(cast(Mapping[str, Any], value))


def mapping(value: object, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def load_draft(source: DraftInput) -> LoadedDraft:
    require(
        SHA256_RE.fullmatch(source.expected_sha256) is not None,
        "DRAFT profile supplied SHA-256 format is invalid",
    )
    path = source.path.resolve(strict=True)
    require(
        not path.is_relative_to(REPO_ROOT.resolve(strict=False)),
        "DRAFT profile must be outside Git",
    )
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    require(digest == source.expected_sha256, "DRAFT profile SHA-256 mismatch")
    profile = load_json(raw, "DRAFT profile")
    expected_keys = {
        "schema_version",
        "profile_id",
        "document_family",
        "artifact_status",
        "reference_provenance",
        "presentation_contract",
        "presentation_contract_fingerprint",
        "approval_provenance",
    }
    require(set(profile) == expected_keys, "DRAFT profile fields mismatch")
    require(
        profile.get("schema_version") == PROFILE_SCHEMA_VERSION
        and profile.get("profile_id") == PROFILE_ID
        and profile.get("document_family") == DOCUMENT_FAMILY
        and profile.get("artifact_status") == "DRAFT_PROFILE_CANDIDATE",
        "DRAFT profile identity mismatch",
    )
    approval = mapping(profile.get("approval_provenance"), "DRAFT approval provenance")
    require(
        approval
        == {
            "status": "DRAFT_UNAPPROVED",
            "authority": None,
            "approval_id": None,
            "approved_at": None,
            "approved_contract_fingerprint": None,
        },
        "source profile is not DRAFT_UNAPPROVED",
    )
    contract = mapping(profile.get("presentation_contract"), "presentation contract")
    fingerprint = sha256_bytes(canonical_json(contract))
    require(
        profile.get("presentation_contract_fingerprint") == fingerprint,
        "DRAFT profile contract fingerprint mismatch",
    )
    provenance = profile.get("reference_provenance")
    require(isinstance(provenance, list), "DRAFT profile provenance missing")
    roles = [
        mapping(item, "profile provenance").get("role")
        for item in cast(list[Any], provenance)
    ]
    require(
        roles.count("CLASSIC_FAMILY_EVIDENCE") == 3
        and roles.count("CANONICAL_LOGO_HUMAN_DECISION") == 1
        and roles.count("IMMUTABLE_APPROVED_PREDECESSOR_PROFILE") == 1
        and "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE" not in roles,
        "DRAFT profile governed evidence roles mismatch",
    )
    require(path.read_bytes() == raw, "DRAFT profile changed during validation")
    return LoadedDraft(path, raw, profile, digest, fingerprint)


def authorization_for(draft: LoadedDraft) -> str:
    return (
        f"{PUBLICATION_AUTHORIZATION_PREFIX}|DRAFT_SHA256={draft.sha256}|"
        f"CONTRACT_FINGERPRINT={draft.contract_fingerprint}"
    )


def approval_id(draft: LoadedDraft) -> str:
    return (
        "IGOR-DINVA-CLASSIC-PRESENTATION-PROFILE-V0-2|" f"DRAFT_SHA256={draft.sha256}"
    )


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_approved_profile(draft: LoadedDraft, approved_at: str) -> dict[str, Any]:
    require(UTC_RE.fullmatch(approved_at) is not None, "approval timestamp is invalid")
    approved = copy.deepcopy(draft.payload)
    approved["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    approved["approval_provenance"] = {
        "status": "APPROVED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approval_id": approval_id(draft),
        "approved_at": approved_at,
        "approved_contract_fingerprint": draft.contract_fingerprint,
    }
    for key in draft.payload:
        if key not in {"artifact_status", "approval_provenance"}:
            require(
                canonical_json(approved[key]) == canonical_json(draft.payload[key]),
                f"approved profile changed forbidden field: {key}",
            )
    return approved


def path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat()
    return metadata.st_dev, metadata.st_ino


def publish_profile_approval(
    source: DraftInput, output: Path, authorization: str
) -> PublicationResult:
    draft = load_draft(source)
    require(
        authorization == authorization_for(draft),
        "exact v0.2 profile approval publication authorization is required",
    )
    output = output.resolve(strict=False)
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent.parent.is_dir(), "output directory owner must already exist")
    require(
        not output.parent.exists() and not output.exists(),
        "new output path already exists",
    )
    require(
        not output.is_relative_to(REPO_ROOT.resolve(strict=False)),
        "approved profile output must be outside Git",
    )
    approved_at = utc_now()
    approved = build_approved_profile(draft, approved_at)
    encoded = (json.dumps(approved, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    final_link_created = False
    staged_identity: tuple[int, int] | None = None
    try:
        descriptor, raw_staging = tempfile.mkstemp(
            prefix=".dinva-profile-v02-approval-", suffix=".tmp", dir=output.parent
        )
        staging = Path(raw_staging)
        os.chmod(staging, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staged_identity = path_identity(staging)
        require(
            load_json(staging.read_bytes(), "staged profile") == approved,
            "staged profile mismatch",
        )
        require(draft.path.read_bytes() == draft.raw, "DRAFT profile TOCTOU mismatch")
        os.link(staging, output)
        final_link_created = True
        require(
            path_identity(output) == staged_identity,
            "published profile identity mismatch",
        )
        require(
            load_json(output.read_bytes(), "published profile") == approved,
            "published profile mismatch",
        )
        staging.unlink()
        require(
            set(output.parent.iterdir()) == {output},
            "profile final directory inventory mismatch",
        )
        return PublicationResult(
            output,
            sha256_bytes(encoded),
            len(encoded),
            approved_at,
            approval_id(draft),
        )
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if (
            final_link_created
            and staged_identity is not None
            and output.exists()
            and path_identity(output) == staged_identity
        ):
            output.unlink()
        if staging is not None and staging.exists():
            staging.unlink()
        if output.parent.exists() and not any(output.parent.iterdir()):
            output.parent.rmdir()
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
            DraftInput(args.draft_profile, args.draft_profile_sha256),
            args.output,
            args.authorization,
        )
    except (OSError, ProfileV02ApprovalError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_PRESENTATION_PROFILE_V0_2=IMMUTABLE_APPROVED_PROFILE")
    print(f"APPROVAL_ID={result.approval_id}")
    print(f"APPROVED_AT={result.approved_at}")
    print(f"SHA256={result.sha256}")
    print(f"SIZE={result.size}")
    print(f"OUTPUT={result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
