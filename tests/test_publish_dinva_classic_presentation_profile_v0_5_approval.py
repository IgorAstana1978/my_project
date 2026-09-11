from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_dinva_v0_2_governed_input_bridge import ROOT, load_file, write_json
from test_dinva_v0_5_print_successor import (
    lifecycle_schema_accepts,
    print_successor,
)


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _, payload, _ = print_successor(tmp_path / "evidence", monkeypatch)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    publisher = load_file(
        "v05_approval_tests",
        ROOT / "scripts/publish_dinva_classic_presentation_profile_v0_5_approval.py",
    )
    draft = tmp_path / "reviewed.synthetic.json"
    sha = write_json(draft, payload)
    fingerprint = payload["presentation_contract_fingerprint"]
    bindings: dict[str, frozenset[str]] = {}
    for binding in payload["reference_provenance"]:
        role = binding["role"]
        bindings[role] = bindings.get(role, frozenset()) | {binding["actual_sha256"]}
    monkeypatch.setattr(publisher, "REVIEWED_DRAFT_SHA256", sha)
    monkeypatch.setattr(publisher, "REVIEWED_FINGERPRINT", fingerprint)
    monkeypatch.setattr(publisher, "REQUIRED_BINDINGS", bindings)
    source = publisher.DraftInput(draft, sha)
    reviewed = publisher.load_draft(source, fingerprint)
    output = tmp_path / "approved-case" / publisher.OUTPUT_FILENAME
    return {
        "p": publisher,
        "source": source,
        "fingerprint": fingerprint,
        "output": output,
        "token": publisher.authorization_for(reviewed, output),
        "payload": payload,
        "reviewed": reviewed,
    }


def publish(case: dict[str, Any]) -> Any:
    return case["p"].publish_profile_approval(
        case["source"], case["fingerprint"], case["output"], case["token"]
    )


def test_content_bound_lifecycle_only_copy_and_consumed_replay(
    case: dict[str, Any],
) -> None:
    p = case["p"]
    before = case["source"].path.read_bytes()
    result = publish(case)
    raw = result.path.read_bytes()
    approved = json.loads(raw)
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.size == len(raw)
    assert set(result.path.parent.iterdir()) == {result.path}
    assert case["source"].path.read_bytes() == before
    expected = copy.deepcopy(case["payload"])
    expected["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    expected["approval_provenance"] = {
        "status": "APPROVED",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approval_id": p.approval_id(case["reviewed"]),
        "approved_at": result.approved_at,
        "approved_contract_fingerprint": case["fingerprint"],
    }
    assert p.canonical_json(approved) == p.canonical_json(expected)
    assert approved["presentation_contract"] == case["payload"]["presentation_contract"]
    assert approved["presentation_contract_fingerprint"] == case["fingerprint"]
    schema = json.loads(
        (
            ROOT / "schemas/dinva_classic_presentation_profile_v0_5.schema.json"
        ).read_bytes()
    )
    assert lifecycle_schema_accepts(schema, approved)
    with pytest.raises(p.ProfileV05ApprovalError, match="already exists"):
        publish(case)
    assert result.path.read_bytes() == raw


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_sha",
        "wrong_fingerprint",
        "static",
        "v04_token",
        "token_content",
        "token_fingerprint",
        "wrong_action",
        "wrong_output",
        "post_review_mutation",
        "collision",
    ],
)
def test_approval_and_token_rejections(case: dict[str, Any], kind: str) -> None:
    p = case["p"]
    if kind == "wrong_sha":
        case["source"] = p.DraftInput(case["source"].path, "0" * 64)
    elif kind == "wrong_fingerprint":
        case["fingerprint"] = "0" * 64
    elif kind == "static":
        case["token"] = p.PUBLICATION_AUTHORIZATION_PREFIX
    elif kind == "v04_token":
        case["token"] = case["token"].replace("V0_5", "V0_4")
    elif kind == "token_content":
        case["token"] = case["token"].replace(case["source"].expected_sha256, "0" * 64)
    elif kind == "token_fingerprint":
        case["token"] = case["token"].replace(case["fingerprint"], "0" * 64)
    elif kind == "wrong_action":
        case["token"] = case["token"].replace(p.APPROVAL_ACTION, "RENDER_OR_DOWNSTREAM")
    elif kind == "wrong_output":
        case["output"] = (
            case["output"].parent.parent / "alternate-case" / p.OUTPUT_FILENAME
        )
    elif kind == "post_review_mutation":
        path = case["source"].path
        path.write_bytes(path.read_bytes() + b" ")
    else:
        case["output"].parent.mkdir()
        case["output"].write_bytes(b"foreign output")
    with pytest.raises(p.ProfileV05ApprovalError):
        publish(case)
    if kind == "collision":
        assert case["output"].read_bytes() == b"foreign output"
    else:
        assert not case["output"].parent.exists()


@pytest.mark.parametrize("binding_index", range(11))
def test_each_of_eleven_source_bindings_is_reread(
    case: dict[str, Any], binding_index: int
) -> None:
    source = case["reviewed"].evidence[binding_index].supplied_path
    source.write_bytes(source.read_bytes() + b" drift")
    with pytest.raises(case["p"].ProfileV05ApprovalError, match="source SHA"):
        publish(case)
    assert not case["output"].parent.exists()


@pytest.mark.parametrize("phase", ["before_link", "after_link"])
def test_source_toctou_rolls_back(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    p = case["p"]
    source = case["reviewed"].evidence[0].supplied_path
    if phase == "before_link":
        original_fsync = p.os.fsync

        def fsync(fd: int) -> None:
            original_fsync(fd)
            source.write_bytes(source.read_bytes() + b" drift")

        monkeypatch.setattr(p.os, "fsync", fsync)
    else:
        original_link = p.os.link

        def link(staging: Path, output: Path) -> None:
            original_link(staging, output)
            source.write_bytes(source.read_bytes() + b" drift")

        monkeypatch.setattr(p.os, "link", link)
    with pytest.raises(p.ProfileV05ApprovalError, match="source SHA"):
        publish(case)
    assert not case["output"].parent.exists()


@pytest.mark.parametrize("kind", ["mixed_lifecycle", "contract_mutation"])
def test_subject_mutation_fail_closed(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    payload = copy.deepcopy(case["payload"])
    if kind == "mixed_lifecycle":
        payload["artifact_status"] = "IMMUTABLE_APPROVED_PROFILE"
    else:
        payload["presentation_contract"]["contract_version"] = "mutated"
    sha = write_json(case["source"].path, payload)
    monkeypatch.setattr(case["p"], "REVIEWED_DRAFT_SHA256", sha)
    case["source"] = case["p"].DraftInput(case["source"].path, sha)
    with pytest.raises(case["p"].ProfileV05ApprovalError):
        publish(case)
    assert not case["output"].parent.exists()


def test_generated_presentation_contract_mutation_is_rejected(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    p = case["p"]
    original = p.copy.deepcopy

    def mutated(value: Any) -> Any:
        copied = original(value)
        copied["presentation_contract"]["contract_version"] = "mutated"
        return copied

    monkeypatch.setattr(p.copy, "deepcopy", mutated)
    with pytest.raises(p.ProfileV05ApprovalError, match="presentation mutation"):
        publish(case)
    assert not case["output"].parent.exists()


def test_inside_git_output_rejected(case: dict[str, Any]) -> None:
    p = case["p"]
    case["output"] = ROOT / "v05-approved.synthetic" / p.OUTPUT_FILENAME
    case["token"] = p.authorization_for(case["reviewed"], case["output"])
    with pytest.raises(p.ProfileV05ApprovalError, match="outside Git"):
        publish(case)
    assert not case["output"].parent.exists()


def test_json_only_action_does_not_delegate_downstream_authority() -> None:
    path = ROOT / "scripts/publish_dinva_classic_presentation_profile_v0_5_approval.py"
    source = path.read_text(encoding="utf-8").lower()
    for forbidden in ("openpyxl", "render_dinva", ".xlsx", ".pdf", "client_send"):
        assert forbidden not in source
    assert 'approval_action = "immutable_approval_publication"' in source
    assert "action={approval_action}" in source


def test_cli_requires_external_authorization(
    case: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    p = case["p"]
    args = [
        "--draft-profile",
        str(case["source"].path),
        "--draft-profile-sha256",
        case["source"].expected_sha256,
        "--contract-fingerprint",
        case["fingerprint"],
        "--output",
        str(case["output"]),
        "--authorization",
        "NOT-AUTHORIZED",
    ]
    assert p.main(args) == 1
    assert "HOLD:" in capsys.readouterr().out
    assert not case["output"].parent.exists()
