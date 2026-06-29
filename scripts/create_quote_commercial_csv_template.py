"""Create an empty strict commercial quote CSV template outside Git."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_DELIMITER = ";"
STRICT_COLUMNS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
    "unit_price_kzt",
    "price_includes_vat",
    "price_confirmed_by_igor",
)


@dataclass(frozen=True)
class TemplateResult:
    output_path: Path
    result: str
    status: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an empty strict commercial quote CSV outside Git."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New commercial .csv path outside the Git project",
    )
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def validate_output(output_path: Path) -> str | None:
    if output_path.suffix.casefold() != ".csv":
        return "output suffix must be .csv"
    if is_inside_project(output_path):
        return "output CSV must be outside the Git project"
    if not output_path.parent.is_dir():
        return "output parent directory does not exist"
    if output_path.exists():
        return "output file already exists"
    return None


def create_template(output: Path) -> TemplateResult:
    output_path = resolved(output)
    failure = validate_output(output_path)
    if failure is not None:
        return TemplateResult(
            output_path=output_path,
            result="fail",
            status=failure,
        )

    try:
        with output_path.open("x", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(
                csv_file,
                delimiter=CSV_DELIMITER,
                lineterminator="\n",
            )
            writer.writerow(STRICT_COLUMNS)
    except FileExistsError:
        return TemplateResult(
            output_path=output_path,
            result="fail",
            status="output file already exists",
        )
    except OSError:
        return TemplateResult(
            output_path=output_path,
            result="fail",
            status="template could not be created",
        )

    return TemplateResult(
        output_path=output_path,
        result="pass",
        status="commercial template created",
    )


def format_report(result: TemplateResult) -> str:
    return "\n".join(
        [
            "COMMERCIAL_QUOTE_CSV_TEMPLATE_REPORT_START",
            f"Result: {result.result}",
            f"Output: {result.output_path}",
            "Rows: 0",
            f"Columns: {len(STRICT_COLUMNS)}",
            f"Delimiter: {CSV_DELIMITER}",
            f"Status: {result.status}",
            "COMMERCIAL_QUOTE_CSV_TEMPLATE_REPORT_END",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = create_template(args.output)
    print(format_report(result))
    return 0 if result.result == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
