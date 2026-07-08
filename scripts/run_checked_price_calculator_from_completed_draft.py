"""Run the read-only price calculator from a validated completed draft."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
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
CALCULATOR_SUMMARY_KEYS = (
    "Status",
    "Mode",
    "Input rows count",
    "Cabinet",
    "Cabinet price",
    "Component material total",
    "Work total",
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


@dataclass
class CheckedRunResult:
    completed_input_json: Path
    price_workbook: Path
    status: str = "FAIL"
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "completed input validation": "fail",
            "CSV bridge": "fail",
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a completed price-calculator input draft, bridge it to "
            "the existing CSV contract, and run the read-only calculator."
        )
    )
    parser.add_argument("--completed-input-json", required=True, type=Path)
    parser.add_argument("--price-workbook", required=True, type=Path)
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


def create_csv_bridge(data: Mapping[str, Any], result: CheckedRunResult) -> Path | None:
    calculator_format = data.get("calculator_input_format")
    if not isinstance(calculator_format, Mapping):
        add_red_flag(result, "calculator_input_format must be an object")
        return None

    columns = calculator_format.get("columns")
    rows = calculator_format.get("rows")
    if columns != list(CALCULATOR_COLUMNS):
        add_red_flag(result, "calculator columns do not match calculator contract")
        return None
    if not isinstance(rows, list) or not rows:
        add_red_flag(result, "calculator rows must be a non-empty list")
        return None

    temp_handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix="checked_price_calculator_",
        delete=False,
    )
    temp_path = Path(temp_handle.name)
    result.temp_csv_path = temp_path
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
            writer.writerow(CALCULATOR_COLUMNS)
            for row_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    add_red_flag(
                        result,
                        f"calculator row must be an object: {row_index}",
                    )
                    return None
                writer.writerow(
                    [string_for_csv(row[column]) for column in CALCULATOR_COLUMNS]
                )
    except OSError:
        add_red_flag(result, "temporary CSV bridge could not be written")
        return None
    except KeyError as exc:
        add_red_flag(result, f"calculator row is missing column: {exc.args[0]}")
        return None

    result.checks["CSV bridge"] = "pass"
    return temp_path


def run_calculator_cli(
    price_workbook: Path,
    input_csv: Path,
) -> CalculatorProcessResult:
    completed = subprocess.run(
        [
            sys.executable,
            str(CALCULATOR_PATH),
            "--price-workbook",
            str(price_workbook),
            "--input-csv",
            str(input_csv),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return CalculatorProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def execute_calculator(result: CheckedRunResult, input_csv: Path) -> bool:
    try:
        process_result = run_calculator_cli(result.price_workbook, input_csv)
    except OSError:
        add_red_flag(result, "calculator invocation failed")
        return False

    result.calculator_returncode = process_result.returncode
    result.calculator_stdout = process_result.stdout
    result.calculator_stderr = process_result.stderr
    if process_result.returncode != 0:
        add_red_flag(
            result,
            f"calculator returned non-zero exit code: {process_result.returncode}",
        )
        return False

    result.checks["calculator execution"] = "pass"
    return True


def cleanup_temp_csv(result: CheckedRunResult) -> None:
    temp_path = result.temp_csv_path
    if temp_path is None:
        result.checks["temp cleanup"] = "pass"
        result.temp_csv_deleted = True
        return

    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError:
        result.temp_csv_deleted = False
        result.checks["temp cleanup"] = "fail"
        add_red_flag(result, "temporary CSV bridge could not be deleted")
        return

    result.temp_csv_deleted = not temp_path.exists()
    result.checks["temp cleanup"] = "pass" if result.temp_csv_deleted else "fail"
    if not result.temp_csv_deleted:
        add_red_flag(result, "temporary CSV bridge still exists after cleanup")


def run_checked_price_calculator_from_completed_draft(
    completed_input_json: Path,
    price_workbook: Path,
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
        temp_csv = create_csv_bridge(data, result)
        if temp_csv is None:
            return result
        execute_calculator(result, temp_csv)
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


def format_report(result: CheckedRunResult) -> str:
    calculator_summary = parse_calculator_summary(result.calculator_stdout)
    if result.calculator_returncode is not None:
        calculator_summary.insert(
            0,
            f"calculator exit code: {result.calculator_returncode}",
        )
    if result.calculator_stderr.strip():
        calculator_summary.append("calculator stderr: present")

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
    result = run_checked_price_calculator_from_completed_draft(
        args.completed_input_json,
        args.price_workbook,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
