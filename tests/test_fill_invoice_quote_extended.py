import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "fill_invoice_quote_extended.py"
DRAFT_SCRIPT = PROJECT_ROOT / "scripts" / "fill_invoice_quote_draft.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


extended = cast(Any, load_script_module("fill_invoice_quote_extended_for_test", SCRIPT))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extended_layout(capacity: int = 8) -> Any:
    return extended.ExtendedLayout(
        item_start_row=17,
        item_end_row=17 + capacity - 1,
        capacity=capacity,
        total_row=17 + capacity,
        signature_range=f"B{20 + capacity}:I{22 + capacity}",
        header_ranges=("C2:I6", "B4:B6"),
        formula_cells=tuple(
            [f"I{row}" for row in range(17, 17 + capacity)] + [f"I{17 + capacity}"]
        ),
    )


def write_extended_template(path: Path, capacity: int = 8) -> Any:
    layout = extended_layout(capacity)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = extended.SHEET_NAME

    for row in range(2, 7):
        for column in range(3, 10):
            worksheet.cell(row=row, column=column).value = f"header-{row}-{column}"
    for row in range(4, 7):
        worksheet.cell(row=row, column=2).value = f"req-{row}"

    worksheet.merge_cells(layout.signature_range)
    worksheet.cell(row=20 + capacity, column=2).value = "signature"

    for row in range(layout.item_start_row, layout.item_end_row + 1):
        worksheet[f"C{row}"] = "template item"
        worksheet[f"D{row}"] = "шт"
        worksheet[f"E{row}"] = 1
        worksheet[f"F{row}"] = "template instruments"
        worksheet[f"G{row}"] = "template cabinet"
        worksheet[f"H{row}"] = "template price"
        worksheet[f"I{row}"] = f"=E{row}*H{row}"
    worksheet[f"I{layout.total_row}"] = (
        f"=SUM(I{layout.item_start_row}:I{layout.item_end_row})"
    )

    workbook.save(path)
    return layout


def item(index: int) -> dict[str, Any]:
    return {
        "name": f"ВРУ-{index}",
        "unit": "шт.",
        "quantity": index,
        "instruments_and_devices": "нужно уточнить",
        "cabinet_type_dimensions_material": "нужно уточнить",
        "price_kzt": None,
        "price_confirmed_by_igor": False,
    }


def payload(items_count: int) -> dict[str, Any]:
    return {"items": [item(index) for index in range(1, items_count + 1)]}


def layout_json(layout: Any) -> dict[str, Any]:
    return {
        "item_start_row": layout.item_start_row,
        "item_end_row": layout.item_end_row,
        "capacity": layout.capacity,
        "total_row": layout.total_row,
        "signature_range": layout.signature_range,
        "header_ranges": list(layout.header_ranges),
        "formula_cells": list(layout.formula_cells),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def cli_args(
    payload_json: Path,
    layout_json_path: Path,
    template: Path,
    output: Path,
) -> list[str]:
    return [
        "--payload-json",
        str(payload_json),
        "--layout-json",
        str(layout_json_path),
        "--template",
        str(template),
        "--output",
        str(output),
    ]


def workbook_values(path: Path) -> dict[str, Any]:
    workbook = load_workbook(path, data_only=False)
    worksheet = workbook[extended.SHEET_NAME]
    return {
        "C17": worksheet["C17"].value,
        "C22": worksheet["C22"].value,
        "I17": worksheet["I17"].value,
        "I25": worksheet["I25"].value,
        "B28": worksheet["B28"].value,
        "C2": worksheet["C2"].value,
    }


def merged_ranges(path: Path) -> tuple[str, ...]:
    workbook = load_workbook(path, data_only=False)
    worksheet = workbook[extended.SHEET_NAME]
    return tuple(str(item) for item in worksheet.merged_cells.ranges)


def test_extended_template_is_created_in_tmp_path(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"

    layout = write_extended_template(template)

    assert template.is_file()
    assert not template.is_relative_to(PROJECT_ROOT)
    assert layout.capacity == 8


def test_writes_six_items_to_extended_template(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)

    result = extended.generate_extended_workbook(
        template=template,
        output=output,
        payload=payload(6),
        layout=layout,
    )

    assert result == output
    assert output.is_file()
    values = workbook_values(output)
    assert values["C17"] == "ВРУ-1"
    assert values["C22"] == "ВРУ-6"
    assert values["I17"] == "=E17*H17"
    assert values["I25"] == "=SUM(I17:I24)"
    assert values["B28"] == "signature"
    assert values["C2"] == "header-2-3"


def test_merged_ranges_are_preserved_after_generation(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    before = merged_ranges(template)

    extended.generate_extended_workbook(
        template=template,
        output=output,
        payload=payload(6),
        layout=layout,
    )

    assert before == (layout.signature_range,)
    assert merged_ranges(output) == before


def test_merged_range_change_fails_closed_and_removes_temp_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    original_fill_item_rows = extended.fill_item_rows

    def fill_and_change_merged_ranges(
        worksheet: Any,
        items: Any,
        layout: Any,
    ) -> None:
        original_fill_item_rows(worksheet, items, layout)
        worksheet.merge_cells("B31:C31")

    monkeypatch.setattr(extended, "fill_item_rows", fill_and_change_merged_ranges)

    try:
        extended.generate_extended_workbook(
            template=template,
            output=output,
            payload=payload(6),
            layout=layout,
        )
    except extended.ExtendedFillError as error:
        assert "merged ranges changed" in str(error)
    else:
        raise AssertionError("merged range change should fail")

    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_successfully_creates_output_for_six_items(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    write_json(payload_json, payload(6))
    write_json(layout_json_path, layout_json(layout))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 0
    assert output.is_file()
    assert workbook_values(output)["C22"] == "ВРУ-6"


def test_cli_capacity_overflow_returns_one_without_output(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template, capacity=6)
    write_json(payload_json, payload(7))
    write_json(layout_json_path, layout_json(layout))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_existing_output_returns_one_without_overwrite(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    output.write_bytes(b"existing")
    layout = write_extended_template(template)
    write_json(payload_json, payload(6))
    write_json(layout_json_path, layout_json(layout))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert output.read_bytes() == b"existing"
    assert list(output_dir.iterdir()) == [output]


def test_cli_missing_payload_json_returns_one(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "missing_payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    write_json(layout_json_path, layout_json(layout))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_invalid_payload_json_returns_one(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    payload_json.write_text("{invalid", encoding="utf-8")
    write_json(layout_json_path, layout_json(layout))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_missing_layout_json_returns_one(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "missing_layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    write_extended_template(template)
    write_json(payload_json, payload(6))

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_invalid_layout_json_returns_one(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    write_extended_template(template)
    write_json(payload_json, payload(6))
    layout_json_path.write_text("{invalid", encoding="utf-8")

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_cli_removes_temp_output_when_generation_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    payload_json = tmp_path / "payload.json"
    layout_json_path = tmp_path / "layout.json"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)
    write_json(payload_json, payload(6))
    write_json(layout_json_path, layout_json(layout))

    def fail_verification(
        _output: Path,
        _layout: Any,
        _before: Any,
    ) -> None:
        raise extended.ExtendedFillError("forced verification failure")

    monkeypatch.setattr(extended, "verify_output", fail_verification)

    exit_code = extended.main(
        cli_args(payload_json, layout_json_path, template, output)
    )

    assert exit_code == 1
    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_items_above_capacity_stop_before_output(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template, capacity=6)

    try:
        extended.generate_extended_workbook(
            template=template,
            output=output,
            payload=payload(7),
            layout=layout,
        )
    except extended.ExtendedFillError as error:
        assert "items count 7 exceeds layout capacity 6" in str(error)
    else:
        raise AssertionError("items above capacity should fail")

    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    output = tmp_path / "out" / "draft.xlsx"
    output.parent.mkdir()
    output.write_bytes(b"existing")
    layout = write_extended_template(template)

    try:
        extended.generate_extended_workbook(
            template=template,
            output=output,
            payload=payload(6),
            layout=layout,
        )
    except extended.ExtendedFillError as error:
        assert "output already exists" in str(error)
    else:
        raise AssertionError("existing output should fail")

    assert output.read_bytes() == b"existing"
    assert list(output.parent.iterdir()) == [output]


def test_temp_output_is_removed_when_verification_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    layout = write_extended_template(template)

    def fail_verification(
        _output: Path,
        _layout: Any,
        _before: Any,
    ) -> None:
        raise extended.ExtendedFillError("forced verification failure")

    monkeypatch.setattr(extended, "verify_output", fail_verification)

    try:
        extended.generate_extended_workbook(
            template=template,
            output=output,
            payload=payload(6),
            layout=layout,
        )
    except extended.ExtendedFillError as error:
        assert "forced verification failure" in str(error)
    else:
        raise AssertionError("verification failure should fail")

    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_layout_fails_closed_before_output(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    output = output_dir / "draft.xlsx"
    write_extended_template(template)
    bad_layout = extended.ExtendedLayout(
        item_start_row=17,
        item_end_row=20,
        capacity=6,
        total_row=21,
        signature_range="B28:I30",
        header_ranges=("C2:I6",),
        formula_cells=("I17",),
    )

    try:
        extended.generate_extended_workbook(
            template=template,
            output=output,
            payload=payload(6),
            layout=bad_layout,
        )
    except extended.ExtendedFillError as error:
        assert "layout capacity must equal" in str(error)
    else:
        raise AssertionError("conflicting layout should fail")

    assert not output.exists()
    assert list(output_dir.iterdir()) == []


def test_old_mvp_sha256_stays_unchanged(tmp_path: Path) -> None:
    before = file_sha256(DRAFT_SCRIPT)
    template = tmp_path / "extended_template.xlsx"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    layout = write_extended_template(template)

    extended.generate_extended_workbook(
        template=template,
        output=output_dir / "draft.xlsx",
        payload=payload(6),
        layout=layout,
    )

    assert file_sha256(DRAFT_SCRIPT) == before


def test_no_real_xlsx_or_manifest_files_are_added_to_git() -> None:
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_paths = [
        line[3:].strip() for line in status.stdout.splitlines() if line.strip()
    ]
    assert not any(path.endswith(".xlsx") for path in changed_paths)
    assert not any(
        Path(path).name.casefold() == "manifest.json" for path in changed_paths
    )
