"""Validate completed price-calculator input draft JSON without pricing."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

REPORT_START = "COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_START"
REPORT_END = "COMPLETED_PRICE_CALCULATOR_INPUT_DRAFT_VALIDATION_REPORT_END"
MODE = "completed price calculator input draft validation only"
COMMERCIAL_STATUS = (
    "calculator input complete only; no price calculated; not price approval; "
    "not commercial CSV; not client-ready КП"
)
HUMAN_APPROVAL = (
    "Igor approval still required before price result, commercial CSV, КП "
    "sending or production"
)

SCHEMA_VERSION = "price_calculator_input_draft.v0.1"
SCHEMA_VERSION_V02 = "price_calculator_input_draft.v0.2"
DRAFT_TYPE = "price_calculator_input_draft"
CALCULATOR_KIND = "confirmed_composition_csv_rows"
CALCULATOR_DELIMITER = ";"
CALCULATOR_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
ROOT_FIELDS = (
    "schema_version",
    "draft_type",
    "source",
    "calculator_input_format",
    "items",
    "safety",
    "next_required_human_actions",
    "operator_completion",
)
CALCULATOR_FORMAT_FIELDS = (
    "kind",
    "delimiter",
    "columns",
    "rows",
    "missing_required_fields",
    "missing_required_fields_note",
)
OPERATOR_COMPLETION_FIELDS = (
    "completed_by",
    "completed_at",
    "completion_note",
    "consumables_factor_confirmed_by_igor",
)
SAFETY_FIELDS = (
    "status",
    "derived_from_confirmed_composition",
    "price_calculation_executed",
    "price_approved_by_igor",
    "commercial_csv_authorized",
    "client_style_export_authorized",
    "sending_authorized",
    "production_authorized",
)
INSTALL_TYPES = {
    "modular_1p",
    "modular_2p",
    "modular_3p",
    "modular_4p",
    "diff_1p_n",
    "diff_3p_4p",
    "load_switch_1p",
    "load_switch_2p",
    "load_switch_3p",
    "load_switch_4p",
    "mccb_up_to_100a",
    "mccb_125_250a",
    "mccb_400a_plus",
    "temperature_relay_din_2mod",
}
V02_COMPLETED_MAPPING_STATUS = "APPROVED_HUMAN_DECISIONS_APPLIED"
V02_COMPLETION_STATUS = "V02_TECHNICAL_COMPLETION_APPLIED_NOT_PRICED"
V02_EXPECTED_COMPONENT_GROUPS = 31
V02_EXPECTED_ROWS = 109
V02_EXPECTED_CABINET_GROUPS = 14
V02_ADDITIVE_SUCCESSOR_CONTRACT = "controlled_additive_completed_input_successor.v0.1"
V02_ADDITIVE_EXPECTED_COMPONENT_GROUPS = 34
V02_ADDITIVE_EXPECTED_ROWS = 112
V02_ADDITIVE_EXPECTED_CABINET_GROUPS = 15
V02_SHU_T2_SUCCESSOR_CONTRACT = "controlled_shu_t2_rt820_technical_successor.v0.1"
V02_SHU_T2_EXPECTED_COMPONENT_GROUPS = 35
V02_SHU_T2_EXPECTED_ROWS = 116
V02_SHU_T2_EXPECTED_CABINET_GROUPS = 15
V02_SHU_T2_PARENT = {
    "path": (
        "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
        "CASE-QF-PROJECT-2024-086-SHU-T1-TECHNICAL-SUCCESSOR-20260818-001\\"
        "price-calculator-input-v0.2-completed-additive-successor.json"
    ),
    "sha256": "08808d1dfa0f5fa2c5a9b9d4a697a8cb44d9875bd32240d77300a0b3f570205e",
    "schema_version": SCHEMA_VERSION_V02,
    "status": V02_COMPLETION_STATUS,
}
V02_SHU_T2_DECISION = {
    "path": (
        "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
        "CASE-QF-PROJECT-2024-086-SHU-T2-RT820-SCOPE-DECISION-20260820-001\\"
        "technical-shu-t2-rt820-scope-human-decision-v0.1.json"
    ),
    "sha256": "92a79401591fa6202af493848dd979a227ae20da8e66b8dea6e8084fc80c2ac6",
    "schema_version": "technical_shu_t2_rt820_scope_human_decision.v0.1",
    "decision_id": "IGOR-SHU-T2-RT820-SCOPE-2024-086-001",
    "status": "IGOR_SHU_T2_RT820_SCOPE_APPROVED_NOT_APPLIED",
    "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
    "application_status": "NOT_APPLIED",
}
V02_ADDITIVE_PARENT = {
    "path": (
        "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
        "CASE-QF-PROJECT-2024-086-PRICE-CALCULATOR-APPLICATION-20260812-001\\"
        "price-calculator-input-v0.2-completed.json"
    ),
    "sha256": "71d933c14a603c24ba8072311b84992d1708cbc7ff1fede59727e727218f5bdb",
}
V02_ADDITIVE_DECISION_BINDINGS = [
    {
        "role": "technical_composition_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-SHU-T1-HUMAN-DECISIONS-20260817-001\\"
            "technical-shu-t1-composition-human-decisions-v0.1.json"
        ),
        "sha256": "bccf62150488037b7df50804c88454119748be103da22dad456db2969126c008",
        "schema_version": "technical_shu_t1_composition_human_decisions.v0.1",
        "status": "IGOR_SHU_T1_COMPOSITION_APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-SHU-T1-COMPOSITION-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
    {
        "role": "cabinet_pricing_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-SHU-T1-CABINET-PRICING-DECISION-20260817-001\\"
            "technical-shu-t1-cabinet-pricing-human-decisions-v0.1.json"
        ),
        "sha256": "b3a1bb84bacb2cc5127752cb378b2151552fcb443f02116b12269a086add4247",
        "schema_version": "technical_shu_t1_cabinet_pricing_human_decisions.v0.1",
        "status": "APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-SHU-T1-CABINET-PRICING-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
    {
        "role": "rt820_code_install_human_decision",
        "path": (
            "C:\\Users\\IgorN\\Documents\\production_ai_cases\\"
            "CASE-QF-PROJECT-2024-086-RT820-CODE-INSTALL-DECISION-20260818-001\\"
            "technical-rt820-code-install-human-decisions-v0.1.json"
        ),
        "sha256": "95c9f2610a6e8429242789e17c3b69ffae31db28655736aed12caa1d3939630f",
        "schema_version": "technical_rt820_code_install_human_decisions.v0.1",
        "status": "IGOR_RT820_CODE_INSTALL_APPROVED_NOT_APPLIED",
        "decision_id": "IGOR-RT820-CODE-INSTALL-2024-086-001",
        "authority": "IGOR_DIRECT_HUMAN_APPROVAL",
        "application_status": "NOT_APPLIED",
    },
]
FORBIDDEN_KEYS = {
    "price_confirmed_by_igor",
    "price_includes_vat",
    "unit_price_kzt",
    "line_total",
    "total_kzt",
    "final_price",
    "client_ready",
    "ready_to_send",
    "send_to_client",
    "commercial_approved",
    "production_approved",
    "production_action_authorized",
    "token_execution_authorized",
    "product_name_guess",
    "product_type_guess",
    "quantity_guess",
    "cabinet_guess",
    "component_code_guess",
    "component_label_guess",
    "install_type_guess",
    "confidence",
    "evidence",
    "requires_igor_confirmation",
}


@dataclass
class ValidationResult:
    input_json: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "JSON readable": "fail",
            "schema constants": "fail",
            "calculator format": "fail",
            "operator completion": "fail",
            "safety boundary": "fail",
            "rows": "fail",
            "forbidden keys": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a completed price-calculator input draft JSON without "
            "executing the calculator."
        )
    )
    parser.add_argument("--input-json", required=True, type=Path)
    return parser.parse_args(argv)


def add_red_flag(result: ValidationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def is_positive_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def require_fields(
    data: Mapping[str, Any],
    fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    for field_name in fields:
        if field_name not in data:
            valid = False
            add_red_flag(
                result,
                f"required field is missing: {field_path(path, field_name)}",
            )
    return valid


def reject_unknown_fields(
    data: Mapping[str, Any],
    allowed_fields: Sequence[str],
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    allowed = set(allowed_fields)
    for field_name in data:
        if field_name not in allowed:
            valid = False
            add_red_flag(
                result,
                f"unknown field is not allowed: {field_path(path, field_name)}",
            )
    return valid


def require_mapping(
    value: Any,
    path: str,
    result: ValidationResult,
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        add_red_flag(result, f"field must be an object: {path}")
        return None
    return cast(Mapping[str, Any], value)


def require_list(value: Any, path: str, result: ValidationResult) -> list[Any] | None:
    if not isinstance(value, list):
        add_red_flag(result, f"field must be a list: {path}")
        return None
    return value


def require_string(value: Any, path: str, result: ValidationResult) -> bool:
    if not is_non_empty_string(value):
        add_red_flag(result, f"field must be a non-empty string: {path}")
        return False
    return True


def require_string_list(value: Any, path: str, result: ValidationResult) -> bool:
    items = require_list(value, path, result)
    if items is None:
        return False
    valid = True
    for index, item in enumerate(items):
        if not is_non_empty_string(item):
            valid = False
            add_red_flag(
                result,
                f"list item must be a non-empty string: {path}[{index}]",
            )
    return valid


def require_positive_number(value: Any, path: str, result: ValidationResult) -> bool:
    if not is_positive_number(value):
        add_red_flag(result, f"field must be a positive number: {path}")
        return False
    return True


def find_forbidden_keys(
    value: Any,
    path: str,
    result: ValidationResult,
) -> bool:
    valid = True
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = field_path(path, key_text)
            if key_text in FORBIDDEN_KEYS:
                valid = False
                add_red_flag(result, f"forbidden key present: {child_path}")
            if not find_forbidden_keys(child, child_path, result):
                valid = False
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if not find_forbidden_keys(child, f"{path}[{index}]", result):
                valid = False
    return valid


def load_json(path: Path, result: ValidationResult) -> Mapping[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "input JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "input JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "input JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "input JSON could not be read")
        return None

    if not isinstance(raw, Mapping):
        add_red_flag(result, "JSON root must be an object")
        return None

    result.checks["JSON readable"] = "pass"
    return cast(Mapping[str, Any], raw)


def validate_schema_constants(
    data: Mapping[str, Any],
    result: ValidationResult,
) -> None:
    valid = True
    if not require_fields(data, ROOT_FIELDS, "", result):
        valid = False
    if not reject_unknown_fields(data, ROOT_FIELDS, "", result):
        valid = False
    if data.get("schema_version") != SCHEMA_VERSION:
        valid = False
        add_red_flag(
            result,
            "schema_version must be price_calculator_input_draft.v0.1",
        )
    if data.get("draft_type") != DRAFT_TYPE:
        valid = False
        add_red_flag(result, "draft_type must be price_calculator_input_draft")
    if "source" in data and require_mapping(data["source"], "source", result) is None:
        valid = False
    if "items" in data:
        items = require_list(data["items"], "items", result)
        if items is None:
            valid = False
        elif not items:
            valid = False
            add_red_flag(result, "items must be a non-empty list")
    if "next_required_human_actions" in data and not require_string_list(
        data["next_required_human_actions"],
        "next_required_human_actions",
        result,
    ):
        valid = False
    result.checks["schema constants"] = "pass" if valid else "fail"


def validate_calculator_format(
    data: Any,
    result: ValidationResult,
) -> Mapping[str, Any] | None:
    calculator_format = require_mapping(data, "calculator_input_format", result)
    if calculator_format is None:
        return None

    valid = True
    if not require_fields(
        calculator_format,
        ("kind", "delimiter", "columns", "rows"),
        "calculator_input_format",
        result,
    ):
        valid = False
    if not reject_unknown_fields(
        calculator_format,
        CALCULATOR_FORMAT_FIELDS,
        "calculator_input_format",
        result,
    ):
        valid = False
    if calculator_format.get("kind") != CALCULATOR_KIND:
        valid = False
        add_red_flag(
            result,
            "calculator_input_format.kind must be confirmed_composition_csv_rows",
        )
    if calculator_format.get("delimiter") != CALCULATOR_DELIMITER:
        valid = False
        add_red_flag(result, "calculator_input_format.delimiter must be ;")
    if calculator_format.get("columns") != list(CALCULATOR_COLUMNS):
        valid = False
        add_red_flag(
            result,
            "calculator_input_format.columns must exactly match the "
            "calculator contract",
        )

    rows = require_list(
        calculator_format.get("rows"),
        "calculator_input_format.rows",
        result,
    )
    if rows is None:
        valid = False
    elif not rows:
        valid = False
        add_red_flag(result, "calculator_input_format.rows must be a non-empty list")

    missing_fields = calculator_format.get("missing_required_fields", [])
    if missing_fields != []:
        valid = False
        add_red_flag(
            result,
            "calculator_input_format.missing_required_fields must be absent or empty",
        )

    result.checks["calculator format"] = "pass" if valid else "fail"
    return calculator_format


def validate_operator_completion(data: Any, result: ValidationResult) -> None:
    completion = require_mapping(data, "operator_completion", result)
    if completion is None:
        return

    valid = True
    if not require_fields(
        completion,
        OPERATOR_COMPLETION_FIELDS,
        "operator_completion",
        result,
    ):
        valid = False
    if not reject_unknown_fields(
        completion,
        OPERATOR_COMPLETION_FIELDS,
        "operator_completion",
        result,
    ):
        valid = False
    for field_name in ("completed_by", "completed_at", "completion_note"):
        if field_name in completion and not require_string(
            completion[field_name],
            field_path("operator_completion", field_name),
            result,
        ):
            valid = False
    if completion.get("consumables_factor_confirmed_by_igor") is not True:
        valid = False
        add_red_flag(
            result,
            "operator_completion.consumables_factor_confirmed_by_igor must be true",
        )
    result.checks["operator completion"] = "pass" if valid else "fail"


def validate_safety(data: Any, result: ValidationResult) -> None:
    safety = require_mapping(data, "safety", result)
    if safety is None:
        return

    valid = True
    if not require_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if not reject_unknown_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if safety.get("status") != "price_calculator_input_draft_only":
        valid = False
        add_red_flag(result, "safety.status must be price_calculator_input_draft_only")
    if safety.get("derived_from_confirmed_composition") is not True:
        valid = False
        add_red_flag(result, "safety.derived_from_confirmed_composition must be true")

    required_false = (
        "price_calculation_executed",
        "price_approved_by_igor",
        "commercial_csv_authorized",
        "client_style_export_authorized",
        "sending_authorized",
        "production_authorized",
    )
    for field_name in required_false:
        value = safety.get(field_name)
        if value is not False:
            valid = False
            add_red_flag(result, f"safety.{field_name} must be false")
        if value is True:
            add_red_flag(result, f"safety authorization is true: safety.{field_name}")

    result.checks["safety boundary"] = "pass" if valid else "fail"


def validate_row(data: Any, path: str, result: ValidationResult) -> bool:
    row = require_mapping(data, path, result)
    if row is None:
        return False

    valid = True
    if tuple(row.keys()) != CALCULATOR_COLUMNS:
        valid = False
        add_red_flag(
            result,
            f"row fields must exactly match calculator columns: {path}",
        )
    for field_name in ("product_name", "cabinet_code", "component_code"):
        if field_name in row and not require_string(
            row[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    if "component_qty" in row and not require_positive_number(
        row["component_qty"],
        field_path(path, "component_qty"),
        result,
    ):
        valid = False
    if "consumables_factor" in row and not require_positive_number(
        row["consumables_factor"],
        field_path(path, "consumables_factor"),
        result,
    ):
        valid = False

    install_type = row.get("install_type")
    if install_type == "manual_review_required":
        valid = False
        add_red_flag(result, f"manual_review_required is not allowed: {path}")
    elif install_type not in INSTALL_TYPES:
        valid = False
        add_red_flag(result, f"install_type is not allowed: {path}")
    return valid


def validate_rows(
    calculator_format: Mapping[str, Any] | None,
    result: ValidationResult,
) -> None:
    if calculator_format is None:
        return

    rows = require_list(
        calculator_format.get("rows"),
        "calculator_input_format.rows",
        result,
    )
    if rows is None:
        return
    if not rows:
        add_red_flag(result, "calculator_input_format.rows must be a non-empty list")
        return

    valid = True
    for index, row in enumerate(rows):
        if not validate_row(row, f"calculator_input_format.rows[{index}]", result):
            valid = False

    result.checks["rows"] = "pass" if valid else "fail"


def validate_v02_additive_envelope(
    data: Mapping[str, Any], result: ValidationResult
) -> bool:
    source = data.get("source")
    metadata = (
        source.get("additive_completed_input_successor")
        if isinstance(source, Mapping)
        else None
    )
    if metadata is None:
        return False
    valid = isinstance(metadata, Mapping)
    if not isinstance(metadata, Mapping):
        add_red_flag(result, "v0.2 additive successor metadata must be an object")
        return True
    expected_metadata = {
        "contract": V02_ADDITIVE_SUCCESSOR_CONTRACT,
        "project_id": "2024/086",
        "parent": V02_ADDITIVE_PARENT,
        "direct_human_decision_inputs": V02_ADDITIVE_DECISION_BINDINGS,
        "append_only": True,
        "scope_expansion": False,
    }
    if metadata != expected_metadata:
        valid = False
        add_red_flag(result, "v0.2 additive successor exact bindings mismatch")
    completion = data.get("completion")
    additive_completion = (
        completion.get("additive_successor")
        if isinstance(completion, Mapping)
        else None
    )
    if additive_completion != {
        "contract": V02_ADDITIVE_SUCCESSOR_CONTRACT,
        "application_status": "NOT_APPLIED",
        "pricing_calculation_executed": False,
        "successor_publication_requires_separate_exact_igor_authorization": True,
    }:
        valid = False
        add_red_flag(result, "v0.2 additive completion envelope mismatch")
    if isinstance(completion, Mapping) and completion.get("scope") != {
        "component_groups": V02_ADDITIVE_EXPECTED_COMPONENT_GROUPS,
        "rows": "112/112",
        "cabinet_groups": "15/15",
        "duplicate_component_membership": 0,
        "duplicate_cabinet_membership": 0,
        "scope_expansion": False,
    }:
        valid = False
        add_red_flag(result, "v0.2 additive completion scope mismatch")
    groups = data.get("cabinet_groups")
    calculator_format = data.get("calculator_input_format")
    rows = (
        calculator_format.get("row_drafts")
        if isinstance(calculator_format, Mapping)
        else None
    )
    expected_values = [
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
    if not (
        isinstance(groups, list)
        and len(groups) == V02_ADDITIVE_EXPECTED_CABINET_GROUPS
        and isinstance(groups[-1], Mapping)
        and groups[-1].get("cabinet_group_id") == "CABINET-GROUP-015"
        and groups[-1].get("product_name") == "ШУ-Т1"
        and groups[-1].get("row_draft_ids")
        == ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"]
    ):
        valid = False
        add_red_flag(result, "v0.2 additive ШУ-Т1 cabinet group mismatch")
    if not (
        isinstance(rows, list)
        and len(rows) == V02_ADDITIVE_EXPECTED_ROWS
        and all(isinstance(row, Mapping) for row in rows[-3:])
        and [row.get("row_id") for row in rows[-3:]]
        == ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"]
        and [row.get("calculator_values") for row in rows[-3:]] == expected_values
        and sum(
            row.get("calculator_values", {}).get("component_code") == "EKF-RT-820"
            for row in rows
            if isinstance(row, Mapping)
        )
        == 1
        and all(
            "TST05" not in str(row.get("calculator_values", {}).get("component_code"))
            for row in rows
            if isinstance(row, Mapping)
        )
    ):
        valid = False
        add_red_flag(result, "v0.2 additive ШУ-Т1 row envelope mismatch")
    if not valid:
        result.checks["schema constants"] = "fail"
    return True


def validate_v02_shu_t2_envelope(
    data: Mapping[str, Any], result: ValidationResult
) -> bool:
    source = data.get("source")
    metadata = (
        source.get("shu_t2_rt820_technical_successor")
        if isinstance(source, Mapping)
        else None
    )
    if metadata is None:
        return False
    valid = isinstance(metadata, Mapping)
    if not isinstance(metadata, Mapping):
        add_red_flag(result, "v0.2 SHU-T2 successor metadata must be an object")
        return True
    projection = metadata.get("technical_projection")
    pricing = metadata.get("rt820_pricing_provenance_only")
    expected_evidence = [
        "COMP-031",
        "COMP-034",
        "COMP-085",
        "COMP-088",
        "COMP-128",
        "COMP-131",
        "COMP-178",
        "COMP-181",
    ]
    if not all(
        (
            metadata.get("contract") == V02_SHU_T2_SUCCESSOR_CONTRACT,
            metadata.get("parent") == V02_SHU_T2_PARENT,
            metadata.get("human_decision") == V02_SHU_T2_DECISION,
            metadata.get("append_only") is True,
            metadata.get("scope_expansion") is False,
            isinstance(projection, Mapping),
            isinstance(projection, Mapping)
            and projection.get("row_ids")
            == ["ROW-DRAFT-0113", "ROW-DRAFT-0114", "ROW-DRAFT-0115", "ROW-DRAFT-0116"],
            isinstance(projection, Mapping) and projection.get("evidence_count") == 8,
            isinstance(projection, Mapping)
            and projection.get("evidence_ids") == expected_evidence,
            isinstance(projection, Mapping)
            and projection.get("outside_cabinet_membership_asserted") is False,
            isinstance(projection, Mapping)
            and projection.get("outside_cabinet_count_transition_asserted") is False,
            isinstance(pricing, Mapping),
            isinstance(pricing, Mapping)
            and pricing.get("source_range") == "КРН!A19:C19",
            isinstance(pricing, Mapping) and pricing.get("material_kzt") == 15000,
            isinstance(pricing, Mapping) and pricing.get("work_kzt") == 900,
            isinstance(pricing, Mapping)
            and pricing.get("pricing_calculation_executed") is False,
            isinstance(pricing, Mapping)
            and pricing.get("generic_work_432_prohibited") is True,
            isinstance(pricing, Mapping)
            and pricing.get("family_fallback_prohibited") is True,
            isinstance(pricing, Mapping)
            and pricing.get("fuzzy_fallback_prohibited") is True,
            isinstance(pricing, Mapping)
            and pricing.get("similar_relay_fallback_prohibited") is True,
        )
    ):
        valid = False
        add_red_flag(result, "v0.2 SHU-T2 successor exact bindings mismatch")
    completion = data.get("completion")
    successor_completion = (
        completion.get("shu_t2_rt820_technical_successor")
        if isinstance(completion, Mapping)
        else None
    )
    if successor_completion != {
        "contract": V02_SHU_T2_SUCCESSOR_CONTRACT,
        "decision_application": "PROJECTED_TO_TECHNICAL_SUCCESSOR_ONLY",
        "pricing_calculation_executed": False,
        "calculator_authorized": False,
        "successor_publication_requires_separate_exact_igor_authorization": True,
    }:
        valid = False
        add_red_flag(result, "v0.2 SHU-T2 completion envelope mismatch")
    if isinstance(completion, Mapping) and completion.get("scope") != {
        "component_groups": V02_SHU_T2_EXPECTED_COMPONENT_GROUPS,
        "rows": "116/116",
        "cabinet_groups": "15/15",
        "duplicate_component_membership": 0,
        "duplicate_cabinet_membership": 0,
        "scope_expansion": False,
    }:
        valid = False
        add_red_flag(result, "v0.2 SHU-T2 completion scope mismatch")
    groups = data.get("cabinet_groups")
    calculator_format = data.get("calculator_input_format")
    rows = (
        calculator_format.get("row_drafts")
        if isinstance(calculator_format, Mapping)
        else None
    )
    expected_rows = [
        {
            "row_id": row_id,
            "cabinet_group_id": "CABINET-GROUP-003",
            "calculator_values": {
                "product_name": "ШУ-Т2",
                "cabinet_code": "CAB-KRN-12",
                "consumables_factor": 1.2,
                "component_code": "EKF-RT-820",
                "component_qty": 1,
                "install_type": "temperature_relay_din_2mod",
            },
            "source_quantity": {
                "decision_id": "IGOR-SHU-T2-RT820-SCOPE-2024-086-001",
                "decision_kind": "DIRECT_PER_CABINET_COMPLETE_SET",
                "technical_position_id": technical_position_id,
                "pricing_position_id": pricing_position_id,
                "section": section,
                "quantity_per_individual_cabinet": 1,
                "physical_multiplicity": 1,
                "applies_once_per_cabinet": True,
                "multiply_by_member_count": False,
                "scope_expansion": False,
            },
            "source_component_evidence_ids": list(evidence_ids),
            "approved_signature": {
                "manufacturer": "EKF",
                "product": "Реле температуры RT-820 EKF PROxima",
                "manufacturer_article": "RT-820",
                "supply_form": (
                    "ONE_TEMPERATURE_RELAY_WITH_ONE_EXTERNAL_TEMPERATURE_SENSOR"
                ),
                "module_width_din": 2,
                "TST05_evidence_included_as_provenance_only": True,
                "TST05_separate_component_row": False,
            },
            "mapping_status": "APPROVED_HUMAN_DECISIONS_APPLIED",
            "component_label": (
                "Реле температуры RT-820 EKF PROxima с внешним датчиком"
            ),
        }
        for (
            row_id,
            technical_position_id,
            pricing_position_id,
            section,
            evidence_ids,
        ) in (
            (
                "ROW-DRAFT-0113",
                "TFE-016",
                "PRICE-POSITION-009",
                "10",
                ("COMP-031", "COMP-034"),
            ),
            (
                "ROW-DRAFT-0114",
                "TFE-041",
                "PRICE-POSITION-023",
                "12",
                ("COMP-085", "COMP-088"),
            ),
            (
                "ROW-DRAFT-0115",
                "TFE-061",
                "PRICE-POSITION-035",
                "14",
                ("COMP-128", "COMP-131"),
            ),
            (
                "ROW-DRAFT-0116",
                "TFE-083",
                "PRICE-POSITION-047",
                "16",
                ("COMP-178", "COMP-181"),
            ),
        )
    ]
    appended_evidence = (
        [
            evidence_id
            for row in rows[-4:]
            for evidence_id in row.get("source_component_evidence_ids", [])
        ]
        if isinstance(rows, list) and all(isinstance(row, Mapping) for row in rows[-4:])
        else []
    )
    if not (
        isinstance(groups, list)
        and len(groups) == V02_SHU_T2_EXPECTED_CABINET_GROUPS
        and isinstance(groups[2], Mapping)
        and groups[2].get("cabinet_group_id") == "CABINET-GROUP-003"
        and groups[2].get("product_name") == "ШУ-Т2"
        and groups[2].get("row_draft_ids")[-4:]
        == ["ROW-DRAFT-0113", "ROW-DRAFT-0114", "ROW-DRAFT-0115", "ROW-DRAFT-0116"]
        and len(groups[2].get("row_draft_ids", [])) == 12
        and isinstance(groups[-1], Mapping)
        and groups[-1].get("cabinet_group_id") == "CABINET-GROUP-015"
        and groups[-1].get("row_draft_ids")
        == ["ROW-DRAFT-0110", "ROW-DRAFT-0111", "ROW-DRAFT-0112"]
    ):
        valid = False
        add_red_flag(result, "v0.2 SHU-T2/SHU-T1 cabinet-group integrity mismatch")
    if not (
        isinstance(rows, list)
        and len(rows) == V02_SHU_T2_EXPECTED_ROWS
        and all(isinstance(row, Mapping) for row in rows[-4:])
        and rows[-4:] == expected_rows
        and appended_evidence == expected_evidence
        and len(appended_evidence) == len(set(appended_evidence)) == 8
        and sum(
            row.get("calculator_values", {}).get("component_code") == "EKF-RT-820"
            for row in rows
            if isinstance(row, Mapping)
        )
        == 5
        and all(
            "TST05"
            not in str(row.get("calculator_values", {}).get("component_code", ""))
            for row in rows
            if isinstance(row, Mapping)
        )
    ):
        valid = False
        add_red_flag(result, "v0.2 SHU-T2 appended-row contract mismatch")
    if not valid:
        result.checks["schema constants"] = "fail"
    return True


def validate_v02_completed_payload(
    data: Mapping[str, Any],
    result: ValidationResult,
) -> None:
    root_fields = {
        "schema_version",
        "draft_type",
        "source",
        "cabinet_groups",
        "calculator_input_format",
        "coverage",
        "safety",
        "next_required_human_actions",
        "completion",
    }
    valid_schema = set(data) == root_fields
    if not valid_schema:
        add_red_flag(result, "v0.2 completed root fields mismatch")
    if data.get("draft_type") != DRAFT_TYPE:
        valid_schema = False
        add_red_flag(result, "draft_type must be price_calculator_input_draft")
    source = data.get("source")
    if not isinstance(source, Mapping):
        valid_schema = False
        add_red_flag(result, "source must be an object")
    completion = data.get("completion")
    if not isinstance(completion, Mapping):
        valid_schema = False
        add_red_flag(result, "completion must be an object for v0.2")
    elif (
        completion.get("status") != V02_COMPLETION_STATUS
        or completion.get("authorization_claim_is_not_human_approval") is not True
    ):
        valid_schema = False
        add_red_flag(result, "v0.2 completion contract mismatch")
    envelope_red_flags_before = len(result.red_flags)
    shu_t2_successor = validate_v02_shu_t2_envelope(data, result)
    additive_successor = (
        False if shu_t2_successor else validate_v02_additive_envelope(data, result)
    )
    if len(result.red_flags) != envelope_red_flags_before:
        valid_schema = False
    result.checks["schema constants"] = "pass" if valid_schema else "fail"

    safety = data.get("safety")
    safety_valid = isinstance(safety, Mapping) and bool(safety)
    if isinstance(safety, Mapping):
        for field_name, value in safety.items():
            if value is not False:
                safety_valid = False
                add_red_flag(result, f"v0.2 safety.{field_name} must be false")
    else:
        add_red_flag(result, "v0.2 safety must be an object")
    result.checks["safety boundary"] = "pass" if safety_valid else "fail"
    result.checks["operator completion"] = "pass"

    calculator_format = data.get("calculator_input_format")
    format_valid = isinstance(calculator_format, Mapping)
    rows: list[Any] | None = None
    if not isinstance(calculator_format, Mapping):
        add_red_flag(result, "v0.2 calculator_input_format must be an object")
    else:
        if (
            calculator_format.get("kind") != "confirmed_composition_csv_row_drafts"
            or calculator_format.get("delimiter") != CALCULATOR_DELIMITER
            or calculator_format.get("columns") != list(CALCULATOR_COLUMNS)
        ):
            format_valid = False
            add_red_flag(result, "v0.2 calculator format constants mismatch")
        rows_value = calculator_format.get("row_drafts")
        if not isinstance(rows_value, list):
            format_valid = False
            add_red_flag(result, "v0.2 row_drafts must be a list")
        else:
            rows = rows_value
    result.checks["calculator format"] = "pass" if format_valid else "fail"

    cabinet_groups = data.get("cabinet_groups")
    expected_groups = (
        V02_SHU_T2_EXPECTED_CABINET_GROUPS
        if shu_t2_successor
        else (
            V02_ADDITIVE_EXPECTED_CABINET_GROUPS
            if additive_successor
            else V02_EXPECTED_CABINET_GROUPS
        )
    )
    expected_rows = (
        V02_SHU_T2_EXPECTED_ROWS
        if shu_t2_successor
        else (V02_ADDITIVE_EXPECTED_ROWS if additive_successor else V02_EXPECTED_ROWS)
    )
    rows_valid = (
        isinstance(cabinet_groups, list)
        and len(cabinet_groups) == expected_groups
        and rows is not None
        and len(rows) == expected_rows
    )
    group_rows: dict[str, set[str]] = {}
    row_ids: set[str] = set()
    if not isinstance(cabinet_groups, list):
        add_red_flag(result, "v0.2 cabinet_groups must be a list")
    else:
        for index, raw_group in enumerate(cabinet_groups):
            path = f"cabinet_groups[{index}]"
            if not isinstance(raw_group, Mapping):
                rows_valid = False
                add_red_flag(result, f"{path} must be an object")
                continue
            group_id = raw_group.get("cabinet_group_id")
            row_draft_ids = raw_group.get("row_draft_ids")
            if (
                not is_non_empty_string(group_id)
                or not isinstance(row_draft_ids, list)
                or not row_draft_ids
                or raw_group.get("mapping_status") != V02_COMPLETED_MAPPING_STATUS
            ):
                rows_valid = False
                add_red_flag(result, f"{path} completion fields mismatch")
                continue
            for field_name in (
                "source_cabinet_template",
                "product_name",
                "cabinet_code",
                "cabinet_label",
            ):
                if not is_non_empty_string(raw_group.get(field_name)):
                    rows_valid = False
                    add_red_flag(result, f"{path}.{field_name} must be non-empty")
            if not is_positive_number(raw_group.get("consumables_factor")):
                rows_valid = False
                add_red_flag(result, f"{path}.consumables_factor must be positive")
            group_id_text = cast(str, group_id)
            if group_id_text in group_rows:
                rows_valid = False
                add_red_flag(result, f"duplicate cabinet_group_id: {group_id_text}")
            elif any(not is_non_empty_string(value) for value in row_draft_ids):
                rows_valid = False
                add_red_flag(result, f"{path}.row_draft_ids is invalid")
            else:
                group_rows[group_id_text] = set(cast(list[str], row_draft_ids))

    if rows is not None:
        for index, raw_row in enumerate(rows):
            path = f"calculator_input_format.row_drafts[{index}]"
            if not isinstance(raw_row, Mapping):
                rows_valid = False
                add_red_flag(result, f"{path} must be an object")
                continue
            row_id = raw_row.get("row_id")
            group_id = raw_row.get("cabinet_group_id")
            values = raw_row.get("calculator_values")
            if (
                not is_non_empty_string(row_id)
                or not is_non_empty_string(group_id)
                or not is_non_empty_string(raw_row.get("component_label"))
                or raw_row.get("mapping_status") != V02_COMPLETED_MAPPING_STATUS
                or not isinstance(values, Mapping)
            ):
                rows_valid = False
                add_red_flag(result, f"{path} completion fields mismatch")
                continue
            row_id_text = cast(str, row_id)
            group_id_text = cast(str, group_id)
            if row_id_text in row_ids:
                rows_valid = False
                add_red_flag(result, f"duplicate row_id: {row_id_text}")
            row_ids.add(row_id_text)
            if row_id_text not in group_rows.get(group_id_text, set()):
                rows_valid = False
                add_red_flag(result, f"{path} cabinet membership mismatch")
            if tuple(values.keys()) != CALCULATOR_COLUMNS:
                rows_valid = False
                add_red_flag(result, f"{path}.calculator_values fields mismatch")
                continue
            for field_name in ("product_name", "cabinet_code", "component_code"):
                if not is_non_empty_string(values.get(field_name)):
                    rows_valid = False
                    add_red_flag(result, f"{path}.{field_name} must be non-empty")
            if not is_positive_number(values.get("consumables_factor")):
                rows_valid = False
                add_red_flag(result, f"{path}.consumables_factor must be positive")
            if not is_positive_number(values.get("component_qty")):
                rows_valid = False
                add_red_flag(result, f"{path}.component_qty must be positive")
            if values.get("install_type") not in INSTALL_TYPES:
                rows_valid = False
                add_red_flag(result, f"{path}.install_type is not allowed")

    if set().union(*group_rows.values()) != row_ids if group_rows else True:
        rows_valid = False
        add_red_flag(result, "v0.2 row/cabinet coverage mismatch")
    coverage = data.get("coverage")
    if not isinstance(coverage, Mapping) or (
        coverage.get("pricing_row_draft_count") != expected_rows
        or coverage.get("cabinet_group_count") != expected_groups
    ):
        rows_valid = False
        add_red_flag(result, "v0.2 coverage fields mismatch")
    result.checks["rows"] = "pass" if rows_valid else "fail"


def validate_completed_price_calculator_input_draft(
    input_json: Path,
) -> ValidationResult:
    result = ValidationResult(input_json=input_json.expanduser().resolve(strict=False))
    data = load_json(result.input_json, result)
    if data is None:
        return result

    forbidden_ok = find_forbidden_keys(data, "", result)
    result.checks["forbidden keys"] = "pass" if forbidden_ok else "fail"
    if data.get("schema_version") == SCHEMA_VERSION_V02:
        validate_v02_completed_payload(data, result)
        all_checks_pass = all(status == "pass" for status in result.checks.values())
        result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
        return result
    validate_schema_constants(data, result)
    calculator_format = validate_calculator_format(
        data.get("calculator_input_format"),
        result,
    )
    validate_operator_completion(data.get("operator_completion"), result)
    validate_safety(data.get("safety"), result)
    validate_rows(calculator_format, result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ValidationResult) -> str:
    lines = [
        REPORT_START,
        "",
        "Status:",
        result.status,
        "",
        "Mode:",
        MODE,
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(["", "Red flags:"])
    lines.extend(format_items(result.red_flags))
    lines.extend(
        [
            "",
            "Commercial status:",
            COMMERCIAL_STATUS,
            "",
            "Human Approval:",
            HUMAN_APPROVAL,
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = validate_completed_price_calculator_input_draft(args.input_json)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
