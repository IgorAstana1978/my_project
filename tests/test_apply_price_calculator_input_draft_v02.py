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


def synthetic_inputs(tmp_path: Path) -> dict[str, Path]:
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

    cabinet_rows: dict[int, list[str]] = {index: [] for index in range(1, 15)}
    for position, row_id in enumerate(row_ids):
        cabinet_rows[(position % 14) + 1].append(row_id)
    templates = {
        1: "ПР",
        2: "Щоф",
        9: "ЩС",
        10: "ЩЭ-3кв",
        11: "ЩЭ-4кв",
        12: "ЩЭ-5кв",
        13: "ЩЭ-6кв",
    }
    cabinet_groups = [
        {
            "cabinet_group_id": f"CABINET-GROUP-{index:03d}",
            "source_cabinet_template": templates.get(index, f"ЩО-{index}"),
            "affected_row_draft_ids": cabinet_rows[index],
            "consumables_factor": 1.2,
        }
        for index in range(1, 15)
    ]
    parent = {
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
                "product_name": (
                    None
                    if group["cabinet_group_id"]
                    in {
                        "CABINET-GROUP-010",
                        "CABINET-GROUP-011",
                        "CABINET-GROUP-012",
                        "CABINET-GROUP-013",
                    }
                    else f"  APPROVED::{group['cabinet_group_id']}::UNCHANGED  "
                ),
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
    write_json(draft_path, draft)
    return {
        "draft": draft_path,
        "effective": effective_path,
        "products": product_path,
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
        "ad12_breaking_capacity_decisions_json": inputs["ad12"],
        "output_json": output,
        "application_authorized_by_igor": authorized,
        **expected_sha_arguments(inputs),
    }


def apply_fixture(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    inputs = synthetic_inputs(tmp_path)
    output = tmp_path / "completed.json"
    payload = application.apply_v02_completion(
        **application_arguments(inputs, output),
        applied_at_utc="2026-08-07T00:00:00+00:00",
    )
    return payload, output


def test_v02_completion_preserves_scope_quantity_and_scoped_bc(
    tmp_path: Path,
) -> None:
    payload, output = apply_fixture(tmp_path)
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
) -> None:
    payload, output = apply_fixture(tmp_path)
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


def test_v02_completion_preserves_standard_product_name_byte_for_byte(
    tmp_path: Path,
) -> None:
    payload, _ = apply_fixture(tmp_path)
    completed = {
        group["cabinet_group_id"]: group for group in payload["cabinet_groups"]
    }

    assert completed["CABINET-GROUP-001"]["source_cabinet_template"] == "ПР"
    assert completed["CABINET-GROUP-001"]["product_name"] == (
        "  APPROVED::CABINET-GROUP-001::UNCHANGED  "
    )


def test_v02_completion_rejects_missing_standard_product_name(tmp_path: Path) -> None:
    inputs = synthetic_inputs(tmp_path)
    draft = json.loads(inputs["draft"].read_text(encoding="utf-8"))
    draft["cabinet_groups"][0]["product_name"] = None
    write_json(inputs["draft"], draft)
    output = tmp_path / "blocked-missing-product.json"

    with pytest.raises(application.CompletionError, match="product_name"):
        application.apply_v02_completion(**application_arguments(inputs, output))
    assert not output.exists()


@pytest.mark.parametrize(
    "expected_sha_argument",
    [
        "expected_draft_sha256",
        "expected_effective_packet_sha256",
        "expected_sche_product_name_decisions_sha256",
        "expected_ad12_breaking_capacity_decisions_sha256",
    ],
)
def test_v02_completion_rejects_each_expected_sha_mismatch_without_output(
    tmp_path: Path,
    expected_sha_argument: str,
) -> None:
    inputs = synthetic_inputs(tmp_path)
    output = tmp_path / f"blocked-{expected_sha_argument}.json"
    arguments = application_arguments(inputs, output)
    arguments[expected_sha_argument] = "0" * 64

    with pytest.raises(application.CompletionError, match="expected SHA-256 mismatch"):
        application.apply_v02_completion(**arguments)
    assert not output.exists()


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


def test_v02_completion_requires_separate_authorization(tmp_path: Path) -> None:
    inputs = synthetic_inputs(tmp_path)
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


def test_v02_completion_refuses_overwrite(tmp_path: Path) -> None:
    inputs = synthetic_inputs(tmp_path)
    output = tmp_path / "exists.json"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(application.CompletionError, match="overwrite is forbidden"):
        application.apply_v02_completion(**application_arguments(inputs, output))
    assert output.read_text(encoding="utf-8") == "keep"


def test_checked_runner_routes_four_sche_groups_through_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, output = apply_fixture(tmp_path)
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
