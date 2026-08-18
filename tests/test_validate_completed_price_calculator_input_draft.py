import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_completed_price_calculator_input_draft.py"
OLD_WORKFLOWS = (
    PROJECT_ROOT
    / "scripts"
    / "build_price_calculator_input_draft_from_confirmed_composition.py",
    PROJECT_ROOT / "scripts" / "calc_quote_price_draft.py",
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_commercial_from_csv.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_commercial_checked.ps1",
    PROJECT_ROOT / "scripts" / "create_client_style_approval_draft.py",
    PROJECT_ROOT / "scripts" / "export_client_style_invoice.py",
    PROJECT_ROOT / "scripts" / "run_client_style_invoice_export.ps1",
    PROJECT_ROOT / "scripts" / "preflight_client_style_invoice_template_contract.py",
    PROJECT_ROOT / "scripts" / "make_quote_capacity100_checked.ps1",
    PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_items.py",
    PROJECT_ROOT / "scripts" / "validate_confirmed_composition_artifact.py",
    PROJECT_ROOT / "scripts" / "validate_preliminary_composition_draft.py",
    PROJECT_ROOT / "scripts" / "verify_preliminary_composition_source_bundle.py",
    PROJECT_ROOT / "scripts" / "build_preliminary_composition_review_card.py",
)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_completed_price_calculator_input_draft_for_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def valid_data() -> dict[str, Any]:
    return {
        "schema_version": "price_calculator_input_draft.v0.1",
        "draft_type": "price_calculator_input_draft",
        "source": {
            "confirmation_id": "CONFIRMED-COMPOSITION-EXAMPLE-001",
            "confirmed_by": "Igor",
            "confirmed_at": "2026-07-07T12:00:00+05:00",
            "source_links": {
                "raw_input_sha256": "1" * 64,
                "preliminary_draft_sha256": "2" * 64,
                "review_card_sha256": "3" * 64,
            },
        },
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_rows",
            "delimiter": ";",
            "columns": [
                "product_name",
                "cabinet_code",
                "consumables_factor",
                "component_code",
                "component_qty",
                "install_type",
            ],
            "rows": [
                {
                    "product_name": "РУ-АВР / ЩРН-24",
                    "cabinet_code": "CAB-KRN-24",
                    "consumables_factor": 1.08,
                    "component_code": "EKF-VA47-29-1P",
                    "component_qty": 4,
                    "install_type": "modular_1p",
                },
                {
                    "product_name": "РУ-АВР / ЩРН-24",
                    "cabinet_code": "CAB-KRN-24",
                    "consumables_factor": 1.08,
                    "component_code": "EKF-VA47-29-3P",
                    "component_qty": 2.5,
                    "install_type": "modular_3p",
                },
            ],
            "missing_required_fields": [],
            "missing_required_fields_note": (
                "resolved by Igor before calculator preflight"
            ),
        },
        "items": [
            {
                "item_id": "ITEM-001",
                "product_name": "РУ-АВР / ЩРН-24",
                "product_type": "switchboard",
                "quantity": 1,
                "cabinet": {
                    "cabinet_code": "CAB-KRN-24",
                    "cabinet_label": "КРН-24",
                },
                "components": [
                    {
                        "component_id": "C-001",
                        "component_code": "EKF-VA47-29-1P",
                        "component_label": "ВА47 1P",
                        "quantity": 4,
                        "install_type": "modular_1p",
                    }
                ],
            }
        ],
        "safety": {
            "status": "price_calculator_input_draft_only",
            "derived_from_confirmed_composition": True,
            "price_calculation_executed": False,
            "price_approved_by_igor": False,
            "commercial_csv_authorized": False,
            "client_style_export_authorized": False,
            "sending_authorized": False,
            "production_authorized": False,
        },
        "next_required_human_actions": [
            "Igor reviews any future price result before commercial CSV or КП.",
        ],
        "operator_completion": {
            "completed_by": "Igor",
            "completed_at": "2026-07-08T10:00:00+05:00",
            "completion_note": "consumables factor confirmed",
            "consumables_factor_confirmed_by_igor": True,
        },
    }


def valid_additive_v02_data() -> dict[str, Any]:
    base_rows: list[dict[str, Any]] = []
    group_row_ids: dict[str, list[str]] = {
        f"CABINET-GROUP-{index:03d}": [] for index in range(1, 15)
    }
    for index in range(1, 110):
        group_index = min(((index - 1) // 8) + 1, 14)
        group_id = f"CABINET-GROUP-{group_index:03d}"
        row_id = f"ROW-DRAFT-{index:04d}"
        group_row_ids[group_id].append(row_id)
        base_rows.append(
            {
                "row_id": row_id,
                "cabinet_group_id": group_id,
                "calculator_values": {
                    "product_name": f"BASE-{group_index}",
                    "cabinet_code": "CAB-KRN-12",
                    "consumables_factor": 1.2,
                    "component_code": "EKF-VA47-29-1P",
                    "component_qty": 1,
                    "install_type": "modular_1p",
                },
                "mapping_status": validator.V02_COMPLETED_MAPPING_STATUS,
                "component_label": "base",
            }
        )
    groups = [
        {
            "cabinet_group_id": group_id,
            "source_cabinet_template": f"BASE-{index}",
            "product_name": f"BASE-{index}",
            "cabinet_code": "CAB-KRN-12",
            "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
            "consumables_factor": 1.2,
            "mapping_status": validator.V02_COMPLETED_MAPPING_STATUS,
            "row_draft_ids": group_row_ids[group_id],
        }
        for index, group_id in enumerate(group_row_ids, start=1)
    ]
    groups.append(
        {
            "cabinet_group_id": "CABINET-GROUP-015",
            "source_cabinet_template": "ЩРН-12",
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "cabinet_label": "Корпус КРН-12 265×330×100 мм, металл",
            "consumables_factor": 1.2,
            "mapping_status": validator.V02_COMPLETED_MAPPING_STATUS,
            "row_draft_ids": ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"],
        }
    )
    appended_values = [
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-RT-820",
            "component_qty": 1,
            "install_type": "temperature_relay_din_2mod",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-AD12-1P-N-C16-30MA-4P5KA",
            "component_qty": 1,
            "install_type": "diff_1p_n",
        },
        {
            "product_name": "ШУ-Т1",
            "cabinet_code": "CAB-KRN-12",
            "consumables_factor": 1.2,
            "component_code": "EKF-VA47-29-2P",
            "component_qty": 1,
            "install_type": "modular_2p",
        },
    ]
    rows = [
        *base_rows,
        *[
            {
                "row_id": f"ROW-DRAFT-{index:04d}",
                "cabinet_group_id": "CABINET-GROUP-015",
                "calculator_values": values,
                "mapping_status": validator.V02_COMPLETED_MAPPING_STATUS,
                "component_label": "approved",
            }
            for index, values in zip(range(110, 113), appended_values, strict=True)
        ],
    ]
    return {
        "schema_version": validator.SCHEMA_VERSION_V02,
        "draft_type": "price_calculator_input_draft",
        "source": {
            "additive_completed_input_successor": {
                "contract": validator.V02_ADDITIVE_SUCCESSOR_CONTRACT,
                "project_id": "2024/086",
                "parent": validator.V02_ADDITIVE_PARENT,
                "direct_human_decision_inputs": copy.deepcopy(
                    validator.V02_ADDITIVE_DECISION_BINDINGS
                ),
                "append_only": True,
                "scope_expansion": False,
            }
        },
        "cabinet_groups": groups,
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_row_drafts",
            "delimiter": ";",
            "columns": list(validator.CALCULATOR_COLUMNS),
            "row_drafts": rows,
        },
        "coverage": {
            "pricing_row_draft_count": 112,
            "cabinet_group_count": 15,
        },
        "safety": {"price_calculation_executed": False},
        "next_required_human_actions": [],
        "completion": {
            "status": validator.V02_COMPLETION_STATUS,
            "authorization_claim_is_not_human_approval": True,
            "scope": {
                "component_groups": 34,
                "rows": "112/112",
                "cabinet_groups": "15/15",
                "duplicate_component_membership": 0,
                "duplicate_cabinet_membership": 0,
                "scope_expansion": False,
            },
            "additive_successor": {
                "contract": validator.V02_ADDITIVE_SUCCESSOR_CONTRACT,
                "application_status": "NOT_APPLIED",
                "pricing_calculation_executed": False,
                "successor_publication_requires_separate_exact_igor_authorization": (
                    True
                ),
            },
        },
    }


def test_additive_v02_full_envelope_passes(tmp_path: Path) -> None:
    result = validator.validate_completed_price_calculator_input_draft(
        write_json(tmp_path, valid_additive_v02_data())
    )
    assert result.status == "PASS"
    assert result.red_flags == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["source"]["additive_completed_input_successor"][
            "direct_human_decision_inputs"
        ][2].__setitem__("sha256", "0" * 64),
        lambda data: data["calculator_input_format"]["row_drafts"][-3][
            "calculator_values"
        ].__setitem__("install_type", "modular_2p"),
        lambda data: data["calculator_input_format"]["row_drafts"].append(
            copy.deepcopy(data["calculator_input_format"]["row_drafts"][-1])
        ),
        lambda data: data["completion"]["scope"].__setitem__("component_groups", 33),
    ],
)
def test_additive_v02_partial_or_drifted_envelope_fails(
    tmp_path: Path, mutation: Any
) -> None:
    data = valid_additive_v02_data()
    mutation(data)
    result = validator.validate_completed_price_calculator_input_draft(
        write_json(tmp_path, data)
    )
    assert result.status == "FAIL"
    assert result.red_flags


def write_json(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "completed-price-calculator-input-draft.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_validation(data: dict[str, Any], tmp_path: Path) -> Any:
    return validator.validate_completed_price_calculator_input_draft(
        write_json(tmp_path, data)
    )


def calculator_format(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["calculator_input_format"])


def first_row(data: dict[str, Any]) -> dict[str, Any]:
    return cast(list[dict[str, Any]], calculator_format(data)["rows"])[0]


def safety(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["safety"])


def operator_completion(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["operator_completion"])


def assert_fails_with(
    data: dict[str, Any],
    tmp_path: Path,
    expected: str,
) -> None:
    result = run_validation(data, tmp_path)

    assert result.status == "FAIL"
    assert any(expected in red_flag for red_flag in result.red_flags), result.red_flags


def test_valid_completed_draft_passes(tmp_path: Path) -> None:
    result = run_validation(valid_data(), tmp_path)

    assert result.status == "PASS"
    assert result.red_flags == []
    assert all(status == "pass" for status in result.checks.values())


def test_malformed_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")

    result = validator.validate_completed_price_calculator_input_draft(path)

    assert result.status == "FAIL"
    assert "input JSON is malformed" in result.red_flags


def test_missing_required_root_field_fails(tmp_path: Path) -> None:
    data = valid_data()
    del data["operator_completion"]

    assert_fails_with(data, tmp_path, "required field is missing: operator_completion")


def test_wrong_schema_version_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["schema_version"] = "price_calculator_input_draft.v9"

    assert_fails_with(data, tmp_path, "schema_version must be")


def test_wrong_draft_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    data["draft_type"] = "other"

    assert_fails_with(data, tmp_path, "draft_type must be")


def test_missing_operator_completion_fails(tmp_path: Path) -> None:
    data = valid_data()
    del data["operator_completion"]

    assert_fails_with(data, tmp_path, "operator_completion")


def test_consumables_factor_confirmed_by_igor_false_fails(tmp_path: Path) -> None:
    data = valid_data()
    operator_completion(data)["consumables_factor_confirmed_by_igor"] = False

    assert_fails_with(data, tmp_path, "consumables_factor_confirmed_by_igor")


def test_missing_required_fields_containing_consumables_factor_fails(
    tmp_path: Path,
) -> None:
    data = valid_data()
    calculator_format(data)["missing_required_fields"] = ["consumables_factor"]

    assert_fails_with(data, tmp_path, "missing_required_fields must be absent or empty")


def test_null_consumables_factor_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["consumables_factor"] = None

    assert_fails_with(data, tmp_path, "consumables_factor")


def test_string_consumables_factor_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["consumables_factor"] = "1.08"

    assert_fails_with(data, tmp_path, "consumables_factor")


def test_consumables_factor_less_than_or_equal_to_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["consumables_factor"] = 0

    assert_fails_with(data, tmp_path, "consumables_factor")


def test_component_qty_less_than_or_equal_to_zero_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["component_qty"] = 0

    assert_fails_with(data, tmp_path, "component_qty")


def test_empty_rows_fails(tmp_path: Path) -> None:
    data = valid_data()
    calculator_format(data)["rows"] = []

    assert_fails_with(data, tmp_path, "rows must be a non-empty list")


def test_wrong_columns_order_fails(tmp_path: Path) -> None:
    data = valid_data()
    columns = cast(list[str], calculator_format(data)["columns"])
    columns[0], columns[1] = columns[1], columns[0]

    assert_fails_with(data, tmp_path, "columns must exactly match")


def test_manual_review_required_install_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["install_type"] = "manual_review_required"

    assert_fails_with(data, tmp_path, "manual_review_required is not allowed")


def test_invalid_install_type_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["install_type"] = "panel_magic"

    assert_fails_with(data, tmp_path, "install_type is not allowed")


def test_price_calculation_executed_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["price_calculation_executed"] = True

    assert_fails_with(data, tmp_path, "price_calculation_executed must be false")


def test_price_approved_by_igor_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["price_approved_by_igor"] = True

    assert_fails_with(data, tmp_path, "price_approved_by_igor must be false")


def test_commercial_csv_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["commercial_csv_authorized"] = True

    assert_fails_with(data, tmp_path, "commercial_csv_authorized must be false")


def test_client_style_export_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["client_style_export_authorized"] = True

    assert_fails_with(data, tmp_path, "client_style_export_authorized must be false")


def test_sending_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["sending_authorized"] = True

    assert_fails_with(data, tmp_path, "sending_authorized must be false")


def test_production_authorized_true_fails(tmp_path: Path) -> None:
    data = valid_data()
    safety(data)["production_authorized"] = True

    assert_fails_with(data, tmp_path, "production_authorized must be false")


def test_forbidden_key_unit_price_kzt_anywhere_fails(tmp_path: Path) -> None:
    data = valid_data()
    first_row(data)["unit_price_kzt"] = 123

    assert_fails_with(data, tmp_path, "forbidden key present")


def test_forbidden_preliminary_key_confidence_anywhere_fails(tmp_path: Path) -> None:
    data = valid_data()
    cast(dict[str, Any], data["items"][0])["confidence"] = 0.9

    assert_fails_with(data, tmp_path, "confidence")


def test_report_has_required_markers_and_safety_boundaries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_json(tmp_path, valid_data())

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert report.startswith(
        "COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_START"
    )
    assert "Mode:\ncompleted price calculator input draft validation only" in report
    assert "Commercial status:\ncalculator input complete only" in report
    assert "no price calculated" in report
    assert "not price approval" in report
    assert "not commercial CSV" in report
    assert "not client-ready КП" in report
    assert "Human Approval:\nIgor approval still required" in report
    assert report.rstrip().endswith(
        "COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_END"
    )


def test_report_does_not_leak_long_completion_note(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = valid_data()
    secret_note = "SECRET OPERATOR COMPLETION NOTE " * 40
    operator_completion(data)["completion_note"] = secret_note
    path = write_json(tmp_path, data)

    assert validator.main(["--input-json", str(path)]) == 0
    report = capsys.readouterr().out

    assert secret_note not in report
    assert "SECRET OPERATOR COMPLETION NOTE" not in report


def test_script_does_not_call_price_calculator() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "calc_quote_price_draft" not in source
    assert "calculate_price_draft" not in source
    assert "PRICE_CALCULATION_DRAFT_REPORT" not in source
    assert "load_workbook" not in source


def test_script_does_not_create_csv_or_xlsx() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()

    assert "write_text" not in source
    assert "csv.reader" not in source
    assert "csv.writer" not in source
    assert "openpyxl" not in source
    assert ".xlsx" not in source


def test_script_does_not_reference_commercial_writer_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "run_invoice_quote_commercial_from_csv" not in source
    assert "make_quote_capacity100_commercial_checked" not in source
    assert "commercial writer" not in source.lower()


def test_script_does_not_reference_client_style_exporter_or_launcher() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "export_client_style_invoice" not in source
    assert "run_client_style_invoice_export" not in source
    assert "client-style exporter" not in source.lower()


def test_script_does_not_call_git() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()

    assert "subprocess" not in source
    assert " git " not in source
    assert "git." not in source


def test_old_workflows_do_not_reference_this_validator() -> None:
    validator_name = "validate_completed_price_calculator_input_draft"

    for path in OLD_WORKFLOWS:
        assert path.is_file(), path
        assert validator_name not in path.read_text(encoding="utf-8"), path
