"""Generate separate draft invoice-quote workbooks from v0.2 block JSON."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PREFIX = "invoice_quote_draft_v0_2"
SUPPORTED_OUTPUT_MODES = {"separate_workbooks_by_block", "both"}
SINGLE_WORKBOOK_ERROR = "single_workbook_sections is not implemented in this script."
MAX_ITEMS_PER_BLOCK = 5


class SeparateFillError(Exception):
    """Expected validation, preflight, or generation error."""


@dataclass(frozen=True)
class PlannedOutput:
    block_name: str
    block_label_for_quote: str
    output_path: Path
    flat_payload: dict[str, Any]


@dataclass(frozen=True)
class PreflightPlan:
    template: Path
    output_dir: Path
    output_mode: str
    planned_outputs: tuple[PlannedOutput, ...]
    single_workbook_notice: str | None = None


def import_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(
    Any,
    import_script_module(
        "validate_invoice_quote_v0_2_runtime",
        PROJECT_ROOT / "scripts" / "validate_invoice_quote_v0_2.py",
    ),
)
draft_filler = cast(
    Any,
    import_script_module(
        "fill_invoice_quote_draft_runtime",
        PROJECT_ROOT / "scripts" / "fill_invoice_quote_draft.py",
    ),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate separate v0.2 draft invoice-quote workbooks by block."
    )
    parser.add_argument("--input-json", required=True, type=Path, help="Path to JSON")
    parser.add_argument("--template", required=True, type=Path, help="Path to .xlsx")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Existing directory outside the Git project",
    )
    return parser.parse_args(argv)


def fail(message: str) -> None:
    raise SeparateFillError(message)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def load_json(path: Path) -> Mapping[str, Any]:
    input_path = resolved(path)
    if not input_path.is_file():
        fail(f"input JSON does not exist: {input_path}")
    try:
        raw_data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"input JSON is invalid: {error.msg}")
    if not isinstance(raw_data, Mapping):
        fail("input JSON must be an object")
    return cast(Mapping[str, Any], raw_data)


def validate_v0_2_contract(data: Mapping[str, Any]) -> None:
    result = validator.validate_invoice_quote_v0_2(data)
    if result.is_valid:
        return
    errors = "; ".join(str(error) for error in result.errors)
    fail(f"validation failed: {errors}")


def require_supported_output_mode(data: Mapping[str, Any]) -> tuple[str, str | None]:
    output_mode = data.get("output_mode")
    if output_mode == "single_workbook_sections":
        fail(SINGLE_WORKBOOK_ERROR)
    if output_mode not in SUPPORTED_OUTPUT_MODES:
        fail("output_mode must be separate_workbooks_by_block or both")
    notice = None
    if output_mode == "both":
        notice = (
            "single_workbook_sections is not implemented in this script; "
            "generated separate_workbooks_by_block outputs only."
        )
    return str(output_mode), notice


def validate_template_and_output_dir(
    template: Path, output_dir: Path
) -> tuple[Path, Path]:
    template_path = resolved(template)
    output_directory = resolved(output_dir)

    if not template_path.is_file():
        fail(f"template does not exist: {template_path}")
    if not output_directory.is_dir():
        fail(f"output_dir does not exist: {output_directory}")
    if output_directory.is_relative_to(PROJECT_ROOT):
        fail(f"output_dir is inside the Git project: {output_directory}")
    return template_path, output_directory


def safe_filename_component(value: Any) -> str:
    source = str(value).strip().casefold()
    cleaned = re.sub(r"[^0-9a-zа-я._-]+", "_", source)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    if not cleaned:
        fail("block_name cannot be converted to a safe filename")
    return cleaned


def flattened_items(block: Mapping[str, Any]) -> list[dict[str, Any]]:
    block_name = str(block.get("block_name"))
    items: list[dict[str, Any]] = []
    subsections = cast(Sequence[Any], block["subsections"])
    for raw_subsection in subsections:
        subsection = cast(Mapping[str, Any], raw_subsection)
        subsection_name = subsection.get("subsection_name")
        subsection_items = cast(Sequence[Any], subsection["items"])
        for raw_item in subsection_items:
            item = copy.deepcopy(cast(dict[str, Any], raw_item))
            if subsection_name not in (None, ""):
                item["name"] = f"{subsection_name}: {item['name']}"
            items.append(item)

    if len(items) > MAX_ITEMS_PER_BLOCK:
        fail(f"block {block_name} has more than 5 items.")
    return items


def flat_payload_for_block(
    data: Mapping[str, Any], block: Mapping[str, Any]
) -> dict[str, Any]:
    payload = {
        "document": copy.deepcopy(data["document"]),
        "customer": copy.deepcopy(data["customer"]),
        "project": copy.deepcopy(data["project"]),
        "items": flattened_items(block),
        "commercial_terms": copy.deepcopy(data["commercial_terms"]),
        "safety_flags": copy.deepcopy(data["safety_flags"]),
        "metadata": copy.deepcopy(data["metadata"]),
    }
    project = cast(dict[str, Any], payload["project"])
    block_label = str(block["block_label_for_quote"])
    existing_position = project.get("section_or_project_position")
    project["section_or_project_position"] = (
        f"{existing_position} / {block_label}" if existing_position else block_label
    )
    project["block_label_for_quote"] = block_label
    project["block_name"] = block["block_name"]

    metadata = cast(dict[str, Any], payload["metadata"])
    metadata["generated_for_block_name"] = block["block_name"]
    metadata["generated_for_block_label_for_quote"] = block_label
    return payload


def validate_flat_payload(plan: PlannedOutput) -> None:
    try:
        draft_filler.validate_contract(plan.flat_payload)
    except draft_filler.DraftFillError as error:
        fail(f"flat payload for block {plan.block_name} is invalid: {error}")


def plan_output_files(
    data: Mapping[str, Any], template: Path, output_dir: Path
) -> tuple[PlannedOutput, ...]:
    planned_outputs: list[PlannedOutput] = []
    seen_paths: set[Path] = set()
    blocks = cast(Sequence[Any], data["project_blocks"])

    for raw_block in blocks:
        block = cast(Mapping[str, Any], raw_block)
        safe_name = safe_filename_component(block["block_name"])
        output_path = output_dir / f"{DEFAULT_OUTPUT_PREFIX}_{safe_name}.xlsx"
        if output_path in seen_paths:
            fail(f"duplicate output filename planned: {output_path.name}")
        seen_paths.add(output_path)
        planned_outputs.append(
            PlannedOutput(
                block_name=str(block["block_name"]),
                block_label_for_quote=str(block["block_label_for_quote"]),
                output_path=output_path,
                flat_payload=flat_payload_for_block(data, block),
            )
        )

    for plan in planned_outputs:
        if plan.output_path == template:
            fail("output matches template")
        if plan.output_path.exists():
            fail(f"output already exists: {plan.output_path}")
        if plan.output_path.is_relative_to(PROJECT_ROOT):
            fail(f"output is inside the Git project: {plan.output_path}")
        validate_flat_payload(plan)

    return tuple(planned_outputs)


def build_preflight_plan(
    input_json: Path, template: Path, output_dir: Path
) -> PreflightPlan:
    data = load_json(input_json)
    validate_v0_2_contract(data)
    output_mode, notice = require_supported_output_mode(data)
    template_path, output_directory = validate_template_and_output_dir(
        template, output_dir
    )
    planned_outputs = plan_output_files(data, template_path, output_directory)
    return PreflightPlan(
        template=template_path,
        output_dir=output_directory,
        output_mode=output_mode,
        planned_outputs=planned_outputs,
        single_workbook_notice=notice,
    )


def generate_workbook(template: Path, output: Path, payload: Mapping[str, Any]) -> None:
    before = draft_filler.snapshot_template(template)
    workbook = draft_filler.load_template_workbook(template)
    draft_filler.fill_allowed_cells(workbook, payload)
    draft_filler.save_output(workbook, template, output, before)
    results = draft_filler.verify_output(template, output, before)
    draft_filler.print_report(results)
    failed_results = [result.name for result in results if not result.passed]
    if failed_results:
        fail(
            f"verification failed for {output.name}: "
            f"{'; '.join(str(name) for name in failed_results)}"
        )


def generate_outputs(plan: PreflightPlan) -> tuple[Path, ...]:
    temporary_outputs: list[tuple[Path, Path]] = []
    try:
        for planned_output in plan.planned_outputs:
            temp_output = (
                plan.output_dir
                / f".{planned_output.output_path.stem}.{uuid.uuid4().hex}.tmp.xlsx"
            )
            temporary_outputs.append((temp_output, planned_output.output_path))
            generate_workbook(
                plan.template,
                temp_output,
                planned_output.flat_payload,
            )

        for _temp_output, final_output in temporary_outputs:
            if final_output.exists():
                fail(f"output already exists: {final_output}")

        for temp_output, final_output in temporary_outputs:
            temp_output.replace(final_output)
    finally:
        for temp_output, final_output in temporary_outputs:
            if temp_output.exists() and not final_output.exists():
                temp_output.unlink()

    return tuple(final_output for _temp_output, final_output in temporary_outputs)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = build_preflight_plan(
            input_json=args.input_json,
            template=args.template,
            output_dir=args.output_dir,
        )
        if plan.single_workbook_notice is not None:
            print(plan.single_workbook_notice)
        generated_outputs = generate_outputs(plan)
    except SeparateFillError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for output in generated_outputs:
        print(f"CREATED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
