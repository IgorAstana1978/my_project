import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from openpyxl import load_workbook  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_BRIDGE_SCRIPT = PROJECT_ROOT / "scripts" / "run_invoice_quote_extended_from_csv.py"
CAPACITY100_SAMPLE_CSV = (
    PROJECT_ROOT / "examples" / "invoice_quote_items_capacity100_sample.csv"
)
ITEMS_BRIDGE_TESTS = (
    PROJECT_ROOT / "tests" / "test_run_invoice_quote_extended_from_items.py"
)
FORBIDDEN_SAMPLE_COMMERCIAL_COLUMNS = {
    "price",
    "price_kzt",
    "sum",
    "vat",
    "currency",
    "term",
    "discount",
    "price_confirmed_by_igor",
}


def load_script_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csv_bridge = cast(
    Any,
    load_script_module(
        "run_invoice_quote_extended_from_csv_for_test",
        CSV_BRIDGE_SCRIPT,
    ),
)
items_bridge_tests = cast(
    Any,
    load_script_module(
        "run_invoice_quote_extended_from_items_helpers_for_csv_test",
        ITEMS_BRIDGE_TESTS,
    ),
)
SHEET_NAME = items_bridge_tests.SHEET_NAME
workbook_value = items_bridge_tests.workbook_value
write_extended_template = items_bridge_tests.write_extended_template


def csv_args(
    items_csv_path: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> list[str]:
    return [
        "--items-csv",
        str(items_csv_path),
        "--template",
        str(template),
        "--template-capacity",
        str(capacity),
        "--output",
        str(output),
    ]


def run_csv_bridge(
    items_csv_path: Path,
    template: Path,
    capacity: int,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CSV_BRIDGE_SCRIPT)]
        + csv_args(items_csv_path, template, capacity, output),
        capture_output=True,
        text=True,
        check=False,
    )


def csv_header() -> str:
    return (
        "name;unit;quantity;instruments_and_devices;"
        "cabinet_type_dimensions_material\n"
    )


def csv_row(index: int) -> str:
    return f"ВРУ-{index};шт.;{index};нужно уточнить;нужно уточнить\n"


def write_items_csv(path: Path, rows: list[str], bom: bool = False) -> None:
    data = csv_header() + "".join(rows)
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(data, encoding=encoding)


def output_path(tmp_path: Path) -> Path:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    return output_dir / "draft.xlsx"


def test_csv_bridge_cli_successfully_runs_six_item_job(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    write_items_csv(items_csv, [csv_row(index) for index in range(1, 7)])

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 0
    assert "CREATED:" in result.stdout
    assert "ERROR:" not in result.stderr
    assert output.is_file()
    assert workbook_value(output, "C22") == "ВРУ-6"
    assert workbook_value(output, "H17") == "нужно уточнить"


def test_csv_bridge_supports_bom_and_russian_values(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    write_items_csv(
        items_csv,
        ["Щит освещения 0012;компл.;2;Автоматы;Шкаф навесной\n"],
        bom=True,
    )

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 0
    assert output.is_file()
    assert workbook_value(output, "C17") == "Щит освещения 0012"
    assert workbook_value(output, "D17") == "компл."
    assert workbook_value(output, "E17") == 2


def test_csv_bridge_supports_quoted_semicolon_quotes_and_newline(
    tmp_path: Path,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    items_csv.write_text(
        csv_header()
        + 'ВРУ-1;шт.;1;"автомат; клеммы ""N""\nвторая строка";"600x400; металл"\n',
        encoding="utf-8",
        newline="",
    )

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 0
    assert output.is_file()
    assert workbook_value(output, "F17") == 'автомат; клеммы "N"\nвторая строка'
    assert workbook_value(output, "G17") == "600x400; металл"


def test_csv_bridge_preserves_string_values_like_0012(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    write_items_csv(items_csv, ["0012;шт.;1;приборы;шкаф\n"])

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 0
    assert output.is_file()
    assert workbook_value(output, "C17") == "0012"


def test_csv_bridge_successfully_runs_fifty_item_job(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template, capacity=50)
    write_items_csv(items_csv, [csv_row(index) for index in range(1, 51)])

    result = run_csv_bridge(items_csv, template, 50, output)

    assert result.returncode == 0
    assert "CREATED:" in result.stdout
    assert output.is_file()
    assert workbook_value(output, "C66") == "ВРУ-50"
    assert workbook_value(output, "I67") == "=SUM(I17:I66)"


def test_capacity100_sample_csv_contract_and_adapter_path(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    output = output_path(tmp_path)
    captured: dict[str, Any] = {}
    sample_text = CAPACITY100_SAMPLE_CSV.read_text(encoding="utf-8-sig")
    rows = list(
        csv.reader(
            sample_text.splitlines(keepends=True),
            delimiter=";",
            strict=True,
        )
    )
    header = rows[0]
    records = rows[1:]

    assert ";".join(header) == csv_header().strip()
    assert not FORBIDDEN_SAMPLE_COMMERCIAL_COLUMNS.intersection(header)
    assert len(records) == 7
    assert all(len(record) == len(header) for record in records)
    assert all(isinstance(int(record[2]), int) for record in records)
    assert any(";" in value for record in records for value in record)
    assert any("\n" in value for record in records for value in record)

    def fake_run_items_bridge(
        items_json: Path,
        template: Path,
        capacity: int,
        output: Path,
    ) -> subprocess.CompletedProcess[str]:
        captured["items_json"] = json.loads(items_json.read_text(encoding="utf-8"))
        captured["template"] = template
        captured["capacity"] = capacity
        captured["output"] = output
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="CREATED\n")

    monkeypatch.setattr(csv_bridge, "run_items_bridge", fake_run_items_bridge)

    exit_code = csv_bridge.main(csv_args(CAPACITY100_SAMPLE_CSV, template, 100, output))

    assert exit_code == 0
    assert captured["template"] == template
    assert captured["capacity"] == 100
    assert captured["output"] == output
    assert len(captured["items_json"]["items"]) == 7


def test_csv_bridge_invokes_existing_items_bridge(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    captured: dict[str, Any] = {}
    write_extended_template(template)
    write_items_csv(items_csv, ["ВРУ;шт.;3;приборы;шкаф\n"])

    def fake_run_items_bridge(
        items_json: Path,
        template: Path,
        capacity: int,
        output: Path,
    ) -> subprocess.CompletedProcess[str]:
        captured["items_json"] = json.loads(items_json.read_text(encoding="utf-8"))
        captured["template"] = template
        captured["capacity"] = capacity
        captured["output"] = output
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="CREATED\n")

    monkeypatch.setattr(csv_bridge, "run_items_bridge", fake_run_items_bridge)

    exit_code = csv_bridge.main(csv_args(items_csv, template, 8, output))

    assert exit_code == 0
    assert captured["template"] == template
    assert captured["capacity"] == 8
    assert captured["output"] == output
    assert captured["items_json"] == {
        "items": [
            {
                "name": "ВРУ",
                "unit": "шт.",
                "quantity": 3,
                "instruments_and_devices": "приборы",
                "cabinet_type_dimensions_material": "шкаф",
                "price_kzt": None,
                "price_confirmed_by_igor": False,
            }
        ]
    }


def test_csv_bridge_cleans_temp_items_after_success(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    temp_parent = tmp_path / "csv-temp"
    temp_parent.mkdir()
    output = output_path(tmp_path)
    created_dirs: list[Path] = []
    write_extended_template(template)
    write_items_csv(items_csv, [csv_row(1)])

    def temporary_directory(*args: Any, **kwargs: Any) -> Any:
        kwargs["dir"] = temp_parent
        manager = tempfile.TemporaryDirectory(*args, **kwargs)
        created_dirs.append(Path(manager.name))
        return manager

    def fake_run_items_bridge(
        items_json: Path,
        template: Path,
        capacity: int,
        output: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert items_json.is_file()
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="CREATED\n")

    monkeypatch.setattr(csv_bridge, "TEMPORARY_DIRECTORY", temporary_directory)
    monkeypatch.setattr(csv_bridge, "run_items_bridge", fake_run_items_bridge)

    exit_code = csv_bridge.main(csv_args(items_csv, template, 8, output))

    assert exit_code == 0
    assert created_dirs
    assert all(not path.exists() for path in created_dirs)
    assert list(temp_parent.iterdir()) == []


def test_csv_bridge_cleans_temp_items_after_downstream_error(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    temp_parent = tmp_path / "csv-temp"
    temp_parent.mkdir()
    output = output_path(tmp_path)
    created_dirs: list[Path] = []
    write_extended_template(template)
    write_items_csv(items_csv, [csv_row(1)])

    def temporary_directory(*args: Any, **kwargs: Any) -> Any:
        kwargs["dir"] = temp_parent
        manager = tempfile.TemporaryDirectory(*args, **kwargs)
        created_dirs.append(Path(manager.name))
        return manager

    def fake_run_items_bridge(
        items_json: Path,
        template: Path,
        capacity: int,
        output: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert items_json.is_file()
        return subprocess.CompletedProcess(args=[], returncode=1, stderr="ERROR\n")

    monkeypatch.setattr(csv_bridge, "TEMPORARY_DIRECTORY", temporary_directory)
    monkeypatch.setattr(csv_bridge, "run_items_bridge", fake_run_items_bridge)

    exit_code = csv_bridge.main(csv_args(items_csv, template, 8, output))

    assert exit_code == 1
    assert created_dirs
    assert all(not path.exists() for path in created_dirs)
    assert list(temp_parent.iterdir()) == []
    assert not output.exists()
    assert list(output.parent.iterdir()) == []


def assert_csv_error(
    tmp_path: Path,
    csv_text: str | bytes,
    expected: str,
    capacity: int = 8,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template, capacity=max(capacity, 1))
    if isinstance(csv_text, bytes):
        items_csv.write_bytes(csv_text)
    else:
        items_csv.write_text(csv_text, encoding="utf-8", newline="")

    result = run_csv_bridge(items_csv, template, capacity, output)

    assert result.returncode == 1
    assert expected in result.stderr
    assert not output.exists()
    assert list(output.parent.iterdir()) == []


def test_csv_bridge_rejects_empty_csv(tmp_path: Path) -> None:
    assert_csv_error(tmp_path, "", "items CSV must not be empty")


def test_csv_bridge_missing_items_csv_returns_one_without_output(
    tmp_path: Path,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "missing.csv"
    output = output_path(tmp_path)
    write_extended_template(template)

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 1
    assert "items CSV does not exist" in result.stderr
    assert not output.exists()
    assert list(output.parent.iterdir()) == []


def test_csv_bridge_rejects_header_without_items(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header(),
        "items CSV must contain at least one item",
    )


def test_csv_bridge_rejects_missing_required_column(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        "name;unit;quantity;instruments_and_devices\nВРУ;шт.;1;приборы\n",
        "missing required columns: cabinet_type_dimensions_material",
    )


def test_csv_bridge_rejects_unknown_column(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header().strip() + ";unknown\nВРУ;шт.;1;приборы;шкаф;x\n",
        "unknown columns: unknown",
    )


def test_csv_bridge_rejects_commercial_column(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header().strip() + ";price\nВРУ;шт.;1;приборы;шкаф;100\n",
        "forbidden commercial columns: price",
    )


def test_csv_bridge_rejects_duplicate_header(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        (
            "name;unit;quantity;instruments_and_devices;"
            "cabinet_type_dimensions_material;name\n"
            "ВРУ;шт.;1;приборы;шкаф;дубль\n"
        ),
        "duplicate columns: name",
    )


def test_csv_bridge_rejects_empty_header(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        "name;unit;;instruments_and_devices;cabinet_type_dimensions_material\n",
        "empty column name",
    )


def test_csv_bridge_rejects_wrong_field_count(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header() + "ВРУ;шт.;1;приборы;шкаф;extra\n",
        "row 2 has 6 fields; expected 5",
    )


def test_csv_bridge_rejects_empty_required_value(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header() + "ВРУ;шт.;;приборы;шкаф\n",
        "row 2.quantity is required",
    )


def test_csv_bridge_rejects_whitespace_only_required_string_value(
    tmp_path: Path,
) -> None:
    assert_csv_error(
        tmp_path,
        csv_header() + 'ВРУ;" \t\n ";1;приборы;шкаф\n',
        "row 2.unit is required",
    )


def test_csv_bridge_rejects_invalid_quantity_type(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header() + "ВРУ;шт.;1.5;приборы;шкаф\n",
        "row 2.quantity must be an integer",
    )


def test_csv_bridge_rejects_invalid_utf8(tmp_path: Path) -> None:
    assert_csv_error(tmp_path, b"\xff\xfe\x00", "items CSV is not valid UTF-8")


def test_csv_bridge_rejects_items_above_template_capacity(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header() + "".join(csv_row(index) for index in range(1, 4)),
        "items count 3 exceeds template capacity 2",
        capacity=2,
    )


def test_csv_bridge_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    output.write_bytes(b"existing")
    write_extended_template(template)
    write_items_csv(items_csv, [csv_row(1)])

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 1
    assert "ERROR:" in result.stderr
    assert "output already exists" in result.stderr
    assert output.read_bytes() == b"existing"
    assert list(output.parent.iterdir()) == [output]


def test_csv_bridge_downstream_error_returns_one_without_partial_output(
    tmp_path: Path,
) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_items_csv(items_csv, [csv_row(1)])

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 1
    assert "ERROR:" in result.stderr
    assert "template does not exist" in result.stderr
    assert not output.exists()
    assert list(output.parent.iterdir()) == []


def test_csv_bridge_rejects_price_confirmation_column(tmp_path: Path) -> None:
    assert_csv_error(
        tmp_path,
        csv_header().strip()
        + ";price_confirmed_by_igor\nВРУ;шт.;1;приборы;шкаф;false\n",
        "forbidden commercial columns: price_confirmed_by_igor",
    )


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


def test_csv_bridge_does_not_write_commercial_price_to_excel(tmp_path: Path) -> None:
    template = tmp_path / "extended_template.xlsx"
    items_csv = tmp_path / "items.csv"
    output = output_path(tmp_path)
    write_extended_template(template)
    write_items_csv(items_csv, ["ВРУ;шт.;1;приборы;шкаф\n"])

    result = run_csv_bridge(items_csv, template, 8, output)

    assert result.returncode == 0
    workbook = load_workbook(output, data_only=False)
    worksheet = workbook[SHEET_NAME]
    assert worksheet["H17"].value == "нужно уточнить"
