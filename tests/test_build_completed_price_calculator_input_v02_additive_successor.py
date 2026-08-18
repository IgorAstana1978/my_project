import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "build_completed_price_calculator_input_v02_additive_successor.py"
)


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "completed_additive_builder_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_module())


def base_payload() -> dict[str, Any]:
    rows = [
        {
            "row_id": f"ROW-DRAFT-{index:04d}",
            "cabinet_group_id": f"CABINET-GROUP-{min(index, 14):03d}",
            "calculator_values": {
                "product_name": f"BASE-{index}",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_code": "EKF-VA47-29-1P",
                "component_qty": 1,
                "install_type": "modular_1p",
            },
            "source_quantity": {},
            "source_component_evidence_ids": [f"COMP-BASE-{index:03d}"],
            "approved_signature": {},
            "mapping_status": builder.MAPPING_STATUS,
            "component_label": "base",
        }
        for index in range(1, 110)
    ]
    groups = [
        {
            "cabinet_group_id": f"CABINET-GROUP-{index:03d}",
            "source_cabinet_template": f"BASE-{index}",
            "product_name": f"BASE-{index}",
            "cabinet_code": "CAB-KRN-12",
            "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
            "consumables_factor": 1.2,
            "mapping_status": builder.MAPPING_STATUS,
            "row_draft_ids": [rows[index - 1]["row_id"]],
        }
        for index in range(1, 15)
    ]
    return {
        "schema_version": builder.BASE_SCHEMA,
        "draft_type": "price_calculator_input_draft",
        "source": {"base": True},
        "cabinet_groups": groups,
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_row_drafts",
            "delimiter": ";",
            "columns": [
                "product_name",
                "cabinet_code",
                "consumables_factor",
                "component_code",
                "component_qty",
                "install_type",
            ],
            "row_drafts": rows,
        },
        "coverage": {
            "installed_component_count": 121,
            "direct_installed_component_count": 107,
            "aggregate_member_count": 14,
            "aggregate_decision_count": 2,
            "pricing_row_draft_count": 109,
            "cabinet_group_count": 14,
            "reserved_meter_space_count": 4,
            "reserved_excluded_from_pricing_count": 4,
            "correction_count": 12,
            "reconfirmation_count": 6,
        },
        "safety": {
            "price_calculation_executed": False,
            "price_approved_by_igor": False,
            "downstream_authorized": False,
        },
        "next_required_human_actions": [],
        "completion": {
            "status": builder.BASE_STATUS,
            "authorization_claim_is_not_human_approval": True,
            "scope": {
                "component_groups": 31,
                "rows": "109/109",
                "cabinet_groups": "14/14",
                "duplicate_component_membership": 0,
                "duplicate_cabinet_membership": 0,
                "scope_expansion": False,
            },
            "ad12_mapping": {"locked": True},
            "mapping_018": {"locked": True},
        },
    }


def decision_identity(contract: tuple[Any, ...]) -> dict[str, Any]:
    _role, _path, _sha, schema, status, decision_id = contract
    return {
        "schema_version": schema,
        "status": status,
        "decision_id": decision_id,
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
        "scope_expansion": False,
        "immutable": True,
        "no_overwrite": True,
    }


def decisions() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    composition = decision_identity(builder.DECISION_CONTRACTS[0])
    composition["exact_scope"] = [
        {
            "section": section,
            "invoice_position": invoice,
            "excel_row": row,
            "technical_position_id": position,
            "physical_quantity": 1,
        }
        for section, position, invoice, row in builder.EXPECTED_SCOPE
    ]
    composition["ordered_component_evidence_ids"] = [
        "COMP-006",
        "COMP-007",
        "COMP-008",
        "COMP-009",
        "COMP-056",
        "COMP-057",
        "COMP-058",
        "COMP-059",
        "COMP-106",
        "COMP-107",
        "COMP-108",
        "COMP-109",
        "COMP-153",
        "COMP-154",
        "COMP-155",
        "COMP-156",
    ]

    cabinet = decision_identity(builder.DECISION_CONTRACTS[1])
    cabinet["authority"] = {"authority": "IGOR_DIRECT_HUMAN_APPROVAL"}
    cabinet["exact_scope"] = {
        "product": "ШУ-Т1",
        "sections_in_order": ["9", "11", "13", "15"],
        "physical_cabinets": 4,
    }
    cabinet["cabinet_decision"] = {
        "source_template": "ЩРН-12",
        "X_cabinet_base_kzt": 6936,
        "I_additional_cabinet_cost_kzt": 0,
        "cabinet_base_counted_exactly_once": True,
        "technical_equivalence_asserted": False,
    }
    cabinet["component_pricing_decisions"] = [
        {"manufacturer_article": "RT-820"},
        {"manufacturer_article": "DA12-16-30-bas"},
        {"manufacturer_article": "mcb4729-2-10C"},
    ]
    cabinet["calculation_contract"] = {
        "inputs_kzt": {"X": 6936, "I": 0, "G": 20450, "H": 1764},
        "approved_calculated_unit_price_kzt": 53763,
        "approved_calculated_exact_scope_total_kzt": 215052,
    }

    rt820 = decision_identity(builder.DECISION_CONTRACTS[2])
    rt820["approved_code_install_contract"] = {
        "manufacturer": "EKF",
        "product": "Реле температуры RT-820 EKF PROxima",
        "manufacturer_article": "RT-820",
        "supply_form": "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR",
        "internal_component_code": "EKF-RT-820",
        "install_type": "temperature_relay_din_2mod",
        "module_width_din": 2,
        "quantity_per_individual_cabinet": 1,
        "unit": "комплект",
        "decision_status": "APPROVED_NOT_APPLIED",
        "application_status": "NOT_APPLIED",
    }
    rt820["pricing_work_semantics"] = {
        "material_source": "КРН!B19",
        "material_price_kzt_per_complete_set": 15000,
        "work_source": "КРН!C19",
        "work_price_kzt_per_complete_set": 900,
        "work_price_semantics": "EXACT_COMPONENT_WORK_PRICE",
        "generic_modular_2p_work_price_prohibited": True,
        "family_fallback_prohibited": True,
        "fuzzy_fallback_prohibited": True,
    }
    rt820["tst05_bundle_semantics"] = {
        "source_evidence_preserved_in_provenance": True,
        "separate_component_row": False,
        "separate_material_charge": False,
        "separate_work_charge": False,
    }
    rt820["scope_isolation"] = {
        "case_scoped_only": True,
        "family_wide_mapping_created": False,
        "other_project_reuse_authorized": False,
    }
    return composition, cabinet, rt820


def test_builds_deterministic_append_only_15_34_112_successor() -> None:
    base = base_payload()
    composition, cabinet, rt820 = decisions()
    first = builder.build_successor_payload(base, composition, cabinet, rt820)
    second = builder.build_successor_payload(base, composition, cabinet, rt820)

    assert first == second
    assert first["cabinet_groups"][:14] == base["cabinet_groups"]
    assert (
        first["calculator_input_format"]["row_drafts"][:109]
        == base["calculator_input_format"]["row_drafts"]
    )
    assert first["coverage"]["cabinet_group_count"] == 15
    assert first["coverage"]["pricing_row_draft_count"] == 112
    assert first["completion"]["scope"]["component_groups"] == 34
    assert [
        row["calculator_values"]["component_code"]
        for row in first["calculator_input_format"]["row_drafts"][-3:]
    ] == [
        "EKF-RT-820",
        "EKF-AD12-1P-N-C16-30MA-4P5KA",
        "EKF-VA47-29-2P",
    ]
    rt_row = first["calculator_input_format"]["row_drafts"][-3]
    assert rt_row["source_component_evidence_ids"] == [
        *builder.RT_EVIDENCE,
        *builder.TST05_EVIDENCE,
    ]
    assert rt_row["approved_signature"]["TST05_separate_component_row"] is False
    assert first["completion"]["ad12_mapping"] == base["completion"]["ad12_mapping"]
    assert first["completion"]["mapping_018"] == base["completion"]["mapping_018"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda values: values[0].__setitem__("status", "APPLIED"), "status"),
        (
            lambda values: values[2]["pricing_work_semantics"].__setitem__(
                "work_price_kzt_per_complete_set", 432
            ),
            "work/fallback",
        ),
        (
            lambda values: values[0]["exact_scope"].pop(),
            "scope",
        ),
    ],
)
def test_human_decision_drift_fails_closed(mutation: Any, message: str) -> None:
    values = list(decisions())
    mutation(values)
    with pytest.raises(builder.ContractError, match=message):
        builder.build_successor_payload(base_payload(), *values)


def test_collision_and_prefix_mutation_fail_closed() -> None:
    base = base_payload()
    base["calculator_input_format"]["row_drafts"][0]["row_id"] = "ROW-DRAFT-0110"
    with pytest.raises(builder.ContractError, match="collision"):
        builder.build_successor_payload(base, *decisions())

    clean = base_payload()
    successor = builder.build_successor_payload(clean, *decisions())
    successor["calculator_input_format"]["row_drafts"][0]["component_label"] = "drift"
    with pytest.raises(builder.ContractError, match="prefix"):
        builder.validate_successor_payload(successor, clean)


def test_duplicate_json_keys_and_authorization_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(builder.ContractError, match="duplicate JSON key"):
        builder.load_json(duplicate, "duplicate")

    output = tmp_path / "out.json"
    publication_calls = 0

    def synthetic_publish(path: Path) -> str:
        nonlocal publication_calls
        publication_calls += 1
        assert path == output
        return "f" * 64

    monkeypatch.setattr(builder, "publish_successor", synthetic_publish)
    rejected_tokens = (
        "IGOR_CODE_ONLY_SUCCESSOR_BUILD_AUTHORIZED",
        "IGOR_SHU_T1_INVOICE519_PRICING_PROFILE_SUCCESSOR_PUBLICATION_AUTHORIZED",
        "NO",
    )
    for token in rejected_tokens:
        with pytest.raises(builder.ContractError, match="publication acknowledgement"):
            builder.main(["--output", str(output), "--authorization", token])
        assert publication_calls == 0
        assert not output.exists()
        assert not list(tmp_path.glob(".*.staging"))

    assert (
        builder.main(
            [
                "--output",
                str(output),
                "--authorization",
                "IGOR_SHU_T1_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED",
            ]
        )
        == 0
    )
    assert publication_calls == 1
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_exclusive_publication_no_overwrite_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = base_payload()
    values = decisions()
    paths = [tmp_path / f"input-{index}.json" for index in range(4)]
    payloads = [base, *values]
    for path, payload in zip(paths, payloads, strict=True):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    shas = [builder.sha256_bytes(path.read_bytes()) for path in paths]
    monkeypatch.setattr(builder, "BASE_COMPLETED_INPUT", paths[0])
    monkeypatch.setattr(builder, "BASE_COMPLETED_INPUT_SHA256", shas[0])
    contracts = tuple(
        (contract[0], path, sha, *contract[3:])
        for contract, path, sha in zip(
            builder.DECISION_CONTRACTS, paths[1:], shas[1:], strict=True
        )
    )
    monkeypatch.setattr(builder, "DECISION_CONTRACTS", contracts)

    output = tmp_path / "successor.json"
    digest = builder.publish_successor(output)
    assert digest == builder.sha256_bytes(output.read_bytes())
    assert not list(tmp_path.glob(".*.staging"))
    with pytest.raises(builder.ContractError, match="overwrite"):
        builder.publish_successor(output)


def test_toctou_change_prevents_publication_and_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = base_payload()
    values = decisions()
    paths = [tmp_path / f"input-{index}.json" for index in range(4)]
    for path, payload in zip(paths, [base, *values], strict=True):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    shas = [builder.sha256_bytes(path.read_bytes()) for path in paths]
    monkeypatch.setattr(builder, "BASE_COMPLETED_INPUT", paths[0])
    monkeypatch.setattr(builder, "BASE_COMPLETED_INPUT_SHA256", shas[0])
    monkeypatch.setattr(
        builder,
        "DECISION_CONTRACTS",
        tuple(
            (contract[0], path, sha, *contract[3:])
            for contract, path, sha in zip(
                builder.DECISION_CONTRACTS, paths[1:], shas[1:], strict=True
            )
        ),
    )
    original_read_bytes = Path.read_bytes
    calls = 0

    def changed_read_bytes(path: Path) -> bytes:
        nonlocal calls
        if path == paths[0]:
            calls += 1
            if calls >= 2:
                return original_read_bytes(path) + b" "
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", changed_read_bytes)
    output = tmp_path / "successor.json"
    with pytest.raises(builder.ContractError, match="TOCTOU"):
        builder.publish_successor(output)
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))
