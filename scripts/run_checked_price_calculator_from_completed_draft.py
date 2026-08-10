"""Run the read-only price calculator from a validated completed draft."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name(
    "validate_completed_price_calculator_input_draft.py"
)
CALCULATOR_PATH = Path(__file__).with_name("calc_quote_price_draft.py")
CUSTOM_SCHE_RESOLVER_PATH = Path(__file__).with_name(
    "resolve_custom_sche_cabinet_base_cost.py"
)

REPORT_START = "CHECKED_PRICE_CALCULATOR_RUN_REPORT_START"
REPORT_END = "CHECKED_PRICE_CALCULATOR_RUN_REPORT_END"
MODE = "checked read-only price calculator run from completed draft"
COMMERCIAL_STATUS = (
    "draft price calculation only; not price approval; not commercial CSV; "
    "not client-ready КП"
)
HUMAN_APPROVAL = (
    "Igor approval required before commercial CSV, КП sending or production"
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
TECHNICAL_CALCULATOR_COLUMNS = CALCULATOR_COLUMNS + (
    "component_label",
    "cabinet_label",
)
V02_SCHEMA_VERSION = "price_calculator_input_draft.v0.2"
CUSTOM_SCHE_CABINET_CODE = "CAB-SCHE-BI-900X900X120-M12"
CUSTOM_SCHE_PRODUCT_NAMES = ("ЩЭ-3кв", "ЩЭ-4кв", "ЩЭ-5кв", "ЩЭ-6кв")
CUSTOM_SCHE_CABINET_LABEL = "Встроенный ЩЭ, 900×900×120 мм, металл 1.2 мм"
CALCULATOR_SUMMARY_KEYS = (
    "Status",
    "Mode",
    "Input rows count",
    "Cabinet",
    "Cabinet price",
    "Component material total",
    "Work total",
    "Additional materials total",
    "Consumables factor",
    "Base",
    "Total preliminary price",
    "Red flags",
    "Commercial status",
    "Human Approval",
)


@dataclass
class CalculatorProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ItemCalculatorInput:
    product_name: str
    cabinet_code: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class ItemCalculationSummary:
    product_name: str
    input_rows_count: int
    cabinet: str
    cabinet_price: str
    component_material_total: str
    work_total: str
    additional_materials_total: str
    total_preliminary_price: int


@dataclass
class CheckedRunResult:
    completed_input_json: Path
    price_workbook: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "completed input validation": "fail",
            "CSV bridge": "fail",
            "custom ЩЭ resolver": "pass",
            "calculator execution": "fail",
            "temp cleanup": "pass",
            "safety boundary": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)
    calculator_returncode: int | None = None
    calculator_stdout: str = ""
    calculator_stderr: str = ""
    temp_csv_path: Path | None = None
    temp_csv_deleted: bool = True
    temp_csv_paths: list[Path] = field(default_factory=list)
    calculator_runs: list[CalculatorProcessResult] = field(default_factory=list)
    item_summaries: list[ItemCalculationSummary] = field(default_factory=list)
    overall_preliminary_total: int | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a completed price-calculator input draft, bridge it to "
            "the existing CSV contract, and run the read-only calculator."
        )
    )
    parser.add_argument("--completed-input-json", required=True, type=Path)
    parser.add_argument("--price-workbook", required=True, type=Path)
    parser.add_argument("--custom-sche-metal-workbook", type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: CheckedRunResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_completed_price_calculator_input_draft_for_checked_runner",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("completed input validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_completed_input_validation(result: CheckedRunResult) -> bool:
    validator = load_validator_module()
    validation = validator.validate_completed_price_calculator_input_draft(
        result.completed_input_json
    )

    if validation.status == "PASS":
        result.checks["completed input validation"] = "pass"
        if validation.checks.get("safety boundary") == "pass":
            result.checks["safety boundary"] = "pass"
        return True

    add_red_flag(result, "completed input validation failed")
    for red_flag in validation.red_flags:
        add_red_flag(result, f"completed input: {red_flag}")
    if validation.checks.get("safety boundary") == "pass":
        result.checks["safety boundary"] = "pass"
    return False


def load_completed_input_json(result: CheckedRunResult) -> Mapping[str, Any] | None:
    try:
        data = json.loads(result.completed_input_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "completed input JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "completed input JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "completed input JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "completed input JSON could not be read")
        return None

    if not isinstance(data, Mapping):
        add_red_flag(result, "completed input JSON root must be an object")
        return None
    return cast(Mapping[str, Any], data)


def string_for_csv(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def split_item_inputs(
    data: Mapping[str, Any],
    result: CheckedRunResult,
) -> list[ItemCalculatorInput]:
    calculator_format = data.get("calculator_input_format")
    items = data.get("items")
    if not isinstance(calculator_format, Mapping):
        add_red_flag(result, "calculator_input_format must be an object")
        return []
    if calculator_format.get("columns") != list(CALCULATOR_COLUMNS):
        add_red_flag(result, "calculator columns do not match calculator contract")
        return []
    rows = calculator_format.get("rows")
    if not isinstance(rows, list) or not rows:
        add_red_flag(result, "calculator rows must be a non-empty list")
        return []
    if not isinstance(items, list) or not items:
        add_red_flag(result, "items must be a non-empty list")
        return []
    if any(not isinstance(row, Mapping) for row in rows):
        add_red_flag(result, "calculator rows must contain only objects")
        return []

    item_inputs: list[ItemCalculatorInput] = []
    used_row_indexes: set[int] = set()
    item_keys: set[tuple[str, str]] = set()
    for item_index, item_value in enumerate(items):
        if not isinstance(item_value, Mapping):
            add_red_flag(result, f"item must be an object: items[{item_index}]")
            return []
        product_name = item_value.get("product_name")
        cabinet = item_value.get("cabinet")
        components = item_value.get("components")
        if not isinstance(product_name, str) or not isinstance(cabinet, Mapping):
            add_red_flag(result, f"item identity is incomplete: items[{item_index}]")
            return []
        cabinet_code = cabinet.get("cabinet_code")
        cabinet_label = cabinet.get("cabinet_label")
        if not isinstance(cabinet_code, str) or not isinstance(cabinet_label, str):
            add_red_flag(result, f"item cabinet is incomplete: items[{item_index}]")
            return []
        if not isinstance(components, list) or not components:
            add_red_flag(result, f"item components are empty: items[{item_index}]")
            return []

        item_key = (product_name, cabinet_code)
        if item_key in item_keys:
            add_red_flag(
                result,
                f"ambiguous item routing for product/cabinet: "
                f"{product_name} / {cabinet_code}; ask Igor",
            )
            return []
        item_keys.add(item_key)
        matching_rows = [
            (row_index, cast(Mapping[str, Any], row))
            for row_index, row in enumerate(rows)
            if cast(Mapping[str, Any], row).get("product_name") == product_name
            and cast(Mapping[str, Any], row).get("cabinet_code") == cabinet_code
        ]
        if len(matching_rows) != len(components):
            add_red_flag(
                result,
                f"item row/component count mismatch for {product_name}: "
                f"{len(matching_rows)} rows / {len(components)} components",
            )
            return []

        enhanced_rows: list[dict[str, Any]] = []
        for component_index, ((row_index, row), component) in enumerate(
            zip(matching_rows, components, strict=True)
        ):
            if not isinstance(component, Mapping):
                add_red_flag(
                    result,
                    f"component must be an object: items[{item_index}].components"
                    f"[{component_index}]",
                )
                return []
            component_label = component.get("component_label")
            expected_values = (
                component.get("component_code"),
                component.get("quantity"),
                component.get("install_type"),
            )
            row_values = (
                row.get("component_code"),
                row.get("component_qty"),
                row.get("install_type"),
            )
            if not isinstance(component_label, str) or row_values != expected_values:
                add_red_flag(
                    result,
                    f"item component audit mismatch for {product_name} at "
                    f"component {component_index + 1}",
                )
                return []
            enhanced = {column: row[column] for column in CALCULATOR_COLUMNS}
            enhanced["component_label"] = component_label
            enhanced["cabinet_label"] = cabinet_label
            enhanced_rows.append(enhanced)
            used_row_indexes.add(row_index)

        item_inputs.append(
            ItemCalculatorInput(
                product_name=product_name,
                cabinet_code=cabinet_code,
                rows=enhanced_rows,
            )
        )

    if used_row_indexes != set(range(len(rows))):
        add_red_flag(result, "calculator rows are not assigned to exactly one item")
        return []
    return item_inputs


def split_v02_item_inputs(
    data: Mapping[str, Any],
    result: CheckedRunResult,
) -> list[ItemCalculatorInput]:
    calculator_format = data.get("calculator_input_format")
    cabinet_groups = data.get("cabinet_groups")
    if not isinstance(calculator_format, Mapping) or not isinstance(
        cabinet_groups, list
    ):
        add_red_flag(result, "v0.2 calculator/cabinet groups are invalid")
        return []
    if calculator_format.get("columns") != list(CALCULATOR_COLUMNS):
        add_red_flag(result, "calculator columns do not match calculator contract")
        return []
    row_drafts = calculator_format.get("row_drafts")
    if not isinstance(row_drafts, list) or not row_drafts:
        add_red_flag(result, "v0.2 row_drafts must be a non-empty list")
        return []

    row_index: dict[str, Mapping[str, Any]] = {}
    for raw_row in row_drafts:
        if not isinstance(raw_row, Mapping):
            add_red_flag(result, "v0.2 row draft must be an object")
            return []
        row_id = raw_row.get("row_id")
        if not isinstance(row_id, str) or row_id in row_index:
            add_red_flag(result, "v0.2 row draft IDs must be unique strings")
            return []
        row_index[row_id] = cast(Mapping[str, Any], raw_row)

    item_inputs: list[ItemCalculatorInput] = []
    used_rows: set[str] = set()
    group_ids: set[str] = set()
    for raw_group in cabinet_groups:
        if not isinstance(raw_group, Mapping):
            add_red_flag(result, "v0.2 cabinet group must be an object")
            return []
        group_id = raw_group.get("cabinet_group_id")
        product_name = raw_group.get("product_name")
        cabinet_code = raw_group.get("cabinet_code")
        cabinet_label = raw_group.get("cabinet_label")
        row_ids = raw_group.get("row_draft_ids")
        if (
            not isinstance(group_id, str)
            or group_id in group_ids
            or not isinstance(product_name, str)
            or not isinstance(cabinet_code, str)
            or not isinstance(cabinet_label, str)
            or not isinstance(row_ids, list)
            or not row_ids
        ):
            add_red_flag(result, "v0.2 cabinet group identity is invalid")
            return []
        group_ids.add(group_id)
        if cabinet_code == CUSTOM_SCHE_CABINET_CODE and (
            product_name not in CUSTOM_SCHE_PRODUCT_NAMES
            or cabinet_label != CUSTOM_SCHE_CABINET_LABEL
            or raw_group.get("consumables_factor") != 1.2
        ):
            add_red_flag(result, f"custom ЩЭ identity mismatch for {group_id}")
            return []

        enhanced_rows: list[dict[str, Any]] = []
        for raw_row_id in row_ids:
            if not isinstance(raw_row_id, str) or raw_row_id in used_rows:
                add_red_flag(result, f"v0.2 duplicate row membership for {group_id}")
                return []
            row = row_index.get(raw_row_id)
            if row is None or row.get("cabinet_group_id") != group_id:
                add_red_flag(result, f"v0.2 row routing mismatch for {raw_row_id}")
                return []
            values = row.get("calculator_values")
            component_label = row.get("component_label")
            if not isinstance(values, Mapping) or not isinstance(component_label, str):
                add_red_flag(result, f"v0.2 row completion mismatch for {raw_row_id}")
                return []
            try:
                enhanced = {column: values[column] for column in CALCULATOR_COLUMNS}
            except KeyError as exc:
                add_red_flag(result, f"v0.2 row is missing column: {exc.args[0]}")
                return []
            if (
                enhanced["product_name"] != product_name
                or enhanced["cabinet_code"] != cabinet_code
                or enhanced["consumables_factor"] != raw_group.get("consumables_factor")
            ):
                add_red_flag(result, f"v0.2 row/group audit mismatch for {raw_row_id}")
                return []
            enhanced["component_label"] = component_label
            enhanced["cabinet_label"] = cabinet_label
            enhanced_rows.append(enhanced)
            used_rows.add(raw_row_id)
        item_inputs.append(
            ItemCalculatorInput(
                product_name=product_name,
                cabinet_code=cabinet_code,
                rows=enhanced_rows,
            )
        )
    if used_rows != set(row_index):
        add_red_flag(result, "v0.2 rows are not assigned to exactly one cabinet group")
        return []
    return item_inputs


def create_csv_bridge(
    item_input: ItemCalculatorInput,
    result: CheckedRunResult,
) -> Path | None:
    temp_handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix="checked_price_calculator_",
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    if result.temp_csv_path is None:
        result.temp_csv_path = temp_path
    result.temp_csv_paths.append(temp_path)
    result.temp_csv_deleted = False

    try:
        if is_inside_project(temp_path):
            add_red_flag(result, "temporary CSV bridge must be outside the project")
            return None

        with temp_handle:
            writer = csv.writer(
                temp_handle,
                delimiter=CSV_DELIMITER,
                lineterminator="\n",
            )
            writer.writerow(TECHNICAL_CALCULATOR_COLUMNS)
            for row in item_input.rows:
                writer.writerow(
                    [
                        string_for_csv(row[column])
                        for column in TECHNICAL_CALCULATOR_COLUMNS
                    ]
                )
    except OSError:
        add_red_flag(result, "temporary CSV bridge could not be written")
        return None
    except KeyError as exc:
        add_red_flag(result, f"calculator row is missing column: {exc.args[0]}")
        return None

    return temp_path


def load_custom_sche_resolver_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "resolve_custom_sche_cabinet_base_cost_for_checked_runner",
        CUSTOM_SCHE_RESOLVER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("custom ЩЭ resolver could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def resolve_custom_sche_base_cost(metal_workbook: Path) -> int:
    resolver = load_custom_sche_resolver_module()
    resolution = resolver.resolve_custom_sche_cabinet_base_cost(
        metal_workbook_path=resolved(metal_workbook),
        expected_workbook_sha256=resolver.APPROVED_WORKBOOK_SHA256,
        internal_cabinet_code=resolver.APPROVED_INTERNAL_CABINET_CODE,
        metal_thickness=str(resolver.APPROVED_METAL_THICKNESS),
        expected_sheet=resolver.APPROVED_SHEET,
        expected_row=resolver.APPROVED_ROW,
    )
    if resolution.get("status") != "CUSTOM_SCHE_BASE_COST_RESOLUTION_VALIDATED":
        raise RuntimeError("custom ЩЭ resolver failed closed")
    base_cost = resolution.get("base_cost")
    if not isinstance(base_cost, Mapping):
        raise RuntimeError("custom ЩЭ resolver base_cost is missing")
    value = base_cost.get("value")
    if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
        raise RuntimeError("custom ЩЭ resolver base_cost is invalid")
    return int(value)


def run_calculator_cli(
    price_workbook: Path,
    input_csv: Path,
    custom_cabinet_base_cost: int | None = None,
) -> CalculatorProcessResult:
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        str(CALCULATOR_PATH),
        "--price-workbook",
        str(price_workbook),
        "--input-csv",
        str(input_csv),
    ]
    if custom_cabinet_base_cost is not None:
        command.extend(["--custom-cabinet-base-cost", str(custom_cabinet_base_cost)])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=child_env,
        check=False,
    )
    return CalculatorProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def parse_calculator_fields(stdout: str) -> dict[str, str]:
    lines = stdout.splitlines()
    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        key = line.removesuffix(":")
        if key in CALCULATOR_SUMMARY_KEYS and index + 1 < len(lines):
            fields[key] = lines[index + 1]
    return fields


def parse_report_integer(value: str) -> int | None:
    compact = value.replace(" ", "")
    return int(compact) if compact.isdigit() else None


def parse_calculator_red_flags(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    try:
        start = lines.index("Red flags:") + 1
    except ValueError:
        return []

    red_flags: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        if line.strip().casefold() != "none":
            red_flags.append(line)
    return red_flags


def execute_calculator(
    result: CheckedRunResult,
    item_input: ItemCalculatorInput,
    input_csv: Path,
    custom_cabinet_base_cost: int | None = None,
) -> bool:
    try:
        process_result = (
            run_calculator_cli(result.price_workbook, input_csv)
            if custom_cabinet_base_cost is None
            else run_calculator_cli(
                result.price_workbook,
                input_csv,
                custom_cabinet_base_cost=custom_cabinet_base_cost,
            )
        )
    except OSError:
        add_red_flag(result, "calculator invocation failed")
        return False

    result.calculator_runs.append(process_result)
    result.calculator_returncode = process_result.returncode
    result.calculator_stdout = process_result.stdout
    result.calculator_stderr = process_result.stderr
    if process_result.returncode != 0:
        add_red_flag(
            result,
            f"calculator returned non-zero exit code for {item_input.product_name}: "
            f"{process_result.returncode}",
        )
        for red_flag in parse_calculator_red_flags(process_result.stdout):
            add_red_flag(result, f"calculator: {red_flag}")
        return False

    fields = parse_calculator_fields(process_result.stdout)
    required_fields = (
        "Status",
        "Input rows count",
        "Cabinet",
        "Cabinet price",
        "Component material total",
        "Work total",
        "Additional materials total",
        "Total preliminary price",
    )
    missing = [field_name for field_name in required_fields if field_name not in fields]
    total = parse_report_integer(fields.get("Total preliminary price", ""))
    row_count = parse_report_integer(fields.get("Input rows count", ""))
    if missing or fields.get("Status") != "PASS" or total is None or row_count is None:
        add_red_flag(
            result,
            f"calculator report is incomplete or failed for {item_input.product_name}",
        )
        return False
    result.item_summaries.append(
        ItemCalculationSummary(
            product_name=item_input.product_name,
            input_rows_count=row_count,
            cabinet=fields["Cabinet"],
            cabinet_price=fields["Cabinet price"],
            component_material_total=fields["Component material total"],
            work_total=fields["Work total"],
            additional_materials_total=fields["Additional materials total"],
            total_preliminary_price=total,
        )
    )
    return True


def cleanup_temp_csv(result: CheckedRunResult) -> None:
    if not result.temp_csv_paths:
        result.checks["temp cleanup"] = "pass"
        result.temp_csv_deleted = True
        return

    for temp_path in result.temp_csv_paths:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            add_red_flag(
                result,
                f"temporary CSV bridge could not be deleted: {temp_path.name}",
            )
    result.temp_csv_deleted = all(
        not temp_path.exists() for temp_path in result.temp_csv_paths
    )
    result.checks["temp cleanup"] = "pass" if result.temp_csv_deleted else "fail"
    if not result.temp_csv_deleted:
        add_red_flag(result, "temporary CSV bridge still exists after cleanup")


def run_checked_price_calculator_from_completed_draft(
    completed_input_json: Path,
    price_workbook: Path,
    custom_sche_metal_workbook: Path | None = None,
) -> CheckedRunResult:
    result = CheckedRunResult(
        completed_input_json=resolved(completed_input_json),
        price_workbook=resolved(price_workbook),
    )

    if not run_completed_input_validation(result):
        return result

    try:
        data = load_completed_input_json(result)
        if data is None:
            return result
        item_inputs = (
            split_v02_item_inputs(data, result)
            if data.get("schema_version") == V02_SCHEMA_VERSION
            else split_item_inputs(data, result)
        )
        if not item_inputs:
            return result
        custom_base_cost: int | None = None
        if any(item.cabinet_code == CUSTOM_SCHE_CABINET_CODE for item in item_inputs):
            if custom_sche_metal_workbook is None:
                result.checks["custom ЩЭ resolver"] = "fail"
                add_red_flag(result, "custom ЩЭ metal workbook is required")
                return result
            try:
                custom_base_cost = resolve_custom_sche_base_cost(
                    custom_sche_metal_workbook
                )
            except (OSError, RuntimeError):  # fmt: skip
                result.checks["custom ЩЭ resolver"] = "fail"
                add_red_flag(result, "custom ЩЭ resolver failed closed")
                return result
        all_bridges_created = True
        all_calculators_passed = True
        for item_input in item_inputs:
            temp_csv = create_csv_bridge(item_input, result)
            if temp_csv is None:
                all_bridges_created = False
                all_calculators_passed = False
                break
            item_custom_base_cost = (
                custom_base_cost
                if item_input.cabinet_code == CUSTOM_SCHE_CABINET_CODE
                else None
            )
            if not execute_calculator(
                result,
                item_input,
                temp_csv,
                custom_cabinet_base_cost=item_custom_base_cost,
            ):
                all_calculators_passed = False
                break
        if all_bridges_created and len(result.temp_csv_paths) == len(item_inputs):
            result.checks["CSV bridge"] = "pass"
        if all_calculators_passed and len(result.item_summaries) == len(item_inputs):
            result.checks["calculator execution"] = "pass"
            result.overall_preliminary_total = sum(
                summary.total_preliminary_price for summary in result.item_summaries
            )
    finally:
        cleanup_temp_csv(result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def parse_calculator_summary(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    summary: list[str] = []
    for index, line in enumerate(lines):
        key = line.removesuffix(":")
        if key in CALCULATOR_SUMMARY_KEYS and index + 1 < len(lines):
            value = lines[index + 1]
            if key == "Status":
                summary.append(f"calculator technical status: {value}")
            elif key == "Mode":
                summary.append(f"calculator mode: {value}")
            elif key == "Commercial status":
                summary.append(f"calculator commercial boundary: {value}")
            elif key == "Human Approval":
                summary.append(f"calculator human approval boundary: {value}")
            else:
                summary.append(f"{key}: {value}")
    return summary if summary else ["not available"]


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def output_or_empty(value: str) -> str:
    return value.rstrip("\r\n") if value else "empty"


def configure_cli_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def format_report(result: CheckedRunResult) -> str:
    calculator_summary = parse_calculator_summary(result.calculator_stdout)
    if result.calculator_returncode is not None:
        calculator_summary.insert(
            0,
            f"calculator exit code: {result.calculator_returncode}",
        )
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
    lines.extend(["", "Calculator result:"])
    lines.extend(format_items(calculator_summary))
    if result.calculator_returncode is not None and result.calculator_returncode != 0:
        lines.extend(
            [
                "",
                "Calculator stdout:",
                output_or_empty(result.calculator_stdout),
                "",
                "Calculator stderr:",
                output_or_empty(result.calculator_stderr),
            ]
        )
    lines.extend(["", "Item results:"])
    if result.item_summaries:
        for index, summary in enumerate(result.item_summaries, start=1):
            lines.extend(
                [
                    f"item {index}: {summary.product_name}",
                    f"rows: {summary.input_rows_count}",
                    f"cabinet: {summary.cabinet}",
                    f"cabinet price: {summary.cabinet_price}",
                    f"component materials: {summary.component_material_total}",
                    f"work: {summary.work_total}",
                    f"additional materials: {summary.additional_materials_total}",
                    f"preliminary total: {summary.total_preliminary_price}",
                ]
            )
    else:
        lines.append("not available")
    lines.extend(
        [
            "",
            "Overall preliminary total:",
            (
                f"{result.overall_preliminary_total:,}".replace(",", " ")
                if result.overall_preliminary_total is not None
                else "not calculated"
            ),
        ]
    )
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
    configure_cli_utf8()
    args = parse_args(argv)
    result = run_checked_price_calculator_from_completed_draft(
        args.completed_input_json,
        args.price_workbook,
        custom_sche_metal_workbook=args.custom_sche_metal_workbook,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
