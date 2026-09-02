from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXED_APPROVED_AT = "2026-09-02T12:34:56Z"


def load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def publisher() -> ModuleType:
    return load_file(
        "dinva_profile_approval_publisher_test",
        ROOT / "scripts" / "publish_dinva_classic_presentation_profile_approval.py",
    )


def synthetic_case(tmp_path: Path, publisher: ModuleType) -> dict[str, Any]:
    helpers = load_file(
        "dinva_profile_approval_render_helpers",
        ROOT / "tests" / "test_render_dinva_classic_quote_invoice.py",
    )
    case = helpers.make_case(tmp_path)
    draft_path = case["profile_path"]
    draft_raw = draft_path.read_bytes()
    draft_sha = hashlib.sha256(draft_raw).hexdigest()
    publisher.__dict__["REPO_ROOT"] = tmp_path / "synthetic-repo"
    publisher.__dict__["DRAFT_PROFILE_SHA256"] = draft_sha
    publisher.__dict__["APPROVED_CONTRACT_FINGERPRINT"] = case["profile"][
        "presentation_contract_fingerprint"
    ]
    publisher.__dict__["utc_now"] = lambda: FIXED_APPROVED_AT
    return {
        **case,
        "draft_path": draft_path,
        "draft_raw": draft_raw,
        "draft_sha": draft_sha,
        "source": publisher.DraftInput(draft_path, draft_sha),
    }


def output_path(
    tmp_path: Path, publisher: ModuleType, name: str = "approval-case"
) -> Path:
    return tmp_path / name / str(publisher.OUTPUT_FILENAME)


def write_payload(path: Path, payload: dict[str, Any]) -> tuple[bytes, str]:
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw, hashlib.sha256(raw).hexdigest()


def test_exact_draft_publishes_only_approved_state_and_renderer_accepts(
    tmp_path: Path, publisher: ModuleType
) -> None:
    assert (
        publisher.DRAFT_PROFILE_SHA256
        == "e1240c471435ba99709ff8cd44571151e9467f1d010b7e83770869383d734b40"
    )
    assert (
        publisher.APPROVED_CONTRACT_FINGERPRINT
        == "246ad0bf2526319eb5b0be067f6d8493560b5ec0722662b1eaf2340ec31bd8cc"
    )
    case = synthetic_case(tmp_path, publisher)
    output = output_path(tmp_path, publisher)

    result = publisher.publish_profile_approval(
        case["source"], output, publisher.PUBLICATION_AUTHORIZATION
    )

    approved, approved_raw = publisher.load_json(output, "approved profile")
    draft = case["profile"]
    changed = {
        key
        for key in publisher.PROFILE_KEYS
        if not publisher.json_equal(approved[key], draft[key])
    }
    assert changed == {"artifact_status", "approval_provenance"}
    assert approved["artifact_status"] == "IMMUTABLE_APPROVED_PROFILE"
    assert approved["approval_provenance"] == {
        "status": "APPROVED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approval_id": (
            "IGOR-DINVA-CLASSIC-PRESENTATION-PROFILE-V0-1-20260902-001"
            f"|DRAFT_SHA256={case['draft_sha']}"
        ),
        "approved_at": FIXED_APPROVED_AT,
        "approved_contract_fingerprint": case["profile"][
            "presentation_contract_fingerprint"
        ],
    }
    assert publisher.canonical_json(approved["presentation_contract"]) == (
        publisher.canonical_json(draft["presentation_contract"])
    )
    assert approved["reference_provenance"] == draft["reference_provenance"]
    assert approved["presentation_contract_fingerprint"] == (
        publisher.contract_fingerprint(approved)
    )
    assert result.sha256 == hashlib.sha256(approved_raw).hexdigest()
    assert result.size == len(approved_raw)
    assert result.approved_at == FIXED_APPROVED_AT
    assert result.approval_id.endswith(case["draft_sha"])
    assert case["draft_path"].read_bytes() == case["draft_raw"]
    assert set(output.parent.iterdir()) == {output}
    assert not any(
        path.suffix.casefold() in {".xlsx", ".pdf"} for path in output.parent.iterdir()
    )
    publisher.validate_against_schema(approved, publisher.load_profile_schema())
    assert (
        case["renderer"].validate_profile(approved, allow_test_profile=False)
        == approved["presentation_contract"]
    )


def test_draft_sha_is_an_exact_content_addressed_boundary(
    tmp_path: Path, publisher: ModuleType
) -> None:
    case = synthetic_case(tmp_path, publisher)
    with pytest.raises(publisher.ApprovalPublicationError, match="format"):
        publisher.load_draft(publisher.DraftInput(case["draft_path"], "invalid"))
    with pytest.raises(publisher.ApprovalPublicationError, match="approved source"):
        publisher.load_draft(publisher.DraftInput(case["draft_path"], "0" * 64))

    modified_path = tmp_path / "modified-recomputed.json"
    modified_raw = case["draft_raw"] + b"\n"
    modified_path.write_bytes(modified_raw)
    with pytest.raises(publisher.ApprovalPublicationError, match="approved source"):
        publisher.load_draft(
            publisher.DraftInput(
                modified_path, hashlib.sha256(modified_raw).hexdigest()
            )
        )

    wrong_actual_path = tmp_path / "wrong-actual.json"
    wrong_actual_path.write_bytes(case["draft_raw"] + b" ")
    with pytest.raises(publisher.ApprovalPublicationError, match="actual bytes"):
        publisher.load_draft(publisher.DraftInput(wrong_actual_path, case["draft_sha"]))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("contract", "fingerprint"),
        ("stored_fingerprint", "fingerprint"),
        ("artifact_status", "DRAFT candidate"),
        ("schema_version", "schema const"),
        ("approval_status", "DRAFT_UNAPPROVED"),
        ("approval_authority", "DRAFT_UNAPPROVED"),
    ],
)
def test_draft_semantic_mutations_are_rejected(
    tmp_path: Path,
    publisher: ModuleType,
    mutation: str,
    message: str,
) -> None:
    case = synthetic_case(tmp_path, publisher)
    payload = copy.deepcopy(case["profile"])
    if mutation == "contract":
        payload["presentation_contract"]["optional_elements"].append("mutation")
    elif mutation == "stored_fingerprint":
        payload["presentation_contract_fingerprint"] = "0" * 64
    elif mutation == "artifact_status":
        payload["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    elif mutation == "schema_version":
        payload["schema_version"] = "wrong"
    elif mutation == "approval_status":
        payload["approval_provenance"]["status"] = "APPROVED"
    else:
        payload["approval_provenance"]["authority"] = "IGOR_DIRECT_HUMAN_APPROVAL"
    path = tmp_path / f"{mutation}.json"
    _raw, digest = write_payload(path, payload)
    publisher.__dict__["DRAFT_PROFILE_SHA256"] = digest
    with pytest.raises(publisher.ApprovalPublicationError, match=message):
        publisher.load_draft(publisher.DraftInput(path, digest))


def test_duplicate_keys_and_non_utf8_are_rejected(
    tmp_path: Path, publisher: ModuleType
) -> None:
    case = synthetic_case(tmp_path, publisher)
    duplicate_raw = case["draft_raw"].replace(
        b'"artifact_status":',
        b'"artifact_status":"DRAFT_PROFILE_CANDIDATE","artifact_status":',
        1,
    )
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_bytes(duplicate_raw)
    duplicate_sha = hashlib.sha256(duplicate_raw).hexdigest()
    publisher.__dict__["DRAFT_PROFILE_SHA256"] = duplicate_sha
    with pytest.raises(publisher.ApprovalPublicationError, match="duplicate JSON key"):
        publisher.load_draft(publisher.DraftInput(duplicate_path, duplicate_sha))

    non_utf8_path = tmp_path / "non-utf8.json"
    non_utf8_path.write_bytes(b"\xff")
    non_utf8_sha = hashlib.sha256(b"\xff").hexdigest()
    publisher.__dict__["DRAFT_PROFILE_SHA256"] = non_utf8_sha
    with pytest.raises(publisher.ApprovalPublicationError, match="strict UTF-8"):
        publisher.load_draft(publisher.DraftInput(non_utf8_path, non_utf8_sha))


def test_authorization_and_output_boundaries_are_fail_closed(
    tmp_path: Path, publisher: ModuleType
) -> None:
    case = synthetic_case(tmp_path, publisher)
    output = output_path(tmp_path, publisher)
    with pytest.raises(publisher.ApprovalPublicationError, match="authorization"):
        publisher.publish_profile_approval(case["source"], output, "WRONG")
    assert not output.parent.exists()

    inside_output = publisher.REPO_ROOT / "inside-case" / publisher.OUTPUT_FILENAME
    with pytest.raises(publisher.ApprovalPublicationError, match="outside Git"):
        publisher.publish_profile_approval(
            case["source"], inside_output, publisher.PUBLICATION_AUTHORIZATION
        )
    assert not inside_output.parent.exists()

    output.parent.mkdir()
    with pytest.raises(publisher.ApprovalPublicationError, match="already exists"):
        publisher.publish_profile_approval(
            case["source"], output, publisher.PUBLICATION_AUTHORIZATION
        )
    assert list(output.parent.iterdir()) == []

    existing_output = output_path(tmp_path, publisher, "existing-output-case")
    existing_output.parent.mkdir()
    existing_output.write_text("preserve", encoding="utf-8")
    with pytest.raises(publisher.ApprovalPublicationError, match="already exists"):
        publisher.publish_profile_approval(
            case["source"], existing_output, publisher.PUBLICATION_AUTHORIZATION
        )
    assert existing_output.read_text(encoding="utf-8") == "preserve"


def test_toctou_rolls_back_owned_staging_and_new_directory(
    tmp_path: Path, publisher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = synthetic_case(tmp_path, publisher)
    output = output_path(tmp_path, publisher)
    original_recheck = publisher.recheck_draft

    def mutate_then_recheck(draft: Any) -> None:
        draft.path.write_bytes(draft.raw + b"\n")
        original_recheck(draft)

    monkeypatch.setattr(publisher, "recheck_draft", mutate_then_recheck)
    with pytest.raises(publisher.ApprovalPublicationError, match="TOCTOU"):
        publisher.publish_profile_approval(
            case["source"], output, publisher.PUBLICATION_AUTHORIZATION
        )
    assert not output.exists()
    assert not output.parent.exists()


def test_publisher_is_json_only_and_does_not_import_renderer(
    publisher: ModuleType,
) -> None:
    source = (
        ROOT / "scripts" / "publish_dinva_classic_presentation_profile_approval.py"
    ).read_text(encoding="utf-8")
    assert "render_dinva_classic_quote_invoice" not in source
    assert "validate_dinva_classic_quote_invoice" not in source
    assert publisher.OUTPUT_FILENAME.endswith(".json")
    assert ".xlsx" not in publisher.OUTPUT_FILENAME.casefold()
    assert ".pdf" not in publisher.OUTPUT_FILENAME.casefold()
