import csv
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "compact_invoice_quote_items_csv.py"


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compact = cast(
    Any,
    load_script_module("compact_invoice_quote_items_csv_for_test", SCRIPT),
)


def csv_header() -> str:
    return (
        "name;unit;quantity;instruments_and_devices;"
        "cabinet_type_dimensions_material\n"
    )


def write_input_csv(path: Path, body: str, bom: bool = False) -> None:
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(csv_header() + body, encoding=encoding, newline="")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file, delimiter=";"))


def output_path(tmp_path: Path) -> Path:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return out_dir / "compact.csv"


def run_cli(input_csv: Path, output_csv: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input-csv",
            str(input_csv),
            "--output-csv",
            str(output_csv),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_compacts_text_fields_without_changing_quantity(tmp_path: Path) -> None:
    input_csv = tmp_path / "items.csv"
    output_csv = output_path(tmp_path)
    write_input_csv(
        input_csv,
        (
            '"Щит   управления\n\nнасосами";шт.;001;'
            '"Контроллер\n\n  датчики   давления\nклеммы";'
            '"Шкаф\nнавесной   металл"\n'
        ),
    )

    result = compact.compact_csv(input_csv, output_csv)

    assert result == output_csv
    assert read_rows(output_csv) == [
        {
            "name": "Щит управления насосами",
            "unit": "шт.",
            "quantity": "001",
            "instruments_and_devices": "Контроллер датчики давления клеммы",
            "cabinet_type_dimensions_material": "Шкаф навесной металл",
        }
    ]


def test_cli_supports_bom_input_and_semicolon_quoting(tmp_path: Path) -> None:
    input_csv = tmp_path / "items.csv"
    output_csv = output_path(tmp_path)
    write_input_csv(
        input_csv,
        '"Поле; с разделителем";шт;2;"Прибор\nсвязи";"Шкаф; металл"\n',
        bom=True,
    )

    result = run_cli(input_csv, output_csv)

    assert result.returncode == 0
    assert "CREATED:" in result.stdout
    assert result.stderr == ""
    assert read_rows(output_csv) == [
        {
            "name": "Поле; с разделителем",
            "unit": "шт",
            "quantity": "2",
            "instruments_and_devices": "Прибор связи",
            "cabinet_type_dimensions_material": "Шкаф; металл",
        }
    ]


def assert_compact_error(
    tmp_path: Path,
    csv_text: str | bytes,
    expected: str,
) -> None:
    input_csv = tmp_path / "items.csv"
    output_csv = output_path(tmp_path)
    if isinstance(csv_text, bytes):
        input_csv.write_bytes(csv_text)
    else:
        input_csv.write_text(csv_text, encoding="utf-8", newline="")

    result = run_cli(input_csv, output_csv)

    assert result.returncode == 1
    assert "ERROR:" in result.stderr
    assert expected in result.stderr
    assert not output_csv.exists()


def test_rejects_missing_input_csv(tmp_path: Path) -> None:
    input_csv = tmp_path / "missing.csv"
    output_csv = output_path(tmp_path)

    result = run_cli(input_csv, output_csv)

    assert result.returncode == 1
    assert "input CSV does not exist" in result.stderr
    assert not output_csv.exists()


def test_rejects_existing_output_csv(tmp_path: Path) -> None:
    input_csv = tmp_path / "items.csv"
    output_csv = output_path(tmp_path)
    output_csv.write_text("existing", encoding="utf-8")
    write_input_csv(input_csv, "ВРУ;шт;1;приборы;шкаф\n")

    result = run_cli(input_csv, output_csv)

    assert result.returncode == 1
    assert "output CSV already exists" in result.stderr
    assert output_csv.read_text(encoding="utf-8") == "existing"


def test_rejects_output_inside_git_project(tmp_path: Path) -> None:
    input_csv = tmp_path / "items.csv"
    output_csv = PROJECT_ROOT / "compact_should_not_be_written.csv"
    write_input_csv(input_csv, "ВРУ;шт;1;приборы;шкаф\n")

    result = run_cli(input_csv, output_csv)

    assert result.returncode == 1
    assert "output CSV must be outside the Git project" in result.stderr
    assert not output_csv.exists()


def test_rejects_wrong_header_order(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        (
            "unit;name;quantity;instruments_and_devices;"
            "cabinet_type_dimensions_material\nшт;ВРУ;1;приборы;шкаф\n"
        ),
        "header must exactly match",
    )


def test_rejects_unknown_column(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        csv_header().strip() + ";unknown\nВРУ;шт;1;приборы;шкаф;x\n",
        "unknown columns: unknown",
    )


def test_rejects_commercial_column(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        csv_header().strip() + ";price\nВРУ;шт;1;приборы;шкаф;100\n",
        "forbidden commercial columns: price",
    )


def test_rejects_empty_required_value_after_compaction(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        csv_header() + 'ВРУ;" \n ";1;приборы;шкаф\n',
        "row 2.unit is required",
    )


def test_rejects_invalid_quantity_type(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        csv_header() + "ВРУ;шт;1.5;приборы;шкаф\n",
        "row 2.quantity must be an integer",
    )


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        b"\xff\xfe\x00",
        "items CSV is not valid UTF-8",
    )


def test_rejects_header_without_items(tmp_path: Path) -> None:
    assert_compact_error(
        tmp_path,
        csv_header(),
        "items CSV must contain at least one item",
    )
