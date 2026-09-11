from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_dinva_v0_2_governed_input_bridge import ROOT, load_file, write_json
from test_dinva_visual_successor import successor


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _, payload, _ = successor(tmp_path / "evidence", monkeypatch)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    publisher = load_file(
        "v03_approval_tests",
        ROOT / "scripts/publish_dinva_classic_presentation_profile_v0_3_approval.py",
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
    return dict(
        p=publisher,
        source=source,
        fingerprint=fingerprint,
        output=tmp_path / "approved-case" / publisher.OUTPUT_FILENAME,
        token=publisher.authorization_for(reviewed),
        payload=payload,
        reviewed=reviewed,
    )


def publish(case: dict[str, Any]) -> Any:
    return case["p"].publish_profile_approval(
        case["source"], case["fingerprint"], case["output"], case["token"]
    )


def test_content_bound_copy_production_renderer_and_second_publication(
    case: dict[str, Any],
) -> None:
    p = case["p"]
    renderer = load_file(
        "v03_approval_renderer", ROOT / "scripts/render_dinva_classic_quote_invoice.py"
    )
    with pytest.raises(renderer.RendererError, match="immutable/approved"):
        renderer.validate_profile(case["payload"], allow_test_profile=False)
    before = case["source"].path.read_bytes()
    result = publish(case)
    raw = result.path.read_bytes()
    approved = json.loads(raw)
    renderer.validate_profile(approved, allow_test_profile=False)
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
    assert case["source"].expected_sha256 in result.approval_id
    assert case["fingerprint"] in result.approval_id
    with pytest.raises(p.ProfileV03ApprovalError, match="already exists"):
        publish(case)
    assert result.path.read_bytes() == raw


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_sha",
        "wrong_fingerprint",
        "static",
        "legacy",
        "token_sha",
        "token_fingerprint",
        "post_review_mutation",
        "source_drift",
        "collision",
    ],
)
def test_approval_rejections(case: dict[str, Any], kind: str) -> None:
    p = case["p"]
    if kind == "wrong_sha":
        case["source"] = p.DraftInput(case["source"].path, "0" * 64)
    elif kind == "wrong_fingerprint":
        case["fingerprint"] = "0" * 64
    elif kind == "static":
        case["token"] = p.PUBLICATION_AUTHORIZATION_PREFIX
    elif kind == "legacy":
        case["token"] = case["token"].replace("V0_3", "V0_2")
    elif kind == "token_sha":
        case["token"] = case["token"].replace(case["source"].expected_sha256, "0" * 64)
    elif kind == "token_fingerprint":
        case["token"] = case["token"].replace(case["fingerprint"], "0" * 64)
    elif kind == "post_review_mutation":
        path = case["source"].path
        path.write_bytes(path.read_bytes() + b" ")
    elif kind == "source_drift":
        path = case["reviewed"].evidence[0].supplied_path
        path.write_bytes(path.read_bytes() + b" ")
    else:
        case["output"].parent.mkdir()
        case["output"].write_bytes(b"foreign output")
    with pytest.raises(p.ProfileV03ApprovalError):
        publish(case)
    if kind == "collision":
        assert case["output"].read_bytes() == b"foreign output"
    else:
        assert not case["output"].parent.exists()


@pytest.mark.parametrize(
    "kind",
    [
        "extra_binding",
        "wrong_predecessor",
        "binding_sha",
        "schema",
        "approval_state",
        "embedded_fingerprint",
    ],
)
def test_subject_structure_fail_closed(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    # Re-pin synthetic SHA only to exercise checks beneath the real exact-SHA gate.
    payload = copy.deepcopy(case["payload"])
    if kind == "extra_binding":
        payload["reference_provenance"].append(payload["reference_provenance"][0])
    elif kind == "wrong_predecessor":
        binding = next(
            b
            for b in payload["reference_provenance"]
            if b["role"] == "IMMUTABLE_APPROVED_V0_2_PREDECESSOR_PROFILE"
        )
        binding["expected_sha256"] = binding["actual_sha256"] = "0" * 64
    elif kind == "binding_sha":
        payload["reference_provenance"][0]["expected_sha256"] = "0" * 64
    elif kind == "schema":
        payload["schema_version"] = "dinva_classic_presentation_profile.v0.2"
    elif kind == "approval_state":
        payload["approval_provenance"]["authority"] = "IGOR_DIRECT_HUMAN_APPROVAL"
    else:
        payload["presentation_contract_fingerprint"] = "0" * 64
    sha = write_json(case["source"].path, payload)
    monkeypatch.setattr(case["p"], "REVIEWED_DRAFT_SHA256", sha)
    case["source"] = case["p"].DraftInput(case["source"].path, sha)
    with pytest.raises(case["p"].ProfileV03ApprovalError):
        publish(case)
    assert not case["output"].parent.exists()


@pytest.mark.parametrize("kind", ["draft", "source", "collision", "io_failure"])
def test_atomic_publication_races_are_fail_closed(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    p = case["p"]
    original = p.os.link

    def raced_link(staging: Path, output: Path) -> None:
        if kind == "io_failure":
            raise OSError("synthetic link failure")
        if kind == "collision":
            output.write_bytes(b"foreign race winner")
        else:
            path = (
                case["source"].path
                if kind == "draft"
                else case["reviewed"].evidence[0].supplied_path
            )
            path.write_bytes(path.read_bytes() + b" ")
        original(staging, output)

    monkeypatch.setattr(p.os, "link", raced_link)
    with pytest.raises((OSError, p.ProfileV03ApprovalError)):
        publish(case)
    if kind == "collision":
        assert case["output"].read_bytes() == b"foreign race winner"
        assert set(case["output"].parent.iterdir()) == {case["output"]}
    else:
        assert not case["output"].parent.exists()


def test_inside_git_paths_rejected(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    p = case["p"]
    monkeypatch.setattr(p, "REPO_ROOT", case["source"].path.parent)
    with pytest.raises(p.ProfileV03ApprovalError, match="outside Git"):
        publish(case)


def test_cli_synthetic_only(
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
        case["token"],
    ]
    assert p.main(args) == 0
    assert "IMMUTABLE_APPROVED_PROFILE" in capsys.readouterr().out
    assert p.main(args) == 1
    assert "HOLD:" in capsys.readouterr().out
