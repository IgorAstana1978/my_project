from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook  # type: ignore[import-untyped]
from test_dinva_v0_5_print_successor import print_successor
from test_render_dinva_classic_quote_invoice import (
    ROOT,
    approved_document,
    canonical_file,
    load_file,
)

bridge: Any = load_file(
    "dinva_case_document_bridge_test",
    ROOT / "scripts/build_dinva_document_from_case.py",
)


def source_payload(tmp_path: Path, case_id: str, count: int) -> dict[str, Any]:
    example = approved_document()
    metadata = {key: copy.deepcopy(example[key]) for key in bridge.METADATA_KEYS}
    metadata.update(
        document_type="QUOTE",
        document_number=case_id,
        basis=case_id,
        object_name="Synthetic object",
    )
    metadata["sections"] = [
        {"label": "Synthetic case", "first_position": 1, "last_position": count}
    ]
    items = []
    for i in range(count):
        item = {
            key: copy.deepcopy(example["items"][0][key])
            for key in bridge.ITEM_KEYS
            if key != "item_id"
        }
        item.update(
            item_id=f"ITEM-{i+1}",
            quantity=i + 1,
            approved_unit_price_kzt=1000 * (i + 1),
            approved_line_total_kzt=1000 * (i + 1) ** 2,
        )
        items.append(item)
    total = sum(item["approved_line_total_kzt"] for item in items)
    metadata["vat"] = {
        "rate_percent": 0,
        "included": True,
        "approved_amount_kzt": 0,
        "approved_text": "НДС 0%",
    }
    metadata["amount_words"] = {"amount_kzt": total, "approved_text": "Synthetic sum"}
    evidence = tmp_path / "technical-source.txt"
    evidence.write_text("Synthetic authoritative technical input", encoding="utf-8")
    return {
        "schema_version": bridge.SOURCE_SCHEMA,
        "case_id": case_id,
        "metadata": metadata,
        "items": items,
        "approved_grand_total_kzt": total,
        "terms": {
            "payment": None,
            "delivery": "Самовывоз",
            "manufacturing_lead_time": "15 рабочих дней",
            "validity": None,
            "commercial_lines": ["15 рабочих дней"],
        },
        "source_bindings": [
            {
                "role": "PROJECT_TECHNICAL_SOURCE",
                "path": str(evidence),
                "sha256": bridge.digest(evidence.read_bytes()),
            }
        ],
    }


def inputs(tmp_path: Path, source: dict[str, Any]) -> tuple[Any, Any]:
    path = tmp_path / "case-source.json"
    canonical_file(path, source)
    case = bridge.Snapshot(path, path.read_bytes())
    core = bridge.prepare_core(
        source,
        {
            "role": "AUTHORITATIVE_DOCUMENT_TEXT_SOURCE",
            "path": str(path),
            "sha256": case.sha256,
        },
    )
    decision = {
        "schema_version": bridge.APPROVAL_SCHEMA,
        "case_id": source["case_id"],
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "approved_by": "Igor",
        "approved_at": "2026-09-30T08:00:00Z",
        "approval_id": "SYNTHETIC-APPROVAL",
        "approved_case_source_sha256": case.sha256,
        "approved_document_fingerprint": bridge.renderer.document_fingerprint(core),
        "technical_composition_approved": True,
        "prices_approved": True,
        "commercial_terms_approved": True,
        "rendering_authorized": True,
        "client_send_authorized": False,
    }
    ap = tmp_path / "case-approval.json"
    canonical_file(ap, decision)
    return case, bridge.Snapshot(ap, ap.read_bytes())


def token(plan: Any, output: Path) -> str:
    return (
        f"{bridge.PUBLICATION_ACTION}|ACTION=IMMUTABLE_DOCUMENT_PUBLICATION"
        f"|CASE_SHA256={plan.snapshots[0].sha256}"
        f"|APPROVAL_SHA256={plan.snapshots[1].sha256}"
        f"|DOCUMENT_FINGERPRINT={plan.document['document_fingerprint']}"
        f"|OUTPUT_PATH_SHA256={bridge.digest(str(output.resolve()).encode('utf-8'))}"
    )


@pytest.mark.parametrize("case_id,count", [("CASE-ALPHA", 3), ("CASE-BETA", 7)])
def test_multi_case_production_document(
    tmp_path: Path, case_id: str, count: int
) -> None:
    source = source_payload(tmp_path, case_id, count)
    case, approval = inputs(tmp_path, source)
    plan = bridge.preflight(case, approval)
    doc = plan.document
    # Sections must cover the arbitrary number of items, not a historical layout.
    assert doc["document_id"] == case_id
    assert len(doc["items"]) == count
    assert doc["terms"]["manufacturing_lead_time"] == "15 рабочих дней"
    assert doc["approval_provenance"]["client_send_authorized"] is False
    assert doc["approved_grand_total_kzt"] == source["approved_grand_total_kzt"]
    assert doc["items"][0]["apparatus"]["source_sha256"] == case.sha256
    assert plan.encoded == bridge.preflight(case, approval).encoded


@pytest.mark.parametrize("field", ["price", "term", "composition", "source"])
def test_substituted_case_rejected_even_with_new_caller_sha(
    tmp_path: Path, field: str
) -> None:
    source = source_payload(tmp_path, "CASE-ALPHA", 1)
    case, approval = inputs(tmp_path, source)
    if field == "price":
        source["items"][0]["approved_unit_price_kzt"] += 1
    elif field == "term":
        source["terms"]["manufacturing_lead_time"] = "10 рабочих дней"
    elif field == "composition":
        source["items"][0]["detailed_technical_composition"] = "Substitution"
    else:
        source["source_bindings"][0]["path"] = str(tmp_path / "replacement.txt")
    new_sha = canonical_file(case.path, source)
    changed = bridge.load(case.path, new_sha)
    with pytest.raises(bridge.BridgeError, match="approved Case source SHA"):
        bridge.preflight(changed, approval)


def test_upstream_drift_and_bound_input_sha(tmp_path: Path) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    with pytest.raises(bridge.BridgeError, match="input SHA mismatch"):
        bridge.load(case.path, "a" * 64)
    evidence = tmp_path / "technical-source.txt"
    evidence.write_text("replaced", encoding="utf-8")
    with pytest.raises(bridge.BridgeError, match="input SHA mismatch"):
        bridge.preflight(case, approval)


@pytest.mark.parametrize(
    "mutation", ["identity", "authority", "fingerprint", "send", "gate"]
)
def test_invalid_approval(tmp_path: Path, mutation: str) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    d = approval.payload()
    if mutation == "identity":
        d["case_id"] = "OTHER"
    elif mutation == "authority":
        d["authority"] = "EXTRACTOR"
    elif mutation == "fingerprint":
        d["approved_document_fingerprint"] = "b" * 64
    elif mutation == "send":
        d["client_send_authorized"] = True
    else:
        d["prices_approved"] = False
    canonical_file(approval.path, d)
    with pytest.raises(bridge.BridgeError):
        bridge.preflight(
            case, bridge.Snapshot(approval.path, approval.path.read_bytes())
        )


def test_bad_arithmetic_and_terms_are_not_repaired(tmp_path: Path) -> None:
    source = source_payload(tmp_path, "CASE", 1)
    source["items"][0]["approved_line_total_kzt"] = 999
    case, approval = inputs(tmp_path, source)
    with pytest.raises(bridge.BridgeError, match="arithmetic mismatch"):
        bridge.preflight(case, approval)
    source["items"][0]["approved_line_total_kzt"] = 1000
    source["terms"]["commercial_lines"] = ["После оплаты — 15 рабочих дней"]
    with pytest.raises(bridge.BridgeError, match="verbatim once"):
        inputs(tmp_path, source)


def test_duplicate_keys_and_non_finite_json_fail_closed(tmp_path: Path) -> None:
    for raw in (b'{"case_id":"A","case_id":"B"}', b'{"price":NaN}'):
        with pytest.raises(bridge.BridgeError):
            bridge.Snapshot(tmp_path / "bad.json", raw).payload()


def test_missing_commercial_data_cannot_be_filled_from_a_historical_case(
    tmp_path: Path,
) -> None:
    source = source_payload(tmp_path, "CASE", 1)
    source["metadata"]["payer"] = None
    with pytest.raises(bridge.BridgeError, match="missing payer"):
        inputs(tmp_path, source)


def test_cli_preflight_is_read_only_and_publish_is_separate(
    tmp_path: Path, capsys: Any
) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    output = tmp_path / "document.json"
    args = [
        "--case-source",
        str(case.path),
        "--case-source-sha256",
        case.sha256,
        "--case-approval",
        str(approval.path),
        "--case-approval-sha256",
        approval.sha256,
        "--output",
        str(output),
    ]
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert bridge.main(args) == 0
    assert "PREFLIGHT_PASS" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert bridge.main(args + ["--authorization", "not permitted"]) == 1
    plan = bridge.preflight(case, approval)
    assert (
        bridge.main(args + ["--publish", "--authorization", token(plan, output)]) == 0
    )
    assert output.read_bytes() == plan.encoded
    with pytest.raises(bridge.BridgeError, match="overwrite"):
        bridge.publish(plan, output, token(plan, output))


def test_wrong_publication_subject_and_source_toctou(tmp_path: Path) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    plan = bridge.preflight(case, approval)
    output = tmp_path / "document.json"
    with pytest.raises(bridge.BridgeError, match="exact Human"):
        bridge.publish(plan, output, token(plan, tmp_path / "other.json"))
    case.path.write_text("{}", encoding="utf-8")
    with pytest.raises(bridge.BridgeError, match="source changed"):
        bridge.publish(plan, output, token(plan, output))
    assert not output.exists()


def test_post_link_source_drift_rolls_back_only_own_output(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    plan = bridge.preflight(case, approval)
    output = tmp_path / "document.json"
    real_link = bridge.os.link

    def drifting_link(src: Path, dest: Path) -> None:
        real_link(src, dest)
        approval.path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(bridge.os, "link", drifting_link)
    with pytest.raises(bridge.BridgeError, match="source changed"):
        bridge.publish(plan, output, token(plan, output))
    assert not output.exists()
    assert not list(tmp_path.glob(".dinva-case-*"))


def test_mutated_in_memory_plan_cannot_bypass_frozen_approval(tmp_path: Path) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    plan = bridge.preflight(case, approval)
    output = tmp_path / "document.json"
    authorization = token(plan, output)
    plan.document["items"][0]["approved_unit_price_kzt"] = 9999
    with pytest.raises(bridge.BridgeError, match="plan was modified"):
        bridge.publish(plan, output, authorization)
    assert not output.exists()


def test_existing_output_race_preserves_foreign_file(
    tmp_path: Path, monkeypatch: Any
) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE", 1))
    plan = bridge.preflight(case, approval)
    output = tmp_path / "document.json"
    real_link = bridge.os.link

    def racing_link(src: Path, dest: Path) -> None:
        dest.write_bytes(b"foreign")
        real_link(src, dest)

    monkeypatch.setattr(bridge.os, "link", racing_link)
    with pytest.raises(FileExistsError):
        bridge.publish(plan, output, token(plan, output))
    assert output.read_bytes() == b"foreign"
    assert not list(tmp_path.glob(".dinva-case-*"))


@pytest.mark.parametrize("number_mode", ["assigned", "null", "omitted"])
def test_produced_document_renders_and_validates_with_v05(
    tmp_path: Path, monkeypatch: Any, number_mode: str
) -> None:
    monkeypatch.setenv("DINVA_RENDERER_TEST_MODE", "1")
    _, profile, _ = print_successor(tmp_path, monkeypatch)
    source = source_payload(tmp_path, "CASE-GAMMA", 3)
    if number_mode == "null":
        source["metadata"]["document_number"] = None
    elif number_mode == "omitted":
        source["metadata"].pop("document_number")
    source["metadata"]["sections"] = [
        {"label": "Synthetic case", "first_position": 1, "last_position": 3}
    ]
    case, approval = inputs(tmp_path, source)
    plan = bridge.preflight(case, approval)
    document_path = tmp_path / "document.json"
    bridge.publish(plan, document_path, token(plan, document_path))
    profile_path = tmp_path / "profile-v05.json"
    profile_sha = canonical_file(profile_path, profile)
    output = tmp_path / "case-v05.xlsx"
    bridge.renderer.render(
        profile_path=profile_path,
        expected_profile_sha256=profile_sha,
        document_path=document_path,
        expected_document_sha256=bridge.digest(plan.encoded),
        output=output,
        allow_test_profile=True,
    )
    bridge.validator.validate_or_raise(
        output,
        profile,
        profile_sha,
        plan.document,
        bridge.digest(plan.encoded),
        allow_test_profile=True,
    )
    assert output.exists()
    book = load_workbook(output)
    try:
        title = book.worksheets[0]["C9"].value
        assert title.startswith("Коммерческое предложение")
        if number_mode != "assigned":
            assert (
                "№" not in title and "CASE-GAMMA" not in title and "None" not in title
            )
            assert plan.document["document_number"] is None
    finally:
        book.close()


def test_governed_defaults_and_case_override(tmp_path: Path, monkeypatch: Any) -> None:
    source = source_payload(tmp_path, "CASE-DEFAULT", 1)
    for key in ("document_number", "document_date", "signatures"):
        source["metadata"].pop(key)
    source["terms"].pop("delivery")
    monkeypatch.setattr(bridge, "formation_date", lambda: "2030-02-03")
    plan = bridge.preflight(*inputs(tmp_path, source))
    assert plan.document["document_number"] is None
    assert plan.document["document_date"] == "2030-02-03"
    assert plan.document["signatures"] == bridge.DEFAULT_SIGNATURES
    assert plan.document["terms"]["delivery"] == "EXW г. Астана"
    lines = plan.document["terms"]["commercial_lines"]
    assert [line["text"] for line in lines] == ["15 рабочих дней", "EXW г. Астана"]
    assert lines[1]["source_sha256"] == bridge.defaults_source().sha256
    assert lines[1]["source_locator"] == "DEFAULT_DELIVERY"
    source["terms"]["delivery"] = "DDP Алматы"
    source["metadata"]["signatures"] = source_payload(tmp_path, "CASE", 1)["metadata"][
        "signatures"
    ]
    source["metadata"]["document_date"] = "2030-02-04"
    override = bridge.preflight(*inputs(tmp_path, source)).document
    assert override["terms"]["delivery"] == "DDP Алматы"
    assert override["signatures"]["director_name"] == "Тестовый Директор"
    assert override["document_date"] == "2030-02-04"


def test_unassigned_is_quote_only_and_unknown_fields_stay_closed(
    tmp_path: Path,
) -> None:
    plan = bridge.preflight(*inputs(tmp_path, source_payload(tmp_path, "CASE", 1)))
    for kind in ("INVOICE", "QUOTE_INVOICE"):
        doc = copy.deepcopy(plan.document)
        doc.update(document_type=kind, document_number=None)
        fp = bridge.renderer.document_fingerprint(doc)
        doc["document_fingerprint"] = fp
        doc["approval_provenance"]["approved_document_fingerprint"] = fp
        with pytest.raises(bridge.renderer.RendererError):
            bridge.renderer.validate_document(doc, allow_test_profile=False)
        with pytest.raises(bridge.validator.ValidationError):
            bridge.validator.validate_document_contract(doc, allow_test_profile=False)
    doc = copy.deepcopy(plan.document)
    doc["unrelated_new_field"] = True
    with pytest.raises(bridge.renderer.RendererError, match="fields mismatch"):
        bridge.renderer.validate_document(doc, allow_test_profile=False)
    schema = json.loads(
        (ROOT / "schemas/dinva_quote_invoice_document_v0_2.schema.json").read_text()
    )
    assert "document_number" not in schema["required"]
    assert schema["properties"]["document_number"]["type"] == ["string", "null"]
    assert schema["allOf"][0]["then"]["required"] == ["document_number"]


def test_memory_preview_reaches_publication_boundary_without_writes(
    tmp_path: Path,
) -> None:
    case, approval = inputs(tmp_path, source_payload(tmp_path, "CASE-PREVIEW", 1))
    case.path.unlink()
    approval.path.unlink()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    plan = bridge.preflight(case, approval, preview=True)
    assert not plan.materialized
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    output = tmp_path / "document.json"
    with pytest.raises(bridge.BridgeError, match="materialization requires"):
        bridge.publish(plan, output, token(plan, output))
    assert not output.exists()
