import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight_quote_commercial_input.py"


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
    load_script_module("preflight_quote_commercial_input_for_test", SCRIPT),
)


def valid_row(index: int = 1, vat_mode: str = "yes") -> list[str]:
    return [
        f"SYNTHETIC-ITEM-{index}",
        "шт.",
        str(index),
        "SYNTHETIC-DEVICES",
        "SYNTHETIC-CABINET",
        str(index * 1000),
        vat_mode,
        "yes",
    ]


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


def report_for(path: Path) -> str:
    result = preflight.preflight(path)
    return cast(str, preflight.format_report(result))


def assert_status(path: Path, expected: str) -> str:
    report = report_for(path)
    assert f"Status:\n{expected}" in report
    return report


def test_valid_one_row_passes(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [valid_row()])

    report = assert_status(csv_path, "PASS")

    assert "Rows:\n1" in report
    assert "Columns:\nstrict 8 columns" in report
    assert "unit price positive integer: pass" in report
    assert "VAT consistent: pass" in report
    assert "price confirmation: pass" in report
    assert preflight.PASS_NEXT in report
    assert "Manual Igor check:\nrequired" in report


def test_valid_multiple_rows_pass(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [valid_row(index, "no") for index in range(1, 4)])

    report = assert_status(csv_path, "PASS")

    assert "Rows:\n3" in report
    assert "VAT value: pass" in report
    assert "VAT consistent: pass" in report


def test_missing_header_column_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    header = list(preflight.REQUIRED_COLUMNS[:-1])
    write_csv(csv_path, [valid_row()[:-1]], header)

    report = assert_status(csv_path, "FAIL")

    assert "header missing columns: price_confirmed_by_igor" in report


def test_extra_header_column_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    header = [*preflight.REQUIRED_COLUMNS, "unknown"]
    write_csv(csv_path, [valid_row() + ["x"]], header)

    report = assert_status(csv_path, "FAIL")

    assert "header has unknown or extra columns: unknown" in report


def test_wrong_header_order_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    header = list(preflight.REQUIRED_COLUMNS)
    header[0], header[1] = header[1], header[0]
    row = valid_row()
    row[0], row[1] = row[1], row[0]
    write_csv(csv_path, [row], header)

    report = assert_status(csv_path, "FAIL")

    assert "header order does not match strict commercial contract" in report


def test_duplicate_header_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    header = [*preflight.REQUIRED_COLUMNS, "name"]
    write_csv(csv_path, [valid_row() + ["duplicate"]], header)

    report = assert_status(csv_path, "FAIL")

    assert "header contains duplicate columns: name" in report


@pytest.mark.parametrize("quantity", ["0", "-1", "1.5"])
def test_invalid_quantity_fails(
    quantity: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[2] = quantity
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: quantity must be a positive integer" in report


@pytest.mark.parametrize(
    "price",
    ["", "0", "-1", "1.5", "1,5", "1e3", " 100", "100 ", "1 000"],
)
def test_invalid_price_fails(
    price: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[5] = price
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    if price == "":
        assert "row 2: unit_price_kzt is required" in report
    assert "row 2: unit_price_kzt must be a positive integer" in report


@pytest.mark.parametrize(
    "confirmation",
    ["", "no", "Yes", "YES", "true", "1", " yes", "yes "],
)
def test_price_confirmation_must_be_exact_yes(
    confirmation: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[7] = confirmation
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: price_confirmed_by_igor must be exact yes" in report


@pytest.mark.parametrize(
    "vat_mode",
    ["", "Yes", "NO", "true", "1", " yes", "no "],
)
def test_vat_mode_must_be_exact_yes_or_no(
    vat_mode: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[6] = vat_mode
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "row 2: price_includes_vat must be exact yes or no" in report


def test_mixed_vat_mode_fails(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [valid_row(1, "yes"), valid_row(2, "no")])

    report = assert_status(csv_path, "FAIL")

    assert "price_includes_vat must be consistent across all rows" in report
    assert "VAT consistent: fail" in report


@pytest.mark.parametrize(
    "column",
    [
        "client_ready",
        "send_to_client",
        "approved_for_client",
        "ready_for_customer",
        "отправить_клиенту",
    ],
)
def test_forbidden_client_control_column_fails(
    column: str,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    header = [*preflight.REQUIRED_COLUMNS, column]
    write_csv(csv_path, [valid_row() + ["yes"]], header)

    report = assert_status(csv_path, "FAIL")

    assert "forbidden client-control column detected" in report
    assert "client-control columns: fail" in report


@pytest.mark.parametrize("column_index", [0, 1, 3, 4])
def test_required_text_field_fails_when_empty(
    column_index: int,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[column_index] = ""
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    column = preflight.REQUIRED_COLUMNS[column_index]
    assert f"row 2: {column} is required" in report


def test_zero_rows_fail(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [])

    report = assert_status(csv_path, "FAIL")

    assert "row count must be 1-100" in report


def test_101_rows_fail(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [valid_row(index) for index in range(1, 102)])

    report = assert_status(csv_path, "FAIL")

    assert "row count must be 1-100" in report


def test_report_does_not_print_rows_or_prices(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    row = valid_row()
    row[0] = "SECRET-SYNTHETIC-CLIENT-ITEM"
    row[3] = "SECRET-SYNTHETIC-DEVICES"
    row[5] = "987654321"
    row[7] = "no"
    write_csv(csv_path, [row])

    report = assert_status(csv_path, "FAIL")

    assert "SECRET-SYNTHETIC-CLIENT-ITEM" not in report
    assert "SECRET-SYNTHETIC-DEVICES" not in report
    assert "987654321" not in report
    assert ";".join(row) not in report


def test_input_inside_repo_fails(tmp_path: Path, monkeypatch: Any) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(preflight, "PROJECT_ROOT", repo_root)
    csv_path = repo_root / "commercial.csv"
    write_csv(csv_path, [valid_row()])

    report = assert_status(csv_path, "FAIL")

    assert "outside Git: fail" in report
    assert "input CSV must be outside the Git project" in report


def test_report_markers_present(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(preflight, "PROJECT_ROOT", tmp_path / "repo")
    csv_path = tmp_path / "commercial.csv"
    write_csv(csv_path, [valid_row()])

    report = report_for(csv_path)

    assert report.startswith("COMMERCIAL_QUOTE_INPUT_PREFLIGHT_REPORT_START")
    assert report.endswith("COMMERCIAL_QUOTE_INPUT_PREFLIGHT_REPORT_END")


def test_cli_exit_codes_match_status(tmp_path: Path) -> None:
    pass_csv = tmp_path / "pass.csv"
    fail_csv = tmp_path / "fail.csv"
    write_csv(pass_csv, [valid_row()])
    failing_row = valid_row()
    failing_row[5] = "1.5"
    write_csv(fail_csv, [failing_row])

    pass_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(pass_csv)],
        capture_output=True,
        text=True,
        check=False,
    )
    fail_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(fail_csv)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert pass_result.returncode == 0
    assert "Status:\nPASS" in pass_result.stdout
    assert fail_result.returncode == 1
    assert "Status:\nFAIL" in fail_result.stdout
    assert "1.5" not in fail_result.stdout
