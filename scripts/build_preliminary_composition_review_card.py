"""Build an Igor review card from a source-bound preliminary composition draft."""

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
VERIFIER_PATH = Path(__file__).with_name(
    "verify_preliminary_composition_source_bundle.py"
)

REPORT_START = "PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_START"
REPORT_END = "PRELIMINARY_COMPOSITION_REVIEW_CARD_REPORT_END"
MODE = "preliminary composition Igor review card only"
COMMERCIAL_STATUS = "not confirmed composition; not price approval; not client-ready КП"
HUMAN_APPROVAL = "Igor confirmation required before price calculation or commercial CSV"
EVIDENCE_LIMIT = 160

FORBIDDEN_MARKDOWN_TOKENS = (
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
    "confirmed_composition",
    "production_action_authorized",
    "token_execution_authorized",
)


@dataclass
class ReviewCardResult:
    raw_input_text: Path
    draft_json: Path
    output_md: Path
    status: str = "FAIL"
    output_created: bool = False
    checks: dict[str, str] = field(
        default_factory=lambda: {
            "source bundle verification": "fail",
            "output policy": "fail",
            "draft read": "fail",
            "review card write": "fail",
            "safety boundary": "fail",
        }
    )
    red_flags: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a preliminary composition review card for Igor."
    )
    parser.add_argument("--raw-input-text", required=True, type=Path)
    parser.add_argument("--draft-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    return parser.parse_args(argv)


def resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_project(path: Path) -> bool:
    return resolved(path).is_relative_to(PROJECT_ROOT)


def add_red_flag(result: ReviewCardResult, message: str) -> None:
    if message not in result.red_flags:
        result.red_flags.append(message)


def load_verifier_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_preliminary_composition_source_bundle_for_review_card",
        VERIFIER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("preliminary composition source bundle verifier missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_source_bundle_verification(result: ReviewCardResult) -> bool:
    verifier = load_verifier_module()
    verification = verifier.verify_source_bundle(
        result.raw_input_text,
        result.draft_json,
    )

    if verification.status == "PASS":
        result.checks["source bundle verification"] = "pass"
        result.checks["safety boundary"] = "pass"
        return True

    add_red_flag(result, "source bundle verifier failed")
    for red_flag in verification.red_flags:
        add_red_flag(result, f"source bundle: {red_flag}")
    if verification.checks.get("safety boundary") == "pass":
        result.checks["safety boundary"] = "pass"
    return False


def validate_output_policy(result: ReviewCardResult) -> bool:
    valid = True
    output = result.output_md

    if output.exists():
        valid = False
        add_red_flag(result, "output Markdown already exists")
    if is_inside_project(output):
        valid = False
        add_red_flag(result, "output Markdown must be outside the project")
    if not output.parent.is_dir():
        valid = False
        add_red_flag(result, "output parent directory does not exist")

    result.checks["output policy"] = "pass" if valid else "fail"
    return valid


def load_draft_json(path: Path, result: ReviewCardResult) -> Mapping[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_red_flag(result, "draft JSON does not exist")
        return None
    except UnicodeDecodeError:
        add_red_flag(result, "draft JSON must be valid UTF-8")
        return None
    except json.JSONDecodeError:
        add_red_flag(result, "draft JSON is malformed")
        return None
    except OSError:
        add_red_flag(result, "draft JSON could not be read")
        return None

    if not isinstance(data, Mapping):
        add_red_flag(result, "draft JSON root must be an object")
        return None

    result.checks["draft read"] = "pass"
    return cast(Mapping[str, Any], data)


def as_mapping(value: Any) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value if isinstance(value, Mapping) else {})


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def truncate_evidence(value: Any) -> str:
    value_text = text(value).replace("\r", " ").replace("\n", " ")
    if len(value_text) <= EVIDENCE_LIMIT:
        return value_text
    return value_text[: EVIDENCE_LIMIT - 3].rstrip() + "..."


def markdown_list(values: Sequence[Any]) -> list[str]:
    if not values:
        return ["  - none"]
    return [f"  - {text(value)}" for value in values]


def evidence_list(values: Sequence[Any]) -> list[str]:
    if not values:
        return ["  - none"]
    return [f"  - {truncate_evidence(value)}" for value in values]


def table_cell(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def component_row(component: Mapping[str, Any]) -> str:
    red_flags = "; ".join(text(flag) for flag in as_list(component.get("red_flags")))
    return " | ".join(
        (
            table_cell(component.get("component_id")),
            table_cell(component.get("component_code_guess")),
            table_cell(component.get("component_label_guess")),
            table_cell(component.get("quantity_guess")),
            table_cell(component.get("install_type_guess")),
            table_cell(component.get("confidence")),
            table_cell(component.get("requires_igor_confirmation")),
            table_cell(red_flags or "none"),
        )
    )


def append_item_section(lines: list[str], index: int, item: Mapping[str, Any]) -> None:
    product_name = text(item.get("product_name_guess"))
    cabinet = as_mapping(item.get("cabinet_guess"))
    components = [
        as_mapping(component) for component in as_list(item.get("components"))
    ]

    lines.extend(
        [
            f"## Item {index} - {product_name}",
            "",
            f"- item_id: {text(item.get('item_id'))}",
            f"- product_type_guess: {text(item.get('product_type_guess'))}",
            f"- quantity_guess: {text(item.get('quantity_guess'))}",
            f"- confidence: {text(item.get('confidence'))}",
            (
                "- requires_igor_confirmation: "
                f"{text(item.get('requires_igor_confirmation'))}"
            ),
            (
                "- cabinet_guess: "
                f"code={text(cabinet.get('code_guess'))}; "
                f"label={text(cabinet.get('label_guess'))}; "
                f"confidence={text(cabinet.get('confidence'))}"
            ),
            "- item red_flags:",
        ]
    )
    lines.extend(markdown_list(as_list(item.get("red_flags"))))
    lines.append("- item assumptions:")
    lines.extend(markdown_list(as_list(item.get("assumptions"))))
    lines.append("- short evidence summary:")
    lines.extend(evidence_list(as_list(item.get("evidence"))))
    lines.extend(
        [
            "",
            "Components:",
            "",
            (
                "component_id | component_code_guess | component_label_guess | qty | "
                "install_type_guess | confidence | "
                "requires_igor_confirmation | red_flags"
            ),
            "--- | --- | --- | --- | --- | --- | --- | ---",
        ]
    )
    lines.extend(component_row(component) for component in components)
    lines.append("")


def checklist_lines(items: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    has_red_flags = False
    for item in items:
        item_id = text(item.get("item_id"))
        lines.extend(
            [
                f"- [ ] Confirm item {item_id} product name/type.",
                f"- [ ] Confirm item {item_id} quantity.",
                f"- [ ] Confirm cabinet for {item_id}.",
            ]
        )
        if as_list(item.get("red_flags")):
            has_red_flags = True
        for component in as_list(item.get("components")):
            component_map = as_mapping(component)
            component_id = text(component_map.get("component_id"))
            lines.append(
                "- [ ] Confirm component "
                f"{component_id} code/label/quantity/install type."
            )
            if as_list(component_map.get("red_flags")):
                has_red_flags = True
    if has_red_flags:
        lines.append("- [ ] Resolve item/component red flags.")
    lines.append("- [ ] Confirm whether this draft may proceed to price calculation.")
    return lines


def build_markdown(data: Mapping[str, Any]) -> str:
    source = as_mapping(data.get("source"))
    safety = as_mapping(data.get("safety"))
    item_list = [as_mapping(item) for item in as_list(data.get("items"))]
    lines = [
        "# Preliminary Composition Review Card",
        "",
        "Status:",
        "PRELIMINARY ONLY - NOT CONFIRMED",
        "",
        "Source:",
        f"- source_type: {text(source.get('source_type'))}",
        f"- source_summary: {text(source.get('source_summary'))}",
        f"- raw_input_sha256: {text(source.get('raw_input_sha256'))}",
        f"- draft_id: {text(data.get('draft_id'))}",
        f"- created_at: {text(data.get('created_at'))}",
        f"- overall_confidence: {text(data.get('overall_confidence'))}",
        "",
        "Safety:",
        f"- confirmed_by_igor: {text(safety.get('confirmed_by_igor'))}",
        (
            "- price_execution_authorized: "
            f"{text(safety.get('price_execution_authorized'))}"
        ),
        (
            "- commercial_csv_authorized: "
            f"{text(safety.get('commercial_csv_authorized'))}"
        ),
        (
            "- client_style_export_authorized: "
            f"{text(safety.get('client_style_export_authorized'))}"
        ),
        f"- sending_authorized: {text(safety.get('sending_authorized'))}",
        f"- production_authorized: {text(safety.get('production_authorized'))}",
        "",
        "Items:",
        "",
    ]
    for index, item in enumerate(item_list, start=1):
        append_item_section(lines, index, item)

    lines.extend(["Human Confirmation Checklist:", ""])
    lines.extend(checklist_lines(item_list))
    lines.extend(
        [
            "",
            "Final safety footer:",
            (
                "This review card does not approve composition, price, commercial "
                "CSV, КП, sending or production."
            ),
            (
                "Igor confirmation is required before any price calculation or "
                "commercial CSV step."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def markdown_has_forbidden_tokens(markdown: str) -> bool:
    lowered = markdown.lower()
    return any(token in lowered for token in FORBIDDEN_MARKDOWN_TOKENS)


def write_review_card(path: Path, markdown: str, result: ReviewCardResult) -> bool:
    if markdown_has_forbidden_tokens(markdown):
        add_red_flag(result, "review card contains forbidden approval-like fields")
        return False
    try:
        path.write_text(markdown, encoding="utf-8")
    except OSError:
        add_red_flag(result, "review card could not be written")
        return False
    result.output_created = True
    result.checks["review card write"] = "pass"
    return True


def build_review_card(
    raw_input_text: Path,
    draft_json: Path,
    output_md: Path,
) -> ReviewCardResult:
    result = ReviewCardResult(
        raw_input_text=resolved(raw_input_text),
        draft_json=resolved(draft_json),
        output_md=resolved(output_md),
    )

    if not run_source_bundle_verification(result):
        return result
    if not validate_output_policy(result):
        return result
    data = load_draft_json(result.draft_json, result)
    if data is None:
        return result
    markdown = build_markdown(data)
    write_review_card(result.output_md, markdown, result)

    all_checks_pass = all(status == "pass" for status in result.checks.values())
    result.status = "PASS" if all_checks_pass and not result.red_flags else "FAIL"
    return result


def format_items(values: Sequence[str]) -> list[str]:
    return list(values) if values else ["none"]


def format_report(result: ReviewCardResult) -> str:
    output_text = str(result.output_md) if result.output_created else "not created"
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
    result = build_review_card(args.raw_input_text, args.draft_json, args.output_md)
    print(format_report(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
