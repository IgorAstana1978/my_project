import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "validate_invoice_quote_v0_2.py"
EXAMPLE = PROJECT_ROOT / "examples" / "invoice_quote_draft_v0_2_blocks.example.json"


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_invoice_quote_v0_2_for_test", SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validator = cast(Any, load_validator_module())


def valid_data() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(EXAMPLE.read_text(encoding="utf-8")),
    )


def validate(data: dict[str, Any]) -> Any:
    return validator.validate_invoice_quote_v0_2(data)


def assert_has_error(data: dict[str, Any], expected: str) -> None:
    result = validate(data)

    assert not result.is_valid
    assert any(expected in error for error in result.errors), result.errors


def first_block(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], data["project_blocks"][0])


def first_subsection(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], first_block(data)["subsections"][0])


def first_item(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], first_subsection(data)["items"][0])


def test_valid_example_passes_validation() -> None:
    result = validate(valid_data())

    assert result.is_valid
    assert result.errors == []
    assert result.warnings == []


def test_invalid_output_mode_returns_error() -> None:
    data = valid_data()
    data["output_mode"] = "xlsx_everywhere"

    assert_has_error(data, "output_mode должен быть одним из")


def test_empty_project_blocks_returns_error() -> None:
    data = valid_data()
    data["project_blocks"] = []

    assert_has_error(data, "project_blocks должен быть непустым списком")


def test_empty_block_name_returns_error() -> None:
    data = valid_data()
    first_block(data)["block_name"] = ""

    assert_has_error(data, "block_name должен быть непустой строкой")


def test_empty_block_label_for_quote_returns_error() -> None:
    data = valid_data()
    first_block(data)["block_label_for_quote"] = ""

    assert_has_error(data, "block_label_for_quote должен быть непустой строкой")


def test_source_pages_from_greater_than_to_returns_error() -> None:
    data = valid_data()
    source_page = cast(dict[str, Any], first_block(data)["source_pages"][0])
    source_page["from"] = 40
    source_page["to"] = 32

    assert_has_error(data, "from не должен быть больше .to")


def test_subsection_without_items_returns_error() -> None:
    data = valid_data()
    del first_subsection(data)["items"]

    assert_has_error(data, "обязательное поле отсутствует")


def test_empty_subsection_items_returns_warning() -> None:
    data = valid_data()
    first_subsection(data)["items"] = []

    result = validate(data)

    assert result.is_valid
    assert any("items пустой" in warning for warning in result.warnings)


def test_item_without_name_returns_error() -> None:
    data = valid_data()
    first_item(data)["name"] = ""

    assert_has_error(data, "name должен быть непустой строкой")


def test_quantity_zero_returns_error() -> None:
    data = valid_data()
    first_item(data)["quantity"] = 0

    assert_has_error(data, "quantity должен быть числом больше 0")


def test_price_set_but_not_confirmed_returns_error() -> None:
    data = valid_data()
    first_item(data)["price_kzt"] = 1000
    first_item(data)["price_confirmed_by_igor"] = False

    assert_has_error(data, "price_kzt задан, но price_confirmed_by_igor = false")


def test_null_price_but_confirmed_returns_error() -> None:
    data = valid_data()
    first_item(data)["price_kzt"] = None
    first_item(data)["price_confirmed_by_igor"] = True

    assert_has_error(data, "price_kzt = null, но price_confirmed_by_igor = true")


def test_draft_only_false_returns_error() -> None:
    data = valid_data()
    safety_flags = cast(dict[str, Any], data["safety_flags"])
    safety_flags["draft_only"] = False

    assert_has_error(data, "safety_flags.draft_only должен быть true")


def test_do_not_add_excel_to_git_false_returns_error() -> None:
    data = valid_data()
    safety_flags = cast(dict[str, Any], data["safety_flags"])
    safety_flags["do_not_add_excel_to_git"] = False

    assert_has_error(data, "safety_flags.do_not_add_excel_to_git должен быть true")


def test_valid_data_helper_returns_independent_copy() -> None:
    first = valid_data()
    second = valid_data()
    first["project_blocks"] = []

    assert second["project_blocks"] != []
    assert deepcopy(second) == second
