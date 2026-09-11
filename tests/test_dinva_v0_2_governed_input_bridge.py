from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from openpyxl import Workbook  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def load_file(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def family_workbook(path: Path, first_item_row: int) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Лист1"
    sheet["C2"] = "ТОО «ДиН ВА-КЭС»"
    sheet["G9"] = "ВНИМАНИЕ!"
    headers = {
        "B": "№ п/п",
        "C": "Наименование",
        "D": "Ед.",
        "E": "Кол-во",
        "F": "Применяемые приборы и аппараты согласно схемы",
        "G": "Корпус (ВхШхГ) степень защиты",
        "H": "Цена",
        "I": "Сумма",
    }
    for column, value in headers.items():
        sheet[f"{column}15"] = value
    sheet.cell(first_item_row, 2).value = 1
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.paperSize = "9"
    sheet.page_setup.scale = 54
    workbook.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_profile_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, list[Any], Any, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    producer = load_file(
        "dinva_profile_v02_producer_for_bridge_tests",
        ROOT / "scripts" / "extract_dinva_classic_presentation_profile_v0_2.py",
    )
    render_helpers = load_file(
        "dinva_render_helpers_for_bridge_tests",
        ROOT / "tests" / "test_render_dinva_classic_quote_invoice.py",
    )
    family_paths = [tmp_path / f"family-{index}.xlsx" for index in range(3)]
    family_hashes = [
        family_workbook(path, first_row)
        for path, first_row in zip(family_paths, [16, 16, 17], strict=True)
    ]
    dynamic_contract = render_helpers.dynamic_profile()["presentation_contract"]
    old_contract = copy.deepcopy(dynamic_contract)
    old_contract["contract_version"] = "dinva_classic_presentation_contract.v0.1"
    dynamic_company = dynamic_contract["fixed_blocks"]["company"]
    old_contract["fixed_blocks"]["company"] = {
        "C2": "ТОО «ДиН ВА-КЭС»",
        "C3": "Республика Казахстан",
        "B4": dynamic_company["B4"],
        "B5": dynamic_company["B5"],
        "B6": dynamic_company["B6"],
        "G2": dynamic_company["I2"],
        "G3": dynamic_company["I3"],
        "G4": dynamic_company["I4"],
        "G5": dynamic_company["I5"],
        "G6": dynamic_company["I6"],
    }
    predecessor = {
        "schema_version": "dinva_classic_presentation_profile.v0.1",
        "artifact_status": "IMMUTABLE_APPROVED_PROFILE",
        "reference_provenance": [
            {"role": "CLASSIC_FAMILY_EVIDENCE", "actual_sha256": digest}
            for digest in family_hashes
        ],
        "presentation_contract": old_contract,
        "presentation_contract_fingerprint": hashlib.sha256(
            canonical_json(old_contract)
        ).hexdigest(),
        "approval_provenance": {
            "status": "APPROVED",
            "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        },
    }
    predecessor_path = tmp_path / "predecessor.json"
    predecessor_sha = write_json(predecessor_path, predecessor)
    logo_raw = base64.b64decode(old_contract["assets"][0]["data_base64"])
    logo_sha = hashlib.sha256(logo_raw).hexdigest()
    logo_pixel_fingerprint = "a" * 64
    logo_decision = {
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "canonical_logo_decision": {
            "raw_sha256": logo_sha,
            "normalized_pixel_fingerprint": logo_pixel_fingerprint,
        },
        "source_bindings": [
            {
                "role": "CLASSIC_FAMILY_EVIDENCE",
                "actual_workbook_sha256": digest,
            }
            for digest in family_hashes
        ],
    }
    logo_decision_path = tmp_path / "logo-decision.json"
    logo_decision_sha = write_json(logo_decision_path, logo_decision)
    monkeypatch.setattr(producer, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(producer, "REQUIRED_FAMILY_SHA256S", frozenset(family_hashes))
    monkeypatch.setattr(producer, "PREDECESSOR_PROFILE_SHA256", predecessor_sha)
    monkeypatch.setattr(producer, "CANONICAL_LOGO_DECISION_SHA256", logo_decision_sha)
    monkeypatch.setattr(producer, "CANONICAL_LOGO_RAW_SHA256", logo_sha)
    monkeypatch.setattr(
        producer, "CANONICAL_LOGO_PIXEL_FINGERPRINT", logo_pixel_fingerprint
    )
    family = [
        producer.BoundInput(path, digest)
        for path, digest in zip(family_paths, family_hashes, strict=True)
    ]
    return (
        producer,
        family,
        producer.BoundInput(predecessor_path, predecessor_sha),
        producer.BoundInput(logo_decision_path, logo_decision_sha),
    )


def test_production_builders_feed_renderer_and_independent_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer, family, predecessor, logo_decision = build_profile_sources(
        tmp_path / "profile-sources", monkeypatch
    )
    draft_profile = producer.extract_profile_v0_2(family, predecessor, logo_decision)
    roles = [item["role"] for item in draft_profile["reference_provenance"]]
    assert roles.count("CLASSIC_FAMILY_EVIDENCE") == 3
    assert "CERTIFIED_RUNTIME_TEMPLATE_EVIDENCE" not in roles
    draft_path = (
        tmp_path
        / "profile-draft-case"
        / "dinva-classic-presentation-profile-v0.2-DRAFT.json"
    )
    producer.publish_draft_profile(draft_profile, draft_path)

    approver = load_file(
        "dinva_profile_v02_approver_for_bridge_tests",
        ROOT
        / "scripts"
        / "publish_dinva_classic_presentation_profile_v0_2_approval.py",
    )
    monkeypatch.setattr(approver, "REPO_ROOT", tmp_path / "repo")
    loaded_draft = approver.load_draft(
        approver.DraftInput(
            draft_path, hashlib.sha256(draft_path.read_bytes()).hexdigest()
        )
    )
    approved_profile = approver.build_approved_profile(
        loaded_draft, "2026-09-04T00:00:00Z"
    )

    document_helpers = load_file(
        "invoice519_document_helpers_for_bridge_tests",
        ROOT / "tests" / "test_publish_invoice519_dinva_document.py",
    )
    document_case = document_helpers.make_case(
        tmp_path / "document-sources", monkeypatch
    )
    document_builder = document_case["publisher"]
    draft_document_result = document_builder.publish_draft_document(
        document_case["ledger"],
        document_case["yauo"],
        document_case["canonical"],
        document_case["draft_output"],
    )
    draft_document_source = document_builder.BoundInput(
        draft_document_result.path, draft_document_result.sha256
    )
    reviewed_document = document_builder.load_draft_document(draft_document_source)
    approved_document_result = document_builder.publish_document(
        draft_document_source,
        document_case["output"],
        document_builder.authorization_for(reviewed_document),
    )
    approved_document = json.loads(
        approved_document_result.path.read_text(encoding="utf-8")
    )
    assert len(approved_document["terms"]["commercial_lines"]) == 8

    profile_path = tmp_path / "approved-profile.synthetic.json"
    profile_sha = write_json(profile_path, approved_profile)
    document_path = approved_document_result.path
    document_sha = approved_document_result.sha256
    renderer = load_file(
        "dinva_renderer_for_bridge_tests",
        ROOT / "scripts" / "render_dinva_classic_quote_invoice.py",
    )
    validator = load_file(
        "dinva_validator_for_bridge_tests",
        ROOT / "scripts" / "validate_dinva_classic_quote_invoice.py",
    )
    monkeypatch.setattr(renderer, "PROJECT_ROOT", tmp_path / "repo")
    output = tmp_path / "synthetic-v02-bridge.xlsx"
    renderer.render(
        profile_path=profile_path,
        expected_profile_sha256=profile_sha,
        document_path=document_path,
        expected_document_sha256=document_sha,
        output=output,
        allow_test_profile=False,
    )
    validator.validate_or_raise(
        output,
        approved_profile,
        profile_sha,
        approved_document,
        document_sha,
        allow_test_profile=False,
    )


def test_profile_approval_publisher_is_content_bound_and_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer, family, predecessor, logo_decision = build_profile_sources(
        tmp_path / "sources", monkeypatch
    )
    draft_profile = producer.extract_profile_v0_2(family, predecessor, logo_decision)
    draft_path = (
        tmp_path / "draft-case" / "dinva-classic-presentation-profile-v0.2-DRAFT.json"
    )
    producer.publish_draft_profile(draft_profile, draft_path)
    draft_sha = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    approver = load_file(
        "dinva_profile_v02_approver_publication_tests",
        ROOT
        / "scripts"
        / "publish_dinva_classic_presentation_profile_v0_2_approval.py",
    )
    monkeypatch.setattr(approver, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(approver, "utc_now", lambda: "2026-09-04T00:00:00Z")
    source = approver.DraftInput(draft_path, draft_sha)
    loaded = approver.load_draft(source)
    output = tmp_path / "approved-case" / approver.OUTPUT_FILENAME
    with pytest.raises(approver.ProfileV02ApprovalError, match="exact v0.2 profile"):
        approver.publish_profile_approval(source, output, "WRONG")
    result = approver.publish_profile_approval(
        source, output, approver.authorization_for(loaded)
    )
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["artifact_status"] == "IMMUTABLE_APPROVED_PROFILE"
    assert payload["approval_provenance"]["approved_contract_fingerprint"] == (
        draft_profile["presentation_contract_fingerprint"]
    )
    with pytest.raises(approver.ProfileV02ApprovalError, match="already exists"):
        approver.publish_profile_approval(
            source, output, approver.authorization_for(loaded)
        )
