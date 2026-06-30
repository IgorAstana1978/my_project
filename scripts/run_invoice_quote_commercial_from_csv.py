"""Create a reconciled internal commercial quote draft from strict CSV."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMERCIAL_PREFLIGHT_SCRIPT = (
    PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py"
)
COMMERCIAL_RECONCILIATION_SCRIPT = (
    PROJECT_ROOT / "scripts" / "inspect_quote_commercial_reconciliation.py"
)
OOXML_CELL_PATCHER_SCRIPT = PROJECT_ROOT / "scripts" / "ooxml_cell_patcher.py"

SHEET_NAME = "Счёт-КП шаблон"
CERTIFIED_CAPACITY = 100
ITEM_START_ROW = 17
ITEM_END_ROW = 116
BASE_ITEM_ROW_HEIGHT = 24
ITEM_ROW_VISUAL_LINE_HEIGHT = 15
ITEM_ROW_VERTICAL_PADDING = 6
MAX_ITEM_ROW_HEIGHT = 360
ROW_HEIGHT_TEXT_WIDTHS = {
    "name": 28,
    "instruments_and_devices": 35,
    "cabinet_type_dimensions_material": 24,
}
PASS_NEXT = (
    "retain as an internal draft only; manual Igor check and separate Human "
    "Approval are required"
)
FAIL_NEXT = "no internal draft was published; correct the reported issue and rerun"


class CommercialWriterError(Exception):
    """Expected commercial writer validation or generation failure."""


@dataclass
class CommercialWriterResult:
    commercial_csv: Path
    template: Path
    output: Path
    status: str = "FAIL"
    row_count: int = 0
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "commercial preflight": "fail",
            "capacity100 profile": "fail",
            "output path": "fail",
            "candidate generation": "fail",
            "commercial reconciliation": "fail",
            "atomic publish": "fail",
        }
    )
    reconciliation_checks: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    next_action: str = FAIL_NEXT


def fail(message: str) -> NoReturn:
    raise CommercialWriterError(message)


def load_sibling_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        fail(f"could not load required helper: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


commercial_preflight = cast(
    Any,
    load_sibling_module(
        "preflight_quote_commercial_input_for_writer",
        COMMERCIAL_PREFLIGHT_SCRIPT,
    ),
)
commercial_reconciliation = cast(
    Any,
    load_sibling_module(
        "inspect_quote_commercial_reconciliation_for_writer",
        COMMERCIAL_RECONCILIATION_SCRIPT,
    ),
)
ooxml_cell_patcher = cast(
    Any,
    load_sibling_module(
        "ooxml_cell_patcher_for_commercial_writer",
        OOXML_CELL_PATCHER_SCRIPT,
    ),
)
OoxmlCellPatcherError = ooxml_cell_patcher.OoxmlCellPatcherError
patch_existing_cells = ooxml_cell_patcher.patch_existing_cells


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reconciled capacity100 commercial XLSX for internal "
            "draft review only."
        )
    )
    parser.add_argument("--commercial-csv", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--template-capacity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_generation_paths(
    template: Path,
    output: Path,
    template_capacity: int,
) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_path = resolved(output)

    if template_capacity != CERTIFIED_CAPACITY:
        fail("only the certified capacity100 profile is supported")
    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if template_path.suffix.casefold() != ".xlsx":
        fail("template suffix must be .xlsx")
    if output_path.suffix.casefold() != ".xlsx":
        fail("output suffix must be .xlsx")
    if output_path.exists():
        fail(f"output already exists: {output_path}")
    if not output_path.parent.is_dir():
        fail(f"output parent directory does not exist: {output_path.parent}")
    if is_inside_project(output_path):
        fail(f"output is inside the Git project: {output_path}")
    if template_path == output_path:
        fail("output matches template")
    return template_path, output_path


def load_commercial_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(
                csv_file,
                delimiter=commercial_preflight.CSV_DELIMITER,
                strict=True,
            )
            rows = [dict(row) for row in reader]
    except OSError, UnicodeDecodeError, csv.Error:
        fail("validated commercial CSV could not be read safely")
    if not rows:
        fail("validated commercial CSV contains no rows")
    return rows


def visual_line_count(value: str, width: int) -> int:
    return sum(max(1, (len(line) + width - 1) // width) for line in value.split("\n"))


def estimate_item_row_height(row: Mapping[str, str]) -> int:
    visual_lines = max(
        visual_line_count(row[field], width)
        for field, width in ROW_HEIGHT_TEXT_WIDTHS.items()
    )
    if visual_lines <= 1:
        return BASE_ITEM_ROW_HEIGHT
    return min(
        MAX_ITEM_ROW_HEIGHT,
        visual_lines * ITEM_ROW_VISUAL_LINE_HEIGHT + ITEM_ROW_VERTICAL_PADDING,
    )


def build_cell_updates(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, str | int | None]:
    updates: dict[str, str | int | None] = {}
    for offset, item in enumerate(rows):
        excel_row = ITEM_START_ROW + offset
        updates[f"C{excel_row}"] = item["name"]
        updates[f"D{excel_row}"] = item["unit"]
        updates[f"E{excel_row}"] = int(item["quantity"])
        updates[f"F{excel_row}"] = item["instruments_and_devices"]
        updates[f"G{excel_row}"] = item["cabinet_type_dimensions_material"]
        updates[f"H{excel_row}"] = int(item["unit_price_kzt"])

    for excel_row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1):
        for column in "CDEFGH":
            updates[f"{column}{excel_row}"] = None
    return updates


def build_row_hidden_updates(rows: Sequence[Mapping[str, str]]) -> dict[int, bool]:
    first_unused_row = ITEM_START_ROW + len(rows)
    return {
        row: row >= first_unused_row for row in range(ITEM_START_ROW, ITEM_END_ROW + 1)
    }


def build_row_height_updates(rows: Sequence[Mapping[str, str]]) -> dict[int, int]:
    updates = {
        ITEM_START_ROW + offset: estimate_item_row_height(item)
        for offset, item in enumerate(rows)
    }
    updates.update(
        {
            row: BASE_ITEM_ROW_HEIGHT
            for row in range(ITEM_START_ROW + len(rows), ITEM_END_ROW + 1)
        }
    )
    return updates


def candidate_path_for(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid.uuid4().hex}.candidate.xlsx")


def generate_candidate(
    template: Path,
    candidate: Path,
    rows: Sequence[Mapping[str, str]],
) -> None:
    try:
        patch_existing_cells(
            template=template,
            output=candidate,
            sheet_name=SHEET_NAME,
            updates=build_cell_updates(rows),
            row_hidden_updates=build_row_hidden_updates(rows),
            row_height_updates=build_row_height_updates(rows),
        )
    except OoxmlCellPatcherError as error:
        fail(f"candidate generation failed: {error}")


def publish_candidate(candidate: Path, output: Path) -> None:
    if output.exists():
        fail(f"output already exists: {output}")
    try:
        candidate.rename(output)
    except OSError:
        fail("candidate could not be published atomically")


def remove_candidate(candidate: Path) -> None:
    if not candidate.exists():
        return
    try:
        candidate.unlink()
    except OSError:
        fail("temporary candidate could not be removed")


def safe_failures(failures: Sequence[str]) -> list[str]:
    return list(failures) if failures else ["unspecified validation failure"]


def run_commercial_writer(
    commercial_csv: Path,
    template: Path,
    template_capacity: int,
    output: Path,
) -> CommercialWriterResult:
    csv_path = resolved(commercial_csv)
    template_path = resolved(template)
    output_path = resolved(output)
    result = CommercialWriterResult(csv_path, template_path, output_path)

    preflight_result = commercial_preflight.preflight(csv_path)
    result.row_count = preflight_result.row_count
    if preflight_result.status != "PASS":
        result.failures.extend(safe_failures(preflight_result.failures))
        return result
    result.checks["commercial preflight"] = "pass"

    try:
        template_path, output_path = validate_generation_paths(
            template_path,
            output_path,
            template_capacity,
        )
        result.template = template_path
        result.output = output_path
        result.checks["capacity100 profile"] = "pass"
        result.checks["output path"] = "pass"
        rows = load_commercial_rows(csv_path)
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result

    candidate = candidate_path_for(output_path)
    published = False
    try:
        generate_candidate(template_path, candidate, rows)
        result.checks["candidate generation"] = "pass"

        reconciliation_result = commercial_reconciliation.reconcile(
            csv_path,
            candidate,
            template_capacity,
        )
        result.reconciliation_checks = dict(reconciliation_result.checks)
        if reconciliation_result.status != "PASS":
            result.failures.extend(safe_failures(reconciliation_result.failures))
            return result
        result.checks["commercial reconciliation"] = "pass"

        publish_candidate(candidate, output_path)
        published = True
        result.checks["atomic publish"] = "pass"
        result.status = "PASS"
        result.next_action = PASS_NEXT
        return result
    except CommercialWriterError as error:
        result.failures.append(str(error))
        return result
    except Exception:
        result.failures.append("unexpected internal writer failure")
        return result
    finally:
        if not published and candidate.exists():
            try:
                remove_candidate(candidate)
            except CommercialWriterError as error:
                result.failures.append(str(error))


def format_report(result: CommercialWriterResult) -> str:
    lines = [
        "COMMERCIAL_QUOTE_WRITER_REPORT_START",
        "",
        "Mode:",
        "internal draft only",
        "",
        "Input CSV:",
        str(result.commercial_csv),
        "",
        "Output XLSX:",
        str(result.output),
        "",
        "Status:",
        result.status,
        "",
        "Rows:",
        str(result.row_count),
        "",
        "Checks:",
    ]
    lines.extend(f"{name}: {status}" for name, status in result.checks.items())
    lines.extend(
        f"reconciliation {name}: {status}"
        for name, status in result.reconciliation_checks.items()
    )
    lines.extend(["", "Failures:"])
    lines.extend(result.failures if result.failures else ["none"])
    lines.extend(
        [
            "",
            "Next:",
            result.next_action,
            "",
            "Manual Igor check:",
            "required",
            "",
            "Human Approval:",
            "separate approval required",
            "",
            "COMMERCIAL_QUOTE_WRITER_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_commercial_writer(
        args.commercial_csv,
        args.template,
        args.template_capacity,
        args.output,
    )
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
