import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "extract_legacy_xls_items_to_csv.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


extractor = cast(
    Any,
    load_script_module("extract_legacy_xls_items_to_csv_for_test", SCRIPT),
)


def matrix(rows: list[list[str]]) -> list[Any]:
    return [
        extractor.SheetMatrix(
            name="Sheet1",
            rows=tuple(tuple(row) for row in rows),
        )
    ]


def header() -> list[str]:
    return [
        "Наименование",
        "Ед. изм.",
        "Количество",
        "Приборы и аппараты",
        "Тип шкафа / габариты / материал",
    ]


def item_row(index: int) -> list[str]:
    return [
        f"ВРУ-{index}",
        "шт.",
        str(index),
        f"приборы-{index}",
        f"шкаф-{index}",
    ]


def extract_rows(rows: list[list[str]]) -> list[dict[str, str]]:
    return extractor.extract_items_from_matrices(matrix(rows))


def output_path(tmp_path: Path) -> Path:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return out_dir / "items.csv"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file, delimiter=";"))


def run_cli(input_xls: Path, output_csv: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(input_xls),
            "--output",
            str(output_csv),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def assert_extract_error(rows: list[list[str]], expected: str) -> None:
    try:
        extractor.extract_items_from_matrices(matrix(rows))
    except extractor.LegacyXlsExtractionError as error:
        assert expected in str(error)
    else:
        raise AssertionError("expected LegacyXlsExtractionError")


def test_happy_path_extracts_one_item_row() -> None:
    assert extract_rows([header(), item_row(1)]) == [
        {
            "name": "ВРУ-1",
            "unit": "шт.",
            "quantity": "1",
            "instruments_and_devices": "приборы-1",
            "cabinet_type_dimensions_material": "шкаф-1",
        }
    ]


def test_happy_path_extracts_three_item_rows() -> None:
    rows = extract_rows([header()] + [item_row(index) for index in range(1, 4)])

    assert [row["name"] for row in rows] == ["ВРУ-1", "ВРУ-2", "ВРУ-3"]


def test_happy_path_extracts_100_item_rows() -> None:
    rows = extract_rows([header()] + [item_row(index) for index in range(1, 101)])

    assert len(rows) == 100
    assert rows[-1]["name"] == "ВРУ-100"


def test_fails_when_there_are_zero_item_rows() -> None:
    assert_extract_error([header()], "no item rows found")


def test_fails_when_there_are_101_item_rows() -> None:
    assert_extract_error(
        [header()] + [item_row(index) for index in range(1, 102)],
        "item row count exceeds 100",
    )


def test_fails_when_required_headers_are_missing() -> None:
    assert_extract_error(
        [["Наименование", "Ед. изм.", "Количество"], item_row(1)],
        "missing required headers",
    )


def test_fails_when_quantity_is_not_integer() -> None:
    bad_row = item_row(1)
    bad_row[2] = "1.5"

    assert_extract_error([header(), bad_row], "quantity must be an integer")


def test_fails_on_ambiguous_or_shifted_layout() -> None:
    shifted_row = item_row(1)
    shifted_row[1] = ""

    assert_extract_error(
        [header(), shifted_row],
        "shifted layout or incomplete item row",
    )


def test_fails_when_multiple_plausible_item_tables_are_found() -> None:
    assert_extract_error(
        [header(), item_row(1), [], header(), item_row(2)],
        "multiple plausible item tables detected",
    )


def test_cli_fails_when_output_exists_without_overwriting(tmp_path: Path) -> None:
    input_xls = tmp_path / "legacy.xls"
    output_csv = output_path(tmp_path)
    input_xls.write_text("synthetic placeholder", encoding="utf-8")
    output_csv.write_text("existing", encoding="utf-8")

    result = run_cli(input_xls, output_csv)

    assert result.returncode == 1
    assert "output CSV already exists" in result.stderr
    assert output_csv.read_text(encoding="utf-8") == "existing"


def test_cli_fails_when_output_is_inside_repo(tmp_path: Path) -> None:
    input_xls = tmp_path / "legacy.xls"
    output_csv = PROJECT_ROOT / "legacy_items_should_not_be_written.csv"
    input_xls.write_text("synthetic placeholder", encoding="utf-8")

    result = run_cli(input_xls, output_csv)

    assert result.returncode == 1
    assert "output CSV must be outside the Git project" in result.stderr
    assert not output_csv.exists()


def test_commercial_columns_are_not_exported(tmp_path: Path, monkeypatch: Any) -> None:
    input_xls = tmp_path / "legacy.xls"
    output_csv = output_path(tmp_path)
    input_xls.write_text("synthetic placeholder", encoding="utf-8")
    sheets = matrix(
        [
            header() + ["Цена", "Сумма", "НДС"],
            item_row(1) + ["1000", "1000", "120"],
        ]
    )

    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path / "repo")
    monkeypatch.setattr(extractor, "read_legacy_xls_matrices", lambda _: sheets)
    result = extractor.extract_legacy_xls_items_to_csv(
        input_xls,
        output_csv,
    )

    assert result == output_csv
    assert read_rows(output_csv) == [
        {
            "name": "ВРУ-1",
            "unit": "шт.",
            "quantity": "1",
            "instruments_and_devices": "приборы-1",
            "cabinet_type_dimensions_material": "шкаф-1",
        }
    ]


def test_exact_csv_header_order(tmp_path: Path, monkeypatch: Any) -> None:
    input_xls = tmp_path / "legacy.xls"
    output_csv = output_path(tmp_path)
    input_xls.write_text("synthetic placeholder", encoding="utf-8")
    sheets = matrix([header(), item_row(1)])

    monkeypatch.setattr(extractor, "PROJECT_ROOT", tmp_path / "repo")
    monkeypatch.setattr(extractor, "read_legacy_xls_matrices", lambda _: sheets)
    extractor.extract_legacy_xls_items_to_csv(input_xls, output_csv)

    header_line = output_csv.read_text(encoding="utf-8").splitlines()[0]
    assert (
        header_line == "name;unit;quantity;instruments_and_devices;"
        "cabinet_type_dimensions_material"
    )


def test_prices_sums_vat_total_payment_and_bank_fields_are_ignored() -> None:
    rows = extract_rows(
        [
            header() + ["Цена", "Сумма", "НДС", "Условия оплаты", "Банк"],
            item_row(1) + ["1000", "1000", "120", "предоплата", "банк"],
            ["ИТОГО", "", "", "", "", "", "1000", "120", "", ""],
            ["Банковские реквизиты", "", "", "", "", "", "", "", "", "KZ00"],
        ]
    )

    assert rows == [
        {
            "name": "ВРУ-1",
            "unit": "шт.",
            "quantity": "1",
            "instruments_and_devices": "приборы-1",
            "cabinet_type_dimensions_material": "шкаф-1",
        }
    ]
