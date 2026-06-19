import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_quote_input.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


preflight = cast(
    Any,
    load_script_module("preflight_quote_input_for_test", SCRIPT),
)


def write_csv(
    path: Path,
    rows: list[list[str]],
    header: list[str] | None = None,
) -> None:
    fieldnames = header or list(preflight.REQUIRED_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, delimiter=";", lineterminator="\n")
        writer.writerow(fieldnames)
        writer.writerows(rows)


def item_row(index: int) -> list[str]:
    return [
        f"ВРУ-{index}",
        "шт.",
        str(index),
        "synthetic devices",
        "synthetic cabinet",
    ]


def report_for(path: Path) -> str:
    return cast(str, preflight.format_report(preflight.preflight(path)))


def assert_status(path: Path, expected: str) -> str:
    report = report_for(path)
    assert f"Status:\n{expected}" in report
    return report


def test_valid_one_row_passes(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(1)])

    report = assert_status(csv_path, "PASS")

    assert "Rows:\n1" in report
    assert "Columns:\nstrict 5 columns" in report
    assert "commercial data scan: pass" in report
    assert "draft output: skip" in report


def test_valid_three_rows_pass(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(index) for index in range(1, 4)])

    report = assert_status(csv_path, "PASS")

    assert "Rows:\n3" in report
    assert "commercial data scan: pass" in report


def test_valid_100_rows_pass(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(index) for index in range(1, 101)])

    report = assert_status(csv_path, "PASS")

    assert "Rows:\n100" in report
    assert "commercial data scan: pass" in report


def test_zero_rows_fail(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [])

    report = assert_status(csv_path, "FAIL")

    assert "row count: fail" in report


def test_101_rows_fail(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(index) for index in range(1, 102)])

    report = assert_status(csv_path, "FAIL")

    assert "row count must be 1-100" in report


def test_wrong_header_order_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(
        csv_path,
        [["шт.", "ВРУ-1", "1", "synthetic devices", "synthetic cabinet"]],
        header=[
            "unit",
            "name",
            "quantity",
            "instruments_and_devices",
            "cabinet_type_dimensions_material",
        ],
    )

    report = assert_status(csv_path, "FAIL")

    assert "header order does not match strict CSV contract" in report


def test_missing_column_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(
        csv_path,
        [["ВРУ-1", "шт.", "1", "synthetic devices"]],
        header=["name", "unit", "quantity", "instruments_and_devices"],
    )

    report = assert_status(csv_path, "FAIL")

    assert "header missing columns: cabinet_type_dimensions_material" in report


def test_extra_commercial_column_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(
        csv_path,
        [item_row(1) + ["1000", "1000"]],
        header=list(preflight.REQUIRED_COLUMNS) + ["price", "Сумма"],
    )

    report = assert_status(csv_path, "FAIL")

    assert "commercial column detected in header" in report
    assert "1000;1000" not in report


def test_non_integer_quantity_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    row = item_row(1)
    row[2] = "1.5"
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: quantity must be an integer" in report


def test_empty_required_name_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    row = item_row(1)
    row[0] = ""
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: name is required" in report


def test_empty_optional_columns_warn_not_fail(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    row = item_row(1)
    row[3] = ""
    row[4] = ""
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "WARN")

    assert "row 2: instruments_and_devices is empty" in report
    assert "row 2: cabinet_type_dimensions_material is empty" in report
    assert "Next:\nsafe to run make_quote_capacity100.ps1" in report


def test_commercial_token_in_data_row_fails_without_full_row(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    row = item_row(1)
    row[3] = "synthetic devices payment 1000; bank secret"
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: commercial token detected in instruments_and_devices" in report
    assert "synthetic devices payment 1000; bank secret" not in report


def test_input_inside_repo_fails(tmp_path: Path, monkeypatch: Any) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(preflight, "PROJECT_ROOT", repo_root)
    csv_path = repo_root / "items.csv"
    write_csv(csv_path, [item_row(1)])

    report = assert_status(csv_path, "FAIL")

    assert "outside Git: fail" in report


def test_report_markers_present(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(1)])

    report = report_for(csv_path)

    assert report.startswith("QUOTE_INPUT_PREFLIGHT_REPORT_START")
    assert report.endswith("QUOTE_INPUT_PREFLIGHT_REPORT_END")


def test_report_does_not_include_full_row_contents_or_client_data(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    row = ["Client secret item", "шт.", "bad", "bank details 1000", "cabinet"]
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "Client secret item" not in report
    assert "bank details 1000" not in report


def test_cli_exit_code_matches_fail_status(tmp_path: Path) -> None:
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(csv_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Status:\nFAIL" in result.stdout


def test_draft_output_omitted_is_skipped(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    write_csv(csv_path, [item_row(1)])

    report = assert_status(csv_path, "PASS")

    assert "draft output: skip" in report


def test_valid_draft_output_outside_git_passes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    output_path = tmp_path / "draft.xlsx"
    write_csv(csv_path, [item_row(1)])

    result = preflight.preflight(csv_path, output_path)
    report = preflight.format_report(result)

    assert "Status:\nPASS" in report
    assert "draft output: pass" in report
    assert f'.\\scripts\\make_quote_capacity100.ps1 "{csv_path.resolve()}"' in report
    assert str(output_path.resolve()) in report


def test_draft_output_inside_repo_fails(tmp_path: Path, monkeypatch: Any) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(preflight, "PROJECT_ROOT", repo_root)
    csv_path = tmp_path / "items.csv"
    output_path = repo_root / "draft.xlsx"
    write_csv(csv_path, [item_row(1)])

    result = preflight.preflight(csv_path, output_path)
    report = preflight.format_report(result)

    assert "Status:\nFAIL" in report
    assert "draft output: fail" in report
    assert "draft output must be outside the Git project" in report


def test_draft_output_wrong_suffix_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    output_path = tmp_path / "draft.xls"
    write_csv(csv_path, [item_row(1)])

    result = preflight.preflight(csv_path, output_path)
    report = preflight.format_report(result)

    assert "Status:\nFAIL" in report
    assert "draft output suffix must be .xlsx" in report


def test_draft_output_missing_parent_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    output_path = tmp_path / "missing" / "draft.xlsx"
    write_csv(csv_path, [item_row(1)])

    result = preflight.preflight(csv_path, output_path)
    report = preflight.format_report(result)

    assert "Status:\nFAIL" in report
    assert "draft output parent directory does not exist" in report


def test_draft_output_existing_file_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.csv"
    output_path = tmp_path / "draft.xlsx"
    write_csv(csv_path, [item_row(1)])
    output_path.write_text("existing synthetic output", encoding="utf-8")

    result = preflight.preflight(csv_path, output_path)
    report = preflight.format_report(result)

    assert "Status:\nFAIL" in report
    assert "draft output file already exists" in report


def test_draft_output_same_as_input_path_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "items.xlsx"
    write_csv(csv_path, [item_row(1)])

    result = preflight.preflight(csv_path, csv_path)
    report = preflight.format_report(result)

    assert "Status:\nFAIL" in report
    assert "draft output must not equal input CSV path" in report
