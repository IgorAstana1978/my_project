"""Build a price-calculator input draft from a confirmed composition artifact."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_confirmed_composition_artifact.py")

REPORT_START = "PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_START"
REPORT_END = "PRICE_CALCULATOR_INPUT_DRAFT_BUILD_REPORT_END"
MODE = "price calculator input draft build only"
COMMERCIAL_STATUS = (
    "calculator input draft only; no price calculated; not price approval; "
    "not commercial CSV; not client-ready КП"
)
HUMAN_APPROVAL = (
    "Igor approval still required before price result, commercial CSV, КП "
    "sending or production"
)

CSV_DELIMITER = ";"
CALCULATOR_COLUMNS = (
    "product_name",
    "cabinet_code",
    "consumables_factor",
    "component_code",
    "component_qty",
    "install_type",
)
FORBIDDEN_OUTPUT_KEYS = {
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
class BuildResult:
    confirmed_composition_json: Path
    output_json: Path
    status: str = "FAIL"
    output_created: bool = False
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "confirmed composition validation": "fail",
            "output policy": "fail",
            "draft read": "fail",
            "mapping": "fail",
            "draft write": "fail",
            "safety boundary": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a JSON price-calculator input draft from a confirmed "
            "composition artifact without calculating price."
        )
    )
    parser.add_argument("--confirmed-composition-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: BuildResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_confirmed_composition_artifact_for_input_draft",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("confirmed composition validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_confirmed_composition_validation(result: BuildResult) -> bool:
    validator = load_validator_module()
    validation = validator.validate_confirmed_composition_artifact(
        result.confirmed_composition_json
    )

    if validation.status == "PASS":
        result.checks["confirmed composition validation"] = "pass"
        result.checks["safety boundary"] = "pass"
        return True

    add_red_flag(result, "confirmed composition validation failed")
    for red_flag in validation.red_flags:
        add_red_flag(result, f"confirmed composition: {red_flag}")
    if validation.checks.get("safety boundary") == "pass":
        result.checks["safety boundary"] = "pass"
    return False


def validate_output_policy(result: BuildResult) -> bool:
    valid = True
    output = result.output_json

    if output.exists():
        valid = False
        add_red_flag(result, "output JSON already exists")
    if is_inside_project(output):
        valid = False
        add_red_flag(result, "output JSON must be outside the project")
    if not output.parent.is_dir():
        valid = False
        add_red_flag(result, "output parent directory does not exist")

    result.checks["output policy"] = "pass" if valid else "fail"
    return valid


def load_confirmed_composition(
    path: Path,
    result: BuildResult,
) -> Mapping[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "confirmed composition JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "confirmed composition JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "confirmed composition JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "confirmed composition JSON could not be read")
        return None

    if not isinstance(data, Mapping):
        add_red_flag(result, "confirmed composition JSON root must be an object")
        return None

    result.checks["draft read"] = "pass"
    return cast(Mapping[str, Any], data)


def as_mapping(value: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value if isinstance(value, Mapping) else {})


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def find_forbidden_output_keys(value: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_OUTPUT_KEYS:
                findings.append(child_path)
            findings.extend(find_forbidden_output_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_forbidden_output_keys(child, f"{path}[{index}]"))
    return findings


def build_calculator_rows(
    data: Mapping[str, Any],
    result: BuildResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in as_list(data.get("items")):
        item_map = as_mapping(item)
        cabinet = as_mapping(item_map.get("cabinet"))
        for component in as_list(item_map.get("components")):
            component_map = as_mapping(component)
            rows.append(
                {
                    "product_name": item_map.get("product_name"),
                    "cabinet_code": cabinet.get("cabinet_code"),
                    "consumables_factor": None,
                    "component_code": component_map.get("component_code"),
                    "component_qty": component_map.get("quantity"),
                    "install_type": component_map.get("install_type"),
                }
            )

    if not rows:
        add_red_flag(result, "no calculator input rows could be mapped")
        return []
    return rows


def build_output_payload(
    data: Mapping[str, Any],
    result: BuildResult,
) -> Mapping[str, Any] | None:
    rows = build_calculator_rows(data, result)
    if not rows:
        return None

    payload: dict[str, Any] = {
        "schema_version": "price_calculator_input_draft.v0.1",
        "draft_type": "price_calculator_input_draft",
        "source": {
            "confirmation_id": data.get("confirmation_id"),
            "confirmed_by": data.get("confirmed_by"),
            "confirmed_at": data.get("confirmed_at"),
            "source_links": data.get("source_links"),
        },
        "calculator_input_format": {
            "kind": "confirmed_composition_csv_rows",
            "delimiter": CSV_DELIMITER,
            "columns": list(CALCULATOR_COLUMNS),
            "rows": rows,
            "missing_required_fields": ["consumables_factor"],
            "missing_required_fields_note": (
                "consumables_factor is required by the existing calculator CSV "
                "contract and must be supplied or confirmed by Igor before a "
                "future calculator run."
            ),
        },
        "items": [
            {
                "item_id": item_map.get("item_id"),
                "product_name": item_map.get("product_name"),
                "product_type": item_map.get("product_type"),
                "quantity": item_map.get("quantity"),
                "cabinet": item_map.get("cabinet"),
                "components": item_map.get("components"),
            }
            for item_map in (as_mapping(item) for item in as_list(data.get("items")))
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
            "Igor confirms consumables_factor before any calculator run.",
            "Igor reviews any future price result before commercial CSV or КП.",
        ],
    }

    forbidden_paths = find_forbidden_output_keys(payload)
    if forbidden_paths:
        add_red_flag(
            result,
            "output draft contains forbidden keys: " + ", ".join(forbidden_paths),
        )
        return None

    result.checks["mapping"] = "pass"
    return payload


def write_output_json(
    path: Path,
    payload: Mapping[str, Any],
    result: BuildResult,
) -> bool:
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        add_red_flag(result, "output JSON could not be written")
        return False

    result.output_created = True
    result.checks["draft write"] = "pass"
    return True


def build_price_calculator_input_draft(
    confirmed_composition_json: Path,
    output_json: Path,
) -> BuildResult:
    result = BuildResult(
        confirmed_composition_json=resolved(confirmed_composition_json),
        output_json=resolved(output_json),
    )

    if not run_confirmed_composition_validation(result):
        return result
    if not validate_output_policy(result):
        return result
    data = load_confirmed_composition(result.confirmed_composition_json, result)
    if data is None:
        return result
    payload = build_output_payload(data, result)
    if payload is None:
        return result
    write_output_json(result.output_json, payload, result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: BuildResult) -> str:
    output_text = str(result.output_json) if result.output_created else "not created"
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
            "Output:",
            output_text,
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
    result = build_price_calculator_input_draft(
        args.confirmed_composition_json,
        args.output_json,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
