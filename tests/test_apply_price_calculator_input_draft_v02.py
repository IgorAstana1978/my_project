import copy
import csv
import hashlib
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLY_SCRIPT = PROJECT_ROOT / "scripts" / "apply_price_calculator_input_draft_v02.py"
VALIDATOR_SCRIPT = (
    PROJECT_ROOT / "scripts" / "validate_completed_price_calculator_input_draft.py"
)
RUNNER_SCRIPT = (
    PROJECT_ROOT / "scripts" / "run_checked_price_calculator_from_completed_draft.py"
)
SUCCESSOR_SCRIPT = (
    PROJECT_ROOT / "scripts" / "build_price_calculator_input_draft_v02_successor.py"
)
SUCCESSOR_TEST_SUPPORT = (
    PROJECT_ROOT / "tests" / "test_build_price_calculator_input_draft_v02_successor.py"
)


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


application = cast(
    Any,
    load_script_module("apply_price_calculator_input_draft_v02_for_test", APPLY_SCRIPT),
)
validator = cast(
    Any,
    load_script_module(
        "validate_completed_price_calculator_input_draft_v02_for_test",
        VALIDATOR_SCRIPT,
    ),
)
runner = cast(
    Any,
    load_script_module(
        "run_checked_price_calculator_from_completed_draft_v02_for_test",
        RUNNER_SCRIPT,
    ),
)


def write_json(path: Path, value: Any) -> str:
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def synthetic_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    row_ids = [f"ROW-DRAFT-{index:04d}" for index in range(1, 110)]
    component_rows: dict[int, list[str]] = {
        9: [f"ROW-DRAFT-{index:04d}" for index in range(24, 28)],
        15: ["ROW-DRAFT-0015"],
        16: [f"ROW-DRAFT-{index:04d}" for index in range(74, 76)],
    }
    reserved = set(component_rows[9] + component_rows[15] + component_rows[16])
    ordinary_groups = [index for index in range(1, 32) if index not in (9, 15, 16)]
    for index in ordinary_groups:
        component_rows[index] = []
    for position, row_id in enumerate(
        [value for value in row_ids if value not in reserved]
    ):
        component_rows[ordinary_groups[position % len(ordinary_groups)]].append(row_id)

    component_groups: list[dict[str, Any]] = []
    for index in range(1, 32):
        review_id = f"COMPONENT-LABEL-REVIEW-{index:03d}"
        mapping_id = f"COMPONENT-MAPPING-{index:03d}"
        rows = component_rows[index]
        code: str | None = "EKF-VA47-29-1P"
        install_type: str | None = "modular_1p"
        base_label = "Автоматический выключатель ВА47 1Р 16А — 1шт."
        breaking_capacity_applies = index <= 18
        breaking_capacity_approval: str | None = None
        if index in (9, 16):
            code = None
            install_type = None
            base_label = "Дифференциальный автомат АД12 2Р 16А, 30мА — 1шт."
        elif index == 15:
            mapping_id = "COMPONENT-MAPPING-012"
            code = "EKF-AD32-1P-N"
            install_type = "diff_1p_n"
            base_label = "АД12, 2P, C16, 30мА"
            breaking_capacity_approval = "6кА"
        elif index > 18:
            code = "EKF-VN-32-3P"
            install_type = "load_switch_3p"
            base_label = "Вводной выключатель нагрузки 3Р Iр=16А - 1шт."
            breaking_capacity_applies = False
        component_groups.append(
            {
                "review_group_id": review_id,
                "mapping_request_id": mapping_id,
                "row_draft_ids": rows,
                "approved_internal_component_code": code,
                "install_type": install_type,
                "proposed_base_label_without_breaking_capacity": base_label,
                "breaking_capacity_policy_applies": breaking_capacity_applies,
                "breaking_capacity_human_approval": breaking_capacity_approval,
                "row_component_qty_per_individual_cabinet": {
                    row_id: 1 for row_id in rows
                },
            }
        )

    cabinet_rows: dict[int, list[str]] = {
        1: [*row_ids[0:14], *row_ids[15:19]],
        2: [row_ids[14]],
        3: row_ids[19:27],
        4: row_ids[27:35],
        5: row_ids[35:43],
        6: row_ids[43:51],
        7: row_ids[51:59],
        8: row_ids[59:67],
        9: row_ids[67:75],
        10: row_ids[75:77],
        11: row_ids[77:93],
        12: row_ids[93:105],
        13: row_ids[105:107],
        14: row_ids[107:109],
    }
    templates = {
        1: "ПР",
        2: "Щоф",
        3: "ШУ-Т2",
        4: "ЩАО-1Ж",
        5: "ЩАО-2Ж",
        6: "ЩАО-3Ж",
        7: "ЩО-1Ж",
        8: "ЩО-2Ж",
        9: "ЩС",
        10: "ЩЭ-3кв",
        11: "ЩЭ-4кв",
        12: "ЩЭ-5кв",
        13: "ЩЭ-6кв",
        14: "ЩО-3Ж",
    }
    cabinet_groups = [
        {
            "cabinet_group_id": f"CABINET-GROUP-{index:03d}",
            "cabinet_mapping_request_id": f"CABINET-MAPPING-{index:03d}",
            "source_cabinet_template": templates[index],
            "affected_row_draft_ids": cabinet_rows[index],
            "consumables_factor": 1.2,
        }
        for index in range(1, 15)
    ]
    parent = {
        "schema_version": "technical_csv_label_human_review_packet.v0.5.1",
        "project_id": "2024/086",
        "component_label_review_groups": component_groups,
        "cabinet_label_review_groups": cabinet_groups,
    }
    parent_path = tmp_path / "parent.json"
    parent_sha = write_json(parent_path, parent)

    cabinet_decisions = [
        (
            ["CABINET-GROUP-001"],
            "CAB-KURN-038-24",
            "Корпус КУРН-0,38-24 540×490×170 мм, металл",
        ),
        (
            ["CABINET-GROUP-002"],
            "CAB-KRN-18",
            "Корпус КРН-18 265×440×100 мм, металл",
        ),
        (
            [
                "CABINET-GROUP-003",
                "CABINET-GROUP-004",
                "CABINET-GROUP-005",
                "CABINET-GROUP-006",
                "CABINET-GROUP-007",
                "CABINET-GROUP-008",
                "CABINET-GROUP-014",
            ],
            "CAB-KRN-12",
            "Корпус КРН-12 265×330×100 мм, металл",
        ),
        (
            ["CABINET-GROUP-009"],
            "CAB-KRN-24",
            "Корпус КРН-24 395×330×100 мм, металл",
        ),
        (
            [
                "CABINET-GROUP-010",
                "CABINET-GROUP-011",
                "CABINET-GROUP-012",
                "CABINET-GROUP-013",
            ],
            "CAB-SCHE-BI-900X900X120-M12",
            "Встроенный ЩЭ, 900×900×120 мм, металл 1.2 мм",
        ),
    ]
    effective = {
        "schema_version": "technical_csv_label_human_review_packet.v0.6",
        "project_id": "2024/086",
        "status": "IGOR_FINAL_HUMAN_REVIEW_COMPLETE_NOT_APPLIED",
        "source_lineage": {
            "parent_effective_packet": {
                "path": str(parent_path),
                "sha256": parent_sha,
            }
        },
        "effective_human_review_counts": {
            "breaking_capacity_remaining": 0,
            "component_label_remaining": 0,
            "cabinet_label_remaining": 0,
            "technical_conflict_remaining": 0,
            "total_remaining_human_review": 0,
        },
        "invariants": {
            "component_groups": 31,
            "component_coverage": "109/109",
            "cabinet_coverage": "14/14",
            "scope_expansion": False,
        },
        "resolved_human_review_not_applied": {
            "breaking_capacity_decisions": [
                {
                    "question_scope": {
                        "review_group_id": f"COMPONENT-LABEL-REVIEW-{index:03d}"
                    },
                    "decision": {
                        "breaking_capacity": "6кА",
                        "status": "APPROVED_BY_IGOR_NOT_APPLIED",
                        "scope_expansion": False,
                    },
                }
                for index in range(1, 19)
            ],
            "cabinet_label_decisions": [
                {
                    "question_scope": {
                        "cabinet_group_ids": group_ids,
                        "internal_cabinet_code": code,
                        "proposed_authoritative_label": label,
                    },
                    "decision": {
                        "status": "APPROVED_BY_IGOR_NOT_APPLIED",
                        "scope_expansion": False,
                    },
                }
                for group_ids, code, label in cabinet_decisions
            ],
        },
    }
    effective_path = tmp_path / "effective.json"
    write_json(effective_path, effective)

    product_decisions = {
        "schema": "technical_sche_product_name_human_decisions.v0.1",
        "status": "IGOR_SCHE_PRODUCT_NAMES_APPROVED_NOT_APPLIED",
        "decisions": [
            {
                "exact_scope": {
                    "cabinet_group_id": f"CABINET-GROUP-{index:03d}",
                },
                "approved_product_name": f"ЩЭ-{index - 7}кв",
                "scope_expansion": False,
                "application_status": "NOT_APPLIED",
            }
            for index in range(10, 14)
        ],
    }
    product_path = tmp_path / "products.json"
    write_json(product_path, product_decisions)

    pmhd = {
        "schema_version": "pricing_mapping_human_decisions.v0.1",
        "project_id": "2024/086",
    }
    pmhd_path = tmp_path / "pmhd.json"
    pmhd_sha = write_json(pmhd_path, pmhd)

    ad12_decisions = {
        "schema": "technical_ad12_breaking_capacity_human_decisions.v0.1",
        "status": "IGOR_AD12_45KA_EXACT_REPLACEMENT_APPROVED_NOT_APPLIED",
        "decisions": [
            {
                "exact_scope": {
                    "mapping_request_id": mapping_id,
                    "row_draft_ids": component_rows[index],
                },
                "approved_replacement_state": {
                    "manufacturer_article": "DA12-16-30-bas",
                    "characteristic": "C",
                    "breaking_capacity": "4,5кА",
                },
                "scope_expansion": False,
                "application_status": "NOT_APPLIED",
            }
            for index, mapping_id in (
                (9, "COMPONENT-MAPPING-009"),
                (16, "COMPONENT-MAPPING-016"),
            )
        ],
    }
    ad12_path = tmp_path / "ad12.json"
    write_json(ad12_path, ad12_decisions)

    row_to_cabinet = {
        row_id: f"CABINET-GROUP-{index:03d}"
        for index, rows in cabinet_rows.items()
        for row_id in rows
    }
    row_to_quantity = {row_id: 1 for rows in component_rows.values() for row_id in rows}
    draft = {
        "schema_version": "price_calculator_input_draft.v0.2",
        "draft_type": "price_calculator_input_draft",
        "source": {"project_id": "2024/086"},
        "cabinet_groups": [
            {
                "cabinet_group_id": group["cabinet_group_id"],
                "source_cabinet_template": group["source_cabinet_template"],
                "product_name": None,
                "cabinet_code": None,
                "cabinet_label": None,
                "consumables_factor": None,
                "mapping_status": "IGOR_REQUIRED",
                "row_draft_ids": group["affected_row_draft_ids"],
            }
            for group in cabinet_groups
        ],
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_row_drafts",
            "delimiter": ";",
            "columns": (
                list(application.CALCULATOR_COLUMNS)
                if hasattr(application, "CALCULATOR_COLUMNS")
                else [
                    "product_name",
                    "cabinet_code",
                    "consumables_factor",
                    "component_code",
                    "component_qty",
                    "install_type",
                ]
            ),
            "row_drafts": [
                {
                    "row_id": row_id,
                    "cabinet_group_id": row_to_cabinet[row_id],
                    "calculator_values": {
                        "product_name": None,
                        "cabinet_code": None,
                        "consumables_factor": None,
                        "component_code": None,
                        "component_qty": row_to_quantity[row_id],
                        "install_type": None,
                    },
                    "source_quantity": {},
                    "source_component_evidence_ids": [f"COMP-{index:03d}"],
                    "approved_signature": {},
                    "mapping_status": "IGOR_REQUIRED",
                }
                for index, row_id in enumerate(row_ids, start=1)
            ],
        },
        "coverage": {
            "pricing_row_draft_count": 109,
            "cabinet_group_count": 14,
        },
        "safety": {
            "price_calculation_executed": False,
            "pricing_started": False,
            "price_approved_by_igor": False,
            "commercial_csv_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
            "downstream_started": False,
        },
        "next_required_human_actions": [],
    }
    draft_path = tmp_path / "draft.json"
    draft_sha = write_json(draft_path, draft)
    standard_authoritative_inputs = (
        {
            "role": "BASE_DRAFT",
            "path": str(draft_path),
            "filename": draft_path.name,
            "sha256": draft_sha,
            "schema": "price_calculator_input_draft.v0.2",
            "project_id_json_path": "$.source.project_id",
        },
        {
            "role": "PRICING_MAPPING_HUMAN_DECISIONS",
            "path": str(pmhd_path),
            "filename": pmhd_path.name,
            "sha256": pmhd_sha,
            "schema": "pricing_mapping_human_decisions.v0.1",
            "project_id_json_path": "$.project_id",
        },
        {
            "role": "PARENT_TECHNICAL_PACKET",
            "path": str(parent_path),
            "filename": parent_path.name,
            "sha256": parent_sha,
            "schema": "technical_csv_label_human_review_packet.v0.5.1",
            "project_id_json_path": "$.project_id",
        },
    )
    standard_decisions = []
    for group_id, product_name in application.STANDARD_PRODUCT_NAMES.items():
        index = int(group_id[-3:])
        group = cabinet_groups[index - 1]
        standard_decisions.append(
            {
                "cabinet_group_id": group_id,
                "mapping_request_id": group["cabinet_mapping_request_id"],
                "row_draft_ids": group["affected_row_draft_ids"],
                "source_template": group["source_cabinet_template"],
                "approved_product_name": product_name,
                "source_bindings": application.standard_source_bindings(
                    base_position=index - 1,
                    pmhd_position=index - 1,
                    parent_position=index - 1,
                ),
                "decision_status": "APPROVED_BY_IGOR_NOT_APPLIED",
                "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
                "application_status": "NOT_APPLIED",
                "scope_expansion": False,
            }
        )
    standard = {
        "schema": application.STANDARD_PRODUCT_DECISION_SCHEMA,
        "project_id": "2024/086",
        "artifact_type": "IMMUTABLE_HUMAN_DECISION_CAPTURE",
        "status": application.STANDARD_PRODUCT_DECISION_STATUS,
        "created_at_utc": "2026-08-11T00:00:00.000Z",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "decision_scope": "STANDARD_CABINET_PRODUCT_NAME_ONLY",
        "application_status": "NOT_APPLIED",
        "scope_expansion": False,
        "immutable_state": {
            "immutable": True,
            "no_overwrite": True,
            "content_frozen_at_creation": True,
            "application_status": "NOT_APPLIED",
        },
        "authoritative_inputs": list(standard_authoritative_inputs),
        "decision_summary": {
            "decision_count": 10,
            "cabinet_group_count": 10,
            "row_count": 77,
            "cabinet_group_ids": list(application.STANDARD_PRODUCT_NAMES),
            "application_status": "NOT_APPLIED",
            "scope_expansion": False,
        },
        "decisions": standard_decisions,
        "safety": dict(application.STANDARD_SAFETY),
    }
    standard_path = tmp_path / "standard-products.json"
    standard_sha = write_json(standard_path, standard)
    monkeypatch.setattr(
        application, "STANDARD_PRODUCT_DECISION_PATH", standard_path.resolve()
    )
    monkeypatch.setattr(application, "STANDARD_PRODUCT_DECISION_SHA256", standard_sha)
    monkeypatch.setattr(
        application, "STANDARD_AUTHORITATIVE_INPUTS", standard_authoritative_inputs
    )
    return {
        "draft": draft_path,
        "effective": effective_path,
        "products": product_path,
        "standard": standard_path,
        "ad12": ad12_path,
    }


def expected_sha_arguments(inputs: dict[str, Path]) -> dict[str, str]:
    return {
        "expected_draft_sha256": hashlib.sha256(
            inputs["draft"].read_bytes()
        ).hexdigest(),
        "expected_effective_packet_sha256": hashlib.sha256(
            inputs["effective"].read_bytes()
        ).hexdigest(),
        "expected_sche_product_name_decisions_sha256": hashlib.sha256(
            inputs["products"].read_bytes()
        ).hexdigest(),
        "expected_standard_product_name_decisions_sha256": hashlib.sha256(
            inputs["standard"].read_bytes()
        ).hexdigest(),
        "expected_ad12_breaking_capacity_decisions_sha256": hashlib.sha256(
            inputs["ad12"].read_bytes()
        ).hexdigest(),
    }


def application_arguments(
    inputs: dict[str, Path], output: Path, *, authorized: bool = True
) -> dict[str, Any]:
    return {
        "draft_json": inputs["draft"],
        "effective_packet_json": inputs["effective"],
        "sche_product_name_decisions_json": inputs["products"],
        "standard_product_name_decisions_json": inputs["standard"],
        "ad12_breaking_capacity_decisions_json": inputs["ad12"],
        "output_json": output,
        "application_authorized_by_igor": authorized,
        **expected_sha_arguments(inputs),
    }


def validate_standard_fixture(
    inputs: dict[str, Path], standard: dict[str, Any] | None = None
) -> dict[str, str]:
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    effective = json.loads(inputs["effective"].read_text(encoding="utf-8"))
    parent_binding = effective["source_lineage"]["parent_effective_packet"]
    parent_path = Path(parent_binding["path"]).resolve(strict=False)
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    artifact = standard or json.loads(inputs["standard"].read_text(encoding="utf-8"))
    return cast(
        dict[str, str],
        application.validate_standard_product_name_decisions(
            artifact,
            draft["cabinet_groups"],
            parent["cabinet_label_review_groups"],
            parent_path=parent_path,
            parent_sha256=parent_binding["sha256"],
        ),
    )


def apply_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Path]:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / "completed.json"
    payload = application.apply_v02_completion(
        **application_arguments(inputs, output),
        applied_at_utc="2026-08-07T00:00:00+00:00",
    )
    return payload, output


def test_v02_completion_preserves_scope_quantity_and_scoped_bc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, output = apply_fixture(tmp_path, monkeypatch)
    rows = {
        row["row_id"]: row for row in payload["calculator_input_format"]["row_drafts"]
    }
    ad12_rows = {
        *(f"ROW-DRAFT-{index:04d}" for index in range(24, 28)),
        *(f"ROW-DRAFT-{index:04d}" for index in range(74, 76)),
    }

    assert output.is_file()
    assert len(rows) == 109
    assert len(payload["cabinet_groups"]) == 14
    assert all(row["calculator_values"]["component_qty"] == 1 for row in rows.values())
    assert all(
        ("4,5кА" in rows[row_id]["component_label"]) == (row_id in ad12_rows)
        for row_id in rows
    )
    assert all(
        rows[row_id]["calculator_values"]["component_code"]
        == "EKF-AD12-1P-N-C16-30MA-4P5KA"
        for row_id in ad12_rows
    )
    assert rows["ROW-DRAFT-0015"]["calculator_values"]["component_code"] == (
        "EKF-AD32-1P-N"
    )
    assert "6кА" in rows["ROW-DRAFT-0015"]["component_label"]
    assert payload["completion"]["scope"] == {
        "component_groups": 31,
        "rows": "109/109",
        "cabinet_groups": "14/14",
        "duplicate_component_membership": 0,
        "duplicate_cabinet_membership": 0,
        "scope_expansion": False,
    }


def test_v02_completion_materializes_four_sche_products_and_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, output = apply_fixture(tmp_path, monkeypatch)
    products = {
        group["cabinet_group_id"]: group["product_name"]
        for group in payload["cabinet_groups"]
        if group["cabinet_code"] == "CAB-SCHE-BI-900X900X120-M12"
    }

    assert products == {
        "CABINET-GROUP-010": "ЩЭ-3кв",
        "CABINET-GROUP-011": "ЩЭ-4кв",
        "CABINET-GROUP-012": "ЩЭ-5кв",
        "CABINET-GROUP-013": "ЩЭ-6кв",
    }
    validation = validator.validate_completed_price_calculator_input_draft(output)
    assert validation.status == "PASS"
    split_result = runner.CheckedRunResult(output, tmp_path / "prices.xlsx")
    item_inputs = runner.split_v02_item_inputs(payload, split_result)
    assert len(item_inputs) == 14
    assert not split_result.red_flags


def test_v02_completion_materializes_exact_standard_product_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _ = apply_fixture(tmp_path, monkeypatch)
    completed = {
        group["cabinet_group_id"]: group for group in payload["cabinet_groups"]
    }

    assert completed["CABINET-GROUP-001"]["source_cabinet_template"] == "ПР"
    assert {
        group_id: completed[group_id]["product_name"]
        for group_id in application.STANDARD_PRODUCT_NAMES
    } == application.STANDARD_PRODUCT_NAMES


def test_v02_completion_rejects_non_null_standard_product_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["cabinet_groups"][0]["product_name"] = "ПР"
    write_json(inputs["draft"], draft)
    output = tmp_path / "blocked-missing-product.json"

    with pytest.raises(application.CompletionError, match="product_name"):
        application.apply_v02_completion(**application_arguments(inputs, output))
    assert not output.exists()


def test_valid_standard_artifact_has_exact_10_group_77_row_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)

    assert validate_standard_fixture(inputs) == application.STANDARD_PRODUCT_NAMES


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "status",
        "authority",
        "immutable",
        "application_status",
        "scope_expansion",
        "input_role",
        "input_path",
        "input_schema",
        "input_sha",
        "input_missing",
        "input_extra",
        "input_reordered",
        "safety_true",
        "safety_missing",
        "decision_missing",
        "decision_extra",
        "decision_duplicate",
        "decision_reordered",
        "row_missing",
        "row_extra",
        "row_duplicate",
        "row_reordered",
        "mapping",
        "template",
        "product_name",
        "json_path",
    ],
)
def test_standard_artifact_contract_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    standard = json.loads(inputs["standard"].read_text(encoding="utf-8"))
    decisions = standard["decisions"]
    if mutation == "schema":
        standard["schema"] = "wrong"
    elif mutation == "status":
        standard["status"] = "APPLIED"
    elif mutation == "authority":
        standard["authority"] = "NOT_IGOR"
    elif mutation == "immutable":
        standard["immutable_state"]["immutable"] = False
    elif mutation == "application_status":
        standard["application_status"] = "APPLIED"
    elif mutation == "scope_expansion":
        standard["scope_expansion"] = True
    elif mutation == "input_role":
        standard["authoritative_inputs"][0]["role"] = "WRONG"
    elif mutation == "input_path":
        standard["authoritative_inputs"][0]["path"] = "wrong.json"
    elif mutation == "input_schema":
        standard["authoritative_inputs"][0]["schema"] = "wrong"
    elif mutation == "input_sha":
        standard["authoritative_inputs"][0]["sha256"] = "0" * 64
    elif mutation == "input_missing":
        standard["authoritative_inputs"].pop()
    elif mutation == "input_extra":
        standard["authoritative_inputs"].append(
            copy.deepcopy(standard["authoritative_inputs"][0])
        )
    elif mutation == "input_reordered":
        standard["authoritative_inputs"].reverse()
    elif mutation == "safety_true":
        standard["safety"]["application_started"] = True
    elif mutation == "safety_missing":
        standard["safety"].pop("production_started")
    elif mutation == "decision_missing":
        decisions.pop()
    elif mutation == "decision_extra":
        decisions.append(copy.deepcopy(decisions[0]))
    elif mutation == "decision_duplicate":
        decisions[1] = copy.deepcopy(decisions[0])
    elif mutation == "decision_reordered":
        decisions[0], decisions[1] = decisions[1], decisions[0]
    elif mutation == "row_missing":
        decisions[0]["row_draft_ids"].pop()
    elif mutation == "row_extra":
        decisions[0]["row_draft_ids"].append("ROW-DRAFT-9999")
    elif mutation == "row_duplicate":
        decisions[0]["row_draft_ids"].append(decisions[0]["row_draft_ids"][0])
    elif mutation == "row_reordered":
        decisions[0]["row_draft_ids"].reverse()
    elif mutation == "mapping":
        decisions[0]["mapping_request_id"] = "CABINET-MAPPING-999"
    elif mutation == "template":
        decisions[0]["source_template"] = "Корпус ..."
    elif mutation == "product_name":
        decisions[0]["approved_product_name"] = "Корпус ..."
    else:
        decisions[0]["source_bindings"]["base_draft"][
            "row_draft_ids_json_path"
        ] = "$.cabinet_groups[1].row_draft_ids"

    with pytest.raises(application.CompletionError):
        validate_standard_fixture(inputs, standard)


def test_standard_artifact_duplicate_json_key_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate-standard.json"
    path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")

    with pytest.raises(application.CompletionError, match="duplicate JSON key"):
        application.load_json(path, "standard product-name decisions")


def test_standard_and_sche_product_scopes_must_not_overlap() -> None:
    standard = dict(application.STANDARD_PRODUCT_NAMES)
    sche = dict(application.SCHE_PRODUCT_NAMES)
    sche["CABINET-GROUP-001"] = "WRONG"

    with pytest.raises(application.CompletionError, match="overlap"):
        application.combine_product_name_decisions(standard, sche)


@pytest.mark.parametrize(
    "expected_sha_argument",
    [
        "expected_draft_sha256",
        "expected_effective_packet_sha256",
        "expected_sche_product_name_decisions_sha256",
        "expected_standard_product_name_decisions_sha256",
        "expected_ad12_breaking_capacity_decisions_sha256",
    ],
)
def test_v02_completion_rejects_each_expected_sha_mismatch_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected_sha_argument: str,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / f"blocked-{expected_sha_argument}.json"
    arguments = application_arguments(inputs, output)
    arguments[expected_sha_argument] = "0" * 64

    with pytest.raises(application.CompletionError, match="SHA.*mismatch"):
        application.apply_v02_completion(**arguments)
    assert not output.exists()


def test_standard_artifact_path_is_hard_bound_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    copied = tmp_path / "copied-standard.json"
    copied.write_bytes(inputs["standard"].read_bytes())
    inputs["standard"] = copied
    output = tmp_path / "wrong-standard-path-output.json"

    with pytest.raises(application.CompletionError, match="path mismatch"):
        application.apply_v02_completion(**application_arguments(inputs, output))
    assert not output.exists()


def test_application_lineage_contains_exact_standard_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, _output = apply_fixture(tmp_path, monkeypatch)
    standard_lineage = payload["completion"]["lineage"][
        "standard_product_name_decisions"
    ]

    assert standard_lineage == {
        "path": str(application.STANDARD_PRODUCT_DECISION_PATH),
        "sha256": application.STANDARD_PRODUCT_DECISION_SHA256,
    }


def test_runner_source_compiles_with_parenthesized_exception_tuple(
    tmp_path: Path,
) -> None:
    source = RUNNER_SCRIPT.read_text(encoding="utf-8")

    assert "except (OSError, RuntimeError):" in source
    assert "except OSError, RuntimeError:" not in source
    py_compile.compile(
        str(RUNNER_SCRIPT),
        cfile=str(tmp_path / "runner.pyc"),
        doraise=True,
    )


def test_v02_completion_requires_separate_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / "blocked.json"

    try:
        application.apply_v02_completion(
            **application_arguments(inputs, output, authorized=False),
        )
    except application.CompletionError as exc:
        assert "separate exact Igor application authorization" in str(exc)
    else:
        raise AssertionError("application must fail closed without authorization")
    assert not output.exists()


def test_v02_completion_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / "exists.json"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(application.CompletionError, match="overwrite is forbidden"):
        application.apply_v02_completion(**application_arguments(inputs, output))
    assert output.read_text(encoding="utf-8") == "keep"


def test_readiness_mode_validates_without_authorization_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    before = sorted(path.name for path in tmp_path.iterdir())
    hashes = expected_sha_arguments(inputs)

    application.validate_v02_application_readiness(
        draft_json=inputs["draft"],
        effective_packet_json=inputs["effective"],
        sche_product_name_decisions_json=inputs["products"],
        standard_product_name_decisions_json=inputs["standard"],
        ad12_breaking_capacity_decisions_json=inputs["ad12"],
        **hashes,
    )

    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_readiness_mode_preserves_existing_quantity_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["calculator_input_format"]["row_drafts"][0]["calculator_values"][
        "component_qty"
    ] = 2
    write_json(inputs["draft"], draft)

    with pytest.raises(application.CompletionError, match="draft quantity changed"):
        application.validate_v02_application_readiness(
            draft_json=inputs["draft"],
            effective_packet_json=inputs["effective"],
            sche_product_name_decisions_json=inputs["products"],
            standard_product_name_decisions_json=inputs["standard"],
            ad12_breaking_capacity_decisions_json=inputs["ad12"],
            **expected_sha_arguments(inputs),
        )


def test_readiness_rejects_missing_standard_product_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["cabinet_groups"][0]["product_name"] = ""
    write_json(inputs["draft"], draft)
    forbidden_output = tmp_path / "must-not-exist.json"

    with pytest.raises(application.CompletionError, match="product_name"):
        application.validate_v02_application_readiness(
            draft_json=inputs["draft"],
            effective_packet_json=inputs["effective"],
            sche_product_name_decisions_json=inputs["products"],
            standard_product_name_decisions_json=inputs["standard"],
            ad12_breaking_capacity_decisions_json=inputs["ad12"],
            **expected_sha_arguments(inputs),
        )
    assert not forbidden_output.exists()


def test_application_readiness_accepts_valid_successor_contract_via_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["source"]["quantity_correction_successor"] = {
        "profile": "synthetic-valid-contract"
    }
    write_json(inputs["draft"], draft)
    calls: list[tuple[Path, str]] = []

    def validate_contract(
        value: dict[str, Any], *, parent_path: Path, parent_sha256: str
    ) -> None:
        assert value["source"]["quantity_correction_successor"]["profile"] == (
            "synthetic-valid-contract"
        )
        calls.append((parent_path, parent_sha256))

    monkeypatch.setattr(
        application, "validate_embedded_successor_contract", validate_contract
    )
    application.validate_v02_application_readiness(
        draft_json=inputs["draft"],
        effective_packet_json=inputs["effective"],
        sche_product_name_decisions_json=inputs["products"],
        standard_product_name_decisions_json=inputs["standard"],
        ad12_breaking_capacity_decisions_json=inputs["ad12"],
        **expected_sha_arguments(inputs),
    )
    assert len(calls) == 1


def test_application_readiness_rejects_transitive_successor_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["source"]["quantity_correction_successor"] = {
        "profile": "synthetic-transitive-drift"
    }
    write_json(inputs["draft"], draft)

    def reject_contract(
        _value: dict[str, Any], *, parent_path: Path, parent_sha256: str
    ) -> None:
        del parent_path, parent_sha256
        raise RuntimeError("transitive base draft changed during validation")

    monkeypatch.setattr(
        application, "validate_embedded_successor_contract", reject_contract
    )
    with pytest.raises(
        application.CompletionError, match="transitive base draft changed"
    ):
        application.validate_v02_application_readiness(
            draft_json=inputs["draft"],
            effective_packet_json=inputs["effective"],
            sche_product_name_decisions_json=inputs["products"],
            standard_product_name_decisions_json=inputs["standard"],
            ad12_breaking_capacity_decisions_json=inputs["ad12"],
            **expected_sha_arguments(inputs),
        )


def test_full_application_runs_embedded_successor_validator_without_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    support = cast(
        Any,
        load_script_module(
            "successor_test_support_for_application", SUCCESSOR_TEST_SUPPORT
        ),
    )
    builder = support.successor
    builder_base, correction, builder_parent = support.fixture_contracts()
    application_base = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    builder_rows = {
        row["row_id"]: row
        for row in builder_base["calculator_input_format"]["row_drafts"]
    }
    for row in application_base["calculator_input_format"]["row_drafts"]:
        contract_row = builder_rows[row["row_id"]]
        row["calculator_values"]["component_qty"] = contract_row["calculator_values"][
            "component_qty"
        ]
        row["source_quantity"] = copy.deepcopy(contract_row["source_quantity"])
        row["source_component_evidence_ids"] = copy.deepcopy(
            contract_row["source_component_evidence_ids"]
        )
        row["approved_signature"] = copy.deepcopy(contract_row["approved_signature"])

    base_path = tmp_path / "successor-base.json"
    base_sha = write_json(base_path, application_base)
    correction_path = tmp_path / "successor-correction.json"
    correction_sha = write_json(correction_path, correction)
    monkeypatch.setattr(builder, "BASE_SHA256", base_sha)
    monkeypatch.setattr(builder, "CORRECTION_SHA256", correction_sha)
    support.bind_parent_correction_path(builder_parent, correction_path)
    builder_parent["source_lineage"]["pr_section_composition_human_decision"][
        "sha256"
    ] = correction_sha
    for group in builder_parent["component_label_review_groups"]:
        group["authoritative_correction_provenance"]["sha256"] = correction_sha
        mapping_id = group["mapping_request_id"]
        mapping_number = int(mapping_id[-3:])
        group["approved_internal_component_code"] = "EKF-VA47-29-1P"
        group["install_type"] = "modular_1p"
        group["proposed_base_label_without_breaking_capacity"] = (
            "Автоматический выключатель ВА47 1Р 16А — 1шт."
        )
        group["breaking_capacity_policy_applies"] = mapping_number <= 18
        group["breaking_capacity_human_approval"] = None
        if mapping_number in (9, 16):
            group["approved_internal_component_code"] = None
            group["install_type"] = None
            group["proposed_base_label_without_breaking_capacity"] = (
                "Дифференциальный автомат АД12 2Р 16А, 30мА — 1шт."
            )
        elif mapping_number == 12:
            group["approved_internal_component_code"] = "EKF-AD32-1P-N"
            group["install_type"] = "diff_1p_n"
            group["breaking_capacity_human_approval"] = "6кА"

    original_parent = json.loads(
        Path(
            json.loads(inputs["effective"].read_text(encoding="utf-8"))[
                "source_lineage"
            ]["parent_effective_packet"]["path"]
        ).read_text(encoding="utf-8")
    )
    builder_parent["cabinet_label_review_groups"] = original_parent[
        "cabinet_label_review_groups"
    ]
    parent_path = tmp_path / "successor-parent.json"
    parent_sha = write_json(parent_path, builder_parent)
    monkeypatch.setattr(builder, "PARENT_SHA256", parent_sha)

    successor_payload = builder.build_successor_payload(
        application_base,
        correction,
        builder_parent,
        base_path=base_path,
        correction_path=correction_path,
        parent_path=parent_path,
    )
    write_json(inputs["draft"], successor_payload)

    effective = json.loads(inputs["effective"].read_text(encoding="utf-8"))
    effective["source_lineage"]["parent_effective_packet"] = {
        "path": str(parent_path),
        "sha256": parent_sha,
    }
    write_json(inputs["effective"], effective)
    ad12 = json.loads(inputs["ad12"].read_text(encoding="utf-8"))
    parent_by_mapping = {
        group["mapping_request_id"]: group
        for group in builder_parent["component_label_review_groups"]
    }
    for decision in ad12["decisions"]:
        mapping_id = decision["exact_scope"]["mapping_request_id"]
        decision["exact_scope"]["row_draft_ids"] = parent_by_mapping[mapping_id][
            "row_draft_ids"
        ]
    write_json(inputs["ad12"], ad12)

    standard = json.loads(inputs["standard"].read_text(encoding="utf-8"))
    standard["authoritative_inputs"][0].update(
        {"path": str(base_path), "filename": base_path.name, "sha256": base_sha}
    )
    standard["authoritative_inputs"][2].update(
        {"path": str(parent_path), "filename": parent_path.name, "sha256": parent_sha}
    )
    standard_sha = write_json(inputs["standard"], standard)
    monkeypatch.setattr(
        application,
        "STANDARD_AUTHORITATIVE_INPUTS",
        tuple(standard["authoritative_inputs"]),
    )
    monkeypatch.setattr(application, "STANDARD_PRODUCT_DECISION_SHA256", standard_sha)

    validator_source = SUCCESSOR_SCRIPT.read_text(encoding="utf-8")
    validator_source = validator_source.replace(
        "PROJECT_ROOT = Path(__file__).resolve().parents[1]",
        f"PROJECT_ROOT = Path({str(PROJECT_ROOT)!r})",
    )
    replacements = {
        "571647f920f2ffcbfda66339c20be4673eb41127c0534054695c3d4cfc15fbf3": base_sha,
        (
            "12d6887edd44c3f13e5b7b5126a8441fa9a6aff350f7eae6ea81da7b4c1abc13"
        ): correction_sha,
        "1c68b9af8edfef2ca42f89c69e70a873553595d096413f197f9bfe77ec80fc00": parent_sha,
    }
    for original, replacement in replacements.items():
        assert original in validator_source
        validator_source = validator_source.replace(original, replacement)
    synthetic_validator = tmp_path / "synthetic-successor-contract.py"
    synthetic_validator.write_text(validator_source, encoding="utf-8")
    monkeypatch.setattr(application, "SUCCESSOR_CONTRACT_PATH", synthetic_validator)

    output = tmp_path / "integrated-completed.json"
    payload = application.apply_v02_completion(
        **application_arguments(inputs, output),
        applied_at_utc="2026-08-11T00:00:00+00:00",
    )

    assert output.is_file()
    assert payload["completion"]["status"] == application.COMPLETION_STATUS
    assert payload["source"]["quantity_correction_successor"]["profile"] == (
        builder.PROFILE
    )


def test_readiness_rejects_malformed_successor_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["source"]["quantity_correction_successor"] = {"profile": "wrong"}
    write_json(inputs["draft"], draft)

    with pytest.raises(
        application.CompletionError, match="successor provenance validation failed"
    ):
        application.validate_v02_application_readiness(
            draft_json=inputs["draft"],
            effective_packet_json=inputs["effective"],
            sche_product_name_decisions_json=inputs["products"],
            standard_product_name_decisions_json=inputs["standard"],
            ad12_breaking_capacity_decisions_json=inputs["ad12"],
            **expected_sha_arguments(inputs),
        )


def test_readiness_cli_forbids_application_authorization(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    hashes = expected_sha_arguments(inputs)
    result = application.main(
        [
            "--draft-json",
            str(inputs["draft"]),
            "--expected-draft-sha256",
            hashes["expected_draft_sha256"],
            "--effective-packet-json",
            str(inputs["effective"]),
            "--expected-effective-packet-sha256",
            hashes["expected_effective_packet_sha256"],
            "--sche-product-name-decisions-json",
            str(inputs["products"]),
            "--expected-sche-product-name-decisions-sha256",
            hashes["expected_sche_product_name_decisions_sha256"],
            "--standard-product-name-decisions-json",
            str(inputs["standard"]),
            "--expected-standard-product-name-decisions-sha256",
            hashes["expected_standard_product_name_decisions_sha256"],
            "--ad12-breaking-capacity-decisions-json",
            str(inputs["ad12"]),
            "--expected-ad12-breaking-capacity-decisions-sha256",
            hashes["expected_ad12_breaking_capacity_decisions_sha256"],
            "--readiness-only",
            "--application-authorized-by-igor",
        ]
    )

    assert result == 1
    assert "forbids --application-authorized-by-igor" in capsys.readouterr().out


def test_application_cleans_staging_if_atomic_publication_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / "atomic-failure.json"

    def fail_link(_source: Path, _target: Path) -> None:
        raise OSError("simulated publication failure")

    monkeypatch.setattr(application.os, "link", fail_link)
    with pytest.raises(application.CompletionError, match="publication failed"):
        application.apply_v02_completion(
            **application_arguments(inputs, output),
            applied_at_utc="2026-08-07T00:00:00+00:00",
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_standard_input_toctou_drift_fails_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = synthetic_inputs(tmp_path, monkeypatch)
    output = tmp_path / "standard-toctou-output.json"
    original_complete = application.complete_v02_payload

    def complete_then_drift(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = cast(dict[str, Any], original_complete(*args, **kwargs))
        inputs["standard"].write_text("drift", encoding="utf-8")
        return payload

    monkeypatch.setattr(application, "complete_v02_payload", complete_then_drift)
    with pytest.raises(
        application.CompletionError,
        match="changed.*standard_product_name_decisions",
    ):
        application.apply_v02_completion(
            **application_arguments(inputs, output),
            applied_at_utc="2026-08-11T00:00:00+00:00",
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".*.staging"))


def test_checked_runner_routes_four_sche_groups_through_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, output = apply_fixture(tmp_path, monkeypatch)
    resolved_workbooks: list[Path] = []
    calculator_costs: list[int | None] = []

    def fake_resolver(path: Path) -> int:
        resolved_workbooks.append(path)
        return 12345

    def fake_calculator(
        price_workbook: Path,
        input_csv: Path,
        custom_cabinet_base_cost: int | None = None,
    ) -> Any:
        with input_csv.open("r", encoding="utf-8", newline="") as csv_file:
            row_count = len(list(csv.reader(csv_file, delimiter=";"))) - 1
        calculator_costs.append(custom_cabinet_base_cost)
        stdout = "\n".join(
            [
                "Status:",
                "PASS",
                "Input rows count:",
                str(row_count),
                "Cabinet:",
                "TEST",
                "Cabinet price:",
                "1",
                "Component material total:",
                "1",
                "Work total:",
                "1",
                "Additional materials total:",
                "1",
                "Total preliminary price:",
                "1",
            ]
        )
        return runner.CalculatorProcessResult(returncode=0, stdout=stdout)

    monkeypatch.setattr(runner, "resolve_custom_sche_base_cost", fake_resolver)
    monkeypatch.setattr(runner, "run_calculator_cli", fake_calculator)
    metal_workbook = tmp_path / "metal.xlsx"
    result = runner.run_checked_price_calculator_from_completed_draft(
        output,
        tmp_path / "prices.xlsx",
        custom_sche_metal_workbook=metal_workbook,
    )

    assert result.status == "PASS"
    assert resolved_workbooks == [metal_workbook.resolve(strict=False)]
    assert calculator_costs.count(12345) == 4
    assert calculator_costs.count(None) == 10
