"""Build a fixed-layout isolated extended writer job from simple items JSON."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOB_RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "run_invoice_quote_extended.py"
PROFILE_NAME = "isolated extended v0.2.1 fixed layout profile"
ITEM_START_ROW = 17
HEADER_RANGES = ("C2:I6", "B4:B6")
TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


class ItemsBridgeError(Exception):
    """Expected simple-input bridge preflight or validation error."""


def fail(message: str) -> None:
    raise ItemsBridgeError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated extended invoice-quote writer from simple items JSON "
            f"using the {PROFILE_NAME}."
        )
    )
    parser.add_argument(
        "--items-json",
        required=True,
        type=Path,
        help="Path to simple items JSON",
    )
    parser.add_argument("--template", required=True, type=Path, help="Path to .xlsx")
    parser.add_argument(
        "--template-capacity",
        required=True,
        type=int,
        help="Prepared template item-row capacity",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output .xlsx path")
    return parser.parse_args(argv)


def load_items_json(path: Path) -> Mapping[str, Any]:
    items_path = path.expanduser().resolve(strict=False)
    if not items_path.is_file():
        fail(f"items JSON does not exist: {items_path}")
    try:
        raw_data = json.loads(items_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"items JSON is invalid: {error.msg}")
    if not isinstance(raw_data, Mapping):
        fail("items JSON must be an object")
    return cast(Mapping[str, Any], raw_data)


def require_items(data: Mapping[str, Any]) -> list[Any]:
    if "items" not in data:
        fail("items is required")
    items = data["items"]
    if not isinstance(items, list):
        fail("items must be a list")
    if not items:
        fail("items must not be empty")
    return items


def validate_template_capacity(capacity: Any) -> int:
    if not isinstance(capacity, int) or isinstance(capacity, bool):
        fail("template_capacity must be a positive integer")
    if capacity < 1:
        fail(f"template_capacity must be positive: {capacity}")
    return capacity


def build_fixed_layout(capacity: int) -> dict[str, Any]:
    item_end_row = ITEM_START_ROW + capacity - 1
    total_row = ITEM_START_ROW + capacity
    return {
        "item_start_row": ITEM_START_ROW,
        "item_end_row": item_end_row,
        "capacity": capacity,
        "total_row": total_row,
        "signature_range": f"B{20 + capacity}:I{22 + capacity}",
        "header_ranges": list(HEADER_RANGES),
        "formula_cells": [f"I{row}" for row in range(ITEM_START_ROW, total_row)]
        + [f"I{total_row}"],
    }


def build_job(items: list[Any], capacity: int) -> dict[str, Any]:
    if len(items) > capacity:
        fail(f"items count {len(items)} exceeds template capacity {capacity}")
    return {
        "payload": {"items": items},
        "layout": build_fixed_layout(capacity),
    }


def write_job(path: Path, job: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")


def run_job_runner(
    job_json: Path,
    template: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(JOB_RUNNER_SCRIPT),
            "--job-json",
            str(job_json),
            "--template",
            str(template),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def forward_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        items_data = load_items_json(args.items_json)
        items = require_items(items_data)
        capacity = validate_template_capacity(args.template_capacity)
        job = build_job(items, capacity)
    except ItemsBridgeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    with TEMPORARY_DIRECTORY(prefix="invoice_quote_extended_items_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        job_json = temp_dir / "job.json"
        write_job(job_json, job)
        result = run_job_runner(
            job_json=job_json,
            template=args.template,
            output=args.output,
        )

    forward_output(result)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
