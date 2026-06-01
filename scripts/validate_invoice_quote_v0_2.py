"""Validate invoice-quote v0.2 JSON contracts without generating Excel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ALLOWED_OUTPUT_MODES = {
    "single_workbook_sections",
    "separate_workbooks_by_block",
    "both",
}
REQUIRED_TOP_LEVEL_FIELDS = (
    "document",
    "customer",
    "project",
    "output_mode",
    "project_blocks",
    "commercial_terms",
    "safety_flags",
    "metadata",
)
REQUIRED_BLOCK_FIELDS = (
    "block_name",
    "block_label_for_quote",
    "project_code",
    "source_file",
    "source_pages",
    "subsections",
)
REQUIRED_SOURCE_PAGE_FIELDS = ("from", "to", "note")
REQUIRED_ITEM_FIELDS = (
    "name",
    "unit",
    "quantity",
    "instruments_and_devices",
    "cabinet_type_dimensions_material",
    "price_kzt",
    "price_confirmed_by_igor",
)


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def field_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def require_mapping(
    value: Any, path: str, result: ValidationResult
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        result.add_error(f"{path} должен быть объектом")
        return None
    return value


def require_list(
    value: Any, path: str, result: ValidationResult
) -> Sequence[Any] | None:
    if not isinstance(value, list):
        result.add_error(f"{path} должен быть списком")
        return None
    return value


def require_field(data: Mapping[str, Any], key: str, path: str) -> bool:
    return key in data


def require_fields(
    data: Mapping[str, Any],
    keys: Sequence[str],
    path: str,
    result: ValidationResult,
) -> None:
    for key in keys:
        if not require_field(data, key, path):
            result.add_error(f"обязательное поле отсутствует: {field_path(path, key)}")


def validate_output_mode(data: Mapping[str, Any], result: ValidationResult) -> None:
    output_mode = data.get("output_mode")
    if output_mode not in ALLOWED_OUTPUT_MODES:
        allowed = ", ".join(sorted(ALLOWED_OUTPUT_MODES))
        result.add_error(f"output_mode должен быть одним из: {allowed}")


def validate_source_pages(
    source_pages: Any, path: str, result: ValidationResult
) -> None:
    pages = require_list(source_pages, path, result)
    if pages is None:
        return

    for index, raw_page in enumerate(pages):
        page_path = f"{path}[{index}]"
        page = require_mapping(raw_page, page_path, result)
        if page is None:
            continue

        require_fields(page, REQUIRED_SOURCE_PAGE_FIELDS, page_path, result)
        if not all(key in page for key in REQUIRED_SOURCE_PAGE_FIELDS):
            continue

        page_from = page["from"]
        page_to = page["to"]
        note = page["note"]
        if page_from is not None and not is_number(page_from):
            result.add_error(f"{page_path}.from должен быть числом или null")
        if page_to is not None and not is_number(page_to):
            result.add_error(f"{page_path}.to должен быть числом или null")
        if not isinstance(note, str):
            result.add_error(f"{page_path}.note должен быть строкой")
        if is_number(page_from) and is_number(page_to) and page_from > page_to:
            result.add_error(f"{page_path}.from не должен быть больше .to")


def validate_item(raw_item: Any, path: str, result: ValidationResult) -> None:
    item = require_mapping(raw_item, path, result)
    if item is None:
        return

    require_fields(item, REQUIRED_ITEM_FIELDS, path, result)
    if not all(key in item for key in REQUIRED_ITEM_FIELDS):
        return

    if not is_non_empty_string(item["name"]):
        result.add_error(f"{path}.name должен быть непустой строкой")
    if not is_non_empty_string(item["unit"]):
        result.add_error(f"{path}.unit должен быть непустой строкой")
    if not is_number(item["quantity"]) or item["quantity"] <= 0:
        result.add_error(f"{path}.quantity должен быть числом больше 0")
    if not isinstance(item["instruments_and_devices"], str):
        result.add_error(f"{path}.instruments_and_devices должен быть строкой")
    if not isinstance(item["cabinet_type_dimensions_material"], str):
        result.add_error(f"{path}.cabinet_type_dimensions_material должен быть строкой")

    price = item["price_kzt"]
    price_confirmed = item["price_confirmed_by_igor"]
    if price is not None and not is_number(price):
        result.add_error(f"{path}.price_kzt должен быть числом или null")
    if not isinstance(price_confirmed, bool):
        result.add_error(f"{path}.price_confirmed_by_igor должен быть boolean")
        return
    if is_number(price) and not price_confirmed:
        result.add_error(f"{path}.price_kzt задан, но price_confirmed_by_igor = false")
    if price is None and price_confirmed:
        result.add_error(f"{path}.price_kzt = null, но price_confirmed_by_igor = true")


def validate_subsections(subsections: Any, path: str, result: ValidationResult) -> None:
    subsection_list = require_list(subsections, path, result)
    if subsection_list is None:
        return
    if not subsection_list:
        result.add_error(f"{path} должен быть непустым списком")
        return

    for index, raw_subsection in enumerate(subsection_list):
        subsection_path = f"{path}[{index}]"
        subsection = require_mapping(raw_subsection, subsection_path, result)
        if subsection is None:
            continue

        require_fields(
            subsection,
            ("subsection_name", "items"),
            subsection_path,
            result,
        )
        if "subsection_name" in subsection and not (
            subsection["subsection_name"] is None
            or isinstance(subsection["subsection_name"], str)
        ):
            result.add_error(
                f"{subsection_path}.subsection_name должен быть строкой или null"
            )

        if "items" not in subsection:
            continue
        items = require_list(subsection["items"], f"{subsection_path}.items", result)
        if items is None:
            continue
        if not items:
            result.add_warning(f"{subsection_path}.items пустой")
        for item_index, item in enumerate(items):
            validate_item(item, f"{subsection_path}.items[{item_index}]", result)


def validate_project_blocks(
    project_blocks: Any, path: str, result: ValidationResult
) -> None:
    blocks = require_list(project_blocks, path, result)
    if blocks is None:
        return
    if not blocks:
        result.add_error("project_blocks должен быть непустым списком")
        return

    for index, raw_block in enumerate(blocks):
        block_path = f"{path}[{index}]"
        block = require_mapping(raw_block, block_path, result)
        if block is None:
            continue

        require_fields(block, REQUIRED_BLOCK_FIELDS, block_path, result)
        if not all(key in block for key in REQUIRED_BLOCK_FIELDS):
            continue

        if not is_non_empty_string(block["block_name"]):
            result.add_error(f"{block_path}.block_name должен быть непустой строкой")
        if not is_non_empty_string(block["block_label_for_quote"]):
            result.add_error(
                f"{block_path}.block_label_for_quote должен быть непустой строкой"
            )
        if not isinstance(block["project_code"], str):
            result.add_error(f"{block_path}.project_code должен быть строкой")
        if not isinstance(block["source_file"], str):
            result.add_error(f"{block_path}.source_file должен быть строкой")

        validate_source_pages(
            block["source_pages"],
            f"{block_path}.source_pages",
            result,
        )
        validate_subsections(block["subsections"], f"{block_path}.subsections", result)


def validate_safety_flags(
    safety_flags: Any, path: str, result: ValidationResult
) -> None:
    flags = require_mapping(safety_flags, path, result)
    if flags is None:
        return

    required_true_flags = (
        "draft_only",
        "do_not_add_excel_to_git",
        "prices_require_igor_confirmation",
        "delivery_requires_igor_confirmation",
    )
    for flag in required_true_flags:
        if flags.get(flag) is not True:
            result.add_error(f"{field_path(path, flag)} должен быть true")

    source_verified = flags.get("source_data_manually_verified")
    if not isinstance(source_verified, bool):
        result.add_error(f"{path}.source_data_manually_verified должен быть boolean")


def validate_metadata(metadata: Any, path: str, result: ValidationResult) -> None:
    metadata_map = require_mapping(metadata, path, result)
    if metadata_map is None:
        return

    if not isinstance(metadata_map.get("schema_version"), str):
        result.add_error(f"{path}.schema_version должен быть строкой")
    if not isinstance(metadata_map.get("source_type"), str):
        result.add_error(f"{path}.source_type должен быть строкой")
    if not isinstance(metadata_map.get("reviewed_by_igor"), bool):
        result.add_error(f"{path}.reviewed_by_igor должен быть boolean")


def validate_invoice_quote_v0_2(data: Mapping[str, Any]) -> ValidationResult:
    result = ValidationResult()
    require_fields(data, REQUIRED_TOP_LEVEL_FIELDS, "", result)

    for key in (
        "document",
        "customer",
        "project",
        "commercial_terms",
    ):
        if key in data:
            require_mapping(data[key], key, result)

    if "output_mode" in data:
        validate_output_mode(data, result)
    if "project_blocks" in data:
        validate_project_blocks(data["project_blocks"], "project_blocks", result)
    if "safety_flags" in data:
        validate_safety_flags(data["safety_flags"], "safety_flags", result)
    if "metadata" in data:
        validate_metadata(data["metadata"], "metadata", result)

    return result
