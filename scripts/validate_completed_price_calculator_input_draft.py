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
}
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


def validate_completed_price_calculator_input_draft(
    input_json: Path,
) -> ValidationResult:
    result = ValidationResult(input_json=input_json.expanduser().resolve(strict=False))
    data = load_json(result.input_json, result)
    if data is None:
        return result

    forbidden_ok = find_forbidden_keys(data, "", result)
    result.checks["forbidden keys"] = "pass" if forbidden_ok else "fail"
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
