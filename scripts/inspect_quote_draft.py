"""Inspect a generated quote draft without printing workbook contents."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class DraftInspectionResult:
    input_path: Path
    status: str = "PASS"
    worksheet_count: int = 0
    file_size_bytes: int = 0
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "input path": "fail",
            "outside Git": "fail",
            "suffix": "fail",
            "file size": "fail",
            "workbook opens": "fail",
            "worksheets present": "fail",
        }
    )
    failures: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a generated quote draft .xlsx without printing cells."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to generated quote draft .xlsx outside Git",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_failure(result: DraftInspectionResult, message: str) -> None:
    result.failures.append(message)


def inspect_draft(input_path: Path) -> DraftInspectionResult:
    draft_path = resolved(input_path)
    result = DraftInspectionResult(input_path=draft_path)

    if draft_path.is_file():
        result.checks["input path"] = "pass"
    else:
        add_failure(result, f"input path does not exist: {draft_path}")

    if is_inside_project(draft_path):
        add_failure(result, "input draft must be outside the Git project")
    else:
        result.checks["outside Git"] = "pass"

    if draft_path.suffix.casefold() == ".xlsx":
        result.checks["suffix"] = "pass"
    else:
        add_failure(result, "input suffix must be .xlsx")

    if result.checks["input path"] == "pass":
        result.file_size_bytes = draft_path.stat().st_size
        if result.file_size_bytes > 0:
            result.checks["file size"] = "pass"
        else:
            add_failure(result, "input draft file is empty")

    should_open_workbook = all(
        result.checks[name] == "pass"
        for name in ("input path", "outside Git", "suffix", "file size")
    )
    if should_open_workbook:
        try:
            workbook = load_workbook(draft_path, read_only=True, data_only=False)
            try:
                result.checks["workbook opens"] = "pass"
                result.worksheet_count = len(workbook.worksheets)
                if result.worksheet_count > 0:
                    result.checks["worksheets present"] = "pass"
                else:
                    add_failure(result, "workbook has no worksheets")
            finally:
                workbook.close()
        except Exception:
            add_failure(result, "workbook could not be opened")

    if result.failures:
        result.status = "FAIL"
    return result


def format_list(values: Sequence[str]) -> list[str]:
    if not values:
        return ["none"]
    return list(values)


def format_report(result: DraftInspectionResult) -> str:
    lines = [
        "QUOTE_DRAFT_INSPECTION_REPORT_START",
        "",
        "Input:",
        str(result.input_path),
        "",
        "Status:",
        result.status,
        "",
        "Checks:",
        f"input path: {result.checks['input path']}",
        f"outside Git: {result.checks['outside Git']}",
        f"suffix: {result.checks['suffix']}",
        f"file size: {result.checks['file size']}",
        f"workbook opens: {result.checks['workbook opens']}",
        f"worksheets present: {result.checks['worksheets present']}",
        "",
        "Workbook:",
        f"worksheet count: {result.worksheet_count}",
        f"file size bytes: {result.file_size_bytes}",
        "",
        "Warnings:",
        "none",
        "",
        "Failures:",
    ]
    lines.extend(format_list(result.failures))
    lines.extend(
        [
            "",
            "Next:",
            "manual Igor check required before sending to client",
            "",
            "QUOTE_DRAFT_INSPECTION_REPORT_END",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = inspect_draft(args.input)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
