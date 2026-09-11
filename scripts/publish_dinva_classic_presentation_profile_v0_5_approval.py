"""Content-bound approval capability for one reviewed v0.5 subject; JSON only."""

from __future__ import annotations

import argparse
import copy
import json
import os
import stat
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from publish_dinva_classic_presentation_profile_v0_4_approval import (
    DraftInput,
    Evidence,
    LoadedDraft,
    ProfileV04ApprovalError,
    PublicationResult,
    ReviewedDraft,
    canonical_json,
    load_json,
    mapping,
    outside_git,
    path_identity,
    recheck,
    require,
    sha256_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWED_DRAFT_SHA256 = (
    "bf8ca678c21040e95a0d870a1657324dd42ecc297315135adc67061e7925dbef"
)
REVIEWED_FINGERPRINT = (
    "537cf6dfd60b25508b72995b0ec60207a9ce4c99e3a7a14dd8a53358c8b9ccef"
)
REQUIRED_BINDINGS = {
    "CLASSIC_FAMILY_EVIDENCE": frozenset(
        {
            "8cf9f2b4ecca94e51a9f868891b6bc00151ef4b05b012db0d875862599c5253c",
            "17e31d0312f728800d31fd4f125d285edb1114880500d4833261239b87ab58b5",
            "d8e652325c142a72ffa4aa390197b3e357b5efc317d07f6d763e01d3c1c4fec9",
        }
    ),
    "CANONICAL_LOGO_HUMAN_DECISION": frozenset(
        {"e7c043f19b7eb8606f59dd8e7de06b29ca4305cc1fe2362ecb93767dd589f63b"}
    ),
    "IMMUTABLE_APPROVED_PREDECESSOR_PROFILE": frozenset(
        {"3c3c448c268e2bc87aa9255720e26e7d26fd5f3faa0bd0a42704ad8f69e3f3ca"}
    ),
    "IMMUTABLE_APPROVED_V0_2_PREDECESSOR_PROFILE": frozenset(
        {"93c41c9f0399e6a6d27e1b075ceb2ab971b345f6c64143c637ac1e2ad02a90b7"}
    ),
    "IMMUTABLE_APPROVED_V0_3_PREDECESSOR_PROFILE": frozenset(
        {"4fab7cb8898dcff55c75bd94b39cc1d8357a73fa59fbd4a0dc52dee5a45c67a8"}
    ),
    "NATIVE_C13_BOLD_ITALIC_WIDTH_MEASUREMENTS": frozenset(
        {"97956027a95bd23127f956a668bf69c9cb287ff46e47fe5f1145f9e8b29d9a51"}
    ),
    "NATIVE_OBJECT_BOLD_ITALIC_FONT_SOURCE": frozenset(
        {"3a29d114cb5229e8dbda5bef6c69be4a210a13b7277de4d66e9fc86963226f6c"}
    ),
    "NATIVE_COUNTRY_BOLD_FONT_SOURCE": frozenset(
        {"54fbe2c70af7c85a97bed0573227e3ccc4b2486012e3ca2a40c6bc77065846f5"}
    ),
    "IMMUTABLE_APPROVED_V0_4_PREDECESSOR_PROFILE": frozenset(
        {"dd2b7f01af54529f8d5f62ebeab168cb95b800af7fc55108822cafb306b5e4a6"}
    ),
}
OUTPUT_FILENAME = "dinva-classic-presentation-profile-v0.5-APPROVED.json"
APPROVAL_ACTION = "IMMUTABLE_APPROVAL_PUBLICATION"
PUBLICATION_AUTHORIZATION_PREFIX = (
    "IGOR_DINVA_CLASSIC_PRESENTATION_PROFILE_V0_5_APPROVAL_PUBLICATION_AUTHORIZED"
)
ProfileV05ApprovalError = ProfileV04ApprovalError


def load_draft(source: DraftInput, fingerprint: str) -> ReviewedDraft:
    require(
        source.expected_sha256 == REVIEWED_DRAFT_SHA256, "reviewed DRAFT SHA mismatch"
    )
    path = outside_git(source.path)
    raw = path.read_bytes()
    require(sha256_bytes(raw) == source.expected_sha256, "DRAFT actual SHA mismatch")
    payload = load_json(raw, "DRAFT v0.5")
    require(
        set(payload)
        == {
            "schema_version",
            "profile_id",
            "document_family",
            "artifact_status",
            "reference_provenance",
            "presentation_contract",
            "presentation_contract_fingerprint",
            "approval_provenance",
        },
        "DRAFT fields mismatch",
    )
    require(
        payload["schema_version"] == "dinva_classic_presentation_profile.v0.5"
        and payload["profile_id"] == "DINVA_CLASSIC_QUOTE_INVOICE_V0_1_DYNAMIC_V0_5"
        and payload["document_family"] == "DINVA_CLASSIC_QUOTE_INVOICE_V0_1"
        and payload["artifact_status"] == "DRAFT_PROFILE_CANDIDATE",
        "DRAFT identity mismatch",
    )
    require(
        payload["approval_provenance"]
        == {
            "status": "DRAFT_UNAPPROVED",
            "authority": None,
            "approval_id": None,
            "approved_at": None,
            "approved_contract_fingerprint": None,
        },
        "source is not coherent DRAFT_UNAPPROVED",
    )
    contract = mapping(payload["presentation_contract"], "contract")
    require(
        contract.get("contract_version") == "dinva_classic_presentation_contract.v0.5"
        and fingerprint
        == REVIEWED_FINGERPRINT
        == payload["presentation_contract_fingerprint"]
        == sha256_bytes(canonical_json(contract)),
        "reviewed contract fingerprint mismatch",
    )
    bindings = payload["reference_provenance"]
    require(
        isinstance(bindings, list) and len(bindings) == 11,
        "exact eleven bindings required",
    )
    seen: set[tuple[str, str]] = set()
    evidence = []
    for value in bindings:
        binding = mapping(value, "source binding")
        require(
            set(binding) == {"path", "role", "expected_sha256", "actual_sha256"},
            "source binding fields mismatch",
        )
        role, digest = binding["role"], binding["expected_sha256"]
        require(
            isinstance(role, str)
            and isinstance(digest, str)
            and digest == binding["actual_sha256"]
            and digest in REQUIRED_BINDINGS.get(role, frozenset())
            and (role, digest) not in seen,
            "source binding identity/SHA mismatch",
        )
        seen.add((role, digest))
        supplied = Path(binding["path"])
        evidence.append(Evidence(supplied, outside_git(supplied), digest))
    require(
        seen
        == {
            (role, digest)
            for role, digests in REQUIRED_BINDINGS.items()
            for digest in digests
        },
        "exact source binding set mismatch",
    )
    reviewed = ReviewedDraft(
        LoadedDraft(path, raw, payload, source.expected_sha256, fingerprint),
        source.path,
        tuple(evidence),
    )
    recheck(reviewed)
    return reviewed


def normalized_output_sha256(output: Path) -> str:
    normalized = str(output.resolve(strict=False)).casefold().encode("utf-8")
    return sha256_bytes(normalized)


def authorization_for(reviewed: ReviewedDraft, output: Path) -> str:
    draft = reviewed.subject
    return (
        f"{PUBLICATION_AUTHORIZATION_PREFIX}|ACTION={APPROVAL_ACTION}|"
        f"DRAFT_SHA256={draft.sha256}|"
        f"CONTRACT_FINGERPRINT={draft.contract_fingerprint}|"
        f"OUTPUT_PATH_SHA256={normalized_output_sha256(output)}"
    )


def approval_id(reviewed: ReviewedDraft) -> str:
    draft = reviewed.subject
    return (
        f"IGOR-DINVA-CLASSIC-PRESENTATION-PROFILE-V0-5|DRAFT_SHA256={draft.sha256}|"
        f"CONTRACT_FINGERPRINT={draft.contract_fingerprint}"
    )


def validate_approved(approved: dict[str, Any], reviewed: ReviewedDraft) -> None:
    draft = reviewed.subject
    require(
        approved.get("artifact_status") == "IMMUTABLE_APPROVED_PROFILE"
        and approved.get("approval_provenance")
        == {
            "status": "APPROVED",
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
            "approval_id": approval_id(reviewed),
            "approved_at": approved["approval_provenance"]["approved_at"],
            "approved_contract_fingerprint": draft.contract_fingerprint,
        }
        and isinstance(approved["approval_provenance"]["approved_at"], str)
        and bool(approved["approval_provenance"]["approved_at"]),
        "approved lifecycle mismatch",
    )
    for key in draft.payload:
        if key not in {"artifact_status", "approval_provenance"}:
            require(
                canonical_json(approved[key]) == canonical_json(draft.payload[key]),
                "forbidden presentation mutation",
            )


def publish_profile_approval(
    source: DraftInput, fingerprint: str, output: Path, authorization: str
) -> PublicationResult:
    reviewed = load_draft(source, fingerprint)
    output = output.resolve(strict=False)
    require(
        authorization == authorization_for(reviewed, output),
        "exact v0.5 action/content/output-bound authorization required",
    )
    require(
        not output.is_relative_to(REPO_ROOT.resolve()), "output must be outside Git"
    )
    require(output.name == OUTPUT_FILENAME, "output filename mismatch")
    require(output.parent.parent.is_dir(), "output owner must already exist")
    require(
        not output.parent.exists() and not output.exists(),
        "new output path already exists",
    )
    timestamp = datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    approved: dict[str, Any] = copy.deepcopy(reviewed.subject.payload)
    approved["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    approved["approval_provenance"] = {
        "status": "APPROVED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approval_id": approval_id(reviewed),
        "approved_at": timestamp,
        "approved_contract_fingerprint": fingerprint,
    }
    validate_approved(approved, reviewed)
    raw = (
        json.dumps(approved, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    recheck(reviewed)
    output.parent.mkdir()
    descriptor = -1
    staging: Path | None = None
    identity: tuple[int, int] | None = None
    linked = False
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".dinva-v05-approval-", suffix=".tmp", dir=output.parent
        )
        staging = Path(name)
        identity = path_identity(staging)
        os.chmod(staging, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(
            staging.read_bytes() == raw and path_identity(staging) == identity,
            "staged profile mismatch",
        )
        recheck(reviewed)
        os.link(staging, output)
        linked = True
        require(
            path_identity(output) == identity and output.read_bytes() == raw,
            "published profile mismatch",
        )
        published = load_json(output.read_bytes(), "APPROVED v0.5")
        validate_approved(published, reviewed)
        recheck(reviewed)
        staging.unlink()
        require(set(output.parent.iterdir()) == {output}, "output inventory mismatch")
        return PublicationResult(
            output, sha256_bytes(raw), len(raw), timestamp, approval_id(reviewed)
        )
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if linked and output.exists() and path_identity(output) == identity:
            output.unlink()
        if (
            staging is not None
            and staging.exists()
            and path_identity(staging) == identity
        ):
            staging.unlink()
        if output.parent.exists() and not any(output.parent.iterdir()):
            output.parent.rmdir()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-profile", required=True, type=Path)
    parser.add_argument("--draft-profile-sha256", required=True)
    parser.add_argument("--contract-fingerprint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorization", required=True)
    args = parser.parse_args(argv)
    try:
        result = publish_profile_approval(
            DraftInput(args.draft_profile, args.draft_profile_sha256),
            args.contract_fingerprint,
            args.output,
            args.authorization,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"HOLD: {exc}")
        return 1
    print("DINVA_CLASSIC_PRESENTATION_PROFILE_V0_5=IMMUTABLE_APPROVED_PROFILE")
    print(f"APPROVAL_ID={result.approval_id}\nAPPROVED_AT={result.approved_at}")
    print(f"SHA256={result.sha256}\nSIZE={result.size}\nOUTPUT={result.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
