"""Schematic pre-HA1 handoff through native validators and TEST-only sources."""

import json
from pathlib import Path
from typing import Any

import cabinet_sizing as sizing  # type: ignore[import-not-found]
import cabinet_sizing_module_accounting as modules  # type: ignore[import-not-found]
import prepare_schematic_ha1_review as review  # type: ignore[import-not-found]
import pytest
from module_accounting_fixtures import NATIVE_BUILD
from test_cabinet_sizing import provision_auto
from test_cabinet_sizing_catalogue import inject, quote_request, record
from test_cabinet_sizing_mixed import make_installed, module_source, pin_fact
from test_future_case_xlsx_flow import (
    cad,
    extraction,
    governed,
    handoff,
    schematic_review,
)
from test_future_case_xlsx_flow import (
    schematic_handoff as schematic_handoff,
)
from test_future_case_xlsx_flow import (
    telegram_handoff as telegram_handoff,
)
from test_governed_schematic_extraction import CadPage
from test_versioned_metal_source import synthetic_sources as synthetic_sources

builder = review.builder


def write_json(path: Path, data: Any) -> dict[str, str]:
    raw = builder.canonical_json_bytes(data)
    path.write_bytes(raw)
    return {"path": str(path), "sha256": builder.sha256_bytes(raw)}


@pytest.fixture
def prepared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schematic_handoff: Any,
    synthetic_sources: Any,
) -> Any:
    args = handoff.preflight(**schematic_handoff)
    reader = type(
        "Reader",
        (),
        {
            "is_encrypted": False,
            "pages": [
                CadPage(
                    [
                        ("Принципиальная схема группового щита", 120, 60),
                        ("НЩР (ЩРн-36)", 205, 45),
                        ("QF0 ВН-32 3P 25А", 100, 650),
                        ("QF1 АВДТ32 2P C16/30мА", 180, 530),
                    ]
                )
            ],
        },
    )()
    monkeypatch.setattr(cad.core, "PdfReader", lambda *_a, **_k: reader)
    monkeypatch.setattr(schematic_review, "PdfReader", lambda *_a, **_k: reader)
    result = extraction.run_versioned_case_extraction(**args)
    assert result.status == "PASS", result.red_flags
    case_id, root = args["case_id"], args["canonical_root"]
    directory = result.output_dir
    version_sha = builder.sha256_bytes(
        (directory / "version-binding.json").read_bytes()
    )
    source = builder.load_snapshot(
        builder.resolve_case_paths(
            case_id, canonical_root=root, extraction_version="V001"
        ),
        schematic_binding_sha256=version_sha,
    )
    item = source.draft["items"][0]
    item_id = item["item_id"]
    decisions = dict(
        schema_version=builder.DECISIONS_INPUT_SCHEMA,
        case_id=case_id,
        draft_id=source.draft["draft_id"],
        input_sha256={
            "source_bundle_manifest": source.hashes[builder.MANIFEST_NAME],
            "preliminary_composition_draft": source.hashes[builder.DRAFT_NAME],
            "igor_review_card": source.hashes[builder.REVIEW_NAME],
        },
        supply_boundary="TEST cabinet and full internal wiring; field cables excluded",
        items=[
            dict(
                item_id=item_id,
                product_name=item["normalized_designation"],
                quantity=2,
                manufacturer="TEST",
                acknowledged_red_flags=item["red_flags"],
                cabinet=dict(acknowledged_red_flags=item["cabinet_guess"]["red_flags"]),
                component_groups=[
                    dict(
                        component_ids=[c["component_id"]],
                        total_quantity=1,
                        final_description=f"TEST {c['component_label_guess']}",
                        install_type=kind,
                        substitution=(
                            dict(
                                original=c["component_label_guess"],
                                final=f"TEST {c['component_label_guess']}",
                                reason="TEST proposed substitution",
                            )
                            if kind == "load_switch_3p"
                            else None
                        ),
                        acknowledged_red_flags=c["red_flags"],
                    )
                    for c, kind in zip(
                        item["components"], ["load_switch_3p", "diff_1p_n"], strict=True
                    )
                ],
            )
        ],
        source_quality_acknowledgements=[
            dict(source_path=f"red_flags[{i}]", warning=warning, reason="TEST review")
            for i, warning in enumerate(source.draft["red_flags"])
        ],
        technical_assumption_resolutions=[
            dict(
                assumption,
                resolution="resolved_by_explicit_composition_decisions",
                reason="TEST complete inventory and scope review",
            )
            for assumption in builder.collect_assumptions(source.draft)
        ],
    )
    decision_path = tmp_path / "composition-decisions.json"
    decision_ref = write_json(decision_path, decisions)
    state = builder.apply_batch_decisions(
        source,
        builder.load_decisions_input(decision_path),
        case_id=case_id,
        automatic_cabinet=True,
    )
    req, _ = provision_auto(tmp_path, monkeypatch, case_id, state.items)
    del req["catalogue"]
    req = quote_request(req, synthetic_sources, {item_id: "TEST-CAB"})
    fact_path = Path(req["source_facts"][item_id]["path"])
    fact = json.loads(fact_path.read_bytes())
    fact.update(dimensions_status="ABSENT", dimensions_mm=None, installation=None)
    req["source_facts"][item_id] = pin_fact(fact_path, fact, monkeypatch)
    inject(monkeypatch, [record("TEST-CAB")])
    installed, _ = make_installed(tmp_path, monkeypatch, state.items[0], req)
    _, ledger_binding, _ = module_source(tmp_path, monkeypatch, state.items[0], req)
    monkeypatch.setattr(modules, "build_sizing_report", NATIVE_BUILD)
    review_input = dict(
        schema_version=review.INPUT_SCHEMA,
        case_id=case_id,
        extraction_version="V001",
        version_binding_sha256=version_sha,
        igor_decision_locator="TEST decision record 001",
        composition_decisions=decision_ref,
        sizing_request=write_json(tmp_path / "sizing.json", req),
        module_evidence=ledger_binding,
        boards={
            item_id: dict(
                qf_products={
                    i["component_id"]: i["product_id"]
                    for i in installed["instances"]
                    if i["component_id"] is not None
                },
                accessories={
                    i["id"]: i["product_id"]
                    for i in installed["instances"]
                    if i["component_id"] is None
                },
                connections=dict(installed["raw_sources"][0], locator="TEST wiring"),
                technical_requirements=dict(
                    installed["raw_sources"][0], locator="TEST electrical requirements"
                ),
            )
        },
    )
    return root, directory, review_input, decisions


def test_schematic_packet_is_review_only(
    prepared: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, directory, data, _ = prepared
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    path = tmp_path / "review.json"
    ref = write_json(path, data)
    native = review.prepare_review
    monkeypatch.setattr(
        review, "prepare_review", lambda *args: native(*args, canonical_root=root)
    )
    argv = [
        "--case-id",
        data["case_id"],
        "--extraction-version",
        "V001",
        "--review-json",
        str(path),
        "--review-sha256",
        ref["sha256"],
    ]
    assert review.main(argv) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["schema_version"] == review.OUTPUT_SCHEMA
    assert packet["status"] == "HUMAN_REVIEW_REQUIRED"
    assert packet["decision_provenance_status"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert packet["electrical_applicability_status"] == "NOT_VERIFIED"
    substitution = packet["composition_decisions"]["expanded_component_decisions"][0][
        "substitution"
    ]
    assert substitution["reason"] == "TEST proposed substitution"
    assert "explicit_igor_decision" not in substitution
    assert (
        packet["composition_confirmed"] is packet["human_approval_1_granted"] is False
    )
    assert packet["extraction_sha256"] == {
        name: builder.sha256_bytes(raw) for name, raw in before.items()
    }
    draft = json.loads(before[builder.DRAFT_NAME])
    assert packet["source_facts"]["items"] == draft["items"]
    assert packet["source_facts"]["qf_count"] == 2
    assert packet["candidate_items"][0]["product_name"] == "НЩР"
    assert packet["candidate_items"][0]["quantity"] == 2
    assert len(packet["cabinet_sizing"]["module_ledger"]["items"][0]["instances"]) == 5
    output = tmp_path / "review-packet.json"
    write_json(output, packet)
    assert builder.default_confirmed_validator(output).status == "FAIL"
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
    argv[-1] = "0" * 64
    assert review.main(argv) == 1
    capture = capsys.readouterr()
    assert not capture.out and "SHA-256 mismatch" in capture.err


@pytest.mark.parametrize(
    "fault,match",
    [
        ("source", "project PDF cannot be read"),
        ("quantity", "missing required fields: quantity"),
        ("mapping", "QF product mapping mismatch"),
        ("accessory", "installed accessory coverage mismatch"),
        ("ledger", "missing required fields: module_evidence"),
        ("sha", "versioned input SHA-256 mismatch"),
        ("approval", "missing required fields: igor_decision_locator"),
        ("connections", "unbound connections source"),
        ("unadmitted_ledger", "HOLD_UNAPPROVED_REUSABLE_SOURCE:module_accounting"),
    ],
)
def test_schematic_packet_holds_on_incomplete_or_changed_inputs(
    prepared: Any,
    tmp_path: Path,
    fault: str,
    match: str,
) -> None:
    root, directory, data, decisions = prepared
    board = next(iter(data["boards"].values()))
    if fault == "source":
        intake = json.loads((directory / "governed-intake.json").read_bytes())
        Path(intake["project_pdf_path"]).unlink()
    elif fault == "quantity":
        del decisions["items"][0]["quantity"]
        data["composition_decisions"] = write_json(
            Path(data["composition_decisions"]["path"]), decisions
        )
    elif fault == "mapping":
        board["qf_products"].popitem()
    elif fault == "accessory":
        board["accessories"].popitem()
    elif fault == "ledger":
        del data["module_evidence"]
    elif fault == "sha":
        path = directory / builder.REVIEW_NAME
        path.write_bytes(path.read_bytes() + b"\n")
    elif fault == "approval":
        del data["igor_decision_locator"]
    elif fault == "connections":
        board["connections"]["sha256"] = "0" * 64
    elif fault == "unadmitted_ledger":
        old = json.loads(Path(data["module_evidence"]["path"]).read_bytes())
        data["module_evidence"] = write_json(tmp_path / "unadmitted.json", old)
    path = tmp_path / "review.json"
    ref = write_json(path, data)
    with pytest.raises((builder.WorkflowError, sizing.SizingHold), match=match):
        review.prepare_review(
            data["case_id"], "V001", path, ref["sha256"], canonical_root=root
        )
    assert not (directory / "confirmed").exists()


@pytest.mark.parametrize("version", [None, "V001"])
def test_schematic_hold_cannot_be_bypassed_in_confirmed_builder(
    prepared: Any,
    version: str | None,
) -> None:
    root, directory, data, _ = prepared
    result = builder.run_builder(
        case_id=data["case_id"],
        confirmation_id="TEST",
        approval_channel="TEST",
        decisions_json=Path(data["composition_decisions"]["path"]),
        extraction_version=version,
        canonical_root=root,
        input_fn=lambda _: pytest.fail("schematic HOLD must precede approval"),
    )
    assert governed.SCHEMATIC_REVIEW_HOLD in result.red_flags[0]
    assert not result.output_created
    assert not (directory.parent / "confirmed").exists()
    assert not (directory / "confirmed").exists()
