"""Run the extended invoice-quote CSV runtime through a temporary compact CSV."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPACT_HELPER_SCRIPT = PROJECT_ROOT / "scripts" / "compact_invoice_quote_items_csv.py"
CSV_BRIDGE_SCRIPT = PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv.py"
TEMPORARY_DIRECTORY = tempfile.TemporaryDirectory


def load_sibling_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compact_helper = cast(
    Any,
    load_sibling_module(
        "compact_invoice_quote_items_csv_for_compact_runner",
        COMPACT_HELPER_SCRIPT,
    ),
)
csv_bridge = cast(
    Any,
    load_sibling_module(
        "run_invoice_quote_extended_from_csv_for_compact_runner",
        CSV_BRIDGE_SCRIPT,
    ),
)
CompactCsvError = compact_helper.CompactCsvError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compact a strict items CSV, then run the isolated extended "
            "invoice-quote CSV runtime."
        )
    )
    parser.add_argument(
        "--items-csv",
        required=True,
        type=Path,
        help="Path to strict semicolon-delimited items CSV",
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


def csv_bridge_args(
    items_csv: Path,
    template: Path,
    template_capacity: int,
    output: Path,
) -> list[str]:
    return [
        "--items-csv",
        str(items_csv),
        "--template",
        str(template),
        "--template-capacity",
        str(template_capacity),
        "--output",
        str(output),
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with TEMPORARY_DIRECTORY(prefix="invoice_quote_compact_csv_") as temp_dir_name:
        compact_csv = Path(temp_dir_name) / "items_compact.csv"
        try:
            compact_helper.compact_csv(args.items_csv, compact_csv)
        except CompactCsvError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

        return cast(
            int,
            csv_bridge.main(
                csv_bridge_args(
                    items_csv=compact_csv,
                    template=args.template,
                    template_capacity=args.template_capacity,
                    output=args.output,
                )
            ),
        )


if __name__ == "__main__":
    raise SystemExit(main())
