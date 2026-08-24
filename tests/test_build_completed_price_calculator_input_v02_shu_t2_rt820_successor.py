import ast
import copy
import importlib.util
import json
import py_compile
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "build_completed_price_calculator_input_v02_shu_t2_rt820_successor.py"
)


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("shu_t2_rt820_successor_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_module())

SHU_T1_PROVENANCE_IDS = (
    "COMP-006",
    "COMP-056",
    "COMP-106",
    "COMP-153",
    "COMP-009",
    "COMP-059",
    "COMP-109",
    "COMP-156",
)
TARGET_IDS = tuple(
    evidence
    for _section, _technical, _pricing, relay, sensor in builder.POSITION_SCOPE
    for evidence in (relay, sensor)
)


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return cast(str, builder.sha256_bytes(path.read_bytes()))


def evidence_record(evidence_id: str, position_id: str) -> dict[str, Any]:
    return {
        "component_evidence_id": evidence_id,
        "position_id": position_id,
        "section_id": position_id,
        "label": f"evidence {evidence_id}",
        "provenance": {"source": "synthetic"},
    }


def applied_value() -> dict[str, Any]:
    target_records = [
        evidence_record(relay, technical)
        for _section, technical, _pricing, relay, _sensor in builder.POSITION_SCOPE
    ] + [
        evidence_record(sensor, technical)
        for _section, technical, _pricing, _relay, sensor in builder.POSITION_SCOPE
    ]
    return {
        "schema_version": builder.APPLIED_SCHEMA,
        "project_id": builder.PROJECT_ID,
        "application_status": "APPLIED",
        "authority": builder.AUTHORITY,
        "source_lineage": {
            "canonical_replay_schema_version": builder.CANONICAL_SCHEMA,
            "canonical_replay_sha256": builder.CANONICAL_SHA256,
        },
        "canonical_component_evidence_records": target_records,
    }


def base_row(number: int) -> dict[str, Any]:
    row_id = f"ROW-DRAFT-{number:04d}"
    if 20 <= number <= 27:
        group_id = builder.TARGET_GROUP_ID
        product = "ШУ-Т2"
        code = "EKF-VA47-29-2P" if number <= 23 else "EKF-AD12"
        install = "modular_2p" if number <= 23 else "diff_1p_n"
        evidence: list[str] = [f"EXISTING-{number}"]
    elif 110 <= number <= 112:
        group_id = builder.SHU_T1_GROUP_ID
        product = "ШУ-Т1"
        code = {
            110: "EKF-RT-820",
            111: "EKF-AD12-1P-N-C16-30MA-4P5KA",
            112: "EKF-VA47-29-2P",
        }[number]
        install = {
            110: "temperature_relay_din_2mod",
            111: "diff_1p_n",
            112: "modular_2p",
        }[number]
        evidence = (
            list(SHU_T1_PROVENANCE_IDS) if number == 110 else [f"SHU-T1-{number}"]
        )
    else:
        group_id = "CABINET-GROUP-001"
        product = "OTHER"
        code = "BASE-COMPONENT"
        install = "base_install"
        evidence = [f"BASE-{number}"]
    return {
        "row_id": row_id,
        "cabinet_group_id": group_id,
        "calculator_values": {
            "product_name": product,
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": code,
            "component_qty": 1,
            "install_type": install,
        },
        "source_quantity": {"quantity_per_cabinet": 1},
        "source_component_evidence_ids": evidence,
        "approved_signature": {"synthetic": True},
        "mapping_status": "APPROVED_HUMAN_DECISIONS_APPLIED",
        "component_label": code,
    }


def parent_value(applied_sha: str) -> dict[str, Any]:
    groups = [
        {
            "cabinet_group_id": f"CABINET-GROUP-{number:03d}",
            "source_cabinet_template": f"GROUP-{number}",
            "product_name": f"GROUP-{number}",
            "cabinet_code": "CAB-KRN-12",
            "cabinet_label": "Synthetic cabinet",
            "consumables_factor": 1.2,
            "mapping_status": "APPROVED_HUMAN_DECISIONS_APPLIED",
            "row_draft_ids": [],
        }
        for number in range(1, 16)
    ]
    groups[0]["row_draft_ids"] = [
        f"ROW-DRAFT-{number:04d}"
        for number in range(1, 113)
        if not 20 <= number <= 27 and not 110 <= number <= 112
    ]
    groups[2].update(
        {
            "source_cabinet_template": "ШУ-Т2",
            "product_name": "ШУ-Т2",
            "row_draft_ids": [f"ROW-DRAFT-{number:04d}" for number in range(20, 28)],
        }
    )
    groups[14].update(
        {
            "source_cabinet_template": "ЩРН-12",
            "product_name": "ШУ-Т1",
            "row_draft_ids": list(builder.SHU_T1_ROW_IDS),
        }
    )
    return {
        "schema_version": builder.PARENT_SCHEMA,
        "draft_type": "price_calculator_input_draft",
        "source": {
            "project_id": builder.PROJECT_ID,
            "applied_bundle_sha256": applied_sha,
            "preserved_parent_source": True,
        },
        "cabinet_groups": groups,
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_row_drafts",
            "delimiter": ";",
            "row_drafts": [base_row(number) for number in range(1, 113)],
        },
        "coverage": {
            "installed_component_count": 124,
            "direct_installed_component_count": 110,
            "aggregate_member_count": 14,
            "aggregate_decision_count": 2,
            "pricing_row_draft_count": 112,
            "cabinet_group_count": 15,
        },
        "safety": {
            "price_approved_by_igor": False,
            "production_authorized": False,
            "pricing_started": False,
            "downstream_started": False,
            "sending_authorized": False,
            "commercial_csv_authorized": False,
            "price_calculation_executed": False,
        },
        "completion": {
            "status": builder.PARENT_STATUS,
            "authorization_claim_is_not_human_approval": True,
            "scope": {
                "component_groups": 34,
                "rows": "112/112",
                "cabinet_groups": "15/15",
                "duplicate_component_membership": 0,
                "duplicate_cabinet_membership": 0,
                "scope_expansion": False,
            },
        },
    }


def decision_value(
    parent_path: Path, parent_sha: str, applied_sha: str
) -> dict[str, Any]:
    target_ids = list(TARGET_IDS)
    return {
        "schema_version": builder.DECISION_SCHEMA,
        "artifact_type": "IMMUTABLE_HUMAN_DECISION_CAPTURE",
        "project_id": builder.PROJECT_ID,
        "decision_id": builder.DECISION_ID,
        "status": builder.DECISION_STATUS,
        "authority": builder.AUTHORITY,
        "application_status": builder.APPLICATION_STATUS,
        "input_bindings": [
            {
                "role": "technical_successor",
                "path": str(parent_path),
                "expected_sha256": parent_sha,
                "actual_sha256": parent_sha,
                "schema_version": builder.PARENT_SCHEMA,
                "status": builder.PARENT_STATUS,
            }
        ],
        "lineage_anchors": {
            "applied_component_lineage_sha256": applied_sha,
            "canonical_position_lineage_sha256": builder.CANONICAL_SHA256,
        },
        "exact_scope": {
            "product": "ШУ-Т2",
            "cabinet_group_id": builder.TARGET_GROUP_ID,
            "cabinet_code": "CAB-KRN-12",
            "positions": [
                {
                    "section": section,
                    "technical_position_id": technical,
                    "pricing_position_id": pricing,
                    "relay_evidence_id": relay,
                    "sensor_evidence_id": sensor,
                    "physical_multiplicity": 1,
                }
                for section, technical, pricing, relay, sensor in builder.POSITION_SCOPE
            ],
            "source_evidence_row_count": 8,
            "future_component_row_count": 4,
        },
        "rt820_contract": {
            "component_code": "EKF-RT-820",
            "component_qty_per_physical_cabinet": 1,
            "install_type": "temperature_relay_din_2mod",
            "module_width": 2,
            "source_range": "КРН!A19:C19",
            "source_label": "Терморегулятор RT-820",
            "material_kzt": 15000,
            "work_kzt": 900,
            "generic_work_432_prohibited": True,
            "family_fallback_prohibited": True,
            "fuzzy_fallback_prohibited": True,
            "similar_relay_fallback_prohibited": True,
        },
        "bundle_semantics": {
            "relay_and_sensor_form_one_indivisible_complete_set": True,
            "tst05_provenance_only": True,
            "separate_tst05_component_row": False,
            "separate_tst05_material_charge": False,
            "separate_tst05_work_charge": False,
            "separate_tst05_pricing_row": False,
            "double_counting_prohibited": True,
        },
        "supersession": {
            "prior_decision_id": "HDA-019-H19-3",
            "superseded_field": (
                "$.supply_boundary.rt007s_authority_proof.rule_payload."
                "forbidden_transfer_designation"
            ),
            "prior_value": "ШУ-Т2",
            "applies_only_to_evidence_ids": target_ids,
            "outside_cabinet_exclusion_count_must_be_derived": True,
            "outside_cabinet_exclusion_count_override_prohibited": True,
            "all_other_supply_boundaries_unchanged": True,
            "all_other_human_decisions_unchanged": True,
            "shu_t1_unchanged": True,
        },
        "shu_t1_integrity": {
            "cabinet_group_id": builder.SHU_T1_GROUP_ID,
            "technical_row_ids": list(builder.SHU_T1_ROW_IDS),
            "byte_and_semantic_change_authorized": False,
        },
        "safety": {
            "human_decision_recorded": True,
            "decision_applied_to_technical_successor": False,
            "decision_applied_to_pricing_profile": False,
            "calculator_run_authorized": False,
            "price_calculated": False,
            "price_approved": False,
            "price_floor_authorized": False,
            "quote_or_invoice_authorized": False,
            "client_send_authorized": False,
            "procurement_authorized": False,
            "production_authorized": False,
            "downstream_authorized": False,
            "scope_expansion": False,
        },
        "publication_control": {
            "immutable": True,
            "no_overwrite": True,
            "atomic_publication": True,
            "input_toctou_recheck_required": True,
            "final_strict_json_reread_required": True,
            "authorization_token_required": True,
        },
    }


def install_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    applied: dict[str, Any] | None = None,
    parent_mutator: Any = None,
    decision_mutator: Any = None,
) -> tuple[Any, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = builder.InputPaths(
        tmp_path / "parent.json",
        tmp_path / "decision.json",
        tmp_path / "applied.json",
    )
    applied_data = copy.deepcopy(applied if applied is not None else applied_value())
    applied_sha = write_json(paths.applied_component_lineage, applied_data)
    parent_data = parent_value(applied_sha)
    if parent_mutator is not None:
        parent_mutator(parent_data)
    parent_sha = write_json(paths.parent_completed_input, parent_data)
    decision_data = decision_value(
        paths.parent_completed_input, parent_sha, applied_sha
    )
    if decision_mutator is not None:
        decision_mutator(decision_data)
    decision_sha = write_json(paths.shu_t2_rt820_decision, decision_data)
    shas = builder.ExpectedShas(parent_sha, decision_sha, applied_sha)
    monkeypatch.setattr(builder, "PARENT_COMPLETED_INPUT", paths.parent_completed_input)
    monkeypatch.setattr(builder, "PARENT_COMPLETED_INPUT_SHA256", parent_sha)
    monkeypatch.setattr(builder, "SHU_T2_RT820_DECISION", paths.shu_t2_rt820_decision)
    monkeypatch.setattr(builder, "SHU_T2_RT820_DECISION_SHA256", decision_sha)
    monkeypatch.setattr(
        builder, "APPLIED_COMPONENT_LINEAGE", paths.applied_component_lineage
    )
    monkeypatch.setattr(builder, "APPLIED_COMPONENT_LINEAGE_SHA256", applied_sha)
    return paths, shas, parent_data, decision_data, applied_data


def cli_arguments(paths: Any, shas: Any, output: Path) -> list[str]:
    return [
        "--parent-completed-input",
        str(paths.parent_completed_input),
        "--parent-completed-input-sha256",
        shas.parent_completed_input,
        "--shu-t2-rt820-decision",
        str(paths.shu_t2_rt820_decision),
        "--shu-t2-rt820-decision-sha256",
        shas.shu_t2_rt820_decision,
        "--applied-component-lineage",
        str(paths.applied_component_lineage),
        "--applied-component-lineage-sha256",
        shas.applied_component_lineage,
        "--output",
        str(output),
        "--authorization",
        builder.PUBLICATION_AUTHORIZATION,
    ]


def test_py_compile_python313_grammar_and_exact_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for source in (SCRIPT, Path(__file__)):
        py_compile.compile(
            str(source), cfile=str(tmp_path / f"{source.stem}.pyc"), doraise=True
        )
    source_text = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source_text, filename=str(SCRIPT), feature_version=(3, 13))
    parser = builder.build_parser()
    long_options = {
        option
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--")
    }
    expected = {
        "--help",
        "--parent-completed-input",
        "--parent-completed-input-sha256",
        "--shu-t2-rt820-decision",
        "--shu-t2-rt820-decision-sha256",
        "--applied-component-lineage",
        "--applied-component-lineage-sha256",
        "--output",
        "--authorization",
    }
    assert long_options == expected
    required = {action.dest for action in parser._actions if action.required}
    assert required == {
        "parent_completed_input",
        "parent_completed_input_sha256",
        "shu_t2_rt820_decision",
        "shu_t2_rt820_decision_sha256",
        "applied_component_lineage",
        "applied_component_lineage_sha256",
        "output",
        "authorization",
    }
    with pytest.raises(SystemExit) as missing:
        builder.parse_args([])
    assert missing.value.code == 2
    with pytest.raises(SystemExit) as raised:
        builder.parse_args(["--help"])
    assert raised.value.code == 0
    assert "--canonical-component-lineage" not in capsys.readouterr().out


def test_positive_build_publication_and_read_only_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, parent, _decision, _applied = install_values(tmp_path, monkeypatch)
    loaded = builder.load_and_validate_inputs(paths, shas)
    successor = builder.build_successor_payload(loaded)
    assert (
        successor["calculator_input_format"]["row_drafts"][:112]
        == parent["calculator_input_format"]["row_drafts"]
    )
    assert len(successor["calculator_input_format"]["row_drafts"]) == 116
    metadata = successor["source"]["shu_t2_rt820_technical_successor"]
    projection = metadata["technical_projection"]
    assert projection["row_count"] == 4
    assert projection["evidence_count"] == 8
    assert projection["outside_cabinet_membership_asserted"] is False
    assert projection["outside_cabinet_count_transition_asserted"] is False
    forbidden_claims = {
        "before_count",
        "after_count",
        "remaining_exclusion_records",
        "remaining_evidence_ids",
        "authoritative_count_json_path",
    }
    assert forbidden_claims.isdisjoint(metadata)
    assert forbidden_claims.isdisjoint(projection)
    report = builder.validate_real_inputs_read_only(paths, shas)
    assert report["status"] == "PASS"
    assert report["publication_called"] is False
    assert report["validated_evidence_count"] == 8
    assert report["outside_cabinet_membership_asserted"] is False
    assert report["outside_cabinet_count_transition_asserted"] is False
    output = tmp_path / "output" / builder.OUTPUT_FILENAME
    result = builder.publish_successor(paths, shas, output)
    assert result.encoded == output.read_bytes()
    assert result.sha256 == builder.sha256_bytes(output.read_bytes())
    assert result.size == len(output.read_bytes())
    published, raw = builder.load_json(output, "published test successor")
    assert raw == builder.serialize(published)
    builder.validate_successor_payload(published, loaded)
    assert list(output.parent.iterdir()) == [output]


def test_authorization_rejected_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    called = False

    def forbidden(*_args: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(builder, "publish_successor", forbidden)
    args = cli_arguments(paths, shas, tmp_path / "output" / builder.OUTPUT_FILENAME)
    args[-1] = "CODE_ONLY"
    with pytest.raises(builder.ContractError, match="publication authorization"):
        builder.main(args)
    assert called is False


@pytest.mark.parametrize(
    "role",
    [
        "parent_completed_input",
        "shu_t2_rt820_decision",
        "applied_component_lineage",
    ],
)
def test_wrong_sha_and_path_fail_closed(
    role: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    with pytest.raises(builder.ContractError, match="expected SHA mismatch"):
        builder.load_and_validate_inputs(paths, replace(shas, **{role: "0" * 64}))
    wrong_paths = replace(paths, **{role: tmp_path / f"wrong-{role}.json"})
    with pytest.raises(builder.ContractError, match="path mismatch"):
        builder.load_and_validate_inputs(wrong_paths, shas)


@pytest.mark.parametrize("bad_sha", ["A" * 64, "0" * 63, "x" * 64])
def test_sha_format_rejected(
    bad_sha: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    with pytest.raises(builder.ContractError, match="lowercase hexadecimal"):
        builder.load_and_validate_inputs(
            paths, replace(shas, parent_completed_input=bad_sha)
        )


def test_duplicate_json_key_rejected(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"project_id":"2024/086","project_id":"X"}', encoding="utf-8")
    with pytest.raises(builder.ContractError, match="duplicate JSON key"):
        builder.load_json(duplicate, "duplicate")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision_id", "OTHER", "decision ID"),
        ("status", "APPLIED", "decision status"),
        ("authority", "OTHER", "decision authority"),
        ("application_status", "APPLIED", "application status"),
    ],
)
def test_wrong_decision_identity_rejected(
    field: str,
    value: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mutate(decision: dict[str, Any]) -> None:
        decision[field] = value

    paths, shas, *_rest = install_values(tmp_path, monkeypatch, decision_mutator=mutate)
    with pytest.raises(builder.ContractError, match=message):
        builder.load_and_validate_inputs(paths, shas)


@pytest.mark.parametrize("mode", ["missing", "duplicate"])
@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_each_target_evidence_must_occur_once(
    mode: str,
    target_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = applied_value()
    records = applied["canonical_component_evidence_records"]
    record = next(
        item for item in records if item["component_evidence_id"] == target_id
    )
    if mode == "missing":
        records.remove(record)
    else:
        records.append(copy.deepcopy(record))
    paths, shas, *_rest = install_values(tmp_path, monkeypatch, applied=applied)
    with pytest.raises(
        builder.ContractError,
        match="exactly once|duplicate applied component evidence ID",
    ):
        builder.load_and_validate_inputs(paths, shas)


@pytest.mark.parametrize("target_id", TARGET_IDS)
def test_each_target_evidence_requires_exact_position_binding(
    target_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied = applied_value()
    record = next(
        item
        for item in applied["canonical_component_evidence_records"]
        if item["component_evidence_id"] == target_id
    )
    record["position_id"] = "TFE-WRONG"
    paths, shas, *_rest = install_values(tmp_path, monkeypatch, applied=applied)
    with pytest.raises(builder.ContractError, match="position binding"):
        builder.load_and_validate_inputs(paths, shas)


def test_malformed_canonical_evidence_structure_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    applied = applied_value()
    applied["canonical_component_evidence_records"] = "bad"
    paths, shas, *_rest = install_values(tmp_path, monkeypatch, applied=applied)
    with pytest.raises(builder.ContractError, match="canonical records missing"):
        builder.load_and_validate_inputs(paths, shas)


def test_unexpected_ninth_superseded_id_and_wrong_rule_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ninth(decision: dict[str, Any]) -> None:
        decision["supersession"]["applies_only_to_evidence_ids"].append("COMP-999")

    paths, shas, *_rest = install_values(
        tmp_path / "ninth", monkeypatch, decision_mutator=ninth
    )
    with pytest.raises(builder.ContractError, match="supersession"):
        builder.load_and_validate_inputs(paths, shas)

    def wrong_rule(decision: dict[str, Any]) -> None:
        decision["supersession"]["prior_value"] = "OTHER"

    paths, shas, *_rest = install_values(
        tmp_path / "rule", monkeypatch, decision_mutator=wrong_rule
    )
    with pytest.raises(builder.ContractError, match="supersession"):
        builder.load_and_validate_inputs(paths, shas)


def test_decision_and_applied_binding_mismatches_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_decision(decision: dict[str, Any]) -> None:
        decision["lineage_anchors"]["applied_component_lineage_sha256"] = "0" * 64

    paths, shas, *_rest = install_values(
        tmp_path / "decision", monkeypatch, decision_mutator=bad_decision
    )
    with pytest.raises(builder.ContractError, match="applied-lineage binding"):
        builder.load_and_validate_inputs(paths, shas)

    applied = applied_value()
    applied["source_lineage"]["canonical_replay_sha256"] = "0" * 64
    paths, shas, *_rest = install_values(
        tmp_path / "applied", monkeypatch, applied=applied
    )
    with pytest.raises(builder.ContractError, match="canonical binding"):
        builder.load_and_validate_inputs(paths, shas)


@pytest.mark.parametrize("mode", ["count", "last_row", "group", "existing_rt820"])
def test_parent_inventory_mismatch_rejected(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def mutate(parent: dict[str, Any]) -> None:
        if mode == "count":
            parent["completion"]["scope"]["component_groups"] = 33
        elif mode == "last_row":
            parent["calculator_input_format"]["row_drafts"][-1]["row_id"] = "BAD"
        elif mode == "group":
            parent["cabinet_groups"][2]["row_draft_ids"].pop()
        else:
            parent["calculator_input_format"]["row_drafts"][19]["calculator_values"][
                "component_code"
            ] = "EKF-RT-820"

    paths, shas, *_rest = install_values(tmp_path, monkeypatch, parent_mutator=mutate)
    with pytest.raises(builder.ContractError):
        builder.load_and_validate_inputs(paths, shas)


@pytest.mark.parametrize(
    "mode", ["prefix", "shu_t1", "row_id", "double", "tst05", "work432", "fallback"]
)
def test_successor_mutations_rejected(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    loaded = builder.load_and_validate_inputs(paths, shas)
    successor = builder.build_successor_payload(loaded)
    rows = successor["calculator_input_format"]["row_drafts"]
    if mode == "prefix":
        rows[0]["component_label"] = "changed"
    elif mode == "shu_t1":
        successor["cabinet_groups"][14]["product_name"] = "changed"
    elif mode == "row_id":
        rows[112]["row_id"] = "BAD"
    elif mode == "double":
        rows.append(copy.deepcopy(rows[-1]))
    elif mode == "tst05":
        rows[112]["calculator_values"]["component_code"] = "TST05"
    elif mode == "work432":
        successor["source"]["shu_t2_rt820_technical_successor"][
            "rt820_pricing_provenance_only"
        ]["generic_work_432_prohibited"] = False
    else:
        successor["source"]["shu_t2_rt820_technical_successor"][
            "rt820_pricing_provenance_only"
        ]["family_fallback_prohibited"] = False
    with pytest.raises(builder.ContractError):
        builder.validate_successor_payload(successor, loaded)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("before_count", 16),
        ("after_count", 8),
        ("remaining_evidence_ids", list(SHU_T1_PROVENANCE_IDS)),
        ("remaining_exclusion_records", []),
    ],
)
def test_unsupported_exclusion_claims_are_rejected(
    claim: str,
    value: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    loaded = builder.load_and_validate_inputs(paths, shas)
    successor = builder.build_successor_payload(loaded)
    projection = successor["source"]["shu_t2_rt820_technical_successor"][
        "technical_projection"
    ]
    projection[claim] = value
    with pytest.raises(builder.ContractError, match="bindings/provenance"):
        builder.validate_successor_payload(successor, loaded)


@pytest.mark.parametrize(
    "claim",
    [
        "outside_cabinet_membership_asserted",
        "outside_cabinet_count_transition_asserted",
    ],
)
def test_unsupported_boolean_exclusion_assertions_cannot_be_enabled(
    claim: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    loaded = builder.load_and_validate_inputs(paths, shas)
    successor = builder.build_successor_payload(loaded)
    projection = successor["source"]["shu_t2_rt820_technical_successor"][
        "technical_projection"
    ]
    projection[claim] = True
    with pytest.raises(builder.ContractError, match="bindings/provenance"):
        builder.validate_successor_payload(successor, loaded)


def test_existing_output_and_atomic_link_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    existing = tmp_path / "existing" / builder.OUTPUT_FILENAME
    existing.parent.mkdir()
    with pytest.raises(builder.ContractError, match="output directory already exists"):
        builder.publish_successor(paths, shas, existing)

    def fail_link(_source: Path, _target: Path) -> None:
        raise OSError("synthetic link failure")

    monkeypatch.setattr(builder.os, "link", fail_link)
    output = tmp_path / "link-failure" / builder.OUTPUT_FILENAME
    with pytest.raises(builder.ContractError, match="atomic no-overwrite"):
        builder.publish_successor(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_toctou_before_link_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    original = Path.read_bytes
    calls = 0

    def changed(path: Path) -> bytes:
        nonlocal calls
        value = original(path)
        if path == paths.parent_completed_input:
            calls += 1
            if calls >= 2:
                return value + b"changed"
        return value

    monkeypatch.setattr(Path, "read_bytes", changed)
    output = tmp_path / "toctou" / builder.OUTPUT_FILENAME
    with pytest.raises(builder.ContractError, match="TOCTOU"):
        builder.publish_successor(paths, shas, output)
    assert not output.exists()
    assert not output.parent.exists()


def test_post_link_validation_failure_is_link_aware_and_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    original_link = builder.os.link
    original_validate = builder.validate_successor_payload
    linked = False

    def track_link(source: Path, target: Path) -> None:
        nonlocal linked
        original_link(source, target)
        linked = True

    def fail_after_link(payload: Any, loaded: Any) -> None:
        if linked:
            raise builder.ContractError("synthetic final validation failure")
        original_validate(payload, loaded)

    monkeypatch.setattr(builder.os, "link", track_link)
    monkeypatch.setattr(builder, "validate_successor_payload", fail_after_link)
    output = tmp_path / "post-link" / builder.OUTPUT_FILENAME
    with pytest.raises(builder.ContractError) as raised:
        builder.main(cli_arguments(paths, shas, output))
    assert str(raised.value) == "synthetic final validation failure"
    assert linked is True
    assert not output.exists()
    assert not output.parent.exists()
    assert "PUBLISHED_IMMUTABLE_NO_OVERWRITE" not in capsys.readouterr().out


def test_foreign_final_replacement_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    original = builder.load_json
    foreign = b"foreign replacement"

    def replace_final(path: Path, label: str) -> Any:
        if label == "published technical successor":
            path.unlink()
            path.write_bytes(foreign)
            raise builder.ContractError("synthetic post-link failure")
        return original(path, label)

    monkeypatch.setattr(builder, "load_json", replace_final)
    output = tmp_path / "foreign" / builder.OUTPUT_FILENAME
    with pytest.raises(
        builder.ContractError, match="foreign final replacement preserved"
    ):
        builder.publish_successor(paths, shas, output)
    assert output.read_bytes() == foreign
    assert list(output.parent.iterdir()) == [output]


def test_staging_cleanup_failure_cannot_return_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, shas, *_rest = install_values(tmp_path, monkeypatch)
    original = Path.unlink

    def fail_staging(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.endswith(".staging"):
            raise OSError("synthetic staging cleanup failure")
        original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staging)
    output = tmp_path / "cleanup" / builder.OUTPUT_FILENAME
    with pytest.raises(builder.ContractError, match="rollback cleanup blocked"):
        builder.publish_successor(paths, shas, output)
    assert not output.exists()
    assert output.parent.exists()
    assert any(path.name.endswith(".staging") for path in output.parent.iterdir())
