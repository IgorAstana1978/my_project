import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT / "scripts" / "build_invoice519_pricing_profile_additive_successor.py"
)


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pricing_additive_builder_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = cast(Any, load_module())


def base_profile() -> dict[str, Any]:
    positions = [
        {
            "pricing_position_id": f"PRICE-POSITION-{index:03d}",
            "physical_multiplicity": 83 if index == 51 else 1,
        }
        for index in range(1, 52)
    ]
    current = {
        "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
        "pricing_profile_decision_status": "APPROVED_NOT_APPLIED",
        "pricing_calculation_status": "NOT_EXECUTED",
        "coverage": {
            "technical_cabinet_groups": 14,
            "section_aware_pricing_positions": 51,
            "physical_cabinets": 133,
            "composition_fingerprints": 11,
        },
        "products": [f"BASE-{index}" for index in range(1, 15)],
        "modular_formula_family": {"scope_cabinet_group_ids": ["CABINET-GROUP-001"]},
        "cabinet_groups": [
            {"cabinet_group_id": f"CABINET-GROUP-{index:03d}"} for index in range(1, 15)
        ],
        "composition_fingerprints": [
            {"fingerprint_sha256": f"{index:064x}"} for index in range(1, 12)
        ],
        "pricing_positions": positions,
    }
    return {
        "schema_version": "technical_invoice519_pricing_profile_human_decisions.v0.1",
        "artifact_type": "igor_invoice519_pricing_profile_human_decisions",
        "project_id": "2024/086",
        "decision_id": "IGOR-INVOICE519-PRICING-PROFILE-2024-086-001",
        "status": "IGOR_INVOICE519_PRICING_PROFILE_APPROVED_NOT_APPLIED",
        "authority": {"authority": "IGOR_DIRECT_HUMAN_APPROVAL"},
        "application_status": "NOT_APPLIED",
        "scope_expansion": False,
        "immutable_state": {"immutable": True, "no_overwrite": True},
        "authoritative_inputs": [],
        "scope_partition": {
            "current_completed_technical_scope": {
                "technical_scope_status": "CURRENT_COMPLETED_INPUT_SCOPE",
                "pricing_profile_decision_status": "APPROVED_NOT_APPLIED",
                "pricing_calculation_status": "NOT_EXECUTED",
                "coverage": copy.deepcopy(current["coverage"]),
            }
        },
        "current_completed_technical_scope": current,
        "safety_flags": {
            "calculator_run_authorized": False,
            "client_send_authorized": False,
            "production_authorized": False,
        },
        "validation_summary": {"current_coverage": "51/133/11"},
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
    }


def decisions() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    composition = decision_identity(builder.DECISION_CONTRACTS[0])
    composition["exact_scope"] = [
        {"section": section} for section in ("9", "11", "13", "15")
    ]
    cabinet = decision_identity(builder.DECISION_CONTRACTS[1])
    cabinet["authority"] = {"authority": "IGOR_DIRECT_HUMAN_APPROVAL"}
    cabinet["calculation_contract"] = {
        "inputs_kzt": {"X": 6936, "I": 0, "G": 20450, "H": 1764},
        "raw_unit_result_kzt": "53762.72702586206896551724138",
        "approved_calculated_unit_price_kzt": 53763,
        "physical_multiplicity": 4,
        "approved_calculated_exact_scope_total_kzt": 215052,
    }
    rt820 = decision_identity(builder.DECISION_CONTRACTS[2])
    rt820["approved_code_install_contract"] = {
        "internal_component_code": "EKF-RT-820",
        "install_type": "temperature_relay_din_2mod",
        "module_width_din": 2,
    }
    rt820["pricing_work_semantics"] = {
        "material_price_kzt_per_complete_set": 15000,
        "work_price_kzt_per_complete_set": 900,
        "work_price_semantics": "EXACT_COMPONENT_WORK_PRICE",
        "generic_modular_2p_work_price_prohibited": True,
        "family_fallback_prohibited": True,
        "fuzzy_fallback_prohibited": True,
    }
    rt820["tst05_bundle_semantics"] = {
        "separate_component_row": False,
        "separate_material_charge": False,
        "separate_work_charge": False,
    }
    return composition, cabinet, rt820


def technical_successor() -> dict[str, Any]:
    base_rows = [
        {
            "row_id": f"ROW-DRAFT-{index:04d}",
            "calculator_values": {
                "component_code": "BASE",
                "component_qty": 1,
                "install_type": "modular_1p",
            },
        }
        for index in range(1, 110)
    ]
    appended_values = [
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_qty": 1,
            "component_code": "EKF-RT-820",
            "install_type": "temperature_relay_din_2mod",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_qty": 1,
            "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
            "install_type": "diff_1p_n",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_qty": 1,
            "component_code": "EKF-VA47-29-2P",
            "install_type": "modular_2p",
        },
    ]
    rows = [
        *base_rows,
        *[
            {
                "row_id": f"ROW-DRAFT-{index:04d}",
                "calculator_values": values,
            }
            for index, values in zip(range(110, 113), appended_values, strict=True)
        ],
    ]
    groups: list[dict[str, Any]] = [
        {"cabinet_group_id": f"CABINET-GROUP-{index:03d}"} for index in range(1, 15)
    ]
    groups.append(
        {
            "cabinet_group_id": "CABINET-GROUP-015",
            "product_name": "ШУ-Т1",
            "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
        }
    )
    return {
        "schema_version": "price_calculator_input_draft.v0.2",
        "source": {
            "additive_completed_input_successor": {
                "contract": builder.TECHNICAL_SUCCESSOR_CONTRACT,
                "direct_human_decision_inputs": [
                    builder.decision_binding(*contract)
                    for contract in builder.DECISION_CONTRACTS
                ],
                "scope_expansion": False,
            }
        },
        "cabinet_groups": groups,
        "calculator_input_format": {"row_drafts": rows},
        "completion": {
            "scope": {
                "component_groups": 34,
                "rows": "112/112",
                "cabinet_groups": "15/15",
            }
        },
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    base = base_profile()
    successor = builder.build_successor_payload(
        base,
        technical_successor(),
        Path(r"C:\outside\completed-successor.json"),
        "a" * 64,
        *decisions(),
    )
    return base, successor


def test_builds_append_only_15_55_137_12_profile_successor() -> None:
    base, successor = build()
    current = successor["current_completed_technical_scope"]
    assert (
        current["cabinet_groups"][:14]
        == base["current_completed_technical_scope"]["cabinet_groups"]
    )
    assert (
        current["pricing_positions"][:51]
        == base["current_completed_technical_scope"]["pricing_positions"]
    )
    assert (
        current["composition_fingerprints"][:11]
        == base["current_completed_technical_scope"]["composition_fingerprints"]
    )
    assert current["coverage"] == {
        "technical_cabinet_groups": 15,
        "section_aware_pricing_positions": 55,
        "physical_cabinets": 137,
        "composition_fingerprints": 12,
    }
    assert [p["pricing_position_id"] for p in current["pricing_positions"][-4:]] == [
        "PRICE-POSITION-052",
        "PRICE-POSITION-053",
        "PRICE-POSITION-054",
        "PRICE-POSITION-055",
    ]
    assert {p["physical_multiplicity"] for p in current["pricing_positions"][-4:]} == {
        1
    }
    assert {
        p["approved_unit_price_kzt"] for p in current["pricing_positions"][-4:]
    } == {53763}
    assert (
        current["composition_fingerprints"][-1]["fingerprint_sha256"]
        == builder.FINGERPRINT
    )
    assert successor["additive_successor"]["candidate_project_total_kzt"] == 11841516
    assert (
        successor["additive_successor"]["price_approval_status"]
        == "REQUIRES_IGOR_PRICE_APPROVAL"
    )


def test_profile_successor_is_deterministic() -> None:
    _base, first = build()
    _base, second = build()
    assert first == second


@pytest.mark.parametrize(
    "mutation",
    [
        lambda technical, values: technical["calculator_input_format"]["row_drafts"][
            -3
        ]["calculator_values"].__setitem__("component_code", "SIMILAR-RELAY"),
        lambda technical, values: values[1]["calculation_contract"].__setitem__(
            "approved_calculated_unit_price_kzt", 53762
        ),
        lambda technical, values: values[2]["pricing_work_semantics"].__setitem__(
            "work_price_kzt_per_complete_set", 432
        ),
    ],
)
def test_technical_or_price_contract_drift_fails_closed(mutation: Any) -> None:
    technical = technical_successor()
    values = list(decisions())
    mutation(technical, values)
    with pytest.raises(builder.ContractError):
        builder.build_successor_payload(
            base_profile(), technical, Path("successor.json"), "a" * 64, *values
        )


def test_prefix_mutation_and_position_collision_fail_closed() -> None:
    base, successor = build()
    successor["current_completed_technical_scope"]["pricing_positions"][0][
        "pricing_position_id"
    ] = "DRIFT"
    with pytest.raises(builder.ContractError, match="prefix"):
        builder.validate_successor_payload(
            successor, base, Path(r"C:\outside\completed-successor.json"), "a" * 64
        )
    base = base_profile()
    base["current_completed_technical_scope"]["pricing_positions"][0][
        "pricing_position_id"
    ] = "PRICE-POSITION-052"
    with pytest.raises(builder.ContractError, match="collision"):
        builder.build_successor_payload(
            base,
            technical_successor(),
            Path(r"C:\outside\completed-successor.json"),
            "a" * 64,
            *decisions(),
        )


def test_duplicate_key_and_authorization_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"x":1,"x":2}', encoding="utf-8")
    with pytest.raises(builder.ContractError, match="duplicate JSON key"):
        builder.load_json(duplicate, "duplicate")

    completed_input = tmp_path / "input.json"
    output = tmp_path / "out.json"
    publication_calls = 0

    def synthetic_publish(path: Path, digest: str, target: Path) -> str:
        nonlocal publication_calls
        publication_calls += 1
        assert path == completed_input
        assert digest == "a" * 64
        assert target == output
        return "f" * 64

    monkeypatch.setattr(builder, "publish_successor", synthetic_publish)

    def arguments(token: str) -> list[str]:
        return [
            "--completed-input-successor",
            str(completed_input),
            "--completed-input-successor-sha256",
            "a" * 64,
            "--output",
            str(output),
            "--authorization",
            token,
        ]

    rejected_tokens = (
        "IGOR_CODE_ONLY_SUCCESSOR_BUILD_AUTHORIZED",
        "IGOR_SHU_T1_TECHNICAL_SUCCESSOR_PUBLICATION_AUTHORIZED",
        "NO",
    )
    for token in rejected_tokens:
        with pytest.raises(builder.ContractError, match="publication acknowledgement"):
            builder.main(arguments(token))
        assert publication_calls == 0
        assert not output.exists()
        assert not list(tmp_path.glob(".*.staging"))

    assert (
        builder.main(
            arguments(
                "IGOR_SHU_T1_INVOICE519_PRICING_PROFILE_SUCCESSOR_PUBLICATION_AUTHORIZED"
            )
        )
        == 0
    )
    assert publication_calls == 1
    assert not completed_input.exists()
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_publication_is_exclusive_and_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = base_profile()
    technical = technical_successor()
    values = decisions()
    paths = [tmp_path / f"input-{index}.json" for index in range(5)]
    for path, payload in zip(paths, [base, technical, *values], strict=True):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    shas = [builder.sha256_bytes(path.read_bytes()) for path in paths]
    monkeypatch.setattr(builder, "BASE_PROFILE", paths[0])
    monkeypatch.setattr(builder, "BASE_PROFILE_SHA256", shas[0])
    monkeypatch.setattr(
        builder,
        "DECISION_CONTRACTS",
        tuple(
            (contract[0], path, sha, *contract[3:])
            for contract, path, sha in zip(
                builder.DECISION_CONTRACTS, paths[2:], shas[2:], strict=True
            )
        ),
    )
    technical["source"]["additive_completed_input_successor"][
        "direct_human_decision_inputs"
    ] = [builder.decision_binding(*contract) for contract in builder.DECISION_CONTRACTS]
    paths[1].write_text(json.dumps(technical, ensure_ascii=False), encoding="utf-8")
    shas[1] = builder.sha256_bytes(paths[1].read_bytes())
    output = tmp_path / "profile-successor.json"
    digest = builder.publish_successor(paths[1], shas[1], output)
    assert digest == builder.sha256_bytes(output.read_bytes())
    assert not list(tmp_path.glob(".*.staging"))
    with pytest.raises(builder.ContractError, match="overwrite"):
        builder.publish_successor(paths[1], shas[1], output)
