"""Validate preliminary switchboard composition drafts without pricing."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

REPORT_START = "PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_START"
REPORT_END = "PRELIMINARY_COMPOSITION_DRAFT_VALIDATION_REPORT_END"
MODE = "preliminary composition draft validation only"
COMMERCIAL_STATUS = "not confirmed composition; not price approval; not client-ready КП"
HUMAN_APPROVAL = "Igor confirmation required before price calculation or commercial CSV"
SCHEMA_VERSION = "preliminary_composition_draft.v0.1"

ROOT_FIELDS = (
    "schema_version",
    "draft_id",
    "created_by",
    "created_at",
    "source",
    "safety",
    "items",
    "overall_confidence",
    "red_flags",
    "assumptions",
    "next_required_human_actions",
)
SOURCE_FIELDS = ("source_type", "source_summary", "raw_input_sha256")
SAFETY_FIELDS = (
    "status",
    "confirmed_by_igor",
    "price_execution_authorized",
    "commercial_csv_authorized",
    "client_style_export_authorized",
    "sending_authorized",
    "production_authorized",
)
ITEM_FIELDS = (
    "item_id",
    "product_name_guess",
    "product_type_guess",
    "quantity_guess",
    "cabinet_guess",
    "components",
    "confidence",
    "evidence",
    "red_flags",
    "assumptions",
    "requires_igor_confirmation",
)
CABINET_FIELDS = (
    "code_guess",
    "label_guess",
    "confidence",
    "evidence",
    "red_flags",
)
COMPONENT_FIELDS = (
    "component_id",
    "component_code_guess",
    "component_label_guess",
    "quantity_guess",
    "install_type_guess",
    "confidence",
    "evidence",
    "red_flags",
    "assumptions",
    "requires_igor_confirmation",
)
SOURCE_TYPES = {
    "text_request",
    "project_fragment",
    "specification",
    "manual_transcription",
    "other",
}
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
    "manual_review_required",
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
    "confirmed_composition",
    "production_action_authorized",
    "token_execution_authorized",
}
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass
class ValidationResult:
    input_json: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "JSON readable": "fail",
            "schema constants": "fail",
            "source": "fail",
            "safety boundary": "fail",
            "items": "fail",
            "forbidden keys": "fail",
            "confidence/evidence": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a preliminary composition draft JSON."
    )
    parser.add_argument("--input-json", required=True, type=Path)
    return parser.parse_args(argv)


def add_red_flag(result: ValidationResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


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


def require_optional_string(value: Any, path: str, result: ValidationResult) -> bool:
    if value is None:
        return True
    if not is_non_empty_string(value):
        add_red_flag(result, f"field must be a non-empty string or null: {path}")
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


def require_non_empty_string_list(
    value: Any,
    path: str,
    result: ValidationResult,
) -> bool:
    items = require_list(value, path, result)
    if items is None:
        return False
    if not items:
        add_red_flag(result, f"field must be a non-empty list: {path}")
        return False
    return require_string_list(value, path, result)


def require_positive_integer(value: Any, path: str, result: ValidationResult) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        add_red_flag(result, f"field must be a positive integer: {path}")
        return False
    return True


def require_positive_number(value: Any, path: str, result: ValidationResult) -> bool:
    if not is_number(value) or value <= 0:
        add_red_flag(result, f"field must be a positive number: {path}")
        return False
    return True


def require_confidence(
    value: Any,
    path: str,
    result: ValidationResult,
) -> bool:
    if not is_number(value) or not 0 <= value <= 1:
        add_red_flag(result, f"confidence must be a number from 0 to 1: {path}")
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
            "schema_version must be preliminary_composition_draft.v0.1",
        )
    for field_name in ("draft_id", "created_by", "created_at"):
        if field_name in data and not require_string(
            data[field_name],
            field_name,
            result,
        ):
            valid = False
    if "overall_confidence" in data and not require_confidence(
        data["overall_confidence"],
        "overall_confidence",
        result,
    ):
        valid = False
    if "red_flags" in data and not require_string_list(
        data["red_flags"],
        "red_flags",
        result,
    ):
        valid = False
    if "assumptions" in data and not require_string_list(
        data["assumptions"],
        "assumptions",
        result,
    ):
        valid = False
    if "next_required_human_actions" in data and not require_non_empty_string_list(
        data["next_required_human_actions"],
        "next_required_human_actions",
        result,
    ):
        valid = False
    result.checks["schema constants"] = "pass" if valid else "fail"


def validate_source(data: Any, result: ValidationResult) -> None:
    source = require_mapping(data, "source", result)
    if source is None:
        return

    valid = True
    if not require_fields(source, SOURCE_FIELDS, "source", result):
        valid = False
    if not reject_unknown_fields(source, SOURCE_FIELDS, "source", result):
        valid = False

    source_type = source.get("source_type")
    if source_type not in SOURCE_TYPES:
        valid = False
        add_red_flag(result, "source.source_type is not allowed")
    if "source_summary" in source and not require_string(
        source["source_summary"],
        "source.source_summary",
        result,
    ):
        valid = False

    raw_input_sha256 = source.get("raw_input_sha256")
    if (
        not isinstance(raw_input_sha256, str)
        or HASH_RE.fullmatch(raw_input_sha256) is None
    ):
        valid = False
        add_red_flag(
            result,
            "source.raw_input_sha256 must be 64 lowercase hex characters",
        )

    result.checks["source"] = "pass" if valid else "fail"


def validate_safety(data: Any, result: ValidationResult) -> None:
    safety = require_mapping(data, "safety", result)
    if safety is None:
        return

    valid = True
    if not require_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if not reject_unknown_fields(safety, SAFETY_FIELDS, "safety", result):
        valid = False
    if safety.get("status") != "preliminary_only":
        valid = False
        add_red_flag(result, "safety.status must be preliminary_only")

    required_false = SAFETY_FIELDS[1:]
    for field_name in required_false:
        value = safety.get(field_name)
        if value is not False:
            valid = False
            add_red_flag(result, f"safety.{field_name} must be false")
        if value is True:
            add_red_flag(result, f"safety authorization is true: safety.{field_name}")

    result.checks["safety boundary"] = "pass" if valid else "fail"


def validate_cabinet(data: Any, path: str, result: ValidationResult) -> bool:
    cabinet = require_mapping(data, path, result)
    if cabinet is None:
        return False

    valid = True
    if not require_fields(cabinet, CABINET_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(cabinet, CABINET_FIELDS, path, result):
        valid = False
    for field_name in ("code_guess", "label_guess"):
        if field_name in cabinet and not require_optional_string(
            cabinet[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    if "confidence" in cabinet and not require_confidence(
        cabinet["confidence"],
        field_path(path, "confidence"),
        result,
    ):
        valid = False
    if "evidence" in cabinet and not require_non_empty_string_list(
        cabinet["evidence"],
        field_path(path, "evidence"),
        result,
    ):
        valid = False
    if "red_flags" in cabinet and not require_string_list(
        cabinet["red_flags"],
        field_path(path, "red_flags"),
        result,
    ):
        valid = False
    return valid


def validate_component(data: Any, path: str, result: ValidationResult) -> bool:
    component = require_mapping(data, path, result)
    if component is None:
        return False

    valid = True
    if not require_fields(component, COMPONENT_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(component, COMPONENT_FIELDS, path, result):
        valid = False
    if "component_id" in component and not require_string(
        component["component_id"],
        field_path(path, "component_id"),
        result,
    ):
        valid = False
    if "component_code_guess" in component and not require_optional_string(
        component["component_code_guess"],
        field_path(path, "component_code_guess"),
        result,
    ):
        valid = False
    if "component_label_guess" in component and not require_string(
        component["component_label_guess"],
        field_path(path, "component_label_guess"),
        result,
    ):
        valid = False
    if "quantity_guess" in component and not require_positive_number(
        component["quantity_guess"],
        field_path(path, "quantity_guess"),
        result,
    ):
        valid = False

    install_type = component.get("install_type_guess")
    if install_type is not None and install_type not in INSTALL_TYPES:
        valid = False
        add_red_flag(result, f"install_type_guess is not allowed: {path}")
    if "confidence" in component and not require_confidence(
        component["confidence"],
        field_path(path, "confidence"),
        result,
    ):
        valid = False
    if "evidence" in component and not require_non_empty_string_list(
        component["evidence"],
        field_path(path, "evidence"),
        result,
    ):
        valid = False
    if "red_flags" in component and not require_string_list(
        component["red_flags"],
        field_path(path, "red_flags"),
        result,
    ):
        valid = False
    if "assumptions" in component and not require_string_list(
        component["assumptions"],
        field_path(path, "assumptions"),
        result,
    ):
        valid = False
    if component.get("requires_igor_confirmation") is not True:
        valid = False
        add_red_flag(
            result,
            f"requires_igor_confirmation must be true: {path}",
        )
    return valid


def validate_item(data: Any, path: str, result: ValidationResult) -> bool:
    item = require_mapping(data, path, result)
    if item is None:
        return False

    valid = True
    if not require_fields(item, ITEM_FIELDS, path, result):
        valid = False
    if not reject_unknown_fields(item, ITEM_FIELDS, path, result):
        valid = False
    for field_name in ("item_id", "product_name_guess", "product_type_guess"):
        if field_name in item and not require_string(
            item[field_name],
            field_path(path, field_name),
            result,
        ):
            valid = False
    if "quantity_guess" in item and not require_positive_integer(
        item["quantity_guess"],
        field_path(path, "quantity_guess"),
        result,
    ):
        valid = False
    if "cabinet_guess" in item and not validate_cabinet(
        item["cabinet_guess"],
        field_path(path, "cabinet_guess"),
        result,
    ):
        valid = False

    components = item.get("components")
    component_list = require_list(components, field_path(path, "components"), result)
    if component_list is None:
        valid = False
    elif not component_list:
        valid = False
        add_red_flag(result, f"field must be a non-empty list: {path}.components")
    else:
        for index, component in enumerate(component_list):
            if not validate_component(component, f"{path}.components[{index}]", result):
                valid = False

    if "confidence" in item and not require_confidence(
        item["confidence"],
        field_path(path, "confidence"),
        result,
    ):
        valid = False
    if "evidence" in item and not require_non_empty_string_list(
        item["evidence"],
        field_path(path, "evidence"),
        result,
    ):
        valid = False
    if "red_flags" in item and not require_string_list(
        item["red_flags"],
        field_path(path, "red_flags"),
        result,
    ):
        valid = False
    if "assumptions" in item and not require_string_list(
        item["assumptions"],
        field_path(path, "assumptions"),
        result,
    ):
        valid = False
    if item.get("requires_igor_confirmation") is not True:
        valid = False
        add_red_flag(
            result,
            f"requires_igor_confirmation must be true: {path}",
        )
    return valid


def validate_items(data: Any, result: ValidationResult) -> None:
    item_list = require_list(data, "items", result)
    if item_list is None:
        return
    if not item_list:
        add_red_flag(result, "items must be a non-empty list")
        return

    valid = True
    for index, item in enumerate(item_list):
        if not validate_item(item, f"items[{index}]", result):
            valid = False

    result.checks["items"] = "pass" if valid else "fail"


def set_confidence_evidence_check(result: ValidationResult) -> None:
    schema_ok = result.checks["schema constants"] == "pass"
    item_ok = result.checks["items"] == "pass"
    result.checks["confidence/evidence"] = "pass" if schema_ok and item_ok else "fail"


def validate_preliminary_composition_draft(input_json: Path) -> ValidationResult:
    result = ValidationResult(input_json=input_json.expanduser().resolve(strict=False))
    data = load_json(result.input_json, result)
    if data is None:
        return result

    forbidden_ok = find_forbidden_keys(data, "", result)
    result.checks["forbidden keys"] = "pass" if forbidden_ok else "fail"
    validate_schema_constants(data, result)
    validate_source(data.get("source"), result)
    validate_safety(data.get("safety"), result)
    validate_items(data.get("items"), result)
    set_confidence_evidence_check(result)

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
    result = validate_preliminary_composition_draft(args.input_json)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
