import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "fill_invoice_quote_v0_2_separate.py"
EXAMPLE = PROJECT_ROOT / "examples" / "invoice_quote_draft_v0_2_blocks.example.json"
DRAFT_TEST = PROJECT_ROOT / "tests" / "test_fill_invoice_quote_draft.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


separate = cast(
    Any, load_script_module("fill_invoice_quote_v0_2_separate_for_test", SCRIPT)
)
draft_test = cast(
    Any, load_script_module("fill_invoice_quote_draft_helpers", DRAFT_TEST)
)


def example_data() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(EXAMPLE.read_text(encoding="utf-8")),
    )


def base_item(name: str = "ВРУ-А8") -> dict[str, Any]:
    return {
        "name": name,
        "unit": "шт.",
        "quantity": 1,
        "instruments_and_devices": "нужно уточнить",
        "cabinet_type_dimensions_material": "нужно уточнить",
        "price_kzt": None,
        "price_confirmed_by_igor": False,
    }


def minimal_data() -> dict[str, Any]:
    data = example_data()
    data["output_mode"] = "separate_workbooks_by_block"
    blocks = [
        {
            "block_name": "orynbor_8",
            "block_label_for_quote": "Пятно 8",
            "project_code": "нужно уточнить",
            "source_file": "Орынбор 8 Блок.pdf",
            "source_pages": [{"from": 32, "to": 37, "note": "спецификация"}],
            "subsections": [{"subsection_name": None, "items": [base_item("ВРУ-А8")]}],
        },
        {
            "block_name": "orynbor_9",
            "block_label_for_quote": "Пятно 9",
            "project_code": "нужно уточнить",
            "source_file": "Орынбор 9 Блок.pdf",
            "source_pages": [{"from": None, "to": None, "note": "спецификация"}],
            "subsections": [{"subsection_name": None, "items": [base_item("ВРУ-А9")]}],
        },
    ]
    data["project_blocks"] = blocks
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_placeholder_template(path: Path) -> None:
    path.write_bytes(b"placeholder")


def build_plan(tmp_path: Path, data: dict[str, Any]) -> Any:
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    write_placeholder_template(template)
    return separate.build_preflight_plan(input_json, template, output_dir)


def test_valid_example_with_separate_mode_passes_preflight(tmp_path: Path) -> None:
    data = example_data()
    data["output_mode"] = "separate_workbooks_by_block"

    plan = build_plan(tmp_path, data)

    assert plan.output_mode == "separate_workbooks_by_block"
    assert len(plan.planned_outputs) == len(data["project_blocks"])


def test_two_project_blocks_produce_two_output_names(tmp_path: Path) -> None:
    plan = build_plan(tmp_path, minimal_data())

    assert [item.output_path.name for item in plan.planned_outputs] == [
        "invoice_quote_draft_v0_2_orynbor_8.xlsx",
        "invoice_quote_draft_v0_2_orynbor_9.xlsx",
    ]


def test_subsection_name_is_prefixed_to_item_name(tmp_path: Path) -> None:
    data = minimal_data()
    first_block = data["project_blocks"][0]
    first_block["subsections"] = [
        {"subsection_name": "Коммерческие помещения", "items": [base_item("ВРУ-А8")]}
    ]

    plan = build_plan(tmp_path, data)

    assert plan.planned_outputs[0].flat_payload["items"][0]["name"] == (
        "Коммерческие помещения: ВРУ-А8"
    )


def test_single_workbook_sections_mode_returns_error(tmp_path: Path) -> None:
    data = minimal_data()
    data["output_mode"] = "single_workbook_sections"

    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    write_placeholder_template(template)

    try:
        separate.build_preflight_plan(input_json, template, output_dir)
    except separate.SeparateFillError as error:
        assert str(error) == separate.SINGLE_WORKBOOK_ERROR
    else:
        raise AssertionError("single_workbook_sections should fail")


def test_output_dir_inside_git_project_returns_error(tmp_path: Path) -> None:
    data = minimal_data()
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    write_json(input_json, data)
    write_placeholder_template(template)

    try:
        separate.build_preflight_plan(input_json, template, PROJECT_ROOT)
    except separate.SeparateFillError as error:
        assert "output_dir is inside the Git project" in str(error)
    else:
        raise AssertionError("output_dir inside project should fail")


def test_existing_output_file_returns_error(tmp_path: Path) -> None:
    data = minimal_data()
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    write_placeholder_template(template)
    existing_output = output_dir / "invoice_quote_draft_v0_2_orynbor_9.xlsx"
    existing_output.write_bytes(b"existing")

    try:
        separate.build_preflight_plan(input_json, template, output_dir)
    except separate.SeparateFillError as error:
        assert "output already exists" in str(error)
    else:
        raise AssertionError("existing output should fail")


def test_block_with_more_than_five_items_fails_before_output_planning(
    tmp_path: Path,
) -> None:
    data = minimal_data()
    first_block = data["project_blocks"][0]
    first_block["subsections"] = [
        {
            "subsection_name": None,
            "items": [deepcopy(base_item(f"item-{index}")) for index in range(6)],
        }
    ]
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    write_placeholder_template(template)

    try:
        separate.build_preflight_plan(input_json, template, output_dir)
    except separate.SeparateFillError as error:
        assert "block orynbor_8 has more than 5 items." in str(error)
    else:
        raise AssertionError("block with more than 5 items should fail")
    assert list(output_dir.iterdir()) == []


def test_invalid_json_by_validator_returns_error(tmp_path: Path) -> None:
    data = minimal_data()
    del data["project_blocks"]
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    write_placeholder_template(template)

    try:
        separate.build_preflight_plan(input_json, template, output_dir)
    except separate.SeparateFillError as error:
        assert "validation failed" in str(error)
        assert "обязательное поле отсутствует: project_blocks" in str(error)
    else:
        raise AssertionError("invalid v0.2 JSON should fail")
    assert list(output_dir.iterdir()) == []


def test_both_mode_generates_separate_outputs_and_notice(tmp_path: Path) -> None:
    data = minimal_data()
    data["output_mode"] = "both"

    plan = build_plan(tmp_path, data)

    assert plan.output_mode == "both"
    assert plan.single_workbook_notice is not None
    assert len(plan.planned_outputs) == 2


def test_real_excel_generation_uses_temp_output_dir_and_does_not_overwrite(
    tmp_path: Path,
) -> None:
    data = minimal_data()
    input_json = tmp_path / "input.json"
    template = tmp_path / "template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    write_json(input_json, data)
    draft_test.write_template(template)

    exit_code = separate.main(
        [
            "--input-json",
            str(input_json),
            "--template",
            str(template),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    outputs = sorted(output_dir.glob("*.xlsx"))
    assert [item.name for item in outputs] == [
        "invoice_quote_draft_v0_2_orynbor_8.xlsx",
        "invoice_quote_draft_v0_2_orynbor_9.xlsx",
    ]
    first_workbook = load_workbook(outputs[0], data_only=False)
    first_sheet = first_workbook["Счёт-КП шаблон"]
    assert first_sheet["C17"].value == "ВРУ-А8"

    overwrite_code = separate.main(
        [
            "--input-json",
            str(input_json),
            "--template",
            str(template),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert overwrite_code == 1
    assert len(list(output_dir.glob("*.xlsx"))) == 2


def test_failed_generation_removes_registered_temp_output(
    tmp_path: Path, monkeypatch: Any
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    final_output = output_dir / "invoice_quote_draft_v0_2_orynbor_8.xlsx"
    plan = separate.PreflightPlan(
        template=tmp_path / "template.xlsx",
        output_dir=output_dir,
        output_mode="separate_workbooks_by_block",
        planned_outputs=(
            separate.PlannedOutput(
                block_name="orynbor_8",
                block_label_for_quote="Пятно 8",
                output_path=final_output,
                flat_payload={},
            ),
        ),
    )

    def fail_after_creating_temp(
        _template: Path, output: Path, _payload: dict[str, Any]
    ) -> None:
        output.write_bytes(b"partial workbook")
        raise separate.SeparateFillError("simulated generation failure")

    monkeypatch.setattr(separate, "generate_workbook", fail_after_creating_temp)

    try:
        separate.generate_outputs(plan)
    except separate.SeparateFillError as error:
        assert "simulated generation failure" in str(error)
    else:
        raise AssertionError("generation failure should fail")

    assert not final_output.exists()
    assert list(output_dir.iterdir()) == []
