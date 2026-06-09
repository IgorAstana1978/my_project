"""Run the isolated extended invoice-quote writer from a single job JSON."""

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
EXTENDED_WRITER_SCRIPT = PROJECT_ROOT / "scripts" / "fill_invoice_quote_extended.py"
TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


class RunnerError(Exception):
    """Expected runner preflight or job validation error."""


def fail(message: str) -> None:
    raise RunnerError(message)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated extended invoice-quote writer from job JSON."
    )
    parser.add_argument("--job-json", required=True, type=Path, help="Path to job JSON")
    parser.add_argument("--template", required=True, type=Path, help="Path to .xlsx")
    parser.add_argument("--output", required=True, type=Path, help="Output .xlsx path")
    return parser.parse_args(argv)


def load_job_json(path: Path) -> Mapping[str, Any]:
    job_path = path.expanduser().resolve(strict=False)
    if not job_path.is_file():
        fail(f"job JSON does not exist: {job_path}")
    try:
        raw_data = json.loads(job_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"job JSON is invalid: {error.msg}")
    if not isinstance(raw_data, Mapping):
        fail("job JSON must be an object")
    return cast(Mapping[str, Any], raw_data)


def require_object(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in data:
        fail(f"job.{key} is required")
    value = data[key]
    if not isinstance(value, Mapping):
        fail(f"job.{key} must be an object")
    return cast(Mapping[str, Any], value)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_extended_writer(
    payload_json: Path,
    layout_json: Path,
    template: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(EXTENDED_WRITER_SCRIPT),
            "--payload-json",
            str(payload_json),
            "--layout-json",
            str(layout_json),
            "--template",
            str(template),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def forward_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        job = load_job_json(args.job_json)
        payload = require_object(job, "payload")
        layout = require_object(job, "layout")
    except RunnerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    with TEMPORARY_DIRECTORY(prefix="invoice_quote_extended_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        payload_json = temp_dir / "payload.json"
        layout_json = temp_dir / "layout.json"
        write_json(payload_json, payload)
        write_json(layout_json, layout)

        result = run_extended_writer(
            payload_json=payload_json,
            layout_json=layout_json,
            template=args.template,
            output=args.output,
        )

    forward_output(result)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
